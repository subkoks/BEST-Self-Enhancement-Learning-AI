"""BSELA command-line interface.

P1 wires ``bsela ingest`` and ``bsela status`` to the capture pipeline +
SQLite memory store.

Output uses ``typer.echo`` / ``typer.secho`` for deterministic, ANSI-free
text by default. Colour activates only when stdout is a TTY, so test
captures and piped output stay machine-parseable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from bsela import __version__
from bsela.core.auditor import (
    DEFAULT_WINDOW_DAYS as AUDIT_DEFAULT_WINDOW_DAYS,
)
from bsela.core.auditor import (
    AuditReport,
    build_audit,
)
from bsela.core.auditor import (
    render_markdown as render_audit_markdown,
)
from bsela.core.auditor import (
    write_report as write_audit_report,
)
from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.core.doctor import FAIL, PASS, WARN, CheckResult, run_checks, worst_status
from bsela.core.gate import evaluate as evaluate_gate
from bsela.core.hook_install import (
    DEFAULT_HOOK_COMMAND,
    apply_install,
    default_claude_settings_path,
    plan_install,
)
from bsela.core.process import (
    DEFAULT_LIMIT as PROCESS_DEFAULT_LIMIT,
)
from bsela.core.process import (
    DEFAULT_SINCE_DAYS as PROCESS_DEFAULT_SINCE_DAYS,
)
from bsela.core.process import (
    process_sessions,
)
from bsela.core.replay import replay_session
from bsela.core.report import (
    DEFAULT_RECENT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    build_report,
    render_markdown,
    write_report,
)
from bsela.core.retention import sweep
from bsela.core.router import classify as classify_task
from bsela.core.updater import UpdaterError, propose_lesson
from bsela.llm.client import make_llm_client
from bsela.llm.distiller import distill_session
from bsela.memory.models import Decision, Lesson
from bsela.memory.store import (
    bsela_home,
    count_lessons,
    count_sessions,
    db_path,
    get_lesson,
    get_session,
    increment_hit_count,
    list_decisions,
    list_errors,
    list_lessons,
    list_replay_records,
    list_sessions,
    save_decision,
    update_lesson_status,
)
from bsela.utils.config import load_thresholds

app = typer.Typer(
    name="bsela",
    help="Best Self-Enhancement Learning Agent — control plane for coding AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
hook_app = typer.Typer(
    name="hook",
    help="Hook entrypoints invoked by editor integrations.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(hook_app, name="hook")
review_app = typer.Typer(
    name="review",
    help="List, propose, and reject pending lessons.",
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
)
app.add_typer(review_app, name="review")
decision_app = typer.Typer(
    name="decision",
    help="Record and review load-bearing autonomous decisions.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(decision_app, name="decision")
sessions_app = typer.Typer(
    name="sessions",
    help="Inspect captured sessions and their detected errors.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(sessions_app, name="sessions")
errors_app = typer.Typer(
    name="errors",
    help="Inspect detected error records.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(errors_app, name="errors")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bsela {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """BSELA root callback."""


@app.command()
def status(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit counts as JSON for machine consumption."),
    ] = False,
) -> None:
    """Show storage metrics: sessions, errors, lessons, pending proposals."""
    home = bsela_home()
    if not db_path().exists():
        if as_json:
            typer.echo(
                json.dumps(
                    {
                        "sessions": 0,
                        "sessions_quarantined": 0,
                        "errors": 0,
                        "lessons": 0,
                        "lessons_pending": 0,
                        "lessons_proposed": 0,
                        "replay_records": 0,
                        "bsela_home": str(home),
                    }
                )
            )
        else:
            typer.echo(f"status: no store at {home} yet — run `bsela ingest` first.")
        raise typer.Exit(code=0)

    sessions_total = count_sessions()
    sessions_quarantined = count_sessions(status="quarantined")
    errors_total = len(list_errors(limit=None))
    lessons_pending = count_lessons(status="pending")
    lessons_proposed = count_lessons(status="proposed")
    lessons_total = count_lessons()
    replay_total = len(list_replay_records(limit=None))

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "sessions": sessions_total,
                    "sessions_quarantined": sessions_quarantined,
                    "errors": errors_total,
                    "lessons": lessons_total,
                    "lessons_pending": lessons_pending,
                    "lessons_proposed": lessons_proposed,
                    "replay_records": replay_total,
                    "bsela_home": str(home),
                }
            )
        )
    else:
        typer.echo(f"BSELA home: {home}")
        typer.echo(f"sessions: {sessions_total} (quarantined: {sessions_quarantined})")
        typer.echo(f"errors:   {errors_total}")
        typer.echo(
            f"lessons:  {lessons_total} (pending: {lessons_pending}, proposed: {lessons_proposed})"
        )
        typer.echo(f"replays:  {replay_total}")
    raise typer.Exit(code=0)


@app.command()
def ingest(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            file_okay=True,
            readable=True,
            help="Path to a session transcript (JSONL).",
        ),
    ],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Origin editor/agent of the transcript.",
        ),
    ] = "claude_code",
) -> None:
    """Ingest one session transcript into the BSELA store."""
    result = ingest_file(path, source=source)
    if result.status == "quarantined":
        typer.secho(
            f"quarantined {result.session_id}: {result.quarantine_reason}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=0)

    typer.secho(
        f"captured {result.session_id} "
        f"turns={result.turn_count} tool_calls={result.tool_call_count} "
        f"errors={result.errors_detected}",
        fg=typer.colors.GREEN,
    )
    raise typer.Exit(code=0)


def _short(value: str, *, limit: int = 60) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _render_pending(lesson: Lesson) -> str:
    gate = evaluate_gate(lesson, load_thresholds())
    tag = "AUTO" if gate.auto_merge else "REVIEW"
    if gate.safety_flag:
        tag = "SAFETY"
    return (
        f"{lesson.id}  [{tag}]  scope={lesson.scope}  "
        f"conf={lesson.confidence:.2f}  {_short(lesson.rule)}"
    )


@review_app.callback(invoke_without_command=True)
def review_root(ctx: typer.Context) -> None:
    """List lessons awaiting operator action (proposed + pending)."""
    if ctx.invoked_subcommand is not None:
        return
    proposed = list_lessons(status="proposed", limit=100)
    pending = list_lessons(status="pending", limit=100)
    actionable = proposed + pending
    if not actionable:
        typer.echo("review: no lessons awaiting action.")
        raise typer.Exit(code=0)
    if proposed:
        n = len(proposed)
        typer.echo(f"review: {n} proposed lesson(s) — run 'bsela review propose/reject <id>'")
        for lesson in proposed:
            typer.echo(_render_pending(lesson))
    if pending:
        typer.echo(f"review: {len(pending)} pending lesson(s) — awaiting gate evaluation")
        for lesson in pending:
            typer.echo(_render_pending(lesson))
    raise typer.Exit(code=0)


@review_app.command("list")
def review_list(
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status: pending|proposed|rejected|approved|applied|rolled_back.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max lessons to show.")] = 50,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON array.")] = False,
    track_hits: Annotated[
        bool,
        typer.Option(
            "--track-hits",
            help="Increment hit_count on every returned lesson (use when surfacing to an editor).",
        ),
    ] = False,
) -> None:
    """List lessons with optional status filter. Default shows all."""
    lessons = list_lessons(status=status, limit=limit)
    if track_hits and lessons:
        increment_hit_count([le.id for le in lessons])
    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "id": lesson.id,
                        "status": lesson.status,
                        "scope": lesson.scope,
                        "confidence": lesson.confidence,
                        "rule": lesson.rule,
                        "why": lesson.why,
                        "how_to_apply": lesson.how_to_apply,
                        "hit_count": lesson.hit_count,
                        "created_at": lesson.created_at.isoformat() if lesson.created_at else None,
                    }
                    for lesson in lessons
                ],
                indent=2,
            )
        )
        return
    if not lessons:
        label = f"status={status}" if status else "any status"
        typer.echo(f"review list: no lessons with {label}.")
        return
    for lesson in lessons:
        typer.echo(
            f"{lesson.id}  [{lesson.status:12}]  scope={lesson.scope}  "
            f"conf={lesson.confidence:.2f}  hits={lesson.hit_count}  {_short(lesson.rule)}"
        )


@review_app.command("propose")
def review_propose(
    lesson_id: Annotated[str, typer.Argument(help="Pending lesson id to propose.")],
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            help="Override BSELA_AGENTS_MD_REPO for this call.",
            dir_okay=True,
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Write a proposal branch on agents-md for a pending lesson."""
    lesson = get_lesson(lesson_id)
    if lesson is None:
        typer.secho(f"review: lesson {lesson_id} not found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if lesson.status != "pending":
        typer.secho(
            f"review: lesson {lesson_id} is status={lesson.status}; nothing to propose.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    gate = evaluate_gate(lesson, load_thresholds())
    try:
        result = propose_lesson(lesson, repo=repo)
    except UpdaterError as exc:
        typer.secho(f"review: proposal failed — {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=2) from None

    new_status = "approved" if gate.auto_merge else "proposed"
    update_lesson_status(lesson_id, status=new_status, note=f"branch={result.branch}")
    typer.secho(
        f"review: proposed lesson {lesson_id} -> {result.branch} "
        f"(base={result.base_branch}, status={new_status})",
        fg=typer.colors.GREEN,
    )
    raise typer.Exit(code=0)


@review_app.command("reject")
def review_reject(
    lesson_id: Annotated[str, typer.Argument(help="Pending lesson id to reject.")],
    note: Annotated[
        str | None,
        typer.Option(
            "--note",
            "-n",
            help="Reason to attach to the rejected lesson.",
        ),
    ] = None,
) -> None:
    """Mark a pending lesson as rejected. No branch is written."""
    lesson = get_lesson(lesson_id)
    if lesson is None:
        typer.secho(f"review: lesson {lesson_id} not found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if lesson.status != "pending":
        typer.secho(
            f"review: lesson {lesson_id} is status={lesson.status}; cannot reject.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    update_lesson_status(lesson_id, status="rejected", note=note)
    typer.echo(f"review: rejected lesson {lesson_id}.")
    raise typer.Exit(code=0)


@app.command()
def rollback(
    lesson_id: Annotated[str, typer.Argument(help="Lesson identifier to revert.")],
    note: Annotated[str | None, typer.Option("--note", "-n", help="Reason for rollback.")] = None,
) -> None:
    """Mark a lesson as rolled back.

    Sets the lesson status to ``rolled_back`` so it no longer participates
    in routing or audit counts. If the lesson was already written to your
    agents-md repo you will need to revert that change there manually — this
    command only updates the local BSELA store.

    Exit code 0: rolled back successfully or already rolled back.
    Exit code 1: lesson not found.
    """
    lesson = get_lesson(lesson_id)
    if lesson is None:
        typer.secho(f"rollback: lesson not found: {lesson_id}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if lesson.status == "rolled_back":
        typer.echo(f"rollback: {lesson_id} is already rolled back — nothing to do.")
        raise typer.Exit(code=0)

    prev_status = lesson.status
    update_lesson_status(lesson_id, status="rolled_back", note=note)
    typer.secho(
        f"rolled back: [{prev_status}] {lesson.rule}",
        fg=typer.colors.YELLOW,
    )
    if prev_status in ("approved", "proposed", "applied"):
        typer.echo(
            "  If this lesson was already written to agents-md, revert that branch manually."
        )


@app.command()
def replay(
    session_id: Annotated[str, typer.Argument(help="Session ID to replay.")],
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save",
            help="Skip persisting the replay result (default: save to store for drift tracking).",
        ),
    ] = False,
) -> None:
    """Re-distill a stored session and show a diff against its existing lessons.

    Requires ANTHROPIC_API_KEY. Lessons are not persisted; by default the
    diff summary is saved to the store so ``bsela audit`` can track drift rate
    over time. Use --no-save to suppress this.

    Exit code 0: no drift (replayed lessons match stored).
    Exit code 1: drift detected or session not found.
    """
    try:
        llm = make_llm_client()
        result = replay_session(session_id, client=llm, persist_result=not no_save)
    except LookupError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo(result.summary())
    drift = any(d.kind != "unchanged" for d in result.diff)
    raise typer.Exit(code=1 if drift else 0)


@decision_app.command("add")
def decision_add(
    title: Annotated[str, typer.Argument(help="Short title — first line of the ADR.")],
    context: Annotated[
        str,
        typer.Option(
            "--context",
            "-c",
            help="Why this decision exists (one paragraph is fine).",
        ),
    ],
    decision: Annotated[
        str,
        typer.Option(
            "--decision",
            "-d",
            help="The chosen option, stated positively.",
        ),
    ],
    consequences: Annotated[
        str,
        typer.Option(
            "--consequences",
            "-x",
            help="Trade-offs and what this forecloses.",
        ),
    ],
) -> None:
    """Persist a load-bearing autonomous decision to the decisions table.

    This is the AGENTS.md "Log autonomous decisions" counterpart for
    work too small to warrant a full ``docs/decisions/00NN-*.md`` ADR
    but large enough to want an audit trail.
    """
    saved = save_decision(
        Decision(
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
        )
    )
    typer.secho(f"decision {saved.id}: recorded.", fg=typer.colors.GREEN)
    raise typer.Exit(code=0)


@decision_app.command("list")
def decision_list(
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, help="Max decisions to show."),
    ] = 20,
) -> None:
    """List recently recorded decisions (newest first)."""
    rows = list_decisions(limit=limit)
    if not rows:
        typer.echo("decision: no entries yet.")
        raise typer.Exit(code=0)
    for row in rows:
        stamp = row.created_at.strftime("%Y-%m-%d %H:%M")
        typer.echo(f"- {row.id}  {stamp}  {row.title}")
    raise typer.Exit(code=0)


@sessions_app.command("list")
def sessions_list(
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, help="Max sessions to show."),
    ] = 20,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status (captured / quarantined).",
        ),
    ] = None,
) -> None:
    """List captured sessions (newest first)."""
    rows = list_sessions(status=status, limit=limit)
    if not rows:
        typer.echo("sessions: no entries.")
        raise typer.Exit(code=0)
    for row in rows:
        stamp = row.ingested_at.strftime("%Y-%m-%d %H:%M")
        tag = row.status.upper()
        typer.echo(
            f"- {row.id}  {stamp}  {tag:<11} "
            f"turns={row.turn_count} tools={row.tool_call_count} src={row.source}"
        )
    raise typer.Exit(code=0)


