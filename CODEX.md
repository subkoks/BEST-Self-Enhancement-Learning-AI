# BSELA — Codex CLI handoff

## Read first

1. [`AGENTS.md`](AGENTS.md) — project invariants, commit scopes, quality gate.
2. [`docs/roadmap.md`](docs/roadmap.md) — phase order; **P6** is active for MCP + adapters.
3. [`docs/decisions/0006-p6-mcp-and-adapters.md`](docs/decisions/0006-p6-mcp-and-adapters.md) — MCP design and adapter expectations.

## Quality gate before you ship

- Python: `make check` (ruff, mypy, pytest).
- TypeScript MCP: `cd mcp && pnpm check`; server entry is `mcp/dist/server.js` after `pnpm build`.

## Wire BSELA into Codex

Follow [`adapters/codex/README.md`](adapters/codex/README.md) — register the stdio MCP server in `~/.codex/config.toml` (or `codex mcp add`). `bsela` must be on `PATH` (`uv tool install -e .` from repo root).

## Suggested next build (P6)

1. **Windsurf adapter** — mirror `adapters/codex/` under `adapters/windsurf/` with editor-specific paths.
2. **Dogfood** — one real Codex session calling `bsela_route` / `bsela_audit` / `bsela_status` against live data; note it in the roadmap when done.
3. Optional: JSON output on the Python side for `bsela audit` / `bsela status` to tighten the MCP contract (ADR 0006 mentions this follow-up).
