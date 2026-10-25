"""Tests for the Codex rollout adapter: discovery + canonicalization."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bsela.adapters.codex import (
    SOURCE,
    default_session_roots,
    discover_rollouts,
    find_rollout,
    is_rollout_path,
    is_user_rollout,
    normalize_event,
    read_session_meta,
    session_id_from_path,
    strip_injected_context,
)

SESSION_ID = "019d1234-5678-7abc-8def-0123456789ab"


def _envelope(payload: dict[str, object], *, kind: str = "response_item") -> dict[str, object]:
    return {"timestamp": "2026-01-15T10:00:00.000Z", "type": kind, "payload": payload}


def _write_rollout(
    directory: Path,
    *,
    name: str | None = None,
    thread_source: object = "user",
    extra_lines: tuple[dict[str, object], ...] = (),
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"rollout-2026-01-15T10-00-00-{SESSION_ID}.jsonl")
    meta = _envelope(
        {
            "id": SESSION_ID,
            "session_id": SESSION_ID,
            "thread_source": thread_source,
            "originator": "codex-tui",
        },
        kind="session_meta",
    )
    lines = [meta, *extra_lines]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


# ---- normalize_event -------------------------------------------------------


def test_normalize_user_message_strips_injected_context() -> None:
    event = _envelope(
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "# AGENTS.md instructions for /tmp/x\n\n<INSTRUCTIONS>\n"
                    "- Hard Stop: never delete files\n</INSTRUCTIONS>\n\n"
                    "<environment_context><cwd>/tmp/x</cwd></environment_context>\n\n"
                    "rename parseAuthToken",
                }
            ],
        }
    )
    canonical = normalize_event(event)
    assert canonical is not None
    assert canonical["type"] == "user"
    assert canonical["message"]["content"][0]["text"] == "rename parseAuthToken"
    assert canonical["ts"] == "2026-01-15T10:00:00.000Z"


def test_normalize_drops_messages_with_only_harness_context() -> None:
    event = _envelope(
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "<environment_context><cwd>/tmp/x</cwd></environment_context>",
                }
            ],
        }
    )
    assert normalize_event(event) is None


def test_normalize_keeps_assistant_text_verbatim() -> None:
    event = _envelope(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Done. <INSTRUCTIONS>not stripped"}],
        }
    )
    canonical = normalize_event(event)
    assert canonical is not None
    assert canonical["message"]["content"][0]["text"] == "Done. <INSTRUCTIONS>not stripped"


def test_normalize_drops_developer_and_unknown_roles() -> None:
    for role in ("developer", "system", "tool"):
        event = _envelope(
            {"type": "message", "role": role, "content": [{"type": "input_text", "text": "x"}]}
        )
        assert normalize_event(event) is None


def test_normalize_drops_non_text_and_empty_blocks() -> None:
    assert (
        normalize_event(
            _envelope(
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": "data:image/png;base64,abc"},
                        {"type": "text", "text": "   "},
                        {"type": "text", "text": 42},
                        "not-a-dict",
                    ],
                }
            )
        )
        is None
    )
    assert (
        normalize_event(_envelope({"type": "message", "role": "user", "content": "flat"})) is None
    )


def test_normalize_function_call_parses_arguments() -> None:
    canonical = normalize_event(
        _envelope(
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd": "ls"}',
            }
        )
    )
    assert canonical is not None
    assert canonical["type"] == "tool_use"
    assert canonical["name"] == "exec_command"
    assert canonical["input"] == {"cmd": "ls"}


def test_normalize_function_call_keeps_unparsable_arguments() -> None:
    canonical = normalize_event(
        _envelope({"type": "function_call", "name": "shell", "arguments": "ls -la"})
    )
    assert canonical is not None
    assert canonical["input"] == {"raw": "ls -la"}


def test_normalize_custom_tool_call_accepts_input_mapping_and_missing_name() -> None:
    canonical = normalize_event(
        _envelope({"type": "custom_tool_call", "input": {"patch": "*** Begin Patch"}})
    )
    assert canonical is not None
    assert canonical["name"] == "custom_tool_call"
    assert canonical["input"] == {"patch": "*** Begin Patch"}

    empty = normalize_event(_envelope({"type": "custom_tool_call"}))
    assert empty is not None
    assert empty["input"] == {}


def test_normalize_tool_output_shapes() -> None:
    text = normalize_event(_envelope({"type": "function_call_output", "output": "exit code: 0"}))
    assert text == {"type": "tool_result", "content": "exit code: 0"}

    nested = normalize_event(
        _envelope({"type": "custom_tool_call_output", "output": {"content": "patched"}})
    )
    assert nested == {"type": "tool_result", "content": "patched"}

    dumped = normalize_event(
        _envelope({"type": "function_call_output", "output": {"exit_code": 1}})
    )
    assert dumped == {"type": "tool_result", "content": '{"exit_code": 1}'}

    listed = normalize_event(_envelope({"type": "function_call_output", "output": [1, 2]}))
    assert listed == {"type": "tool_result", "content": "[1, 2]"}

    odd = normalize_event(_envelope({"type": "function_call_output", "output": {1, 2}}))
    assert odd is not None
    assert "1" in odd["content"]

    assert normalize_event(_envelope({"type": "function_call_output"})) is None
    assert normalize_event(_envelope({"type": "function_call_output", "output": ""})) is None


def test_normalize_skips_non_content_envelopes() -> None:
    assert normalize_event({"type": "turn_context", "payload": {"cwd": "/tmp"}}) is None
    assert normalize_event({"type": "response_item", "payload": "not-a-mapping"}) is None
    assert normalize_event(_envelope({"type": "reasoning", "summary": []})) is None
    assert normalize_event({"type": "response_item"}) is None


def test_normalize_omits_ts_when_envelope_has_none() -> None:
    canonical = normalize_event(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        }
    )
    assert canonical is not None
    assert "ts" not in canonical


# ---- strip_injected_context ------------------------------------------------


def test_strip_injected_context_removes_known_envelopes() -> None:
    text = (
        "<recommended_plugins>\n- Airtable\n</recommended_plugins>\n"
        "<skill>\n<name>x</name>\n</skill>\n"
        "keep me"
    )
    assert strip_injected_context(text) == "keep me"


def test_strip_injected_context_drops_truncated_envelope() -> None:
    text = "do the thing\n<environment_context>\n  <cwd>/tmp/x</cwd>"
    assert strip_injected_context(text) == "do the thing"


def test_strip_injected_context_keeps_ide_request_only() -> None:
    text = (
        "# Context from my IDE setup:\n\n## Active file: arithmetic.py\n\n"
        "## My request:\nCreate an image of a horse"
    )
    assert strip_injected_context(text) == "Create an image of a horse"


def test_strip_injected_context_without_request_marker_returns_empty() -> None:
    text = "# Context from my IDE setup:\n\n## Active file: arithmetic.py"
    assert strip_injected_context(text) == ""


def test_strip_injected_context_drops_agents_header_without_path() -> None:
    text = "# AGENTS.md instructions\n\n<INSTRUCTIONS>\n- rule\n</INSTRUCTIONS>\n"
    assert strip_injected_context(text) == ""


def test_strip_injected_context_passes_user_prose_through() -> None:
    assert strip_injected_context("please rename the helper") == "please rename the helper"


# ---- path helpers ----------------------------------------------------------


def test_is_rollout_path_and_session_id() -> None:
    path = Path(f"/tmp/{SESSION_ID}.jsonl")
    assert is_rollout_path(Path(f"rollout-2026-01-15T10-00-00-{SESSION_ID}.jsonl"))
    assert not is_rollout_path(path)
    assert not is_rollout_path(Path("rollout-2026-01-15.jsonl.bak"))
    assert session_id_from_path(Path(f"rollout-2026-01-15T10-00-00-{SESSION_ID}.jsonl")) == (
        SESSION_ID
    )
    assert session_id_from_path(Path("rollout-2026-01-15.jsonl")) is None
    assert SOURCE == "codex"


def test_default_session_roots_point_at_codex_home() -> None:
    roots = default_session_roots()
    assert roots[0].parts[-1] == "sessions"
    assert roots[1].parts[-1] == "archived_sessions"


# ---- session meta + sub-thread filter --------------------------------------


def test_read_session_meta_reads_first_envelope(tmp_path: Path) -> None:
    path = _write_rollout(tmp_path)
    meta = read_session_meta(path)
    assert meta is not None
    assert meta["id"] == SESSION_ID
    assert is_user_rollout(path)


def test_read_session_meta_handles_missing_and_malformed(tmp_path: Path) -> None:
    assert read_session_meta(tmp_path / "absent.jsonl") is None

    broken = tmp_path / "rollout-broken.jsonl"
    broken.write_text("{ not json\n", encoding="utf-8")
    assert read_session_meta(broken) is None

    not_meta = tmp_path / "rollout-other.jsonl"
    not_meta.write_text(json.dumps(_envelope({"type": "message"})) + "\n", encoding="utf-8")
    assert read_session_meta(not_meta) is None

    scalar = tmp_path / "rollout-scalar.jsonl"
    scalar.write_text('"just a string"\n', encoding="utf-8")
    assert read_session_meta(scalar) is None

    bad_payload = tmp_path / "rollout-bad-payload.jsonl"
    bad_payload.write_text(
        json.dumps({"type": "session_meta", "payload": 7}) + "\n", encoding="utf-8"
    )
    assert read_session_meta(bad_payload) is None


def test_is_user_rollout_flags_guardian_and_subagent_threads(tmp_path: Path) -> None:
    guardian = _write_rollout(tmp_path / "g", thread_source="guardian_review")
    subagent = _write_rollout(tmp_path / "s", thread_source="subagent")
    assert not is_user_rollout(guardian)
    assert not is_user_rollout(subagent)


def test_is_user_rollout_treats_meta_less_files_as_user_threads(tmp_path: Path) -> None:
    orphan = tmp_path / "rollout-2026-01-15.jsonl"
    orphan.write_text("[1, 2, 3]\n", encoding="utf-8")
    assert is_user_rollout(orphan)


# ---- discovery -------------------------------------------------------------


def test_discover_rollouts_newest_first_and_filtered(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    older = _write_rollout(root / "2026" / "01" / "15")
    newer = _write_rollout(
        root / "2026" / "01" / "16",
        name="rollout-2026-01-16T10-00-00-019d9999-1111-7222-8333-444455556666.jsonl",
    )
    guardian = _write_rollout(root / "2026" / "01" / "17", thread_source="guardian_review")
    (root / "notes.txt").write_text("ignore me", encoding="utf-8")

    now = datetime.now(UTC).timestamp()
    os.utime(older, (now - 3 * 86400, now - 3 * 86400))
    os.utime(newer, (now - 2 * 86400, now - 2 * 86400))
    os.utime(guardian, (now, now))

    found = discover_rollouts([root])
    assert found == [newer, older]
    assert discover_rollouts([tmp_path / "absent"]) == []
    assert discover_rollouts([root], limit=1) == [newer]
    assert discover_rollouts([root], since=datetime.now(UTC) - timedelta(days=1)) == []
    assert discover_rollouts([root], user_threads_only=False) == [guardian, newer, older]


def test_find_rollout_by_session_id(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    path = _write_rollout(root / "2026" / "01" / "15")
    assert find_rollout(SESSION_ID, roots=[root]) == path
    assert find_rollout("019d9999-1111-7222-8333-444455556666", roots=[root]) is None
    assert find_rollout("not-an-id", roots=[root]) is None
    assert find_rollout(SESSION_ID, roots=[tmp_path / "absent"]) is None


def test_find_rollout_prefers_newest_and_skips_internal_threads(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    older = _write_rollout(root / "2026" / "01" / "15")
    newer = _write_rollout(
        root / "2026" / "01" / "16",
        name=f"rollout-2026-01-16T10-00-00-{SESSION_ID}.jsonl",
        thread_source="subagent",
    )
    now = datetime.now(UTC).timestamp()
    os.utime(older, (now - 60, now - 60))
    os.utime(newer, (now, now))

    # The newer file is an internal subagent thread, so the user thread wins.
    assert find_rollout(SESSION_ID, roots=[root]) == older


def test_find_rollout_compares_candidates_across_roots(tmp_path: Path) -> None:
    newer_root = tmp_path / "newer"
    older_root = tmp_path / "older"
    newer = _write_rollout(newer_root)
    older = _write_rollout(older_root)
    now = datetime.now(UTC).timestamp()
    os.utime(newer, (now, now))
    os.utime(older, (now - 3600, now - 3600))

    # Older root first: the newer candidate replaces it, then loses to nothing.
    assert find_rollout(SESSION_ID, roots=[older_root, newer_root]) == newer
    # Newer root first: the older candidate is inspected and rejected.
    assert find_rollout(SESSION_ID, roots=[newer_root, older_root]) == newer
