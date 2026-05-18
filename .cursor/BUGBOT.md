# Bugbot — BSELA review rules

## Priority: security and invariants

- Flag any API keys, tokens, session strings, or credentials in code, tests, logs, or committed config.
- Flag writes to synced editor artifacts (`~/.claude/CLAUDE.md`, `~/.cursor/rules/*`, etc.). Rules must go through `agents-md`, not local editor copies.
- Flag fine-tuning / weight-training suggestions — out of scope (harness + context only).
- Flag bypassing or weakening the secret scrubber, or distilling quarantined sessions.
- Flag auto-merge paths for `global` scope lessons or changes to safety / crypto / wallet / trading rules without explicit human-review markers.

## Python (`src/bsela/**`, `tests/**`)

- Require type hints on new/changed public functions; prefer `pathlib.Path` over `os.path`.
- Flag bare `except:` or swallowed exceptions in `core/`, `memory/`, `llm/`, and CLI paths.
- SQLite changes: flag missing migrations/backward compatibility for `~/.bsela/bsela.db` schema.
- New CLI commands need help text and a smoke test in `tests/test_cli_*`.
- Cost paths: flag unbounded LLM calls without budget checks against `config/thresholds.toml`.

## MCP (`mcp/**`)

- TypeScript strict; no `any` on exported APIs.
- Parity tests must stay aligned when MCP tools change (`mcp/tests/`).

## Docs-only PRs

- Skip blocking bugs for markdown-only typos in `docs/` unless they contradict ADRs in `docs/decisions/`.

## Before merge

- CI must pass: `ruff check`, `ruff format --check`, `mypy src tests`, `pytest`.
- One logical change per commit; scopes: `cli|core|memory|llm|adapters|docs|ci|config|hooks|tests`.
