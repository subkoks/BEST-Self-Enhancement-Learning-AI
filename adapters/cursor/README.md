# Cursor — BSELA MCP adapter

Wires the BSELA MCP server into Cursor via the `~/.cursor/mcp.json` config.

## Prerequisites

1. `bsela` on `PATH` — `uv sync && uv tool install -e .` from the repo root
2. MCP server built — `cd mcp && pnpm install --frozen-lockfile && pnpm build`
3. Confirm `mcp/dist/server.js` exists

## Wiring

1. Copy or symlink [`mcp.json`](mcp.json) to `~/.cursor/mcp.json`:

    ```bash
    cp /absolute/path/to/BEST-Self-Enhancement-Learning-AI/adapters/cursor/mcp.json ~/.cursor/mcp.json
    ```

2. Edit `~/.cursor/mcp.json` and replace `<BSELA_REPO>` with the absolute path to this repo.

3. Restart Cursor or reload the window (`Cmd/Ctrl + Shift + P` → "Developer: Reload Window").

## Verify

Open Cursor's Composer (Cmd/Ctrl + I) and ask:

> "Call bsela_status and tell me my session count."

A healthy response shows:

```json
{
  "sessions": <n>,
  "errors": <n>,
  "lessons": <n>,
  "bsela_home": "/Users/<you>/.bsela"
}
```

If you see "bsela not found on PATH", revisit step 1 of prerequisites.

## Tools available

| Tool            | Purpose                                                    |
| --------------- | ---------------------------------------------------------- |
| `bsela_route`   | Classify a task into a model role (planner, builder, etc.) |
| `bsela_audit`   | Get audit digest for recent activity                       |
| `bsela_status`  | Session/error/lesson counts                                |
| `bsela_lessons` | List pending lessons with AUTO/REVIEW/SAFETY tags          |

Write surfaces (`bsela ingest`, `review propose`, etc.) stay CLI-only per [ADR 0006](../../docs/decisions/0006-p6-mcp-and-adapters.md).

## Troubleshooting

- **"command not found"** — `bsela` is not on PATH. Run `bsela doctor` to diagnose.
- **"ENOENT: dist/server.js"** — MCP server not built. Run `pnpm build` in `mcp/`.
- **Empty response** — Check the absolute path in `mcp.json` is correct and points to `mcp/dist/server.js`.
