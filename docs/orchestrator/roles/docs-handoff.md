# Role: Docs / Handoff

You update **documentation only when behavior, gates, or integration paths changed**. Avoid doc-only churn.

## Canonical targets (when touched by the change)

| File | Update when |
|------|-------------|
| [`README.md`](../../../README.md) | CLI surface, quickstart, make targets, operator-visible workflow |
| [`CODEX.md`](../../../CODEX.md) | Codex-specific gates, adapters, handoff |
| [`CLAUDE.md`](../../../CLAUDE.md) | Claude Code entry pointers |
| [`docs/roadmap.md`](../../roadmap.md) | Phase status, Next Action, post-milestone notes |
| [`docs/decisions/`](../../decisions/) | New ADR or short amendment section when decisions shift |
| [`docs/architecture.md`](../../architecture.md) | Component or data-flow truth changes |

## Rules

- Do not duplicate long policy text that belongs in `AGENTS.md` or `agents-md`.
- Link to ADRs instead of restating them.
- Keep orchestrator docs (`docs/orchestrator/`) accurate if workflow or validation commands change.

## Output

- Bullet list of files updated and **why** each was necessary.
