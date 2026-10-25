"""Detector behaviour on Codex rollouts (canonicalization + harness stripping)."""

from __future__ import annotations

import json
from pathlib import Path

from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.memory.store import list_errors

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"
SESSION_ID = "019d1234-5678-7abc-8def-0123456789ab"


def _write_rollout(path: Path, events: list[dict[str, object]]) -> Path:
    meta = {
        "timestamp": "2026-01-16T09:00:00.000Z",
        "type": "session_meta",
        "payload": {"id": SESSION_ID, "thread_source": "user", "originator": "codex-tui"},
    }
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in [meta, *events]), encoding="utf-8"
    )
    return path


def _message(role: str, text: str, *, kind: str = "input_text") -> dict[str, object]:
    return {
        "type": "response_item",
        "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]},
    }


def test_injected_agents_rules_do_not_mint_corrections(tmp_bsela_home: Path) -> None:
    result = ingest_file(FIXTURES / "codex-rollout.jsonl", source="codex")
    assert result.errors_detected == 0
    assert list_errors(session_id=result.session_id) == []


def test_codex_assistant_text_is_scanned_for_stack_traces(
    tmp_bsela_home: Path, tmp_path: Path
) -> None:
    rollout = _write_rollout(
        tmp_path / "rollout-2026-01-16T09-00-00.jsonl",
        [
            _message("user", "run the test suite"),
            _message(
                "assistant",
                "The run failed:\nTraceback (most recent call last):\n  ValueError: bad input",
                kind="output_text",
            ),
        ],
    )
    captured = ingest_file(rollout, source="codex")
    errors = list_errors(session_id=captured.session_id)
    assert [err.category for err in errors] == ["stack_trace"]
    assert errors[0].line_number == 3


def test_codex_loop_pass_uses_canonical_tool_calls(tmp_bsela_home: Path, tmp_path: Path) -> None:
    call: dict[str, object] = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "apply_patch",
            "input": "*** Begin Patch\n*** End Patch",
        },
    }
    rollout = _write_rollout(
        tmp_path / "rollout-2026-01-16T09-00-01.jsonl",
        [_message("user", "apply the patch"), call, call, call],
    )
    captured = ingest_file(rollout, source="codex")
    categories = [err.category for err in list_errors(session_id=captured.session_id)]
    assert categories == ["loop"]


def test_detector_is_a_noop_for_missing_transcript(tmp_bsela_home: Path, tmp_path: Path) -> None:
    rollout = _write_rollout(tmp_path / "rollout-2026-01-16T09-00-02.jsonl", [])
    captured = ingest_file(rollout, source="codex")
    rollout.unlink()
    result = detect_errors(captured.session_id, persist=False)
    assert result.errors == ()
