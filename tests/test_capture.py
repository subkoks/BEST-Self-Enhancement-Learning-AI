"""P1 tests: capture pipeline — scrubber, metadata, persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bsela.core.capture import Scrubber, ingest_file
from bsela.memory.store import get_session


def test_scrubber_matches_aws_key() -> None:
    scrub = Scrubber.from_patterns([r"AKIA[0-9A-Z]{16}"])
    assert scrub.scan("nothing here") == []
    assert scrub.scan("AKIAABCDEFGHIJKLMNOP present") == [r"AKIA[0-9A-Z]{16}"]


def test_ingest_clean_session(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    result = ingest_file(sample_clean_session, source="claude_code")
    assert result.status == "captured"
    assert result.quarantine_reason is None
    assert result.turn_count >= 3
    assert result.tool_call_count >= 1

    row = get_session(result.session_id)
    assert row is not None
    assert row.status == "captured"
    assert row.content_hash
    assert row.source == "claude_code"
    # SQLite stores naive datetimes; compare tz-naively.
    assert row.started_at.replace(tzinfo=None) <= datetime.now(UTC).replace(tzinfo=None)


def test_ingest_quarantines_on_secret(tmp_bsela_home: Path, sample_leaked_session: Path) -> None:
    result = ingest_file(sample_leaked_session)
    assert result.status == "quarantined"
    assert result.quarantine_reason is not None
    assert "AKIA" in result.quarantine_reason

    row = get_session(result.session_id)
    assert row is not None
    assert row.status == "quarantined"


def test_ingest_missing_file(tmp_bsela_home: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest_file(tmp_path / "does-not-exist.jsonl")
