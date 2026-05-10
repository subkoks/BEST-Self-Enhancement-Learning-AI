# Replay drift investigation — 2026-05-10

## Summary

After **PR #40** merged (`replay_harness` JSON flag + empty `recent_lessons` in replay mode + prompt guidance), all **15** sessions in the weekly audit window were re-run with `bsela replay`. **`replay_drift.drift_rate` stayed at 1.0** (15/15 with `had_drift=True`, threshold 0.88). The weekly **REPLAY DRIFT** alert therefore remains active.

This is **not** primarily a Jaccard pairing threshold issue: several high-drift replays show **different substantive rules** on replay versus what was originally stored for the same session, not near-paraphrases sitting just below `dedupe.similarity_threshold` (0.78).

## Evidence (CLI excerpts)

### `d66099c6` (stored=3, replayed=3, +3 −3 ~0)

Stored lessons (themes): avoid duplicate tool calls; clear message when an external binary is missing; import sanity before full test suite.

Replayed lessons (themes): validate `pyproject.toml` author email; ensure CI runtime tools exist; run ruff/mypy before tests.

Token overlap between matched “slots” is low — these are **different extractions** from the same session, not wording variants of the same rule.

### `7d0e9afa` (stored=3, replayed=2, +2 −3 ~0)

Count mismatch plus topic shift — pairing cannot collapse this to “unchanged” without losing fidelity.

### `3fc74662` (stored=1, replayed=2, +2 −1 ~0)

One stored rule on tool-argument coercion versus two replayed globals (numeric validation + stack traces) — again **lesson set churn**, not a single paraphrase split across the threshold.

### Operational note

One replay (`49120abe…`) hit **`TimeoutError`** during the OpenRouter/HTTP read path on the first attempt; a **retry succeeded**. Rate-limit guidance (sleep + retry) remains appropriate for batch replays.

## Hypotheses

| # | Hypothesis | Verdict |
|---|------------|---------|
| (a) | Paraphrases fall below Jaccard 0.78 so `+`/`-` inflate while semantics match | **Ruled out** as the dominant driver for inspected sessions; counterexamples show unrelated rule text. |
| (b) | Stored lessons are outdated vs current distiller prompt | **Possible** in the weak sense that any prompt edit moves the extraction frontier; **not** evidence that approved rows are “wrong” — do **not** auto-rollback. |
| (c) | Judge variance flips healthy ↔ unhealthy | **Secondary** for diff magnitude when `force_distill` runs with existing lessons; lesson **content** variance dominates the signal. |

## Recommended next steps (pick one primary track)

1. **Treat replay drift as a model-stability metric, not a release gate (until models stabilize).** Add an ADR and raise `audit.replay_drift_threshold` (or introduce a separate “strict” profile) so the weekly job stays informative without permanent red on free-tier models.

2. **Structured distillation output** (e.g. fixed rubric slots / schema-first candidates) to reduce **which** rule the model chooses for a given transcript — engineering effort; pairs well with Haiku on paid tier.

3. **Optional**: replay-only **lower pairing threshold** or **max-weight bipartite** pairing helps **pure paraphrase** cases; it will **not** clear alerts when replay emits a genuinely different lesson multiset (evidence above).

## Commands used

```bash
uv run bsela audit --weekly --json
uv run bsela replays list --drift-only --json --limit 100
uv run bsela replay <session-prefix>
```

## References

- PR #40 — <https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/pull/40> — merge commit `9b2217efa663c66621e883df724b4a6e38c52766`.
- ADR [0007 — P7 replay and drift](../decisions/0007-p7-replay-and-drift.md).
