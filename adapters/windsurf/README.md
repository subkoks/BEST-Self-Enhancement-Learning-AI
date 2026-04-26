# Windsurf adapter

Wires the [`bsela-mcp`](../../mcp/) stdio server into Windsurf's MCP
config. Read-only tools (`bsela_route`, `bsela_audit`, `bsela_status`)
become callable inside any Windsurf / Cascade session.

## Prerequisites

See [`adapters/README.md`](../README.md#prerequisites-shared-across-all-editors).
`bsela` must be on `PATH` and `mcp/dist/server.js` must exist.

## Install

1. Build the MCP server if you have not already:

   ```bash
   cd <BSELA_REPO>/mcp
   pnpm install --frozen-lockfile
   pnpm build
   ```

2. Open `~/.codeium/windsurf/mcp_config.json`. Merge the `bsela`
   entry from [`mcp_config.json`](mcp_config.json) into the existing
   `mcpServers` map. Replace `<BSELA_REPO>` with the absolute path to
   this repo (e.g. `/Users/<you>/Projects/Current/Active/BEST-Self-Enhancement-Learning-AI`).

3. Windsurf inherits the GUI's `PATH`, so the `env.PATH` field is
   only required if `bsela` or `node` is not on the launchd-inherited
   `PATH`. If `bsela doctor` works from the Windsurf-launched
   terminal, you can omit the `env` block. Otherwise keep it and
   point at the directories holding `bsela` and Node 22 LTS.

4. Restart Windsurf (or use the MCP refresh action in Cascade
   settings) so it re-reads the config.

## Verify

Inside a Cascade session, ask Windsurf to call `bsela_status`. You
should see the same store counts that `bsela status` prints from the
shell.

If Windsurf reports the tool is missing, the most common cause is the
GUI not seeing `bsela` on `PATH` — set `env.PATH` explicitly per
step 3.

## Notes

- Windsurf already keeps timestamped backups of `mcp_config.json`
  (e.g. `mcp_config.json.bak-YYYYMMDD`) when its UI rewrites the file.
  Manual edits are safe so long as the JSON stays valid.
- Updating BSELA: re-run `pnpm build` in `mcp/` after pulling.
  Windsurf re-spawns the server when you reload the workspace; no
  config change needed.
- This snippet matches the shape Cursor and Claude Desktop also
  consume (`mcpServers` map keyed by server name) — if you wire
  Cursor next, reuse the JSON object verbatim and drop it into
  `~/.cursor/mcp.json`.
