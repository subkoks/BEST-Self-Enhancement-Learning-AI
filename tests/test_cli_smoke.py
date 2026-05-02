"""Smoke tests: CLI loads and all commands respond without crashing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bsela import __version__
from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.core.hook_install import InstallPlan, InstallResult
from bsela.core.process import ProcessResult
from bsela.llm.distiller import DistillationResult
from bsela.llm.types import DistillResponse, JudgeVerdict
from bsela.memory.models import ErrorRecord, Lesson
from bsela.memory.store import list_sessions, save_error, save_lesson, update_lesson_status


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("status", "ingest", "review", "lessons", "rollback"):
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
    assert payload["lessons_proposed"] == 0
    assert "bsela_home" in payload
    assert sorted(payload.keys()) == [
        "bsela_home",
        "errors",
        "lessons",
        "lessons_pending",
        "lessons_proposed",
        "replay_records",
        "sessions",
        "sessions_quarantined",
    ]


def test_review_with_empty_store_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BSELA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0
    assert "no lessons awaiting action" in result.stdout


def test_lessons_json_with_empty_store_returns_empty_array(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["lessons", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == []


def test_lessons_json_locks_item_keys(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(session_id=session_id, category="loop", severity="medium", snippet="test")
    )
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="Never repeat the same failed call",
            why="Avoid retry loops and token waste.",
            how_to_apply="Change strategy after repeated failure.",
            confidence=0.9,
            status="pending",
        )
    )

    result = CliRunner().invoke(app, ["lessons", "--json", "--limit", "1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert sorted(payload[0].keys()) == [
        "confidence",
        "created_at",
        "hit_count",
        "how_to_apply",
        "id",
        "rule",
        "scope",
        "status",
        "why",
    ]


def test_rollback_not_found_exits_1(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["rollback", "no-such-id"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_rollback_pending_lesson_succeeds(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            severity="medium",
            snippet="test",
        )
    )
    lesson = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="Never do X",
            why="reason",
            how_to_apply="action",
            confidence=0.9,
            status="pending",
        )
    )
    result = CliRunner().invoke(app, ["rollback", lesson.id])
    assert result.exit_code == 0
    assert "rolled back" in result.stdout


def test_rollback_already_rolled_back_exits_0(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            severity="medium",
            snippet="test",
        )
    )
    lesson = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="Never do Y",
            why="reason",
            how_to_apply="action",
            confidence=0.9,
            status="rolled_back",
        )
    )
    result = CliRunner().invoke(app, ["rollback", lesson.id])
    assert result.exit_code == 0
    assert "already rolled back" in result.stdout


def test_doctor_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "doctor:" in result.stdout


def test_route_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["route", "write a unit test"])
    assert result.exit_code == 0
    assert len(result.stdout.strip()) > 0


def test_audit_stdout_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["audit", "--stdout"])
    assert result.exit_code in (0, 1)


def test_report_stdout_exits_without_crash(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["report", "--stdout"])
    assert result.exit_code == 0


# ---- distill CLI command ----


def _healthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=True, efficiency=0.95, looped=False, wasted_tokens=False, confidence=0.9
    )


def _unhealthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=False, efficiency=0.3, looped=True, wasted_tokens=True, confidence=0.6
    )


def _fake_distill_result(
    verdict: JudgeVerdict, distilled: bool, lessons: tuple[Lesson, ...] = ()
) -> DistillationResult:
    return DistillationResult(
        session_id="fake-session-id",
        verdict=verdict,
        distilled=distilled,
        response=DistillResponse(status="ok"),
        persisted=lessons,
    )


def test_distill_cli_healthy_session(tmp_bsela_home: Path) -> None:
    """distill CLI: judge says healthy → no lessons, exit 0."""
    fake_result = _fake_distill_result(_healthy_verdict(), distilled=False)
    fake_client = MagicMock()
    with (
        patch("bsela.cli.make_llm_client", return_value=fake_client),
        patch("bsela.cli.distill_session", return_value=fake_result),
    ):
        result = CliRunner().invoke(app, ["distill", "--session-id", "fake-session-id"])
    assert result.exit_code == 0
    assert "judge says healthy" in result.stdout


def test_distill_cli_distills_session(tmp_bsela_home: Path) -> None:
    """distill CLI: distilled → lesson count message, exit 0."""
    lesson = Lesson(
        scope="project", rule="test rule", why="why", how_to_apply="how", confidence=0.9
    )
    fake_result = _fake_distill_result(_unhealthy_verdict(), distilled=True, lessons=(lesson,))
    fake_client = MagicMock()
    with (
        patch("bsela.cli.make_llm_client", return_value=fake_client),
        patch("bsela.cli.distill_session", return_value=fake_result),
    ):
        result = CliRunner().invoke(app, ["distill", "--session-id", "fake-session-id"])
    assert result.exit_code == 0
    assert "1 lesson(s)" in result.stdout
    assert "persisted" in result.stdout


def test_distill_cli_no_persist(tmp_bsela_home: Path) -> None:
    """distill CLI: --no-persist → 'drafted' in message."""
    lesson = Lesson(
        scope="project", rule="test rule", why="why", how_to_apply="how", confidence=0.9
    )
    fake_result = _fake_distill_result(_unhealthy_verdict(), distilled=True, lessons=(lesson,))
    fake_client = MagicMock()
    with (
        patch("bsela.cli.make_llm_client", return_value=fake_client),
        patch("bsela.cli.distill_session", return_value=fake_result),
    ):
        result = CliRunner().invoke(
            app, ["distill", "--session-id", "fake-session-id", "--no-persist"]
        )
    assert result.exit_code == 0
    assert "drafted" in result.stdout


# ---- rollback with approved/proposed lesson ----


def test_rollback_approved_hints_agents_md(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    """rollback: approved lesson prints agents-md warning."""
    ingest_file(sample_clean_session)
    session_id = list_sessions()[0].id
    err = save_error(
        ErrorRecord(session_id=session_id, category="loop", severity="medium", snippet="t")
    )
    lesson = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule="rule",
            why="why",
            how_to_apply="how",
            confidence=0.9,
            status="pending",
        )
    )
    update_lesson_status(lesson.id, status="approved", note=None)

    result = CliRunner().invoke(app, ["rollback", lesson.id])
    assert result.exit_code == 0
    assert "rolled back" in result.stdout
    assert "agents-md" in result.stdout


# ---- hook install error paths ----


def test_hook_install_dry_run_oserror(tmp_path: Path) -> None:
    """hook install dry-run: OSError reading target → exit 1."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        result = CliRunner().invoke(app, ["hook", "install", "--settings", str(settings)])
    assert result.exit_code == 1
    assert "cannot read" in result.stdout


