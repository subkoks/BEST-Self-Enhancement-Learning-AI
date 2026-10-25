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

## Current maintenance

Read [provider maintenance](docs/provider-maintenance.md) and
[ADR 0013](docs/decisions/0013-provider-maintenance.md).
Codex GPT-6.1 Sol via ChatGPT login is primary; DeepSeek Flash is manual.
Source defaults disable live calls until the canary and isolation gates pass.
Keep historical editor capture adapters; new setup targets Codex and VS Code.
Run make mcp-parity when CLI/MCP fields change.
