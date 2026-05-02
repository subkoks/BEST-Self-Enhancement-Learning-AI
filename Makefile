# BSELA developer gate. Mirrors what CI enforces — CI runs the same
# ruff / mypy / pytest matrix. All targets run via uv so tool versions
# follow the pyproject lockfile.

.PHONY: help check doctor lint format format-check type test cov fix clean mcp-check mcp-parity orchestrator-help

help:
	@echo "BSELA make targets:"
	@echo "  check         run lint + format-check + type + test (the full gate)"
	@echo "  doctor        uv run bsela doctor (PATH, store, hook, agents-md)"
	@echo "  lint          ruff check ."
	@echo "  format        ruff format . (writes)"
	@echo "  format-check  ruff format --check ."
	@echo "  type          mypy src tests"
	@echo "  test          pytest -q"
	@echo "  cov           pytest -q with coverage (same flags as CI)"
	@echo "  fix           ruff check --fix + ruff format (auto-fix what can be fixed)"
	@echo "  clean         remove caches (.pytest_cache, .mypy_cache, .ruff_cache)"
	@echo "  mcp-check     run pnpm check in mcp/ (format, lint, typecheck, tests)"
	@echo "  mcp-parity    run CLI↔MCP parity harness in mcp/"
	@echo "  orchestrator-help  print docs/orchestrator quick reference"

check: lint format-check type test

doctor:
	uv run bsela doctor

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

type:
	uv run --extra dev mypy src tests

test:
	uv run pytest -q

cov:
	uv run pytest -q --cov=bsela --cov-report=term-missing

fix:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache

mcp-check:
	cd mcp && pnpm check

mcp-parity:
	cd mcp && pnpm parity

orchestrator-help:
	@echo "BSELA repo-local orchestrator (markdown roles):"
	@echo "  Lead prompt:   docs/orchestrator/ORCHESTRATOR.md"
	@echo "  Index + roles: docs/orchestrator/README.md"
	@echo "  ADR:           docs/decisions/0008-developer-orchestrator-workflow.md"
	@echo "Validation: make check | make mcp-check | uv run bsela doctor"
	@echo "---"
	@sed -n '1,40p' docs/orchestrator/README.md
