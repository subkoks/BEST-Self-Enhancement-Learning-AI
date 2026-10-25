"""Tests for ``bsela scan`` and ``bsela hook codex-stop``."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.adapters import codex as codex_adapter
from bsela.cli import app
from bsela.core import scan as scan_module
from bsela.memory.models import Lesson
from bsela.memory.store import count_sessions, list_errors, list_sessions, save_lesson

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"
SESSION_ID = "019d1234-5678-7abc-8def-0123456789ab"
GUARDIAN_ID = "019d9999-1111-7222-8333-444455556666"


def _seed_root(
    tmp_path: Path,
    *,
    fixture: Path = FIXTURES / "codex-rollout.jsonl",
    session_id: str = SESSION_ID,
    thread_source: str = "user",
    age_days: int = 0,
) -> Path:
    root = tmp_path / "sessions"
    day = root / "2026" / "01" / "16"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-01-16T10-00-00-{session_id}.jsonl"
    lines = []
    for raw in fixture.read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        if event.get("type") == "session_meta":
            event["payload"]["id"] = session_id
            event["payload"]["session_id"] = session_id
            event["payload"]["thread_source"] = thread_source
        lines.append(json.dumps(event))
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    stamp = datetime.now(UTC).timestamp() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return root


def _append_user_message(path: Path, text: str) -> None:
    event = {
        "timestamp": "2026-01-16T10:05:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


# ---- bsela scan ------------------------------------------------------------


def test_scan_dry_run_lists_without_writing(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    result = CliRunner().invoke(app, ["scan", "--root", str(root), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "scan (dry-run): 1 rollout(s)" in result.stdout
    assert "pending" in result.stdout
    assert "no store writes" in result.stdout
    assert count_sessions() == 0


def test_scan_ingests_rollouts_and_emits_json(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    result = CliRunner().invoke(app, ["scan", "--root", str(root), "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["captured"] == 1
    assert payload["updated"] == 0
    assert payload["considered"] == 1
    assert payload["rollouts"][0]["turn_count"] == 2
    assert payload["rollouts"][0]["path"].endswith(".jsonl")
    assert count_sessions() == 1


def test_scan_reports_unchanged_then_updated(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    path = next(root.rglob("rollout-*.jsonl"))
    runner = CliRunner()
    assert runner.invoke(app, ["scan", "--root", str(root)]).exit_code == 0

    repeat = runner.invoke(app, ["scan", "--root", str(root)])
    assert "unchanged=1" in repeat.stdout

    _append_user_message(path, "one more turn")
    grown = runner.invoke(app, ["scan", "--root", str(root)])
    assert "updated=1" in grown.stdout
    assert count_sessions() == 1


def test_scan_skips_internal_threads(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path, session_id=GUARDIAN_ID, thread_source="guardian_review")
    result = CliRunner().invoke(app, ["scan", "--root", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "0 rollout(s)" in result.stdout
    assert count_sessions() == 0


def test_scan_window_filters_old_rollouts(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path, age_days=30)
    result = CliRunner().invoke(app, ["scan", "--root", str(root), "--since-days", "7"])
    assert "0 rollout(s)" in result.stdout

    unbounded = CliRunner().invoke(app, ["scan", "--root", str(root), "--since-days", "0"])
    assert "captured=1" in unbounded.stdout


def test_scan_reports_failures_without_aborting(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("rollout vanished mid-scan")

    monkeypatch.setattr(scan_module, "ingest_file", boom)
    result = CliRunner().invoke(app, ["scan", "--root", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "failed=1" in result.stdout
    assert "rollout vanished mid-scan" in result.stdout


def test_scan_flags_quarantined_rollout(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    path = next(root.rglob("rollout-*.jsonl"))
    _append_user_message(path, "token ghp_0123456789abcdefghijklmnopqrstuvwxyz")

    result = CliRunner().invoke(app, ["scan", "--root", str(root), "--json"])
    payload = json.loads(result.stdout)
    assert payload["quarantined"] == 1
    assert payload["rollouts"][0]["status"] == "quarantined"


def test_scan_reports_skipped_distilled_session(tmp_bsela_home: Path, tmp_path: Path) -> None:
    root = _seed_root(tmp_path, fixture=FIXTURES / "codex-correction.jsonl")
    path = next(root.rglob("rollout-*.jsonl"))
    runner = CliRunner()
    assert runner.invoke(app, ["scan", "--root", str(root)]).exit_code == 0

    session = list_sessions()[0]
    error = list_errors(session_id=session.id)[0]
    save_lesson(
        Lesson(
            source_error_id=error.id,
            scope="global",
            rule="Re-read the file instead of repeating the same command.",
            why="Repeated identical calls waste budget.",
            how_to_apply="Check the last tool result before retrying.",
            confidence=0.8,
        )
    )
    _append_user_message(path, "one more thing")

    result = runner.invoke(app, ["scan", "--root", str(root)])
    assert result.exit_code == 0, result.stdout
    assert "skipped=1" in result.stdout
    assert "(distilled)" in result.stdout


# ---- bsela hook codex-stop -------------------------------------------------


def _point_adapter_at(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(codex_adapter.rollout, "default_session_roots", lambda: (root,))


def test_codex_stop_ingests_from_notify_argument(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)
    payload = json.dumps({"type": "agent-turn-complete", "thread-id": SESSION_ID})

    result = CliRunner().invoke(app, ["hook", "codex-stop", payload])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert count_sessions() == 1
    assert list_sessions()[0].source == "codex"


def test_codex_stop_reads_hooks_payload_from_stdin(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)
    path = next(root.rglob("rollout-*.jsonl"))
    payload = json.dumps(
        {
            "session_id": SESSION_ID,
            "transcript_path": str(path),
            "hook_event_name": "SessionEnd",
        }
    )

    result = CliRunner().invoke(app, ["hook", "codex-stop"], input=payload)
    assert result.exit_code == 0
    assert count_sessions() == 1


def test_codex_stop_falls_back_to_session_lookup_for_missing_path(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)
    payload = json.dumps(
        {"transcript_path": str(tmp_path / "gone.jsonl"), "session_id": SESSION_ID}
    )

    result = CliRunner().invoke(app, ["hook", "codex-stop", payload])
    assert result.exit_code == 0
    assert count_sessions() == 1


def test_codex_stop_updates_row_on_growth(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)
    path = next(root.rglob("rollout-*.jsonl"))
    payload = json.dumps({"thread_id": SESSION_ID})
    runner = CliRunner()

    assert runner.invoke(app, ["hook", "codex-stop", payload]).exit_code == 0
    _append_user_message(path, "follow-up request")
    assert runner.invoke(app, ["hook", "codex-stop", payload]).exit_code == 0
    assert count_sessions() == 1
    assert list_sessions()[0].turn_count == 3


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json at all",
        json.dumps(["a", "list"]),
        json.dumps({"type": "agent-turn-complete"}),
        json.dumps({"thread-id": "019d9999-1111-7222-8333-444455556666"}),
        json.dumps({"session_id": "   "}),
    ],
)
def test_codex_stop_is_silent_when_payload_is_unusable(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)
    args = ["hook", "codex-stop", payload] if payload else ["hook", "codex-stop"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert result.stdout == ""
    assert count_sessions() == 0


def test_codex_stop_swallows_ingest_failures(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _seed_root(tmp_path)
    _point_adapter_at(monkeypatch, root)

    def boom(*args: object, **kwargs: object) -> None:
        raise ValueError("unreadable rollout")

    monkeypatch.setattr("bsela.cli.ingest_file", boom)
    result = CliRunner().invoke(app, ["hook", "codex-stop", json.dumps({"thread-id": SESSION_ID})])
    assert result.exit_code == 0
    assert result.stdout == ""
