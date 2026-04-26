# Codex CLI — BSELA MCP adapter

Registers the read-only [`bsela-mcp`](../../mcp/) stdio server so Codex can call `bsela_route`, `bsela_audit`, and `bsela_status`. Spec: [ADR 0006](../../docs/decisions/0006-p6-mcp-and-adapters.md).

## Prerequisites

- Node.js 22+ and `pnpm` (see [`mcp/README.md`](../../mcp/README.md)).
- `bsela` on `PATH`: from repo root, `uv sync && uv tool install -e .`, then `bsela doctor`.
- Built server: `cd mcp && pnpm install --frozen-lockfile && pnpm build`. Note the absolute path to `mcp/dist/server.js`.

## Option A — `codex mcp add` (recommended)

From any directory (adjust paths to your clone):

```bash
codex mcp add bsela -- node /absolute/path/to/BEST-Self-Enhancement-Learning-AI/mcp/dist/server.js
```

Use `codex mcp list` to confirm. Approve tools in the Codex UI the first time if prompted.

## Option B — `~/.codex/config.toml`

Add a table (use your real path):

```toml
[mcp_servers.bsela]
command = "node"
args = ["/absolute/path/to/BEST-Self-Enhancement-Learning-AI/mcp/dist/server.js"]
# Read-only tools; parallel calls are optional — leave default unless you measure safe overlap.
```

Restart Codex after editing. Full MCP options: [Codex config docs](https://github.com/openai/codex/blob/main/docs/config.md).

## Smoke test

In Codex, ask the agent to use the BSELA MCP tool `bsela_status` and confirm counts print. If the server fails to start, verify `node` resolves, the `dist/server.js` path exists, and `which bsela` succeeds in the same environment Codex uses.
