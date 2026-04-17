"""P1 tests: retention sweeper drops rows older than the configured window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from bsela.core.retention import sweep, sweep_errors, sweep_sessions
from bsela.memory.models import ErrorRecord, Metric, SessionRecord
from bsela.memory.store import (
    count_sessions,
    list_errors,
    list_metrics,
    save_error,
    save_metric,
    save_session,
)


def _session(ingested_at: datetime) -> SessionRecord:
    return save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/x.jsonl",
            content_hash="h",
            ingested_at=ingested_at,
        )
    )


def test_sweep_errors_drops_only_old(tmp_bsela_home: Path) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sess = _session(now)
    old = save_error(
        ErrorRecord(
            session_id=sess.id,
            category="loop",
            snippet="x",
            detected_at=now - timedelta(days=120),
        )
    )
    fresh = save_error(
        ErrorRecord(
            session_id=sess.id,
            category="loop",
            snippet="y",
            detected_at=now - timedelta(days=10),
        )
    )
    deleted = sweep_errors(days=90, now=now)
    assert deleted == 1
    remaining = {e.id for e in list_errors()}
    assert remaining == {fresh.id}
    assert old.id not in remaining


def test_sweep_sessions_cascades_to_errors_and_metrics(tmp_bsela_home: Path) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    old_sess = _session(now - timedelta(days=120))
    new_sess = _session(now - timedelta(days=5))
    save_error(
        ErrorRecord(
            session_id=old_sess.id,
            category="loop",
            snippet="x",
            detected_at=now - timedelta(days=119),
        )
    )
    save_metric(Metric(session_id=old_sess.id, stage="ingest", tokens_in=1, tokens_out=1))

    deleted = sweep_sessions(days=90, now=now)

    assert deleted == 1
    assert count_sessions() == 1
    assert list_errors(session_id=old_sess.id) == []
    assert list_metrics(session_id=old_sess.id) == []
    assert list_metrics(session_id=new_sess.id) == []  # never had any


def test_sweep_uses_thresholds_config(tmp_bsela_home: Path) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sess = _session(now - timedelta(days=200))
    save_error(
        ErrorRecord(
            session_id=sess.id,
            category="loop",
            snippet="x",
            detected_at=now - timedelta(days=200),
        )
    )
    result = sweep(now=now)
    assert result.sessions_deleted == 1
    assert result.errors_deleted == 1
