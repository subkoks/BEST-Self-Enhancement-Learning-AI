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


def _pair_exact(
    stored: list[Lesson], replayed: list[Lesson]
) -> tuple[list[tuple[Lesson, Lesson]], set[int], set[int]]:
    """First-pass exact normalised match: cheap and stable."""
    norm_replayed: dict[str, int] = {}
    for idx, r in enumerate(replayed):
        norm_replayed.setdefault(_normalize(r.rule), idx)
    pairs: list[tuple[Lesson, Lesson]] = []
    matched_stored: set[int] = set()
    matched_replayed: set[int] = set()
    for s_idx, s in enumerate(stored):
        r_idx = norm_replayed.get(_normalize(s.rule))
        if r_idx is not None and r_idx not in matched_replayed:
            pairs.append((s, replayed[r_idx]))
            matched_stored.add(s_idx)
            matched_replayed.add(r_idx)
    return pairs, matched_stored, matched_replayed


def _pair_semantic(
    stored: list[Lesson],
    replayed: list[Lesson],
    skip_stored: set[int],
    skip_replayed: set[int],
    threshold: float,
) -> list[tuple[Lesson, Lesson]]:
    """Second-pass: greedy Jaccard match on remaining lessons above ``threshold``."""
    leftover_stored = [(i, s) for i, s in enumerate(stored) if i not in skip_stored]
    leftover_replayed = [(i, r) for i, r in enumerate(replayed) if i not in skip_replayed]
    scored: list[tuple[float, int, int]] = []
    for s_idx, s in leftover_stored:
        s_toks = _tokens(s.rule)
        for r_idx, r in leftover_replayed:
            sim = _jaccard(s_toks, _tokens(r.rule))
            if sim >= threshold:
                scored.append((sim, s_idx, r_idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    used_stored: set[int] = set()
    used_replayed: set[int] = set()
    pairs: list[tuple[Lesson, Lesson]] = []
    for _sim, s_idx, r_idx in scored:
        if s_idx in used_stored or r_idx in used_replayed:
            continue
        pairs.append((stored[s_idx], replayed[r_idx]))
        used_stored.add(s_idx)
        used_replayed.add(r_idx)
    return pairs


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
    exact_pairs, matched_s, matched_r = _pair_exact(stored, replayed)
    semantic_pairs = _pair_semantic(stored, replayed, matched_s, matched_r, threshold)
    pairs = exact_pairs + semantic_pairs

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
    diffs.extend(
        LessonDiff("added", r.rule, r.confidence, r.scope)
        for r in replayed
        if id(r) not in paired_replayed
    )
    diffs.extend(
        LessonDiff("removed", s.rule, s.confidence, s.scope)
        for s in stored
        if id(s) not in paired_stored
    )
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

    If the session already has stored lessons, replay forces distillation even
    when the judge now marks the session as healthy. This keeps replay drift
    focused on lesson stability instead of judge-gating variance.

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
        force_distill=bool(stored),
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
