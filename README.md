# BSELA — Best Self-Enhancement Learning Agent

A local control plane that makes existing coding agents (Claude Code, Codex, Windsurf, Cursor) measurably better over time.

BSELA captures every session, distills recurring failures into durable rules, proposes updates against the canonical `agents-md` repo, and routes new tasks to the right model. It is not a new model, not a new IDE — it is the **self-improving context + harness layer** the existing stack is missing.

## Status

P0–P3 complete. **P4 — MVP Dogfood** is active: live ingestion, metric collection, and threshold tuning. See [`docs/roadmap.md`](docs/roadmap.md).

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
bsela ingest <transcript.jsonl>           # capture a session into the store
bsela detect [--session-id <id>]          # run the deterministic error detector
bsela distill --session-id <id>           # judge + distill (needs ANTHROPIC_API_KEY)
bsela review                              # list pending lessons with AUTO/REVIEW/SAFETY tags
bsela review propose <lesson-id>          # write a proposal branch on agents-md
bsela review reject  <lesson-id> -n ...   # reject a pending lesson with a note
bsela report [--window-days 7] [--stdout] # P4 dogfood report → ~/.bsela/reports/dogfood.md
bsela status                              # session / error / lesson counts
bsela prune                               # drop rows outside retention windows
bsela hook install [--apply]              # wire the Claude Code Stop hook (dry-run by default)
```

Auto-ingestion: `bsela hook install` previews the merged
`~/.claude/settings.json`; add `--apply` to write it (a timestamped
`.bak` is left alongside). See [`docs/architecture.md`](docs/architecture.md)
for the full pipeline and [`config/thresholds.toml`](config/thresholds.toml)
for tunables.

## Architecture

See [`docs/architecture.md`](docs/architecture.md).

## Decisions

Architectural decision records live in [`docs/decisions/`](docs/decisions/).

## License

MIT — see [`LICENSE`](LICENSE).
