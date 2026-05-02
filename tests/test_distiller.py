"""P2 tests: distiller orchestrates judge → distill → persisted lessons."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import bsela.llm.distiller as _distiller_mod
from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.llm.client import FakeLLMClient, _extract_json_object
from bsela.llm.distiller import (
    _find_distiller_prompt,
    _is_duplicate,
    _jaccard,
    _tokens,
    distill_session,
)
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import Lesson
from bsela.memory.store import count_lessons, list_lessons, save_lesson

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


def _healthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=True,
        efficiency=0.9,
        looped=False,
        wasted_tokens=False,
        confidence=0.95,
    )


def _unhealthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=False,
        efficiency=0.3,
        looped=True,
        wasted_tokens=True,
        confidence=0.6,
    )


def _sample_distill() -> DistillResponse:
    return DistillResponse(
        status="ok",
        confidence=0.92,
        lessons=[
            LessonCandidate(
                rule="Stop retrying Read on a missing path after the first ENOENT",
                why="Loop detector flagged three identical Read calls returning ENOENT",
                how_to_apply="When Read returns ENOENT twice on the same path, change strategy",
                scope="project",
                confidence=0.9,
                evidence={"line_range": [3, 9]},
            )
        ],
    )


def test_extract_json_object_tolerates_prose() -> None:
    raw = 'Sure, here is the JSON: {"a": 1, "b": [1,2]} — done.'
    payload = json.loads(_extract_json_object(raw))
    assert payload == {"a": 1, "b": [1, 2]}


def test_extract_json_object_raises_when_absent() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        _extract_json_object("nothing to parse here")


def test_distill_skips_healthy_session(tmp_bsela_home: Path) -> None:
    sid = ingest_file(FIXTURES / "clean.jsonl").session_id
    client = FakeLLMClient(
        judge_response=_healthy_verdict(),
        distill_response=_sample_distill(),
    )
    result = distill_session(sid, client=client)
    assert result.distilled is False
    assert result.persisted == ()
    assert client.judge_calls == 1
    assert client.distill_calls == 0
    assert count_lessons() == 0


def test_distill_persists_lessons_for_unhealthy_session(tmp_bsela_home: Path) -> None:
    sid = ingest_file(FIXTURES / "looped-read.jsonl").session_id
    detect_errors(sid)
    client = FakeLLMClient(
        judge_response=_unhealthy_verdict(),
        distill_response=_sample_distill(),
    )
    result = distill_session(sid, client=client)
    assert result.distilled is True
    assert client.distill_calls == 1
    assert len(result.persisted) == 1
    stored = list_lessons(status="pending")
    assert len(stored) == 1
    assert stored[0].scope == "project"
    assert stored[0].source_error_id is not None


def test_distill_without_persist_skips_writes(tmp_bsela_home: Path) -> None:
    sid = ingest_file(FIXTURES / "looped-read.jsonl").session_id
    detect_errors(sid)
    client = FakeLLMClient(
        judge_response=_unhealthy_verdict(),
        distill_response=_sample_distill(),
    )
    result = distill_session(sid, client=client, persist=False)
    assert result.distilled is True
    assert len(result.persisted) == 1
    assert count_lessons() == 0


def test_distill_missing_session_raises(tmp_bsela_home: Path) -> None:
    client = FakeLLMClient(
        judge_response=_healthy_verdict(),
        distill_response=_sample_distill(),
    )
    with pytest.raises(LookupError):
        distill_session("missing", client=client)


# ---- dedup unit tests ----


def test_tokens_removes_stop_words_and_short_words() -> None:
    toks = _tokens("Stop retrying Read on a missing path")
    assert "on" not in toks
    assert "a" not in toks
    assert "retrying" in toks
    assert "missing" in toks
    assert "path" in toks
    # "Read" normalises to "read" (len=4 > 2)
    assert "read" in toks


def test_tokens_short_words_excluded() -> None:
    # words with len <= 2 are dropped
    toks = _tokens("an ox go do up")
    assert toks == frozenset()


def test_jaccard_identical_sets() -> None:
    a = frozenset(["read", "retry", "path"])
    assert _jaccard(a, a) == pytest.approx(1.0)


def test_jaccard_disjoint_sets() -> None:
    a = frozenset(["read", "retry"])
    b = frozenset(["write", "commit"])
    assert _jaccard(a, b) == pytest.approx(0.0)


def test_jaccard_partial_overlap() -> None:
    a = frozenset(["read", "retry", "path"])
    b = frozenset(["read", "retry", "write"])
    # intersection=2, union=4
    assert _jaccard(a, b) == pytest.approx(2 / 4)


def test_jaccard_both_empty() -> None:
    assert _jaccard(frozenset(), frozenset()) == pytest.approx(1.0)


def _make_lesson(rule: str) -> Lesson:
    return Lesson(
        scope="project",
        rule=rule,
        why="test",
        how_to_apply="test",
        confidence=0.9,
        status="pending",
    )


def test_is_duplicate_exact_match(tmp_bsela_home: Path) -> None:
    rule = "Stop retrying Read on a missing path after the first ENOENT"
    existing = [save_lesson(_make_lesson(rule))]
    assert _is_duplicate(rule, existing, threshold=0.85) is True


def test_is_duplicate_near_match(tmp_bsela_home: Path) -> None:
    # Differ only by one word — high Jaccard overlap.
    rule_a = "Stop retrying Read on a missing path after the first ENOENT"
    rule_b = "Stop retrying Read calls on a missing path after the first ENOENT"
    existing = [save_lesson(_make_lesson(rule_a))]
    # intersection=7 / union=8 = 0.875 > 0.5 threshold
    assert _is_duplicate(rule_b, existing, threshold=0.5) is True


def test_is_duplicate_different_rules(tmp_bsela_home: Path) -> None:
    existing = [save_lesson(_make_lesson("Always use pathlib for filesystem operations"))]
    assert (
        _is_duplicate(
            "Check external CLI tool availability before invoking", existing, threshold=0.85
        )
        is False
    )


def test_distill_dedup_suppresses_duplicate_candidate(tmp_bsela_home: Path) -> None:
    """Candidate that duplicates a recent lesson must not be persisted."""
    sid = ingest_file(FIXTURES / "looped-read.jsonl").session_id
    detect_errors(sid)

    # Pre-save a lesson with the same rule the FakeLLMClient will return.
    rule = "Stop retrying Read on a missing path after the first ENOENT"
    save_lesson(_make_lesson(rule))

    client = FakeLLMClient(
        judge_response=_unhealthy_verdict(),
        distill_response=_sample_distill(),  # returns the same rule as above
    )
    result = distill_session(sid, client=client, recent_lessons_limit=10)
    # Distillation ran but candidate was deduped — nothing new persisted.
    assert result.distilled is True
    assert result.persisted == ()
    assert count_lessons(status="pending") == 1  # only the pre-saved one


def test_distill_dedup_within_batch(tmp_bsela_home: Path) -> None:
    """Two identical candidates in the same response — only one should persist."""
    sid = ingest_file(FIXTURES / "looped-read.jsonl").session_id
    detect_errors(sid)

    candidate = LessonCandidate(
        rule="Stop retrying Read on a missing path after the first ENOENT",
        why="loop",
        how_to_apply="change strategy",
        scope="project",
        confidence=0.9,
    )
    double_response = DistillResponse(status="ok", confidence=0.9, lessons=[candidate, candidate])
    client = FakeLLMClient(
        judge_response=_unhealthy_verdict(),
        distill_response=double_response,
    )
    result = distill_session(sid, client=client)
    assert result.distilled is True
    assert len(result.persisted) == 1  # second copy deduped within batch
    assert count_lessons(status="pending") == 1


def test_find_distiller_prompt_raises_when_not_found() -> None:
    """Cover line 141: prompt file not found anywhere → FileNotFoundError."""
    with (
        patch.object(_distiller_mod, "__file__", "/nonexistent/path/fake.py"),
        pytest.raises(FileNotFoundError, match=r"failure-distiller\.md"),
    ):
        _find_distiller_prompt()
