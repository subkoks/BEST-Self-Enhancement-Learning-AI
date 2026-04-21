"""Tests for the ``bsela decision`` subapp (lightweight ADR trail)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.memory.store import list_decisions


def test_decision_add_persists_row(tmp_bsela_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "decision",
            "add",
            "Pin judge to Haiku 3.5",
            "--context",
            "Cost ceiling of ~$0.05/session per P4 budget.",
            "--decision",
            "Use claude-3-5-haiku-20241022 for the judge pass.",
            "--consequences",
            "Accept slightly higher false-positive rate; revisit at P5.",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "recorded" in result.stdout

    rows = list_decisions()
    assert len(rows) == 1
    saved = rows[0]
    assert saved.title == "Pin judge to Haiku 3.5"
    assert "Cost ceiling" in saved.context
    assert "haiku" in saved.decision.lower()
    assert "false-positive" in saved.consequences


def test_decision_list_empty(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["decision", "list"])
    assert result.exit_code == 0
    assert "no entries" in result.stdout


def test_decision_list_orders_newest_first(tmp_bsela_home: Path) -> None:
    runner = CliRunner()
    for title in ("first", "second", "third"):
        runner.invoke(
            app,
            [
                "decision",
                "add",
                title,
                "--context",
                "c",
                "--decision",
                "d",
                "--consequences",
                "x",
            ],
        )

    listed = runner.invoke(app, ["decision", "list", "--limit", "2"])
    assert listed.exit_code == 0
    lines = [line for line in listed.stdout.splitlines() if line.startswith("- ")]
    assert len(lines) == 2
    assert "third" in lines[0]
    assert "second" in lines[1]


def test_decision_requires_all_fields(tmp_bsela_home: Path) -> None:
    # Missing --consequences should be a usage error (non-zero exit).
    result = CliRunner().invoke(
        app,
        [
            "decision",
            "add",
            "incomplete",
            "--context",
            "c",
            "--decision",
            "d",
        ],
    )
    assert result.exit_code != 0
    assert list_decisions() == []