@sessions_app.command("show")
def sessions_show(
    session_id: Annotated[str, typer.Argument(help="Session id (uuid).")],
) -> None:
    """Show session metadata and its detected errors."""
    row = get_session(session_id)
    if row is None:
        typer.secho(f"sessions: {session_id} not found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"id:              {row.id}")
    typer.echo(f"source:          {row.source}")
    typer.echo(f"status:          {row.status}")
    if row.quarantine_reason:
        typer.echo(f"quarantine:      {row.quarantine_reason}")
    typer.echo(f"transcript:      {row.transcript_path}")
    typer.echo(f"content_hash:    {row.content_hash}")
    typer.echo(f"started_at:      {row.started_at.isoformat()}")
    if row.ended_at is not None:
        typer.echo(f"ended_at:        {row.ended_at.isoformat()}")
    typer.echo(f"ingested_at:     {row.ingested_at.isoformat()}")
    typer.echo(f"turn_count:      {row.turn_count}")
    typer.echo(f"tool_call_count: {row.tool_call_count}")
    typer.echo(f"tokens_in:       {row.tokens_in}")
    typer.echo(f"tokens_out:      {row.tokens_out}")
    typer.echo(f"cost_usd:        {row.cost_usd:.4f}")

    errs = list_errors(session_id=row.id, limit=50)
    typer.echo(f"\nerrors ({len(errs)}):")
    if not errs:
        typer.echo("  (none)")
    else:
        for err in errs:
            line = f"L{err.line_number}" if err.line_number is not None else "L-"
            typer.echo(f"  - {err.id}  [{err.category}/{err.severity}] {line}: {err.snippet[:80]}")
    raise typer.Exit(code=0)


@errors_app.command("list")
def errors_list(
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Filter by session id."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, help="Max errors to show."),
    ] = 50,
) -> None:
    """List detected error records (newest first)."""
    rows = list_errors(session_id=session_id, limit=limit)
    if not rows:
        typer.echo("errors: no entries.")
        raise typer.Exit(code=0)
    for row in rows:
        stamp = row.detected_at.strftime("%Y-%m-%d %H:%M")
        line = f"L{row.line_number}" if row.line_number is not None else "L-"
        typer.echo(
            f"- {row.id}  {stamp}  [{row.category}/{row.severity}] "
            f"sess={row.session_id[:8]}… {line}: {row.snippet[:80]}"
        )
    raise typer.Exit(code=0)


