# Codex CLI adapter

Wires the [`bsela-mcp`](../../mcp/) stdio server into Codex CLI's MCP
config. Read-only tools (`bsela_route`, `bsela_audit`, `bsela_status`)
become callable inside any Codex session.

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

2. Open `~/.codex/config.toml`. Codex stores MCP servers under
   `[mcp_servers.<name>]` tables. Append the block from
   [`config.toml`](config.toml), substituting `<BSELA_REPO>` with the
   absolute path to this repo (e.g. `/Users/<you>/Projects/Current/Active/BEST-Self-Enhancement-Learning-AI`).

3. Confirm Node 22 LTS is on the `PATH` you give the server. The
   snippet defaults to `/usr/local/bin:/usr/bin:/bin` plus the nvm
   Node 22 path — adjust if your machine differs. The MCP server also
   needs `bsela` reachable via that same `PATH`, so include the
   directory holding the `bsela` binary (typically `~/.local/bin`).

4. Restart Codex CLI so it re-reads `config.toml`.

## Verify

Inside a Codex session, ask the model to call `bsela_status`. You
should see the same store counts that `bsela status` prints from the
shell.

If Codex reports the tool is missing, run:

```bash
node <BSELA_REPO>/mcp/dist/server.js
```

manually and check the process boots without errors. Then re-check
that `[mcp_servers.bsela]` is present in `~/.codex/config.toml` and
that the `command` / `args` paths are absolute.

## Notes

- The snippet uses `node` + an absolute `args` path rather than the
  package's `bsela-mcp` bin, because the workspace is not published to
  npm and Codex resolves `command` against `PATH`. Pointing at
  `dist/server.js` directly avoids requiring a global install.
- Updating BSELA: re-run `pnpm build` in `mcp/` after pulling. Codex
  re-spawns the server on each session, so no Codex restart is needed
  unless you change `config.toml` itself.
