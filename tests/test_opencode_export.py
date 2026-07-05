"""Tests for OpenCode SQLite → JSONL export."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.adapters.opencode.export import (
    default_export_path,
    export_session_to_jsonl,
    resolve_opencode_db,
)
from bsela.cli import app


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE session (
            id text PRIMARY KEY,
            project_id text NOT NULL,
            slug text NOT NULL,
            directory text NOT NULL,
            title text NOT NULL,
            version text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL
        );
        CREATE TABLE message (
            id text PRIMARY KEY,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE part (
            id text PRIMARY KEY,
            message_id text NOT NULL,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            data text NOT NULL
        );
        """
    )


def _seed_rich_session(db_path: Path, session_id: str = "ses_rich") -> None:
    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        conn.execute(
            "INSERT INTO session VALUES (?, 'p', 's', '/tmp', 't', '1', 1, 2)",
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO message VALUES
              ('msg_user', ?, 1700000000000, 1700000001000, ?),
              ('msg_asst', ?, 1700000002000, 1700000003000, ?),
              ('msg_empty', ?, 1700000004000, 1700000005000, ?)
            """,
            (
                session_id,
                json.dumps({"role": "user"}),
                session_id,
                json.dumps(
                    {
                        "role": "assistant",
                        "error": {"data": {"message": "invalid x-api-key"}},
                    }
                ),
                session_id,
                "not-json",
            ),
        )
        conn.execute(
            """
            INSERT INTO part VALUES
              ('p1', 'msg_user', ?, 1, 2, ?),
              ('p2', 'msg_asst', ?, 3, 4, ?),
              ('p3', 'msg_empty', ?, 5, 6, ?)
            """,
            (
                session_id,
                json.dumps({"type": "text", "text": "hello user"}),
                session_id,
                json.dumps({"type": "text", "text": "assistant reply"}),
                session_id,
                json.dumps({"type": "tool", "text": "skip me"}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_resolve_opencode_db_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_opencode_db(tmp_path / "missing.db")


def test_default_export_path_sanitizes_slashes(tmp_bsela_home: Path) -> None:
    path = default_export_path("ses/a/b")
    assert path.name == "ses_a_b.jsonl"
    assert path.parent.name == "opencode-transcripts"


def test_export_session_to_jsonl_includes_errors(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    out = tmp_path / "out.jsonl"
    _seed_rich_session(db)
    export_session_to_jsonl("ses_rich", out, db_path=db)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    user = json.loads(lines[0])
    assistant = json.loads(lines[1])
    assert user["type"] == "user"
    assert user["content"] == "hello user"
    assert assistant["type"] == "assistant"
    assert "assistant reply" in assistant["content"]
    assert "[error] invalid x-api-key" in assistant["content"]


def test_export_session_no_messages_raises(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(db)
    try:
        _create_schema(conn)
        conn.execute("INSERT INTO session VALUES ('ses_empty', 'p', 's', '/tmp', 't', '1', 1, 2)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(LookupError, match="no messages"):
        export_session_to_jsonl("ses_empty", tmp_path / "out.jsonl", db_path=db)


def test_export_session_no_exportable_text_raises(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(db)
    try:
        _create_schema(conn)
        conn.execute("INSERT INTO session VALUES ('ses_blank', 'p', 's', '/tmp', 't', '1', 1, 2)")
        conn.execute(
            """
            INSERT INTO message VALUES ('m1', 'ses_blank', 1, 2, ?)
            """,
            (json.dumps({"role": "user"}),),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ValueError, match="no exportable text"):
        export_session_to_jsonl("ses_blank", tmp_path / "out.jsonl", db_path=db)


def test_export_skips_invalid_parts_and_unknown_roles(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    out = tmp_path / "out.jsonl"
    conn = sqlite3.connect(db)
    try:
        _create_schema(conn)
        conn.execute("INSERT INTO session VALUES ('ses_edge', 'p', 's', '/tmp', 't', '1', 1, 2)")
        conn.execute(
            """
            INSERT INTO message VALUES ('msg1', 'ses_edge', 1700000000000, 1, ?)
            """,
            (json.dumps({"role": "system"}),),
        )
        conn.execute(
            """
            INSERT INTO part VALUES
              ('p_bad', 'msg1', 'ses_edge', 1, 2, 'not-json'),
              ('p_ok', 'msg1', 'ses_edge', 3, 4, ?)
            """,
            (json.dumps({"type": "text", "text": "visible"}),),
        )
        conn.commit()
    finally:
        conn.close()
    export_session_to_jsonl("ses_edge", out, db_path=db)
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["type"] == "message"
    assert row["content"] == "visible"


def test_export_error_without_message_is_ignored(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    out = tmp_path / "out.jsonl"
    conn = sqlite3.connect(db)
    try:
        _create_schema(conn)
        conn.execute("INSERT INTO session VALUES ('ses_err', 'p', 's', '/tmp', 't', '1', 1, 2)")
        conn.execute(
            """
            INSERT INTO message VALUES ('msg1', 'ses_err', 1, 2, ?)
            """,
            (json.dumps({"role": "assistant", "error": {"data": {"code": 401}}}),),
        )
        conn.execute(
            """
            INSERT INTO part VALUES ('p1', 'msg1', 'ses_err', 1, 2, ?)
            """,
            (json.dumps({"type": "text", "text": "only text"}),),
        )
        conn.commit()
    finally:
        conn.close()
    export_session_to_jsonl("ses_err", out, db_path=db)
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["content"] == "only text"


def test_opencode_stop_noops_on_malformed_json(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["hook", "opencode-stop"], input="not-json")
    assert result.exit_code == 0


def test_opencode_stop_noops_without_session_id(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["hook", "opencode-stop"], input='{"cwd":"/tmp"}')
    assert result.exit_code == 0


def test_opencode_stop_noops_when_db_missing(tmp_bsela_home: Path, tmp_path: Path) -> None:
    payload = json.dumps({"session_id": "ses_test"})
    result = CliRunner().invoke(
        app,
        ["hook", "opencode-stop", "--db", str(tmp_path / "ghost.db")],
        input=payload,
    )
    assert result.exit_code == 0
