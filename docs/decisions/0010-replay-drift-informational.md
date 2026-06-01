# ADR 0010 — Replay drift is an informational metric, not a release gate

- **Status:** Accepted
- **Date:** 2026-05-31
- **Supersedes:** ADR [0007](0007-p7-replay-and-drift.md) §3 (the "drift alarm gates the run" framing).

## Context

ADR 0007 shipped the replay harness and a drift alarm: `bsela audit` counted
`had_drift=True` replay records over the window and, if the rate exceeded
`config/thresholds.toml → audit.replay_drift_threshold`, appended a
`REPLAY DRIFT` entry to the blocking `alerts` list — which makes the `bsela
audit` command exit non-zero (`cli.py`, `raise typer.Exit(code=1 if alerts)`).

That alarm has fired continuously since 2026-05. Multiple sessions drove it to
ground:

- Determinism was hardened end-to-end — `temperature=0` (Anthropic + OpenRouter),
  `seed` (OpenRouter), Jaccard semantic pairing in `_diff_lessons`, and replay
  input isolation (`recent_lessons=[]`, `replay_harness=True`). Merged via #34,
  #36, #40.
- Despite that, the rate stayed at ~100%. The investigation
  ([docs/reports/replay-drift-2026-05-10.md](../reports/replay-drift-2026-05-10.md))
  established the cause is **not** sub-threshold paraphrasing: on replay the
  distiller emits a genuinely **different lesson multiset** (different rules, not
  reworded ones) for the same transcript. This is model-selection variance —
  intrinsic to nondeterministic / free-tier models that ignore `seed` and vary
  judge verdicts — not a regression in stored lessons.

ADR 0007's own re-open condition anticipated this: "Drift rate … above 25% for
more than two consecutive audit windows — investigate prompt or model
instability **rather than tuning the threshold**." The investigation is done; the
conclusion is model instability. Lowering the bar to silence the alarm would be
dishonest masking, and raising the threshold is explicitly discouraged.

## Decision

1. **Replay drift is reclassified from a blocking *alert* to an informational
   *warning*.** `AuditReport` now carries two severities: `alerts` (blocking:
   cost over budget, stale lessons, ADR hygiene) and `warnings` (informational:
   replay drift). `build_audit` appends the replay-drift line to `warnings`.

2. **The CLI exit code gates on `alerts` only.** `bsela audit` exits non-zero
   only for blocking alerts; informational warnings never fail the run. The
   drift rate, threshold, and `over_threshold` flag remain fully visible in both
   the markdown report (`## Warnings` + `## Replay Drift`) and the
   `bsela audit --json` payload (new `warnings` array; `replay_drift` block
   unchanged).

3. **The threshold is retained as a sensitivity knob, not a gate.** It still
   decides whether the informational warning is emitted, so the signal stays
   useful for tracking model stability over time and tightens automatically
   toward 0.25 when the pipeline moves to deterministic Haiku (per the existing
   comment in `thresholds.toml`).

## Consequences

- The weekly audit stops permanently red on free-tier models while still
  reporting the drift rate. Operators reading the digest see replay drift under
  `## Warnings`, clearly marked informational.
- No change to the replay harness, the diff algorithm, or stored lessons. This
  is purely a severity reclassification of an existing signal.
- If the pipeline later moves to a deterministic paid model and drift stays
  high, that is a genuine regression — but it would then be investigated via the
  warning trend, and promotion back to a blocking alert is a one-line change
  (move the `warnings.append` back to `alerts.append`) gated by a new ADR.

## Rejected alternatives

- **Raise `replay_drift_threshold` toward 1.0.** Rejected: hides the signal and
  contradicts ADR 0007's re-open guidance against threshold tuning.
- **Structured / schema-first distillation to stabilise lesson selection.**
  Deferred, not rejected: it is the right long-term fix (report Option 2) but is
  real engineering effort and pairs with a paid deterministic model. It does not
  block this reclassification.
- **Drop the metric entirely.** Rejected: drift rate is a legitimate
  model-stability signal; it just is not a release gate on nondeterministic
  models.

## References

- ADR [0007 — P7 replay and drift](0007-p7-replay-and-drift.md) — original gate.
- [docs/reports/replay-drift-2026-05-10.md](../reports/replay-drift-2026-05-10.md) — root-cause investigation (Option 1).
- [config/thresholds.toml](../../config/thresholds.toml) — `audit.replay_drift_threshold`.
- Issue #58 — replay harness determinism / audit drift.
