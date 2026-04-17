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
from bsela.core.detector import detect_errors
from bsela.core.retention import sweep
from bsela.llm.client import AnthropicClient
from bsela.llm.distiller import distill_session
from bsela.memory.store import (
    bsela_home,
    count_lessons,
    count_sessions,
    db_path,
    list_errors,
    list_sessions,
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
        console.print(f"session {result.session_id}: {len(result.errors)} candidate errors")
        raise typer.Exit(code=0)

    targets = [s for s in list_sessions(status="captured", limit=10_000)]
    total = 0
    for sess in targets:
        result = detect_errors(sess.id)
        total += len(result.errors)
    console.print(f"scanned {len(targets)} sessions, found {total} candidate errors")
    raise typer.Exit(code=0)


@app.command()
def prune() -> None:
    """Drop sessions + errors older than the retention windows in thresholds.toml."""
    result = sweep()
    console.print(f"pruned sessions: {result.sessions_deleted}  errors: {result.errors_deleted}")
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
        console.print(
            f"session {session_id}: judge says healthy "
            f"(confidence={result.verdict.confidence:.2f}); no lessons distilled."
        )
        raise typer.Exit(code=0)
    console.print(
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


if __name__ == "__main__":
    app()
