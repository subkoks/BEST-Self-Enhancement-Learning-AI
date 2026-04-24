"""Tests for ``bsela sessions list/show`` and ``bsela errors list``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.memory.store import list_errors, list_sessions

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
