"""Distiller orchestration: Haiku judge → Opus distill → Lesson rows.

The judge scores a session's overall health. When the session looks clean
(goal achieved + high judge confidence), no distillation happens. Otherwise
the distiller turns the detector's ``ErrorRecord`` candidates into
``LessonCandidate`` entries, which are (optionally) persisted as ``Lesson``
rows with ``status='pending'`` for the P3 updater to consume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bsela.llm.client import LLMClient
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import ErrorRecord, Lesson, SessionRecord
from bsela.memory.store import get_session, list_errors, list_lessons, save_lesson

JUDGE_SYSTEM_PROMPT = (
    "You score a completed coding-AI session. Read the summary JSON and return a single "
    "JSON object with these keys and nothing else:\n\n"
    '{"goal_achieved": bool, "efficiency": 0..1, "looped": bool, "wasted_tokens": bool, '
    '"confidence": 0..1, "notes": ""}\n\n'
    "Rules:\n"
    "- Ground every flag in candidate_errors. With no candidates, assume goal_achieved=true.\n"
    "- efficiency is a float 0..1 where 1.0 is optimal.\n"
    "- confidence is how sure you are in this verdict.\n"
    "- Never include text outside the JSON object.\n"
)


@dataclass(frozen=True)
class DistillationResult:
    session_id: str
    verdict: JudgeVerdict
    distilled: bool
    response: DistillResponse
    persisted: tuple[Lesson, ...]


def _find_distiller_prompt() -> str:
    here = Path(__file__).resolve().parent
    for parent in (here, *here.parents):
        candidate = parent / "docs" / "prompts" / "failure-distiller.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "docs/prompts/failure-distiller.md not found — distiller prompt required."
    )


def _error_payload(error: ErrorRecord) -> dict[str, object]:
    return {
        "id": error.id,
        "category": error.category,
        "severity": error.severity,
        "snippet": error.snippet,
        "line_number": error.line_number,
    }


def _session_payload(
    session: SessionRecord,
    errors: list[ErrorRecord],
    recent_lessons: list[Lesson],
) -> str:
    payload = {
        "session": {
            "id": session.id,
            "source": session.source,
            "turn_count": session.turn_count,
            "tool_call_count": session.tool_call_count,
            "status": session.status,
            "candidate_errors": [_error_payload(e) for e in errors],
        },
        "recent_lessons": [
            {"id": lesson.id, "rule": lesson.rule, "scope": lesson.scope}
            for lesson in recent_lessons
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _candidate_to_lesson(
    session_id: str,
    source_error_id: str | None,
    candidate: LessonCandidate,
) -> Lesson:
    evidence = dict(candidate.evidence)
    evidence.setdefault("session_id", session_id)
    return Lesson(
        source_error_id=source_error_id,
        scope=candidate.scope,
        rule=candidate.rule,
        why=candidate.why,
        how_to_apply=candidate.how_to_apply,
        confidence=candidate.confidence,
        status="pending",
    )


def distill_session(
    session_id: str,
    *,
    client: LLMClient,
    persist: bool = True,
    judge_threshold: float = 0.8,
    recent_lessons_limit: int = 10,
) -> DistillationResult:
    """Run judge→distill for one session. Returns the decision trail."""
    session = get_session(session_id)
    if session is None:
        raise LookupError(f"session not found: {session_id}")

    errors = list_errors(session_id=session_id, limit=50)
    recent = list_lessons(limit=recent_lessons_limit)
    user_payload = _session_payload(session, errors, recent)

    verdict = client.judge(system=JUDGE_SYSTEM_PROMPT, user=user_payload)

    healthy = (
        verdict.goal_achieved
        and verdict.confidence >= judge_threshold
        and not verdict.looped
        and not verdict.wasted_tokens
    )
    if healthy:
        return DistillationResult(
            session_id=session_id,
            verdict=verdict,
            distilled=False,
            response=DistillResponse(status="skip"),
            persisted=(),
        )

    response = client.distill(system=_find_distiller_prompt(), user=user_payload)
    persisted: list[Lesson] = []
    if persist:
        source_error_id = errors[0].id if errors else None
        for candidate in response.lessons:
            lesson = _candidate_to_lesson(session_id, source_error_id, candidate)
            persisted.append(save_lesson(lesson))
    else:
        persisted = [_candidate_to_lesson(session_id, None, c) for c in response.lessons]

    return DistillationResult(
        session_id=session_id,
        verdict=verdict,
        distilled=True,
        response=response,
        persisted=tuple(persisted),
    )


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "DistillationResult",
    "distill_session",
]
