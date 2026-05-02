"""Tests for ``bsela sessions list/show`` and ``bsela errors list``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.memory.models import SessionRecord
from bsela.memory.store import list_errors, list_sessions, session_scope

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


def test_sessions_list_empty(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["sessions", "list"])
    assert result.exit_code == 0
    assert "no entries" in result.stdout


def test_sessions_list_shows_captured(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "clean.jsonl")
    ingest_file(FIXTURES / "leaked-aws-key.jsonl")

    result = CliRunner().invoke(app, ["sessions", "list"])
    assert result.exit_code == 0, result.stdout
    assert "CAPTURED" in result.stdout
    assert "QUARANTINED" in result.stdout
    assert "src=claude_code" in result.stdout


def test_sessions_list_filter_status(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "clean.jsonl")
    ingest_file(FIXTURES / "leaked-aws-key.jsonl")

    result = CliRunner().invoke(app, ["sessions", "list", "--status", "quarantined"])
    assert result.exit_code == 0, result.stdout
    assert "QUARANTINED" in result.stdout
    assert "CAPTURED" not in result.stdout


def test_sessions_show_prints_metadata_and_errors(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "user-correction.jsonl")
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id

    errs = list_errors(session_id=sid)
    assert errs, "auto-detect should have produced at least one error"

    result = CliRunner().invoke(app, ["sessions", "show", sid])
    assert result.exit_code == 0, result.stdout
    assert sid in result.stdout
    assert "transcript:" in result.stdout
    assert "turn_count:" in result.stdout
    assert "errors (" in result.stdout
    assert "correction" in result.stdout


def test_sessions_show_missing_exits_nonzero(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["sessions", "show", "not-a-real-id"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_errors_list_empty(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["errors", "list"])
    assert result.exit_code == 0
    assert "no entries" in result.stdout


def test_errors_list_shows_detected(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "user-correction.jsonl")

    result = CliRunner().invoke(app, ["errors", "list"])
    assert result.exit_code == 0, result.stdout
    assert "correction" in result.stdout


def test_errors_list_filter_by_session(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "user-correction.jsonl")
    ingest_file(FIXTURES / "looped-read.jsonl")
    sessions = list_sessions(status="captured", limit=10)
    assert len(sessions) == 2
    target = sessions[0].id

    result = CliRunner().invoke(app, ["errors", "list", "--session-id", target])
    assert result.exit_code == 0, result.stdout
    # Every listed row must belong to this session.
    for line in result.stdout.splitlines():
        if not line.startswith("- "):
            continue
        assert f"sess={target[:8]}" in line


def test_sessions_show_quarantine_and_ended_at(tmp_bsela_home: Path) -> None:
    """Cover quarantine_reason and ended_at branches in sessions show."""
    ingest_file(FIXTURES / "leaked-aws-key.jsonl")
    quarantined = list_sessions(status="quarantined", limit=1)
    assert quarantined
    sid = quarantined[0].id

    # Patch in an ended_at value so that branch is exercised.
    with session_scope() as s:
        rec = s.get(SessionRecord, sid)
        assert rec is not None
        rec.ended_at = datetime.now(UTC)
        s.add(rec)
        s.commit()

    result = CliRunner().invoke(app, ["sessions", "show", sid])
    assert result.exit_code == 0, result.stdout
    assert "quarantine:" in result.stdout
    assert "ended_at:" in result.stdout


def test_sessions_show_no_errors(tmp_bsela_home: Path) -> None:
    """Cover the '(none)' branch when a session has no detected errors."""
    ingest_file(FIXTURES / "clean.jsonl")
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id
    errs = list_errors(session_id=sid)
    assert not errs, "clean.jsonl should produce no errors"

    result = CliRunner().invoke(app, ["sessions", "show", sid])
    assert result.exit_code == 0, result.stdout
    assert "(none)" in result.stdout


def test_detect_single_session(tmp_bsela_home: Path) -> None:
    """Cover detect --session-id <id> single-session path."""
    ingest_file(FIXTURES / "looped-read.jsonl")
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id

    result = CliRunner().invoke(app, ["detect", "--session-id", sid])
    assert result.exit_code == 0, result.stdout
    assert sid in result.stdout
    assert "candidate errors" in result.stdout


def test_detect_bulk_sessions(tmp_bsela_home: Path) -> None:
    """Cover detect bulk scan path (no --session-id)."""
    ingest_file(FIXTURES / "looped-read.jsonl")
    ingest_file(FIXTURES / "user-correction.jsonl")

    result = CliRunner().invoke(app, ["detect"])
    assert result.exit_code == 0, result.stdout
    assert "scanned" in result.stdout
    assert "sessions" in result.stdout


def test_sessions_show_no_ended_at(tmp_bsela_home: Path) -> None:
    """Cover branch where session.ended_at is None (no ended_at line printed)."""
    ingest_file(FIXTURES / "clean.jsonl")
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id

    # Clear ended_at so the branch is skipped.
    with session_scope() as s:
        rec = s.get(SessionRecord, sid)
        assert rec is not None
        rec.ended_at = None
        s.add(rec)
        s.commit()

    result = CliRunner().invoke(app, ["sessions", "show", sid])
    assert result.exit_code == 0, result.stdout
    assert "ended_at:" not in result.stdout
    assert "ingested_at:" in result.stdout


def test_sessions_show_prefix_id(tmp_bsela_home: Path) -> None:
    """sessions show accepts an 8-char ID prefix."""
    ingest_file(FIXTURES / "clean.jsonl")
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id
    prefix = sid[:8]

    result = CliRunner().invoke(app, ["sessions", "show", prefix])
    assert result.exit_code == 0, result.stdout
    assert sid in result.stdout


def test_detect_skips_already_detected_by_default(tmp_bsela_home: Path) -> None:
    """detect batch skips sessions that auto-detect already covered."""
    ingest_file(FIXTURES / "user-correction.jsonl")  # auto-detect fires
    captured = list_sessions(status="captured", limit=1)
    assert captured
    initial_errors = len(list_errors(session_id=captured[0].id))
    assert initial_errors >= 1

    result = CliRunner().invoke(app, ["detect"])
    assert result.exit_code == 0, result.stdout
    assert "already-detected skipped" in result.stdout
    # Error count must not have grown.
    assert len(list_errors(session_id=captured[0].id)) == initial_errors


def test_detect_force_reruns_detection(tmp_bsela_home: Path) -> None:
    """detect --force re-detects sessions that already have errors."""
    ingest_file(FIXTURES / "user-correction.jsonl")
    result = CliRunner().invoke(app, ["detect", "--force"])
    assert result.exit_code == 0, result.stdout
    assert "scanned" in result.stdout
    # --force skips the "already-detected" note
    assert "already-detected skipped" not in result.stdout


def test_detect_session_id_prefix(tmp_bsela_home: Path) -> None:
    """detect --session-id accepts an 8-char prefix."""
    ingest_file(FIXTURES / "looped-read.jsonl", auto_detect=False)
    captured = list_sessions(status="captured", limit=1)
    assert captured
    prefix = captured[0].id[:8]

    result = CliRunner().invoke(app, ["detect", "--session-id", prefix])
    assert result.exit_code == 0, result.stdout
    assert "candidate errors" in result.stdout


def test_sessions_list_json_output(tmp_bsela_home: Path) -> None:
    """sessions list --json emits a JSON array with the expected keys."""
    ingest_file(FIXTURES / "clean.jsonl")
    ingest_file(FIXTURES / "leaked-aws-key.jsonl")

    result = CliRunner().invoke(app, ["sessions", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert sorted(rows[0].keys()) == [
        "id",
        "ingested_at",
        "source",
        "status",
        "tool_call_count",
        "turn_count",
    ]


def test_sessions_list_json_empty(tmp_bsela_home: Path) -> None:
    """sessions list --json returns an empty array when no sessions exist."""
    result = CliRunner().invoke(app, ["sessions", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert rows == []


def test_sessions_list_json_status_filter(tmp_bsela_home: Path) -> None:
    """sessions list --json --status quarantined returns only quarantined rows."""
    ingest_file(FIXTURES / "clean.jsonl")
    ingest_file(FIXTURES / "leaked-aws-key.jsonl")

    result = CliRunner().invoke(app, ["sessions", "list", "--json", "--status", "quarantined"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert all(r["status"] == "quarantined" for r in rows)
    assert len(rows) == 1
