# BSELA — Best Self-Enhancement Learning Agent

A local control plane that makes existing coding agents (Claude Code, Codex, Windsurf, Cursor) measurably better over time.

BSELA captures every session, distills recurring failures into durable rules, proposes updates against the canonical `agents-md` repo, and routes new tasks to the right model. It is not a new model, not a new IDE — it is the **self-improving context + harness layer** the existing stack is missing.

## Status

P0–P3 complete. **P4 — MVP Dogfood** is active: live ingestion, metric collection, and threshold tuning. **P5 — Router + Auditor** is scaffolded per [ADR 0005](docs/decisions/0005-p5-router-and-auditor.md). **P6 — MCP server** (TypeScript) is wired per [ADR 0006](docs/decisions/0006-p6-mcp-and-adapters.md): the `bsela-mcp` stdio binary ships four read-only tools (`bsela_route`, `bsela_audit`, `bsela_status`, `bsela_lessons`) — see [`mcp/`](mcp/). **Codex + Windsurf** adapter snippets live under [`adapters/`](adapters/); for a short Codex-only continuation brief see [`CODEX.md`](CODEX.md). Only real-editor dogfood validation still gates "P6 shipped". Full phase status in [`docs/roadmap.md`](docs/roadmap.md).

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

MCP gate: `make mcp-check` runs `pnpm check` in `mcp/`.
`make mcp-parity` runs the CLI↔MCP parity harness (`route`,
`audit`, `status`, `lessons`).

## Architecture

See [`docs/architecture.md`](docs/architecture.md).

## Decisions

Architectural decision records live in [`docs/decisions/`](docs/decisions/).

## License

MIT
