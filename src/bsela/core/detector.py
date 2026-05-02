"""Deterministic error detector — regex + heuristic scan over captured sessions.

Passes (V1):
    * correction   — user message contains a correction marker.
    * loop         — same tool_use fingerprint repeated ``loop_threshold`` times.
    * stack_trace  — Python/JS traceback patterns in assistant or tool_result.

All passes run against the JSONL transcript referenced by ``SessionRecord``
and write ``ErrorRecord`` rows linked to that session. Pure I/O + regex, no
LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bsela.memory.models import ErrorRecord, SessionRecord
from bsela.memory.store import get_session, save_error
from bsela.utils.config import load_thresholds

_STACK_TRACE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r"^\s*at\s+\S+\s+\(.+:\d+:\d+\)\s*$", re.MULTILINE),
    re.compile(r"\b[A-Z]\w*Error:\s"),
    re.compile(r"\bpanic:\s"),
)
_MAX_SNIPPET_CHARS = 240
_MAX_RECORDS_PER_SESSION = 10


@dataclass(frozen=True)
class DetectionResult:
    session_id: str
    errors: tuple[ErrorRecord, ...]


def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            yield idx, json.loads(line)


def _nested_content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return content blocks from event.message.content[] (Claude Code JSONL format)."""
    msg = event.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content", [])
    return content if isinstance(content, list) else []


def _extract_block_text(block: dict[str, Any]) -> str:
    """Return text content from a single content block (text or tool_result)."""
    if block.get("type") == "text":
        return str(block.get("text") or "")
    if block.get("type") == "tool_result":
        inner = block.get("content", "")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list):
            return "\n".join(
                ib.get("text", "")
                for ib in inner
                if isinstance(ib, dict) and ib.get("type") == "text"
            )
    return ""


