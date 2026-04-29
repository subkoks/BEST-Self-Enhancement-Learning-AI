#!/usr/bin/env bash
# Install (or reinstall) all BSELA launchd agents from config/launchd/.
#
# Usage:
#   ./ops/install-launchd.sh
#
# Each plist uses /bin/zsh -lc so the shell reads ~/.zprofile on launch.
# Make sure OPENROUTER_API_KEY (or ANTHROPIC_API_KEY) is exported there
# before loading these agents, otherwise bsela process will fail silently.

set -euo pipefail

LAUNCHD_SRC="$(cd "$(dirname "$0")/.." && pwd)/config/launchd"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/.bsela/logs"
REPORTS_DIR="$HOME/.bsela/reports"

mkdir -p "$LOG_DIR" "$REPORTS_DIR"

for plist in "$LAUNCHD_SRC"/*.plist; do
    name="$(basename "$plist")"
    dst="$LAUNCH_AGENTS/$name"
    label="${name%.plist}"

    cp "$plist" "$dst"
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    echo "Loaded $label"
done

echo ""
echo "All BSELA launchd agents installed."
echo "Logs: $LOG_DIR"
echo "Reports: $REPORTS_DIR"
