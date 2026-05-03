# BSELA — Best Self-Enhancement Learning Agent

A local control plane that makes existing coding agents (Claude Code, Codex, Windsurf, Cursor) measurably better over time.

BSELA captures every session, distills recurring failures into durable rules, proposes updates against the canonical `agents-md` repo, and routes new tasks to the right model. It is not a new model, not a new IDE — it is the **self-improving context + harness layer** the existing stack is missing.

## Status

**P0–P7 are complete** per [`docs/roadmap.md`](docs/roadmap.md): capture through replay, drift alarms, rollback, and the TypeScript MCP server ([ADR 0006](docs/decisions/0006-p6-mcp-and-adapters.md)) with four read-only tools in [`mcp/`](mcp/), plus editor wiring under [`adapters/`](adapters/) (Claude Code: [`adapters/claude/README.md`](adapters/claude/README.md); Codex/Windsurf: per-editor folders there). Ongoing operator work is dogfood, threshold tuning, and cross-editor MCP validation — see the **Next Action** section in the roadmap. Quick Codex handoff: [`CODEX.md`](CODEX.md).

## Mission

Move improvement out of the model weights (expensive, slow, wrong leverage) into two layers you actually control:

1. **Harness** — hooks, routing, gating, scheduling.
2. **Context** — typed, versioned, deduplicated memory across sessions.

Every failed or wasteful session becomes a candidate lesson. Every lesson becomes a rule-change proposal. Every approved proposal flows through the existing `agents-md` canonical repo and syncs to all six editor targets.

## Quickstart

```bash
uv sync
uv tool install -e .
bsela --help
```

Core commands:

```bash
bsela ingest <transcript.jsonl>           # capture → scrub → auto-detect in one step
bsela detect [--session-id <id>]          # re-run the deterministic detector manually
bsela distill --session-id <id>           # judge + distill one session (needs ANTHROPIC_API_KEY)
bsela process [-n 10] [-d 7]              # batch-distill recent captures (needs ANTHROPIC_API_KEY)
bsela review                              # list pending lessons with AUTO/REVIEW/SAFETY tags
bsela lessons [--json]                   # top-level alias for `bsela review list`
bsela review show <lesson-id>           # display lesson details (rule, why, how_to_apply)
bsela review propose <lesson-id>          # write a proposal branch on agents-md
bsela review reject  <lesson-id> -n ...   # reject a pending lesson with a note
bsela report [--window-days 7] [--stdout] # P4 dogfood report → ~/.bsela/reports/dogfood.md
bsela status                              # session / error / lesson counts
bsela sessions list [--status captured]   # list captured sessions, newest first
bsela sessions show <session-id>          # metadata + detected errors for one session
bsela errors list [--session-id <id>]     # list detected error records
bsela prune                               # drop rows outside retention windows
bsela doctor                              # environment health check (API key, hook, agents-md repo)
bsela hook install [--apply]              # wire the Claude Code Stop hook (dry-run by default)
bsela decision add "<title>" -c ... -d ... -x ...  # log a load-bearing autonomous decision
bsela decision list [-n 20]               # show recent decisions, newest first
bsela route "<task>" [--json]             # P5 router: classify task → model role
bsela audit [--weekly|--window-days N] [--stdout|--json]  # P5 weekly audit digest (markdown or JSON)
bsela replay <session-id> [--no-save]   # P7: re-distill vs stored lessons; exit 1 on drift (needs API key)
bsela rollback <lesson-id> [-n "..."]     # P7: soft-mark lesson rolled_back (local store only)
```

The detector now runs inline during `bsela ingest` (and therefore during
the Stop hook), so error rows land without a second command — set
`--no-auto-detect` on the library call only if you need to decouple the
two. `bsela process` batches judge+distill over recent captured
sessions, skipping anything quarantined, error-free, or already
distilled.

Auto-ingestion: `bsela hook install` previews the merged
`~/.claude/settings.json`; add `--apply` to write it (a timestamped
`.bak` is left alongside). See [`docs/architecture.md`](docs/architecture.md)
for the full pipeline and [`config/thresholds.toml`](config/thresholds.toml)
for tunables.

Developer gate: `make check` runs the full local gate
(ruff check → ruff format --check → mypy → pytest). `make fix`
auto-resolves what ruff can. The same checks run in CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) on every push
to `main` and every PR.

Health: `make doctor` runs `uv run bsela doctor` (Python, `bsela` on
`PATH`, API key, `~/.bsela` store, agents-md repo, Claude Stop hook).

MCP gate: `make mcp-check` runs `pnpm check` then `pnpm build` in `mcp/`
(so `dist/server.js` exists for editor MCP configs).
`make mcp-parity` runs the CLI↔MCP parity harness (`route`,
`audit`, `status`, `lessons`).

**Agent orchestrator (optional):** repo-local lead + role prompts live
under [`docs/orchestrator/`](docs/orchestrator/README.md). Run
`make orchestrator-help` for paths. See
[ADR 0008](docs/decisions/0008-developer-orchestrator-workflow.md).

**GitHub `@claude` (optional):** install the Claude GitHub App, add
`ANTHROPIC_API_KEY` (or OAuth token) to Actions secrets, then use `@claude` on
PRs/issues. See [adapters/claude/README.md §7](adapters/claude/README.md).

**Terminal noise (pyenv):** If the integrated terminal shows
`pyenv: shell integration not enabled`, add the hook from
[pyenv shell setup](https://github.com/pyenv/pyenv#shell-setup)
(`eval "$(pyenv init -)"` in `~/.zshrc`) and open a new terminal. For this
repo, prefer **`uv run …`** and **`.venv`** after `uv sync` instead of
`pyenv shell`.

## Architecture

See [`docs/architecture.md`](docs/architecture.md).

## Decisions

Architectural decision records live in [`docs/decisions/`](docs/decisions/).

## License

MIT
