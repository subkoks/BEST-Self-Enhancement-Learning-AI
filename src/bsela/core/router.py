"""Task → model router for BSELA.

Pure function: given a task description and the loaded ``ModelsConfig``,
decide which task class applies and which model should handle it. No
network, no LLM calls, no store access — this is v1 of the router and
is explicitly keyword-based so it can run offline and is trivially
testable.

The router is the single seam where "what kind of work is this?" gets
answered. Adapters (Claude Code, Codex, Cursor, Windsurf, MCP) call it
to pick a model before dispatching. The v2 upgrade path (Haiku-scored
classifier prompt) is documented in ADR 0005; no ADR is required to
tune keyword buckets in this module.

Design invariants (AGENTS.md "Haiku-first pipeline"):

* Default to Haiku unless the task explicitly signals planning,
  architecture, auditing, or a tricky root-cause debug.
* Opus 4.7 is reserved for ``planner`` / ``auditor`` / ``debugger`` /
  ``distiller`` classes — i.e. low-confidence or high-leverage work.
* Sonnet 4.6 covers bulk builds and research.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from bsela.utils.config import ModelRole, ModelsConfig, load_models

DEFAULT_CLASS: Final[str] = "builder"


@dataclass(frozen=True)
class RouteDecision:
    """Outcome of routing a task to a model."""

    task_class: str
    model: str
    reason: str
    confidence: float
    matched_keywords: tuple[str, ...]


# Keyword buckets → task class. Ordered from most specific to least.
# First bucket whose pattern matches wins; ties broken by order here.
_BUCKETS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "planner",
        (
            "plan",
            "design",
            "architect",
            "architecture",
            "roadmap",
            "trade-off",
            "tradeoff",
            "phased",
            "strategy",
            "spec out",
        ),
    ),
    (
        "auditor",
        (
            "audit",
            "weekly digest",
            "drift",
            "compliance review",
            "full codebase review",
            "security posture",
        ),
    ),
    (
        "debugger",
        (
            "root cause",
            "root-cause",
            "why is this failing",
            "diagnose",
            "triage",
            "crash",
            "stack trace",
            "flaky test",
            "regression",
        ),
    ),
    (
        "distiller",
        (
            "distill",
            "extract lesson",
            "summarize failure",
            "write adr",
            "draft adr",
        ),
    ),
    (
        "reviewer",
        (
            "review this diff",
            "pr review",
            "pre-commit",
            "lint check",
            "style review",
            "code review",
        ),
    ),
    (
        "researcher",
        (
            "research",
            "investigate",
            "compare libraries",
            "find documentation",
            "survey",
            "benchmark",
        ),
    ),
    (
        "memory_updater",
        (
            "dedupe",
            "merge memory",
            "consolidate notes",
            "update memory",
        ),
    ),
    (
        "judge",
        (
            "score",
            "rate confidence",
            "classify sentiment",
            "quick scoring",
        ),
    ),
    (
        "builder",
        (
            "build",
            "scaffold",
            "implement",
            "write the function",
            "add feature",
            "refactor",
            "port",
            "wire up",
            "hook up",
            "rename",
        ),
    ),
)


def _compile(keywords: tuple[str, ...]) -> re.Pattern[str]:
    escaped = "|".join(re.escape(k) for k in keywords)
    # Word-ish boundaries: require non-letter before/after so "plan" does not
    # match inside "plantain". Hyphens count as part of the token.
    return re.compile(rf"(?<![A-Za-z])({escaped})(?![A-Za-z])", re.IGNORECASE)


_COMPILED: Final[tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...]] = tuple(
    (name, _compile(keywords), keywords) for name, keywords in _BUCKETS
)


def classify(task: str, models: ModelsConfig | None = None) -> RouteDecision:
    """Route a task description to a class + model.

    Args:
        task: Free-form task description (the first user message, a PR
            title, a ticket summary, etc.). Empty / whitespace-only
            input falls through to ``DEFAULT_CLASS``.
        models: Loaded ``ModelsConfig``. ``None`` → ``load_models()``.

    Returns:
        A ``RouteDecision``. ``confidence`` is a coarse proxy:
        ``1.0`` when at least one unique keyword matched the winning
        bucket, ``0.5`` for the fallthrough default.
    """
    cfg = models or load_models()
    stripped = task.strip()
    if not stripped:
        return _default(cfg, reason="empty task — fell through to default")

    matches: list[tuple[str, tuple[str, ...]]] = []
    for name, pattern, _keywords in _COMPILED:
        found = tuple(sorted({m.group(1).lower() for m in pattern.finditer(stripped)}))
        if found:
            matches.append((name, found))

    if not matches:
        return _default(cfg, reason="no keyword bucket matched")

    # Pick the most-specific bucket: most unique matches wins, ties broken
    # by order (earlier buckets are more specific by construction).
    matches.sort(key=lambda item: (-len(item[1]), _bucket_index(item[0])))
    winner, keywords = matches[0]
    role = _role_for(cfg, winner)
    return RouteDecision(
        task_class=winner,
        model=role.model,
        reason=f"matched '{winner}' bucket via {', '.join(keywords)}",
        confidence=1.0,
        matched_keywords=keywords,
    )


def _default(cfg: ModelsConfig, *, reason: str) -> RouteDecision:
    role = _role_for(cfg, DEFAULT_CLASS)
    return RouteDecision(
        task_class=DEFAULT_CLASS,
        model=role.model,
        reason=reason,
        confidence=0.5,
        matched_keywords=(),
    )


def _bucket_index(name: str) -> int:
    for i, (bucket_name, _pattern, _keywords) in enumerate(_COMPILED):
        if bucket_name == name:
            return i
    return len(_COMPILED)


def _role_for(cfg: ModelsConfig, task_class: str) -> ModelRole:
    try:
        role = getattr(cfg, task_class)
    except AttributeError as exc:
        raise ValueError(f"models.toml has no role named {task_class!r}") from exc
    if not isinstance(role, ModelRole):
        raise ValueError(f"{task_class!r} in models.toml is not a ModelRole")
    return role


__all__ = ["DEFAULT_CLASS", "RouteDecision", "classify"]
