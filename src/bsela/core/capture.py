"""Capture — read a session transcript (JSONL), scrub secrets, persist metadata.

This module is intentionally pure I/O + regex. It never calls an LLM.
If the scrubber hits a secret pattern, the session is persisted with
``status='quarantined'`` and the raw transcript body is *not* logged back
anywhere — callers should treat the file on disk as sensitive and delete
or move it accordingly.

``ingest_file`` chains the deterministic detector after a successful
(non-quarantined) capture by default; detection is pure regex and free,
so the hook path naturally produces ``ErrorRecord`` rows without a
second command. Detect failures are swallowed — capture must succeed
even if a downstream pass goes wrong.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bsela.core.detector import detect_errors
from bsela.memory.models import SessionRecord
from bsela.memory.store import save_session
from bsela.utils.config import load_thresholds

_log = logging.getLogger(__name__)

# Stream transcript bytes for hashing so multi-hour JSONL sessions do not
# spike RSS (read_bytes() loads the entire file at once).
_HASH_CHUNK_BYTES = 1024 * 1024

_TURN_TYPES = frozenset({"user", "assistant", "message"})
_TOOL_TYPES = frozenset({"tool_use", "tool_call"})


@dataclass(frozen=True)
class Scrubber:
    """Compiled secret-pattern scanner."""

    patterns: tuple[re.Pattern[str], ...]

    @classmethod
    def from_patterns(cls, patterns: Iterable[str]) -> Scrubber:
        return cls(tuple(re.compile(p) for p in patterns))

    @classmethod
    def from_config(cls) -> Scrubber:
        return cls.from_patterns(load_thresholds().scrubber.patterns)

    def scan(self, text: str) -> list[str]:
        """Return the source patterns that matched ``text``."""
        return [p.pattern for p in self.patterns if p.search(text)]


@dataclass(frozen=True)
class CaptureResult:
    session_id: str
    status: str
    quarantine_reason: str | None
    turn_count: int
    tool_call_count: int
    transcript_path: Path
    errors_detected: int = 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            yield json.loads(line)


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _scan_event(event: dict[str, Any], scrubber: Scrubber) -> list[str]:
    parts = [_stringify(v) for k, v in event.items() if k not in ("ts", "type")]
    return scrubber.scan(" ".join(parts))


def ingest_file(
    path: str | Path,
    *,
    source: str = "claude_code",
    scrubber: Scrubber | None = None,
    auto_detect: bool = True,
) -> CaptureResult:
    """Ingest a JSONL transcript, scrub, persist, and run the detector.

    ``auto_detect`` chains the deterministic detector after a successful
    non-quarantined capture so the hook path produces ``ErrorRecord``
    rows without a second command. Detect errors are logged and swallowed
    — a failed detector pass must not roll back a successful capture.
    """
    transcript = Path(path).expanduser().resolve()
    if not transcript.is_file():
        raise FileNotFoundError(transcript)

    scan = scrubber or Scrubber.from_config()
    content_hash = _sha256_file(transcript)

    turn_count = 0
    tool_call_count = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    scrub_hits: set[str] = set()

    for event in _iter_jsonl(transcript):
        etype = event.get("type")
        if etype in _TURN_TYPES:
            turn_count += 1
        if etype in _TOOL_TYPES or event.get("tool_calls"):
            tool_call_count += 1
        elif etype == "assistant":
            # Claude Code nested format: tool_use blocks inside message.content[]
            msg = event.get("message") or {}
            nested = msg.get("content", []) if isinstance(msg, dict) else []
            if isinstance(nested, list):
                tool_call_count += sum(
                    1 for b in nested if isinstance(b, dict) and b.get("type") in _TOOL_TYPES
                )
        scrub_hits.update(_scan_event(event, scan))
        ts = _parse_ts(event.get("ts"))
        if ts is not None:
            if started_at is None or ts < started_at:
                started_at = ts
            if ended_at is None or ts > ended_at:
                ended_at = ts

    quarantined = bool(scrub_hits)
    reason = f"secret patterns matched: {sorted(scrub_hits)}" if quarantined else None

    record = SessionRecord(
        source=source,
        transcript_path=str(transcript),
        content_hash=content_hash,
        started_at=started_at or datetime.now(UTC),
        ended_at=ended_at,
        turn_count=turn_count,
        tool_call_count=tool_call_count,
        status="quarantined" if quarantined else "captured",
        quarantine_reason=reason,
    )
    saved = save_session(record)

    errors_detected = 0
    if auto_detect and saved.status == "captured":
        errors_detected = _safe_detect(saved.id)

    return CaptureResult(
        session_id=saved.id,
        status=saved.status,
        quarantine_reason=saved.quarantine_reason,
        turn_count=turn_count,
        tool_call_count=tool_call_count,
        transcript_path=transcript,
        errors_detected=errors_detected,
    )


def _safe_detect(session_id: str) -> int:
    """Run the detector for ``session_id``; log and swallow any failure.

    Capture must never fail on downstream errors, so this intentionally
    catches ``Exception`` — a broken detector pass must not roll back a
    successful capture.
    """
    try:
        result = detect_errors(session_id)
    except Exception:
        _log.exception("auto-detect failed for session %s", session_id)
        return 0
    return len(result.errors)


__all__ = ["CaptureResult", "Scrubber", "ingest_file"]
