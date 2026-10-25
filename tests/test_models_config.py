"""Explicit supported provider/model defaults, independent of credentials."""

from bsela.utils.config import ModelRole, load_models


def test_roles_use_sol_and_chatgpt_adapter():
    cfg = load_models()
    for value in cfg.__dict__.values():
        if isinstance(value, ModelRole):
            assert value.model == "gpt-6.1-sol"
            assert value.provider == "codex"
            assert value.reasoning_effort == "medium"
    assert cfg.deepseek.model == "deepseek-flash"
    assert cfg.default["live_enabled"] is False
