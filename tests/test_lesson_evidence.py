"""Regression coverage for attribution, quoted diagnostics, and polling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.detector import _scan_loop, _scan_stack_trace
from bsela.llm.client import FakeLLMClient
from bsela.llm.distiller import distill_session
from bsela.llm.runtime import ProviderError
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import ErrorRecord, Lesson, LessonEvidence, SessionRecord
from bsela.memory.store import (
    count_lessons,
    get_lesson_evidence,
    has_session_evaluation,
    save_error,
    save_lesson,
    save_session,
)


def candidate(evidence: dict[str, object]) -> LessonCandidate:
    return LessonCandidate(
        rule="Validate subprocess diagnostics before declaring completion",
        why="A subprocess failed",
        how_to_apply="Inspect its diagnostic",
        scope="project",
        confidence=0.9,
        evidence=evidence,
    )


def setup_session(tmp_path: Path) -> tuple[SessionRecord, ErrorRecord, ErrorRecord]:
    path = tmp_path / "evidence.jsonl"
    path.write_text("{}\n" * 10)
    session = save_session(
        SessionRecord(source="test", transcript_path=str(path), content_hash="test")
    )
    first = save_error(
        ErrorRecord(session_id=session.id, category="stack_trace", snippet="first", line_number=2)
    )
    second = save_error(
        ErrorRecord(session_id=session.id, category="stack_trace", snippet="second", line_number=8)
    )
    return session, first, second


def fake(candidates: list[LessonCandidate]) -> FakeLLMClient:
    return FakeLLMClient(
        JudgeVerdict(
            goal_achieved=False, efficiency=0.2, looped=False, wasted_tokens=False, confidence=0.9
        ),
        DistillResponse(lessons=candidates),
    )


def test_links_cited_error_and_persists_reviewable_range(
    tmp_bsela_home: Path, tmp_path: Path
) -> None:
    session, first, second = setup_session(tmp_path)
    result = distill_session(
        session.id, client=fake([candidate({"session_id": session.id, "line_range": [7, 9]})])
    )
    lesson = result.persisted[0]
    assert lesson.source_error_id == second.id != first.id
    evidence = get_lesson_evidence(lesson.id)
    assert evidence is not None
    assert (evidence.session_id, evidence.line_start, evidence.line_end) == (session.id, 7, 9)
    cli = CliRunner()
    shown = cli.invoke(app, ["review", "show", lesson.id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["evidence"] == {"session_id": session.id, "line_range": [7, 9]}
    text = cli.invoke(app, ["review", "show", lesson.id])
    assert text.exit_code == 0
    assert "lines 7-9" in text.stdout


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"session_id": "foreign", "line_range": [2, 2]},
        {"line_range": "2,2"},
        {"line_range": [2]},
        {"line_range": [False, 2]},
        {"line_range": ["2", 2]},
        {"line_range": [2.0, 2]},
        {"line_range": [0, 2]},
        {"line_range": [8, 2]},
        {"line_range": [2, 11]},
        {"line_range": [3, 4]},
    ],
)
def test_bad_evidence_rejects_entire_response_without_checkpoint(
    tmp_bsela_home: Path, tmp_path: Path, evidence: dict[str, object]
) -> None:
    session, _, _ = setup_session(tmp_path)
    with pytest.raises(ProviderError, match="invalid response evidence"):
        distill_session(
            session.id, client=fake([candidate({"line_range": [2, 2]}), candidate(evidence)])
        )
    assert count_lessons() == 0
    assert not has_session_evaluation(session.id)


def test_evidence_record_mismatch_rolls_back_lesson(tmp_bsela_home: Path) -> None:
    lesson = Lesson(scope="project", rule="rule", why="why", how_to_apply="how")
    with pytest.raises(ValueError, match="belong"):
        save_lesson(
            lesson,
            evidence=LessonEvidence(
                lesson_id="other", session_id="missing", line_start=1, line_end=1
            ),
        )
    assert count_lessons() == 0
    assert get_lesson_evidence(lesson.id) is None


@pytest.mark.parametrize(
    "text",
    [
        '"""Client abstraction raises RuntimeError: missing provider."""',
        '  213\t raise last_exc or RuntimeError("failed")',
        "+    except ValueError: pass",
        "# Example\n```python\nValueError: example only\n```",
        "~~~text\nTraceback (most recent call last):\nValueError: example\n~~~",
        "```\nValueError: example\n~~~\nValueError: still fenced\n```",
        '{"code":200,"name":"ValueError"}',
        '{"code":"401","name":"AuthError"}',
        '{"code":401,"name":"AuthFailure"}',
        '{"code":401,"name":false}',
        '{"code":401,broken}',
        '[{"code":401,"name":"AuthError"}]',
    ],
)
def test_quoted_source_and_documents_are_not_runtime_failures(text: str) -> None:
    assert not _scan_stack_trace([(1, {"type": "tool_result", "content": text})], "session")


@pytest.mark.parametrize(
    "text",
    [
        "Process exited with code 0\nTraceback (most recent call last):\nModuleNotFoundError: yaml",
        'Process exited with code 0\n{"code":401,"name":"AuthenticationRequiredError"}',
        '{"status":403,"name":"AuthorizationError"}',
        "```python\nValueError: example\n```\nValueError: real failure",
        "panic: runtime failure",
        "TypeError: undefined\n    at fn (/tmp/app.js:12:3)",
    ],
)
def test_real_failures_survive_exit_zero_wrappers(text: str) -> None:
    assert len(_scan_stack_trace([(1, {"type": "tool_result", "content": text})], "session")) == 1


@pytest.mark.parametrize(("chars", "expected"), [("", 0), ("run\n", 1)])
def test_polling_is_distinct_from_repeated_writes(chars: str, expected: int) -> None:
    event = {
        "type": "tool_use",
        "name": "functions.write_stdin",
        "input": {"session_id": 1, "chars": chars},
    }
    assert len(_scan_loop([(n, event) for n in range(1, 4)], "session", 3)) == expected
