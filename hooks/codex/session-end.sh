#!/usr/bin/env bash
# Codex CLI capture hook.
#
# Codex delivers two relevant payload shapes:
#   * ``notify`` (config.toml) passes one JSON argument —
#     ``{"type": "agent-turn-complete", "thread-id": "..."}``.
#   * ``hooks.json`` (SessionEnd / Stop) writes
#     ``{"session_id": "...", "transcript_path": "...", ...}`` to stdin.
#
# ``bsela hook codex-stop`` accepts both and resolves them to the rollout
# transcript under ``~/.codex/sessions``. The ingest runs in the background so
# the editor's shutdown path never waits on capture, and the sweep job
# (``bsela scan``) backstops anything a killed background job missed. Silent
# no-op when bsela is not installed.

set -euo pipefail

if ! command -v bsela >/dev/null 2>&1; then
    exit 0
fi

if [[ $# -ge 1 ]]; then
    (bsela hook codex-stop "$1" >/dev/null 2>&1 &)
else
    (bsela hook codex-stop >/dev/null 2>&1 &)
fi

exit 0
