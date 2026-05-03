# Cursor — BSELA MCP adapter

Wires the BSELA MCP server into Cursor via the `~/.cursor/mcp.json` config.

For **multi-session / role-scoped** work in this repo, use the markdown orchestrator: start from [`docs/orchestrator/ORCHESTRATOR.md`](../../docs/orchestrator/ORCHESTRATOR.md) and the role index in [`docs/orchestrator/README.md`](../../docs/orchestrator/README.md) (see [ADR 0008](../../docs/decisions/0008-developer-orchestrator-workflow.md)).

## Prerequisites

1. `bsela` on `PATH` — `uv sync && uv tool install -e .` from the repo root
2. MCP server built — `cd mcp && pnpm install --frozen-lockfile && pnpm build`
3. Confirm `mcp/dist/server.js` exists

## Open this repo in Cursor (recommended)

For the fewest editor quirks (including false **GitHub Actions** diagnostics on workflow YAML), open the multi-root workspace file instead of only the folder:

**File → Open Workspace from File… → choose [`bsela.code-workspace`](../../bsela.code-workspace)** at the repo root.

That workspace embeds the same `files.associations` / `github-actions.use-enterprise` defaults as [`.vscode/settings.json`](../../.vscode/settings.json). After opening, run **Developer: Reload Window** once if the status bar still shows **GitHub Actions Workflow** for files under `.github/workflows/`.

If **Source Control / Git** reports that `.vscode/settings.json` is ignored, your `~/.gitignore_global` likely contains `.vscode/`. Either run `git add -f .vscode/settings.json` when that file changes, or remove `.vscode/` from the global ignore so the tracked file stages normally.

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
- **Problems: “Unable to resolve action …” on `.github/workflows/*.yml`** — False positives from the GitHub Actions extension when it cannot resolve `uses:` via the API (auth, rate limits, or [extension bugs](https://github.com/github/vscode-github-actions/issues/433)). Prefer opening [`bsela.code-workspace`](../../bsela.code-workspace); otherwise rely on [`.vscode/settings.json`](../../.vscode/settings.json) (`files.associations` → plain `yaml`). Reload the window (**Developer: Reload Window**). If the status bar still says **GitHub Actions Workflow**, use **Change Language Mode** (`Cmd/Ctrl+K` then `M`) → **YAML** once, or **Extensions → GitHub Actions → Disable (Workspace)**. Confirm the folder is **Workspace Trusted** and you are signed in to GitHub under **Accounts** if you keep the extension enabled.
