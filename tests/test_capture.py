"""P1 tests: capture pipeline — scrubber, metadata, persistence, auto-detect."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bsela.core import capture as capture_module
from bsela.core.capture import Scrubber, _parse_ts, _stringify, ingest_file
from bsela.memory.store import get_session, list_errors

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


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


def test_ingest_auto_detects_on_clean_session(tmp_bsela_home: Path) -> None:
    result = ingest_file(FIXTURES / "user-correction.jsonl")
    assert result.status == "captured"
    assert result.errors_detected >= 1
    stored = list_errors(session_id=result.session_id)
    assert len(stored) == result.errors_detected
    assert any(err.category == "correction" for err in stored)


def test_ingest_skips_detect_on_quarantined(
    tmp_bsela_home: Path, sample_leaked_session: Path
) -> None:
    result = ingest_file(sample_leaked_session)
    assert result.status == "quarantined"
    assert result.errors_detected == 0
    assert list_errors(session_id=result.session_id) == []


def test_ingest_auto_detect_can_be_disabled(tmp_bsela_home: Path) -> None:
    result = ingest_file(FIXTURES / "user-correction.jsonl", auto_detect=False)
    assert result.status == "captured"
    assert result.errors_detected == 0
    assert list_errors(session_id=result.session_id) == []


def test_ingest_swallows_detect_failures(
    tmp_bsela_home: Path,
    sample_clean_session: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(session_id: str) -> object:
        raise RuntimeError("synthetic detector failure")

    monkeypatch.setattr("bsela.core.capture.detect_errors", boom)
    result = ingest_file(sample_clean_session)
    assert result.status == "captured"
    assert result.errors_detected == 0
    assert capture_module.ingest_file is ingest_file


def test_ingest_with_empty_jsonl_lines(tmp_bsela_home: Path, tmp_path: Path) -> None:
    """Cover line 74: _iter_jsonl skips blank lines."""
    jsonl = tmp_path / "sparse.jsonl"
    jsonl.write_text(
        '{"type":"human","content":"hello"}\n\n\n{"type":"assistant","content":"hi"}\n',
        encoding="utf-8",
    )
    result = ingest_file(jsonl)
    assert result.status in ("captured", "quarantined")


# ---- _parse_ts unit tests ----


def test_parse_ts_returns_none_on_non_string() -> None:
    assert _parse_ts(None) is None
    assert _parse_ts(42) is None
    assert _parse_ts("") is None


def test_parse_ts_returns_none_on_invalid_date() -> None:
    assert _parse_ts("not-a-date") is None


def test_parse_ts_parses_z_suffix() -> None:
    result = _parse_ts("2026-01-15T10:00:00Z")
    assert result is not None
    assert result.year == 2026


# ---- _stringify unit tests ----


def test_stringify_returns_json_for_dict() -> None:
    assert _stringify({"key": "value"}) == '{"key": "value"}'


def test_stringify_falls_back_to_str_on_non_serializable() -> None:
    class Unserializable:
        def __repr__(self) -> str:
            return "unserializable"

    result = _stringify(Unserializable())
    assert "unserializable" in result
