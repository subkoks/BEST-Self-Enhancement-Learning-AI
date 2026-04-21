"""Dogfood report: rolling markdown summary for P4 measurement.

Aggregates the BSELA store over a rolling window and renders a concise
markdown report so P4 dogfood can track the success criteria defined in
``docs/roadmap.md``:

* ≥ 1 useful lesson per 10 coding sessions.
* Median distillation cost ≤ $0.02 / session.
* Zero secret leaks (quarantine rate signal).
* Lesson gate mix (AUTO / REVIEW / SAFETY).

Pure-ish: ``build_report`` reads the store and returns a dataclass;
``render_markdown`` is a total function of that dataclass. File I/O is
confined to ``write_report``.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import select

from bsela.core.gate import evaluate as evaluate_gate
from bsela.memory.models import ErrorRecord, Lesson, Metric, SessionRecord
from bsela.memory.store import bsela_home, session_scope
from bsela.utils.config import Thresholds, load_thresholds

DEFAULT_WINDOW_DAYS = 7
DEFAULT_RECENT_LIMIT = 10
REPORTS_SUBDIR = "reports"
REPORT_FILENAME = "dogfood.md"


@dataclass(frozen=True)
class LessonSummary:
    id: str
    status: str
    scope: str
    confidence: float
    gate_tag: str
    rule: str


@dataclass(frozen=True)
class DogfoodReport:
    generated_at: datetime
    window_days: int
    window_start: datetime
    window_end: datetime
    sessions_total: int
    sessions_captured: int
    sessions_quarantined: int
    errors_total: int
    errors_by_category: dict[str, int]
    lessons_total: int
    lessons_by_status: dict[str, int]
    lessons_by_scope: dict[str, int]
    gate_tag_counts: dict[str, int]
    cost_total_usd: float
    cost_median_per_session_usd: float
    useful_lesson_ratio: float
    recent_lessons: list[LessonSummary] = field(default_factory=list)

    @property
    def quarantine_rate(self) -> float:
        if self.sessions_total == 0:
            return 0.0
        return self.sessions_quarantined / self.sessions_total


def default_report_path() -> Path:
    return bsela_home() / REPORTS_SUBDIR / REPORT_FILENAME


def _gate_tag(lesson: Lesson, thresholds: Thresholds) -> str:
    decision = evaluate_gate(lesson, thresholds)
    if decision.safety_flag:
        return "SAFETY"
    return "AUTO" if decision.auto_merge else "REVIEW"


def build_report(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    recent_limit: int = DEFAULT_RECENT_LIMIT,
    now: datetime | None = None,
    thresholds: Thresholds | None = None,
) -> DogfoodReport:
    """Aggregate store rows inside the rolling window into a report."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if recent_limit < 0:
        raise ValueError("recent_limit must be non-negative")

    end = now or datetime.now(UTC)
    start = end - timedelta(days=window_days)
    cfg = thresholds or load_thresholds()

    with session_scope() as s:
        sessions = list(
            s.exec(
                select(SessionRecord)
                .where(SessionRecord.ingested_at >= start)
                .where(SessionRecord.ingested_at <= end)
            ).all()
        )
        errors = list(
            s.exec(
                select(ErrorRecord)
                .where(ErrorRecord.detected_at >= start)
                .where(ErrorRecord.detected_at <= end)
            ).all()
        )
        lessons = list(
            s.exec(
                select(Lesson).where(Lesson.created_at >= start).where(Lesson.created_at <= end)
            ).all()
        )
        metrics = list(
            s.exec(
                select(Metric).where(Metric.created_at >= start).where(Metric.created_at <= end)
            ).all()
        )

    sessions_captured = sum(1 for sess in sessions if sess.status == "captured")
    sessions_quarantined = sum(1 for sess in sessions if sess.status == "quarantined")

    errors_by_category = dict(Counter(err.category for err in errors))
    lessons_by_status = dict(Counter(lesson.status for lesson in lessons))
    lessons_by_scope = dict(Counter(lesson.scope for lesson in lessons))

    pending = [lesson for lesson in lessons if lesson.status == "pending"]
    gate_tag_counts: dict[str, int] = dict(Counter(_gate_tag(lesson, cfg) for lesson in pending))

    cost_total = round(sum(m.cost_usd for m in metrics), 6)
    per_session_costs = [sess.cost_usd for sess in sessions if sess.cost_usd > 0.0]
    cost_median = round(statistics.median(per_session_costs), 6) if per_session_costs else 0.0

    useful = sum(1 for lesson in lessons if lesson.status in {"approved", "proposed"})
    useful_ratio = useful / len(sessions) if sessions else 0.0

    recent = sorted(lessons, key=lambda lesson: lesson.created_at, reverse=True)[:recent_limit]
    recent_summaries = [
        LessonSummary(
            id=lesson.id,
            status=lesson.status,
            scope=lesson.scope,
            confidence=lesson.confidence,
            gate_tag=_gate_tag(lesson, cfg),
            rule=lesson.rule,
        )
        for lesson in recent
    ]

    return DogfoodReport(
        generated_at=end,
        window_days=window_days,
        window_start=start,
        window_end=end,
        sessions_total=len(sessions),
        sessions_captured=sessions_captured,
        sessions_quarantined=sessions_quarantined,
        errors_total=len(errors),
        errors_by_category=errors_by_category,
        lessons_total=len(lessons),
        lessons_by_status=lessons_by_status,
        lessons_by_scope=lessons_by_scope,
        gate_tag_counts=gate_tag_counts,
        cost_total_usd=cost_total,
        cost_median_per_session_usd=cost_median,
        useful_lesson_ratio=useful_ratio,
        recent_lessons=recent_summaries,
    )


