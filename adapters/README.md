# `adapters/` — editor wiring for the `bsela-mcp` server

Per [ADR 0006](../docs/decisions/0006-p6-mcp-and-adapters.md), the
TypeScript MCP server in [`mcp/`](../mcp/) is the single seam every
editor talks to. This directory holds the per-editor config snippets
that point each editor at the same `bsela-mcp` stdio binary.

Everything here is config-only. Tool schemas, transport, and behavior
live in [`mcp/`](../mcp/) — adapters never re-implement BSELA logic.

## Prerequisites (shared across all editors)

1. `bsela` on `PATH` — `uv sync && uv tool install -e .` from the repo
   root, then `bsela doctor` to verify.
2. `mcp/` built — `cd mcp && pnpm install --frozen-lockfile && pnpm build`.
   Confirm `mcp/dist/server.js` exists and is executable.
3. Note the absolute path of `mcp/dist/server.js` — every snippet below
   substitutes it as `<BSELA_REPO>/mcp/dist/server.js`.

## Editors

| Editor         | Snippet                                                                                                             | Target config file                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Codex CLI      | [`codex/config.toml`](codex/config.toml)                                                                            | `~/.codex/config.toml`                                                            |
| Windsurf       | [`windsurf/mcp_config.json`](windsurf/mcp_config.json)                                                              | `~/.codeium/windsurf/mcp_config.json`                                             |
| Claude Code    | [`claude/README.md`](claude/README.md) (hook + MCP + local permissions)                                             | `~/.claude/settings.json` + optional repo `.claude/settings.local.json`           |
| Claude Desktop | [`mcp/README.md`](../mcp/README.md#running-the-mcp-server)                                                          | Desktop MCP config (same `mcpServers` shape as in `claude/settings.example.json`) |
| Cursor         | (not yet wired — Cursor speaks MCP via the same JSON shape as Claude Desktop; reuse the snippet in `mcp/README.md`) | `~/.cursor/mcp.json`                                                              |

The Codex + Windsurf snippets are the two adapters formally tracked
under P6. Others are documented inline.

## Tools exposed (read-only, P6)

| Tool            | Inputs                          | Returns              |
| --------------- | ------------------------------- | -------------------- |
| `bsela_route`   | `task: string`                  | `RouteDecision` JSON |
| `bsela_audit`   | `window_days?: number (1..365)` | audit JSON payload   |
| `bsela_status`  | —                               | status JSON payload  |
| `bsela_lessons` | `status?: enum, limit?: number` | lessons JSON array   |

Write surfaces (`bsela ingest`, `review propose`, `decision add`,
`hook install`) stay CLI-only until the read surfaces have telemetry.
That cap is set by ADR 0006 — re-open under "Re-open Condition".

## Verifying an adapter is live

After wiring an editor, the fastest end-to-end check is to ask the
editor to call `bsela_status`. A healthy response includes:

```
{
  "sessions": <n>,
  "errors": <n>,
  "lessons": <n>,
  "bsela_home": "/Users/<you>/.bsela"
}
```

If the tool errors with "bsela not found on PATH", revisit step 1 of
the prerequisites — the MCP server shells out to `bsela` per ADR 0006.
