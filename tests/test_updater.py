"""P3 tests: updater writes a proposal branch + commit on agents-md."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from bsela.core.updater import (
    BRANCH_PREFIX,
    DEFAULT_AGENTS_MD_REPO,
    DRAFTS_SUBDIR,
    ProposalResult,
    UpdaterError,
    _detect_base_branch,
    propose_lesson,
    resolve_agents_md_repo,
)
from bsela.memory.models import Lesson


def _run(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def fake_agents_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "agents-md"
    repo.mkdir()
    _run(repo, "init", "-b", "main")
    _run(repo, "config", "user.email", "test@example.com")
    _run(repo, "config", "user.name", "Tester")
    (repo / "README.md").write_text("agents-md\n", encoding="utf-8")
    _run(repo, "add", "README.md")
    _run(repo, "commit", "-m", "chore: seed")
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(repo))
    return repo


def _lesson(
    *,
    scope: str = "project",
    rule: str = "Stop retrying Read on missing path after first ENOENT",
    why: str = "Detector flagged looped Read calls returning ENOENT",
    how_to_apply: str = "Change strategy after two ENOENTs on same path",
    confidence: float = 0.92,
) -> Lesson:
    return Lesson(
        scope=scope,
        rule=rule,
        why=why,
        how_to_apply=how_to_apply,
        confidence=confidence,
    )


def test_resolve_repo_prefers_override_over_env(tmp_path: Path) -> None:
    target = tmp_path / "explicit"
    target.mkdir()
    resolved = resolve_agents_md_repo(target)
    assert resolved == target.resolve()


def test_resolve_repo_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_target = tmp_path / "env-target"
    env_target.mkdir()
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(env_target))
    assert resolve_agents_md_repo() == env_target.resolve()


def test_propose_lesson_creates_branch_and_commit(fake_agents_md: Path) -> None:
    lesson = _lesson()
    result = propose_lesson(lesson)

    assert isinstance(result, ProposalResult)
    assert result.base_branch == "main"
    assert result.branch.startswith(f"{BRANCH_PREFIX}/")
    assert result.repo == fake_agents_md.resolve()

    rel = result.file_path.relative_to(result.repo)
    assert rel.parts[:2] == DRAFTS_SUBDIR.parts
    assert rel.name == f"{lesson.id}.md"
    body = result.file_path.read_text(encoding="utf-8")
    assert lesson.rule in body
    assert "**Why**" in body
    assert "**How to apply**" in body

    current = _run(fake_agents_md, "rev-parse", "--abbrev-ref", "HEAD")
    assert current == result.branch
    log = _run(fake_agents_md, "log", "--format=%s", "-n", "1")
    assert log.startswith("feat(bsela-lesson): ")
    assert result.commit_sha
    main_sha = _run(fake_agents_md, "rev-parse", "main")
    assert main_sha != result.commit_sha


def test_propose_lesson_refuses_dirty_worktree(fake_agents_md: Path) -> None:
    (fake_agents_md / "dirty.txt").write_text("uncommitted", encoding="utf-8")
    with pytest.raises(UpdaterError, match="worktree is dirty"):
        propose_lesson(_lesson())


def test_propose_lesson_requires_existing_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(missing))
    with pytest.raises(UpdaterError, match="not found"):
        propose_lesson(_lesson())


def test_propose_lesson_rejects_non_git_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("BSELA_AGENTS_MD_REPO", str(plain))
    with pytest.raises(UpdaterError, match="not a git working copy"):
        propose_lesson(_lesson())


def test_propose_lesson_is_idempotent_on_rerun(fake_agents_md: Path) -> None:
    lesson = _lesson()
    first = propose_lesson(lesson)
    _run(fake_agents_md, "checkout", first.base_branch)
    second = propose_lesson(lesson)
    assert second.branch == first.branch
    assert second.commit_sha == first.commit_sha
    log = _run(fake_agents_md, "log", second.branch, "--format=%s").splitlines()
    assert log[0].startswith("feat(bsela-lesson): ")
    assert log[-1] == "chore: seed"
    assert len(log) == 2


def test_resolve_repo_uses_default_when_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover line 56: neither override nor env var → DEFAULT_AGENTS_MD_REPO.resolve()."""
    monkeypatch.delenv("BSELA_AGENTS_MD_REPO", raising=False)
    result = resolve_agents_md_repo()
    assert result == DEFAULT_AGENTS_MD_REPO.resolve()


def test_detect_base_branch_returns_master(fake_agents_md: Path) -> None:
    """Cover line 102-103: repo has 'master' not 'main'."""
    # Create a master-only repo by renaming the default main branch.
    _run(fake_agents_md, "branch", "-m", "main", "master")
    with patch.dict("os.environ", {"BSELA_AGENTS_MD_REPO": str(fake_agents_md)}):
        branch = _detect_base_branch(fake_agents_md)
    assert branch == "master"


def test_detect_base_branch_raises_when_neither(fake_agents_md: Path) -> None:
    """Cover line 104: no main or master branch raises UpdaterError."""
    _run(fake_agents_md, "branch", "-m", "main", "trunk")
    with pytest.raises(UpdaterError, match="no main/master branch"):
        _detect_base_branch(fake_agents_md)
