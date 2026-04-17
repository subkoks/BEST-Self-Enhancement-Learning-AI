"""P2 tests: distiller orchestrates judge → distill → persisted lessons."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.llm.client import FakeLLMClient, _extract_json_object
from bsela.llm.distiller import distill_session
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.store import count_lessons, list_lessons

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
