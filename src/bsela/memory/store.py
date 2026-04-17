"""Typed CRUD wrapper around the SQLite-backed SQLModel store.

The store is keyed by the resolved BSELA home (env ``BSELA_HOME`` or
``~/.bsela``). Engines are cached per DB URL so tests that change
``BSELA_HOME`` get their own isolated SQLite file.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
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
    for engine in list(_engine_for.__wrapped__.__dict__.values()):  # pragma: no cover
        del engine
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


def list_sessions(
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[SessionRecord]:
    stmt = select(SessionRecord).order_by(SessionRecord.ingested_at.desc())  # type: ignore[attr-defined]
    if status is not None:
        stmt = stmt.where(SessionRecord.status == status)
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


def list_errors(*, session_id: str | None = None, limit: int = 100) -> list[ErrorRecord]:
    stmt = select(ErrorRecord).order_by(ErrorRecord.detected_at.desc())  # type: ignore[attr-defined]
    if session_id is not None:
        stmt = stmt.where(ErrorRecord.session_id == session_id)
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


def list_lessons(
    *,
    status: str | None = None,
    scope: str | None = None,
    limit: int = 100,
) -> list[Lesson]:
    stmt = select(Lesson).order_by(Lesson.created_at.desc())  # type: ignore[attr-defined]
    if status is not None:
        stmt = stmt.where(Lesson.status == status)
    if scope is not None:
        stmt = stmt.where(Lesson.scope == scope)
    stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


def count_lessons(*, status: str | None = None) -> int:
    stmt = select(Lesson)
    if status is not None:
        stmt = stmt.where(Lesson.status == status)
    with session_scope() as s:
        return len(list(s.exec(stmt).all()))


# ---- Decisions -------------------------------------------------------------


def save_decision(record: Decision) -> Decision:
    with session_scope() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def list_decisions(*, limit: int = 100) -> list[Decision]:
    stmt = select(Decision).order_by(Decision.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
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
    limit: int = 100,
) -> list[Metric]:
    stmt = select(Metric).order_by(Metric.created_at.desc())  # type: ignore[attr-defined]
    if session_id is not None:
        stmt = stmt.where(Metric.session_id == session_id)
    if stage is not None:
        stmt = stmt.where(Metric.stage == stage)
    stmt = stmt.limit(limit)
    with session_scope() as s:
        return list(s.exec(stmt).all())


__all__ = [
    "bsela_home",
    "count_lessons",
    "count_sessions",
    "db_path",
    "get_engine",
    "get_session",
    "list_decisions",
    "list_errors",
    "list_lessons",
    "list_metrics",
    "list_sessions",
    "reset_engine_cache",
    "save_decision",
    "save_error",
    "save_lesson",
    "save_metric",
    "save_session",
    "session_scope",
]
