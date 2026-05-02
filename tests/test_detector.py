"""P2 tests: deterministic detector spots corrections, loops, and tracebacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsela.core.capture import ingest_file
from bsela.core.detector import (
    _extract_block_text,
    _fingerprint,
    _iter_tool_uses,
    _text_of,
    _user_text_only,
    detect_errors,
)
from bsela.memory.models import SessionRecord
from bsela.memory.store import list_errors, save_session

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


def _ingest(path: Path) -> str:
    """Ingest without auto-detect so each detector test starts from zero errors."""
    return ingest_file(path, auto_detect=False).session_id


def test_detects_user_correction(tmp_bsela_home: Path) -> None:
    sid = _ingest(FIXTURES / "user-correction.jsonl")
    result = detect_errors(sid)
    categories = [e.category for e in result.errors]
    assert "correction" in categories
    persisted = list_errors(session_id=sid)
    assert {e.category for e in persisted} == set(categories)


def test_detects_tool_use_loop(tmp_bsela_home: Path) -> None:
    sid = _ingest(FIXTURES / "looped-read.jsonl")
    result = detect_errors(sid)
    loops = [e for e in result.errors if e.category == "loop"]
    assert len(loops) == 1
    assert "Read" in loops[0].snippet


def test_detects_stack_trace(tmp_bsela_home: Path) -> None:
    sid = _ingest(FIXTURES / "stack-trace.jsonl")
    result = detect_errors(sid)
    traces = [e for e in result.errors if e.category == "stack_trace"]
    assert len(traces) >= 1
    assert "ValueError" in traces[0].snippet or "Traceback" in traces[0].snippet


def test_clean_session_yields_no_errors(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    sid = _ingest(sample_clean_session)
    result = detect_errors(sid)
    assert result.errors == ()
    assert list_errors(session_id=sid) == []


def test_quarantined_session_is_skipped(tmp_bsela_home: Path, sample_leaked_session: Path) -> None:
    sid = _ingest(sample_leaked_session)
    result = detect_errors(sid)
    assert result.errors == ()


def test_missing_session_raises(tmp_bsela_home: Path) -> None:
    with pytest.raises(LookupError):
        detect_errors("does-not-exist")


def test_persist_false_skips_write(tmp_bsela_home: Path) -> None:
    sid = _ingest(FIXTURES / "user-correction.jsonl")
    result = detect_errors(sid, persist=False)
    assert result.errors
    assert list_errors(session_id=sid) == []


# ---- Claude Code nested format (event.message.content[]) --------------------


def test_detects_loop_in_nested_format(tmp_bsela_home: Path) -> None:
    """Loop detector must find repeated tool_use blocks in assistant.message.content[]."""
    sid = _ingest(FIXTURES / "nested-looped-read.jsonl")
    result = detect_errors(sid)
    loops = [e for e in result.errors if e.category == "loop"]
    assert len(loops) == 1
    assert "Read" in loops[0].snippet


def test_detects_stack_trace_in_nested_tool_result(tmp_bsela_home: Path) -> None:
    """Stack-trace detector must find tracebacks inside user.message.content[tool_result]."""
    sid = _ingest(FIXTURES / "nested-stack-trace.jsonl")
    result = detect_errors(sid)
    traces = [e for e in result.errors if e.category == "stack_trace"]
    assert len(traces) >= 1
    assert "Traceback" in traces[0].snippet or "ValueError" in traces[0].snippet


def test_detect_missing_transcript(tmp_bsela_home: Path, tmp_path: Path) -> None:
    """Cover _detect_for line 269: transcript file doesn't exist."""
    phantom = tmp_path / "ghost.jsonl"  # does not exist
    rec = SessionRecord(
        source="test",
        transcript_path=str(phantom),
        content_hash="abc",
        started_at=None,
        ended_at=None,
        turn_count=0,
        tool_call_count=0,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        status="captured",
    )
    save_session(rec)
    result = detect_errors(rec.id, persist=False)
    assert result.errors == ()


# ---- internal function unit tests ----


def test_extract_block_text_returns_text_block() -> None:
    assert _extract_block_text({"type": "text", "text": "hello"}) == "hello"


def test_extract_block_text_returns_empty_for_none_text() -> None:
    assert _extract_block_text({"type": "text", "text": None}) == ""


def test_extract_block_text_tool_result_string() -> None:
    assert _extract_block_text({"type": "tool_result", "content": "output"}) == "output"


def test_extract_block_text_tool_result_list() -> None:
    content = [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]
    result = _extract_block_text({"type": "tool_result", "content": content})
    assert "line1" in result
    assert "line2" in result