@app.command()
def detect(
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session-id",
            "-s",
            help="Detect against a single session id. Omit to scan all captured sessions.",
        ),
    ] = None,
) -> None:
    """Run the deterministic detector over captured sessions."""
    if session_id is not None:
        result = detect_errors(session_id)
        typer.echo(f"session {result.session_id}: {len(result.errors)} candidate errors")
        raise typer.Exit(code=0)

    targets = list_sessions(status="captured", limit=None)
    total = 0
    for sess in targets:
        result = detect_errors(sess.id)
        total += len(result.errors)
    typer.echo(f"scanned {len(targets)} sessions, found {total} candidate errors")
    raise typer.Exit(code=0)


@app.command()
def prune() -> None:
    """Drop sessions + errors older than the retention windows in thresholds.toml."""
    result = sweep()
    typer.echo(
        f"pruned sessions: {result.sessions_deleted}"
        f"  errors: {result.errors_deleted}"
        f"  replay_records: {result.replay_records_deleted}"
    )
    raise typer.Exit(code=0)


_DOCTOR_COLOR = {
    PASS: typer.colors.GREEN,
    WARN: typer.colors.YELLOW,
    FAIL: typer.colors.RED,
}


def _format_doctor_line(result: CheckResult) -> tuple[str, str]:
    tag = result.status.upper()
    return (
        f"[{tag:<4}] {result.name:<20} {result.detail}",
        _DOCTOR_COLOR[result.status],
    )


