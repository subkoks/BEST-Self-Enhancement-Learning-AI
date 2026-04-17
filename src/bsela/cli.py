"""BSELA command-line interface.

P0 scaffold: commands are declared but return stubs. Logic lands in P1-P3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from bsela import __version__

app = typer.Typer(
    name="bsela",
    help="Best Self-Enhancement Learning Agent — control plane for coding AI agents.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
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
    console.print("[yellow]status:[/yellow] not implemented (P1).")
    raise typer.Exit(code=0)


@app.command()
def ingest(
    path: Annotated[
        Path,
        typer.Argument(
            exists=False,
            dir_okay=False,
            file_okay=True,
            readable=True,
            help="Path to a session transcript (JSONL).",
        ),
    ],
) -> None:
    """Ingest one session transcript into the BSELA store."""
    console.print(f"[yellow]ingest[/yellow] {path}: not implemented (P1).")
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


if __name__ == "__main__":
    app()
