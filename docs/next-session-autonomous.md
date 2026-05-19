# BSELA Next Session Runbook (Autonomous)

Use this as the **first file to load** in a fresh agent session.

## Mission

Ship BSELA to a polished public-ready state with minimal operator input.

Agent behavior:

- Work in auto mode for long sessions.
- Do not pause for routine decisions.
- Only stop on hard-stop actions (destructive/irreversible/security-sensitive).

## Session host: Cursor vs Codex

Pick one host per session; both can follow this runbook.

### Option A — Cursor (Agent + Auto)

Use when Cursor quota is healthy. If **usage is already high** (for example ~90–96%+ of your plan), expect throttling or degraded agent runs — **switch to Option B** for long autonomous work.

- **Workspace:** open [`bsela.code-workspace`](../bsela.code-workspace) at repo root (fewer Actions YAML false positives); see [`adapters/cursor/README.md`](../adapters/cursor/README.md).
- **Agent:** enable **Auto** / auto-approve safe terminal + file edits per your comfort; keep hard stops for destructive git, secrets, and org-wide GitHub changes.
- **Rules:** project rules load from `AGENTS.md` / `CLAUDE.md`; personal overlay is optional (`~/AGENTS.md`).

### Option B — Codex 5.3 (free / no subscription)

Use when Cursor limits are tight or you want a **fresh free-plan** session without burning Cursor quota.

- **Read first:** [`CODEX.md`](../CODEX.md), then this file, then `AGENTS.md`, `docs/roadmap.md`.
- **MCP:** wire BSELA per [`adapters/codex/README.md`](../adapters/codex/README.md) (`codex mcp add`, `config.toml`); `bsela` must be on `PATH` (`uv tool install -e .` from repo root).
- **Discipline:** batch tool use, avoid repeating the full plan every turn, one logical change per commit — free tiers reward compact autonomous execution.

## Skills: what to use and where they live

**How to use skills:** in Cursor, `@`-mention a skill or open `SKILL.md` from the paths below. In Codex, use the skill path your install exposes (often under `~/.codex/skills/` with symlinks to `~/.agents/skills/`).

### Default stack for this repo (load first)

| Priority | Skill / role                             | When                                                                                                                                                                                |
| -------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | **Orchestrator (repo-local)**            | Long multi-step work: read [`docs/orchestrator/ORCHESTRATOR.md`](orchestrator/ORCHESTRATOR.md) + one role from [`docs/orchestrator/roles/`](orchestrator/roles/) per unit of work.  |
| 2        | **GitHub**                               | Issues, PRs, branch protection, Actions triage: `github-full-access-engineer` (`~/.claude/skills/github-full-access-engineer/`) **or** GitHub MCP tools (`user-github`) if enabled. |
| 3        | **systematic-debug**                     | Any failing test, replay drift, or unclear regression (`~/.claude/skills/systematic-debug/`).                                                                                       |
| 4        | **coding-rules**                         | Style + stack alignment (`~/.claude/skills/coding-rules/`).                                                                                                                         |
| 5        | **python-best-practices**                | Python changes (`~/.agents/skills/python-best-practices/`).                                                                                                                         |
| 6        | **git-commit-helper** / **smart-commit** | Conventional commits after staging (`~/.agents/skills/git-commit-helper/`, `~/.agents/skills/smart-commit/`).                                                                       |
| 7        | **github-actions**                       | Editing `.github/workflows/*` (`~/.agents/skills/github-actions/`).                                                                                                                 |
| 8        | **security-best-practices**              | Auth, boundaries, dependency surface — **only** when explicitly doing a security pass (`~/.claude/skills/security-best-practices/`).                                                |

### Skills pick list (by task — attach as needed)

| Task type                                                     | Suggested skills                                                                                            |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| GitHub platform (rulesets, secrets, org)                      | `github-full-access-engineer`                                                                               |
| CI red / workflow fix                                         | `github-actions`, optionally `gh-fix-ci` style flow via Codex skill `~/.codex/skills/gh-fix-ci/` if present |
| Large refactor / many files                                   | `planner` (readonly) or orchestrator **planner** role                                                       |
| Tests only                                                    | `test-driven-development` (`~/.agents/skills/test-driven-development/`)                                     |
| MCP server / TypeScript                                       | `mcp-builder` or `anthropic-mcp-builder` (`~/.agents/skills/anthropic-mcp-builder/`), `typescript-patterns` |
| Solana / crypto (out of scope for core BSELA unless touching) | `solana-dev` — skip unless relevant                                                                         |
| Docs-only (when asked)                                        | `anthropic-doc-coauthoring`                                                                                 |
| Cursor product questions                                      | `cursor-guide` subagent or Cursor docs — not in default BSELA path                                          |

**Cursor-only convenience skills** (under `~/.cursor/skills-cursor/`): `babysit` (PR merge loop), `create-hook`, `create-rule`, `create-skill`, `update-cursor-settings`, `statusline`, `split-to-prs` — use only when the task matches.

**Browser / E2E** (optional): `webapp-testing` / `playwright` skills if you add UI; not required for CLI+MCP core.