@app.command()
def doctor() -> None:
    """Check environment health (API key, store, hook, agents-md repo)."""
    results = run_checks()
    for row in results:
        line, color = _format_doctor_line(row)
        typer.secho(line, fg=color)
    overall = worst_status(results)
    summary = {
        PASS: "all checks passed.",
        WARN: "some checks warned.",
        FAIL: "some checks failed.",
    }[overall]
    typer.secho(f"doctor: {summary}", fg=_DOCTOR_COLOR[overall])
    raise typer.Exit(code=1 if overall == FAIL else 0)


@app.command()
def report(
    window_days: Annotated[
        int,
        typer.Option(
            "--window-days",
            "-w",
            min=1,
            help="Rolling window in days.",
        ),
    ] = DEFAULT_WINDOW_DAYS,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            dir_okay=False,
            file_okay=True,
            help="Target path. Defaults to ~/.bsela/reports/dogfood.md.",
        ),
    ] = None,
    to_stdout: Annotated[
        bool,
        typer.Option("--stdout", help="Print markdown to stdout instead of writing."),
    ] = False,
    recent: Annotated[
        int,
        typer.Option(
            "--recent",
            min=0,
            help="Number of recent lessons to list.",
        ),
    ] = DEFAULT_RECENT_LIMIT,
) -> None:
    """Generate the P4 dogfood report from the BSELA store."""
    data = build_report(window_days=window_days, recent_limit=recent)
    if to_stdout:
        typer.echo(render_markdown(data))
        raise typer.Exit(code=0)
    target = write_report(data, output)
    typer.echo(f"report: wrote {data.lessons_total} lesson(s) over {window_days}d to {target}")
    raise typer.Exit(code=0)


