"""Unit + CLI tests for ``bsela.core.doctor`` and ``bsela doctor``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.doctor import (
    FAIL,
    PASS,
    WARN,
    CheckResult,
    _check_agents_md_repo,
    _check_bsela_home,
    _check_bsela_on_path,
    _check_claude_hook,
    _check_llm_api_key,
    _check_python,
    _read_claude_settings,
    run_checks,
    worst_status,
)


def test_check_python_passes_on_current_interpreter() -> None:
    row = _check_python()
    assert row.status == PASS
    assert row.name == "python"


def test_check_api_key_fail_when_both_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    row = _check_llm_api_key()
    assert row.status == FAIL
    assert "neither" in row.detail


def test_check_api_key_pass_with_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-deadbeef")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    row = _check_llm_api_key()
    assert row.status == PASS
    assert "ANTHROPIC_API_KEY" in row.detail
    assert "chars" in row.detail


def test_check_api_key_pass_with_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-deadbeef")
    row = _check_llm_api_key()
    assert row.status == PASS
    assert "OPENROUTER_API_KEY" in row.detail
    assert "chars" in row.detail


def test_check_agents_md_repo_warns_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "agents-md-does-not-exist"
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(missing))
    row = _check_agents_md_repo()
    assert row.status == WARN
    assert "not found" in row.detail


def test_check_agents_md_repo_fail_when_not_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(plain))
    row = _check_agents_md_repo()
    assert row.status == FAIL
    assert "not a git repo" in row.detail


def test_check_agents_md_repo_pass_when_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "agents-md"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(repo))
    row = _check_agents_md_repo()
    assert row.status == PASS


def test_check_claude_hook_warns_when_file_missing(tmp_path: Path) -> None:
    row = _check_claude_hook(tmp_path / "no-such.json")
    assert row.status == WARN
    assert "does not exist" in row.detail


def test_check_claude_hook_fails_on_invalid_json(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{not json", encoding="utf-8")
    row = _check_claude_hook(settings)
    assert row.status == FAIL
    assert "not valid JSON" in row.detail


def test_check_claude_hook_warns_when_stop_missing(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": []}}), encoding="utf-8")
    row = _check_claude_hook(settings)
    assert row.status == WARN
    assert "Stop" in row.detail


def test_check_claude_hook_pass_when_registered(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    payload = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "bsela hook claude-stop"}],
                }
            ]
        }
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    row = _check_claude_hook(settings)
    assert row.status == PASS
    assert "registered" in row.detail


def test_worst_status_picks_fail() -> None:

    results = [
        CheckResult("a", PASS, ""),
        CheckResult("b", WARN, ""),
        CheckResult("c", FAIL, ""),
    ]
    assert worst_status(results) == FAIL


def test_worst_status_picks_warn() -> None:

    assert worst_status([CheckResult("x", PASS, ""), CheckResult("y", WARN, "")]) == WARN


def test_worst_status_all_pass() -> None:

    assert worst_status([CheckResult("x", PASS, ""), CheckResult("y", PASS, "")]) == PASS


def test_run_checks_returns_all_probes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(tmp_path / "absent"))
    rows = run_checks(settings_path=tmp_path / "settings.json")
    names = [r.name for r in rows]
    assert "python" in names
    assert "LLM API key" in names
    assert "bsela_home" in names
    assert "store" in names
    assert "agents-md repo" in names
    assert "claude-code hook" in names


def test_cli_doctor_exit_zero_when_no_fail(
    tmp_bsela_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ok")
    repo = tmp_path / "agents-md"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(repo))

    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "doctor:" in result.stdout
    assert "LLM API key" in result.stdout


def test_cli_doctor_exit_zero_with_openrouter(
    tmp_bsela_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-ok")
    repo = tmp_path / "agents-md"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(repo))

    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "OPENROUTER_API_KEY" in result.stdout


def test_cli_doctor_exit_one_when_any_fail(
    tmp_bsela_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


# ---- additional branch coverage ----


def test_check_python_fails_on_old_version() -> None:
    """FAIL branch: Python < 3.13."""
    mock_vi = MagicMock()
    mock_vi.__getitem__ = lambda self, key: (3, 12, 9, "final", 0)[key]
    mock_vi.micro = 9
    with patch("bsela.core.doctor.sys.version_info", mock_vi):
        row = _check_python()
    assert row.status == FAIL
    assert "3.12" in row.detail


def test_check_bsela_home_warns_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WARN branch: bsela_home does not exist."""
    monkeypatch.setenv("BSELA_HOME", str(tmp_path / "nonexistent"))
    row = _check_bsela_home()
    assert row.status == WARN
    assert "does not exist" in row.detail


def test_check_bsela_on_path_fails_when_missing() -> None:
    """FAIL branch: bsela not found on PATH."""
    with patch("shutil.which", return_value=None):
        row = _check_bsela_on_path()
    assert row.status == FAIL
    assert "not found" in row.detail


def test_check_claude_hook_warns_when_hooks_not_dict(tmp_path: Path) -> None:
    """WARN branch: `hooks` key present but not a dict."""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": "not-a-dict"}), encoding="utf-8")
    row = _check_claude_hook(settings)
    assert row.status == WARN
    assert "no hooks block" in row.detail


def test_check_claude_hook_warns_when_hook_not_found(tmp_path: Path) -> None:
    """WARN branch: Stop list exists but command doesn't match — returns WARN at end of loop."""
    settings = tmp_path / "settings.json"
    payload = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "something-else"}],
                }
            ]
        }
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    row = _check_claude_hook(settings)
    assert row.status == WARN
    assert "not registered" in row.detail


def test_check_claude_hook_skips_non_dict_group(tmp_path: Path) -> None:
    """Loop `continue` branches: group not a dict or entries not a list."""
    settings = tmp_path / "settings.json"
    payload = {
        "hooks": {
            "Stop": [
                42,  # not a dict → continue
                {"matcher": "", "hooks": "not-a-list"},  # entries not a list → continue
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "bsela hook claude-stop"}],
                },
            ]
        }
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    row = _check_claude_hook(settings)
    # Third group is valid — should pass
    assert row.status == PASS


def test_read_claude_settings_returns_none_on_oserror() -> None:
    """OSError branch: read_text raises OSError."""
    mock_path = MagicMock(spec=Path)
    mock_path.read_text.side_effect = OSError("permission denied")
    result = _read_claude_settings(mock_path)
    assert result is None
