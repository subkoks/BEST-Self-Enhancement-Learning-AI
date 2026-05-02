"""Typed CRUD wrapper around the SQLite-backed SQLModel store.

The store is keyed by the resolved BSELA home (env ``BSELA_HOME`` or
``~/.bsela``). Engines are cached per DB URL so tests that change
``BSELA_HOME`` get their own isolated SQLite file.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from bsela.memory.models import (
    Decision,
    ErrorRecord,
    Lesson,
    Metric,
    ReplayRecord,
    SessionRecord,
)


def bsela_home() -> Path:
    """Resolve the BSELA home directory (``BSELA_HOME`` env or ``~/.bsela``)."""
    env = os.environ.get("BSELA_HOME")
    return Path(env).expanduser() if env else Path.home() / ".bsela"


def db_path() -> Path:
    """Absolute path to the SQLite database file."""
    return bsela_home() / "bsela.db"


def _db_url() -> str:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


@lru_cache(maxsize=32)
def _engine_for(url: str) -> Engine:
    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: object, _: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine


def get_engine() -> Engine:
    return _engine_for(_db_url())


def reset_engine_cache() -> None:
    """Dispose every cached engine. Intended for tests."""
    for engine in list(_engine_for.__wrapped__.__dict__.values()):
        engine.dispose()
    _engine_for.cache_clear()


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


# ---- Sessions --------------------------------------------------------------


def save_session(record: SessionRecord) -> SessionRecord:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def get_session(session_id: str) -> SessionRecord | None:
    with session_scope() as s:
        return s.get(SessionRecord, session_id)


def resolve_session(id_or_prefix: str) -> SessionRecord | None:
    """Exact match first; if not found, try a prefix LIKE query.

    Returns ``None`` when no match exists. Raises ``LookupError`` when a
    prefix matches more than one row so callers can surface an unambiguous
    error instead of silently picking the first result.
    """
    exact = get_session(id_or_prefix)
    if exact is not None:
        return exact
    stmt = (
        select(SessionRecord)
        .where(SessionRecord.id.like(f"{id_or_prefix}%"))  # type: ignore[attr-defined]
        .limit(2)
    )
    with session_scope() as s:
        rows = list(s.exec(stmt).all())
    if len(rows) > 1:
        raise LookupError(f"ambiguous prefix '{id_or_prefix}': {len(rows)} sessions match")
    return rows[0] if rows else None


def list_sessions(
    *,
    status: str | None = None,
    limit: int | None = 100,
) -> list[SessionRecord]:
    stmt = select(SessionRecord).order_by(SessionRecord.ingested_at.desc())  # type: ignore[attr-defined]
    if status is not None:
        stmt = stmt.where(SessionRecord.status == status)
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


def list_sessions_with_errors(
    *,
    status: str | None = None,
    limit: int | None = 100,
) -> list[SessionRecord]:
    """Return sessions that have at least one ErrorRecord, newest first."""
    stmt = (
        select(SessionRecord)
        .where(SessionRecord.id.in_(select(ErrorRecord.session_id).distinct()))  # type: ignore[attr-defined]
        .order_by(SessionRecord.ingested_at.desc())  # type: ignore[attr-defined]
    )
    if status is not None:
        stmt = stmt.where(SessionRecord.status == status)
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


def count_sessions(*, status: str | None = None) -> int:
    stmt = select(SessionRecord)
    if status is not None:
        stmt = stmt.where(SessionRecord.status == status)
    with session_scope() as s:
        return len(list(s.exec(stmt).all()))


# ---- Errors ----------------------------------------------------------------


def save_error(record: ErrorRecord) -> ErrorRecord:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def list_errors(*, session_id: str | None = None, limit: int | None = 100) -> list[ErrorRecord]:
    stmt = select(ErrorRecord).order_by(ErrorRecord.detected_at.desc())  # type: ignore[attr-defined]
    if session_id is not None:
        stmt = stmt.where(ErrorRecord.session_id == session_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


# ---- Lessons ---------------------------------------------------------------


def save_lesson(record: Lesson) -> Lesson:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def get_lesson(lesson_id: str) -> Lesson | None:
    with session_scope() as s:
        return s.get(Lesson, lesson_id)


def resolve_lesson(id_or_prefix: str) -> Lesson | None:
    """Exact match first; if not found, try a prefix LIKE query.

    Returns ``None`` when no match exists. Raises ``LookupError`` when a
    prefix matches more than one row.
    """
    exact = get_lesson(id_or_prefix)
    if exact is not None:
        return exact
    stmt = (
        select(Lesson)
        .where(Lesson.id.like(f"{id_or_prefix}%"))  # type: ignore[attr-defined]
        .limit(2)
    )
    with session_scope() as s:
        rows = list(s.exec(stmt).all())
    if len(rows) > 1:
        raise LookupError(f"ambiguous prefix '{id_or_prefix}': {len(rows)} lessons match")
    return rows[0] if rows else None


def update_lesson_status(
    lesson_id: str,
    *,
    status: str,
    note: str | None = None,
) -> Lesson:
    """Transition a lesson to a new status. Returns the refreshed row.

    ``note`` is appended to ``how_to_apply`` under a ``-- review note --``
    delimiter so reviewer context survives without a separate column.
    """
    with session_scope() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise LookupError(f"lesson not found: {lesson_id}")
        lesson.status = status
        lesson.updated_at = datetime.now(UTC)
        if note:
            lesson.how_to_apply = f"{lesson.how_to_apply}\n\n-- review note --\n{note}"
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        return lesson


def increment_hit_count(lesson_ids: list[str]) -> None:
    """Atomically bump hit_count on each lesson in lesson_ids.

    Silently skips IDs that no longer exist. Intended to be called whenever
    lessons are surfaced to an editor (MCP bsela_lessons, route context).
    """
    if not lesson_ids:
        return
    with session_scope() as s:
        for lid in lesson_ids:
            lesson = s.get(Lesson, lid)
            if lesson is not None:
                lesson.hit_count += 1
                lesson.updated_at = datetime.now(UTC)
                s.add(lesson)
        s.commit()


def list_lessons(
    *,
    status: str | None = None,
    scope: str | None = None,
    session_id: str | None = None,
    limit: int | None = 100,
) -> list[Lesson]:
    stmt = select(Lesson).order_by(Lesson.created_at.desc())  # type: ignore[attr-defined]
    if status is not None:
        stmt = stmt.where(Lesson.status == status)
    if scope is not None:
        stmt = stmt.where(Lesson.scope == scope)
    if session_id is not None:
        stmt = stmt.join(ErrorRecord, Lesson.source_error_id == ErrorRecord.id).where(  # type: ignore[arg-type]
            ErrorRecord.session_id == session_id
        )
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


def count_lessons(*, status: str | None = None) -> int:
    stmt = select(Lesson)
    if status is not None:
        stmt = stmt.where(Lesson.status == status)
    with session_scope() as s:
        return len(list(s.exec(stmt).all()))


def session_has_lessons(session_id: str) -> bool:
    """Return True iff any Lesson exists whose source_error_id is from this session."""
    stmt = (
        select(Lesson.id)
        .join(ErrorRecord, Lesson.source_error_id == ErrorRecord.id)  # type: ignore[arg-type]
        .where(ErrorRecord.session_id == session_id)
        .limit(1)
    )
    with session_scope() as s:
        return s.exec(stmt).first() is not None


# ---- Decisions -------------------------------------------------------------


def save_decision(record: Decision) -> Decision:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def list_decisions(*, limit: int | None = 100) -> list[Decision]:
    stmt = select(Decision).order_by(Decision.created_at.desc())  # type: ignore[attr-defined]
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


# ---- Metrics ---------------------------------------------------------------


def save_metric(record: Metric) -> Metric:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def list_metrics(
    *,
    session_id: str | None = None,
    stage: str | None = None,
    limit: int | None = 100,
) -> list[Metric]:
    stmt = select(Metric).order_by(Metric.created_at.desc())  # type: ignore[attr-defined]
    if session_id is not None:
        stmt = stmt.where(Metric.session_id == session_id)
    if stage is not None:
        stmt = stmt.where(Metric.stage == stage)
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


# ---- Replay records --------------------------------------------------------


def save_replay_record(record: ReplayRecord) -> ReplayRecord:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
    return record


def list_replay_records(
    *,
    window_days: int | None = None,
    limit: int | None = 100,
) -> list[ReplayRecord]:
    stmt = select(ReplayRecord).order_by(ReplayRecord.replayed_at.desc())  # type: ignore[attr-defined]
    if window_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        stmt = stmt.where(ReplayRecord.replayed_at >= cutoff)
    if limit is not None:
        stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


__all__ = [
    "bsela_home",
    "count_lessons",
    "count_sessions",
    "db_path",
    "get_engine",
    "get_lesson",
    "get_session",
    "list_decisions",
    "list_errors",
    "list_lessons",
    "list_metrics",
    "list_replay_records",
    "list_sessions",
    "list_sessions_with_errors",
    "reset_engine_cache",
    "resolve_lesson",
    "resolve_session",
    "save_decision",
    "save_error",
    "save_lesson",
    "save_metric",
    "save_replay_record",
    "save_session",
    "session_has_lessons",
    "session_scope",
    "update_lesson_status",
]
