#!/usr/bin/env bash
# First-run installer. Creates ~/.bsela, syncs deps, installs CLI in editable mode.

set -euo pipefail

BSELA_HOME="${BSELA_HOME:-$HOME/.bsela}"

mkdir -p "${BSELA_HOME}"/{sessions,logs,reports}

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

uv sync --all-extras
uv tool install --force -e .

echo "bsela installed. Try: bsela --help"
