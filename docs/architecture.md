# Architecture

## Mental Model

Continual-learning systems improve across three layers: **weights**, **harness**, and **context** (per the LangChain continual-learning framing). Weights training is out of scope — too slow, too expensive, wrong leverage. BSELA operates purely on harness and context:

- **Harness** — hook scripts, schedulers, routers, gates.
- **Context** — typed memory, lessons, errors, decisions, metrics.

BSELA is a **control plane**, not a runtime. It reads what other agents already produce (session transcripts, git diffs, test output) and writes rule proposals back into the canonical `agents-md` repo that already syncs to every editor the user lives in.

## Components

```
┌──────────────────────────────────────────────────────────────┐
│                        BSELA Core                             │
│                                                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │ Capture  │──▶│ Detector │──▶│Distiller │──▶│ Updater  │  │
│  │ (hooks)  │   │(failures)│   │ (lesson) │   │(rule PR) │  │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘  │
│       │              │              │              │         │
│       ▼              ▼              ▼              ▼         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Memory Store (SQLite + JSON)            │   │
│  │  sessions · errors · lessons · decisions · metrics   │   │
│  └──────────────────────────────────────────────────────┘   │
│       ▲              ▲              ▲              ▲         │
│       │              │              │              │         │
│  ┌────┴─────┐   ┌────┴─────┐   ┌────┴─────┐   ┌────┴─────┐  │
│  │  Router  │   │ Auditor  │   │Researcher│   │ Reviewer │  │
│  │(task→   │   │(cron,    │   │(web, docs│   │(pre-     │  │
│  │ model)   │   │ audits)  │   │ search)  │   │ commit)  │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘  │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
       ┌────────────────────────────────────────┐
       │  agents-md canonical repo (existing)   │
       │  → sync to 6 editor targets (existing) │
       └────────────────────────────────────────┘
```

### Capture

Hook scripts (Claude Code `Stop`/`PostResponse`, Codex session-end) append raw transcripts + metadata to `~/.bsela/sessions/<uuid>.jsonl`. Pure I/O, zero LLM cost. Secret scrubber runs inline; quarantined sessions never reach the store.

### Detector

Deterministic regex + heuristic scan of new sessions. Flags user corrections (`stop`, `no`, `don't`, undo markers), repeated identical tool calls, stack traces, aborted commits, >N tool retries. Emits candidate `error` records. No LLM yet — fast, cheap, high recall.

### Distiller

Two-tier LLM pipeline:

1. **Haiku 4.5** scores each candidate with a typed rubric `{goal_achieved, efficiency, looped, wasted_tokens, confidence}`.
2. Low-confidence or high-impact cases escalate to **Opus 4.7** for full distillation into a `lesson` record (`{rule, why, how_to_apply, scope, confidence}`).
   Dedupe against existing lessons via string match + embedding similarity before write.

### Updater

Writes rule-change proposals as git branches + commits on `~/Projects/Current/Active/agents-md`. Never edits synced artifacts directly — always upstreams to canonical. Gates:

- **Auto-merge** when `scope == project-local` AND `confidence ≥ 0.9` AND no high-priority overlap.
- **Human review** otherwise; user runs `bsela review` to inspect and approve.

### Router

Given a task prompt, classifies it into one of `{plan, build, review, research, debug, audit}` using `config/models.toml` (keyword-based v1) and prints the decision to stdout or `--json` (`bsela route`). The same logic is exposed as the MCP tool `bsela_route`.

### Auditor

`launchd`-driven cron. Weekly: codebase scans, duplicate-rule detection, lesson compaction, drift detection (did a lesson's hit-rate collapse?), storage hygiene. Emits a digest to `~/.bsela/reports/YYYY-WW.md`.

### Researcher

On-demand. Given a topic, fetches external docs/repos (via existing MCP servers: firecrawl, github, WebFetch) and compresses to a reference card filed under `docs/research/`.

### Reviewer

Opt-in pre-commit hook. Runs staged diffs against distilled rules + `agents-md` conventions. Haiku 4.5 only. Blocks commit on hard-rule violations.

## Memory Taxonomy

| Type               | Storage                                         | Scope       | TTL                                      |
| ------------------ | ----------------------------------------------- | ----------- | ---------------------------------------- |
| short-term task    | editor-native                                   | single task | session                                  |
| project            | `<repo>/AGENTS.md` + `<repo>/.bsela/project.db` | single repo | project life                             |
| long-term learning | `~/.bsela/bsela.db` (`lessons`)                | global      | permanent (versioned)                    |
| error              | `~/.bsela/bsela.db` (`errors`)                  | global      | 90d rolling                              |
| decision           | `~/.bsela/bsela.db` (`decisions`)             | global      | permanent                                |
| replay (drift log) | `~/.bsela/bsela.db` (`replay_records`)        | per session | cascade on session prune (`bsela prune`) |

`replay_records` holds one row per `bsela replay` so `bsela audit` can measure drift without re-running the distiller. Global rows share one SQLite file (`bsela.db`, WAL) with typed tables via `sqlmodel`; project scope may use `<repo>/.bsela/project.db`. JSON exports for human review. Never a monolithic markdown.

## Data Flow

1. Editor session ends → hook fires → `bsela ingest <path>` → scrubber → raw session in SQLite + JSONL.
2. Detector scans new sessions → candidate errors written.
3. Distiller polls candidates → lessons written (with dedupe).
4. Updater proposes lessons → branch + commit on `agents-md` → gate → merge → existing sync script pushes to 6 editor targets.
5. Router reads active lessons when classifying new tasks.

## Observability

- Structured JSON logs: `~/.bsela/logs/bsela-YYYY-MM-DD.jsonl`.
- Per-command metrics: `bsela status`.
- Weekly auditor digest: `~/.bsela/reports/YYYY-WW.md`.
- Cost tracker: per-session token + USD spend in the `metrics` table.

## Concurrency

BSELA is single-process, single-user. Ingest runs inline via hook. Distiller + auditor run as on-demand commands or via `launchd`. SQLite WAL mode handles the rare overlap. No queues, no workers, no message bus.

## Retention

`bsela prune` runs `bsela.core.retention.sweep()` using `retention.session_days` and `retention.error_days` in `config/thresholds.toml`. Stale sessions are deleted together with dependent `errors`, `metrics`, and `replay_records` rows so the store (and drift history) does not grow without bound.

## Extension Points (V2+)

- **MCP** — additional tools beyond the shipped read-only quartet (`bsela_route`, `bsela_audit`, `bsela_status`, `bsela_lessons`); see ADR 0006.
- **Sub-agents** for parallel multi-repo audits once V1 metrics prove sequential auditing is a bottleneck.
- **Batch replay gates** — optional automation on top of `bsela replay` to block merges when drift exceeds a policy (not implemented; P7 ships interactive replay + audit alarm only).
