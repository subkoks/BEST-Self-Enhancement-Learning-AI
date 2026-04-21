# BSELA developer gate. Mirrors what CI will enforce once wired up.
# All targets run via uv so tool versions follow pyproject lock.

.PHONY: help check lint format format-check type test fix clean

help:
	@echo "BSELA make targets:"
	@echo "  check         run lint + format-check + type + test (the full gate)"
	@echo "  lint          ruff check ."
	@echo "  format        ruff format . (writes)"
	@echo "  format-check  ruff format --check ."
	@echo "  type          mypy src tests"
	@echo "  test          pytest -q"
	@echo "  fix           ruff check --fix + ruff format (auto-fix what can be fixed)"
	@echo "  clean         remove caches (.pytest_cache, .mypy_cache, .ruff_cache)"

check: lint format-check type test

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

type:
	uv run mypy src tests

test:
	uv run pytest -q

fix:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
