"""Codex rollout sweep — backfill capture for sessions no hook observed.

The Codex hook fires at session end; a crashed editor, an ``codex exec`` run
with ``notify`` disabled, or a session from before the hook existed leaves the
rollout on disk with nothing in the store. :func:`scan_rollouts` walks the
Codex rollout roots and ingests whatever is new or has grown, newest first.

Re-ingest uses ``replace`` semantics so one rollout stays one session row no
matter how often the sweep runs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bsela.adapters.codex import SOURCE as CODEX_SOURCE
from bsela.adapters.codex import discover_rollouts
from bsela.core.capture import CaptureResult, ingest_file

_log = logging.getLogger(__name__)

DEFAULT_SINCE_DAYS = 14
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class ScanOutcome:
    """One rollout's disposition within a sweep."""

    path: Path
    status: str  # captured | updated | unchanged | quarantined | skipped | error
    session_id: str | None = None
    turn_count: int = 0
    tool_call_count: int = 0
    errors_detected: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class ScanResult:
    considered: int
    captured: int
    updated: int
    unchanged: int
    quarantined: int
    skipped: int
    failed: int
    errors_detected: int
    outcomes: list[ScanOutcome] = field(default_factory=list)


def _cutoff(since_days: int, now: datetime | None) -> datetime | None:
    if since_days <= 0:
        return None
    return (now or datetime.now(UTC)) - timedelta(days=since_days)


def _status_for(result: CaptureResult) -> str:
    """Map a ``CaptureResult`` onto a sweep status label."""
    if result.skipped_reason:
        return "skipped"
    if result.unchanged:
        return "unchanged"
    if result.status == "quarantined":
        return "quarantined"
    return "updated" if result.updated else "captured"


def scan_rollouts(
    *,
    roots: Iterable[Path] | None = None,
    since_days: int = DEFAULT_SINCE_DAYS,
    limit: int | None = DEFAULT_LIMIT,
    replace: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ScanResult:
    """Ingest new or grown Codex rollouts, newest first.

    ``dry_run`` reports the same selection without touching the store; the
    caller sees ``status`` labels only, no session ids or counts.
    """
    paths = discover_rollouts(roots, since=_cutoff(since_days, now), limit=limit)
    outcomes: list[ScanOutcome] = []
    counts: dict[str, int] = {
        "captured": 0,
        "updated": 0,
        "unchanged": 0,
        "quarantined": 0,
        "skipped": 0,
        "error": 0,
    }
    errors_detected = 0

    for path in paths:
        if dry_run:
            outcomes.append(ScanOutcome(path=path, status="pending"))
            continue
        try:
            result = ingest_file(path, source=CODEX_SOURCE, replace=replace)
        except (OSError, ValueError) as exc:  # a locked or vanished rollout
            _log.warning("scan could not ingest %s: %s", path, exc)
            counts["error"] += 1
            outcomes.append(ScanOutcome(path=path, status="error", detail=str(exc)))
            continue
        status = _status_for(result)
        counts[status] += 1
        errors_detected += result.errors_detected
        outcomes.append(
            ScanOutcome(
                path=path,
                status=status,
                session_id=None if status == "skipped" else result.session_id,
                turn_count=result.turn_count,
                tool_call_count=result.tool_call_count,
                errors_detected=result.errors_detected,
                detail=result.skipped_reason,
            )
        )

    return ScanResult(
        considered=len(paths),
        captured=counts["captured"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        quarantined=counts["quarantined"],
        skipped=counts["skipped"],
        failed=counts["error"],
        errors_detected=errors_detected,
        outcomes=outcomes,
    )


__all__ = ["DEFAULT_LIMIT", "DEFAULT_SINCE_DAYS", "ScanOutcome", "ScanResult", "scan_rollouts"]
