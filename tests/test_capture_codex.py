"""Codex capture: rollout counts, ``replace`` semantics, quarantine."""

from __future__ import annotations

import json
from pathlib import Path

from bsela.core.capture import ingest_file
from bsela.memory.models import Lesson, SessionRecord
from bsela.memory.store import (
    count_sessions,
    get_session,
    list_errors,
    save_lesson,
    upsert_session,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"
ROLLOUT = FIXTURES / "codex-rollout.jsonl"
CORRECTION = FIXTURES / "codex-correction.jsonl"


def _copy_rollout(source: Path, destination: Path) -> Path:
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _append_user_message(path: Path, text: str) -> None:
    event = {
        "timestamp": "2026-01-15T10:05:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def test_ingest_codex_rollout_counts_turns_and_tools(tmp_bsela_home: Path) -> None:
    result = ingest_file(ROLLOUT, source="codex")
    assert result.status == "captured"
    assert result.turn_count == 2
    assert result.tool_call_count == 1
    assert result.errors_detected == 0
    assert result.updated is False
    assert result.unchanged is False

    row = get_session(result.session_id)
    assert row is not None
    assert row.source == "codex"
    assert row.turn_count == 2
    assert row.ended_at is not None
    assert row.started_at < row.ended_at


def test_ingest_codex_rollout_detects_correction_loop_and_trace(tmp_bsela_home: Path) -> None:
    result = ingest_file(CORRECTION, source="codex")
    assert result.status == "captured"
    categories = {err.category for err in list_errors(session_id=result.session_id)}
    assert categories == {"correction", "loop", "stack_trace"}


def test_reingest_unchanged_codex_rollout_is_a_noop(tmp_bsela_home: Path) -> None:
    first = ingest_file(ROLLOUT, source="codex")
    again = ingest_file(ROLLOUT, source="codex")
    assert again.unchanged is True
    assert again.session_id == first.session_id
    assert count_sessions() == 1


def test_replace_refreshes_grown_rollout_in_place(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _copy_rollout(ROLLOUT, tmp_path / ROLLOUT.name)
    first = ingest_file(rollout, source="codex", replace=True)
    _append_user_message(rollout, "also update the docs")

    grown = ingest_file(rollout, source="codex", replace=True)
    assert grown.session_id == first.session_id
    assert grown.updated is True
    assert grown.turn_count == first.turn_count + 1
    assert count_sessions() == 1


def test_replace_clears_stale_error_rows(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _copy_rollout(CORRECTION, tmp_path / CORRECTION.name)
    first = ingest_file(rollout, source="codex", replace=True)
    assert len(list_errors(session_id=first.session_id)) == 3

    _copy_rollout(ROLLOUT, rollout)  # same path, no corrections left
    replaced = ingest_file(rollout, source="codex", replace=True)
    assert replaced.session_id == first.session_id
    assert replaced.errors_detected == 0
    assert list_errors(session_id=first.session_id) == []


def test_default_ingest_keeps_snapshot_behaviour(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _copy_rollout(ROLLOUT, tmp_path / ROLLOUT.name)
    first = ingest_file(rollout, source="codex")
    _append_user_message(rollout, "another turn")

    snapshot = ingest_file(rollout, source="codex")
    assert snapshot.session_id != first.session_id
    assert snapshot.updated is False
    assert count_sessions() == 2


def test_replace_leaves_distilled_session_alone(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _copy_rollout(CORRECTION, tmp_path / CORRECTION.name)
    first = ingest_file(rollout, source="codex", replace=True)
    error = list_errors(session_id=first.session_id)[0]
    save_lesson(
        Lesson(
            source_error_id=error.id,
            scope="global",
            rule="Read the release notes before editing the changelog.",
            why="Avoids clobbering generated sections.",
            how_to_apply="Check docs/releases first.",
            confidence=0.8,
        )
    )

    _append_user_message(rollout, "one more thing")
    skipped = ingest_file(rollout, source="codex", replace=True)
    assert skipped.skipped_reason == "distilled"
    assert skipped.session_id == first.session_id
    assert skipped.updated is False
    row = get_session(first.session_id)
    assert row is not None
    assert row.turn_count == first.turn_count
    assert count_sessions() == 1


def test_codex_rollout_with_secret_is_quarantined(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _copy_rollout(ROLLOUT, tmp_path / ROLLOUT.name)
    _append_user_message(rollout, "here is my token ghp_0123456789abcdefghijklmnopqrstuvwxyz")

    result = ingest_file(rollout, source="codex", replace=True)
    assert result.status == "quarantined"
    assert result.quarantine_reason is not None
    assert result.errors_detected == 0
    assert list_errors(session_id=result.session_id) == []

    again = ingest_file(rollout, source="codex", replace=True)
    assert again.status == "quarantined"
    assert again.unchanged is True


def test_upsert_session_inserts_missing_row(tmp_bsela_home: Path) -> None:
    record = SessionRecord(source="codex", transcript_path="/tmp/x.jsonl", content_hash="abc")
    saved = upsert_session(record)
    assert get_session(saved.id) is not None
