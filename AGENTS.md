# BSELA — Project Agent Rules

> Overlay on `~/AGENTS.md`. This file adds project-specific rules. Global rules still apply unless explicitly overridden here.

## Project Identity

- **Name:** BSELA (Best Self-Enhancement Learning Agent).
- **Folder:** `BEST-Self-Enhancement-Learning-AI` (kept descriptive; do not rename).
- **CLI + Python package:** `bsela`.
- **Role in the stack:** control plane over existing coding agents. Never duplicates them.

## Core Invariants

- **Harness + context, not weights.** Any suggestion to fine-tune or train a model is out of scope.
- **Reuse `agents-md`, do not fork it.** Rule changes are proposals against `~/Projects/Current/Active/agents-md`. Never write rules directly into the synced artifacts (`~/.claude/CLAUDE.md`, `~/.cursor/rules/gotcha.md`, etc.) — always upstream to canonical.
- **Single-agent V1.** No LangGraph / CrewAI / autogen. Reach for sub-agents only after V1 metrics justify it.
- **Local-first.** SQLite + filesystem. No Postgres/Redis unless the data shape truly demands it.
- **Haiku-first pipeline.** Opus 4.7 only for low-confidence distillation, planning, and audits. Track per-session cost.

## Memory Taxonomy (canonical)

Five types, one SQLite DB, typed tables:

- `short-term task` — editor-native; BSELA does not persist.
- `project` — `<repo>/AGENTS.md` + `<repo>/.bsela/project.db`.
- `long-term learning` — `~/.bsela/lessons.db`; permanent; git-versioned via `agents-md`.
- `error` — `~/.bsela/errors.db`; 90-day rolling window.
- `decision` — `~/.bsela/decisions.db`; ADR-style, permanent.

## Improvement Loop Contract

- **Trigger** → session-end hook / error regex / cron / manual `bsela review`.
- **Feedback source** → transcript + diff + tests + correction markers (`stop`, `no`, `don't`, undo) + retry counts.
- **Evaluation** → Haiku 4.5 rubric; low scores promoted to Opus 4.7.
- **Update** → proposal branch on `agents-md` → gate → merge → sync.
- **Rollback** → every change is a commit; `bsela rollback <lesson-id>` reverts; replay harness validates.

## Safety Gates

- **Auto-merge allowed only when:** scope is project-local AND distiller confidence ≥ 0.9 AND no overlap with existing high-priority rules.
- **Human review required for:** any global rule, any change that modifies safety posture, any change touching crypto / wallet / trading rules.
- **Secret scrubber** runs before any session data enters the store. Quarantine on hit, never distill.

## Auto Mode (BSELA overlay)

> Global **Default Mode / Auto Mode / Hard Stop / Communication / Token / Planning / Nonstop** sections in `~/AGENTS.md` apply verbatim. The rules below are project-specific additions; they do not restate the global rules.

### Project-specific Hard Stops

Pause and surface even in Auto Mode when a change would:

- Write directly to synced editor artifacts (`~/.claude/CLAUDE.md`, `~/.cursor/rules/*`, `~/.windsurf/rules/*`, `~/.codeium/...`, `~/.codex/AGENTS.md`). Always upstream to `~/Projects/Current/Active/agents-md` and let existing sync propagate.
- Fine-tune, distill into, or otherwise modify foundation-model weights (violates harness+context invariant).
- Bypass the secret scrubber, weaken its patterns, or attempt to distill a quarantined session.
- Auto-merge a lesson scoped `global`, or touch safety / crypto / wallet / trading rules — these always require human review.
- Override `config/thresholds.toml` gates, budgets, or retention windows without a matching ADR in `docs/adr/`.
- Exceed `cost.monthly_budget_usd` or sustain overshoot of `cost.per_session_budget_usd` — trip the breaker, do not widen the budget.

### Execution norms in Auto Mode

- **Ship only on green.** Every commit must leave `ruff check`, `ruff format --check`, `mypy src tests`, and `pytest` passing. If red, fix or revert — never commit broken.
- **One logical change per commit.** Use `type(scope):` with scopes `cli|core|memory|llm|adapters|docs|ci|config|hooks|tests`. Stage files by name; never `git add .` / `-A`.
- **Follow `docs/roadmap.md` phase order.** Jumping a phase requires a one-line flag in the status update and an ADR if the deviation is durable.
- **Stay on `main` for solo work** per repo convention. No force-push, no history rewrites, no branch deletion without explicit ask.
- **Batch + compact.** Parallelize independent reads/greps in one turn; avoid sleep-polling; prefer targeted diffs, short plans, terse status updates.
- **Log autonomous decisions.** When resolving ambiguity without asking, add a one-sentence note to the end-of-turn summary and, once `bsela decision add` lands, persist load-bearing ones to the `decisions` table.
- **Two-failure rule.** If the same approach or identical tool call fails twice, switch strategy — do not loop retries.

## Tech Stack

- Python 3.13 via pyenv; `uv` for deps.
- `typer`, `sqlmodel`, `anthropic`, `pydantic`, `ruff`, `mypy`, `pytest`, `hypothesis`.
- TypeScript only for the future MCP server (P6+).

## Commit Conventions

- Repo-scoped rules from `~/AGENTS.md` apply.
- Use `type(scope):` — scopes: `cli`, `core`, `memory`, `llm`, `adapters`, `docs`, `ci`, `config`, `hooks`, `tests`.
- One logical change per commit. Never `git add .`.

## Branch Naming Policy

- Primary branch types: `feat/...`, `fix/...`, `chore/...`, `docs/...`.
- Keep one branch per task; do not create a new branch only because the editor/agent changed.
- Tool-prefixed branches are optional and reserved for parallel experiments: `cursor/...`, `codex/...`, `claude/...`, `windsurf/...`.
- If already on the correct task branch, continue on it unless explicitly instructed to branch.
- For solo work, staying on `main` is still the default unless task risk/scope justifies a feature branch.
- Use tool tags in commit/PR text only when useful (for example: `[cursor]`, `[codex]`), not as a hard requirement.

## Out of Scope

- Model training / fine-tuning / RLHF infrastructure.
- Multi-tenant / SaaS / auth.
- Real-money trading execution (import safety posture from `~/AGENTS.md`).
- IDE replacement.
