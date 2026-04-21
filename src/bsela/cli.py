"""BSELA command-line interface.

P1 wires ``bsela ingest`` and ``bsela status`` to the capture pipeline +
SQLite memory store. ``review`` and ``rollback`` stay stubbed until P3/P7.

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
from bsela.core.capture import ingest_file
from bsela.core.detector import detect_errors
from bsela.core.gate import evaluate as evaluate_gate
from bsela.core.hook_install import (
    DEFAULT_HOOK_COMMAND,
    apply_install,
    default_claude_settings_path,
    plan_install,
)
from bsela.core.report import (
    DEFAULT_RECENT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    build_report,
    render_markdown,
    write_report,
)
from bsela.core.retention import sweep
from bsela.core.updater import UpdaterError, propose_lesson
from bsela.llm.client import AnthropicClient
from bsela.llm.distiller import distill_session
from bsela.memory.models import Lesson
from bsela.memory.store import (
    bsela_home,
    count_lessons,
    count_sessions,
    db_path,
    get_lesson,
    list_errors,
    list_lessons,
    list_sessions,
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
def status() -> None:
    """Show storage metrics: sessions, errors, lessons, pending proposals."""
    home = bsela_home()
    if not db_path().exists():
        typer.echo(f"status: no store at {home} yet — run `bsela ingest` first.")
        raise typer.Exit(code=0)

    sessions_total = count_sessions()
    sessions_quarantined = count_sessions(status="quarantined")
    errors_total = len(list_errors(limit=10_000))
    lessons_pending = count_lessons(status="pending")
    lessons_total = count_lessons()

    typer.echo(f"BSELA home: {home}")
    typer.echo(f"sessions: {sessions_total} (quarantined: {sessions_quarantined})")
    typer.echo(f"errors:   {errors_total}")
    typer.echo(f"lessons:  {lessons_total} (pending: {lessons_pending})")
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
    """List pending rule-change proposals awaiting approval."""
    if ctx.invoked_subcommand is not None:
        return
    pending = list_lessons(status="pending", limit=100)
    if not pending:
        typer.echo("review: no pending lessons.")
        raise typer.Exit(code=0)
    typer.echo(f"review: {len(pending)} pending lesson(s)")
    for lesson in pending:
        typer.echo(_render_pending(lesson))
    raise typer.Exit(code=0)


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
) -> None:
    """Revert a previously applied lesson."""
    typer.echo(f"rollback {lesson_id}: not implemented (P7).")
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

    targets = [s for s in list_sessions(status="captured", limit=10_000)]
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
    typer.echo(f"pruned sessions: {result.sessions_deleted}  errors: {result.errors_deleted}")
    raise typer.Exit(code=0)


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
    client = AnthropicClient.from_config()
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
