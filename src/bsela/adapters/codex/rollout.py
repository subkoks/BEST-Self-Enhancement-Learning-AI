"""Codex CLI rollout transcripts — discovery and canonicalization.

Codex writes one JSONL *rollout* per session. Active sessions live under
``~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl`` and are
moved to ``~/.codex/archived_sessions/`` when archived. Every line is an
envelope::

    {"timestamp": "...", "type": "response_item", "payload": {...}}

Capture and detection speak a Claude-Code-shaped *canonical* event (top-level
``type``/``role`` plus ``message.content[]`` blocks). :func:`normalize_event`
translates one Codex envelope into that shape, and returns ``None`` for
envelopes carrying no user-visible content (reasoning items, token counts,
thread metadata, ``developer`` instructions).

Codex injects harness context — the ``AGENTS.md`` instruction block and an
``<environment_context>`` blob — as ordinary ``user`` messages. Those are
stripped during normalization so the deterministic detector never reads
injected rules text as a user correction.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOURCE = "codex"

_ROLLOUT_GLOB = "rollout-*.jsonl"
_SESSION_ID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

# Codex ``response_item.payload.type`` values that map onto a canonical event.
_MESSAGE_ROLES = {"user": "user", "assistant": "assistant"}
_TEXT_BLOCK_TYPES = frozenset({"input_text", "output_text", "text"})
_TOOL_CALL_TYPES = frozenset({"function_call", "custom_tool_call", "local_shell_call"})
_TOOL_OUTPUT_TYPES = frozenset(
    {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}
)

# Harness-injected context Codex prepends to user turns. Stripped before the
# correction scanner sees the text: an AGENTS.md body quotes Hard-Stop markers
# ("stop", "never", "don't") that would otherwise mint false corrections.
_INJECTED_BLOCKS = (
    re.compile(r"<environment_context\b[^>]*>.*?</environment_context\s*>", re.DOTALL | re.I),
    re.compile(r"<INSTRUCTIONS\b[^>]*>.*?</INSTRUCTIONS\s*>", re.DOTALL | re.I),
    re.compile(r"<user_instructions\b[^>]*>.*?</user_instructions\s*>", re.DOTALL | re.I),
    re.compile(r"<skill\b[^>]*>.*?</skill\s*>", re.DOTALL | re.I),
    re.compile(r"<recommended_plugins\b[^>]*>.*?</recommended_plugins\s*>", re.DOTALL | re.I),
)
# Truncated envelopes (killed session mid-write) run to the end of the message.
_UNCLOSED_INJECTED_BLOCKS = (
    re.compile(r"<environment_context\b[^>]*>[\s\S]*\Z", re.IGNORECASE),
    re.compile(r"<INSTRUCTIONS\b[^>]*>[\s\S]*\Z", re.IGNORECASE),
)
_AGENTS_INSTRUCTIONS_HEADER = re.compile(
    r"^#\s+AGENTS\.md instructions\b.*$", re.MULTILINE | re.IGNORECASE
)
# VS Code's Codex extension prepends editor state and follows it with the user's
# actual request after a ``## My request:`` marker — keep only the request.
_IDE_CONTEXT_HEADER = re.compile(
    r"^#\s+Context from my IDE setup:.*$", re.MULTILINE | re.IGNORECASE
)
_IDE_REQUEST_MARKER = re.compile(r"^##\s+My request:\s*$", re.MULTILINE | re.IGNORECASE)

# ``thread_source`` values Codex uses for internal work it runs off a user
# thread: guardian approval reviews and spawned subagents. Those rollouts are
# agent-internal transcript, not session material for the learning loop.
_INTERNAL_THREAD_SOURCES = frozenset({"subagent", "guardian_review"})


def default_session_roots() -> tuple[Path, ...]:
    """Codex rollout roots: live sessions first, then the archive."""
    home = Path.home() / ".codex"
    return (home / "sessions", home / "archived_sessions")


def is_rollout_path(path: Path) -> bool:
    """True when ``path`` looks like a Codex rollout transcript."""
    return path.suffix == ".jsonl" and path.name.startswith("rollout-")


def session_id_from_path(path: Path) -> str | None:
    """Return the session (thread) id embedded in a rollout filename."""
    match = _SESSION_ID_RE.search(path.stem)
    return match.group(1) if match else None


def read_session_meta(path: Path) -> dict[str, Any] | None:
    """Return the rollout's ``session_meta`` payload, or ``None`` when absent."""
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return None
    try:
        event = json.loads(first)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, Mapping) or event.get("type") != "session_meta":
        return None
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    return dict(payload)


def is_user_rollout(path: Path) -> bool:
    """False for Codex-internal rollouts (guardian reviews, spawned subagents).

    Rollouts written before Codex recorded ``thread_source`` have no marker and
    are treated as user threads.
    """
    meta = read_session_meta(path)
    if meta is None:
        return True
    return meta.get("thread_source") not in _INTERNAL_THREAD_SOURCES


