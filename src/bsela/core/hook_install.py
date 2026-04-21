"""Install the Claude Code ``Stop`` hook into ``~/.claude/settings.json``.

Pure ``plan_install`` computes the merged settings given an existing dict;
``apply_install`` reads/writes disk with a timestamped ``.bak`` backup and
an atomic rename. Idempotent: re-running never creates duplicate hook
entries.

The settings.json hook schema Claude Code expects is::

    {
      "hooks": {
        "Stop": [
          {
            "matcher": "",
            "hooks": [
              {"type": "command", "command": "bsela hook claude-stop"}
            ]
          }
        ]
      }
    }

This module only touches ``settings.json`` hook wiring — never
``CLAUDE.md`` or any other rules artifact (those remain the exclusive
domain of the ``agents-md`` canonical repo).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_HOOK_COMMAND = "bsela hook claude-stop"
DEFAULT_EVENT = "Stop"


def default_claude_settings_path() -> Path:
    """Return the canonical user-scope Claude Code settings path."""
    return Path.home() / ".claude" / "settings.json"


@dataclass(frozen=True)
class InstallPlan:
    """Outcome of planning a hook install against existing settings."""

    changed: bool
    reason: str
    merged: dict[str, Any]
    event: str = DEFAULT_EVENT
    command: str = DEFAULT_HOOK_COMMAND


def _coerce_hooks_root(existing: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied settings dict with a dict ``hooks`` key."""
    merged: dict[str, Any] = json.loads(json.dumps(existing))  # deep copy
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        merged["hooks"] = {}
    return merged


def _find_matching_command(event_groups: list[Any], command: str) -> bool:
    """True if any matcher group under ``event_groups`` already has ``command``."""
    for group in event_groups:
        if not isinstance(group, dict):
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "command" and entry.get("command") == command:
                return True
    return False


def plan_install(
    existing: dict[str, Any],
    *,
    command: str = DEFAULT_HOOK_COMMAND,
    event: str = DEFAULT_EVENT,
) -> InstallPlan:
    """Compute the merged settings dict for installing ``command`` under ``event``.

    Preserves every unrelated key, event, and hook entry verbatim. If the
    exact command is already registered anywhere under ``event``, the plan
    returns ``changed=False`` with the original content unchanged.
    """
    merged = _coerce_hooks_root(existing)
    hooks_root: dict[str, Any] = merged["hooks"]

    event_groups = hooks_root.get(event)
    if not isinstance(event_groups, list):
        event_groups = []
        hooks_root[event] = event_groups

    if _find_matching_command(event_groups, command):
        return InstallPlan(
            changed=False,
            reason=f"{command!r} already registered under hooks.{event}",
            merged=merged,
            event=event,
            command=command,
        )

    event_groups.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": command}],
        }
    )
    return InstallPlan(
        changed=True,
        reason=f"appended {command!r} to hooks.{event}",
        merged=merged,
        event=event,
        command=command,
    )


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"settings at {path} must be a JSON object at the top level; got {type(data).__name__}"
        )
    return data


def _backup_path(path: Path, *, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return path.with_suffix(path.suffix + f".bak.{stamp}")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class InstallResult:
    """Outcome of ``apply_install``; ``backup`` is set only when a file existed."""

    path: Path
    plan: InstallPlan
    wrote: bool
    backup: Path | None


def apply_install(
    path: Path | None = None,
    *,
    command: str = DEFAULT_HOOK_COMMAND,
    event: str = DEFAULT_EVENT,
    backup: bool = True,
    now: datetime | None = None,
) -> InstallResult:
    """Merge the hook into ``path`` on disk. Returns whether a write occurred."""
    target = path or default_claude_settings_path()
    existing = _load_settings(target)
    plan = plan_install(existing, command=command, event=event)

    if not plan.changed:
        return InstallResult(path=target, plan=plan, wrote=False, backup=None)

    backup_path: Path | None = None
    if backup and target.is_file():
        backup_path = _backup_path(target, now=now)
        backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

    rendered = json.dumps(plan.merged, indent=2, sort_keys=True) + "\n"
    _atomic_write(target, rendered)
    return InstallResult(path=target, plan=plan, wrote=True, backup=backup_path)


__all__ = [
    "DEFAULT_EVENT",
    "DEFAULT_HOOK_COMMAND",
    "InstallPlan",
    "InstallResult",
    "apply_install",
    "default_claude_settings_path",
    "plan_install",
]
