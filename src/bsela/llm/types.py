"""Typed request / response shapes for the LLM judge + distiller."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JudgeVerdict(BaseModel):
    """Typed rubric score for one session."""

    goal_achieved: bool
    efficiency: float = Field(ge=0.0, le=1.0)
    looped: bool
    wasted_tokens: bool
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str = ""


class LessonCandidate(BaseModel):
    """One distilled lesson candidate. Persisted via ``memory.store.save_lesson``."""

    rule: str
    why: str
    how_to_apply: str
    scope: Literal["project", "global"]
    confidence: float = Field(ge=0.0, le=1.0)
    # Keep the dictionary interface for stored/replayed candidates, but give
    # strict-output providers the concrete evidence shape used by our prompt.
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        json_schema_extra={
            "properties": {
                "session_id": {"type": "string"},
                "line_range": {"type": "array", "items": {"type": "integer"}},
            },
        },
    )


class DistillResponse(BaseModel):
    """Typed distiller response envelope."""

    status: Literal["ok", "skip", "error"] = "ok"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    lessons: list[LessonCandidate] = Field(default_factory=list)


__all__ = ["DistillResponse", "JudgeVerdict", "LessonCandidate"]