## Tools and MCP: turn on for BSELA work

### Always (every session)

- **Shell:** `git`, `gh`, `uv`, `pnpm` (for `mcp/`), `make`.
- **Read/search:** repo file reads + ripgrep-style search (editor-native).

### Cursor MCP (enable if available)

Enable in **Cursor Settings → MCP** (names may match your local config):

| MCP                    | Use for                                                                                                                                                                           |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BSELA MCP server**   | Read-only status/route/audit/lessons/sessions/errors — per [`adapters/cursor/mcp.json`](../adapters/cursor/mcp.json) and README; requires `bsela` on PATH + `mcp/dist/server.js`. |
| **user-github**        | Issues, PRs, `issue_write`, branch metadata — prefer over `curl` (token safety).                                                                                                  |
| **cursor-ide-browser** | Only if debugging a web surface; not needed for core BSELA.                                                                                                                       |

**Note:** Some environments block `gh issue create` via hooks; if so, use **GitHub MCP** `issue_write` / `list_issues` when the server is connected.

### Codex MCP

- Follow [`adapters/codex/README.md`](../adapters/codex/README.md): add the BSELA stdio server + ensure `bsela` is installed on PATH.
- Add **GitHub** MCP only if your Codex config supports it and tokens stay out of logs.

### Do not enable casually

- Anything that runs **live wallet / signing / prod deploy** — out of scope for routine BSELA maintenance.
- **Supabase / Notion / etc.** — only if you explicitly extend the project; not default for this repo.

## Session Start Instructions

1. Confirm workspace and tool access.
2. Read project rules first: `AGENTS.md`, `CLAUDE.md`, `docs/roadmap.md`.
3. Run a full health snapshot before touching code.

## Phase 0 - Preflight (required)

Run in this order:

```bash
git fetch origin
git status --short --branch
gh auth status
uv run bsela doctor
make check
make mcp-check
uv run bsela audit --weekly --json
```

Record outputs in session notes (especially failed checks and alert payloads).

## Phase 1 - Normalize Local Git State

Current known risk: local `main` can diverge from `origin/main`.

Actions:

1. Inspect divergence and commit graph.
2. Reconcile safely so local `main` is clean and understandable.
3. Preserve local-only work on backup branch before any risky sync.
4. Clean stale local branches after verifying no unique work is lost.

Success criteria:

- `git status` clean or intentionally dirty with known files.
- `main` no longer ambiguous (`ahead/behind` resolved).

## Phase 2 - Product Blockers (code + quality)

Primary blocker is replay reliability/drift signal quality.

Work queue (in order):

1. Fix replay determinism/drift reliability (issue `#44`).
2. Fix metadata/public package URL correctness (issue `#45`).
3. Add/adjust tests to guard both fixes.

Minimum gate after each change set:

```bash
make check
make mcp-check
uv run bsela audit --weekly --json
```

## Phase 3 - GitHub Platform Hardening

Use `gh` (or GitHub MCP tools) and apply improvements directly when safe.

Priority order:

1. Enable code scanning (CodeQL default setup or equivalent workflow).
2. Tighten branch protection review requirements on `main` (>=1 approval).
3. Ensure required checks cover Python + MCP surfaces.
4. Add missing community profile items (for example, `CODE_OF_CONDUCT.md` if absent).
5. Prepare next release once code and audit are green.

Validate:

- Actions runs are green.
- No open critical security signals.
- Branch rules reflect public-repo standards.

## Phase 4 - Issues/PR Workflow (autonomous)

If work is non-trivial, prefer issue + PR traceability:

1. Create/update issue with clear acceptance criteria.
2. Attempt assignment to Copilot coding agent when available.
3. If Copilot unavailable, implement directly in-session.
4. Open PR with concise summary and test plan.

If working directly on `main` by project convention, still keep atomic commits and clear messages.

## Phase 5 - Documentation Polish

Ensure docs are consistent for external users:

- Remove/avoid personal machine assumptions in user-facing guidance.
- Keep adapter/MCP tool lists consistent.
- Keep entry docs stable; avoid session-log noise in quickstart docs.
- Update `CHANGELOG.md` for shipped user-visible changes.

## Phase 6 - Release Readiness Gate

Ready-to-go means all are true:

- `make check` passes.
- `make mcp-check` passes.
- `uv run bsela doctor` passes.
- `uv run bsela audit --weekly --json` has no blocking alerts for target release.
- GitHub Actions green on latest commit.
- Branch protection and code scanning configured.
- Release notes/changelog updated for shipped changes.

## End-of-Session Output (required)

Provide:

1. What changed locally (files + rationale).
2. What changed on GitHub (issues/PRs/branch rules/actions).
3. Current gate status (`check`, `mcp-check`, `doctor`, `audit`).
4. Open risks/blockers.
5. Exact next command sequence for the next session.

## Hard Stops

Pause and request explicit approval for:

- Force push, history rewrite, branch deletion with risk.
- Destructive file/database operations.
- Secret/token exposure risks.
- Any irreversible org/repo security policy change with high blast radius.
