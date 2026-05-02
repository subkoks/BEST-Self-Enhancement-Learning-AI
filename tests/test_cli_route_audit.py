"""P5 CLI smoke tests: `bsela route` and `bsela audit`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.memory.models import Metric
from bsela.memory.store import save_metric


def test_route_prints_class_model_and_reason() -> None:
    result = CliRunner().invoke(app, ["route", "plan the P5 rollout"])
    assert result.exit_code == 0
    assert "class:" in result.stdout
    assert "planner" in result.stdout
    assert "claude-opus-4-7" in result.stdout
    assert "keywords:" in result.stdout


def test_route_json_mode_returns_machine_payload() -> None:
    result = CliRunner().invoke(app, ["route", "refactor the updater", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task_class"] == "builder"
    assert payload["confidence"] == 1.0
    assert "refactor" in payload["matched_keywords"]


def test_route_empty_task_falls_back_to_default() -> None:
    result = CliRunner().invoke(app, ["route", "   "])
    assert result.exit_code == 0
    # builder is the default class (DEFAULT_CLASS).
    assert "builder" in result.stdout
    assert "0.50" in result.stdout


def test_audit_writes_markdown_when_store_empty(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit"])
    # Empty store, no alerts → exit 0, file written.
    assert result.exit_code == 0, result.stdout
    assert "audit:" in result.stdout
    audit_path = tmp_bsela_home / "reports" / "audit.md"
    assert audit_path.exists()
    content = audit_path.read_text(encoding="utf-8")
    assert "# BSELA Weekly Audit" in content
    assert "_all clear._" in content


def test_audit_weekly_flag_uses_default_window(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit", "--weekly"])
    assert result.exit_code == 0
    assert "window=30d" in result.stdout


def test_audit_stdout_prints_markdown_without_writing(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit", "--stdout"])
    assert result.exit_code == 0
    assert "# BSELA Weekly Audit" in result.stdout
    # No file should be written in --stdout mode.
    assert not (tmp_bsela_home / "reports" / "audit.md").exists()


def test_audit_json_returns_machine_payload(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert sorted(payload.keys()) == [
        "adrs",
        "alerts",
        "cost",
        "drift",
        "errors_total",
        "generated_at",
        "replay_drift",
        "sessions",
        "window_days",
        "window_end",
        "window_start",
    ]
    assert sorted(payload["sessions"].keys()) == ["quarantine_rate", "quarantined", "total"]
    assert sorted(payload["cost"].keys()) == [
        "burn_ratio",
        "monthly_budget_usd",
        "over_budget",
        "prorated_monthly_usd",
        "total_usd",
    ]
    assert payload["window_days"] == 30
    assert payload["sessions"]["total"] == 0
    assert payload["errors_total"] == 0
    assert payload["cost"]["over_budget"] is False
    assert isinstance(payload["alerts"], list)
    # JSON mode should not write markdown output.
    assert not (tmp_bsela_home / "reports" / "audit.md").exists()


def test_audit_exits_nonzero_when_alerts_present(tmp_bsela_home: Path) -> None:
    save_metric(
        Metric(
            stage="distill",
            cost_usd=500.0,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    result = CliRunner().invoke(app, ["audit"])
    # Cost over budget → exit 1 so launchd logs the alert.
    assert result.exit_code == 1
    assert "alerts=" in result.stdout


def test_audit_json_preserves_nonzero_exit_when_alerts_present(tmp_bsela_home: Path) -> None:
    save_metric(
        Metric(
            stage="distill",
            cost_usd=500.0,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    result = CliRunner().invoke(app, ["audit", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["cost"]["over_budget"] is True
    assert len(payload["alerts"]) >= 1
