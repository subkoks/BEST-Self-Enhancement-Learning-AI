"""P2 tests: deterministic detector spots corrections, loops, and tracebacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.memory.store import list_errors

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
