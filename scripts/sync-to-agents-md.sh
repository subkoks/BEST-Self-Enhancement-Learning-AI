#!/usr/bin/env bash
# Trigger the canonical agents-md sync after BSELA merges a rule proposal.
# Wrapper around the existing pipeline in ~/Projects/Current/Active/agents-md.

set -euo pipefail

AGENTS_MD_ROOT="${AGENTS_MD_ROOT:-$HOME/Projects/Current/Active/agents-md}"

if [[ ! -d "${AGENTS_MD_ROOT}" ]]; then
    echo "error: agents-md not found at ${AGENTS_MD_ROOT}" >&2
    exit 1
fi

cd "${AGENTS_MD_ROOT}"

if [[ -x "./scripts/sync.sh" ]]; then
    ./scripts/sync.sh
elif [[ -f "./package.json" ]] && command -v pnpm >/dev/null 2>&1; then
    command pnpm run sync
else
    echo "warn: no known sync entrypoint in ${AGENTS_MD_ROOT}; skipping." >&2
fi
