# Roadmap

## Phases

| Phase | Status | Duration | Outcome |
|---|---|---|---|
| **P0 — Bootstrap** | ✅ in progress | 1 day | Repo, git, pyproject, CI, README, AGENTS.md, ADRs. No runtime logic. |
| **P1 — Capture + Store** | ⬜ | 3 days | Hook → ingest → SQLite. Tested against real Claude Code sessions. |
| **P2 — Detect + Distill** | ⬜ | 4 days | Regex detector + Haiku distiller. Lessons produced on seeded failures. |
| **P3 — Propose + Gate** | ⬜ | 2 days | Updater writes branches on `agents-md`. `bsela review` UX live. |
| **P4 — MVP Dogfood** | ⬜ | 7 days | Daily use. Measure lesson quality, false positives. Tune thresholds. |
| **P5 — Router + Auditor** | ⬜ | 5 days | Task classifier + weekly `launchd` audit. |
| **P6 — MCP + Multi-editor** | ⬜ | 7 days | MCP server (TypeScript); Codex + Windsurf adapters. |
| **P7 — A/B + Drift** | ⬜ | 5 days | Replay harness, drift alarms, rollback tooling. |

## MVP Scope (P0–P4)

Ship criterion: running `bsela ingest` on a real Claude Code session produces at least one distilled lesson committed as a proposal branch on `~/Projects/Current/Active/agents-md` within 10 minutes.

Included:
1. `bsela` CLI (P0).
2. Claude Code `Stop` hook → `bsela ingest` (P1).
3. Session parser + SQLite store: sessions, errors, lessons (P1).
4. Regex detector (P2).
5. Haiku 4.5 distiller using `failure-distiller.md` (P2).
6. Updater writes proposal branches (P3).
7. `bsela review` and `bsela status` commands (P3).
8. CI: ruff + mypy + pytest (P0).
9. README quickstart (P0).

Deferred past MVP: Router, Auditor, Reviewer, Researcher, MCP server, Codex/Windsurf adapters, dashboard, A/B rollback harness.

## Success Criteria

- ≥ 1 useful lesson per 10 coding sessions during P4.
- Median distillation cost ≤ $0.02 / session.
- Zero secret leaks (verified by scrubber tests).
- `agents-md` sync remains green across all six editor targets after BSELA updates.
- User self-reports fewer repeated corrections over 4 weeks.

## Out of Scope

- Training foundation models / fine-tuning / RLHF infra.
- Multi-tenant SaaS, auth, org RBAC.
- Real-money trading execution.
- IDE replacement.

## Next Action

Execute P1: implement `src/bsela/core/capture.py` + `src/bsela/memory/models.py` + `src/bsela/memory/store.py` + install the Claude Code `Stop` hook.
