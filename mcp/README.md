# @bsela/mcp

TypeScript package hosting the future BSELA MCP server and the thin
CLI client it is built on. Part of P6 per
[ADR 0006](../docs/decisions/0006-p6-mcp-and-adapters.md).

## Status

- `BselaClient` — shells out to the `bsela` Python CLI and parses
  JSON / text. First tools covered: `route`, `audit`, `status`.
- MCP server binary `bsela-mcp` — implemented. Stdio transport,
  three read-only tools (`bsela_route`, `bsela_audit`,
  `bsela_status`). Built artefact at `dist/server.js`.
- Codex / Windsurf adapters — deferred; land under `../adapters/`
  in a follow-up.

## Prerequisites

- Node.js 22 LTS (this workspace is tested on Node 22+ per
  `engines`).
- `pnpm` 10+.
- `bsela` on `PATH` — follow the Python quickstart in the root
  `README.md` (`uv sync && uv tool install -e .`). `bsela doctor`
  will tell you if anything is missing.

## Install and test

```bash
cd mcp
pnpm install --frozen-lockfile
pnpm test
```

The `bsela-client.test.ts` suite is integration-style — it shells
out to the installed `bsela` CLI. The `server-tools.test.ts` and
`server.test.ts` suites are unit tests over a stubbed
`BselaClient`. If `bsela` is not on `PATH`, the integration tests
fail fast and the error message points back here.

## Running the MCP server

```bash
pnpm build
node dist/server.js          # stdio transport — read JSON-RPC on stdin
```

Or, after `pnpm install` in a downstream package, the `bin` entry
exposes `bsela-mcp` directly. Editors point at it like any other
stdio MCP server. Example Claude Desktop config snippet:

```json
{
  "mcpServers": {
    "bsela": {
      "command": "node",
      "args": ["/absolute/path/to/mcp/dist/server.js"]
    }
  }
}
```

`bsela` must be on `PATH` for the same reason it has to be for the
Claude Code Stop hook — the server shells out to it. `bsela
doctor` validates this.

### Tools exposed

| Tool | Inputs | Returns |
|---|---|---|
| `bsela_route` | `task: string` | JSON `RouteDecision` (text + structuredContent) |
| `bsela_audit` | `window_days?: number (1..365)` | Audit markdown (raw text) |
| `bsela_status` | — | Store counts + bsela home (raw text) |

## Other scripts

```bash
pnpm typecheck      # tsc --noEmit
pnpm build          # emit dist/
pnpm lint           # eslint
pnpm format         # prettier --write
pnpm format:check   # prettier --check
pnpm check          # format:check + lint + typecheck + test
```

## Layout

```
mcp/
├── src/
│   ├── bsela-client.ts    # child_process wrapper around the bsela CLI
│   ├── server-tools.ts    # tool handlers (pure: client + args -> result)
│   ├── server.ts          # MCP server entry point (stdio transport)
│   └── index.ts           # named exports
├── tests/
│   ├── bsela-client.test.ts   # integration: shells to real bsela
│   ├── server-tools.test.ts   # unit: stubbed client
│   └── server.test.ts         # end-to-end: in-memory MCP transport
├── package.json
├── tsconfig.json
├── tsconfig.build.json
├── vitest.config.ts
├── eslint.config.js
├── .prettierrc.json
└── .gitignore
```

## Design notes

- The client is the *seam*. The Python core owns all logic; this
  package is strictly a transport / adaptation layer.
- `route` is the only typed path today. `audit` and `status` return
  raw markdown/text because the Python CLI doesn't emit JSON for
  those commands yet — adding JSON output is a small follow-up on
  the Python side, not a TS side change.
- Errors surface as `BselaClientError` with the exit code and a
  truncated stderr snippet. No rethrown unknowns.
