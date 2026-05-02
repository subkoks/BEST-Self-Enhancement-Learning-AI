"""Smoke tests for Typer help text — catches dropped or renamed CLI commands."""

from __future__ import annotations

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