def _fmt_iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "_none_"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _short(value: str, *, limit: int = 70) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_markdown(report: DogfoodReport) -> str:
    """Render a ``DogfoodReport`` to a self-contained markdown document."""
    lines: list[str] = []
    lines.append("# BSELA Dogfood Report")
    lines.append("")
    lines.append(f"- Generated: `{_fmt_iso(report.generated_at)}`")
    lines.append(
        f"- Window: `{_fmt_iso(report.window_start)}` → "
        f"`{_fmt_iso(report.window_end)}` ({report.window_days}d)"
    )
    lines.append("")
    lines.append("## Capture")
    lines.append("")
    lines.append(f"- Sessions: **{report.sessions_total}**")
    lines.append(f"- Captured: {report.sessions_captured}")
    lines.append(
        f"- Quarantined: {report.sessions_quarantined} (rate: {report.quarantine_rate:.1%})"
    )
    lines.append("")
    lines.append("## Detect")
    lines.append("")
    lines.append(f"- Errors: **{report.errors_total}**")
    lines.append(f"- By category: {_fmt_counts(report.errors_by_category)}")
    lines.append("")
    lines.append("## Distill")
    lines.append("")
    lines.append(f"- Lessons: **{report.lessons_total}**")
    lines.append(f"- By status: {_fmt_counts(report.lessons_by_status)}")
    lines.append(f"- By scope:  {_fmt_counts(report.lessons_by_scope)}")
    lines.append("")
    lines.append("## Gate (pending)")
    lines.append("")
    lines.append(f"- Tags: {_fmt_counts(report.gate_tag_counts)}")
    lines.append("")
    lines.append("## Cost")
    lines.append("")
    lines.append(f"- Total: ${report.cost_total_usd:.4f}")
    lines.append(f"- Median per session: ${report.cost_median_per_session_usd:.4f}")
    lines.append("")
    lines.append("## Success Criteria")
    lines.append("")
    lines.append(
        f"- Useful-lesson ratio: **{report.useful_lesson_ratio:.2f}** "
        "(target ≥ 0.10 = 1 per 10 sessions)"
    )
    lines.append("")
    lines.append("## Recent Lessons")
    lines.append("")
    if not report.recent_lessons:
        lines.append("_none in window._")
    else:
        for lesson in report.recent_lessons:
            lines.append(
                f"- `{lesson.id[:8]}` [{lesson.gate_tag}] "
                f"status={lesson.status} scope={lesson.scope} "
                f"conf={lesson.confidence:.2f} — {_short(lesson.rule)}"
            )
    lines.append("")
    return "\n".join(lines)


def write_report(report: DogfoodReport, path: Path | None = None) -> Path:
    """Render and write the report; returns the resolved path."""
    target = path or default_report_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(report), encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_RECENT_LIMIT",
    "DEFAULT_WINDOW_DAYS",
    "REPORTS_SUBDIR",
    "REPORT_FILENAME",
    "DogfoodReport",
    "LessonSummary",
    "build_report",
    "default_report_path",
    "render_markdown",
    "write_report",
]
