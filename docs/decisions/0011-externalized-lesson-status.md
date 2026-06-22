# ADR 0011 — `externalized` terminal lesson status (drift gate vs. dedup corpus)

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

`bsela audit` raised a **blocking** DRIFT alert every run:
`DRIFT: 3/3 applied lessons unused for 14+ days (100.0% > 50.0% threshold)`.

The three `applied` lessons (`55adbcb3`, `809875ce`, `6a6601cb`) were promoted
into the `agents-md` `AGENTS.md` distilled-lessons section via PR #31 and
reconciled `proposed → applied` on 2026-06-20. The drift detector
(`core/auditor.py`) counts lessons in `("applied","approved")` with
`hit_count == 0` older than `STALE_LESSON_AGE_DAYS` (14) as stale.

A lesson's `hit_count` only increments through `bsela lessons --bump`
(`cli.py` → `store.increment_hit_count`), i.e. when BSELA surfaces the lesson to
an editor. Once a lesson is externalized into `AGENTS.md`, the editor reads it
directly as a durable rule — BSELA never surfaces it, so it can **never** accrue
a hit. These lessons are therefore permanently `hit_count == 0` and permanently
"stale" by the metric. The alert is a structural false-positive: it fires at
100% on every audit regardless of real drift, training the operator to ignore the
auditor.

The pre-existing terminal status `rolled_back` is excluded from audit counts, but
it cannot be reused here: the distiller dedup corpus
(`llm/distiller.py`) is built from `approved` + `applied` lessons only, and
rolling these back would drop them from that corpus — so the distiller would
regenerate the very rules that already live in `AGENTS.md` as fresh candidates.

## Decision

1. **Introduce a new terminal lesson status, `externalized`,** for lessons that
   have graduated into `agents-md` as durable rules. `status` is a plain `str`
   column — no schema migration.

2. **Externalized lessons leave the drift gate.** `auditor.py` keeps
   `tracked_statuses = ("applied","approved")`, so `externalized` is excluded
   from `lessons_total`/`lessons_stale` automatically. A new
   `DriftSnapshot.lessons_externalized` count is computed and rendered
   (`## Drift → Externalized (durable in agents-md): N`) and is present in the
   `--json` payload, so the lessons remain visible, just not gated.

3. **Externalized lessons stay in the distiller dedup corpus.** This is the one
   behavioural difference from `rolled_back`: `distill_session` now includes
   `list_lessons(status="externalized")` in `approved_corpus`, so a candidate
   duplicating an externalized rule is still suppressed.

4. **Transition is operator-driven** via a new `bsela externalize <id>` command
   (mirrors `bsela rollback`: `resolve_lesson` → `update_lesson_status`). The
   three lessons above are migrated `applied → externalized`. The MCP
   `bsela_lessons` status enum gains `externalized` for parity. `trackHits`
   (MCP) deliberately does **not** include `externalized` — they cannot be hit.

## Consequences

- The weekly audit stops permanently red on the externalized-lessons
  false-positive while still surfacing genuine staleness of any future
  `applied`/`approved` lesson that goes unused.
- Dedup integrity is preserved: externalized rules cannot be regenerated as
  duplicate candidates (regression-tested).
- The drift metric now has an honest population — only lessons that *could*
  realistically accrue hits are gated.
- Reversible: `externalized` is a status string; a lesson can be moved back, and
  removing the status from the dedup corpus query is a one-line revert.

## Rejected alternatives

- **Roll back the three lessons.** Wrong semantics (they are live rules, not
  reverted) and breaks dedup — duplicates would regenerate.
- **Raise `audit.drift_alarm_threshold`.** Masks the signal and would hide a
  genuine future drift regression. Threshold tuning to silence an alarm is the
  same anti-pattern ADR 0010 rejected for replay drift.
- **Document as an accepted false-positive (ADR only, no code).** The alert would
  keep firing every run; it does not address the operator-noise problem.

## References

- ADR [0005 — P5 router and auditor](0005-p5-router-and-auditor.md) — drift alarm origin.
- ADR [0010 — replay drift informational](0010-replay-drift-informational.md) — prior "don't tune thresholds to silence alarms" precedent.
- `agents-md` PR #31 — the externalization of the three lessons.
- `config/thresholds.toml` — `audit.drift_alarm_threshold` (unchanged).
