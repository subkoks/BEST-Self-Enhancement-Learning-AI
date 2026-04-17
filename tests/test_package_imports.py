"""P0 smoke tests: all subpackages import cleanly."""

from __future__ import annotations

import importlib

import bsela


def test_subpackages_import() -> None:
    for module in (
        "bsela",
        "bsela.cli",
        "bsela.core",
        "bsela.memory",
        "bsela.llm",
        "bsela.adapters",
        "bsela.utils",
    ):
        importlib.import_module(module)


def test_version_exported() -> None:
    assert isinstance(bsela.__version__, str)
    assert bsela.__version__.count(".") == 2
