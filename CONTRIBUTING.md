# Contributing to BSELA

Thanks for considering a contribution. BSELA is a local control plane that
learns from coding-AI sessions, so the project is intentionally small,
local-first, and conservative about external dependencies.

## Quick start

```bash
git clone https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI.git
cd BEST-Self-Enhancement-Learning-AI

# Python toolchain (recommended)
uv sync          # install deps from pyproject.toml + uv.lock
uv run pytest -q # run tests

# Pre-flight checks
make lint        # if available
make test        # if available
```

## Workflow

1. Open an issue first for non-trivial changes — alignment is faster than
   re-architecture in review.
2. Branch from `main` using a descriptive prefix:
   - `feat/...` new feature
   - `fix/...` bug fix
   - `chore/...` tooling, refactor, infra
   - `docs/...` documentation only
3. Keep PRs focused: one logical change per PR.
4. Update or add tests for behavior changes.
5. Run `pytest` (and any TS tests under `mcp/`) before requesting review.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) where
practical:

```
<type>(<scope>): <short summary>
```

Examples: `feat(hooks): add transcript redaction`,
`fix(adapters): handle missing AGENTS.md`.

## Code style

- Python 3.13+; type hints on all public functions.
- `ruff format` + `ruff check` for Python; Prettier for the TS in `mcp/`.
- No silent breaking changes; flag with a `BREAKING:` footer in commit body.

## Tests

- `pytest` for Python; vitest for TypeScript MCP code.
- Prefer fast unit tests; use the smallest fixture that proves the change.
- Don't introduce mocks for things you can run for real cheaply (filesystem,
  local sqlite, in-process MCP).

## Reporting bugs and feature requests

Use the issue templates: `Bug report` or `Feature request`. Security issues
go through `SECURITY.md`, not the public tracker.

## License

By contributing you agree your work is licensed under the MIT License (see
`LICENSE`).
