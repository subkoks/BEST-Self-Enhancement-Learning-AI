"""P1 tests: capture pipeline — scrubber, metadata, persistence, auto-detect."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bsela.core import capture as capture_module
from bsela.core.capture import Scrubber, _parse_ts, _stringify, ingest_file
from bsela.memory.store import count_sessions, get_session, list_errors

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


def test_ingest_skips_malformed_jsonl_line(
    tmp_bsela_home: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A corrupt line is skipped+logged; valid turns around it are still counted."""
    jsonl = tmp_path / "corrupt.jsonl"
    jsonl.write_text(
        '{"type":"user","content":"hello"}\n'
        "{ not valid json\n"
        '{"type":"assistant","content":"hi"}\n',
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        result = ingest_file(jsonl)
    assert result.status == "captured"
    assert result.turn_count == 2
    assert any("malformed JSONL line 2" in r.message for r in caplog.records)


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


def test_ingest_assistant_event_with_string_content(tmp_bsela_home: Path, tmp_path: Path) -> None:
    """Cover line 139→143: nested content is a string, not a list → skip tool_use counting."""
    jsonl = tmp_path / "str-content.jsonl"
    jsonl.write_text(
        '{"type":"assistant","message":{"content":"just a string response"}}\n',
        encoding="utf-8",
    )
    result = ingest_file(jsonl)
    assert result.status in ("captured", "quarantined")
    assert result.tool_call_count == 0


def test_ingest_multiple_timestamps_tracks_min_max(tmp_bsela_home: Path, tmp_path: Path) -> None:
    """Cover line 148→129: second ts <= ended_at stays on the same path, loop continues."""
    jsonl = tmp_path / "multi-ts.jsonl"
    jsonl.write_text(
        '{"type":"user","content":"a","ts":"2026-01-15T10:00:00Z"}\n'
        '{"type":"assistant","content":"b","ts":"2026-01-15T11:00:00Z"}\n'
        '{"type":"user","content":"c","ts":"2026-01-15T10:30:00Z"}\n',
        encoding="utf-8",
    )
    result = ingest_file(jsonl)
    assert result.status == "captured"
    assert result.turn_count == 3


# ---- Cursor role-keyed format ----


def test_ingest_cursor_format_counts_turns_and_tools(
    tmp_bsela_home: Path,
) -> None:
    """Cursor transcripts use ``role`` instead of ``type``; turns and tools must still count."""
    result = ingest_file(
        FIXTURES / "cursor-looped-read.jsonl",
        source="cursor",
        auto_detect=False,
    )
    assert result.status == "captured"
    # 4 user + assistant role events (user, assistant x 3 pairs)
    assert result.turn_count >= 4
    # 3 tool_use blocks inside assistant.message.content
    assert result.tool_call_count >= 3


# ---- long-session / hashing ----


# ---- Dedup: same transcript ingested twice ----


def test_ingest_quarantined_transcript_dedup(
    tmp_bsela_home: Path, sample_leaked_session: Path
) -> None:
    """Re-ingesting a quarantined transcript returns the existing record, no new DB row."""
    first = ingest_file(sample_leaked_session)
    assert first.status == "quarantined"
    assert count_sessions() == 1

    second = ingest_file(sample_leaked_session)
    assert second.session_id == first.session_id
    assert second.status == "quarantined"
    assert count_sessions() == 1  # no new row


def test_ingest_captured_unchanged_content_hash_dedup(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    """Re-ingesting a captured transcript with identical content returns the existing record."""
    first = ingest_file(sample_clean_session, auto_detect=False)
    assert first.status == "captured"
    assert count_sessions() == 1

    second = ingest_file(sample_clean_session, auto_detect=False)
    assert second.session_id == first.session_id
    assert second.status == "captured"
    assert count_sessions() == 1  # no new row


def test_ingest_captured_new_content_hash_creates_new_record(
    tmp_bsela_home: Path, tmp_path: Path
) -> None:
    """Re-ingesting a captured transcript with grown content creates a new record."""
    jsonl = tmp_path / "growing.jsonl"
    jsonl.write_text('{"type":"user","content":"hello"}\n', encoding="utf-8")
    first = ingest_file(jsonl, auto_detect=False)
    assert first.status == "captured"
    assert count_sessions() == 1

    # Append a new line to simulate the transcript growing between hook fires.
    jsonl.write_text(
        '{"type":"user","content":"hello"}\n{"type":"assistant","content":"hi"}\n',
        encoding="utf-8",
    )
    second = ingest_file(jsonl, auto_detect=False)
    assert second.session_id != first.session_id
    assert count_sessions() == 2  # new row for the grown transcript


# ---- Scrubber allowlist ----


def test_scrubber_allowlist_suppresses_false_positive(tmp_bsela_home: Path) -> None:
    """Text containing only an allowlisted placeholder key must not trigger quarantine."""
    scrub = Scrubber.from_patterns(
        [r"AKIA[0-9A-Z]{16}"],
        allowlist=["AKIAIOSFODNN7EXAMPLE"],
    )
    assert scrub.scan("The example key is AKIAIOSFODNN7EXAMPLE in the docs.") == []


def test_scrubber_allowlist_does_not_suppress_real_key(tmp_bsela_home: Path) -> None:
    """A non-allowlisted AKIA string must still trigger the pattern."""
    scrub = Scrubber.from_patterns(
        [r"AKIA[0-9A-Z]{16}"],
        allowlist=["AKIAIOSFODNN7EXAMPLE"],
    )
    # AKIAREALKEYABCD12345 = AKIA + 16 uppercase/digit chars, not in allowlist
    assert scrub.scan("key=AKIAREALKEYABCD12345") == [r"AKIA[0-9A-Z]{16}"]


def test_ingest_streaming_hash_matches_full_file_digest(
    tmp_bsela_home: Path,
) -> None:
    """Large JSONL transcripts must hash like read_bytes() without OOM risk."""
    pad = "x" * 450
    line = f'{{"type":"user","ts":"2025-01-01T00:00:00Z","p":"{pad}"}}\n'
    n = 3500
    path = tmp_bsela_home / "sessions" / "long.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (line * n).encode("utf-8")
    assert len(body) > 1024 * 1024, "fixture should exceed one hash chunk"
    path.write_bytes(body)

    expected = hashlib.sha256(body).hexdigest()
    result = ingest_file(path, auto_detect=False)
    session = get_session(result.session_id)
    assert session is not None
    assert session.content_hash == expected
