# Roadmap

## Phases

| Phase | Status | Duration | Outcome |
|---|---|---|---|
| **P0 — Bootstrap** | ✅ done | 1 day | Repo, git, pyproject, CI, README, AGENTS.md, ADRs. No runtime logic. |
| **P1 — Capture + Store** | ✅ done | 3 days | Hook → ingest → SQLite. Tested against real Claude Code sessions. |
| **P2 — Detect + Distill** | ✅ done | 4 days | Regex detector + Haiku distiller. Lessons produced on seeded failures. |
| **P3 — Propose + Gate** | ✅ done | 2 days | Updater writes branches on `agents-md`. `bsela review` UX live. |
| **P4 — MVP Dogfood** | ✅ done | 7 days | MVP criteria met 2026-04-28: 44 sessions captured, 15 lessons distilled, useful-lesson ratio 0.25 (target ≥ 0.10), cost $0.00/session (free tier via OpenRouter), all doctor checks pass, proposal branches written to agents-md. OpenRouter free-tier provider added (no Anthropic credits needed). Detector fixed for Claude Code nested JSONL format. |
| **P5 — Router + Auditor** | ✅ done | 5 days | Task classifier + weekly audit operational. `bsela route` and `bsela audit` validated against live dogfood data. Audit alerts fire correctly (REPLAY DRIFT confirmed). |
| **P6 — MCP + Multi-editor** | ✅ done | 7 days | MCP server (TypeScript) + Codex/Windsurf adapters shipped. Gate met 2026-04-28: `bsela_status` and `bsela_route` called via MCP stdio transport in a live Claude Code session, returning real store counts and routing decisions. `mcp/` wired in `~/.claude/settings.json`. MCP test suite green. Adapter snippets under `adapters/`. |
| **P7 — A/B + Drift** | ✅ done | 5 days | Replay harness, drift alarms, rollback tooling. `bsela replay` validated against real sessions (3 replayed, drift alert firing). `bsela rollback` wired. ReplayRecord cascade-delete on retention sweep. Replay drift threshold validated at 25%. |

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

P4 tooling is self-serve. Runtime work left for the operator:

1. `bsela hook install --apply` — wire the Claude Code `Stop` hook.
2. Use Claude Code normally for a few days so sessions accumulate.
   Ingest now auto-runs the deterministic detector, so `ErrorRecord`
   rows land without a second command.
3. `bsela process -n 10 -d 7` — batch-distill the most recent week.
   Needs `ANTHROPIC_API_KEY`; skips quarantined, error-free, and
   already-distilled sessions automatically.
4. `bsela review` → `bsela review propose <id>` for AUTO-tagged
   lessons; `bsela review reject <id> -n "…"` for false positives.
5. `bsela report --stdout` (or let the weekly launchd plist write to
   `~/.bsela/reports/dogfood.md`) — review useful-lesson ratio,
   quarantine rate, gate-tag distribution, cost.
6. Tune `config/thresholds.toml` (loop_threshold, judge_threshold,
   correction_markers, scrubber patterns) based on the false-positive
   rate observed. Any change that overrides a gate / budget / retention
   window is a Hard Stop — it requires a matching ADR in `docs/decisions/`.
7. When comfortable, declare P4 shipped and close out P5 (Router +
   Auditor already scaffolded per ADR 0005; the dogfood data is the
   last piece needed to tune and declare it shipped).

## P5 — already landed

The code-side of P5 ships in parallel with P4 dogfood:

* `bsela route "<task>"` classifies a free-form task into one of the
  model roles in `config/models.toml` (keyword-based v1). `--json` for
  machine consumers.
* `bsela audit [--weekly|--window-days N|--stdout]` produces the
  30-day audit digest at `~/.bsela/reports/audit.md`. Exits non-zero
  on any active alert (cost burn, drift, ADR hygiene).
* `config/launchd/com.blackterminal.bsela.audit.plist` is now
  loadable; the command it references exists.

What still gates "P5 shipped":
* Real dogfood data — need at least one non-empty audit run and one
  non-default routing decision in a real session before we can tune
  the keyword buckets or thresholds.
* Review misroute rate. ADR 0005 sets the re-open condition at ≥ 10%.

## P6 — workspace bootstrapped

Per ADR 0006, the TS side landed as:

* `mcp/` pnpm workspace — strict TS, vitest, eslint, prettier.
* `BselaClient` — shells to the `bsela` CLI and returns typed
  `RouteDecision` / typed audit + status output. Seven integration
  tests green against the real CLI.
* `bsela-mcp` server binary (`mcp/src/server.ts`, dist entry
  `mcp/dist/server.js`) — stdio transport, four tools registered:
  `bsela_route`, `bsela_audit`, `bsela_status`, `bsela_lessons`.
  Smoke-tested via the
  MCP SDK `Client` over `InMemoryTransport` and over real `stdio`.
* `.github/workflows/mcp.yml` — runs `pnpm check` inside `mcp/` on
  PRs that touch `mcp/**` or any Python surface the JSON contract
  depends on. Python gates still explicitly exclude `mcp/`.

What still gates "P6 shipped":
* ~~Codex + Windsurf adapters under `adapters/<editor>/`~~ — landed
  as TOML/JSON snippets + per-editor READMEs at
  [`adapters/codex/`](../adapters/codex/) and
  [`adapters/windsurf/`](../adapters/windsurf/), with a shared
  prerequisites doc at [`adapters/README.md`](../adapters/README.md).
* At least one real editor session that uses an MCP tool against
  live BSELA state, captured in the dogfood report. Until that
  happens, the binary is "wired but unproven".
