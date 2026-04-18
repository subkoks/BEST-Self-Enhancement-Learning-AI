"""Auto-merge gate for distilled lessons.

Pure function: given a ``Lesson`` row and the loaded ``Thresholds``,
decide whether the lesson is eligible for auto-merge on the
``agents-md`` proposal branch or must route through human review.

The rules mirror the Safety Gates section of the project ``AGENTS.md``:

* ``scope == "global"``              → always human review
* safety / crypto / wallet / trading → always human review
* ``confidence < auto_merge_conf``   → always human review
* otherwise                          → auto-merge eligible
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bsela.memory.models import Lesson
from bsela.utils.config import Thresholds

SAFETY_KEYWORDS: tuple[str, ...] = (
    "crypto",
    "wallet",
    "private key",
    "seed phrase",
    "trading",
    "trade execution",
    "signing",
    "sign transaction",
    "rpc credential",
    "api key",
    "secret",
    "credential",
    "destructive",
    "force push",
    "hard reset",
)

_SAFETY_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in SAFETY_KEYWORDS) + r")\b", re.I)


@dataclass(frozen=True)
class GateDecision:
    """Outcome of evaluating a lesson against the auto-merge gates."""

    auto_merge: bool
    requires_review: bool
    reason: str
    safety_flag: bool = False


def touches_safety(lesson: Lesson) -> bool:
    """True if the lesson text mentions a safety-sensitive keyword."""
    blob = f"{lesson.rule}\n{lesson.why}\n{lesson.how_to_apply}"
    return bool(_SAFETY_RE.search(blob))


def evaluate(lesson: Lesson, thresholds: Thresholds) -> GateDecision:
    """Return the gate decision for ``lesson`` under ``thresholds``."""
    gates = thresholds.gates

    if lesson.scope == "global" and gates.global_rules_require_review:
        return GateDecision(
            auto_merge=False,
            requires_review=True,
            reason="global-scope lessons require human review",
        )

    if gates.safety_rules_require_review and touches_safety(lesson):
        return GateDecision(
            auto_merge=False,
            requires_review=True,
            reason="touches safety / crypto / wallet / trading; review required",
            safety_flag=True,
        )

    if lesson.confidence < gates.auto_merge_confidence:
        return GateDecision(
            auto_merge=False,
            requires_review=True,
            reason=(
                f"confidence {lesson.confidence:.2f} < "
                f"auto_merge_confidence {gates.auto_merge_confidence:.2f}"
            ),
        )

    return GateDecision(
        auto_merge=True,
        requires_review=False,
        reason="project scope, safe keywords, confidence clears threshold",
    )


__all__ = ["SAFETY_KEYWORDS", "GateDecision", "evaluate", "touches_safety"]