def _text_of(event: dict[str, Any]) -> str:
    """Extract all searchable text from an event in either flat or nested format."""
    parts: list[str] = []

    # Flat format: top-level content / result fields
    flat = event.get("content") or event.get("result")
    if isinstance(flat, str) and flat:
        parts.append(flat)

    # Claude Code nested format: event.message.content[] blocks
    for block in _nested_content_blocks(event):
        t = _extract_block_text(block)
        if t:
            parts.append(t)

    if parts:
        return "\n".join(parts)

    # Fallback: JSON-dump whatever is there
    if flat is not None and not isinstance(flat, str):
        try:
            return json.dumps(flat, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(flat)
    return ""


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_SNIPPET_CHARS else text[: _MAX_SNIPPET_CHARS - 1] + "…"


def _fingerprint(event: dict[str, Any]) -> str:
    name = event.get("name") or event.get("tool_name") or ""
    payload = event.get("input") or event.get("arguments") or {}
    try:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        blob = str(payload)
    return hashlib.sha1(f"{name}|{blob}".encode(), usedforsecurity=False).hexdigest()


def _event_type(event: dict[str, Any]) -> str | None:
    """Return normalized event type — ``type`` first, then ``role`` (Cursor format)."""
    return event.get("type") or event.get("role")


def _correction_markers(markers: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(rf"\b{re.escape(m)}\b", re.IGNORECASE) for m in markers)


def _user_text_only(event: dict[str, Any]) -> str:
    """Return only the plain user-typed text from a user event.

    Deliberately excludes tool_result blocks (file reads, shell output, etc.)
    so that correction markers don't fire on file content that happens to
    contain phrases like 'hard stop'.
    """
    # Flat format: top-level content string on a user event
    flat = event.get("content")
    if isinstance(flat, str) and flat:
        return flat

    # Claude Code nested format: collect only plain text blocks, skip tool_result
    parts: list[str] = []
    for block in _nested_content_blocks(event):
        if block.get("type") == "text":
            t = str(block.get("text") or "")
            if t:
                parts.append(t)
    return "\n".join(parts)


def _scan_correction(
    events: list[tuple[int, dict[str, Any]]],
    session_id: str,
    markers: tuple[re.Pattern[str], ...],
) -> list[ErrorRecord]:
    out: list[ErrorRecord] = []
    for line_no, event in events:
        if _event_type(event) != "user":
            continue
        # Only inspect the human-typed text — not tool_result file content
        text = _user_text_only(event)
        if not text:
            continue
        for pattern in markers:
            if pattern.search(text):
                out.append(
                    ErrorRecord(
                        session_id=session_id,
                        category="correction",
                        severity="high",
                        snippet=_truncate(text),
                        line_number=line_no,
                    )
                )
                break
    return out


def _iter_tool_uses(
    events: list[tuple[int, dict[str, Any]]],
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield (line_no, tool_use_block) for every tool call in the event stream.

    Handles both the flat legacy format (top-level type=tool_use) and the
    Claude Code nested format (assistant.message.content[].type=tool_use).
    """
    for ln, event in events:
        etype = _event_type(event)
        if etype in {"tool_use", "tool_call"}:
            yield ln, event
        elif etype in ("assistant", "message"):
            for block in _nested_content_blocks(event):
                if block.get("type") in {"tool_use", "tool_call"}:
                    yield ln, block


def _scan_loop(
    events: list[tuple[int, dict[str, Any]]],
    session_id: str,
    loop_threshold: int,
) -> list[ErrorRecord]:
    calls = list(_iter_tool_uses(events))
    out: list[ErrorRecord] = []
    run_fp: str | None = None
    run_start_line = 0
    run_count = 0
    for line_no, event in calls:
        fp = _fingerprint(event)
        if fp == run_fp:
            run_count += 1
        else:
            run_fp = fp
            run_count = 1
            run_start_line = line_no
        if run_count == loop_threshold:
            out.append(
                ErrorRecord(
                    session_id=session_id,
                    category="loop",
                    severity="medium",
                    snippet=_truncate(
                        f"tool_use {event.get('name') or '?'} repeated x{loop_threshold}"
                    ),
                    line_number=run_start_line,
                )
            )
    return out


def _scan_stack_trace(
    events: list[tuple[int, dict[str, Any]]],
    session_id: str,
) -> list[ErrorRecord]:
    out: list[ErrorRecord] = []
    for line_no, event in events:
        # Flat format: assistant / tool_result / message events
        # Nested format: user events whose message.content[] contains tool_result blocks
        if _event_type(event) not in {"assistant", "tool_result", "message", "user"}:
            continue
        text = _text_of(event)
        if not text:
            continue
        for pattern in _STACK_TRACE_PATTERNS:
            if pattern.search(text):
                out.append(
                    ErrorRecord(
                        session_id=session_id,
                        category="stack_trace",
                        severity="high",
                        snippet=_truncate(text),
                        line_number=line_no,
                    )
                )
                break
    return out


def detect_errors(
    session_id: str,
    *,
    persist: bool = True,
) -> DetectionResult:
    """Run all deterministic detectors against one stored session."""
    session = get_session(session_id)
    if session is None:
        raise LookupError(f"session not found: {session_id}")
    if session.status == "quarantined":
        return DetectionResult(session_id=session_id, errors=())
    return _detect_for(session, persist=persist)


def _detect_for(session: SessionRecord, *, persist: bool) -> DetectionResult:
    transcript = Path(session.transcript_path)
    if not transcript.is_file():
        return DetectionResult(session_id=session.id, errors=())

    cfg = load_thresholds().detector
    events = list(_iter_jsonl(transcript))
    markers = _correction_markers(cfg.correction_markers)

    candidates: list[ErrorRecord] = []
    candidates.extend(_scan_correction(events, session.id, markers))
    candidates.extend(_scan_loop(events, session.id, cfg.loop_threshold))
    candidates.extend(_scan_stack_trace(events, session.id))

    candidates = candidates[:_MAX_RECORDS_PER_SESSION]

    if persist:
        candidates = [save_error(err) for err in candidates]
    return DetectionResult(session_id=session.id, errors=tuple(candidates))


__all__ = ["DetectionResult", "detect_errors"]
