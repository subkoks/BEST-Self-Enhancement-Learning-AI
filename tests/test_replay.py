"""P7 tests: replay harness diffs stored vs. replayed lessons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.core.replay import LessonDiff, ReplayResult, replay_session
from bsela.llm.client import FakeLLMClient
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate
from bsela.memory.models import ErrorRecord, Lesson, ReplayRecord
from bsela.memory.store import (
    list_replay_records,
    list_sessions,
    save_error,
    save_lesson,
    save_replay_record,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample-sessions"


def _unhealthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=False,
        efficiency=0.3,
        looped=True,
        wasted_tokens=True,
        confidence=0.6,
    )


def _healthy_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        goal_achieved=True,
        efficiency=0.9,
        looped=False,
        wasted_tokens=False,
        confidence=0.95,
    )


def _distill_response(
    rule: str = "Do not retry on the same error twice",
    *,
    scope: Literal["project", "global"] = "project",
    confidence: float = 0.88,
) -> DistillResponse:
    return DistillResponse(
        status="ok",
        confidence=confidence,
        lessons=[
            LessonCandidate(
                rule=rule,
                why="loop detector flagged retries",
                how_to_apply="switch strategy after second failure",
                scope=scope,
                confidence=confidence,
                evidence={},
            )
        ],
    )


def _fake_client(
    verdict: JudgeVerdict | None = None,
    distill: DistillResponse | None = None,
) -> FakeLLMClient:
    return FakeLLMClient(
        judge_response=verdict or _unhealthy_verdict(),
        distill_response=distill or _distill_response(),
    )


def _seed_error(session_id: str) -> ErrorRecord:
    """Persist a synthetic error for session_id so lessons can be JOIN-discovered."""
    return save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            severity="medium",
            snippet="fake snippet for test",
        )
    )


# ---- core replay_session ----------------------------------------------------


def test_replay_raises_for_missing_session(tmp_bsela_home: Path) -> None:
    with pytest.raises(LookupError, match="session not found"):
        replay_session("nonexistent-id", client=_fake_client())


def test_replay_healthy_session_produces_no_diff(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    detect_errors(session_id)

    client = _fake_client(verdict=_healthy_verdict())
    result = replay_session(session_id, client=client)

    assert not result.distilled
    assert result.diff == ()
    assert "healthy" in result.summary()


def test_replay_no_stored_lessons_shows_all_added(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    detect_errors(session_id)

    result = replay_session(session_id, client=_fake_client())

    assert result.distilled
    added = [d for d in result.diff if d.kind == "added"]
    assert len(added) >= 1
    assert result.replayed_lessons


def test_replay_identical_lesson_shows_unchanged(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    rule = "Do not retry on the same error twice"
    stored = save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=rule,
            why="loop detected",
            how_to_apply="switch strategy",
            confidence=0.88,
            status="pending",
        )
    )

    result = replay_session(session_id, client=_fake_client(distill=_distill_response(rule)))

    assert stored.id is not None
    unchanged = [d for d in result.diff if d.kind == "unchanged"]
    assert any(d.rule == rule for d in unchanged), result.diff


def test_replay_changed_rule_shows_added_and_removed(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    old_rule = "Old rule that was superseded"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=old_rule,
            why="old reason",
            how_to_apply="old action",
            confidence=0.7,
            status="pending",
        )
    )

    new_rule = "New improved rule after prompt update"
    result = replay_session(session_id, client=_fake_client(distill=_distill_response(new_rule)))

    kinds = {d.kind for d in result.diff}
    assert "added" in kinds
    assert "removed" in kinds


def test_replay_diff_normalization_ignores_case_and_whitespace(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    base_rule = "Do not retry on the same error twice"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=base_rule.upper(),
            why="reason",
            how_to_apply="action",
            confidence=0.8,
            status="pending",
        )
    )

    result = replay_session(
        session_id,
        client=_fake_client(distill=_distill_response(base_rule.lower())),
    )

    unchanged = [d for d in result.diff if d.kind == "unchanged"]
    assert len(unchanged) >= 1


def test_replay_scope_change_shows_changed(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    rule = "Do not retry on the same error twice"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=rule,
            why="reason",
            how_to_apply="action",
            confidence=0.88,
            status="pending",
        )
    )

    result = replay_session(
        session_id,
        client=_fake_client(distill=_distill_response(rule, scope="global")),
    )

    changed = [d for d in result.diff if d.kind == "changed"]
    assert any(d.rule == rule for d in changed), result.diff


def test_replay_confidence_drift_shows_changed(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    rule = "Do not retry on the same error twice"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=rule,
            why="reason",
            how_to_apply="action",
            confidence=0.60,
            status="pending",
        )
    )

    result = replay_session(
        session_id,
        client=_fake_client(distill=_distill_response(rule, confidence=0.88)),
    )

    changed = [d for d in result.diff if d.kind == "changed"]
    assert any(d.rule == rule for d in changed), result.diff


def test_replay_small_confidence_delta_shows_unchanged(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    err = _seed_error(session_id)

    rule = "Do not retry on the same error twice"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="project",
            rule=rule,
            why="reason",
            how_to_apply="action",
            confidence=0.82,
            status="pending",
        )
    )

    result = replay_session(
        session_id,
        client=_fake_client(distill=_distill_response(rule, confidence=0.88)),
    )

    unchanged = [d for d in result.diff if d.kind == "unchanged"]
    assert any(d.rule == rule for d in unchanged), result.diff


# ---- ReplayResult.summary() -------------------------------------------------


def test_summary_shows_session_id_and_counts() -> None:
    result = ReplayResult(
        session_id="abc-123",
        distilled=True,
        stored_lessons=(),
        replayed_lessons=(),
        diff=(
            LessonDiff("added", "new rule", 0.9, "project"),
            LessonDiff("removed", "old rule", 0.7, "project"),
            LessonDiff("changed", "drifted rule", 0.5, "global"),
        ),
    )
    summary = result.summary()
    assert "abc-123" in summary
    assert "+1" in summary
    assert "-1" in summary
    assert "~1" in summary


# ---- ReplayRecord persistence -----------------------------------------------


def test_replay_persist_result_writes_record(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id

    replay_session(session_id, client=_fake_client(), persist_result=True)

    records = list_replay_records()
    assert len(records) == 1
    assert records[0].session_id == session_id


def test_replay_no_save_skips_record(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id

    replay_session(session_id, client=_fake_client(), persist_result=False)

    assert list_replay_records() == []


def test_replay_persist_had_drift_true_when_drift(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id

    # Stored lesson with different scope → drift
    err = _seed_error(session_id)
    rule = "Do not retry on the same error twice"
    save_lesson(
        Lesson(
            source_error_id=err.id,
            scope="global",
            rule=rule,
            why="r",
            how_to_apply="a",
            confidence=0.88,
            status="pending",
        )
    )

    replay_session(
        session_id,
        client=_fake_client(distill=_distill_response(rule, scope="project")),
        persist_result=True,
    )

    records = list_replay_records()
    assert records[0].had_drift is True


# ---- CLI bsela replay -------------------------------------------------------


def test_cli_replay_ambiguous_prefix_exits_1(tmp_bsela_home: Path) -> None:
    with patch("bsela.cli.resolve_session", side_effect=LookupError("ambiguous")):
        result = CliRunner().invoke(app, ["replay", "abc"])
    assert result.exit_code == 1
    assert "ambiguous" in result.stdout


def test_cli_replay_session_lookup_error_from_replay_session(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id
    with (
        patch("bsela.cli.replay_session", side_effect=LookupError("session gone")),
        patch("bsela.cli.make_llm_client", return_value=None),
    ):
        result = CliRunner().invoke(app, ["replay", session_id])
    assert result.exit_code == 1
    assert "session gone" in result.stdout


def test_cli_replay_not_found_exits_1(tmp_bsela_home: Path) -> None:
    fake = FakeLLMClient(
        judge_response=JudgeVerdict(
            goal_achieved=False, efficiency=0.3, looped=True, wasted_tokens=True, confidence=0.6
        ),
        distill_response=DistillResponse(status="ok", confidence=0.9, lessons=[]),
    )
    with patch("bsela.cli.make_llm_client", return_value=fake):
        result = CliRunner().invoke(app, ["replay", "no-such-session"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_cli_replay_no_save_skips_record(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    session_id = list_sessions(status="captured")[0].id

    fake = FakeLLMClient(
        judge_response=JudgeVerdict(
            goal_achieved=True, efficiency=0.9, looped=False, wasted_tokens=False, confidence=0.9
        ),
        distill_response=DistillResponse(status="ok", confidence=0.9, lessons=[]),
    )
    with patch("bsela.cli.make_llm_client", return_value=fake):
        result = CliRunner().invoke(app, ["replay", session_id, "--no-save"])
    # replay may exit 0 (no drift) or 1 (drift detected) — both valid
    assert result.exit_code in (0, 1)
    assert list_replay_records() == []


def test_cli_replays_list_empty(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["replays", "list"])
    assert result.exit_code == 0
    assert "no entries" in result.stdout


def test_cli_replays_list_json_empty_store_returns_empty_array(tmp_bsela_home: Path) -> None:
    result = CliRunner().invoke(app, ["replays", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_cli_replays_list_json_drift_only_returns_empty_when_only_non_drift_records(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    sid = list_sessions(status="captured")[0].id
    save_replay_record(
        ReplayRecord(session_id=sid, had_drift=False, added_count=0, removed_count=0)
    )
    result = CliRunner().invoke(app, ["replays", "list", "--json", "--drift-only"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_cli_replays_list_shows_records(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    sid = list_sessions(status="captured")[0].id
    save_replay_record(
        ReplayRecord(
            session_id=sid,
            had_drift=True,
            added_count=1,
            removed_count=2,
            changed_count=0,
            unchanged_count=3,
        )
    )

    result = CliRunner().invoke(app, ["replays", "list"])
    assert result.exit_code == 0
    assert "DRIFT" in result.stdout
    assert sid[:8] in result.stdout


def test_cli_replays_list_drift_only_filter(
    tmp_bsela_home: Path, sample_clean_session: Path
) -> None:
    ingest_file(sample_clean_session)
    sid = list_sessions(status="captured")[0].id
    save_replay_record(
        ReplayRecord(session_id=sid, had_drift=False, added_count=0, removed_count=0)
    )

    result = CliRunner().invoke(app, ["replays", "list", "--drift-only"])
    assert result.exit_code == 0
    assert "no entries" in result.stdout


def test_cli_replays_list_json_output(tmp_bsela_home: Path, sample_clean_session: Path) -> None:
    ingest_file(sample_clean_session)
    sid = list_sessions(status="captured")[0].id
    save_replay_record(ReplayRecord(session_id=sid, had_drift=True, added_count=1, removed_count=0))

    result = CliRunner().invoke(app, ["replays", "list", "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert sorted(rows[0].keys()) == [
        "added_count",
        "changed_count",
        "had_drift",
        "id",
        "removed_count",
        "replayed_at",
        "session_id",
        "unchanged_count",
    ]
    assert rows[0]["had_drift"] is True
    assert rows[0]["session_id"] == sid
