"""Retention sweeper: drop stale sessions + errors per thresholds.toml.

Session deletion also drops the ``errors`` and ``metrics`` rows that
reference the removed sessions (V1: explicit iteration, not FK cascade).
Called from ``bsela prune`` and can be scheduled via ``launchd`` alongside
the weekly auditor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from bsela.memory.models import ErrorRecord, Metric, SessionRecord
from bsela.memory.store import session_scope
from bsela.utils.config import load_thresholds


@dataclass(frozen=True)
class SweepResult:
    sessions_deleted: int
    errors_deleted: int


def _cutoff(days: int, now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=days)


def sweep_errors(*, days: int, now: datetime | None = None) -> int:
    """Delete error rows older than ``days``. Returns count removed."""
    cutoff = _cutoff(days, now)
    with session_scope() as s:
        stale = list(s.exec(select(ErrorRecord).where(ErrorRecord.detected_at < cutoff)).all())
        for row in stale:
            s.delete(row)
        s.commit()
        return len(stale)


def sweep_sessions(*, days: int, now: datetime | None = None) -> int:
    """Delete session rows older than ``days`` and their dependents."""
    cutoff = _cutoff(days, now)
    with session_scope() as s:
        stale = list(s.exec(select(SessionRecord).where(SessionRecord.ingested_at < cutoff)).all())
        if not stale:
            return 0
        ids = {row.id for row in stale}
        dependents_errors = s.exec(select(ErrorRecord).where(ErrorRecord.session_id.in_(ids))).all()
        dependents_metrics = s.exec(select(Metric).where(Metric.session_id.in_(ids))).all()
        for row in dependents_errors:
            s.delete(row)
        for row in dependents_metrics:
            s.delete(row)
        for row in stale:
            s.delete(row)
        s.commit()
        return len(stale)


def sweep(*, now: datetime | None = None) -> SweepResult:
    """Run both sweepers using retention windows from ``thresholds.toml``."""
    retention = load_thresholds().retention
    errors_deleted = sweep_errors(days=retention.error_days, now=now)
    sessions_deleted = sweep_sessions(days=retention.session_days, now=now)
    return SweepResult(sessions_deleted=sessions_deleted, errors_deleted=errors_deleted)


__all__ = ["SweepResult", "sweep", "sweep_errors", "sweep_sessions"]
