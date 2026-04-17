#!/usr/bin/env bash
# Install BSELA hook wrappers and print the settings.json snippet the user
# needs to paste into ~/.claude/settings.json (we do not mutate that file).
# Idempotent; safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$HOME/.claude/hooks"

mkdir -p "${HOOKS_DIR}"
chmod +x "${REPO_ROOT}/hooks/claude-code/"*.sh

STOP_LINK="${HOOKS_DIR}/bsela-stop.sh"
ln -sf "${REPO_ROOT}/hooks/claude-code/stop.sh" "${STOP_LINK}"
echo "installed: ${STOP_LINK} -> ${REPO_ROOT}/hooks/claude-code/stop.sh"

cat <<EOF

Next step: register the hook in ~/.claude/settings.json. Merge this block
into the existing "hooks" object (do not blindly overwrite the file):

{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "${STOP_LINK}" }
        ]
      }
    ]
  }
}

Verify by running a Claude Code session, then:  bsela status
EOF
