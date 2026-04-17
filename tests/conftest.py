"""Shared pytest fixtures for BSELA tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from bsela.memory import store as memory_store
from bsela.utils import config as config_module

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


@pytest.fixture
def tmp_bsela_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolated BSELA home dir per test."""
    home = tmp_path / ".bsela"
    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir()
    (home / "logs").mkdir()
    (home / "reports").mkdir()
    monkeypatch.setenv("BSELA_HOME", str(home))
    memory_store._engine_for.cache_clear()
    config_module.clear_cache()
    yield home
    memory_store._engine_for.cache_clear()
    config_module.clear_cache()


@pytest.fixture
def sample_clean_session() -> Path:
    return FIXTURES / "clean.jsonl"


@pytest.fixture
def sample_leaked_session() -> Path:
    return FIXTURES / "leaked-aws-key.jsonl"
