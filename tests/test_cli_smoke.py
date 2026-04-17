"""P0 smoke tests: CLI loads and stub commands respond."""

from __future__ import annotations

from typer.testing import CliRunner

from bsela import __version__
from bsela.cli import app


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("status", "ingest", "review", "rollback"):
        assert cmd in result.stdout


def test_status_stub_exits_zero() -> None:
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not implemented" in result.stdout


def test_review_stub_exits_zero() -> None:
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0