def test_hook_install_dry_run_non_object(tmp_path: Path) -> None:
    """hook install dry-run: top-level JSON is not an object → exit 1."""
    settings = tmp_path / "settings.json"
    settings.write_text("[1, 2, 3]", encoding="utf-8")
    result = CliRunner().invoke(app, ["hook", "install", "--settings", str(settings)])
    assert result.exit_code == 1
    assert "not a JSON object" in result.stdout


def test_hook_install_apply_oserror(tmp_path: Path) -> None:
    """hook install --apply: OSError in apply_install → exit 1."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    with patch("bsela.cli.apply_install", side_effect=OSError("disk full")):
        result = CliRunner().invoke(
            app, ["hook", "install", "--apply", "--settings", str(settings)]
        )
    assert result.exit_code == 1
    assert "disk full" in result.stdout


def test_hook_install_apply_with_backup(tmp_path: Path) -> None:
    """hook install --apply: backup path appears in success message."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    backup_path = tmp_path / "settings.json.bak"

    plan = InstallPlan(changed=True, reason="installed", merged={})
    mock_result = InstallResult(wrote=True, path=settings, plan=plan, backup=backup_path)

    with patch("bsela.cli.apply_install", return_value=mock_result):
        result = CliRunner().invoke(
            app, ["hook", "install", "--apply", "--settings", str(settings)]
        )
    assert result.exit_code == 0
    assert "backup" in result.stdout


# ---- process with errors hint ----


def test_process_cli_errors_hint(tmp_bsela_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """process CLI: errors > 0 prints billing hint."""
    fake_result = ProcessResult(
        considered=1,
        processed=1,
        distilled=0,
        lessons_created=0,
        skipped_quarantined=0,
        skipped_no_errors=0,
        skipped_already_distilled=0,
        skipped_judge_healthy=0,
        errors=1,
    )
    fake_client = MagicMock()
    monkeypatch.setattr("bsela.cli.make_llm_client", lambda: fake_client)
    with patch("bsela.cli.process_sessions", return_value=fake_result):
        result = CliRunner().invoke(app, ["process"])
    assert result.exit_code == 0
    assert "hint" in result.stdout


def test_python_m_bsela_prints_help() -> None:
    """Cover __main__.py: `python -m bsela` invokes the CLI and exits cleanly."""
    result = subprocess.run(
        [sys.executable, "-m", "bsela", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "bsela" in result.stdout.lower()
