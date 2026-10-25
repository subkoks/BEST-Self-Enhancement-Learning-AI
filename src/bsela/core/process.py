"""Batch distillation over recent captured sessions.

``bsela process`` turns accumulated captures into lesson candidates with
a single command. The distiller charges LLM tokens, so the pipeline
stays manual by design — the hook-driven capture path only runs the
free deterministic detector (see ``bsela.core.capture.ingest_file``).

Skips are explicit so the operator can see why a session was ignored:

* ``quarantined``          — captured with a secret hit; never distilled.
* ``no_errors``            — detector produced zero ``ErrorRecord`` rows.
* ``already_distilled``    — a Lesson already references one of this
  session's errors (idempotent reruns).
* ``judge_healthy``        — selected judge says ``goal_achieved`` +
  high confidence; nothing to learn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from bsela.llm.client import LLMClient
from bsela.llm.distiller import DistillationResult, distill_session, evaluation_fingerprint
from bsela.llm.runtime import ProviderError
from bsela.memory.models import SessionRecord
from bsela.memory.store import (
    has_evaluation,
    has_session_evaluation,
    list_errors,
    list_sessions_with_errors,
    session_has_lessons,
)

_log = logging.getLogger(__name__)

DEFAULT_LIMIT = 10
DEFAULT_SINCE_DAYS = 7


@dataclass(frozen=True)
class SessionOutcome:
    """One row in a ``ProcessResult``: why a session landed where it did."""

    session_id: str
    status: str
    lessons_created: int = 0
    turn_count: int = 0  # populated in dry-run mode for the preview table
    detail: str = ""


@dataclass(frozen=True)
class ProcessResult:
    considered: int
    processed: int
    distilled: int
    lessons_created: int
    skipped_quarantined: int
    skipped_no_errors: int
    skipped_already_distilled: int
    skipped_judge_healthy: int
    errors: int
    outcomes: list[SessionOutcome] = field(default_factory=list)
    skipped_already_evaluated: int = 0


def _is_within_window(session: SessionRecord, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    ingested = session.ingested_at
    if ingested.tzinfo is None:
        ingested = ingested.replace(tzinfo=UTC)
    return ingested >= cutoff


def _is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        isinstance(exc, ProviderError)
        or "credit" in msg
        or "billing" in msg
        or "authentication" in msg
    )


def _safe_failure_detail(exc: Exception) -> str:
    """Only fixed operator text; never echo a provider response or transcript."""
    if not isinstance(exc, ProviderError):
        return "unexpected processing failure"
    message = str(exc)
    if message == "codex invocation failed or timed out":
        return "Codex invocation failed or timed out"
    for prefix, detail in (
        ("auth:", "provider authentication failed"),
        ("quota:", "provider quota unavailable"),
        ("isolation:", "provider isolation check failed"),
        ("model:", "provider model request failed"),
        ("invalid", "provider response failed validation"),
        ("run deadline", "total run deadline exceeded"),
    ):
        if message.startswith(prefix):
            return detail
    return "provider request failed"


def process_sessions(
    *,
    client: LLMClient | None = None,
    limit: int = DEFAULT_LIMIT,
    since_days: int | None = DEFAULT_SINCE_DAYS,
    skip_already_distilled: bool = True,
    persist: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
    provider: str = "codex",
) -> ProcessResult:
    """Distill up to ``limit`` captured sessions ingested within the window.

    ``since_days=None`` disables the time filter. Quarantined sessions
    are never considered because ``list_sessions(status='captured')``
    filters them out at the SQL layer.

    When ``dry_run=True`` no LLM calls are made and the store is not
    mutated. ``client`` is unused and may be ``None``. Outcomes use
    ``would_distill`` / ``would_skip_already_distilled`` statuses and
    ``lessons_created`` holds the error count as an estimate.
    """
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=since_days) if since_days is not None else None

    # Only fetch sessions that already have errors — avoids scanning clean sessions
    # and allows the limit to represent actual work, not wasted no-error skips.
    candidates = [
        session
        for session in list_sessions_with_errors(status="captured", limit=None)
        if _is_within_window(session, cutoff)
    ]
    outcomes: list[SessionOutcome] = []
    processed = distilled = lessons_created = 0
    skipped_no_errors = skipped_already = skipped_healthy = errors_count = 0
    skipped_evaluated = 0

    for session in candidates:
        if processed >= limit:
            break
        errs = list_errors(session_id=session.id, limit=50)
        if not errs:
            # Shouldn't happen, but guard anyway
            skipped_no_errors += 1
            outcomes.append(SessionOutcome(session.id, "no_errors"))
            continue

        if skip_already_distilled and has_evaluation(
            evaluation_fingerprint(session, errs, client=client, provider=provider)
        ):
            skipped_evaluated += 1
            status = "would_skip_already_evaluated" if dry_run else "already_evaluated"
            outcomes.append(SessionOutcome(session.id, status, turn_count=session.turn_count))
            continue

        # Preserve legacy lesson-based skips when no content-aware checkpoint
        # exists. Once tracked, grown content is eligible even if it has lessons.
        if (
            skip_already_distilled
            and session_has_lessons(session.id)
            and not has_session_evaluation(session.id)
        ):
            skipped_already += 1
            status = "would_skip_already_distilled" if dry_run else "already_distilled"
            outcomes.append(SessionOutcome(session.id, status, turn_count=session.turn_count))
            continue

        if dry_run:
            distilled += 1
            estimated = len(errs)
            lessons_created += estimated
            outcomes.append(
                SessionOutcome(
                    session.id,
                    "would_distill",
                    lessons_created=estimated,
                    turn_count=session.turn_count,
                )
            )
            processed += 1
            continue

        try:
            result: DistillationResult = distill_session(session.id, client=client, persist=persist)  # type: ignore[arg-type]
        except Exception as exc:
            detail = _safe_failure_detail(exc)
            _log.warning("distill failed for %s: %s", session.id[:8], detail)
            errors_count += 1
            outcomes.append(
                SessionOutcome(
                    session.id,
                    "provider_failure" if isinstance(exc, ProviderError) else "error",
                    detail=detail,
                )
            )
            processed += 1
            if _is_billing_error(exc):
                break
            continue

        if result.outcome == "judge_healthy":
            skipped_healthy += 1

        created = len(result.persisted)
        distilled += int(result.distilled)
        lessons_created += created
        outcomes.append(SessionOutcome(session.id, result.outcome, lessons_created=created))
        processed += 1

    return ProcessResult(
        considered=len(candidates),
        processed=processed,
        distilled=distilled,
        lessons_created=lessons_created,
        skipped_quarantined=0,
        skipped_no_errors=skipped_no_errors,
        skipped_already_distilled=skipped_already,
        skipped_judge_healthy=skipped_healthy,
        errors=errors_count,
        outcomes=outcomes,
        skipped_already_evaluated=skipped_evaluated,
    )


__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_SINCE_DAYS",
    "ProcessResult",
    "SessionOutcome",
    "process_sessions",
]
