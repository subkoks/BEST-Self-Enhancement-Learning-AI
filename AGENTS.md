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

## Tech Stack

- Python 3.13 via pyenv; `uv` for deps.
- `typer`, `sqlmodel`, `anthropic`, `pydantic`, `ruff`, `mypy`, `pytest`, `hypothesis`.
- TypeScript only for the future MCP server (P6+).

## Commit Conventions

- Repo-scoped rules from `~/AGENTS.md` apply.
- Use `type(scope):` — scopes: `cli`, `core`, `memory`, `llm`, `adapters`, `docs`, `ci`, `config`, `hooks`, `tests`.
- One logical change per commit. Never `git add .`.

## Out of Scope

- Model training / fine-tuning / RLHF infrastructure.
- Multi-tenant / SaaS / auth.
- Real-money trading execution (import safety posture from `~/AGENTS.md`).
- IDE replacement.
