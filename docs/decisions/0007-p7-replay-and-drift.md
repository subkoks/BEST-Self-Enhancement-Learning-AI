# ADR 0007 — P7 Replay harness, drift alarms, and rollback tooling

- **Status:** Shipped
- **Date:** 2026-04-28
- **Shipped:** 2026-05-02 — `bsela replay` validated; `ReplayRecord` persisted; drift alarm fires at 25% threshold; `bsela rollback` wired; 310 tests green, CI passing.

## Context

P6 delivered read-only MCP tooling. The system can now capture sessions, detect errors, distill lessons, propose changes, route tasks, and audit cost and ADR health. What it cannot do is answer:

> "If we re-ran distillation on an old session today, would it produce the same lessons?"

Without this, lesson quality is opaque over time. Prompt changes, model upgrades, and rule drift all silently shift what the distiller produces. Operators have no signal for regression.

P7 per the roadmap:

> Replay harness, drift alarms, rollback tooling. `bsela replay` validated against real sessions.

## Decision

1. **Replay is re-distillation, not re-execution.** `bsela replay <session-id>` re-runs the full judge → distill pipeline on a stored session and diffs the resulting lessons against the lessons currently on record for that session. Nothing is persisted to `lessons`; only the diff summary is written to `replay_records`.

2. **Diff is normalized and rule-centric.** Comparison normalises whitespace + case, compares `(rule, scope, confidence)` tuples. Four diff kinds: `unchanged`, `added`, `removed`, `changed`. `changed` fires when the rule text matches but scope or confidence shifted beyond the precision of the stored float.

3. **Drift alarm is threshold-based and auditor-integrated.** `bsela audit` counts `had_drift=True` replay records in the window. If the ratio exceeds `thresholds.toml → auditor.replay_drift_threshold` (default 0.25), the audit exits non-zero and prints a `REPLAY DRIFT` alert. The weekly launchd job therefore surfaces regressions automatically.

4. **`bsela rollback <lesson-id>` reverts a lesson to `rolled_back` status.** Rollback does not delete — it soft-marks so downstream aggregates (report, audit) exclude the lesson from the active corpus. Every change remains a commit; the `rolled_back` status is the undo token. Re-instating a rolled-back lesson is a manual `bsela review propose` → auto-merge cycle.

5. **`ReplayRecord` participates in the retention sweep.** `bsela retention --sweep` cascade-deletes replay records for sessions that fall outside the 90-day error window. This keeps `replay_records` from growing unboundedly for high-frequency dogfood setups.

6. **No new LLM calls for rollback.** Rollback is a pure store operation. It does not re-run the judge or distiller — the decision to roll back is always operator-driven.

## Consequences

- **`replay_records` table added to store.** Schema: `id`, `session_id`, `had_drift`, `diff_json`, `replayed_at`. Replayed-at is indexed for retention sweep efficiency.
- **Audit gains a drift-ratio signal.** Operators who don't inspect sessions directly still see drift rate in the weekly digest. False-positive rate depends on prompt stability — operators who change `failure-distiller.md` should expect a spike.
- **Rollback is soft, not surgical.** Rolling back one lesson does not revert the `agents-md` proposal branch that may have landed from that lesson. Operators must handle that separately via `git revert` on the `agents-md` repo.
- **Replay requires API key.** Same constraint as distillation. Tests patch `make_llm_client` to avoid CI key dependency.

## Rejected Alternatives

- **Hard-delete on rollback.** Rejected: destroys audit trail. Soft-mark preserves the full history for future analysis (e.g. "how often do we roll back high-confidence lessons?").
- **Replay patches lessons in place.** Rejected: mutation without confirmation violates the gate contract. Replay is read-only relative to the lesson corpus; operators act on the diff.
- **Drift alarm in a separate background process.** Rejected: the existing weekly `bsela audit` cron is the right surface for this signal. Adding another daemon increases supervision cost with no benefit.

## Re-open Condition

Revisit when any of the following hold:

- Drift rate in production stays above 25% for more than two consecutive audit windows — investigate prompt or model instability rather than tuning the threshold.
- Rollback frequency suggests lessons are being distilled at too low a confidence bar — lower `thresholds.toml → gates.auto_merge_confidence`.
- Replay latency becomes a bottleneck for large session archives — add a `--limit` or `--dry-run` flag, or make replay async.

## References

- [docs/roadmap.md](../roadmap.md) — P7 row.
- [ADR 0002 — Single-agent V1](0002-single-agent-v1.md) — loop contract referenced by the rollback policy.
- [ADR 0005 — P5 Router + Auditor](0005-p5-router-and-auditor.md) — audit surface that now includes the drift alarm.
- [config/thresholds.toml](../../config/thresholds.toml) — `auditor.replay_drift_threshold` gate.
