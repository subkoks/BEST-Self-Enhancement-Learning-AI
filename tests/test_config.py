"""P1 tests: config loader validates repo-level thresholds + models TOML."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import bsela.utils.config as _cfg
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


def test_env_override_valid_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover line 99: BSELA_CONFIG_DIR points to a dir containing thresholds.toml."""
    real_config = config_module.find_config_dir()
    shutil.copy(real_config / "thresholds.toml", tmp_path / "thresholds.toml")
    shutil.copy(real_config / "models.toml", tmp_path / "models.toml")
    monkeypatch.setenv("BSELA_CONFIG_DIR", str(tmp_path))
    config_module.clear_cache()
    result = config_module.find_config_dir()
    assert result == tmp_path
    monkeypatch.delenv("BSELA_CONFIG_DIR")
    config_module.clear_cache()


def test_find_config_dir_raises_when_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover line 106: walk up all parents, never find thresholds.toml."""
    monkeypatch.delenv("BSELA_CONFIG_DIR", raising=False)
    # Patch __file__ to point inside tmp_path (no config/ there)
    monkeypatch.setattr(_cfg, "__file__", str(tmp_path / "fake.py"))
    config_module.clear_cache()
    with pytest.raises(FileNotFoundError, match=r"thresholds\.toml"):
        config_module.find_config_dir()
    config_module.clear_cache()


def test_bundled_config_dir_none_in_source_checkout() -> None:
    """No ``bsela/_config`` exists in an editable install / source checkout."""
    assert config_module._bundled_config_dir() is None


def test_bundled_config_dir_none_when_resource_lookup_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resource lookup failure (e.g. namespace package) degrades to None."""

    def _boom(_pkg: str) -> Path:
        raise ModuleNotFoundError("bsela not importable as a resource anchor")

    monkeypatch.setattr(_cfg, "files", _boom)
    assert config_module._bundled_config_dir() is None


def test_find_config_dir_uses_bundled_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wheel case: source-tree walk misses, packaged ``_config`` resolves."""
    real_config = config_module.find_config_dir()
    bundled = tmp_path / "_config"
    bundled.mkdir()
    shutil.copy(real_config / "thresholds.toml", bundled / "thresholds.toml")
    shutil.copy(real_config / "models.toml", bundled / "models.toml")

    monkeypatch.delenv("BSELA_CONFIG_DIR", raising=False)
    # Make the source-tree walk miss (no config/ above tmp_path)...
    monkeypatch.setattr(_cfg, "__file__", str(tmp_path / "pkg" / "fake.py"))
    # ...and make the packaged-resource lookup point at our fake wheel layout.
    monkeypatch.setattr(_cfg, "files", lambda _pkg: tmp_path)
    config_module.clear_cache()

    assert config_module.find_config_dir() == bundled
    config_module.clear_cache()


def test_cached_thresholds_and_models() -> None:
    """Cover lines 124 + 130: cached thresholds() and models() accessors."""
    config_module.clear_cache()
    t = config_module.thresholds()
    assert t.gates.auto_merge_confidence > 0
    m = config_module.models()
    assert m.judge.model
    config_module.clear_cache()
