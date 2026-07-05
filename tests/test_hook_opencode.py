"""Tests for ``bsela hook opencode-stop``."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app
from bsela.memory.store import list_sessions


def _seed_opencode_db(db_path: Path, session_id: str = "ses_test") -> None:
    conn = sqlite3.connect(db_path)
    try:
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
        conn.execute(
            """
            INSERT INTO session VALUES (?, 'proj', 'slug', '/tmp', 'title', '1', 1000, 2000)
            """,
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO message VALUES ('msg1', ?, 1700000000000, 1700000001000, ?)
            """,
            (
                session_id,
                json.dumps({"role": "user", "agent": "build"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO part VALUES ('part1', 'msg1', ?, 1700000000000, 1700000001000, ?)
            """,
            (
                session_id,
                json.dumps({"type": "text", "text": "fix the failing test please"}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_opencode_stop_exports_and_ingests(tmp_bsela_home: Path, tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    _seed_opencode_db(db)
    payload = json.dumps({"sessionID": "ses_test"})
    result = CliRunner().invoke(
        app,
        ["hook", "opencode-stop", "--db", str(db)],
        input=payload,
    )
    assert result.exit_code == 0, result.stdout
    sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].source == "opencode"


def test_opencode_stop_noops_on_empty_stdin(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["hook", "opencode-stop"], input="")
    assert result.exit_code == 0
    assert list_sessions() == []


def test_opencode_stop_noops_when_session_missing(tmp_bsela_home: Path, tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    _seed_opencode_db(db)
    payload = json.dumps({"sessionID": "ses_missing"})
    result = CliRunner().invoke(
        app,
        ["hook", "opencode-stop", "--db", str(db)],
        input=payload,
    )
    assert result.exit_code == 0
    assert list_sessions() == []