def test_extract_block_text_unknown_type() -> None:
    assert _extract_block_text({"type": "image", "data": "..."}) == ""


def test_text_of_json_dumps_non_string_flat() -> None:
    """Cover lines 98-99: flat content is a dict, JSON-serializable."""
    event = {"content": {"key": "value"}}
    result = _text_of(event)
    assert '"key"' in result


def test_text_of_json_fallback_non_serializable() -> None:
    """Cover lines 100-101: flat is not JSON-serializable → str()."""

    class Unserializable:
        def __repr__(self) -> str:
            return "unserializable_obj"

    event = {"content": Unserializable()}
    result = _text_of(event)
    assert "unserializable_obj" in result


def test_fingerprint_fallback_on_non_serializable_payload() -> None:
    """Cover lines 114-115: payload can't be JSON-dumped."""

    class BadPayload:
        pass

    event = {"name": "Read", "input": BadPayload()}
    # Should not raise — falls back to str()
    fp = _fingerprint(event)
    assert isinstance(fp, str)
    assert len(fp) == 40  # SHA1 hex


def test_user_text_only_returns_nested_text_blocks() -> None:
    """Cover lines 139-141: user event with nested message.content text blocks."""
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": "ignored"},
                {"type": "text", "text": "user typed this"},
            ]
        },
    }
    result = _user_text_only(event)
    assert "user typed this" in result
    assert "ignored" not in result


def test_extract_block_text_tool_result_non_list_non_str_content() -> None:
    """Cover line 69→75: content is neither str nor list → return ''."""
    result = _extract_block_text({"type": "tool_result", "content": 42})
    assert result == ""


def test_user_text_only_empty_text_block_skipped() -> None:
    """Cover line 140→137: text block with empty text → skip append."""
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "text", "text": ""},  # empty → skipped
                {"type": "text", "text": "real content"},
            ]
        },
    }
    result = _user_text_only(event)
    assert result == "real content"


def test_iter_jsonl_skips_blank_lines(tmp_bsela_home: Path, tmp_path: Path) -> None:
    """Cover line 48: blank lines in JSONL are skipped."""
    jsonl = tmp_path / "sparse.jsonl"
    jsonl.write_text(
        '{"type":"user","content":"hello"}\n\n\n{"type":"assistant","content":"hi"}\n',
        encoding="utf-8",
    )
    # Create a session record pointing at this file and run detect_errors
    sess = save_session(
        SessionRecord(
            source="test",
            transcript_path=str(jsonl),
            content_hash="sparse",
            status="captured",
        )
    )
    result = detect_errors(sess.id, persist=False)
    assert result.errors == ()  # no errors in simple content


def test_iter_tool_uses_skips_non_tool_blocks_in_assistant() -> None:
    """Cover line 187→186: nested block type is not tool_use → skip it."""
    events = [
        (
            1,
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "some prose"},  # not tool_use → skip
                        {"type": "tool_use", "name": "Read", "id": "x", "input": {}},
                    ]
                },
            },
        )
    ]
    results = list(_iter_tool_uses(events))
    assert len(results) == 1
    assert results[0][1].get("type") == "tool_use"


# ---- Cursor role-keyed format (role instead of type at event top level) ----


def test_detects_correction_in_cursor_format(tmp_bsela_home: Path) -> None:
    """Correction detector must fire on ``role: "user"`` events (Cursor transcript format)."""
    sid = _ingest(FIXTURES / "cursor-correction.jsonl")
    result = detect_errors(sid)
    categories = [e.category for e in result.errors]
    assert "correction" in categories


def test_detects_loop_in_cursor_format(tmp_bsela_home: Path) -> None:
    """Loop detector must find repeated tool_use in ``role: "assistant".message.content[]``."""
    sid = _ingest(FIXTURES / "cursor-looped-read.jsonl")
    result = detect_errors(sid)
    loops = [e for e in result.errors if e.category == "loop"]
    assert len(loops) == 1
    assert "Read" in loops[0].snippet


def test_detects_stack_trace_in_cursor_format(tmp_bsela_home: Path) -> None:
    """Stack-trace detector must find tracebacks in ``role: "user"`` tool_result blocks."""
    sid = _ingest(FIXTURES / "cursor-stack-trace.jsonl")
    result = detect_errors(sid)
    traces = [e for e in result.errors if e.category == "stack_trace"]
    assert len(traces) >= 1
    assert "Traceback" in traces[0].snippet or "ValueError" in traces[0].snippet
