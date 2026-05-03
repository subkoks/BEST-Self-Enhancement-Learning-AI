"""Smoke tests for Typer help text — catches dropped or renamed CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela import __version__
from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.memory.models import Lesson
from bsela.memory.store import save_lesson


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_root_help_lists_core_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    for name in (
        "ingest",
        "status",
        "distill",
        "process",
        "report",
        "route",
        "audit",
        "replay",
        "replays",
        "rollback",
        "doctor",
        "hook",
        "review",
        "sessions",
        "errors",
        "decision",
        "prune",
        "detect",
        "lessons",
    ):
        assert name in out, f"missing command name {name!r} in bsela --help"


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0, result.stdout
    assert __version__ in result.stdout


def test_hook_subgroup_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["hook", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "install" in result.stdout


def test_route_json_contract_stable_keys(runner: CliRunner) -> None:
    """Keep CLI JSON aligned with MCP ``bsela_route`` consumers."""
    result = runner.invoke(app, ["route", "plan the P5 rollout", "--json"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert set(data.keys()) == {
        "task_class",
        "model",
        "confidence",
        "reason",
        "matched_keywords",
    }
    assert data["task_class"] == "planner"
    assert isinstance(data["matched_keywords"], list)


def test_nested_command_help_pages_load(runner: CliRunner) -> None:
    for argv in (
        ["review", "list", "--help"],
        ["sessions", "list", "--help"],
        ["errors", "list", "--help"],
        ["decision", "add", "--help"],
        ["replays", "list", "--help"],
        ["detect", "--help"],
        ["hook", "install", "--help"],
    ):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, (argv, result.stdout)
        assert "Usage:" in result.stdout, argv


def test_status_json_contract_stable_keys(tmp_bsela_home: Path, runner: CliRunner) -> None:
    """Keep CLI JSON aligned with MCP ``bsela_status`` / ``StatusPayload``."""
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert set(data.keys()) == {
        "sessions",
        "sessions_quarantined",
        "errors",
        "lessons",
        "lessons_pending",
        "lessons_proposed",
        "replay_records",
        "bsela_home",
    }
    assert data["bsela_home"] == str(tmp_bsela_home)
    assert data["sessions"] == 0


def test_lessons_json_empty_store(tmp_bsela_home: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["lessons", "--json"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


# Must match ``LessonItem`` in ``mcp/src/bsela-client.ts`` (MCP ``bsela_lessons``).
_LESSON_ITEM_JSON_KEYS = frozenset(
    {
        "id",
        "status",
        "scope",
        "confidence",
        "rule",
        "why",
        "how_to_apply",
        "hit_count",
        "created_at",
    }
)


def _assert_lesson_item_row(row: object) -> None:
    assert isinstance(row, dict)
    d: dict[str, object] = row
    assert set(d.keys()) == _LESSON_ITEM_JSON_KEYS
    assert isinstance(d["id"], str)
    assert isinstance(d["status"], str)
    assert isinstance(d["scope"], str)
    assert isinstance(d["confidence"], (int, float))
    assert isinstance(d["rule"], str)
    assert isinstance(d["why"], str)
    assert isinstance(d["how_to_apply"], str)
    assert isinstance(d["hit_count"], int)
    ca = d["created_at"]
    assert ca is None or isinstance(ca, str)


def _seed_lesson_for_json_contract() -> Lesson:
    return save_lesson(
        Lesson(
            scope="project",
            rule="Contract test rule",
            why="Exercise JSON shape",
            how_to_apply="Run pytest",
            confidence=0.88,
        )
    )


def test_lessons_top_level_json_row_matches_mcp_lesson_item(
    tmp_bsela_home: Path, runner: CliRunner
) -> None:
    """Non-empty ``bsela lessons --json`` rows match MCP ``LessonItem``."""
    saved = _seed_lesson_for_json_contract()
    result = runner.invoke(app, ["lessons", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    _assert_lesson_item_row(rows[0])
    assert rows[0]["id"] == saved.id
    assert rows[0]["rule"] == "Contract test rule"


def test_review_list_json_row_matches_mcp_lesson_item(
    tmp_bsela_home: Path, runner: CliRunner
) -> None:
    """Non-empty ``bsela review list --json`` rows match MCP ``LessonItem``."""
    saved = _seed_lesson_for_json_contract()
    result = runner.invoke(app, ["review", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    _assert_lesson_item_row(rows[0])
    assert rows[0]["id"] == saved.id


_AUDIT_JSON_TOP_LEVEL = frozenset(
    {
        "generated_at",
        "window_days",
        "window_start",
        "window_end",
        "sessions",
        "errors_total",
        "cost",
        "drift",
        "replay_drift",
        "adrs",
        "alerts",
    }
)


def test_audit_json_contract_stable_keys(tmp_bsela_home: Path, runner: CliRunner) -> None:
    """Keep CLI JSON aligned with MCP ``bsela_audit`` / ``AuditPayload``."""
    result = runner.invoke(app, ["audit", "--window-days", "1", "--json"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert set(data.keys()) == _AUDIT_JSON_TOP_LEVEL
    assert data["window_days"] == 1
    assert isinstance(data["alerts"], list)


# Must match ``SessionItem`` in ``mcp/src/bsela-client.ts`` (MCP ``bsela_sessions``).
_SESSION_ITEM_JSON_KEYS = frozenset(
    {"id", "status", "source", "turn_count", "tool_call_count", "ingested_at"}
)

# Must match ``ErrorItem`` in ``mcp/src/bsela-client.ts`` (MCP ``bsela_errors``).
_ERROR_ITEM_JSON_KEYS = frozenset(
    {"id", "session_id", "category", "severity", "line_number", "snippet", "detected_at"}
)


def test_sessions_list_json_contract(tmp_bsela_home: Path, runner: CliRunner) -> None:
    """bsela sessions list --json row shape matches MCP SessionItem."""
    fixtures = Path(__file__).parent / "fixtures" / "sample-sessions"
    ingest_file(fixtures / "clean.jsonl")

    result = runner.invoke(app, ["sessions", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert set(rows[0].keys()) == _SESSION_ITEM_JSON_KEYS


def test_errors_list_json_contract(tmp_bsela_home: Path, runner: CliRunner) -> None:
    """bsela errors list --json row shape matches MCP ErrorItem."""
    fixtures = Path(__file__).parent / "fixtures" / "sample-sessions"
    ingest_file(fixtures / "user-correction.jsonl")

    result = runner.invoke(app, ["errors", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert len(rows) >= 1
    assert set(rows[0].keys()) == _ERROR_ITEM_JSON_KEYS
