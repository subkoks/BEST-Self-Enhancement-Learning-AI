# ADR 0005 — P5 Router + Auditor scaffold (parallel to P4 dogfood)

- **Status:** Accepted
- **Date:** 2026-04-24

## Context

P4 scaffolding is complete (`bsela hook install`, `bsela process`, `bsela review`, `bsela report`, `bsela decision`, `bsela doctor`, weekly launchd plist for the dogfood report). The *runtime* half of P4 — set `ANTHROPIC_API_KEY`, install the Claude Code Stop hook, accumulate real sessions, tune `config/thresholds.toml` — is strictly operator-side and cannot be advanced by an agent.

Project AGENTS.md "Execution norms in Auto Mode" says:

> Follow `docs/roadmap.md` phase order. Jumping a phase requires a one-line flag in the status update and an ADR if the deviation is durable.

Rather than block dev on operator throughput, this ADR authorises starting P5 (Router + Auditor) in parallel with P4 dogfood. P5 delivers two surfaces that P4 dogfood will exercise the moment it starts producing data, so the two phases are complementary, not sequential.

## Decision

Scaffold P5 now with two pure cores and a thin CLI, reusing P4 patterns:

1. **Router** — `src/bsela/core/router.py`.
   - Pure function `classify(task: str, models: ModelsConfig) -> RouteDecision`.
   - No I/O, no network.
   - Heuristic v1: keyword buckets mapped onto the task classes already declared in `config/models.toml` (`judge`, `distiller`, `planner`, `builder`, `reviewer`, `researcher`, `auditor`, `debugger`, `memory_updater`).
   - Haiku-first bias per the `Core Invariants` section of AGENTS.md. Opus 4.7 only when keywords explicitly indicate planning, architecture, auditing, or debugging a known root cause.
   - Exposed via `bsela route "<task>"` for manual inspection; library-importable for later wiring into adapters / MCP server.

2. **Auditor** — `src/bsela/core/auditor.py`.
   - Pure `build_audit(window_days: int, ...) -> AuditReport` + total function `render_markdown(report) -> str` + `write_report` side effect, mirroring `src/bsela/core/report.py`.
   - Default 30-day window (dogfood is 7-day), a longer lens for drift and cost trend.
   - Signals: cost burn vs. `cost.monthly_budget_usd`, quarantine-rate vs. threshold, lesson-drift fraction vs. `audit.drift_alarm_threshold`, ADR freshness from `docs/decisions/`.
   - `bsela audit --weekly` writes `~/.bsela/reports/audit.md`; `--stdout` prints; `--window-days N` overrides.
   - Unblocks the already-reserved `com.blackterminal.bsela.audit.plist` without changing its scheduling semantics.

3. **Tests.** Colocated `tests/test_router.py`, `tests/test_auditor.py`, and CLI smoke tests via `CliRunner`, using the existing `tmp_bsela_home` fixture. No network in unit tests.

## Consequences

- **P4 dogfood remains the blocking critical path.** P5 code lands behind the same green gate (ruff, ruff format, mypy src+tests, pytest, CI) but does not declare P5 "shipped" — that still requires operator signal plus the next ADR.
- **No new runtime dependencies.** Router v1 is keyword-based; the classifier prompt variant is explicitly deferred. Auditor reuses `sqlmodel`, `pydantic`, stdlib `statistics` / `pathlib` — no additions.
- **The launchd audit plist becomes loadable.** `config/launchd/README.md` will be updated to move `com.blackterminal.bsela.audit.plist` from "reserved" to "active" once the command lands.
- **Model costs stay bounded by `thresholds.toml`.** The router recommends a model but does not execute LLM calls. The circuit-breaker logic around `cost.monthly_budget_usd` and `cost.per_session_budget_usd` stays in the distiller / judge path; routing decisions are pre-cost.
- **Re-opens if Router v1 misroutes.** Moving from keywords to a Haiku-scored classifier prompt is the natural v2 upgrade and will ship behind a later ADR if the dogfood data shows ≥ 10% misroute rate.

## Rejected Alternatives

- **Wait for P4 to be declared shipped before starting P5.** Rejected: operator throughput on the runtime runbook is independent of dev throughput. Sequential would waste a week of agent time with nothing to add.
- **Ship the Router as an LLM-scored classifier from day one.** Rejected: adds network + cost to every routing call; introduces a chicken-and-egg problem (no dogfood data yet to tune the prompt). Keyword v1 is testable offline.
- **Merge Auditor into the existing P4 dogfood report.** Rejected: the dogfood report's 7-day window and "did the pipeline catch anything" framing is different from the auditor's 30-day drift / cost-burn framing. Keeping them distinct avoids a monolith with conflicting defaults.
- **Start P6 (MCP + multi-editor) instead.** Rejected: MCP/TypeScript work is larger scope and further from the P4 data that will validate routing. P5 has the tighter feedback loop.

## Re-open Condition

Revisit when any of the following hold:

- Router v1 misroutes ≥ 10% of sampled tasks during P4 dogfood — promote to Haiku-scored classifier prompt.
- Auditor surfaces a drift or cost signal that requires an action the CLI cannot take (e.g. auto-rollback of a regressed lesson) — that lifts into P7.
- A second surface (Codex, Windsurf) needs routing before MCP ships — generalise the router call site.

## References

- [AGENTS.md](../../AGENTS.md) — "Haiku-first pipeline", "Safety Gates", "Execution norms in Auto Mode".
- [config/models.toml](../../config/models.toml) — task-class → model table the router keys off.
- [config/thresholds.toml](../../config/thresholds.toml) — `[audit]` block (digest_day, drift_alarm_threshold), `[cost]` block (monthly / per-session budgets).
- [docs/roadmap.md](../roadmap.md) — P5 scope.
- ADR [0001 — Harness over weights](0001-harness-over-weights.md), [0002 — Single-agent V1](0002-single-agent-v1.md), [0004 — P3 updater and gate](0004-p3-updater-and-gate.md).
