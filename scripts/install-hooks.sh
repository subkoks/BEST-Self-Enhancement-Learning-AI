#!/usr/bin/env bash
# Install Claude Code hooks by symlinking into ~/.claude/hooks/.
# Idempotent; safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$HOME/.claude/hooks"

mkdir -p "${HOOKS_DIR}"

chmod +x "${REPO_ROOT}/hooks/claude-code/"*.sh

ln -sf "${REPO_ROOT}/hooks/claude-code/stop.sh" "${HOOKS_DIR}/bsela-stop.sh"

echo "installed: ${HOOKS_DIR}/bsela-stop.sh -> ${REPO_ROOT}/hooks/claude-code/stop.sh"
echo "note: register the hook path in ~/.claude/settings.json if not already wired."
