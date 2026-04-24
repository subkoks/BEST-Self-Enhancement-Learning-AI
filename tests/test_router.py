"""P5 router: keyword-based task → model classifier."""

from __future__ import annotations

import pytest

from bsela.core.router import DEFAULT_CLASS, RouteDecision, classify
from bsela.utils.config import ModelsConfig, load_models


@pytest.fixture(scope="module")
def models() -> ModelsConfig:
    return load_models()


def test_empty_task_falls_through_to_default(models: ModelsConfig) -> None:
    decision = classify("", models)
    assert isinstance(decision, RouteDecision)
    assert decision.task_class == DEFAULT_CLASS
    assert decision.confidence == 0.5
    assert decision.matched_keywords == ()
    assert "empty" in decision.reason.lower()


def test_whitespace_task_falls_through_to_default(models: ModelsConfig) -> None:
    decision = classify("   \n\t", models)
    assert decision.task_class == DEFAULT_CLASS
    assert decision.confidence == 0.5


def test_planning_task_routes_to_planner_opus(models: ModelsConfig) -> None:
    decision = classify("plan the P5 rollout and call out trade-offs", models)
    assert decision.task_class == "planner"
    assert decision.model == models.planner.model
    assert "plan" in decision.matched_keywords
    assert decision.confidence == 1.0


def test_audit_task_routes_to_auditor(models: ModelsConfig) -> None:
    decision = classify("run the weekly audit and flag drift", models)
    assert decision.task_class == "auditor"
    assert decision.model == models.auditor.model


def test_debug_task_routes_to_debugger(models: ModelsConfig) -> None:
    decision = classify("find the root cause of the flaky test", models)
    assert decision.task_class == "debugger"
    assert decision.model == models.debugger.model


def test_refactor_task_routes_to_builder(models: ModelsConfig) -> None:
    decision = classify("refactor the updater to accept multiple repos", models)
    assert decision.task_class == "builder"
    assert decision.model == models.builder.model


def test_pr_review_task_routes_to_reviewer_haiku(models: ModelsConfig) -> None:
    decision = classify("pr review: style pass on hook_install.py", models)
    assert decision.task_class == "reviewer"
    assert decision.model == models.reviewer.model


def test_research_task_routes_to_researcher(models: ModelsConfig) -> None:
    decision = classify("investigate which sqlite FTS extension to use", models)
    assert decision.task_class == "researcher"
    assert decision.model == models.researcher.model


def test_distill_task_routes_to_distiller(models: ModelsConfig) -> None:
    decision = classify("distill this failure into a durable lesson", models)
    assert decision.task_class == "distiller"
    assert decision.model == models.distiller.model


def test_unknown_task_falls_back_to_builder(models: ModelsConfig) -> None:
    decision = classify("make the thing go", models)
    assert decision.task_class == DEFAULT_CLASS
    assert decision.confidence == 0.5
    assert decision.matched_keywords == ()


def test_word_boundaries_prevent_false_positives(models: ModelsConfig) -> None:
    # "plan" inside "plantain" must not match the planner bucket.
    decision = classify("write a recipe for plantain bread", models)
    assert decision.task_class == DEFAULT_CLASS


def test_multiple_matches_most_specific_wins(models: ModelsConfig) -> None:
    # "plan" + "refactor" both hit buckets. Most matches in a single bucket
    # wins; ties broken by bucket order (planner before builder).
    decision = classify("plan the refactor and design the phases", models)
    assert decision.task_class == "planner"
    assert "plan" in decision.matched_keywords
    assert "design" in decision.matched_keywords


def test_case_insensitive(models: ModelsConfig) -> None:
    decision = classify("AUDIT the codebase", models)
    assert decision.task_class == "auditor"


def test_default_models_are_loaded_when_cfg_omitted() -> None:
    # Calling without passing an explicit ModelsConfig should still work.
    decision = classify("plan the migration")
    assert decision.task_class == "planner"
    assert decision.model  # some non-empty model id
