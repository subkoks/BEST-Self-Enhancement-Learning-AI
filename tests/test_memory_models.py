"""P1 tests: each SQLModel table round-trips through SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsela.memory.models import Decision, ErrorRecord, Lesson, Metric, ReplayRecord, SessionRecord
from bsela.memory.store import (
    get_lesson,
    get_session,
    increment_hit_count,
    list_decisions,
    list_errors,
    list_lessons,
    list_metrics,
    list_replay_records,
    list_sessions,
    list_sessions_with_errors,
    save_decision,
    save_error,
    save_lesson,
    save_metric,
    save_replay_record,
    save_session,
    update_lesson_status,
)


def test_session_roundtrip(tmp_bsela_home: Path) -> None:
    assert tmp_bsela_home.exists()
    saved = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/x.jsonl",
            content_hash="deadbeef",
            turn_count=4,
            tool_call_count=2,
        )
    )
    assert saved.id
    fetched = get_session(saved.id)
    assert fetched is not None
    assert fetched.source == "claude_code"
    assert fetched.status == "captured"
    assert [s.id for s in list_sessions()] == [saved.id]


def test_error_fk_to_session(tmp_bsela_home: Path) -> None:
    session = save_session(
        SessionRecord(source="claude_code", transcript_path="/tmp/y.jsonl", content_hash="abc")
    )
    err = save_error(
        ErrorRecord(
            session_id=session.id,
            category="correction",
            snippet="no wait",
        )
    )
    assert err.id
    errors = list_errors(session_id=session.id)
    assert [e.id for e in errors] == [err.id]


def test_lesson_and_decision_and_metric(tmp_bsela_home: Path) -> None:
    lesson = save_lesson(
        Lesson(
            scope="project",
            rule="Always run ruff before commit",
            why="Keeps CI green",
            how_to_apply="Run 'ruff check .' prior to 'git commit'",
            confidence=0.95,
        )
    )
    decision = save_decision(
        Decision(
            title="Use SQLite",
            context="Local-first storage",
            decision="Adopt SQLite + SQLModel",
            consequences="Single-process only",
        )
    )
    metric = save_metric(
        Metric(stage="ingest", tokens_in=10, tokens_out=20, cost_usd=0.0001, duration_ms=12)
    )

    assert [lesson.id] == [row.id for row in list_lessons(scope="project")]
    assert [decision.id] == [row.id for row in list_decisions()]
    assert [metric.id] == [row.id for row in list_metrics(stage="ingest")]


def test_get_lesson_returns_none_for_unknown_id(tmp_bsela_home: Path) -> None:
    assert get_lesson("does-not-exist") is None


def test_update_lesson_status_transitions_and_notes(tmp_bsela_home: Path) -> None:
    lesson = save_lesson(
        Lesson(
            scope="project",
            rule="Run ruff before commit",
            why="Keep CI green",
            how_to_apply="Before every commit",
            confidence=0.9,
        )
    )
    updated = update_lesson_status(lesson.id, status="approved", note="matches repo policy")
    assert updated.status == "approved"
    assert updated.updated_at >= lesson.updated_at
    assert "-- review note --" in updated.how_to_apply
    assert "matches repo policy" in updated.how_to_apply


def test_update_lesson_status_raises_for_missing(tmp_bsela_home: Path) -> None:
    with pytest.raises(LookupError):
        update_lesson_status("missing", status="rejected")


# ---- store branch-coverage helpers ----


def test_list_sessions_with_errors_no_status_no_limit(tmp_bsela_home: Path) -> None:
    """Cover lines 121→123 False + 123→125 False: status=None, limit=None."""
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h1",
        )
    )
    save_error(ErrorRecord(session_id=sess.id, category="loop", snippet="x"))
    rows = list_sessions_with_errors(status=None, limit=None)
    assert any(r.id == sess.id for r in rows)


def test_list_decisions_no_limit(tmp_bsela_home: Path) -> None:
    """Cover line 254→256 False: limit=None skips stmt.limit()."""
    save_decision(
        Decision(
            title="Use SQLite",
            context="Local-first",
            decision="Adopt SQLite",
            consequences="Single-process",
        )
    )
    rows = list_decisions(limit=None)
    assert len(rows) >= 1


def test_list_metrics_no_limit(tmp_bsela_home: Path) -> None:
    """Cover line 282→284 False: limit=None skips stmt.limit()."""
    save_metric(Metric(stage="test", cost_usd=0.01))
    rows = list_metrics(limit=None)
    assert len(rows) >= 1


def test_list_replay_records_with_window_days(tmp_bsela_home: Path) -> None:
    """Cover lines 306-307: window_days is not None → cutoff filter applied."""
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h2",
        )
    )
    save_replay_record(ReplayRecord(session_id=sess.id, had_drift=False))
    rows = list_replay_records(window_days=7)
    assert len(rows) >= 1


def test_increment_hit_count_updates_lessons(tmp_bsela_home: Path) -> None:
    """increment_hit_count bumps hit_count on each given lesson id."""
    lesson = save_lesson(
        Lesson(scope="project", rule="test rule", why="w", how_to_apply="h", confidence=0.9)
    )
    assert lesson.hit_count == 0
    increment_hit_count([lesson.id])
    updated = get_lesson(lesson.id)
    assert updated is not None
    assert updated.hit_count == 1
    # calling twice cumulates
    increment_hit_count([lesson.id])
    updated2 = get_lesson(lesson.id)
    assert updated2 is not None
    assert updated2.hit_count == 2


def test_increment_hit_count_empty_list_is_noop(tmp_bsela_home: Path) -> None:
    """increment_hit_count with empty list does nothing and does not raise."""
    increment_hit_count([])  # should not raise


def test_increment_hit_count_skips_missing_ids(tmp_bsela_home: Path) -> None:
    """Nonexistent lesson IDs are silently skipped."""
    increment_hit_count(["nonexistent-id"])  # should not raise
