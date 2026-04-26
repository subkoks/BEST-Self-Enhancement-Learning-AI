"""Replay harness — P7 foundation.

Re-runs the detector+distiller pipeline on a previously captured session
without persisting the result, then diffs the candidate lessons against
whatever lessons are already stored for that session.

The diff is the signal: if the same session produces different lessons
after a rule/prompt change, that's drift. The harness surfaces it so the
operator can decide whether the drift is intentional improvement or
regression.

Usage:
    result = replay_session(session_id, client=llm_client)
    print(result.summary())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bsela.llm.client import LLMClient
from bsela.llm.distiller import DistillationResult, distill_session
from bsela.memory.models import Lesson, ReplayRecord
from bsela.memory.store import get_session, list_lessons, save_replay_record

_CONFIDENCE_DRIFT_THRESHOLD = 0.1


@dataclass(frozen=True)
class LessonDiff:
    """One entry in the diff between stored and replayed lessons."""

    kind: Literal["added", "removed", "unchanged", "changed"]
    rule: str
    confidence: float
    scope: str


@dataclass(frozen=True)
class ReplayResult:
    """Full replay outcome for one session."""

    session_id: str
    distilled: bool
    stored_lessons: tuple[Lesson, ...]
    replayed_lessons: tuple[Lesson, ...]
    diff: tuple[LessonDiff, ...]

    def summary(self) -> str:
        if not self.distilled:
            return f"session {self.session_id}: judge rated healthy — no lessons produced"
        added = [d for d in self.diff if d.kind == "added"]
        removed = [d for d in self.diff if d.kind == "removed"]
        changed = [d for d in self.diff if d.kind == "changed"]
        unchanged = [d for d in self.diff if d.kind == "unchanged"]
        parts = [f"session {self.session_id}: replay diff"]
        parts.append(
            f"  stored={len(self.stored_lessons)}"
            f"  replayed={len(self.replayed_lessons)}"
            f"  +{len(added)} -{len(removed)} ~{len(changed)} ={len(unchanged)}"
        )
        for d in self.diff:
            prefix = {"added": "+", "removed": "-", "unchanged": "=", "changed": "~"}[d.kind]
            parts.append(f"  {prefix} [{d.scope}] {d.rule} (conf={d.confidence:.2f})")
        return "\n".join(parts)


def _normalize(rule: str) -> str:
    """Lowercase + collapse whitespace so minor formatting changes don't inflate diffs."""
    return " ".join(rule.lower().split())


def _diff_lessons(
    stored: list[Lesson],
    replayed: list[Lesson],
) -> tuple[LessonDiff, ...]:
    """Rule-level diff with scope/confidence drift detection.

    Rules are matched on normalised text. When a rule matches, scope or a
    confidence delta ≥ _CONFIDENCE_DRIFT_THRESHOLD produces "changed" rather
    than "unchanged", so safety-gate-affecting replay differences surface.
    """
    stored_rules = {_normalize(s.rule): s for s in stored}
    replayed_rules = {_normalize(r.rule): r for r in replayed}

    diffs: list[LessonDiff] = []
    all_keys = stored_rules.keys() | replayed_rules.keys()
    for key in sorted(all_keys):
        if key in stored_rules and key in replayed_rules:
            s = stored_rules[key]
            r = replayed_rules[key]
            scope_drifted = s.scope != r.scope
            conf_drifted = abs(s.confidence - r.confidence) >= _CONFIDENCE_DRIFT_THRESHOLD
            kind: Literal["unchanged", "changed"] = (
                "changed" if (scope_drifted or conf_drifted) else "unchanged"
            )
            diffs.append(LessonDiff(kind, r.rule, r.confidence, r.scope))
        elif key in replayed_rules:
            r = replayed_rules[key]
            diffs.append(LessonDiff("added", r.rule, r.confidence, r.scope))
        else:
            s = stored_rules[key]
            diffs.append(LessonDiff("removed", s.rule, s.confidence, s.scope))
    return tuple(diffs)


def replay_session(
    session_id: str,
    *,
    client: LLMClient,
    persist_result: bool = True,
) -> ReplayResult:
    """Re-distill a stored session without persisting; diff against current lessons.

    When ``persist_result`` is True (the default), the diff summary is written
    to the ``replay_records`` table so ``bsela audit`` can compute a drift rate
    over a rolling window without re-invoking the LLM.

    Raises ``LookupError`` if ``session_id`` is not in the store.
    """
    session = get_session(session_id)
    if session is None:
        raise LookupError(f"session not found: {session_id}")

    stored = list_lessons(session_id=session_id, limit=None)

    result: DistillationResult = distill_session(
        session_id,
        client=client,
        persist=False,
    )

    replayed = list(result.persisted)
    diff = _diff_lessons(stored, replayed)

    replay_result = ReplayResult(
        session_id=session_id,
        distilled=result.distilled,
        stored_lessons=tuple(stored),
        replayed_lessons=tuple(replayed),
        diff=diff,
    )

    if persist_result:
        added = sum(1 for d in diff if d.kind == "added")
        removed = sum(1 for d in diff if d.kind == "removed")
        changed = sum(1 for d in diff if d.kind == "changed")
        unchanged = sum(1 for d in diff if d.kind == "unchanged")
        save_replay_record(
            ReplayRecord(
                session_id=session_id,
                had_drift=(added + removed + changed) > 0,
                added_count=added,
                removed_count=removed,
                changed_count=changed,
                unchanged_count=unchanged,
            )
        )

    return replay_result


__all__ = [
    "LessonDiff",
    "ReplayRecord",
    "ReplayResult",
    "replay_session",
]
