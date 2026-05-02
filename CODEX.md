# BSELA — Codex CLI handoff

## Read first

1. `[AGENTS.md](AGENTS.md)` — project invariants, commit scopes, quality gate.
2. `[docs/roadmap.md](docs/roadmap.md)` — phase order; **P6** is active for MCP + adapters.
3. `[docs/decisions/0006-p6-mcp-and-adapters.md](docs/decisions/0006-p6-mcp-and-adapters.md)` — MCP design and adapter expectations.

## Quality gate before you ship

- Python: `make check` (ruff, mypy, pytest).
- TypeScript MCP: `cd mcp && pnpm check`; server entry is `mcp/dist/server.js` after `pnpm build`.

## Wire BSELA into Codex

Index: `[adapters/README.md](adapters/README.md)`. Codex-specific steps:
`[adapters/codex/README.md](adapters/codex/README.md)` (includes `codex mcp add` and a `config.toml` template). `bsela` must be on `PATH` (`uv tool install -e .` from repo root).

## Suggested next build (P6)

1. **Cross-editor dogfood** — run one real Codex session and one real Claude Code session against the same `~/.bsela` store, then record parity/notes in `docs/roadmap.md`.
2. **MCP parity checks** — verify `bsela_route` / `bsela_audit` / `bsela_status` / `bsela_lessons` results match shell `bsela route|audit|status|lessons` output in both editors.
3. Optional: keep CLI↔MCP contract parity tests current (`route`, `audit`, `status`, `lessons`) whenever payload fields change.
