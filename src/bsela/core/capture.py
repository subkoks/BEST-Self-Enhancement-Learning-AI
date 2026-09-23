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

from bsela.adapters.codex import SOURCE as CODEX_SOURCE
from bsela.adapters.codex import normalize_event
from bsela.core.detector import detect_errors
from bsela.memory.models import SessionRecord
from bsela.memory.store import (
    delete_errors_for_session,
    find_session_by_transcript,
    save_session,
    session_has_lessons,
    upsert_session,
)
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
    allowlist: frozenset[str] = frozenset()

    @classmethod
    def from_patterns(
        cls,
        patterns: Iterable[str],
        *,
        allowlist: Iterable[str] = (),
    ) -> Scrubber:
        return cls(tuple(re.compile(p) for p in patterns), frozenset(allowlist))

    @classmethod
    def from_config(cls) -> Scrubber:
        cfg = load_thresholds().scrubber
        return cls.from_patterns(cfg.patterns, allowlist=cfg.allowlist)

    def scan(self, text: str) -> list[str]:
        """Return the source patterns that matched ``text``.

        A pattern is included only if at least one of its matches is NOT in
        the allowlist (i.e. a literal known-safe placeholder). Patterns whose
        every match is allowlisted are suppressed.
        """
        hits: list[str] = []
        for p in self.patterns:
            matches = [m.group(0) for m in p.finditer(text)]
            if not matches:
                continue
            if all(m in self.allowlist for m in matches):
                continue
            hits.append(p.pattern)
        return hits


@dataclass(frozen=True)
class CaptureResult:
    session_id: str
    status: str
    quarantine_reason: str | None
    turn_count: int
    tool_call_count: int
    transcript_path: Path
    errors_detected: int = 0
    #: True when the stored row already matched this transcript's content hash.
    unchanged: bool = False
    #: True when an existing row was refreshed in place instead of inserted.
    updated: bool = False
    #: Set when a ``replace`` ingest deliberately left an existing row alone.
    skipped_reason: str | None = None


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
        for idx, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A single corrupt line must not lose the whole session.
                _log.warning("skipping malformed JSONL line %d in %s", idx, path)


