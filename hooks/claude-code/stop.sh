#!/usr/bin/env bash
# Claude Code `Stop` hook — invoked when a conversation ends.
# Claude Code writes a JSON payload (session_id, transcript_path, cwd, ...)
# to stdin; forward it to `bsela hook claude-stop` which parses and ingests.
# Silent no-op when bsela is not installed so the hook never blocks Claude Code.

set -euo pipefail

if ! command -v bsela >/dev/null 2>&1; then
    exit 0
fi

bsela hook claude-stop >/dev/null 2>&1 || true
