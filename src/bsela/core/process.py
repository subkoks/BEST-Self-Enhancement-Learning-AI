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
* ``judge_healthy``        — Haiku judge says ``goal_achieved`` +
  high confidence; nothing to learn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from bsela.llm.client import LLMClient
from bsela.llm.distiller import DistillationResult, distill_session
from bsela.memory.models import SessionRecord
from bsela.memory.store import (
    list_errors,
    list_sessions,
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


def _is_within_window(session: SessionRecord, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    ingested = session.ingested_at
    if ingested.tzinfo is None:
        ingested = ingested.replace(tzinfo=UTC)
    return ingested >= cutoff


def process_sessions(
    *,
    client: LLMClient,
    limit: int = DEFAULT_LIMIT,
    since_days: int | None = DEFAULT_SINCE_DAYS,
    skip_already_distilled: bool = True,
    persist: bool = True,
    now: datetime | None = None,
) -> ProcessResult:
    """Distill up to ``limit`` captured sessions ingested within the window.

    ``since_days=None`` disables the time filter. Quarantined sessions
    are never considered because ``list_sessions(status='captured')``
    filters them out at the SQL layer.
    """
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=since_days) if since_days is not None else None

    # Only fetch sessions that already have errors — avoids scanning clean sessions
    # and allows the limit to represent actual work, not wasted no-error skips.
    candidates = list_sessions_with_errors(status="captured", limit=max(limit * 3, limit))
    outcomes: list[SessionOutcome] = []
    processed = 0
    distilled = 0
    lessons_created = 0
    skipped_no_errors = 0
    skipped_already = 0
    skipped_healthy = 0
    errors_count = 0

    for session in candidates:
        if processed >= limit:
            break
        if not _is_within_window(session, cutoff):
            continue

        errs = list_errors(session_id=session.id, limit=50)
        if not errs:
            # Shouldn't happen, but guard anyway
            skipped_no_errors += 1
            outcomes.append(SessionOutcome(session.id, "no_errors"))
            continue

        if skip_already_distilled and session_has_lessons(session.id):
            skipped_already += 1
            outcomes.append(SessionOutcome(session.id, "already_distilled"))
            processed += 1
            continue

        try:
            result: DistillationResult = distill_session(session.id, client=client, persist=persist)
        except Exception as exc:
            _log.warning("distill failed for %s: %s", session.id[:8], exc)
            errors_count += 1
            outcomes.append(SessionOutcome(session.id, "error"))
            processed += 1
            # Propagate billing / auth errors immediately — no point processing more
            err_str = str(exc).lower()
            if "credit" in err_str or "billing" in err_str or "authentication" in err_str:
                break
            continue

        if not result.distilled:
            skipped_healthy += 1
            outcomes.append(SessionOutcome(session.id, "judge_healthy"))
            processed += 1
            continue

        created = len(result.persisted)
        distilled += 1
        lessons_created += created
        outcomes.append(SessionOutcome(session.id, "distilled", lessons_created=created))
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
    )


__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_SINCE_DAYS",
    "ProcessResult",
    "SessionOutcome",
    "process_sessions",
]
