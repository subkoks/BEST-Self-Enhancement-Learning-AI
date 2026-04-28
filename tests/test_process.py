"""P4 tests: ``bsela process`` batch-distills captured sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.core.process import process_sessions
from bsela.llm.client import FakeLLMClient
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import SessionRecord
from bsela.memory.store import count_lessons, list_sessions, session_scope

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


def _unhealthy() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=False,
        efficiency=0.3,
        looped=True,
        wasted_tokens=True,
        confidence=0.6,
    )


def _healthy() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=True,
        efficiency=0.95,
        looped=False,
        wasted_tokens=False,
        confidence=0.9,
    )


def _one_lesson_distill() -> DistillResponse:
    return DistillResponse(
        status="ok",
        confidence=0.92,
        lessons=[
            LessonCandidate(
                rule="Stop retrying Read on a missing path after the first ENOENT",
                why="Loop detector flagged repeated identical Read calls",
                how_to_apply="When Read returns ENOENT twice, change strategy",
                scope="project",
                confidence=0.9,
            )
        ],
    )


def _client(verdict: JudgeVerdict | None = None) -> FakeLLMClient:
    return FakeLLMClient(
        judge_response=verdict or _unhealthy(),
        distill_response=_one_lesson_distill(),
    )


def test_process_empty_store(tmp_bsela_home: Path) -> None:
    result = process_sessions(client=_client())
    assert result.considered == 0
    assert result.processed == 0
    assert result.lessons_created == 0


def test_process_distills_sessions_with_errors(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")
    client = _client()
    result = process_sessions(client=client)
    assert result.processed == 1
    assert result.distilled == 1
    assert result.lessons_created == 1
    assert client.judge_calls == 1
    assert client.distill_calls == 1
    assert count_lessons(status="pending") == 1


def test_process_skips_sessions_without_errors(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "clean.jsonl")
    client = _client()
    result = process_sessions(client=client)
    # Clean sessions are not fetched by list_sessions_with_errors, so they
    # never enter the loop — considered=0, no skipped_no_errors counter bump.
    assert result.considered == 0
    assert result.processed == 0
    assert result.skipped_no_errors == 0
    assert result.lessons_created == 0
    assert client.judge_calls == 0
    assert client.distill_calls == 0


def test_process_idempotent_on_rerun(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")
    client = _client()
    first = process_sessions(client=client)
    assert first.distilled == 1

    second_client = _client()
    second = process_sessions(client=second_client)
    assert second.distilled == 0
    assert second.skipped_already_distilled == 1
    assert second_client.judge_calls == 0


def test_process_rerun_forces_redistill(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")
    process_sessions(client=_client())

    client = _client()
    result = process_sessions(client=client, skip_already_distilled=False)
    assert result.distilled == 1
    assert client.judge_calls == 1
    assert count_lessons(status="pending") >= 2


def test_process_skips_judge_healthy(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")
    client = _client(_healthy())
    result = process_sessions(client=client)
    assert result.skipped_judge_healthy == 1
    assert result.distilled == 0
    assert result.lessons_created == 0


def test_process_respects_since_days_window(tmp_bsela_home: Path) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")

    old = datetime.now(UTC) - timedelta(days=30)
    captured = list_sessions(status="captured", limit=1)
    assert captured
    sid = captured[0].id
    with session_scope() as s:
        session = s.get(SessionRecord, sid)
        assert session is not None
        session.ingested_at = old
        s.add(session)
        s.commit()

    # Window of 1 day excludes the backdated session.
    result = process_sessions(client=_client(), since_days=1)
    assert result.processed == 0
    assert result.lessons_created == 0

    # since_days=None disables the filter.
    result_unbounded = process_sessions(client=_client(), since_days=None)
    assert result_unbounded.processed == 1


def test_process_honours_limit(tmp_bsela_home: Path) -> None:
    for _ in range(3):
        ingest_file(FIXTURES / "looped-read.jsonl")
    assert len(list_sessions(status="captured", limit=10)) == 3

    result = process_sessions(client=_client(), limit=2)
    assert result.processed == 2


def test_process_cli_invokes_real_client_path(
    tmp_bsela_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest_file(FIXTURES / "looped-read.jsonl")

    fake = _client()
    monkeypatch.setattr("bsela.cli.make_llm_client", lambda: fake)

    runner = CliRunner()
    result = runner.invoke(app, ["process", "--limit", "5"])
    assert result.exit_code == 0, result.stdout
    assert "distilled=1" in result.stdout
    assert "lessons=1" in result.stdout
