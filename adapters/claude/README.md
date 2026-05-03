# Claude Code — BSELA wiring

Use this checklist once per machine. Canonical project rules stay in
[`AGENTS.md`](../../AGENTS.md); rule _text_ changes belong in the
`agents-md` repo, not in editor copies under `~/.claude/`.

## 1. Prerequisites

From the repo root:

```bash
uv sync && uv tool install -e .
make doctor
cd mcp && pnpm install --frozen-lockfile && pnpm build
make mcp-check
```

(`make doctor` is `uv run bsela doctor`; `make mcp-check` is the full MCP
workspace gate from the repo `Makefile`.)

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

## 7. GitHub — Claude Code Action (`@claude` on PRs and issues)

Workflow: [`.github/workflows/claude.yml`](../../.github/workflows/claude.yml)
([`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action)).

**One-time setup (repository admin):**

1. Install the [Claude GitHub App](https://github.com/apps/claude) on this
   repository (or organization), per Anthropic’s
   [setup guide](https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md).
2. Under **Settings → Secrets and variables → Actions**, add **`ANTHROPIC_API_KEY`**
   for direct API use in Actions. Alternatively, add **`CLAUDE_CODE_OAUTH_TOKEN`**
   (from `claude setup-token` locally for Pro/Max) and change the workflow
   step to pass `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`
   instead of `anthropic_api_key`.
3. Trigger by including **`@claude`** in an issue title/body, a PR review body,
   or a PR/issue comment (see the job `if:` filter in the workflow).

**Plugins (CI only):** The workflow registers the
[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
marketplace and installs **`code-review`** and **`mcp-server-dev`** for those
runs. Nothing is written under `~/.claude/` on your machine. For local installs,
use `/plugin install <name>@claude-plugins-official` in Claude Code.

**Security:** On public repositories, read Anthropic’s
[security notes](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md)
before widening triggers or permissions.

**Python pipeline vs Agent SDK:** BSELA V1 does not depend on `claude-agent-sdk`;
see [ADR 0009](../../docs/decisions/0009-claude-agent-sdk-non-adoption.md).

## References

- [ADR 0006 — MCP + adapters](../../docs/decisions/0006-p6-mcp-and-adapters.md)
- [`mcp/README.md`](../../mcp/README.md) — build, tools table, Desktop-style MCP JSON
- [`../README.md`](../README.md) — adapter index for all editors
