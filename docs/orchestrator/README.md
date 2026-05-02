# BSELA — Agent Orchestrator (repo-local)

This folder defines a **lightweight multi-role workflow** for day-to-day development in this repository. It is **not** a second runtime inside `bsela` and does not replace ADR 0002’s single-process pipeline; see [ADR 0008](../decisions/0008-developer-orchestrator-workflow.md).

## When to use it

- You want one **lead** session to coordinate, route work, and synthesize results.
- You spawn **focused** follow-ups (or reuse the same session sequentially) with a single role prompt and a tight **Execution Brief**.

## Quick start (Claude Code CLI)

1. Open the repo root in Claude Code.
2. Load [`ORCHESTRATOR.md`](ORCHESTRATOR.md) as the lead instructions (paste, file reference, or project instruction that points here).
3. For each delegated unit, pass **only** the brief plus **one** role file from [`roles/`](roles/).
4. Track active context in a **local** handoff file (see below); do not commit secrets or raw transcripts.

## Role index

| Role file                                              | Responsibility                                     |
| ------------------------------------------------------ | -------------------------------------------------- |
| [`roles/planner.md`](roles/planner.md)                 | Next task, execution brief from roadmap + ADRs     |
| [`roles/builder.md`](roles/builder.md)                 | Minimal-diff implementation                        |
| [`roles/test.md`](roles/test.md)                       | Lint, typecheck, tests, doctor                     |
| [`roles/review.md`](roles/review.md)                   | Scope and defect-focused code review               |
| [`roles/git-release.md`](roles/git-release.md)         | Commits, branch/PR, push policy                    |
| [`roles/docs-handoff.md`](roles/docs-handoff.md)       | CODEX, CLAUDE, roadmap, ADRs when behavior changes |
| [`roles/mcp-integration.md`](roles/mcp-integration.md) | `mcp/`, adapters, `pnpm check`, parity             |
| [`roles/qa-contract.md`](roles/qa-contract.md)         | CLI / JSON / MCP contract stability                |

## Handoff file (local only)

1. Copy [`templates/handoff.template.md`](templates/handoff.template.md) to `HANDOFF.local.md` in this directory (gitignored).
2. The orchestrator updates **Objective**, **Execution Brief**, **Active role**, and **Artifacts** each cycle.
3. Never paste API keys or `.env` contents into handoff files.

## Optional external tooling

[`../../agent-orchestrator.yaml`](../../agent-orchestrator.yaml) configures the **Composio Agent Orchestrator** (tmux worktrees, dashboard, etc.). That stack is **optional**. This markdown workflow works with plain Claude Code and no extra services.

## Makefile helper

From repo root:

```bash
make orchestrator-help
```

Prints paths and a one-line reminder of validation commands.
