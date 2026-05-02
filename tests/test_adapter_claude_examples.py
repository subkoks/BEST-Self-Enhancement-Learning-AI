"""Guardrail: Claude adapter example JSON must stay parseable."""

from __future__ import annotations

import json
from pathlib import Path


def test_claude_adapter_example_json_parses() -> None:
    root = Path(__file__).resolve().parents[1] / "adapters" / "claude"
    for name in ("settings.example.json", "settings.local.example.json"):
        raw = (root / name).read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)