@app.command()
def route(
    task: Annotated[str, typer.Argument(help="Free-form task description.")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit the decision as JSON for machine consumption."),
    ] = False,
) -> None:
    """Route a task to a model class via the keyword-based router (P5)."""
    decision = classify_task(task)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "task_class": decision.task_class,
                    "model": decision.model,
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "matched_keywords": list(decision.matched_keywords),
                }
            )
        )
    else:
        typer.echo(f"class:      {decision.task_class}")
        typer.echo(f"model:      {decision.model}")
        typer.echo(f"confidence: {decision.confidence:.2f}")
        typer.echo(f"reason:     {decision.reason}")
        if decision.matched_keywords:
            typer.echo(f"keywords:   {', '.join(decision.matched_keywords)}")
    raise typer.Exit(code=0)


def _audit_json_payload(report_data: object) -> dict[str, object]:
    """Serialize ``AuditReport`` into a machine-readable JSON payload."""
    if not isinstance(report_data, AuditReport):
        raise TypeError("report_data must be an AuditReport")
    return {
        "generated_at": report_data.generated_at.isoformat(),
        "window_days": report_data.window_days,
        "window_start": report_data.window_start.isoformat(),
        "window_end": report_data.window_end.isoformat(),
        "sessions": {
            "total": report_data.sessions_total,
            "quarantined": report_data.sessions_quarantined,
            "quarantine_rate": report_data.quarantine_rate,
        },
        "errors_total": report_data.errors_total,
        "cost": {
            "total_usd": report_data.cost.total_usd,
            "prorated_monthly_usd": report_data.cost.prorated_monthly_usd,
            "monthly_budget_usd": report_data.cost.monthly_budget_usd,
            "burn_ratio": report_data.cost.burn_ratio,
            "over_budget": report_data.cost.over_budget,
        },
        "drift": {
            "lessons_total": report_data.drift.lessons_total,
            "lessons_stale": report_data.drift.lessons_stale,
            "threshold": report_data.drift.threshold,
            "drift_fraction": report_data.drift.drift_fraction,
            "over_threshold": report_data.drift.over_threshold,
        },
        "replay_drift": {
            "sessions_replayed": report_data.replay_drift.sessions_replayed,
            "sessions_with_drift": report_data.replay_drift.sessions_with_drift,
            "threshold": report_data.replay_drift.threshold,
            "drift_rate": report_data.replay_drift.drift_rate,
            "over_threshold": report_data.replay_drift.over_threshold,
        },
        "adrs": {
            "total": report_data.adrs.total,
            "missing_status": list(report_data.adrs.missing_status),
            "scanned": report_data.adrs.scanned,
        },
        "alerts": list(report_data.alerts),
    }


