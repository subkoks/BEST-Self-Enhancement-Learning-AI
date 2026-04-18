"""Proposal-branch writer for the canonical ``agents-md`` repo.

Given a pending ``Lesson``, the updater:

1. Resolves the ``agents-md`` working copy (``BSELA_AGENTS_MD_REPO`` env
   or ``~/Projects/Current/Active/agents-md`` fallback).
2. Creates a branch ``bsela/lesson/<short-id>`` rooted on the current base
   branch.
3. Writes ``drafts/bsela-lessons/<lesson-id>.md`` with the canonical
   lesson structure (``rule`` / Why / How to apply).
4. Stages + commits the file with a conventional message.

The updater never pushes and never merges. ``bsela review`` decides the
status transition; the user handles the PR. All git invocations go
through ``subprocess.run`` — no additional dependency surface.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bsela.memory.models import Lesson

DEFAULT_AGENTS_MD_REPO = Path("~/Projects/Current/Active/agents-md").expanduser()
DRAFTS_SUBDIR = Path("drafts/bsela-lessons")
BRANCH_PREFIX = "bsela/lesson"


class UpdaterError(RuntimeError):
    """Raised when the updater cannot produce a proposal branch."""


@dataclass(frozen=True)
class ProposalResult:
    """Outcome of ``propose_lesson``."""

    lesson_id: str
    repo: Path
    branch: str
    base_branch: str
    file_path: Path
    commit_sha: str


def resolve_agents_md_repo(override: Path | None = None) -> Path:
    """Resolve the agents-md working copy. Override > env > default."""
    if override is not None:
        return override.expanduser().resolve()
    env = os.environ.get("BSELA_AGENTS_MD_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_AGENTS_MD_REPO.resolve()


def _run_git(repo: Path, *args: str) -> str:
    """Invoke ``git`` inside ``repo`` and return trimmed stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover — git is expected
        raise UpdaterError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise UpdaterError(f"git {' '.join(args)} failed: {stderr}") from exc
    return result.stdout.strip()


def _require_clean_worktree(repo: Path) -> None:
    status = _run_git(repo, "status", "--porcelain")
    if status:
        raise UpdaterError(
            f"agents-md worktree is dirty ({repo}) — commit or stash before proposing."
        )


def _has_staged_changes(repo: Path) -> bool:
    """True when there is something staged to commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def _detect_base_branch(repo: Path) -> str:
    branches = _run_git(repo, "branch", "--list", "main", "master").splitlines()
    names = {line.lstrip("* ").strip() for line in branches if line.strip()}
    if "main" in names:
        return "main"
    if "master" in names:
        return "master"
    raise UpdaterError(f"no main/master branch in {repo} — unsupported layout")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, *, limit: int = 40) -> str:
    lowered = text.lower().strip()
    slug = _SLUG_RE.sub("-", lowered).strip("-")
    return slug[:limit].rstrip("-") or "lesson"


def _ensure_repo(repo: Path) -> Path:
    if not repo.exists():
        raise UpdaterError(f"agents-md repo not found: {repo}")
    if not (repo / ".git").exists():
        raise UpdaterError(f"{repo} is not a git working copy")
    return repo


def _short_id(lesson_id: str) -> str:
    head = lesson_id.split("-", 1)[0]
    return head[:12] if head else lesson_id[:12]


def _render_markdown(lesson: Lesson) -> str:
    return (
        f"# Lesson {lesson.id}\n\n"
        f"**Rule**: {lesson.rule}\n\n"
        f"**Why**: {lesson.why}\n\n"
        f"**How to apply**: {lesson.how_to_apply}\n\n"
        f"**Scope**: `{lesson.scope}`\n\n"
        f"**Confidence**: {lesson.confidence:.2f}\n\n"
        f"**Source error**: `{lesson.source_error_id or 'n/a'}`\n\n"
        f"**Created at**: {lesson.created_at.isoformat()}\n"
    )


def propose_lesson(
    lesson: Lesson,
    *,
    repo: Path | None = None,
) -> ProposalResult:
    """Write ``lesson`` as a proposal branch on the agents-md repo."""
    working = _ensure_repo(resolve_agents_md_repo(repo))
    _require_clean_worktree(working)
    base = _detect_base_branch(working)

    branch = f"{BRANCH_PREFIX}/{_short_id(lesson.id)}-{_slug(lesson.rule)}"
    drafts_dir = working / DRAFTS_SUBDIR
    file_path = drafts_dir / f"{lesson.id}.md"

    _run_git(working, "checkout", base)
    try:
        _run_git(working, "checkout", "-b", branch)
    except UpdaterError:
        # Branch already exists (re-propose scenario) — switch to it.
        _run_git(working, "checkout", branch)

    drafts_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(_render_markdown(lesson), encoding="utf-8")

    rel = file_path.relative_to(working)
    _run_git(working, "add", str(rel))
    subject = f"feat(bsela-lesson): {lesson.rule[:70]}"
    if _has_staged_changes(working):
        _run_git(working, "commit", "-m", subject)
    sha = _run_git(working, "rev-parse", "HEAD")

    return ProposalResult(
        lesson_id=lesson.id,
        repo=working,
        branch=branch,
        base_branch=base,
        file_path=file_path,
        commit_sha=sha,
    )


__all__ = [
    "BRANCH_PREFIX",
    "DEFAULT_AGENTS_MD_REPO",
    "DRAFTS_SUBDIR",
    "ProposalResult",
    "UpdaterError",
    "propose_lesson",
    "resolve_agents_md_repo",
]
