"""P3 tests: bsela review list / propose / reject."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.updater import UpdaterError
from bsela.memory.models import Lesson
from bsela.memory.store import get_lesson, increment_hit_count, save_lesson, update_lesson_status


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def fake_agents_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "agents-md"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "README.md").write_text("agents-md\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "chore: seed")
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(repo))
    return repo


def _project_lesson(confidence: float = 0.95) -> Lesson:
    return save_lesson(
        Lesson(
            scope="project",
            rule="Stop retrying Read on ENOENT after first miss",
            why="Detector flagged three identical Reads returning ENOENT",
            how_to_apply="On ENOENT twice, change strategy",
            confidence=confidence,
        )
    )


def _global_lesson() -> Lesson:
    return save_lesson(
        Lesson(
            scope="global",
            rule="Prefer ruff check before commit",
            why="Catches lint regressions early",
            how_to_apply="Run ruff before every commit",
            confidence=0.99,
        )
    )


def _safety_lesson() -> Lesson:
    return save_lesson(
        Lesson(
            scope="project",
            rule="Confirm before a wallet transfer",
            why="Prevents irreversible fund loss",
            how_to_apply="Show signer diff for any wallet transfer",
            confidence=0.99,
        )
    )


def test_review_list_shows_pending_lessons(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0, result.stdout
    assert lesson.id in result.stdout
    assert "[AUTO]" in result.stdout


def test_review_list_tags_review_and_safety(tmp_bsela_home: Path) -> None:
    _global_lesson()
    _safety_lesson()
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0, result.stdout
    assert "[REVIEW]" in result.stdout
    assert "[SAFETY]" in result.stdout


def test_review_propose_writes_branch_and_approves(
    tmp_bsela_home: Path, fake_agents_md: Path
) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["review", "propose", lesson.id])
    assert result.exit_code == 0, result.stdout
    assert "proposed lesson" in result.stdout
    assert "status=approved" in result.stdout

    refreshed = get_lesson(lesson.id)
    assert refreshed is not None
    assert refreshed.status == "approved"

    current = _git(fake_agents_md, "rev-parse", "--abbrev-ref", "HEAD")
    assert current.startswith("bsela/lesson/")


def test_review_propose_global_scope_leaves_as_proposed(
    tmp_bsela_home: Path, fake_agents_md: Path
) -> None:
    lesson = _global_lesson()
    result = CliRunner().invoke(app, ["review", "propose", lesson.id])
    assert result.exit_code == 0, result.stdout
    refreshed = get_lesson(lesson.id)
    assert refreshed is not None
    assert refreshed.status == "proposed"


def test_review_propose_rejects_unknown_id(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["review", "propose", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_review_propose_rejects_non_pending(tmp_bsela_home: Path, fake_agents_md: Path) -> None:
    lesson = _project_lesson()
    first = CliRunner().invoke(app, ["review", "propose", lesson.id])
    assert first.exit_code == 0, first.stdout
    second = CliRunner().invoke(app, ["review", "propose", lesson.id])
    assert second.exit_code == 1
    assert "nothing to propose" in second.stdout


def test_review_reject_marks_status_rejected(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["review", "reject", lesson.id, "--note", "not transferable"])
    assert result.exit_code == 0, result.stdout
    refreshed = get_lesson(lesson.id)
    assert refreshed is not None
    assert refreshed.status == "rejected"
    assert "not transferable" in refreshed.how_to_apply


def test_review_reject_unknown_id_exits_nonzero(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["review", "reject", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


# ---- review list subcommand ----


def test_review_list_no_filter_shows_all(tmp_bsela_home: Path) -> None:
    pending = _project_lesson()  # status=pending
    result = CliRunner().invoke(app, ["review", "list"])
    assert result.exit_code == 0
    assert pending.id in result.stdout
    assert "pending" in result.stdout


def test_review_list_status_filter(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    # Reject it, then list by status.
    CliRunner().invoke(app, ["review", "reject", lesson.id])
    result = CliRunner().invoke(app, ["review", "list", "--status", "rejected"])
    assert result.exit_code == 0
    assert lesson.id in result.stdout
    assert "rejected" in result.stdout


def test_review_list_empty_pending_shows_message(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["review", "list", "--status", "pending"])
    assert result.exit_code == 0
    assert "no lessons" in result.stdout


def test_review_list_json_output(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["review", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert any(item["id"] == lesson.id for item in data)
    # Check expected keys present
    assert all("rule" in item and "status" in item and "confidence" in item for item in data)


def test_review_list_limit(tmp_bsela_home: Path) -> None:
    for _ in range(5):
        _project_lesson()
    result = CliRunner().invoke(app, ["review", "list", "--limit", "2"])
    assert result.exit_code == 0
    assert result.stdout.count("\n") == 2


def test_review_propose_updater_error(tmp_bsela_home: Path) -> None:
    """Cover UpdaterError path in review propose (exit 2)."""
    lesson = _project_lesson()
    with patch("bsela.cli.propose_lesson", side_effect=UpdaterError("git failed")):
        result = CliRunner().invoke(app, ["review", "propose", lesson.id])
    assert result.exit_code == 2
    assert "proposal failed" in result.stdout


def test_review_reject_non_pending_exits_nonzero(tmp_bsela_home: Path) -> None:
    """Cover 'cannot reject' branch: reject an already-rejected lesson."""
    lesson = _project_lesson()
    update_lesson_status(lesson.id, status="rejected", note=None)
    result = CliRunner().invoke(app, ["review", "reject", lesson.id])
    assert result.exit_code == 1
    assert "cannot reject" in result.stdout


def test_review_root_shows_proposed_lessons(tmp_bsela_home: Path) -> None:
    """Cover lines 272-276: review root shows proposed + pending lessons."""
    # Create a proposed lesson
    lesson = _project_lesson()
    update_lesson_status(lesson.id, status="proposed", note=None)
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0
    assert "proposed" in result.stdout
    assert lesson.id[:8] in result.stdout


def test_review_root_shows_pending_lessons(tmp_bsela_home: Path) -> None:
    """Cover lines 277-280: review root shows pending lessons."""
    _project_lesson()  # default status is pending
    result = CliRunner().invoke(app, ["review"])
    assert result.exit_code == 0
    assert "pending" in result.stdout


def test_review_list_track_hits(tmp_bsela_home: Path) -> None:
    """Cover line 307: --track-hits increments hit_count on returned lessons."""
    increment_hit_count([])  # warm import; real assertion below
    lesson = _project_lesson()
    assert lesson.hit_count == 0
    result = CliRunner().invoke(app, ["review", "list", "--track-hits"])
    assert result.exit_code == 0
    updated = get_lesson(lesson.id)
    assert updated is not None
    assert updated.hit_count == 1


def test_lessons_alias_json_output(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["lessons", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    entry = next(item for item in data if item["id"] == lesson.id)
    assert sorted(entry.keys()) == [
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
    assert entry["hit_count"] == 0


def test_lessons_alias_track_hits(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    assert lesson.hit_count == 0
    result = CliRunner().invoke(app, ["lessons", "--track-hits"])
    assert result.exit_code == 0
    updated = get_lesson(lesson.id)
    assert updated is not None
    assert updated.hit_count == 1


def test_lessons_alias_track_hits_json_reflects_increment(tmp_bsela_home: Path) -> None:
    lesson = _project_lesson()
    result = CliRunner().invoke(app, ["lessons", "--json", "--track-hits", "--limit", "1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == lesson.id
    # JSON payload reflects the selected row before increment; persistence updates after.
    assert data[0]["hit_count"] == 0
    updated = get_lesson(lesson.id)
    assert updated is not None
    assert updated.hit_count == 1


def test_review_show_displays_lesson_details(tmp_bsela_home: Path) -> None:
    """Cover review_show: displays lesson fields including rule, why, how_to_apply."""
    lesson = _project_lesson(confidence=0.87)
    result = CliRunner().invoke(app, ["review", "show", lesson.id])
    assert result.exit_code == 0
    assert lesson.id in result.stdout
    assert "pending" in result.stdout
    assert "project" in result.stdout
    assert "0.87" in result.stdout
    assert lesson.rule in result.stdout
    assert lesson.why in result.stdout
    assert lesson.how_to_apply in result.stdout


def test_review_show_not_found_exits_nonzero(tmp_bsela_home: Path) -> None:
    """Cover review_show not-found branch."""
    result = CliRunner().invoke(app, ["review", "show", "nonexistent-uuid"])
    assert result.exit_code == 1
    assert "not found" in result.stdout
