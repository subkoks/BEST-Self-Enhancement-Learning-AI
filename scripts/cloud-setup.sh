#!/usr/bin/env bash
# cloud-setup.sh — dependency bootstrap for Claude Code on the web.
# Invoked by the .claude/settings.json SessionStart hook. No-op locally:
# runs only inside Anthropic cloud sessions (CLAUDE_CODE_REMOTE=true) and
# installs only what a committed manifest calls for. Idempotent + safe.
set -uo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
log() { printf '[cloud-setup] %s\n' "$1"; }

# --- Python ---
if [ -f pyproject.toml ]; then
  log "pyproject.toml -> uv sync"
  if command -v uv >/dev/null 2>&1; then
    uv sync 2>/dev/null || uv pip install -e . 2>/dev/null || true
  else
    pip install -e . 2>/dev/null || true
  fi
fi
if [ -f requirements.txt ]; then
  log "requirements.txt -> pip install"
  pip install -r requirements.txt 2>/dev/null || true
fi

# --- Node ---
# Install Node deps for a directory, picking the manager from its lockfile.
node_install() {
  dir="$1"
  [ -f "$dir/package.json" ] || return 0
  if [ -f "$dir/pnpm-lock.yaml" ]; then
    log "$dir -> pnpm install"; corepack enable 2>/dev/null || true
    (cd "$dir" && { pnpm install --frozen-lockfile 2>/dev/null || pnpm install 2>/dev/null; }) || true
  elif [ -f "$dir/yarn.lock" ]; then
    log "$dir -> yarn install"
    (cd "$dir" && { yarn install --frozen-lockfile 2>/dev/null || yarn install 2>/dev/null; }) || true
  elif [ -f "$dir/package-lock.json" ]; then
    log "$dir -> npm ci"
    (cd "$dir" && { npm ci 2>/dev/null || npm install 2>/dev/null; }) || true
  else
    log "$dir -> npm install"
    (cd "$dir" && npm install 2>/dev/null) || true
  fi
}

# Root, then known workspaces (BSELA's MCP server lives in mcp/).
node_install .
node_install mcp

exit 0
