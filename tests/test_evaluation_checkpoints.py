"""Behavioral acceptance for zero-lesson checkpoints and truthful outcomes."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest
from sqlmodel import select
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.core.process import _safe_failure_detail, process_sessions
from bsela.core.retention import sweep_sessions
from bsela.llm.client import CodexClient, FakeLLMClient
from bsela.llm.distiller import distill_session, evaluation_fingerprint
from bsela.llm.runtime import ProviderError
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import Lesson, SessionEvaluation
from bsela.memory.store import (
    get_session,
    has_evaluation,
    has_session_evaluation,
    list_errors,
    save_error,
    save_lesson,
    save_session,
    session_scope,
)

pytestmark = pytest.mark.usefixtures("tmp_bsela_home")
FIXTURE = Path(__file__).parent / "fixtures/sample-sessions/looped-read.jsonl"


def client(
    *,
    healthy: bool = False,
    status: Literal["ok", "skip", "error"] = "ok",
    lessons: Sequence[LessonCandidate] = (),
) -> FakeLLMClient:
    return FakeLLMClient(
        JudgeVerdict(
            goal_achieved=healthy,
            efficiency=0.8,
            looped=False,
            wasted_tokens=False,
            confidence=0.9 if healthy else 0.4,
        ),
        DistillResponse(status=status, lessons=list(lessons)),
    )


@pytest.mark.parametrize(
    ("healthy", "status", "expected"),
    [
        (True, "ok", "judge_healthy"),
        (False, "skip", "distiller_skipped"),
        (False, "ok", "no_lessons"),
    ],
)
def test_zero_lesson_success_is_truthful_and_idempotent(healthy, status, expected):
    sid = ingest_file(FIXTURE).session_id
    fake = client(healthy=healthy, status=status)
    first = process_sessions(client=fake)
    assert first.outcomes[0].status == expected
    assert first.skipped_judge_healthy == int(healthy)
    assert has_session_evaluation(sid)
    second = process_sessions(client=fake)
    assert second.processed == 0
    assert second.skipped_already_evaluated == 1
    assert fake.judge_calls == 1
    preview = process_sessions(dry_run=True)
    assert preview.outcomes[0].status == "would_skip_already_evaluated"
    assert preview.distilled == 0
    rerun = process_sessions(client=fake, skip_already_distilled=False)
    assert rerun.processed == 1
    assert fake.judge_calls == 2


def test_changed_content_and_detector_evidence_are_reevaluated():
    sid = ingest_file(FIXTURE).session_id
    fake = client()
    process_sessions(client=fake)
    session = get_session(sid)
    assert session is not None
    session.content_hash = "new-content"
    save_session(session)
    assert process_sessions(client=fake).processed == 1
    error = list_errors(session_id=sid)[0]
    error.snippet = "changed detector evidence"
    save_error(error)
    assert process_sessions(client=fake).processed == 1
    assert fake.judge_calls == 3


def test_fingerprint_includes_provider_prompt_and_policy():
    sid = ingest_file(FIXTURE).session_id
    session = get_session(sid)
    assert session is not None
    errors = list_errors(session_id=sid)
    key = evaluation_fingerprint(session, errors)
    assert key == evaluation_fingerprint(session, errors, client=CodexClient())
    assert key != evaluation_fingerprint(session, errors, provider="deepseek")
    assert key != evaluation_fingerprint(session, errors, client=CodexClient(model="different"))
    assert key != evaluation_fingerprint(session, errors, judge_threshold=0.95)
    with patch("bsela.llm.distiller._find_distiller_prompt", return_value="new prompt"):
        assert key != evaluation_fingerprint(session, errors)


@pytest.mark.parametrize("mode", ["dry_run", "no_persist", "replay"])
def test_preview_and_replay_do_not_suppress_future_processing(mode):
    sid = ingest_file(FIXTURE).session_id
    if mode == "dry_run":
        process_sessions(dry_run=True)
    else:
        distill_session(
            sid, client=client(), persist=mode != "no_persist", replay_harness=mode == "replay"
        )
    assert not has_session_evaluation(sid)
    assert process_sessions(client=client()).processed == 1


def test_failures_are_retryable_and_never_echo_private_text(caplog):
    sid = ingest_file(FIXTURE).session_id
    with patch(
        "bsela.core.process.distill_session", side_effect=ProviderError("model: PRIVATE DATA")
    ):
        result = process_sessions(client=client())
    assert result.errors == 1
    assert result.outcomes[0].status == "provider_failure"
    assert result.outcomes[0].detail == "provider model request failed"
    assert "PRIVATE DATA" not in caplog.text
    assert not has_session_evaluation(sid)
    assert process_sessions(client=client()).processed == 1


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (RuntimeError("private"), "unexpected processing failure"),
        (
            ProviderError("codex invocation failed or timed out"),
            "Codex invocation failed or timed out",
        ),
        (ProviderError("auth: private"), "provider authentication failed"),
        (ProviderError("quota: private"), "provider quota unavailable"),
        (ProviderError("isolation: private"), "provider isolation check failed"),
        (ProviderError("invalid response private"), "provider response failed validation"),
        (ProviderError("run deadline private"), "total run deadline exceeded"),
        (ProviderError("private"), "provider request failed"),
    ],
)
def test_failure_details_are_allowlisted(error, detail):
    assert _safe_failure_detail(error) == detail


def test_model_error_never_creates_checkpoint():
    sid = ingest_file(FIXTURE).session_id
    assert process_sessions(client=client(status="error")).errors == 1
    assert not has_session_evaluation(sid)


def test_skips_do_not_use_call_limit_or_starve_older_sessions(tmp_path):
    for i in range(5):
        path = tmp_path / f"session-{i}.jsonl"
        path.write_text(FIXTURE.read_text().replace("missing.toml", f"missing-{i}.toml"))
        sid = ingest_file(path).session_id
        if i:
            distill_session(sid, client=client())
    fake = client()
    result = process_sessions(client=fake, limit=1)
    assert result.skipped_already_evaluated == 4
    assert result.processed == 1
    assert fake.judge_calls == 1


def test_legacy_lesson_skip_and_duplicates_are_distinct():
    sid = ingest_file(FIXTURE).session_id
    error = list_errors(session_id=sid)[0]
    candidate = LessonCandidate(
        rule="Use a new strategy",
        why="loop",
        how_to_apply="on retry",
        scope="project",
        confidence=0.9,
        evidence={"line_range": [3, 3]},
    )
    save_lesson(Lesson(source_error_id=error.id, **candidate.model_dump(exclude={"evidence"})))
    preview = process_sessions(dry_run=True)
    assert preview.outcomes[0].status == "would_skip_already_distilled"
    result = process_sessions(client=client())
    assert result.skipped_already_distilled == 1
    rerun = process_sessions(client=client(lessons=[candidate]), skip_already_distilled=False)
    assert rerun.outcomes[0].status == "duplicates_only"
    session = get_session(sid)
    assert session is not None
    session.content_hash = "grown"
    save_session(session)
    assert process_sessions(client=client()).processed == 1


def test_checkpoint_cascades_on_session_retention():
    sid = ingest_file(FIXTURE).session_id
    process_sessions(client=client())
    session = get_session(sid)
    assert session is not None
    key = evaluation_fingerprint(session, list_errors(session_id=sid))
    assert has_evaluation(key)
    session.ingested_at = datetime.now(UTC) - timedelta(days=30)
    save_session(session)
    assert sweep_sessions(days=7) == 1
    assert not has_evaluation(key)


@pytest.mark.parametrize(
    ("status", "message"), [("skip", "distiller skipped"), ("ok", "no transferable lessons")]
)
def test_distill_cli_does_not_label_low_confidence_as_healthy(status, message):
    sid = ingest_file(FIXTURE).session_id
    with patch("bsela.cli.make_llm_client", return_value=client(status=status)):
        result = CliRunner().invoke(app, ["distill", "--session-id", sid])
    assert result.exit_code == 0
    assert message in result.stdout
    assert "healthy" not in result.stdout


def test_process_cli_reports_safe_provider_failure():
    ingest_file(FIXTURE)
    with (
        patch("bsela.cli.make_llm_client", return_value=client()),
        patch(
            "bsela.core.process.distill_session", side_effect=ProviderError("auth: PRIVATE DATA")
        ),
    ):
        result = CliRunner().invoke(app, ["process", "--limit", "1"])
    assert result.exit_code == 1
    assert "provider_failure" in result.stdout
    assert "provider authentication failed" in result.stdout
    assert "PRIVATE DATA" not in result.stdout


def test_completion_records_contain_no_raw_evidence():
    ingest_file(FIXTURE)
    process_sessions(client=client())
    with session_scope() as db:
        record = db.exec(select(SessionEvaluation)).one()
        assert set(record.model_dump()) == {"input_hash", "session_id", "outcome", "evaluated_at"}
