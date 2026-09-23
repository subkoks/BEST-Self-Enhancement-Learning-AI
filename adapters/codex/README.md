# Codex CLI adapter

Two independent wires:

1. **Capture** — Codex rollout transcripts land in `~/.bsela/` so the
   learning loop has current sessions to work from.
2. **MCP** — the [`bsela-mcp`](../../mcp/) stdio server exposes read-only
   tools (`bsela_route`, `bsela_audit`, `bsela_status`, `bsela_lessons`)
   inside any Codex session.

## Prerequisites

See [`adapters/README.md`](../README.md#prerequisites-shared-across-all-editors).
`bsela` must be on `PATH` and `mcp/dist/server.js` must exist.

## Capture — Codex rollouts → `~/.bsela/`

Codex writes one JSONL **rollout** per session under
`~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl` and moves
finished sessions to `~/.codex/archived_sessions/`. That layout is not the
Claude-Code event shape BSELA counts turns in, so the adapter canonicalizes it
(`src/bsela/adapters/codex/rollout.py`): `response_item` messages become
user/assistant turns, `function_call` / `custom_tool_call` become tool calls,
and Codex-internal rollouts (`thread_source: subagent` or `guardian_review`)
are skipped. Harness context Codex prepends to user turns — the `AGENTS.md`
instruction block, `<environment_context>`, `<skill>` bodies, IDE context — is
stripped before the detector runs, so injected rules text never registers as a
user correction.

### Option A — `notify` (near-real-time, already trusted)

Point Codex's `notify` at the capture wrapper (or append its call to an
existing notify script). Codex passes one JSON argument with `thread-id`:

```toml
# ~/.codex/config.toml
notify = ["/bin/bash", "<BSELA_REPO>/hooks/codex/session-end.sh"]
```

### Option B — `hooks.json` (`SessionEnd`)

Copy [`hooks.json`](hooks.json) to `~/.codex/hooks.json` (or merge the block
into an existing one). The `SessionEnd` payload carries `session_id` and
`transcript_path`, so no `notify` wiring is needed. Codex asks once per hook
file to trust it; hooks stay inert until that approval (or
`--dangerously-bypass-hook-trust`) is given.

### Option C — scheduled sweep (`bsela scan`)

Backfills whatever no hook observed (crashed sessions, `codex exec` runs, or
sessions from before the hook existed):

```bash
bsela scan --since-days 14 --limit 50 --dry-run   # preview the selection
bsela scan --since-days 14 --limit 50             # ingest new/grown rollouts
bsela scan --since-days 0 --json                  # machine-readable summary
```

`--replace` (default) keeps one row per rollout: re-ingesting a grown
transcript refreshes the existing session in place and re-runs detection
instead of inserting a snapshot. Rows whose errors already produced a Lesson
are left alone. `config/launchd/com.blackterminal.bsela.scan.plist` schedules
the sweep daily; load it per [`config/launchd/README.md`](../../config/launchd/README.md).

### Verify capture

```bash
bsela scan --since-days 7 --dry-run          # are rollouts in range?
bsela sessions list --source codex | head    # do they have turns/tool calls?
bsela report --stdout                        # 7-day dogfood window
```

An empty Codex session (`turn_count=0`) means the transcript was ingested by a
parser that did not understand the rollout envelope — re-run `bsela scan
--replace` (default) to repair those rows in place.

## Option A — `codex mcp add` (quick)

From any directory (adjust the path to your clone):

```bash
codex mcp add bsela -- node /absolute/path/to/BEST-Self-Enhancement-Learning-AI/mcp/dist/server.js
```

Ensure the environment Codex uses includes `bsela` on `PATH` (you may need `--env PATH=...` if the default is too narrow). Use `codex mcp list` to confirm.

## Option B — append to `~/.codex/config.toml`

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

3. Adjust the `PATH` line in that snippet so it includes the directory
   holding the `bsela` binary (typically `~/.local/bin`) and your Node 22
   install.

4. Restart Codex CLI so it re-reads `config.toml`.

Full MCP options: [Codex config docs](https://github.com/openai/codex/blob/main/docs/config.md).

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

## Tools available

| Tool            | Purpose                                                    |
| --------------- | ---------------------------------------------------------- |
| `bsela_route`   | Classify a task into a model role (planner, builder, etc.) |
| `bsela_audit`   | Get audit digest for recent activity                       |
| `bsela_status`  | Session/error/lesson counts                                |
| `bsela_lessons` | List pending lessons with AUTO/REVIEW/SAFETY tags          |

Write surfaces (`bsela ingest`, `review propose`, etc.) stay CLI-only per [ADR 0006](../../docs/decisions/0006-p6-mcp-and-adapters.md).

## Notes

- The snippet uses `node` + an absolute `args` path rather than the
  package's `bsela-mcp` bin, because the workspace is not published to
  npm and Codex resolves `command` against `PATH`. Pointing at
  `dist/server.js` directly avoids requiring a global install.
- Updating BSELA: re-run `pnpm build` in `mcp/` after pulling. Codex
  re-spawns the server on each session, so no Codex restart is needed
  unless you change `config.toml` itself.