def _iter_canonical(
    path: Path, source: str
) -> Iterator[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Yield ``(raw_event, canonical_event)`` pairs from a transcript.

    Claude Code transcripts are already canonical, so both entries are the same
    object. Codex rollouts are translated by the Codex adapter; envelopes with
    nothing to count (reasoning items, token counts, thread metadata) yield
    ``None`` as their canonical form. The raw event is always returned so the
    scrubber still inspects text that carries no turn.
    """
    for raw in _iter_jsonl(path):
        if source == CODEX_SOURCE:
            yield raw, normalize_event(raw)
        else:
            yield raw, raw


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


def _make_result(
    record: SessionRecord,
    transcript: Path,
    *,
    unchanged: bool = False,
    updated: bool = False,
    skipped_reason: str | None = None,
) -> CaptureResult:
    return CaptureResult(
        session_id=record.id,
        status=record.status,
        quarantine_reason=record.quarantine_reason,
        turn_count=record.turn_count,
        tool_call_count=record.tool_call_count,
        transcript_path=transcript,
        errors_detected=0,
        unchanged=unchanged,
        updated=updated,
        skipped_reason=skipped_reason,
    )


def _dedup_check(transcript: Path) -> tuple[CaptureResult | None, str | None]:
    """Return (early_result, precomputed_hash).

    early_result is non-None when this transcript was already ingested and the
    caller should return immediately. precomputed_hash carries the SHA-256 when
    it was computed here (captured + grown transcript), so the caller avoids a
    second disk read; it is None when the hash is not yet known.
    """
    existing = find_session_by_transcript(str(transcript))
    if existing is None:
        return None, None
    if existing.status == "quarantined":
        _log.debug("skipping re-ingest of quarantined transcript %s", transcript)
        return _make_result(existing, transcript, unchanged=True), None
    content_hash = _sha256_file(transcript)
    if existing.content_hash == content_hash:
        _log.debug("skipping re-ingest of unchanged captured transcript %s", transcript)
        return _make_result(existing, transcript, unchanged=True), None
    return None, content_hash


def _event_ts(event: dict[str, Any]) -> datetime | None:
    """Timestamp of an event: Codex/canonical ``ts`` first, then ``timestamp``."""
    return _parse_ts(event.get("ts") or event.get("timestamp"))


def _replacement_target(transcript: Path, *, enabled: bool) -> SessionRecord | None:
    """Existing row a ``replace`` ingest should update in place, if any.

    Quarantined rows are never rewritten: their transcript body was withheld
    from the store on purpose and re-ingest stays a no-op.
    """
    if not enabled:
        return None
    existing = find_session_by_transcript(str(transcript))
    if existing is None or existing.status == "quarantined":
        return None
    return existing


@dataclass(frozen=True)
class _ScanStats:
    """Turn/tool counters and secret hits gathered from one transcript pass."""

    turn_count: int
    tool_call_count: int
    started_at: datetime | None
    ended_at: datetime | None
    scrub_hits: frozenset[str]


def _scan_transcript(transcript: Path, source: str, scrubber: Scrubber) -> _ScanStats:
    """Count turns and tool calls and collect secret-pattern hits."""
    turn_count = 0
    tool_call_count = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    scrub_hits: set[str] = set()

    for raw, canonical in _iter_canonical(transcript, source):
        scrub_hits.update(_scan_event(raw, scrubber))
        if canonical is None:
            continue
        # Accept both `type` (native Claude Code) and `role` (Cursor-hosted Claude Code).
        etype = canonical.get("type") or canonical.get("role")
        if etype in _TURN_TYPES:
            turn_count += 1
        if etype in _TOOL_TYPES or canonical.get("tool_calls"):
            tool_call_count += 1
        elif etype in ("assistant", "message"):
            # Nested format: tool_use blocks inside message.content[]
            msg = canonical.get("message") or {}
            nested = msg.get("content", []) if isinstance(msg, dict) else []
            if isinstance(nested, list):
                tool_call_count += sum(
                    1 for b in nested if isinstance(b, dict) and b.get("type") in _TOOL_TYPES
                )
        ts = _event_ts(canonical)
        if ts is not None:
            if started_at is None or ts < started_at:
                started_at = ts
            if ended_at is None or ts > ended_at:
                ended_at = ts

    return _ScanStats(
        turn_count=turn_count,
        tool_call_count=tool_call_count,
        started_at=started_at,
        ended_at=ended_at,
        scrub_hits=frozenset(scrub_hits),
    )


def ingest_file(
    path: str | Path,
    *,
    source: str = "claude_code",
    scrubber: Scrubber | None = None,
    auto_detect: bool = True,
    replace: bool = False,
) -> CaptureResult:
    """Ingest a JSONL transcript, scrub, persist, and run the detector.

    ``auto_detect`` chains the deterministic detector after a successful
    non-quarantined capture so the hook path produces ``ErrorRecord``
    rows without a second command. Detect errors are logged and swallowed
    — a failed detector pass must not roll back a successful capture.

    ``replace`` keeps one row per transcript: when the file was ingested
    before and has since grown, the existing row is updated in place and its
    stale error rows are re-detected instead of a new snapshot being inserted.
    Rows whose errors already produced a Lesson are left untouched, so
    distillation history never loses the evidence it references.
    """
    transcript = Path(path).expanduser().resolve()
    if not transcript.is_file():
        raise FileNotFoundError(transcript)

    dedup, content_hash = _dedup_check(transcript)
    if dedup is not None:
        return dedup
    if content_hash is None:
        content_hash = _sha256_file(transcript)

    target = _replacement_target(transcript, enabled=replace)
    if target is not None and session_has_lessons(target.id):
        _log.debug("leaving distilled session %s in place for %s", target.id, transcript)
        return _make_result(target, transcript, skipped_reason="distilled")

    stats = _scan_transcript(transcript, source, scrubber or Scrubber.from_config())
    quarantined = bool(stats.scrub_hits)
    reason = f"secret patterns matched: {sorted(stats.scrub_hits)}" if quarantined else None

    record = SessionRecord(
        source=source,
        transcript_path=str(transcript),
        content_hash=content_hash,
        started_at=stats.started_at or datetime.now(UTC),
        ended_at=stats.ended_at,
        turn_count=stats.turn_count,
        tool_call_count=stats.tool_call_count,
        status="quarantined" if quarantined else "captured",
        quarantine_reason=reason,
    )
    if target is not None:
        record.id = target.id
        delete_errors_for_session(target.id)
        saved = upsert_session(record)
    else:
        saved = save_session(record)

    errors_detected = 0
    if auto_detect and saved.status == "captured":
        errors_detected = _safe_detect(saved.id)

    return CaptureResult(
        session_id=saved.id,
        status=saved.status,
        quarantine_reason=saved.quarantine_reason,
        turn_count=stats.turn_count,
        tool_call_count=stats.tool_call_count,
        transcript_path=transcript,
        errors_detected=errors_detected,
        updated=target is not None,
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
