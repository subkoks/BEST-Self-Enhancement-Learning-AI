"""SQLModel tables for the BSELA memory store.

Five typed tables live in one SQLite database per BSELA home:
    sessions   — raw captured sessions (+ scrubber status)
    errors     — candidate error records produced by the detector
    lessons    — distilled lessons awaiting / applied to agents-md
    decisions  — ADR-style decisions
    metrics    — per-stage cost / latency counters
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SessionRecord(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=_new_id, primary_key=True)
    source: str = Field(index=True)
    transcript_path: str
    content_hash: str = Field(index=True)
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = Field(default=None)
    turn_count: int = Field(default=0)
    tool_call_count: int = Field(default=0)
    tokens_in: int = Field(default=0)
    tokens_out: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    status: str = Field(default="captured", index=True)
    quarantine_reason: str | None = Field(default=None)
    ingested_at: datetime = Field(default_factory=_utcnow, index=True)


class ErrorRecord(SQLModel, table=True):
    __tablename__ = "errors"

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    category: str = Field(index=True)
    severity: str = Field(default="medium")
    snippet: str
    line_number: int | None = Field(default=None)
    detected_at: datetime = Field(default_factory=_utcnow, index=True)


class Lesson(SQLModel, table=True):
    __tablename__ = "lessons"

    id: str = Field(default_factory=_new_id, primary_key=True)
    source_error_id: str | None = Field(default=None, foreign_key="errors.id", index=True)
    scope: str = Field(index=True)
    rule: str
    why: str
    how_to_apply: str
    confidence: float = Field(default=0.0)
    status: str = Field(default="pending", index=True)
    hit_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow)


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"

    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = Field(index=True)
    context: str
    decision: str
    consequences: str
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class Metric(SQLModel, table=True):
    __tablename__ = "metrics"

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str | None = Field(default=None, foreign_key="sessions.id", index=True)
    stage: str = Field(index=True)
    model: str | None = Field(default=None)
    tokens_in: int = Field(default=0)
    tokens_out: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    duration_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


__all__ = [
    "Decision",
    "ErrorRecord",
    "Lesson",
    "Metric",
    "SessionRecord",
]
