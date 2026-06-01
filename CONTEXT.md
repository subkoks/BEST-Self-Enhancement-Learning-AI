# BSELA

BSELA (Best Self-Enhancement Learning Agent) is a local control plane that makes
existing coding agents better over time. It captures every agent session, distills
recurring failures into durable rules, gates and proposes those rules against the
canonical rules repo, and routes new tasks to the right model. This glossary pins
the domain vocabulary; use these terms in code, comments, commits, and reviews.

## Layers

**Harness**:
The control surface BSELA owns — hooks, routing, gating, scheduling. One of the two
layers improvement is moved into (away from model weights).

**Context**:
The typed, versioned, deduplicated memory carried across sessions. The second layer
improvement is moved into. Capitalized "Context" means this layer, not ambient context.

**agents-md**:
The canonical rules repository BSELA proposes changes against; approved rules flow
through it and sync to all editor targets. The destination of the pipeline, not part
of BSELA's own store.
_Avoid_: "the rules file", "config repo"

## Pipeline artifacts

**Session**:
One captured agent transcript plus its scrub status and counters. The atomic unit of
input to the pipeline.
_Avoid_: "conversation", "run", "transcript" (the transcript is the file; the Session
is the stored record)

**Error**:
A candidate failure record produced by the deterministic detector from a Session —
regex/heuristic only, never LLM. Carries a category and severity. A signal that *might*
become a Lesson, not a program exception.
_Avoid_: "exception", "bug", "failure" (those are outcomes; an Error is a detected record)

**Lesson**:
A distilled, durable rule derived from one or more Errors, with a `rule`, `why`, and
`how_to_apply`. The unit BSELA proposes into agents-md. Moves through the lesson
lifecycle (see below).
_Avoid_: "rule" (a rule is a field *on* a Lesson), "memory", "insight"

**Decision**:
An ADR-style record of a load-bearing, hard-to-reverse choice — stored in the local
store via `bsela decision` and/or as a file under `docs/decisions/`.
_Avoid_: "note", "log entry"

**Replay record**:
The persisted outcome of one `bsela replay` run: re-distilling a past Session against
the current lesson corpus and counting added/removed/changed/unchanged rows. Feeds the
replay-drift signal.

## Session states

**Captured**:
A Session that was ingested cleanly (no secrets matched). The normal, processable state.

**Quarantined**:
A Session the scrubber flagged because a secret pattern matched. Persisted with a
`quarantine_reason`; its transcript is treated as sensitive and is **not** processed
further.
_Avoid_: "rejected", "blocked"

## Lesson lifecycle

**Pending**:
A freshly distilled Lesson awaiting evaluation by the gate. The default starting state.
_Avoid_: "new", "draft"

**Approved**:
A Lesson the auto-merge **gate** cleared **without human review** — high confidence,
non-global scope, no safety keywords. "Approved" here means *machine-approved*.
_Avoid_: "human-approved" (no human is involved — that path is Proposed)

**Proposed**:
A Lesson the gate **withheld** from auto-merge and **escalated to a human** (low
confidence, global scope, or safety-sensitive). Counterintuitively a *later/stricter*
path than Approved, not an earlier draft.
_Avoid_: "draft", "pending", "suggested"

**Applied**:
A Lesson actually written into agents-md (live). The terminal success state.
_Avoid_: "merged", "shipped"

**Rejected**:
A pending Lesson a human declined, with a note. Terminal.
_Avoid_: "deleted", "dropped"

**Rolled back**:
A previously-live Lesson (was approved/proposed/applied) soft-marked back out in the
local store. Terminal; does not delete history.
_Avoid_: "reverted", "undone"

## Gating & routing

**Gate**:
The deterministic check that decides whether a Lesson auto-merges (→ Approved) or needs
a human (→ Proposed). Tags lessons AUTO / REVIEW / SAFETY.

**Scope**:
The breadth a Lesson applies to. `global` scope always forces human review regardless
of confidence.
_Avoid_: "level", "category"

**Confidence**:
The distiller's 0–1 score on a Lesson; below the auto-merge threshold forces human
review.

**Safety flag**:
Set when a Lesson's text mentions a safety-sensitive keyword (crypto, wallet, private
key, seed phrase, trading). Always forces human review.

**Model role**:
The task class the router maps a task to, each bound to a model: `planner`, `builder`,
`reviewer`, `judge`, `distiller`, `researcher`, `auditor`, `debugger`, `memory_updater`.
_Avoid_: "agent", "persona"

## Audit signals

The auditor asks "is the pipeline drifting, overspending, or surfacing stale artifacts?"
It emits two severities: **alerts** (blocking) and **warnings** (informational).

**Drift**:
The stale-lesson fraction (`lessons_stale / lessons_total`) over the audit window. A
blocking **alert** when it exceeds `audit.drift_alarm_threshold`. About the *lesson
corpus going stale*.
_Avoid_: "replay drift" (a different signal — see below), "decay"

**Replay drift**:
The fraction of replayed Sessions whose re-distillation differs from the stored result
(`sessions_with_drift / sessions_replayed`). An informational **warning** only (ADR
0010): on nondeterministic/free-tier models the distiller picks a different lesson
multiset per run, so this tracks *model stability*, not a regression.
_Avoid_: "drift" (that's the corpus-staleness alert)

**Cost burn**:
Prorated monthly spend vs the configured budget (`burn_ratio`). A blocking alert when
prorated burn exceeds `cost.monthly_budget_usd`.
_Avoid_: "spend", "cost"

**ADR hygiene**:
Whether every ADR file under `docs/decisions/` carries a `**Status:**` header. A missing
header surfaces as an alert.

## Processing verbs

**Capture**:
Ingest + scrub a transcript into a Session (pure I/O + regex; never an LLM).

**Detect**:
Run the deterministic detector over a Session to produce Error records (regex, free).

**Judge**:
The LLM step that decides whether a Session's failures are worth distilling.

**Distill**:
The LLM step that turns judged failures into candidate Lessons, deduplicated against the
approved+applied corpus.

**Replay**:
Re-distill a past Session against the current corpus to measure replay drift.

**Scrubber**:
The regex pass that detects secret patterns during Capture and triggers Quarantine.
