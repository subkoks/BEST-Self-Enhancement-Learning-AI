"""P1 tests: each SQLModel table round-trips through SQLite."""

from __future__ import annotations

from pathlib import Path

from bsela.memory.models import Decision, ErrorRecord, Lesson, Metric, SessionRecord
from bsela.memory.store import (
    get_session,
    list_decisions,
    list_errors,
    list_lessons,
    list_metrics,
    list_sessions,
    save_decision,
    save_error,
    save_lesson,
    save_metric,
    save_session,
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
