"""P1 tests: ``bsela hook claude-stop`` reads stdin JSON and ingests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.memory.store import count_sessions, list_sessions


def test_claude_stop_ingests_from_stdin(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    payload = json.dumps(
        {
            "session_id": "abc-123",
            "transcript_path": str(sample_clean_session),
            "cwd": str(tmp_bsela_home),
            "hook_event_name": "Stop",
        }
    )
    result = CliRunner().invoke(app, ["hook", "claude-stop"], input=payload)
    assert result.exit_code == 0, result.stdout
    sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].source == "claude_code"


def test_claude_stop_noops_on_empty_stdin(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["hook", "claude-stop"], input="")
    assert result.exit_code == 0
    assert count_sessions() == 0


def test_claude_stop_noops_on_malformed_json(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["hook", "claude-stop"], input="not json")
    assert result.exit_code == 0
    assert count_sessions() == 0


def test_claude_stop_noops_when_transcript_missing(tmp_bsela_home: Path) -> None:
    payload = json.dumps({"transcript_path": str(tmp_bsela_home / "ghost.jsonl")})
    result = CliRunner().invoke(app, ["hook", "claude-stop"], input=payload)
    assert result.exit_code == 0
    assert count_sessions() == 0


def test_prune_command_runs(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["prune"])
    assert result.exit_code == 0
    assert "pruned sessions:" in result.stdout
    assert "errors:" in result.stdout
    assert "replay_records:" in result.stdout
