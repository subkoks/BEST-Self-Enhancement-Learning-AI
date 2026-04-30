"""Environment smoke check for BSELA — ``bsela doctor``.

Runs a handful of cheap, read-only probes against the local
environment and reports pass / warn / fail for each. Useful during
P4 dogfood when something stops producing lessons and the operator
needs a quick triage — "is the API key set? is the hook installed?
does the agents-md repo exist?"

Pure ``run_checks`` returns a list of ``CheckResult`` dataclasses so
the CLI layer is a thin formatter. Each probe is self-contained and
isolated: a failure in one does not abort the rest.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bsela.core.hook_install import (
    DEFAULT_EVENT,
    DEFAULT_HOOK_COMMAND,
    default_claude_settings_path,
)
from bsela.memory.store import bsela_home, db_path

PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str


def _check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info.micro}"
    if (major, minor) < (3, 13):
        return CheckResult(
            "python",
            FAIL,
            f"need >= 3.13, found {version}",
        )
    return CheckResult("python", PASS, version)


def _check_llm_api_key() -> CheckResult:
    """Accept either ANTHROPIC_API_KEY or OPENROUTER_API_KEY."""
    anthropic = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    openrouter = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if anthropic:
        return CheckResult("LLM API key", PASS, f"ANTHROPIC_API_KEY set ({len(anthropic)} chars)")
    if openrouter:
        return CheckResult("LLM API key", PASS, f"OPENROUTER_API_KEY set ({len(openrouter)} chars)")
    return CheckResult(
        "LLM API key",
        FAIL,
        "neither ANTHROPIC_API_KEY nor OPENROUTER_API_KEY is set — bsela distill / process will fail",
    )


def _check_bsela_home() -> CheckResult:
    home = bsela_home()
    if not home.exists():
        return CheckResult(
            "bsela_home",
            WARN,
            f"{home} does not exist yet (will be created on first ingest)",
        )
    return CheckResult("bsela_home", PASS, str(home))


def _check_db() -> CheckResult:
    path = db_path()
    if not path.exists():
        return CheckResult(
            "store",
            WARN,
            f"{path} does not exist yet (created lazily on first write)",
        )
    size_kb = path.stat().st_size / 1024
    return CheckResult("store", PASS, f"{path} ({size_kb:.1f} KiB)")


def _check_bsela_on_path() -> CheckResult:
    exe = shutil.which("bsela")
    if exe is None:
        return CheckResult(
            "bsela on PATH",
            FAIL,
            "not found — run `uv tool install -e .` from the repo root",
        )
    return CheckResult("bsela on PATH", PASS, exe)


def _check_agents_md_repo() -> CheckResult:
    override = os.environ.get("BSELA_AGENTS_MD_REPO")
    if override:
        candidate = Path(override).expanduser()
        label = f"{candidate} (via BSELA_AGENTS_MD_REPO)"
    else:
        candidate = Path.home() / "Projects" / "Current" / "Active" / "agents-md"
        label = str(candidate)
    if not candidate.exists():
        return CheckResult(
            "agents-md repo",
            WARN,
            f"{label} not found — bsela review propose will fail",
        )
    if not (candidate / ".git").exists():
        return CheckResult("agents-md repo", FAIL, f"{label} is not a git repo")
    return CheckResult("agents-md repo", PASS, label)


def _read_claude_settings(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _check_claude_hook(settings_path: Path | None = None) -> CheckResult:
    path = settings_path or default_claude_settings_path()
    if not path.exists():
        return CheckResult(
            "claude-code hook",
            WARN,
            f"{path} does not exist — run `bsela hook install --apply`",
        )
    data = _read_claude_settings(path)
    if data is None:
        return CheckResult(
            "claude-code hook",
            FAIL,
            f"{path} is not valid JSON",
        )
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return CheckResult(
            "claude-code hook",
            WARN,
            f"no hooks block in {path} — run `bsela hook install --apply`",
        )
    stop_groups = hooks.get(DEFAULT_EVENT)
    if not isinstance(stop_groups, list):
        return CheckResult(
            "claude-code hook",
            WARN,
            f"no {DEFAULT_EVENT} hook registered — run `bsela hook install --apply`",
        )
    for group in stop_groups:
        if not isinstance(group, dict):
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if (
                isinstance(entry, dict)
                and entry.get("type") == "command"
                and entry.get("command") == DEFAULT_HOOK_COMMAND
            ):
                return CheckResult("claude-code hook", PASS, "registered")
    return CheckResult(
        "claude-code hook",
        WARN,
        f"{DEFAULT_HOOK_COMMAND!r} not registered under {DEFAULT_EVENT} — "
        "run `bsela hook install --apply`",
    )


def run_checks(*, settings_path: Path | None = None) -> list[CheckResult]:
    """Run all probes and return the flat result list."""
    return [
        _check_python(),
        _check_bsela_on_path(),
        _check_llm_api_key(),
        _check_bsela_home(),
        _check_db(),
        _check_agents_md_repo(),
        _check_claude_hook(settings_path),
    ]


def worst_status(results: list[CheckResult]) -> str:
    """Return the most severe status across results (fail > warn > pass)."""
    statuses = {r.status for r in results}
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return WARN
    return PASS


__all__ = [
    "FAIL",
    "PASS",
    "WARN",
    "CheckResult",
    "run_checks",
    "worst_status",
]
