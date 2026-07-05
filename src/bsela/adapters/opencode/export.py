"""Export OpenCode SQLite sessions to JSONL for BSELA capture."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bsela.memory.store import bsela_home

DEFAULT_OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"


def resolve_opencode_db(path: Path | None = None) -> Path:
    candidate = (path or DEFAULT_OPENCODE_DB).expanduser()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def default_export_path(session_id: str) -> Path:
    safe_id = session_id.replace("/", "_")
    return bsela_home() / "opencode-transcripts" / f"{safe_id}.jsonl"


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _part_text(data_raw: str) -> str | None:
    try:
        data = json.loads(data_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "text":
        return None
    text = data.get("text")
    return text if isinstance(text, str) and text.strip() else None


def _message_role(data_raw: str) -> str:
    try:
        data = json.loads(data_raw)
    except json.JSONDecodeError:
        return "message"
    role = data.get("role")
    if isinstance(role, str) and role in ("user", "assistant"):
        return role
    return "message"


def _message_error_suffix(data_raw: str) -> str:
    try:
        data = json.loads(data_raw)
    except json.JSONDecodeError:
        return ""
    err = data.get("error")
    if not isinstance(err, dict):
        return ""
    nested = err.get("data") if isinstance(err.get("data"), dict) else err
    if isinstance(nested, dict):
        msg = nested.get("message")
        if isinstance(msg, str) and msg.strip():
            return f"\n[error] {msg.strip()}"
    return ""


def export_session_to_jsonl(
    session_id: str,
    dest: Path,
    *,
    db_path: Path | None = None,
) -> Path:
    """Write one JSONL transcript file from an OpenCode session id."""
    db = resolve_opencode_db(db_path)
    dest = dest.expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        msg_rows = conn.execute(
            """
            SELECT m.id, m.time_created, m.data
            FROM message m
            WHERE m.session_id = ?
            ORDER BY m.time_created, m.id
            """,
            (session_id,),
        ).fetchall()
        if not msg_rows:
            raise LookupError(f"no messages for OpenCode session {session_id!r}")

        part_rows = conn.execute(
            """
            SELECT message_id, data
            FROM part
            WHERE session_id = ?
            ORDER BY time_created, id
            """,
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    parts_by_message: dict[str, list[str]] = {}
    for message_id, part_data in part_rows:
        text = _part_text(part_data)
        if text:
            parts_by_message.setdefault(message_id, []).append(text)

    lines: list[str] = []
    for message_id, time_created, msg_data in msg_rows:
        chunks = parts_by_message.get(message_id, [])
        content = "\n".join(chunks).strip()
        content = (content + _message_error_suffix(msg_data)).strip()
        if not content:
            continue
        event = {
            "ts": _ms_to_iso(int(time_created)),
            "type": _message_role(msg_data),
            "content": content,
        }
        lines.append(json.dumps(event, ensure_ascii=False))

    if not lines:
        raise ValueError(f"session {session_id!r} has no exportable text")

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest
