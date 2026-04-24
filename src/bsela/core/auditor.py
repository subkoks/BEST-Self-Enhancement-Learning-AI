"""Weekly auditor: longer-lens digest of the BSELA store.

Complements the P4 dogfood report (``bsela report``). Where dogfood
answers "did the pipeline produce anything this week?", the auditor
answers "is the pipeline drifting, overspending, or surfacing stale
artifacts?". Different window (default 30d), different signals.

Pure-ish: ``build_audit`` reads the store and returns a dataclass;
``render_markdown`` is a total function of that dataclass; file I/O
lives in ``write_report``. Mirrors the layout of ``core/report.py``
so the two are easy to hold in one head.

Alerts are derived from ``config/thresholds.toml``:

* ``cost.monthly_budget_usd``       — trip if prorated burn > budget.
* ``audit.drift_alarm_threshold``   — trip if stale-lesson fraction
  exceeds threshold.
* ADR status header — surface any ADR file missing ``**Status:**``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import select

from bsela.memory.models import ErrorRecord, Lesson, Metric, SessionRecord
from bsela.memory.store import bsela_home, session_scope
from bsela.utils.config import Thresholds, find_config_dir, load_thresholds

DEFAULT_WINDOW_DAYS = 30
STALE_LESSON_AGE_DAYS = 14
REPORTS_SUBDIR = "reports"
AUDIT_FILENAME = "audit.md"
ADR_SUBPATH = Path("docs") / "decisions"


@dataclass(frozen=True)
class CostSnapshot:
    total_usd: float
    prorated_monthly_usd: float
    monthly_budget_usd: float

    @property
    def burn_ratio(self) -> float:
        if self.monthly_budget_usd <= 0:
            return 0.0
        return self.prorated_monthly_usd / self.monthly_budget_usd

    @property
    def over_budget(self) -> bool:
        return self.prorated_monthly_usd > self.monthly_budget_usd


@dataclass(frozen=True)
class DriftSnapshot:
    lessons_total: int
    lessons_stale: int
    threshold: float

    @property
    def drift_fraction(self) -> float:
        if self.lessons_total == 0:
            return 0.0
        return self.lessons_stale / self.lessons_total

    @property
    def over_threshold(self) -> bool:
        return self.drift_fraction > self.threshold


@dataclass(frozen=True)
class AdrSnapshot:
    total: int
    missing_status: tuple[str, ...]

    @property
    def scanned(self) -> bool:
        return self.total > 0 or bool(self.missing_status)


@dataclass(frozen=True)
class AuditReport:
    generated_at: datetime
    window_days: int
    window_start: datetime
    window_end: datetime
    sessions_total: int
    sessions_quarantined: int
    errors_total: int
    cost: CostSnapshot
    drift: DriftSnapshot
    adrs: AdrSnapshot
    alerts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def quarantine_rate(self) -> float:
        if self.sessions_total == 0:
            return 0.0
        return self.sessions_quarantined / self.sessions_total


def default_report_path() -> Path:
    return bsela_home() / REPORTS_SUBDIR / AUDIT_FILENAME


def _adr_dir() -> Path | None:
    """Return the ADR directory if BSELA is running inside its own repo."""
    override = os.environ.get("BSELA_ADR_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.is_dir() else None
    try:
        config_dir = find_config_dir()
    except FileNotFoundError:
        return None
    candidate = config_dir.parent / ADR_SUBPATH
    return candidate if candidate.is_dir() else None


def _scan_adrs() -> AdrSnapshot:
    directory = _adr_dir()
    if directory is None:
        return AdrSnapshot(total=0, missing_status=())
    files = sorted(directory.glob("*.md"))
    missing: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "**Status:**" not in text:
            missing.append(path.name)
    return AdrSnapshot(total=len(files), missing_status=tuple(missing))


def build_audit(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: datetime | None = None,
    thresholds: Thresholds | None = None,
) -> AuditReport:
    """Aggregate store rows into an audit report."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    end = now or datetime.now(UTC)
    start = end - timedelta(days=window_days)
    cfg = thresholds or load_thresholds()

    stale_cutoff = end - timedelta(days=STALE_LESSON_AGE_DAYS)
    tracked_statuses = ("applied", "approved")

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
        lessons_tracked_count = len(
            list(
                s.exec(
                    select(Lesson).where(Lesson.status.in_(tracked_statuses))  # type: ignore[attr-defined]
                ).all()
            )
        )
        stale_count = len(
            list(
                s.exec(
                    select(Lesson)
                    .where(Lesson.status.in_(tracked_statuses))  # type: ignore[attr-defined]
                    .where(Lesson.hit_count == 0)
                    .where(Lesson.created_at < stale_cutoff)
                ).all()
            )
        )
        metrics = list(
            s.exec(
                select(Metric).where(Metric.created_at >= start).where(Metric.created_at <= end)
            ).all()
        )

    sessions_quarantined = sum(1 for sess in sessions if sess.status == "quarantined")

    cost_total = round(sum(m.cost_usd for m in metrics), 6)
    # Prorate the window's spend up to a monthly equivalent.
    prorated = cost_total * (30.0 / window_days) if window_days > 0 else 0.0
    cost_snapshot = CostSnapshot(
        total_usd=cost_total,
        prorated_monthly_usd=round(prorated, 6),
        monthly_budget_usd=cfg.cost.monthly_budget_usd,
    )

    drift_snapshot = DriftSnapshot(
        lessons_total=lessons_tracked_count,
        lessons_stale=stale_count,
        threshold=cfg.audit.drift_alarm_threshold,
    )

    adrs = _scan_adrs()

    alerts: list[str] = []
    if cost_snapshot.over_budget:
        alerts.append(
            f"COST: prorated monthly spend ${cost_snapshot.prorated_monthly_usd:.2f} "
            f"exceeds budget ${cost_snapshot.monthly_budget_usd:.2f} "
            f"({cost_snapshot.burn_ratio:.1%})"
        )
    if drift_snapshot.over_threshold:
        alerts.append(
            f"DRIFT: {drift_snapshot.lessons_stale}/{drift_snapshot.lessons_total} "
            f"applied lessons unused for {STALE_LESSON_AGE_DAYS}+ days "
            f"({drift_snapshot.drift_fraction:.1%} > "
            f"{drift_snapshot.threshold:.1%} threshold)"
        )
    if adrs.missing_status:
        alerts.append(
            f"ADR: {len(adrs.missing_status)} file(s) missing Status header — "
            f"{', '.join(adrs.missing_status)}"
        )

    return AuditReport(
        generated_at=end,
        window_days=window_days,
        window_start=start,
        window_end=end,
        sessions_total=len(sessions),
        sessions_quarantined=sessions_quarantined,
        errors_total=len(errors),
        cost=cost_snapshot,
        drift=drift_snapshot,
        adrs=adrs,
        alerts=tuple(alerts),
    )


def _fmt_iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_markdown(report: AuditReport) -> str:
    """Render an ``AuditReport`` as a self-contained markdown document."""
    lines: list[str] = []
    lines.append("# BSELA Weekly Audit")
    lines.append("")
    lines.append(f"- Generated: `{_fmt_iso(report.generated_at)}`")
    lines.append(
        f"- Window: `{_fmt_iso(report.window_start)}` → "
        f"`{_fmt_iso(report.window_end)}` ({report.window_days}d)"
    )
    lines.append("")

    lines.append("## Alerts")
    lines.append("")
    if not report.alerts:
        lines.append("_all clear._")
    else:
        for alert in report.alerts:
            lines.append(f"- ⚠️ {alert}")
    lines.append("")

    lines.append("## Capture")
    lines.append("")
    lines.append(f"- Sessions: **{report.sessions_total}**")
    lines.append(
        f"- Quarantined: {report.sessions_quarantined} (rate: {report.quarantine_rate:.1%})"
    )
    lines.append(f"- Errors detected: {report.errors_total}")
    lines.append("")

    lines.append("## Cost")
    lines.append("")
    lines.append(f"- Window spend:   ${report.cost.total_usd:.4f}")
    lines.append(
        f"- Prorated month: ${report.cost.prorated_monthly_usd:.4f} "
        f"(budget ${report.cost.monthly_budget_usd:.2f}, "
        f"burn {report.cost.burn_ratio:.1%})"
    )
    lines.append("")

    lines.append("## Drift")
    lines.append("")
    lines.append(f"- Applied/approved lessons: {report.drift.lessons_total}")
    lines.append(
        f"- Unused ≥ {STALE_LESSON_AGE_DAYS}d: {report.drift.lessons_stale} "
        f"({report.drift.drift_fraction:.1%}, "
        f"threshold {report.drift.threshold:.1%})"
    )
    lines.append("")

    lines.append("## ADRs")
    lines.append("")
    if not report.adrs.scanned:
        lines.append("_ADR directory not found — running outside the BSELA repo._")
    else:
        lines.append(f"- Files scanned: {report.adrs.total}")
        if report.adrs.missing_status:
            lines.append("- Missing `**Status:**` header:")
            for name in report.adrs.missing_status:
                lines.append(f"  - `{name}`")
        else:
            lines.append("- All ADRs carry a `**Status:**` header.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: AuditReport, path: Path | None = None) -> Path:
    """Render and write the audit; returns the resolved path."""
    target = path or default_report_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(report), encoding="utf-8")
    return target


__all__ = [
    "ADR_SUBPATH",
    "AUDIT_FILENAME",
    "DEFAULT_WINDOW_DAYS",
    "REPORTS_SUBDIR",
    "STALE_LESSON_AGE_DAYS",
    "AdrSnapshot",
    "AuditReport",
    "CostSnapshot",
    "DriftSnapshot",
    "build_audit",
    "default_report_path",
    "render_markdown",
    "write_report",
]
