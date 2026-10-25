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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bsela.adapters.codex import default_session_roots, discover_rollouts
from bsela.core.hook_install import (
    DEFAULT_EVENT,
    DEFAULT_HOOK_COMMAND,
    default_claude_settings_path,
)
from bsela.core.updater import DEFAULT_AGENTS_MD_REPO
from bsela.llm.client import codex_environment, keychain_credential, make_llm_client
from bsela.llm.runtime import ProviderError, model_run
from bsela.memory.store import bsela_home, db_path, find_session_by_transcript
from bsela.utils.config import load_models

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


def _check_llm_provider(
    provider: str = "codex", *, auth_check: bool = False, live: bool = False
) -> CheckResult:
    cfg = load_models()
    if provider not in {"codex", "deepseek"}:
        return CheckResult("model provider", FAIL, "unsupported provider")
    if provider == "codex" and not shutil.which("codex"):
        return CheckResult("model provider", FAIL, "codex executable not found")
    if not auth_check and not live:
        return CheckResult(
            "model provider",
            WARN,
            f"{provider}: offline only; authentication/model access unverified; "
            f"live_enabled={cfg.default.get('live_enabled', False)}",
        )
    try:
        if provider == "deepseek":
            keychain_credential(presence_only=True)
        else:
            status = subprocess.run(
                ["codex", "-c", 'forced_login_method="chatgpt"', "login", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                env=codex_environment(),
                check=False,
            )
            if status.returncode or "chatgpt" not in (status.stdout + status.stderr).lower():
                raise ProviderError("auth: Codex ChatGPT login unavailable")
        if live:
            with model_run():
                make_llm_client(provider).judge(
                    system="Return a JSON rubric verdict for a successful synthetic session.",
                    user='{"candidate_errors": []}',
                )
    except (ProviderError, OSError, subprocess.TimeoutExpired):
        return CheckResult(
            "model provider",
            FAIL,
            f"{provider}: auth/live check failed; use approved provider diagnostics",
        )
    return CheckResult(
        "model provider",
        PASS,
        f"{provider}: "
        f"{'live model verified' if live else 'credential present; model access unverified'}",
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
        candidate = DEFAULT_AGENTS_MD_REPO
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


def _check_codex_capture(roots: tuple[Path, ...] | None = None) -> CheckResult:
    """Report whether the newest Codex rollout actually reached the store.

    A wired hook and a correct schedule still produce empty reports if the
    rollout parser misses the transcript format, so this probe checks the
    stored turn count of the most recent rollout rather than the wiring alone.
    """
    search = roots if roots is not None else default_session_roots()
    if not any(Path(root).expanduser().is_dir() for root in search):
        return CheckResult("codex capture", PASS, "no ~/.codex rollout tree on this machine")
    rollouts = discover_rollouts(search, limit=1)
    if not rollouts:
        return CheckResult("codex capture", WARN, "no user-thread rollouts found under ~/.codex")
    newest = rollouts[0]
    # Never open the store here: a probe that creates an empty database would
    # change what `bsela status` reports about a not-yet-initialized install.
    stored = find_session_by_transcript(str(newest.resolve())) if db_path().exists() else None
    if stored is None:
        return CheckResult(
            "codex capture",
            WARN,
            f"{newest.name} not ingested — wire the notify hook or run `bsela scan`",
        )
    if stored.turn_count <= 0:
        return CheckResult(
            "codex capture",
            WARN,
            f"{newest.name} stored with 0 turns — run `bsela scan` to repair the row",
        )
    return CheckResult("codex capture", PASS, f"{newest.name} captured (turns={stored.turn_count})")


def run_checks(
    *,
    settings_path: Path | None = None,
    provider: str = "codex",
    auth_check: bool = False,
    live: bool = False,
) -> list[CheckResult]:
    """Run all probes and return the flat result list."""
    return [
        _check_python(),
        _check_bsela_on_path(),
        _check_llm_provider(provider, auth_check=auth_check, live=live),
        _check_bsela_home(),
        _check_db(),
        _check_agents_md_repo(),
        _check_claude_hook(settings_path),
        _check_codex_capture(),
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
