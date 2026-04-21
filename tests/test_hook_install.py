"""P4 tests: ``bsela hook install`` planner, writer, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.hook_install import (
    DEFAULT_HOOK_COMMAND,
    apply_install,
    plan_install,
)


def _stop_commands(merged: dict[str, object]) -> list[str]:
    hooks = merged.get("hooks")
    assert isinstance(hooks, dict)
    groups = hooks.get("Stop")
    assert isinstance(groups, list)
    commands: list[str] = []
    for group in groups:
        assert isinstance(group, dict)
        entries = group.get("hooks")
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            cmd = entry.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    return commands


def test_plan_install_on_empty_dict_adds_stop_hook() -> None:
    plan = plan_install({})
    assert plan.changed is True
    assert _stop_commands(plan.merged) == [DEFAULT_HOOK_COMMAND]


def test_plan_install_is_idempotent() -> None:
    first = plan_install({})
    second = plan_install(first.merged)
    assert second.changed is False
    assert "already registered" in second.reason
    assert _stop_commands(second.merged) == [DEFAULT_HOOK_COMMAND]


def test_plan_install_preserves_unrelated_settings() -> None:
    pre_tool_use = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo pre"}]}]
    existing: dict[str, object] = {
        "theme": "dark",
        "hooks": {"PreToolUse": pre_tool_use},
    }
    plan = plan_install(existing)
    assert plan.changed is True
    assert plan.merged["theme"] == "dark"
    assert plan.merged["hooks"]["PreToolUse"] == pre_tool_use
    assert _stop_commands(plan.merged) == [DEFAULT_HOOK_COMMAND]


def test_plan_install_appends_when_other_stop_entries_exist() -> None:
    existing = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "echo other"}],
                }
            ]
        }
    }
    plan = plan_install(existing)
    assert plan.changed is True
    commands = _stop_commands(plan.merged)
    assert "echo other" in commands
    assert DEFAULT_HOOK_COMMAND in commands


def test_plan_install_noop_when_hooks_root_is_not_dict() -> None:
    plan = plan_install({"hooks": "bogus"})
    assert plan.changed is True
    assert _stop_commands(plan.merged) == [DEFAULT_HOOK_COMMAND]


def test_plan_install_accepts_custom_command() -> None:
    plan = plan_install({}, command="custom-cmd")
    assert _stop_commands(plan.merged) == ["custom-cmd"]


def test_apply_install_writes_file_and_backup(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    result = apply_install(target)
    assert result.wrote is True
    assert result.backup is not None
    assert result.backup.is_file()
    assert json.loads(result.backup.read_text()) == {"theme": "dark"}

    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk["theme"] == "dark"
    assert _stop_commands(on_disk) == [DEFAULT_HOOK_COMMAND]


def test_apply_install_creates_file_without_backup(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "settings.json"
    result = apply_install(target)
    assert result.wrote is True
    assert result.backup is None
    assert target.is_file()
    assert _stop_commands(json.loads(target.read_text())) == [DEFAULT_HOOK_COMMAND]


def test_apply_install_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    first = apply_install(target)
    second = apply_install(target)
    assert first.wrote is True
    assert second.wrote is False
    assert "already registered" in second.plan.reason


def test_apply_install_rejects_non_object_top_level(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="top level"):
        apply_install(target)


def test_cli_dry_run_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    result = CliRunner().invoke(app, ["hook", "install", "--settings", str(target)])
    assert result.exit_code == 0, result.stdout
    assert "dry-run" in result.stdout
    assert DEFAULT_HOOK_COMMAND in result.stdout
    assert not target.exists()


def test_cli_apply_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    result = CliRunner().invoke(app, ["hook", "install", "--settings", str(target), "--apply"])
    assert result.exit_code == 0, result.stdout
    assert target.is_file()
    assert _stop_commands(json.loads(target.read_text())) == [DEFAULT_HOOK_COMMAND]


def test_cli_apply_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    first = CliRunner().invoke(app, ["hook", "install", "--settings", str(target), "--apply"])
    second = CliRunner().invoke(app, ["hook", "install", "--settings", str(target), "--apply"])
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "no change" in second.stdout


def test_cli_custom_command_flag(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    result = CliRunner().invoke(
        app,
        [
            "hook",
            "install",
            "--settings",
            str(target),
            "--command",
            "my-cmd",
            "--apply",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert _stop_commands(json.loads(target.read_text())) == ["my-cmd"]
