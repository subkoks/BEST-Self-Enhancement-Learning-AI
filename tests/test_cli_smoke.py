"""Smoke tests: CLI loads and all commands respond without crashing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela import __version__
from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.memory.models import ErrorRecord, Lesson
from bsela.memory.store import list_sessions, save_error, save_lesson


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("status", "ingest", "review", "rollback"):
        assert cmd in result.stdout


def test_status_exits_zero_when_store_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BSELA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no store" in result.stdout


def test_status_json_exits_zero_when_store_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BSELA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sessions"] == 0
    assert payload["errors"] == 0
    assert payload["lessons"] == 0
    assert payload["lessons_pending"] == 0
    assert "bsela_home" in payload


def test_review_with_empty_store_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BSELA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0
    assert "no pending lessons" in result.stdout


def test_rollback_not_found_exits_1(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["rollback", "no-such-id"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_rollback_pending_lesson_succeeds(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            severity="medium",
            snippet="test",
        )
    )
    lesson = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="Never do X",
            why="reason",
            how_to_apply="action",
            confidence=0.9,
            status="pending",
        )
    )
    result = CliRunner().invoke(app, ["rollback", lesson.id])
    assert result.exit_code == 0
    assert "rolled back" in result.stdout


def test_rollback_already_rolled_back_exits_0(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            severity="medium",
            snippet="test",
        )
    )
    lesson = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="Never do Y",
            why="reason",
            how_to_apply="action",
            confidence=0.9,
            status="rolled_back",
        )
    )
    result = CliRunner().invoke(app, ["rollback", lesson.id])
    assert result.exit_code == 0
    assert "already rolled back" in result.stdout


def test_doctor_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "doctor:" in result.stdout


def test_route_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["route", "write a unit test"])
    assert result.exit_code == 0
    assert len(result.stdout.strip()) > 0


def test_audit_stdout_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit", "--stdout"])
    assert result.exit_code in (0, 1)


def test_report_stdout_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["report", "--stdout"])
    assert result.exit_code == 0
