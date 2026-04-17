# BSELA — Best Self-Enhancement Learning Agent

A local control plane that makes existing coding agents (Claude Code, Codex, Windsurf, Cursor) measurably better over time.

BSELA captures every session, distills recurring failures into durable rules, proposes updates against the canonical `agents-md` repo, and routes new tasks to the right model. It is not a new model, not a new IDE — it is the **self-improving context + harness layer** the existing stack is missing.

## Status

P0 — bootstrap. No runtime logic yet. See [`docs/roadmap.md`](docs/roadmap.md).

## Mission

Move improvement out of the model weights (expensive, slow, wrong leverage) into two layers you actually control:

1. **Harness** — hooks, routing, gating, scheduling.
2. **Context** — typed, versioned, deduplicated memory across sessions.

Every failed or wasteful session becomes a candidate lesson. Every lesson becomes a rule-change proposal. Every approved proposal flows through the existing `agents-md` canonical repo and syncs to all six editor targets.

## Quickstart (coming in P1)

```bash
uv sync
uv tool install -e .
bsela --help
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md).

## Decisions

Architectural decision records live in [`docs/decisions/`](docs/decisions/).

## License

MIT — see [`LICENSE`](LICENSE).