@app.command()
def audit(
    window_days: Annotated[
        int,
        typer.Option(
            "--window-days",
            "-w",
            min=1,
            help="Rolling window in days.",
        ),
    ] = AUDIT_DEFAULT_WINDOW_DAYS,
    weekly: Annotated[
        bool,
        typer.Option(
            "--weekly",
            help="Shorthand used by the launchd plist; equivalent to the default 30d window.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            dir_okay=False,
            file_okay=True,
            help="Target path. Defaults to ~/.bsela/reports/audit.md.",
        ),
    ] = None,
    to_stdout: Annotated[
        bool,
        typer.Option("--stdout", help="Print markdown to stdout instead of writing."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit the audit report as JSON for machine consumption."),
    ] = False,
) -> None:
    """Generate the P5 weekly audit from the BSELA store."""
    # --weekly is presentational; it just pins the window to the default.
    window = AUDIT_DEFAULT_WINDOW_DAYS if weekly else window_days
    report_data = build_audit(window_days=window)
    if as_json:
        typer.echo(json.dumps(_audit_json_payload(report_data)))
    elif to_stdout:
        typer.echo(render_audit_markdown(report_data))
    else:
        target = write_audit_report(report_data, output)
        typer.echo(f"audit: wrote window={window}d, alerts={len(report_data.alerts)} to {target}")
    # Non-zero exit on active alerts so the weekly launchd run surfaces in logs.
    raise typer.Exit(code=1 if report_data.alerts else 0)


@app.command()
def distill(
    session_id: Annotated[
        str,
        typer.Option("--session-id", "-s", help="Session id to distill."),
    ],
    persist: Annotated[
        bool,
        typer.Option("--persist/--no-persist", help="Write pending Lesson rows."),
    ] = True,
) -> None:
    """Run judge → distill over one session (requires ANTHROPIC_API_KEY)."""
    client = make_llm_client()
    result = distill_session(session_id, client=client, persist=persist)
    if not result.distilled:
        typer.echo(
            f"session {session_id}: judge says healthy "
            f"(confidence={result.verdict.confidence:.2f}); no lessons distilled."
        )
        raise typer.Exit(code=0)
    typer.echo(
        f"session {session_id}: {len(result.persisted)} lesson(s) "
        f"{'persisted' if persist else 'drafted'}."
    )
    raise typer.Exit(code=0)


@app.command()
def process(
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, help="Max sessions to distill in one run."),
    ] = PROCESS_DEFAULT_LIMIT,
    since_days: Annotated[
        int,
        typer.Option(
            "--since-days",
            "-d",
            min=0,
            help="Only consider sessions ingested within this window. 0 = no window.",
        ),
    ] = PROCESS_DEFAULT_SINCE_DAYS,
    rerun: Annotated[
        bool,
        typer.Option(
            "--rerun/--skip-already-distilled",
            help="Re-distill sessions even if a Lesson already references their errors.",
        ),
    ] = False,
    persist: Annotated[
        bool,
        typer.Option("--persist/--no-persist", help="Write pending Lesson rows."),
    ] = True,
) -> None:
    """Batch-distill recent captured sessions (requires ANTHROPIC_API_KEY)."""
    client = make_llm_client()
    result = process_sessions(
        client=client,
        limit=limit,
        since_days=since_days if since_days > 0 else None,
        skip_already_distilled=not rerun,
        persist=persist,
    )
    typer.echo(
        f"process: considered={result.considered} processed={result.processed} "
        f"distilled={result.distilled} lessons={result.lessons_created}"
    )
    typer.echo(
        f"  skipped: no_errors={result.skipped_no_errors} "
        f"already_distilled={result.skipped_already_distilled} "
        f"judge_healthy={result.skipped_judge_healthy} errors={result.errors}"
    )
    if result.errors:
        typer.secho(
            "  hint: check ANTHROPIC_API_KEY and credit balance "
            "(run `bsela distill <session-id>` to see the full error)",
            fg=typer.colors.YELLOW,
        )
    raise typer.Exit(code=0)


