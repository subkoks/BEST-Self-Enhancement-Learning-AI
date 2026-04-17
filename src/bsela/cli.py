"""BSELA command-line interface.

P1 wires ``bsela ingest`` and ``bsela status`` to the capture pipeline +
SQLite memory store. ``review`` and ``rollback`` stay stubbed until P3/P7.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from bsela import __version__
from bsela.core.capture import ingest_file
from bsela.core.retention import sweep
from bsela.memory.store import (
    bsela_home,
    count_lessons,
    count_sessions,
    db_path,
    list_errors,
)

app = typer.Typer(
    name="bsela",
    help="Best Self-Enhancement Learning Agent — control plane for coding AI agents.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
hook_app = typer.Typer(
    name="hook",
    help="Hook entrypoints invoked by editor integrations.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(hook_app, name="hook")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"bsela {__version__}")
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
        console.print(
            f"[yellow]status:[/yellow] no store at {home} yet — "
            "run [bold]bsela ingest[/bold] first."
        )
        raise typer.Exit(code=0)

    sessions_total = count_sessions()
    sessions_quarantined = count_sessions(status="quarantined")
    errors_total = len(list_errors(limit=10_000))
    lessons_pending = count_lessons(status="pending")
    lessons_total = count_lessons()

    console.print(f"[bold]BSELA home:[/bold] {home}")
    console.print(f"sessions: {sessions_total} (quarantined: {sessions_quarantined})")
    console.print(f"errors:   {errors_total}")
    console.print(f"lessons:  {lessons_total} (pending: {lessons_pending})")
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
        console.print(f"[red]quarantined[/red] {result.session_id}: {result.quarantine_reason}")
        raise typer.Exit(code=0)

    console.print(
        f"[green]captured[/green] {result.session_id} "
        f"turns={result.turn_count} tool_calls={result.tool_call_count}"
    )
    raise typer.Exit(code=0)


@app.command()
def review() -> None:
    """List pending rule-change proposals awaiting approval."""
    console.print("[yellow]review:[/yellow] not implemented (P3).")
    raise typer.Exit(code=0)


@app.command()
def rollback(
    lesson_id: Annotated[str, typer.Argument(help="Lesson identifier to revert.")],
) -> None:
    """Revert a previously applied lesson."""
    console.print(f"[yellow]rollback[/yellow] {lesson_id}: not implemented (P7).")
    raise typer.Exit(code=0)


@app.command()
def prune() -> None:
    """Drop sessions + errors older than the retention windows in thresholds.toml."""
    result = sweep()
    console.print(f"pruned sessions: {result.sessions_deleted}  errors: {result.errors_deleted}")
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


if __name__ == "__main__":
    app()
