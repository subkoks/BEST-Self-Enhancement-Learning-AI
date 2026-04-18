"""P3 tests: auto-merge gate decisions for distilled lessons."""

from __future__ import annotations

from bsela.core.gate import evaluate, touches_safety
from bsela.memory.models import Lesson
from bsela.utils.config import (
    AuditConfig,
    CostConfig,
    DedupeConfig,
    DetectorConfig,
    GatesConfig,
    RetentionConfig,
    ScrubberConfig,
    Thresholds,
)


def _thresholds(
    *,
    auto_merge_confidence: float = 0.9,
    global_rules_require_review: bool = True,
    safety_rules_require_review: bool = True,
) -> Thresholds:
    return Thresholds(
        gates=GatesConfig(
            auto_merge_confidence=auto_merge_confidence,
            global_rules_require_review=global_rules_require_review,
            safety_rules_require_review=safety_rules_require_review,
        ),
        detector=DetectorConfig(loop_threshold=3, retry_threshold=4, correction_markers=["stop"]),
        dedupe=DedupeConfig(similarity_threshold=0.85, max_global_lessons=200),
        cost=CostConfig(monthly_budget_usd=50.0, per_session_budget_usd=0.1),
        retention=RetentionConfig(session_days=90, error_days=90),
        audit=AuditConfig(digest_day=0, drift_alarm_threshold=0.5),
        scrubber=ScrubberConfig(patterns=[]),
    )


def _lesson(
    *,
    scope: str = "project",
    rule: str = "Stop retrying the same Read on ENOENT",
    why: str = "Loop detector flagged repeated Reads",
    how_to_apply: str = "After two ENOENTs on the same path, change strategy",
    confidence: float = 0.95,
) -> Lesson:
    return Lesson(
        scope=scope,
        rule=rule,
        why=why,
        how_to_apply=how_to_apply,
        confidence=confidence,
    )


def test_project_scope_high_confidence_auto_merges() -> None:
    decision = evaluate(_lesson(), _thresholds())
    assert decision.auto_merge is True
    assert decision.requires_review is False
    assert decision.safety_flag is False


def test_global_scope_always_requires_review() -> None:
    decision = evaluate(_lesson(scope="global", confidence=1.0), _thresholds())
    assert decision.auto_merge is False
    assert decision.requires_review is True
    assert "global-scope" in decision.reason


def test_low_confidence_requires_review() -> None:
    decision = evaluate(_lesson(confidence=0.5), _thresholds())
    assert decision.auto_merge is False
    assert decision.requires_review is True
    assert "confidence" in decision.reason


def test_safety_keyword_blocks_auto_merge() -> None:
    sensitive = _lesson(
        rule="Never skip signing confirmation on a wallet transfer",
        why="Prevents accidental fund loss",
        how_to_apply="Always confirm before a wallet transfer",
        confidence=0.99,
    )
    decision = evaluate(sensitive, _thresholds())
    assert decision.auto_merge is False
    assert decision.requires_review is True
    assert decision.safety_flag is True


def test_safety_flag_off_allows_auto_merge() -> None:
    sensitive = _lesson(
        rule="Never skip signing confirmation on a wallet transfer",
        confidence=0.99,
    )
    decision = evaluate(
        sensitive,
        _thresholds(safety_rules_require_review=False),
    )
    assert decision.auto_merge is True
    assert decision.safety_flag is False


def test_touches_safety_is_case_insensitive_and_word_bounded() -> None:
    assert touches_safety(_lesson(rule="Block API KEY leaks at capture")) is True
    assert touches_safety(_lesson(rule="Refactor helper for readability")) is False