@hook_app.command("claude-stop")
def claude_stop() -> None:
    """Read a Claude Code Stop JSON payload on stdin and ingest its transcript."""
    raw = sys.stdin.read()
    if not raw.strip():
        raise typer.Exit(code=0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise typer.Exit(code=0) from None
    transcript = payload.get("transcript_path") or payload.get("transcriptPath")
    if not isinstance(transcript, str) or not transcript:
        raise typer.Exit(code=0)
    path = Path(transcript).expanduser()
    if not path.is_file():
        raise typer.Exit(code=0)
    ingest_file(path, source="claude_code")
    raise typer.Exit(code=0)


@hook_app.command("install")
def hook_install(
    settings: Annotated[
        Path | None,
        typer.Option(
            "--settings",
            "-s",
            dir_okay=False,
            file_okay=True,
            help="Override Claude Code settings path (default: ~/.claude/settings.json).",
        ),
    ] = None,
    command: Annotated[
        str,
        typer.Option(
            "--command",
            "-c",
            help="Command to register under the Stop hook.",
        ),
    ] = DEFAULT_HOOK_COMMAND,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Write to disk. Defaults to dry-run — prints the would-be merged JSON.",
        ),
    ] = False,
    backup: Annotated[
        bool,
        typer.Option(
            "--backup/--no-backup",
            help="Write a timestamped .bak copy before mutating an existing file.",
        ),
    ] = True,
) -> None:
    """Install the Claude Code Stop hook into ``~/.claude/settings.json``.

    Idempotent: if the target command is already registered the run is a
    no-op. Default is ``--dry-run`` — pass ``--apply`` to write.
    """
    target = settings or default_claude_settings_path()

    if not apply:
        try:
            raw = target.read_text(encoding="utf-8") if target.is_file() else ""
        except OSError as exc:
            typer.secho(f"hook install: cannot read {target}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        existing = json.loads(raw) if raw.strip() else {}
        if not isinstance(existing, dict):
            typer.secho(
                f"hook install: {target} is not a JSON object at the top level.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)
        plan = plan_install(existing, command=command)
        typer.echo(f"hook install (dry-run): {plan.reason}")
        typer.echo(f"target: {target}")
        typer.echo("--- proposed settings.json ---")
        typer.echo(json.dumps(plan.merged, indent=2, sort_keys=True))
        typer.echo("--- end ---")
        typer.echo("re-run with --apply to write.")
        raise typer.Exit(code=0)

    try:
        result = apply_install(target, command=command, backup=backup)
    except (OSError, ValueError) as exc:
        typer.secho(f"hook install: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    if not result.wrote:
        typer.echo(f"hook install: {result.plan.reason} (no change)")
        raise typer.Exit(code=0)

    msg = f"hook install: {result.plan.reason} at {result.path}"
    if result.backup is not None:
        msg += f" (backup: {result.backup})"
    typer.secho(msg, fg=typer.colors.GREEN)
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
