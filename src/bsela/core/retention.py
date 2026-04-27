"""Retention sweeper: drop stale sessions + errors per thresholds.toml.

Session deletion also drops the ``errors``, ``metrics``, and
``replay_records`` rows that reference the removed sessions (explicit
iteration, not FK cascade). Called from ``bsela prune`` and can be
scheduled via ``launchd`` alongside the weekly auditor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import col, select

from bsela.memory.models import ErrorRecord, Metric, ReplayRecord, SessionRecord
from bsela.memory.store import session_scope
from bsela.utils.config import load_thresholds


@dataclass(frozen=True)
class SweepResult:
    sessions_deleted: int
    errors_deleted: int
    replay_records_deleted: int = 0


def _cutoff(days: int, now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=days)


def sweep_errors(*, days: int, now: datetime | None = None) -> int:
    """Delete error rows older than ``days``. Returns count removed."""
    cutoff = _cutoff(days, now)
    with session_scope() as s:
        stale = list(s.exec(select(ErrorRecord).where(ErrorRecord.detected_at < cutoff)).all())
        for err in stale:
            s.delete(err)
        s.commit()
        return len(stale)


def sweep_sessions(*, days: int, now: datetime | None = None) -> int:
    """Delete session rows older than ``days`` and their dependents.

    Also deletes associated ``errors``, ``metrics``, and ``replay_records``
    to prevent orphaned rows accumulating after a prune.

    Returns the number of sessions deleted.
    """
    sessions_deleted, _ = _sweep_sessions_full(days=days, now=now)
    return sessions_deleted


def _sweep_sessions_full(*, days: int, now: datetime | None = None) -> tuple[int, int]:
    """Delete stale sessions and all dependents; return (sessions, replay_records)."""
    cutoff = _cutoff(days, now)
    with session_scope() as s:
        stale = list(s.exec(select(SessionRecord).where(SessionRecord.ingested_at < cutoff)).all())
        if not stale:
            return 0, 0
        ids = {sess.id for sess in stale}
        dep_errors = s.exec(select(ErrorRecord).where(col(ErrorRecord.session_id).in_(ids))).all()
        dep_metrics = s.exec(select(Metric).where(col(Metric.session_id).in_(ids))).all()
        dep_replays = list(
            s.exec(select(ReplayRecord).where(col(ReplayRecord.session_id).in_(ids))).all()
        )
        for err in dep_errors:
            s.delete(err)
        for metric in dep_metrics:
            s.delete(metric)
        for replay in dep_replays:
            s.delete(replay)
        for sess in stale:
            s.delete(sess)
        s.commit()
        return len(stale), len(dep_replays)


def sweep(*, now: datetime | None = None) -> SweepResult:
    """Run both sweepers using retention windows from ``thresholds.toml``."""
    retention = load_thresholds().retention
    errors_deleted = sweep_errors(days=retention.error_days, now=now)
    sessions_deleted, replay_records_deleted = _sweep_sessions_full(
        days=retention.session_days, now=now
    )
    return SweepResult(
        sessions_deleted=sessions_deleted,
        errors_deleted=errors_deleted,
        replay_records_deleted=replay_records_deleted,
    )


__all__ = ["SweepResult", "sweep", "sweep_errors", "sweep_sessions"]
