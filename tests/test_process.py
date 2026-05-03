"""P4 tests: ``bsela process`` batch-distills captured sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.core.process import _is_within_window, process_sessions
from bsela.llm.client import FakeLLMClient
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import SessionRecord
from bsela.memory.store import (
    count_lessons,
    list_errors,
    list_sessions,
    session_scope,
)

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
    # Dedup suppresses the identical lesson on re-run; only the first run's lesson persists.
    assert count_lessons(status="pending") == 1
    assert result.lessons_created == 0


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


def test_process_distill_exception_increments_errors(tmp_bsela_home: Path) -> None:
    """Distill exceptions are counted and don't abort the whole run."""
    ingest_file(FIXTURES / "looped-read.jsonl")

    class BoomClient(FakeLLMClient):
        def judge(self, *, system: str, user: str) -> JudgeVerdict:
            raise RuntimeError("transient failure")

    result = process_sessions(
        client=BoomClient(judge_response=_unhealthy(), distill_response=_one_lesson_distill())
    )
    assert result.errors == 1
    assert result.distilled == 0
    assert count_lessons() == 0


def test_process_billing_error_aborts_early(tmp_bsela_home: Path) -> None:
    """A billing error in distill stops processing immediately."""
    for _ in range(3):
        ingest_file(FIXTURES / "looped-read.jsonl")

    call_count = 0

    class BillingClient(FakeLLMClient):
        def judge(self, *, system: str, user: str) -> JudgeVerdict:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("billing error: insufficient credits")

    result = process_sessions(
        client=BillingClient(judge_response=_unhealthy(), distill_response=_one_lesson_distill()),
        limit=10,
    )
    # Billing error on first session → should abort after 1
    assert call_count == 1
    assert result.errors == 1


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


def test_is_within_window_handles_naive_datetime(
    tmp_bsela_home: Path,
) -> None:
    """Cover line 66→68 both branches: naive and aware ingested_at."""
    cutoff = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)

    # True branch (66→67): naive datetime gets UTC stamp
    naive_session = SessionRecord(
        source="claude_code",
        transcript_path="/tmp/fake.jsonl",
        content_hash="naivehash",
        status="captured",
        ingested_at=datetime(2026, 4, 24, 10, 0, 0),  # no tzinfo
    )
    assert _is_within_window(naive_session, cutoff) is True

    # False branch (66→68): aware datetime skips the replace
    aware_session = SessionRecord(
        source="claude_code",
        transcript_path="/tmp/fake.jsonl",
        content_hash="awarehash",
        status="captured",
        ingested_at=datetime(2026, 4, 24, 10, 0, 0, tzinfo=UTC),
    )
    assert _is_within_window(aware_session, cutoff) is True


def test_process_skips_session_with_no_errors_in_list(
    tmp_bsela_home: Path,
) -> None:
    """Cover lines 110-112: list_errors returns [] even though session was in candidates."""
    ingest_file(FIXTURES / "looped-read.jsonl")

    # Patch list_errors to return empty for any session → skipped_no_errors path
    with patch("bsela.core.process.list_errors", return_value=[]):
        result = process_sessions(client=_client(), limit=5)

    assert result.skipped_no_errors >= 1


# ---- dry-run mode -----------------------------------------------------------


def test_process_dry_run_no_llm_calls_no_store_writes(tmp_bsela_home: Path) -> None:
    """--dry-run makes no LLM calls and leaves the store unchanged."""
    ingest_file(FIXTURES / "looped-read.jsonl")
    fake = _client()

    result = process_sessions(client=None, dry_run=True)

    assert fake.judge_calls == 0
    assert fake.distill_calls == 0
    assert count_lessons() == 0
    assert result.distilled >= 1
    assert result.lessons_created >= 1  # estimated from error count
    assert any(o.status == "would_distill" for o in result.outcomes)


def test_process_dry_run_estimates_from_error_count(tmp_bsela_home: Path) -> None:
    """Estimated lesson candidates equal the number of error records for that session."""
    ingest_file(FIXTURES / "looped-read.jsonl")
    sid = list_sessions(status="captured", limit=1)[0].id
    expected_errors = len(list_errors(session_id=sid))

    result = process_sessions(client=None, dry_run=True, limit=1)

    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.status == "would_distill"
    assert outcome.lessons_created == expected_errors
    assert result.lessons_created == expected_errors


def test_process_dry_run_skips_already_distilled(tmp_bsela_home: Path) -> None:
    """--dry-run marks already-distilled sessions as would_skip_already_distilled."""
    ingest_file(FIXTURES / "looped-read.jsonl")
    # First run distills the session for real.
    process_sessions(client=_client())
    assert count_lessons() == 1

    # Dry-run now sees it as already distilled.
    result = process_sessions(client=None, dry_run=True)
    assert count_lessons() == 1  # still no new writes
    assert any(o.status == "would_skip_already_distilled" for o in result.outcomes)


def test_process_dry_run_cli_exits_zero_no_api_key(tmp_bsela_home: Path) -> None:
    """process --dry-run exits 0 without requiring ANTHROPIC_API_KEY."""
    ingest_file(FIXTURES / "looped-read.jsonl")

    runner = CliRunner()
    result = runner.invoke(app, ["process", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "dry-run" in result.stdout
    assert "no LLM calls" in result.stdout
    assert "no store writes" in result.stdout
    assert "would_distill" in result.stdout


def test_process_dry_run_cli_empty_store(tmp_bsela_home: Path) -> None:
    """process --dry-run on an empty store exits 0 with a clean summary."""
    runner = CliRunner()
    result = runner.invoke(app, ["process", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "dry-run" in result.stdout
    assert "no LLM calls" in result.stdout


def test_process_help_mentions_dry_run_without_api_key(tmp_bsela_home: Path) -> None:
    """CLI help distinguishes live mode (API key) from --dry-run (no key)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["process", "--help"],
        env={"NO_COLOR": "1", "TERM": "dumb"},
    )
    assert result.exit_code == 0, result.stdout
    lowered = result.stdout.lower()
    assert "anthropic_api_key" in lowered
    assert "--dry-run" in lowered
    assert "no api calls" in lowered
