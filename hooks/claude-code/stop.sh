#!/usr/bin/env bash
# Claude Code `Stop` hook — called when a conversation ends.
# Forwards the transcript path to `bsela ingest`. Safe to no-op if bsela isn't installed.

set -euo pipefail

TRANSCRIPT_PATH="${CLAUDE_TRANSCRIPT_PATH:-${1:-}}"

if [[ -z "${TRANSCRIPT_PATH}" ]]; then
    exit 0
fi

if ! command -v bsela >/dev/null 2>&1; then
    exit 0
fi

bsela ingest "${TRANSCRIPT_PATH}" >/dev/null 2>&1 &
disown
