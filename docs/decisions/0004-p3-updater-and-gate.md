# ADR 0004 — P3 auto-merge gate and agents-md updater

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

P3 needed a mechanism to route distilled lessons from `~/.bsela/bsela.db` into the canonical `agents-md` repo with the right human gating. Two orthogonal concerns surfaced:

1. **Decision** — given a `Lesson` row, should it auto-merge or go to human review?
2. **Action** — how do we materialize an approved (or pending-review) lesson as a reviewable artifact without touching synced editor artifacts?

The project AGENTS.md "Safety Gates" section already dictates the policy (global scope → review, safety-adjacent content → review, sub-threshold confidence → review, otherwise auto-merge eligible). P3 had to encode this policy in code and wire it to a proposal writer without expanding the dependency surface.

## Decision

Split the concern into three small modules and compose them from the CLI:

- **Pure gate** in [src/bsela/core/gate.py](../../src/bsela/core/gate.py): `evaluate(lesson, thresholds) -> GateDecision`. No I/O. Routes to human review when `scope == "global"`, when `SAFETY_KEYWORDS` (`crypto`, `wallet`, `private key`, `seed phrase`, `trading`, `signing`, `secret`, `credential`, `force push`, `hard reset`, etc.) hit the lesson text, or when `confidence < gates.auto_merge_confidence`. Otherwise `auto_merge=True`.
- **Side-effect updater** in [src/bsela/core/updater.py](../../src/bsela/core/updater.py): `propose_lesson(lesson)` resolves the repo via `BSELA_AGENTS_MD_REPO` (default `~/Projects/Current/Active/agents-md`), requires a clean worktree, checks out `main`, branches `bsela/lesson/<short-id>-<slug>`, writes `drafts/bsela-lessons/<lesson-id>.md`, and commits `feat(bsela-lesson): ...`. Never pushes, never merges. Idempotent on rerun: the same lesson writes the same file, so a second call is a no-op commit returning the existing HEAD.
- **Review UX** in [src/bsela/cli.py](../../src/bsela/cli.py): `bsela review` lists pending lessons with `AUTO` / `REVIEW` / `SAFETY` tags; `bsela review propose <id>` runs gate + updater and transitions the lesson to `approved` (auto-merge eligible) or `proposed` (human review needed); `bsela review reject <id> --note` marks it rejected with an optional note appended to `how_to_apply`.

## Consequences

- **Safety is non-negotiable.** A wallet / trading / credential lesson can never auto-merge regardless of confidence. The keyword list is the single seam to adjust if it becomes too loose or too strict.
- **Human still owns the push.** The updater stops at a local branch; nothing reaches the GitHub `agents-md` remote without a manual `git push` + PR.
- **No new library dependencies.** `subprocess.run(["git", ...])` handles every git operation, keeping the dependency list the same as P2.
- **`drafts/` separation** keeps BSELA proposals logically distinct from `agents-md/src/gotcha.md`, preserving the harness-over-weights invariant (ADR 0001): BSELA never writes canonical rules directly.
- **Testable in isolation.** The gate has no I/O. The updater is exercised against a temp-dir `git init` repo. The CLI review flow is covered end-to-end via `CliRunner` + an isolated `BSELA_HOME`.

## Rejected Alternatives

- **Flat confidence threshold only** — too easy to auto-merge a wallet / trading lesson once the distiller's confidence climbs. Keyword gating is a cheap, explicit backstop.
- **`GitPython` / `dulwich`** — extra dependency surface (native bindings in one, pure-Python reimplementation in the other) for zero functional gain over `subprocess`. Git is already on every dev machine BSELA runs on.
- **Write directly into `agents-md/src/gotcha.md`** — bypasses the review gate entirely and violates the canonical-vs-draft separation. `drafts/bsela-lessons/` keeps the diff reviewable.
- **Let the updater push the branch** — any autonomous push crosses the Hard Stop boundary in `~/AGENTS.md` ("`main`/`master` are protected — push to feature branches only") and removes the user's manual review step. Explicitly rejected.

## Re-open Condition

Revisit when any of the following hold:
- The keyword list produces a meaningful false-positive rate during P4 dogfood — consider moving to a small classifier prompt scored by the Haiku judge.
- We need to propose lessons against repos other than `agents-md` (e.g. project-local AGENTS.md overlays) — generalize the updater's repo-resolution logic.
- A second operator or CI starts generating lessons concurrently — replace the "clean worktree" precondition with a branch-stash strategy.

## References

- [AGENTS.md](../../AGENTS.md) — "Safety Gates" and "Auto Mode" sections.
- [config/thresholds.toml](../../config/thresholds.toml) — `[gates]` block.
- [tests/test_gate.py](../../tests/test_gate.py), [tests/test_updater.py](../../tests/test_updater.py), [tests/test_cli_review.py](../../tests/test_cli_review.py).
- ADR [0001 — Harness over weights](0001-harness-over-weights.md).
