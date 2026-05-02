"""P1 tests: ``bsela ingest`` and ``bsela status`` wired end-to-end."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bsela.cli import app


def test_ingest_captures_clean_session(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    result = CliRunner().invoke(app, ["ingest", str(sample_clean_session)])
    assert result.exit_code == 0, result.stdout
    assert "captured" in result.stdout


def test_ingest_quarantines_leaked_session(
    tmp_bsela_home: Path, sample_leaked_session: Path
) -> None:
    result = CliRunner().invoke(app, ["ingest", str(sample_leaked_session)])
    assert result.exit_code == 0, result.stdout
    assert "quarantined" in result.stdout


def test_status_before_and_after_ingest(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    runner = CliRunner()
    pre = runner.invoke(app, ["status"])
    assert pre.exit_code == 0
    assert "no store" in pre.stdout

    ingested = runner.invoke(app, ["ingest", str(sample_clean_session)])
    assert ingested.exit_code == 0

    post = runner.invoke(app, ["status"])
    assert post.exit_code == 0
    assert "sessions: 1" in post.stdout
    assert "quarantined: 0" in post.stdout


def test_status_json_after_ingest(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["ingest", str(sample_clean_session)])

    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sessions"] == 1
    assert payload["sessions_quarantined"] == 0
    assert isinstance(payload["errors"], int)
    assert isinstance(payload["lessons"], int)
    assert isinstance(payload["lessons_pending"], int)
    assert isinstance(payload["lessons_proposed"], int)
    assert "bsela_home" in payload
    assert sorted(payload.keys()) == [
        "bsela_home",
        "errors",
        "lessons",
        "lessons_pending",
        "lessons_proposed",
        "replay_records",
        "sessions",
        "sessions_quarantined",
    ]
