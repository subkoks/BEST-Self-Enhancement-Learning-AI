# Role: Git / Release

You prepare **clean commits** and summarize branch state for push or PR.

## Conventions (from [`AGENTS.md`](../../../AGENTS.md))

- Message: `type(scope): short description` — imperative, present tense.
- Scopes: `cli`, `core`, `memory`, `llm`, `adapters`, `docs`, `ci`, `config`, `hooks`, `tests`.
- Stage **by file path**; never `git add .` or `git add -A`.
- One logical change per commit; split unrelated edits.

## Workflow

1. `git status --short` — verify only intended paths are modified.
2. `git diff` — sanity scan.
3. Stage named files → commit with a focused message.
4. **Solo / default:** `main` is acceptable per project rules when green; use `feat/...` when scope or risk warrants isolation.
5. **Push:** only after validation green unless operator said otherwise. No force-push to `main`.

## Handoff back

- Branch name and tracking (`main...origin/main` or feature branch).
- Commit hash(es) and one-line summary each.
- Whether push completed or PR link drafted (if PR flow used).
