# BSELA — Codex CLI handoff

## Read first

1. `[AGENTS.md](AGENTS.md)` — project invariants, commit scopes, quality gate.
2. `[docs/roadmap.md](docs/roadmap.md)` — phase order; **P0–P7 shipped**; MCP + adapters remain the main integration surface for editors.
3. `[docs/decisions/0006-p6-mcp-and-adapters.md](docs/decisions/0006-p6-mcp-and-adapters.md)` — MCP design and adapter expectations.
4. Optional multi-role workflow: `[docs/orchestrator/README.md](docs/orchestrator/README.md)` (lead: `[docs/orchestrator/ORCHESTRATOR.md](docs/orchestrator/ORCHESTRATOR.md)`; ADR [0008](docs/decisions/0008-developer-orchestrator-workflow.md)).
5. Agent SDK posture: `[docs/decisions/0009-claude-agent-sdk-non-adoption.md](docs/decisions/0009-claude-agent-sdk-non-adoption.md)`.

## Quality gate before you ship

- Python: `make check` (ruff, mypy, pytest).
- Health: `make doctor` (`uv run bsela doctor` — PATH, store, hook, agents-md).
- TypeScript MCP: `make mcp-check` (runs `pnpm check` then `pnpm build`) or `cd mcp && pnpm check && pnpm build`; server entry is `mcp/dist/server.js`.

## Wire BSELA into Codex

Index: `[adapters/README.md](adapters/README.md)`. Codex-specific steps:
`[adapters/codex/README.md](adapters/codex/README.md)` (includes `codex mcp add` and a `config.toml` template). `bsela` must be on `PATH` (`uv tool install -e .` from repo root).

## Suggested steady-state ops (post-P7)

P0–P7 are shipped; prioritize operator work from [`docs/roadmap.md`](docs/roadmap.md) **Next Action** (hook, ingest/process, review/propose, report, thresholds with ADR when gates move, cross-editor MCP depth).

1. **Cross-editor dogfood** — run real Codex, Cursor, Windsurf, and Claude Code sessions against the same `~/.bsela` store; record parity or gaps in the roadmap or [ADR 0006](docs/decisions/0006-p6-mcp-and-adapters.md) notes.
2. **MCP parity** — confirm `bsela_route` / `bsela_audit` / `bsela_status` / `bsela_lessons` match `bsela route|audit|status|lessons`; run `make mcp-parity` when CLI or MCP payloads change.
3. Keep CLI↔MCP contract tests in `mcp/` current whenever tool fields change.
