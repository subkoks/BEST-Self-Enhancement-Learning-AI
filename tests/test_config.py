"""P1 tests: config loader validates repo-level thresholds + models TOML."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsela.utils import config as config_module


def test_load_thresholds_defaults() -> None:
    t = config_module.load_thresholds()
    assert 0.0 < t.gates.auto_merge_confidence <= 1.0
    assert t.detector.loop_threshold > 0
    assert t.detector.correction_markers
    assert any("AKIA" in p for p in t.scrubber.patterns)


def test_load_models_defaults() -> None:
    m = config_module.load_models()
    assert m.judge.model.startswith("claude-")
    assert m.distiller.model.startswith("claude-")


def test_env_override_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BSELA_CONFIG_DIR", str(tmp_path))
    config_module.clear_cache()
    with pytest.raises(FileNotFoundError):
        config_module.load_thresholds()
    monkeypatch.delenv("BSELA_CONFIG_DIR")
    config_module.clear_cache()
