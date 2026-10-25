"""Maintenance acceptance: health, truthful failures, schedule and helper isolation."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.auditor import build_audit
from bsela.core.doctor import FAIL, PASS, _check_llm_provider
from bsela.llm.client import FakeLLMClient
from bsela.llm.distiller import distill_session
from bsela.llm.ledger import reserve
from bsela.llm.runtime import ProviderError, model_run
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import SessionRecord
from bsela.memory.store import list_lessons, save_session

pytestmark = pytest.mark.usefixtures("tmp_bsela_home")
ROOT = Path(__file__).resolve().parents[1]


def test_invalid_provider_and_missing_codex(monkeypatch):
    assert _check_llm_provider("retired").status == FAIL
    monkeypatch.setattr("bsela.core.doctor.shutil.which", lambda _: None)
    assert _check_llm_provider().status == FAIL


@pytest.mark.parametrize("live", [False, True])
def test_codex_health_uses_supported_login_status(monkeypatch, live):
    monkeypatch.setattr("bsela.core.doctor.shutil.which", lambda _: "/fake/codex")
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT"))
    monkeypatch.setattr("bsela.core.doctor.subprocess.run", run)
    fake = MagicMock()
    monkeypatch.setattr("bsela.core.doctor.make_llm_client", lambda _: fake)
    row = _check_llm_provider(auth_check=True, live=live)
    assert row.status == PASS
    assert fake.judge.call_count == int(live)
    assert 'forced_login_method="chatgpt"' in run.call_args.args[0]


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, "", "private"),
        subprocess.CompletedProcess([], 0, "API key", ""),
        OSError("private"),
        subprocess.TimeoutExpired("fake", 1),
    ],
)
def test_codex_health_errors_are_sanitized(monkeypatch, result):
    monkeypatch.setattr("bsela.core.doctor.shutil.which", lambda _: "/fake/codex")
    run = (
        MagicMock(side_effect=result)
        if isinstance(result, Exception)
        else MagicMock(return_value=result)
    )
    monkeypatch.setattr("bsela.core.doctor.subprocess.run", run)
    row = _check_llm_provider(auth_check=True)
    assert row.status == FAIL
    assert "private" not in row.detail


def test_deepseek_presence_check_never_requests_value(monkeypatch):
    credential = MagicMock(return_value="present")
    monkeypatch.setattr("bsela.core.doctor.keychain_credential", credential)
    assert _check_llm_provider("deepseek", auth_check=True).status == PASS
    credential.assert_called_once_with(presence_only=True)
    credential.side_effect = ProviderError("credential: missing")
    assert _check_llm_provider("deepseek", auth_check=True).status == FAIL


def test_cli_overlap_truthfully_fails():
    with model_run():
        result = CliRunner().invoke(app, ["process"])
    assert result.exit_code == 1
    assert "overlap" in result.stdout


@pytest.mark.parametrize(("day", "limit"), [(0, 3), (6, 10)])
def test_scheduled_dry_run_limits(monkeypatch, day, limit):
    clock = MagicMock()
    clock.now.return_value.weekday.return_value = day
    monkeypatch.setattr("bsela.cli.datetime", clock)
    result = CliRunner().invoke(app, ["process", "--scheduled", "--dry-run"])
    assert result.exit_code == 0
    assert f"limit={limit}" in result.stdout


def test_quarantine_and_model_error_persist_nothing():
    verdict = JudgeVerdict(
        goal_achieved=False, efficiency=0.5, looped=False, wasted_tokens=False, confidence=0.5
    )
    client = FakeLLMClient(verdict, DistillResponse(status="error"))
    session = save_session(
        SessionRecord(
            source="test", transcript_path="fake", content_hash="fake", status="quarantined"
        )
    )
    with pytest.raises(ProviderError, match="quarantined"):
        distill_session(session.id, client=client)
    session.status = "captured"
    save_session(session)
    with pytest.raises(ProviderError, match="model reported"):
        distill_session(session.id, client=client)
    assert not list_lessons()


def test_unknown_charge_is_audit_alert():
    reserve(
        run_id="r",
        session_id="s",
        provider="deepseek",
        model="deepseek-flash",
        stage="judge",
        input_bytes=1,
        max_tokens=10,
    )
    report = build_audit()
    assert any("Unresolved" in alert for alert in report.alerts)
    assert report.usage["api_reserved_usd"] > 0


@pytest.mark.parametrize("failure", [False, True])
def test_self_enhance_never_processes_and_reports_phase_failure(tmp_path, failure):
    home = tmp_path / "home"
    home.mkdir()
    binary = tmp_path / "bin"
    binary.mkdir()
    cli = binary / "bsela"
    cli.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$1" >> "$BSELA_TEST_CALLS"\n'
        + ('if [ "$1" = "review" ]; then exit 1; fi\n' if failure else "")
        + 'echo "fake success"\n'
    )
    cli.chmod(0o700)
    logfile = tmp_path / "calls"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "BSELA_TEST_CALLS": str(logfile),
    }
    result = subprocess.run(
        ["/bin/zsh", str(ROOT / "ops/self-enhance.sh"), "--full"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == int(failure)
    assert "process" not in logfile.read_text().splitlines()
    report = next((home / ".agent/enhancements").glob("*.md")).read_text()
    assert ("Completed successfully" in report) is (not failure)


def test_installer_refuses_missing_canary_before_writes(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "UV_DEFAULT_INDEX": "https://pypi.org/simple"}
    result = subprocess.run(
        ["bash", str(ROOT / "ops/install-launchd.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "canary evidence missing" in result.stderr
    assert not (tmp_path / "Library/LaunchAgents").exists()


def test_templates_use_direct_cli_and_sunday():
    for job in ("process", "report", "audit"):
        data = plistlib.loads(
            (ROOT / f"config/launchd/com.blackterminal.bsela.{job}.plist").read_bytes()
        )
        assert data["ProgramArguments"][0].endswith("/bsela")
        assert data["EnvironmentVariables"]["TZ"] == "Europe/London"
        calendar = data["StartCalendarInterval"]
        assert calendar["Hour"] == (8 if job == "process" else 9)
        assert calendar.get("Weekday") == (None if job == "process" else 0)
        assert "API_KEY" not in json.dumps(data)


def test_skip_response_cannot_persist_partial_lessons():
    verdict = JudgeVerdict(
        goal_achieved=False, efficiency=0.5, looped=False, wasted_tokens=False, confidence=0.5
    )
    client = FakeLLMClient(
        verdict,
        DistillResponse(
            status="skip",
            lessons=[
                LessonCandidate(
                    rule="must not persist",
                    why="skip",
                    how_to_apply="none",
                    scope="project",
                    confidence=0.9,
                )
            ],
        ),
    )
    session = save_session(
        SessionRecord(source="test", transcript_path="fake", content_hash="fake")
    )
    result = distill_session(session.id, client=client)
    assert not result.distilled
    assert not result.persisted
    assert not list_lessons()


def test_lock_excludes_another_process():
    code = (
        "from bsela.llm.runtime import model_run,ProviderError\n"
        "try:\n"
        " with model_run(): pass\n"
        "except ProviderError as error:\n"
        " print(error)\n"
        " raise SystemExit(7)\n"
    )
    with model_run():
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 7
    assert "overlap" in result.stdout
