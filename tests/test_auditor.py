"""P5 auditor: build_audit / render_markdown / write_report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bsela.core.auditor import (
    AUDIT_FILENAME,
    REPORTS_SUBDIR,
    STALE_LESSON_AGE_DAYS,
    build_audit,
    default_report_path,
    render_markdown,
    write_report,
)
from bsela.memory.models import ErrorRecord, Lesson, Metric, ReplayRecord, SessionRecord
from bsela.memory.store import (
    save_error,
    save_lesson,
    save_metric,
    save_replay_record,
    save_session,
)

NOW = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


def _session(
    *,
    status: str = "captured",
    ingested_at: datetime | None = None,
) -> SessionRecord:
    return save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="hash",
            status=status,
            ingested_at=ingested_at or NOW - timedelta(hours=1),
        )
    )


def _metric(cost_usd: float, *, created_at: datetime | None = None) -> Metric:
    return save_metric(
        Metric(
            stage="distill",
            cost_usd=cost_usd,
            created_at=created_at or NOW - timedelta(hours=1),
        )
    )


def _lesson(
    *,
    status: str = "approved",
    hit_count: int = 0,
    created_at: datetime | None = None,
) -> Lesson:
    return save_lesson(
        Lesson(
            scope="project",
            rule="use pathlib",
            why="ergonomic",
            how_to_apply="replace os.path",
            confidence=0.95,
            status=status,
            hit_count=hit_count,
            created_at=created_at or NOW - timedelta(days=30),
        )
    )


def _error(session_id: str) -> ErrorRecord:
    return save_error(
        ErrorRecord(
            session_id=session_id,
            category="loop",
            snippet="same tool twice",
            detected_at=NOW - timedelta(hours=1),
        )
    )


# ---- build_audit ----


def test_empty_store_returns_empty_audit(tmp_bsela_home: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    assert report.sessions_total == 0
    assert report.errors_total == 0
    assert report.cost.total_usd == 0.0
    assert report.drift.lessons_total == 0
    assert report.alerts == ()


def test_build_audit_counts_sessions_and_quarantine(tmp_bsela_home: Path) -> None:
    _session(status="captured")
    _session(status="captured")
    _session(status="quarantined")

    report = build_audit(window_days=30, now=NOW)
    assert report.sessions_total == 3
    assert report.sessions_quarantined == 1
    assert report.quarantine_rate == pytest.approx(1 / 3)


def test_build_audit_counts_errors(tmp_bsela_home: Path) -> None:
    session = _session()
    _error(session.id)
    _error(session.id)

    report = build_audit(window_days=30, now=NOW)
    assert report.errors_total == 2


def test_build_audit_prorates_cost(tmp_bsela_home: Path) -> None:
    # $5 over 15 days prorates to $10/month.
    _metric(5.0, created_at=NOW - timedelta(hours=1))
    report = build_audit(window_days=15, now=NOW)
    assert report.cost.total_usd == pytest.approx(5.0)
    assert report.cost.prorated_monthly_usd == pytest.approx(10.0)
    assert not report.cost.over_budget  # default budget is $50


def test_cost_over_budget_triggers_alert(tmp_bsela_home: Path) -> None:
    # $100 over 30 days == $100/month, well over the $50 budget.
    _metric(100.0)
    report = build_audit(window_days=30, now=NOW)
    assert report.cost.over_budget
    assert any("COST" in alert for alert in report.alerts)


def test_drift_stale_applied_lesson_above_threshold_alerts(
    tmp_bsela_home: Path,
) -> None:
    # 3 applied lessons, all older than the stale cutoff with hit_count=0.
    # drift_fraction = 1.0 > threshold (0.5 default) → alert.
    old = NOW - timedelta(days=STALE_LESSON_AGE_DAYS + 5)
    _lesson(status="approved", hit_count=0, created_at=old)
    _lesson(status="approved", hit_count=0, created_at=old)
    _lesson(status="applied", hit_count=0, created_at=old)

    report = build_audit(window_days=30, now=NOW)
    assert report.drift.lessons_total == 3
    assert report.drift.lessons_stale == 3
    assert report.drift.drift_fraction == pytest.approx(1.0)
    assert any("DRIFT" in alert for alert in report.alerts)


def test_drift_fresh_lesson_does_not_alert(tmp_bsela_home: Path) -> None:
    # Lesson younger than the stale cutoff — doesn't count as stale.
    _lesson(status="approved", hit_count=0, created_at=NOW - timedelta(days=3))
    report = build_audit(window_days=30, now=NOW)
    assert report.drift.lessons_stale == 0
    assert not report.drift.over_threshold


def test_hit_lesson_does_not_count_as_stale(tmp_bsela_home: Path) -> None:
    old = NOW - timedelta(days=STALE_LESSON_AGE_DAYS + 5)
    _lesson(status="approved", hit_count=5, created_at=old)
    report = build_audit(window_days=30, now=NOW)
    assert report.drift.lessons_total == 1
    assert report.drift.lessons_stale == 0


def test_adr_scan_via_env_override(
    tmp_bsela_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    (adr_dir / "0001-good.md").write_text("- **Status:** Accepted\n", encoding="utf-8")
    (adr_dir / "0002-bad.md").write_text("no status line\n", encoding="utf-8")
    monkeypatch.setenv("BSELA_ADR_DIR", str(adr_dir))

    report = build_audit(window_days=30, now=NOW)
    assert report.adrs.total == 2
    assert report.adrs.missing_status == ("0002-bad.md",)
    assert any("ADR" in alert for alert in report.alerts)


def test_window_days_validation(tmp_bsela_home: Path) -> None:
    with pytest.raises(ValueError, match="window_days must be positive"):
        build_audit(window_days=0, now=NOW)


# ---- render_markdown ----


def test_render_markdown_all_clear(tmp_bsela_home: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    md = render_markdown(report)
    assert "# BSELA Weekly Audit" in md
    assert "## Alerts" in md
    assert "_all clear._" in md
    assert "## Cost" in md
    assert "## Drift" in md
    assert "## ADRs" in md


def test_render_markdown_includes_alerts(tmp_bsela_home: Path) -> None:
    _metric(500.0)
    report = build_audit(window_days=30, now=NOW)
    md = render_markdown(report)
    assert "⚠️" in md
    assert "COST" in md


# ---- write_report ----


def test_write_report_writes_to_default_path(tmp_bsela_home: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    path = write_report(report)
    assert path == default_report_path()
    assert path.exists()
    assert path.parent.name == REPORTS_SUBDIR
    assert path.name == AUDIT_FILENAME
    assert "# BSELA Weekly Audit" in path.read_text(encoding="utf-8")


def test_write_report_custom_path(tmp_bsela_home: Path, tmp_path: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    custom = tmp_path / "sub" / "custom.md"
    path = write_report(report, custom)
    assert path == custom
    assert custom.exists()


# ---- replay drift alarm ----


def _replay_rec(
    session_id: str, *, had_drift: bool, replayed_at: datetime | None = None
) -> ReplayRecord:
    return save_replay_record(
        ReplayRecord(
            session_id=session_id,
            had_drift=had_drift,
            replayed_at=replayed_at or NOW - timedelta(hours=1),
        )
    )


def test_replay_drift_no_records(tmp_bsela_home: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    assert report.replay_drift.sessions_replayed == 0
    assert report.replay_drift.drift_rate == 0.0
    assert not report.replay_drift.over_threshold
    assert not any("REPLAY DRIFT" in a for a in report.alerts)


def test_replay_drift_below_threshold_no_alert(tmp_bsela_home: Path) -> None:
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h1",
            ingested_at=NOW - timedelta(hours=2),
        )
    )
    _replay_rec(sess.id, had_drift=False)
    _replay_rec(sess.id, had_drift=False)
    _replay_rec(sess.id, had_drift=True)
    _replay_rec(sess.id, had_drift=True)  # 2/4 = 50% < 80% threshold, not over

    report = build_audit(window_days=30, now=NOW)
    assert report.replay_drift.sessions_replayed == 4
    assert report.replay_drift.sessions_with_drift == 2
    assert report.replay_drift.drift_rate == pytest.approx(0.50)
    assert not report.replay_drift.over_threshold
    assert not any("REPLAY DRIFT" in a for a in report.alerts)


def test_replay_drift_above_threshold_triggers_alert(tmp_bsela_home: Path) -> None:
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h2",
            ingested_at=NOW - timedelta(hours=2),
        )
    )
    _replay_rec(sess.id, had_drift=True)
    _replay_rec(sess.id, had_drift=True)
    _replay_rec(sess.id, had_drift=True)
    _replay_rec(sess.id, had_drift=True)  # 4/4 = 100% > any threshold

    report = build_audit(window_days=30, now=NOW)
    assert report.replay_drift.drift_rate == pytest.approx(1.0)
    assert report.replay_drift.over_threshold
    assert any("REPLAY DRIFT" in a for a in report.alerts)


def test_replay_drift_outside_window_excluded(tmp_bsela_home: Path) -> None:
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h3",
            ingested_at=NOW - timedelta(days=40),
        )
    )
    # Record from 35 days ago — outside the 30-day window.
    _replay_rec(sess.id, had_drift=True, replayed_at=NOW - timedelta(days=35))

    report = build_audit(window_days=30, now=NOW)
    assert report.replay_drift.sessions_replayed == 0


def test_render_markdown_includes_replay_drift_section(tmp_bsela_home: Path) -> None:
    report = build_audit(window_days=30, now=NOW)
    md = render_markdown(report)
    assert "## Replay Drift" in md
    assert "bsela replay" in md


def test_render_markdown_shows_replay_counts(tmp_bsela_home: Path) -> None:
    sess = save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="h4",
            ingested_at=NOW - timedelta(hours=2),
        )
    )
    _replay_rec(sess.id, had_drift=False)
    _replay_rec(sess.id, had_drift=True)

    report = build_audit(window_days=30, now=NOW)
    md = render_markdown(report)
    assert "Sessions replayed" in md
    assert "2" in md
