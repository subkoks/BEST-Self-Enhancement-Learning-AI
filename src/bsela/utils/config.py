"""Load + validate BSELA config files (``thresholds.toml``, ``models.toml``).

Discovery order:
    1. ``BSELA_CONFIG_DIR`` env var (explicit override).
    2. Walk up from this module until a ``config/thresholds.toml`` is found.
"""

from __future__ import annotations

import os
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GatesConfig(BaseModel):
    auto_merge_confidence: float
    global_rules_require_review: bool
    safety_rules_require_review: bool


class DetectorConfig(BaseModel):
    loop_threshold: int
    retry_threshold: int
    correction_markers: list[str]


class DedupeConfig(BaseModel):
    similarity_threshold: float
    max_global_lessons: int


class CostConfig(BaseModel):
    monthly_budget_usd: float
    per_session_budget_usd: float


class RetentionConfig(BaseModel):
    session_days: int
    error_days: int


class AuditConfig(BaseModel):
    digest_day: int
    drift_alarm_threshold: float


class ScrubberConfig(BaseModel):
    patterns: list[str]


class Thresholds(BaseModel):
    gates: GatesConfig
    detector: DetectorConfig
    dedupe: DedupeConfig
    cost: CostConfig
    retention: RetentionConfig
    audit: AuditConfig
    scrubber: ScrubberConfig


class ModelRole(BaseModel):
    model: str
    max_tokens: int
    temperature: float = Field(default=0.0)


class ModelsConfig(BaseModel):
    default: dict[str, Any]
    judge: ModelRole
    distiller: ModelRole
    planner: ModelRole
    builder: ModelRole
    reviewer: ModelRole
    researcher: ModelRole
    auditor: ModelRole
    debugger: ModelRole
    memory_updater: ModelRole


def find_config_dir() -> Path:
    env = os.environ.get("BSELA_CONFIG_DIR")
    if env:
        p = Path(env).expanduser()
        if (p / "thresholds.toml").is_file():
            return p
        raise FileNotFoundError(f"BSELA_CONFIG_DIR={p!s} does not contain thresholds.toml")
    here = Path(__file__).resolve().parent
    for parent in (here, *here.parents):
        candidate = parent / "config"
        if (candidate / "thresholds.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not locate config/thresholds.toml. Set BSELA_CONFIG_DIR.")


def load_thresholds(config_dir: Path | None = None) -> Thresholds:
    cfg_dir = config_dir or find_config_dir()
    data = tomllib.loads((cfg_dir / "thresholds.toml").read_text(encoding="utf-8"))
    return Thresholds.model_validate(data)


def load_models(config_dir: Path | None = None) -> ModelsConfig:
    cfg_dir = config_dir or find_config_dir()
    data = tomllib.loads((cfg_dir / "models.toml").read_text(encoding="utf-8"))
    return ModelsConfig.model_validate(data)


@cache
def thresholds() -> Thresholds:
    """Cached default-config accessor."""
    return load_thresholds()


@cache
def models() -> ModelsConfig:
    """Cached default-config accessor."""
    return load_models()


def clear_cache() -> None:
    thresholds.cache_clear()
    models.cache_clear()


__all__ = [
    "AuditConfig",
    "CostConfig",
    "DedupeConfig",
    "DetectorConfig",
    "GatesConfig",
    "ModelRole",
    "ModelsConfig",
    "RetentionConfig",
    "ScrubberConfig",
    "Thresholds",
    "clear_cache",
    "find_config_dir",
    "load_models",
    "load_thresholds",
    "models",
    "thresholds",
]
