"""P4 dogfood report: build_report / render_markdown / bsela report CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bsela.cli import app
from bsela.core.report import (
    REPORT_FILENAME,
    REPORTS_SUBDIR,
    build_report,
    default_report_path,
    render_markdown,
)
from bsela.memory.models import ErrorRecord, Lesson, Metric, SessionRecord
from bsela.memory.store import (
    save_error,
    save_lesson,
    save_metric,
    save_session,
)

NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)


def _session(
    *,
    status: str = "captured",
    ingested_at: datetime | None = None,
    cost_usd: float = 0.0,
) -> SessionRecord:
    return save_session(
        SessionRecord(
            source="claude_code",
            transcript_path="/tmp/fake.jsonl",
            content_hash="hash",
            status=status,
            cost_usd=cost_usd,
            ingested_at=ingested_at or NOW - timedelta(hours=1),
        )
    )


def _error(session_id: str, category: str, *, detected_at: datetime | None = None) -> ErrorRecord:
    return save_error(
        ErrorRecord(
            session_id=session_id,
            category=category,
            snippet="loop detected",
            detected_at=detected_at or NOW - timedelta(hours=1),
        )
    )


def _lesson(
    *,
    scope: str = "project",
    status: str = "pending",
    confidence: float = 0.95,
    rule: str = "Stop retrying Read on ENOENT after first miss",
    created_at: datetime | None = None,
) -> Lesson:
    return save_lesson(
        Lesson(
            scope=scope,
            rule=rule,
            why="detector evidence",
            how_to_apply="change strategy on second ENOENT",
            confidence=confidence,
            status=status,
            created_at=created_at or NOW - timedelta(hours=1),
        )
    )


def _metric(cost_usd: float, *, created_at: datetime | None = None) -> Metric:
    return save_metric(
        Metric(
            stage="distiller",
            model="haiku",
            cost_usd=cost_usd,
            created_at=created_at or NOW - timedelta(hours=1),
        )
    )


def test_build_report_empty_store(tmp_bsela_home: Path) -> None:
    r = build_report(window_days=7, now=NOW)
    assert r.sessions_total == 0
    assert r.errors_total == 0
    assert r.lessons_total == 0
    assert r.gate_tag_counts == {}
    assert r.useful_lesson_ratio == 0.0
    assert r.quarantine_rate == 0.0
    assert r.cost_total_usd == 0.0
    assert r.cost_median_per_session_usd == 0.0
    assert r.recent_lessons == []


def test_build_report_aggregates_within_window(tmp_bsela_home: Path) -> None:
    sess_a = _session(cost_usd=0.01)
    sess_b = _session(cost_usd=0.03)
    _session(status="quarantined")
    _error(sess_a.id, "tool_loop")
    _error(sess_a.id, "tool_loop")
    _error(sess_b.id, "correction_marker")

    _lesson(status="pending", scope="project", confidence=0.95)
    _lesson(status="pending", scope="global", confidence=0.99)
    _lesson(
        status="pending",
        scope="project",
        confidence=0.95,
        rule="Confirm before a wallet transfer",
    )
    _lesson(status="approved", scope="project")
    _lesson(status="rejected", scope="project")

    _metric(0.05)
    _metric(0.02)

    r = build_report(window_days=7, now=NOW)

    assert r.sessions_total == 3
    assert r.sessions_captured == 2
    assert r.sessions_quarantined == 1
    assert r.errors_total == 3
    assert r.errors_by_category == {"tool_loop": 2, "correction_marker": 1}
    assert r.lessons_total == 5
    assert r.lessons_by_status["pending"] == 3
    assert r.lessons_by_status["approved"] == 1
    assert r.lessons_by_status["rejected"] == 1
    assert r.gate_tag_counts == {"AUTO": 1, "REVIEW": 1, "SAFETY": 1}
    assert r.cost_total_usd == 0.07
    assert r.cost_median_per_session_usd == 0.02
    assert r.useful_lesson_ratio == 1 / 3
    assert len(r.recent_lessons) == 5


def test_build_report_excludes_rows_outside_window(tmp_bsela_home: Path) -> None:
    old = NOW - timedelta(days=30)
    _session(ingested_at=old)
    _lesson(created_at=old)

    r = build_report(window_days=7, now=NOW)
    assert r.sessions_total == 0
    assert r.lessons_total == 0


def test_render_markdown_contains_expected_sections(tmp_bsela_home: Path) -> None:
    _session()
    _lesson(status="approved")
    md = render_markdown(build_report(window_days=7, now=NOW))

    for heading in (
        "# BSELA Dogfood Report",
        "## Capture",
        "## Detect",
        "## Distill",
        "## Gate (pending)",
        "## Cost",
        "## Success Criteria",
        "## Recent Lessons",
    ):
        assert heading in md


def test_report_cli_writes_default_path(tmp_bsela_home: Path) -> None:
    _session()
    _lesson()
    result = CliRunner().invoke(app, ["report"])
    assert result.exit_code == 0, result.stdout

    expected = tmp_bsela_home / REPORTS_SUBDIR / REPORT_FILENAME
    assert expected == default_report_path()
    assert expected.is_file()
    body = expected.read_text(encoding="utf-8")
    assert "# BSELA Dogfood Report" in body


def test_report_cli_stdout_does_not_write(tmp_bsela_home: Path) -> None:
    _lesson()
    target = tmp_bsela_home / REPORTS_SUBDIR / REPORT_FILENAME
    result = CliRunner().invoke(app, ["report", "--stdout"])
    assert result.exit_code == 0, result.stdout
    assert "# BSELA Dogfood Report" in result.stdout
    assert not target.exists()


def test_report_cli_custom_output_path(tmp_bsela_home: Path, tmp_path: Path) -> None:
    _lesson()
    out = tmp_path / "custom.md"
    result = CliRunner().invoke(app, ["report", "--output", str(out), "--window-days", "3"])
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "# BSELA Dogfood Report" in out.read_text(encoding="utf-8")


def test_build_report_raises_on_zero_window_days(tmp_bsela_home: Path) -> None:
    """Cover line 95: window_days <= 0 → ValueError."""
    with pytest.raises(ValueError, match="window_days must be positive"):
        build_report(window_days=0)


def test_build_report_raises_on_negative_recent_limit(tmp_bsela_home: Path) -> None:
    """Cover line 97: recent_limit < 0 → ValueError."""
    with pytest.raises(ValueError, match="recent_limit must be non-negative"):
        build_report(recent_limit=-1)
