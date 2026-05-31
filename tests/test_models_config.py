"""Guard: every Anthropic model configured in ``models.toml`` is current/active.

Fails when a role points at a retired/deprecated model or an unknown id, so a
future Anthropic retirement (or a typo) breaks CI instead of production. Update
``CURRENT_ANTHROPIC_MODELS`` deliberately when adopting a new model. Source of
truth: https://platform.claude.com/docs/en/about-claude/model-deprecations
"""

from __future__ import annotations

from bsela.utils.config import ModelRole, load_models

# Active Anthropic model ids (checked 2026-05-31). Add ids here when adopting them.
CURRENT_ANTHROPIC_MODELS = frozenset(
    {
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-opus-4-5-20251101",
        "claude-opus-4-1",
        "claude-opus-4-1-20250805",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
    }
)

# Known retired/deprecated ids that must never appear in models.toml.
RETIRED_ANTHROPIC_MODELS = frozenset(
    {
        "claude-opus-4-0",
        "claude-opus-4-20250514",
        "claude-sonnet-4-0",
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    }
)

_ROLE_FIELDS = (
    "judge",
    "distiller",
    "planner",
    "builder",
    "reviewer",
    "researcher",
    "auditor",
    "debugger",
    "memory_updater",
)


def _configured_anthropic_models() -> dict[str, str]:
    cfg = load_models()
    models: dict[str, str] = {}
    for field in _ROLE_FIELDS:
        role = getattr(cfg, field)
        assert isinstance(role, ModelRole)
        models[field] = role.model
    return models


def test_every_role_uses_a_current_anthropic_model() -> None:
    stale = {
        role: model
        for role, model in _configured_anthropic_models().items()
        if model not in CURRENT_ANTHROPIC_MODELS
    }
    assert not stale, (
        f"models.toml roles point at non-current models: {stale}. Bump them or "
        "update CURRENT_ANTHROPIC_MODELS after checking the model-deprecations page."
    )


def test_no_role_uses_a_retired_model() -> None:
    retired = {
        role: model
        for role, model in _configured_anthropic_models().items()
        if model in RETIRED_ANTHROPIC_MODELS
    }
    assert not retired, f"models.toml roles point at retired models: {retired}"
