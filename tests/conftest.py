"""Shared pytest fixtures for BSELA tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_bsela_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated BSELA home dir per test."""
    home = tmp_path / ".bsela"
    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir()
    (home / "logs").mkdir()
    (home / "reports").mkdir()
    monkeypatch.setenv("BSELA_HOME", str(home))
    return home
