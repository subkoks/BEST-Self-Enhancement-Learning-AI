# BSELA developer gate. `make check` mirrors CI: orchestrator drift guard,
# ruff, mypy, pytest with `--cov-fail-under=99` (same as `.github/workflows/ci.yml`).
# All targets run via uv so tool versions follow the pyproject lockfile.

.PHONY: help check doctor lint format format-check type test cov fix clean mcp-check mcp-parity orchestrator-help dogfood-report dogfood-audit dogfood-process

help:
	@echo "BSELA make targets:"
	@echo "  check         orchestrator-help + lint + format-check + type + cov (CI parity)"
	@echo "  doctor        uv run bsela doctor (PATH, store, hook, agents-md)"
	@echo "  lint          ruff check ."
	@echo "  format        ruff format . (writes)"
	@echo "  format-check  ruff format --check ."
	@echo "  type          mypy src tests"
	@echo "  test          pytest -q"
	@echo "  cov           pytest -q with coverage + --cov-fail-under=99 (CI parity)"
	@echo "  fix           ruff check --fix + ruff format (auto-fix what can be fixed)"
	@echo "  clean         remove caches (.pytest_cache, .mypy_cache, .ruff_cache)"
	@echo "  mcp-check     run pnpm check + pnpm build in mcp/ (gate + dist/server.js)"
	@echo "  mcp-parity    run CLI↔MCP parity harness in mcp/"
	@echo "  orchestrator-help  print docs/orchestrator quick reference"
	@echo "  dogfood-report   uv run bsela report --stdout (P4 dogfood; uses BSELA_HOME)"
	@echo "  dogfood-audit    uv run bsela audit --weekly --stdout (P5 digest; exit 1 if alerts)"
	@echo "  dogfood-process  print the batch-distill command (uses API; does not run it)"

check: orchestrator-help lint format-check type cov

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
	uv run pytest -q --cov=bsela --cov-report=term-missing --cov-fail-under=99

fix:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache

mcp-check:
	cd mcp && pnpm check && pnpm build

mcp-parity:
	cd mcp && pnpm parity

dogfood-report:
	uv run bsela report --stdout

dogfood-audit:
	uv run bsela audit --weekly --stdout

dogfood-process:
	@echo "Batch distill (API spend):  uv run bsela process -n 10 -d 7"
	@echo "Needs ANTHROPIC_API_KEY; skips quarantined, no-error, and already-distilled sessions."

orchestrator-help:
	@echo "BSELA repo-local orchestrator (markdown roles):"
	@echo "  Lead prompt:   docs/orchestrator/ORCHESTRATOR.md"
	@echo "  Index + roles: docs/orchestrator/README.md"
	@echo "  ADR:           docs/decisions/0008-developer-orchestrator-workflow.md"
	@echo "Validation: make check | make mcp-check | uv run bsela doctor"
	@echo "---"
	@sed -n '1,40p' docs/orchestrator/README.md
