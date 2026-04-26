"""P0 smoke tests: CLI loads and stub commands respond."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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
