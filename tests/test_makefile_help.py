"""Makefile help stays in sync with declared targets (distilled lesson: Make targets)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_make_help_lists_core_targets() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        ["make", "help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for name in ("check", "doctor", "mcp-check", "mcp-parity"):
        assert name in out, f"expected make help to mention {name!r}"