def discover_rollouts(
    roots: Iterable[Path] | None = None,
    *,
    since: datetime | None = None,
    limit: int | None = None,
    user_threads_only: bool = True,
) -> list[Path]:
    """Rollout transcripts under ``roots``, newest first.

    ``since`` filters on the file modification time; ``limit`` truncates the
    result after sorting. ``user_threads_only`` drops Codex-internal rollouts
    (guardian reviews and subagent threads). Missing roots are skipped so a
    machine without an ``~/.codex`` tree yields an empty list instead of an
    error.
    """
    found: list[tuple[float, str, Path]] = []
    for root in default_session_roots() if roots is None else roots:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for path in base.glob(f"**/{_ROLLOUT_GLOB}"):
            mtime = path.stat().st_mtime
            if since is not None and datetime.fromtimestamp(mtime, tz=UTC) < since:
                continue
            if user_threads_only and not is_user_rollout(path):
                continue
            found.append((mtime, str(path), path))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    paths = [path for _, _, path in found]
    return paths[:limit] if limit is not None else paths


def find_rollout(session_id: str, *, roots: Iterable[Path] | None = None) -> Path | None:
    """Newest rollout file for ``session_id``, or ``None`` when it is unknown."""
    if not _SESSION_ID_RE.fullmatch(session_id):
        return None
    best: tuple[float, str, Path] | None = None
    for root in default_session_roots() if roots is None else roots:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for path in base.glob(f"**/rollout-*-{session_id}.jsonl"):
            if not is_user_rollout(path):
                continue
            candidate = (path.stat().st_mtime, str(path), path)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best is not None else None


def strip_injected_context(text: str) -> str:
    """Remove Codex harness envelopes (rules, environment) from user text."""
    cleaned = text
    for pattern in _INJECTED_BLOCKS:
        cleaned = pattern.sub("", cleaned)
    for pattern in _UNCLOSED_INJECTED_BLOCKS:
        cleaned = pattern.sub("", cleaned)
    cleaned = _AGENTS_INSTRUCTIONS_HEADER.sub("", cleaned)
    cleaned = _strip_ide_context(cleaned)
    return cleaned.strip()


def _strip_ide_context(text: str) -> str:
    """Keep the ``## My request:`` tail of VS Code's IDE-context preamble."""
    if _IDE_CONTEXT_HEADER.search(text) is None:
        return text
    marker = _IDE_REQUEST_MARKER.search(text)
    return text[marker.end() :] if marker is not None else ""


def _json_text(value: Any) -> str:
    """Render a non-string tool output as text; never raise on odd payloads."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _call_input(payload: Mapping[str, Any]) -> Any:
    """Tool-call arguments: parsed JSON when possible, else the raw payload."""
    for key in ("arguments", "input"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
        if isinstance(raw, Mapping):
            return dict(raw)
    return {}


def _tool_output_text(payload: Mapping[str, Any]) -> str:
    output = payload.get("output")
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        content = output.get("content")
        if isinstance(content, str):
            return content
    return _json_text(output)


def _normalize_message(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    role = payload.get("role")
    canonical_role = _MESSAGE_ROLES.get(role) if isinstance(role, str) else None
    if canonical_role is None:
        return None

    blocks: list[dict[str, Any]] = []
    content = payload.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, Mapping) or block.get("type") not in _TEXT_BLOCK_TYPES:
                continue
            text = block.get("text")
            if not isinstance(text, str):
                continue
            if canonical_role == "user":
                text = strip_injected_context(text)
            if text:
                blocks.append({"type": "text", "text": text})
    if not blocks:
        return None
    return {"type": canonical_role, "message": {"role": canonical_role, "content": blocks}}


def normalize_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Translate one Codex rollout envelope into a canonical event.

    Returns ``None`` for envelopes the detector has nothing to read: reasoning
    items, token counts, thread metadata, and instructions addressed to the
    model rather than turns exchanged with the user.
    """
    if event.get("type") != "response_item":
        return None
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None

    item_type = payload.get("type")
    if item_type == "message":
        canonical = _normalize_message(payload)
    elif item_type in _TOOL_CALL_TYPES:
        canonical = {
            "type": "tool_use",
            "name": str(payload.get("name") or item_type),
            "input": _call_input(payload),
        }
    elif item_type in _TOOL_OUTPUT_TYPES:
        text = _tool_output_text(payload)
        return {"type": "tool_result", "content": text} if text else None
    else:
        return None

    timestamp = event.get("timestamp")
    if canonical is not None and isinstance(timestamp, str):
        canonical["ts"] = timestamp
    return canonical


__all__ = [
    "SOURCE",
    "default_session_roots",
    "discover_rollouts",
    "find_rollout",
    "is_rollout_path",
    "is_user_rollout",
    "normalize_event",
    "read_session_meta",
    "session_id_from_path",
    "strip_injected_context",
]
