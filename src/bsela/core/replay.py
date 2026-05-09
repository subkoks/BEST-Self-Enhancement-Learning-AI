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
from bsela.llm.distiller import (
    DistillationResult,
    _jaccard,
    _tokens,
    distill_session,
)
from bsela.memory.models import Lesson, ReplayRecord
from bsela.memory.store import get_session, list_lessons, save_replay_record
from bsela.utils.config import load_thresholds

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
    """Semantic rule-level diff with scope/confidence drift detection.

    Rules are matched via Jaccard token similarity using the same
    ``dedupe.similarity_threshold`` that the distiller applies — so paraphrases
    of the same rule pair as ``unchanged``/``changed`` rather than inflating
    drift with ``+`` and ``-`` rows. First, exact normalised matches are paired
    (cheap and stable); then each remaining stored lesson greedily pairs with
    the most-similar remaining replayed lesson above threshold. Anything left
    over is genuinely added/removed.

    Why: temperature=0 + seed cannot fully stabilise paraphrasing across
    Anthropic (no seed support) and judge non-determinism. Aligning the diff
    metric with the dedupe metric prevents replay drift from firing on noise
    that would have been deduped at persist time anyway.
    """
    threshold = load_thresholds().dedupe.similarity_threshold

    stored_remaining = list(stored)
    replayed_remaining = list(replayed)
    pairs: list[tuple[Lesson, Lesson]] = []

    # Pass 1: exact normalised matches — fast and stable.
    norm_replayed: dict[str, int] = {}
    for idx, r in enumerate(replayed_remaining):
        norm_replayed.setdefault(_normalize(r.rule), idx)
    matched_stored: set[int] = set()
    matched_replayed: set[int] = set()
    for s_idx, s in enumerate(stored_remaining):
        r_idx = norm_replayed.get(_normalize(s.rule))
        if r_idx is not None and r_idx not in matched_replayed:
            pairs.append((s, replayed_remaining[r_idx]))
            matched_stored.add(s_idx)
            matched_replayed.add(r_idx)

    # Pass 2: greedy semantic match on remaining — best Jaccard above threshold.
    leftover_stored = [s for i, s in enumerate(stored_remaining) if i not in matched_stored]
    leftover_replayed_idx = [i for i in range(len(replayed_remaining)) if i not in matched_replayed]
    replayed_used: set[int] = set()
    stored_used: set[int] = set()
    scored: list[tuple[float, int, int]] = []
    for ls_idx, s in enumerate(leftover_stored):
        s_toks = _tokens(s.rule)
        for r_idx in leftover_replayed_idx:
            r = replayed_remaining[r_idx]
            sim = _jaccard(s_toks, _tokens(r.rule))
            if sim >= threshold:
                scored.append((sim, ls_idx, r_idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    for _sim, ls_idx, r_idx in scored:
        if ls_idx in stored_used or r_idx in replayed_used:
            continue
        pairs.append((leftover_stored[ls_idx], replayed_remaining[r_idx]))
        stored_used.add(ls_idx)
        replayed_used.add(r_idx)

    paired_stored = {id(s) for s, _ in pairs}
    paired_replayed = {id(r) for _, r in pairs}

    diffs: list[LessonDiff] = []
    for s, r in pairs:
        scope_drifted = s.scope != r.scope
        conf_drifted = abs(s.confidence - r.confidence) >= _CONFIDENCE_DRIFT_THRESHOLD
        kind: Literal["unchanged", "changed"] = (
            "changed" if (scope_drifted or conf_drifted) else "unchanged"
        )
        diffs.append(LessonDiff(kind, r.rule, r.confidence, r.scope))
    for r in replayed_remaining:
        if id(r) not in paired_replayed:
            diffs.append(LessonDiff("added", r.rule, r.confidence, r.scope))
    for s in stored_remaining:
        if id(s) not in paired_stored:
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
