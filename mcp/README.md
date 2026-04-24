# @bsela/mcp

TypeScript package hosting the future BSELA MCP server and the thin
CLI client it is built on. Part of P6 per
[ADR 0006](../docs/decisions/0006-p6-mcp-and-adapters.md).

## Status

- `BselaClient` — shells out to the `bsela` Python CLI and parses
  JSON / text. First tools covered: `route`, `audit`, `status`.
- MCP server binary — deferred to a follow-up commit once the tool
  schema stabilises.
- Codex / Windsurf adapters — deferred; land under `../adapters/`.

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

Tests are integration-style — they shell out to the installed
`bsela` CLI. If `bsela` is not on `PATH`, the test run fails fast
and the error message points back here.

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
│   ├── bsela-client.ts   # child_process wrapper around the bsela CLI
│   └── index.ts          # named exports
├── tests/
│   └── bsela-client.test.ts
├── package.json
├── tsconfig.json
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
