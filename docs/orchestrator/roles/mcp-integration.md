# Role: MCP / Integration

You own **`mcp/`** TypeScript, **adapter snippets** under `adapters/`, and **contract parity** with the Python CLI.

## Mandatory gate

After substantive `mcp/` or contract changes:

```bash
cd mcp && pnpm check && pnpm build
```

From repo root, `make mcp-check` runs the same commands (gate plus `dist/server.js` for editors).

## Also run when

- MCP tool names, args, or JSON payloads change.
- Python CLI output shape changes and parity tests live under `mcp/`.

## Typical tasks

- Align README tables in `adapters/*` with actual tools (`bsela_route`, `bsela_audit`, `bsela_status`, `bsela_lessons`).
- Run or extend parity harness: `make mcp-parity` when CLI↔MCP drift is in scope.

## Handoff back

- `pnpm check` result.
- Any `pnpm parity` result if run.
- Note server entry path (`mcp/dist/server.js` after build) if operators must reconfigure editors.
