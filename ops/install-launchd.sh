#!/usr/bin/env bash
# Install (or reinstall) the BSELA weekly process launchd agent.
#
# Usage:
#   ./ops/install-launchd.sh
#
# Requires OPENROUTER_API_KEY to be set in the environment. The script
# patches the placeholder in the plist before installing so the key is
# baked into the LaunchAgent (stored in ~/Library/LaunchAgents/).

set -euo pipefail

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.blackterminal.bsela.process.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.blackterminal.bsela.process.plist"
LOG_DIR="$HOME/.bsela/logs"
LABEL="com.blackterminal.bsela.process"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "ERROR: OPENROUTER_API_KEY is not set." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"

# Patch the API key placeholder and write to LaunchAgents.
sed "s|REPLACE_ME|${OPENROUTER_API_KEY}|g" "$PLIST_SRC" > "$PLIST_DST"
echo "Wrote $PLIST_DST"

# Unload existing agent if loaded (ignore errors if not loaded yet).
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "Loaded $LABEL"

echo "Done. bsela process will run every Monday at 08:00."
echo "Logs: $LOG_DIR/process.{log,err}"
