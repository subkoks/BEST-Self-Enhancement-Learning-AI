"""Smoke tests for Typer help text — catches dropped or renamed CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela import __version__
from bsela.cli import app


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
