"""Distiller orchestration: Provider-neutral judge → distill → Lesson rows.

The judge scores a session's overall health. When the session looks clean
(goal achieved + high judge confidence), no distillation happens. Otherwise
the distiller turns the detector's ``ErrorRecord`` candidates into
``LessonCandidate`` entries, which are (optionally) persisted as ``Lesson``
rows with ``status='pending'`` for the P3 updater to consume.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from bsela.llm.client import LLMClient
from bsela.llm.runtime import ProviderError
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import (
    ErrorRecord,
    Lesson,
    LessonEvidence,
    SessionEvaluation,
    SessionRecord,
)
from bsela.memory.store import get_session, list_errors, list_lessons, save_evaluation, save_lesson
from bsela.utils.config import load_models, load_thresholds

_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "all",
        "not",
        "no",
        "any",
        "if",
        "when",
        "before",
        "after",
        "as",
        "than",
        "so",
        "very",
        "also",
        "only",
        "even",
        "just",
    ]
)


def _tokens(text: str) -> frozenset[str]:
    """Lowercase word tokens, stop-words removed."""
    return frozenset(
        w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP_WORDS and len(w) > 2
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _is_duplicate(rule: str, existing: list[Lesson], threshold: float) -> bool:
    """Return True if *rule* is too similar to any existing lesson rule."""
    new_toks = _tokens(rule)
    return any(_jaccard(new_toks, _tokens(lesson.rule)) >= threshold for lesson in existing)


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
    judge_healthy: bool = False

    @property
    def outcome(self) -> str:
        if self.judge_healthy:
            return "judge_healthy"
        if self.persisted:
            return "distilled"
        if self.response.status == "skip":
            return "distiller_skipped"
        if not self.response.lessons:
            return "no_lessons"
        return "duplicates_only"


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
    *,
    replay_harness: bool = False,
) -> str:
    payload: dict[str, object] = {
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
    if replay_harness:
        payload["replay_harness"] = True
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _candidate_to_lesson(
    session_id: str,
    source_error_id: str | None,
    candidate: LessonCandidate,
) -> Lesson:
    return Lesson(
        source_error_id=source_error_id,
        scope=candidate.scope,
        rule=candidate.rule,
        why=candidate.why,
        how_to_apply=candidate.how_to_apply,
        confidence=candidate.confidence,
        status="pending",
    )


def _validated_evidence(
    session: SessionRecord, errors: list[ErrorRecord], candidate: LessonCandidate, line_count: int
) -> tuple[ErrorRecord, tuple[int, int]]:
    """Bind a citation to an actual supplied error, never the first error by default."""
    evidence = candidate.evidence
    span = evidence.get("line_range")
    # An omitted session id inherits the trusted request context for old clients.
    if evidence.get("session_id", session.id) != session.id or not (
        isinstance(span, list)
        and len(span) == 2
        and all(type(n) is int for n in span)
        and 1 <= span[0] <= span[1] <= line_count
    ):
        raise ProviderError("invalid response evidence; no lessons persisted")
    start, end = span
    matches = [
        e
        for e in errors
        if e.session_id == session.id
        and e.line_number is not None
        and start <= e.line_number <= end
    ]
    if not matches:
        raise ProviderError("invalid response evidence: no matching error; no lessons persisted")
    error = min(matches, key=lambda e: (e.line_number or 0, e.id))
    return error, (start, end)


def evaluation_fingerprint(
    session: SessionRecord,
    errors: list[ErrorRecord],
    *,
    client: LLMClient | None = None,
    provider: str = "codex",
    judge_threshold: float = 0.8,
    force_distill: bool = False,
) -> str:
    """Invalidate on content, detector evidence, model, prompt or policy changes.

    Recent lessons are deliberately excluded: new lessons must not cause an
    endless reevaluation cycle. Use --rerun for deliberate reconsideration.
    """
    cfg = load_models()
    payload = {
        "version": 1,
        "session_id": session.id,
        "content_hash": session.content_hash,
        "errors": sorted(
            (_error_payload(error) for error in errors), key=lambda error: str(error["id"])
        ),
        "provider": getattr(client, "provider", provider),
        "model": getattr(client, "model", None),
        "reasoning_effort": getattr(client, "reasoning_effort", None),
        "models": cfg.model_dump(exclude={"default"}),
        "judge_schema": JudgeVerdict.model_json_schema(),
        "distiller_schema": DistillResponse.model_json_schema(),
        "judge_prompt": JUDGE_SYSTEM_PROMPT,
        "distiller_prompt": _find_distiller_prompt(),
        "judge_threshold": judge_threshold,
        "force_distill": force_distill,
        "dedupe_threshold": load_thresholds().dedupe.similarity_threshold,
    }
    # Resolve the same provider defaults for a dry-run as for a real client.
    payload["model"] = payload["model"] or (
        cfg.judge.model if payload["provider"] == "codex" else cfg.deepseek.model
    )
    payload["reasoning_effort"] = payload["reasoning_effort"] or (
        cfg.judge.reasoning_effort if payload["provider"] == "codex" else None
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def distill_session(
    session_id: str,
    *,
    client: LLMClient,
    persist: bool = True,
    force_distill: bool = False,
    recent_lessons: list[Lesson] | None = None,
    replay_harness: bool = False,
    judge_threshold: float = 0.8,
    recent_lessons_limit: int = 10,
) -> DistillationResult:
    """Run judge→distill for one session. Returns the decision trail.

    When ``force_distill`` is true, the judge still runs for telemetry but a
    "healthy" verdict does not short-circuit the distiller call.

    When ``replay_harness`` is true, the JSON payload includes ``replay_harness`` so
    the distiller prompt can treat empty ``recent_lessons`` as intentional for
    replay diffing, not as "no prior lesson context".
    """
    session = get_session(session_id)
    if session is None:
        raise LookupError(f"session not found: {session_id}")

    if session.status == "quarantined":
        raise ProviderError("quarantined session cannot be sent to a provider")
    begin = getattr(client, "begin_session", None)
    if begin is not None:
        begin(session_id)
    errors = list_errors(session_id=session_id, limit=50)
    recent = (
        recent_lessons if recent_lessons is not None else list_lessons(limit=recent_lessons_limit)
    )
    user_payload = _session_payload(session, errors, recent, replay_harness=replay_harness)
    input_hash = evaluation_fingerprint(
        session, errors, client=client, judge_threshold=judge_threshold, force_distill=force_distill
    )

    def complete(result: DistillationResult) -> DistillationResult:
        if persist and not replay_harness:
            save_evaluation(
                SessionEvaluation(
                    input_hash=input_hash, session_id=session.id, outcome=result.outcome
                )
            )
        return result

    verdict = client.judge(system=JUDGE_SYSTEM_PROMPT, user=user_payload)

    healthy = (
        verdict.goal_achieved
        and verdict.confidence >= judge_threshold
        and not verdict.looped
        and not verdict.wasted_tokens
    )
    if healthy and not force_distill:
        return complete(
            DistillationResult(
                session_id=session_id,
                verdict=verdict,
                distilled=False,
                response=DistillResponse(status="skip"),
                persisted=(),
                judge_healthy=True,
            )
        )

    response = client.distill(system=_find_distiller_prompt(), user=user_payload)
    if response.status == "error":
        raise ProviderError("model reported distillation error; no lessons persisted")
    if response.status == "skip":
        return complete(DistillationResult(session_id, verdict, False, response, ()))
    dedup_threshold = load_thresholds().dedupe.similarity_threshold
    persisted: list[Lesson] = []
    if persist:
        # Validate the whole response before writing even its first lesson.
        line_count = 0
        if response.lessons:
            with Path(session.transcript_path).open(encoding="utf-8") as transcript:
                line_count = sum(1 for _ in transcript)
        citations = [
            _validated_evidence(session, errors, candidate, line_count)
            for candidate in response.lessons
        ]
        # Dedupe must always check against the canonical body of approved/applied
        # lessons regardless of recency — otherwise a candidate that duplicates
        # an older approved rule slips through once newer pending rows push it
        # past ``recent_lessons_limit`` (root cause of the 2026-05-09 17/17 dup
        # batch). ``externalized`` rules (graduated into agents-md, ADR 0011) are
        # included too: they have left the drift gate but must still suppress
        # regeneration of a rule that already lives as a durable AGENTS.md entry.
        # Fetched lazily inside this branch to avoid two unbounded DB reads on
        # healthy sessions and ``persist=False`` calls.
        approved_corpus = (
            list_lessons(status="approved", limit=None)
            + list_lessons(status="applied", limit=None)
            + list_lessons(status="externalized", limit=None)
        )
        saved_this_batch: list[Lesson] = list(recent) + list(approved_corpus)
        for candidate, (source_error, (start, end)) in zip(
            response.lessons, citations, strict=True
        ):
            if _is_duplicate(candidate.rule, saved_this_batch, dedup_threshold):
                continue
            lesson = _candidate_to_lesson(session_id, source_error.id, candidate)
            saved = save_lesson(
                lesson,
                evidence=LessonEvidence(
                    lesson_id=lesson.id, session_id=session.id, line_start=start, line_end=end
                ),
            )
            persisted.append(saved)
            saved_this_batch.append(saved)
    else:
        persisted = [_candidate_to_lesson(session_id, None, c) for c in response.lessons]

    return complete(
        DistillationResult(
            session_id=session_id,
            verdict=verdict,
            distilled=True,
            response=response,
            persisted=tuple(persisted),
        )
    )


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "DistillationResult",
    "distill_session",
    "evaluation_fingerprint",
]
