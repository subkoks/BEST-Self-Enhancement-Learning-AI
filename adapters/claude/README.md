# Claude Code — BSELA wiring

Use this checklist once per machine. Canonical project rules stay in
[`AGENTS.md`](../../AGENTS.md); rule _text_ changes belong in the
`agents-md` repo, not in editor copies under `~/.claude/`.

## 1. Prerequisites

From the repo root:

```bash
uv sync && uv tool install -e .
bsela doctor
cd mcp && pnpm install --frozen-lockfile && pnpm build
```

Replace `<BSELA_REPO>` below with the absolute path to this repository
(for example `/Users/you/Projects/.../BEST-Self-Enhancement-Learning-AI`).

## 2. Stop hook → `bsela ingest`

Registers `bsela hook claude-stop` on Claude Code’s **Stop** event so
sessions land in `~/.bsela/` with scrub + detector.

```bash
bsela hook install              # dry-run: shows the merge plan
bsela hook install --apply      # writes ~/.claude/settings.json (+ .bak)
```

Idempotent: re-running does not duplicate the hook. See
[`src/bsela/core/hook_install.py`](../../src/bsela/core/hook_install.py)
for the exact JSON shape.

## 3. MCP server (`bsela_*` tools)

1. Copy [`settings.example.json`](settings.example.json) to a scratch file.
2. Replace `<BSELA_REPO>` in the `mcpServers.bsela.args[0]` path with your
   real repo path (must point at `mcp/dist/server.js` after `pnpm build`).
3. Merge the `mcpServers` object into **`~/.claude/settings.json`** with
   your editor (same file the hook installer uses). Keep existing keys;
   do not delete unrelated hooks or permissions.

`bsela` must stay on `PATH` — the MCP server shells out to the CLI (ADR
0006). Verify with `bsela doctor`.

## 4. Repo-local permissions (optional)

Claude Code reads **`.claude/settings.local.json`** inside the opened
project (ignored by git here). To reduce permission prompts for this
repo only:

```bash
cp adapters/claude/settings.local.example.json .claude/settings.local.json
# edit paths or tighten `Read(**)` if you use a stricter policy
```

Adjust `allow` lists to match how you actually work; the example is a
starting point, not a security review.

## 5. Cursor “Cloud Agents” (separate product)

The **Cloud Agents** screen in **Cursor Settings** (GitHub/GitLab,
Slack, team defaults) configures **Cursor-hosted agents**, not Claude
Code’s `~/.claude` files. Connect GitHub there if you want Cursor to
open PRs from cloud runs; it does not replace steps 2–4 above.

## 6. Verify

- In Claude Code, end a short session → confirm a new row under
  `bsela sessions list`.
- Ask the assistant to call MCP tool **`bsela_status`** → JSON should show
  your `bsela_home` path and counts.

## References

- [ADR 0006 — MCP + adapters](../../docs/decisions/0006-p6-mcp-and-adapters.md)
- [`mcp/README.md`](../../mcp/README.md) — build, tools table, Desktop-style MCP JSON
- [`../README.md`](../README.md) — adapter index for all editors
