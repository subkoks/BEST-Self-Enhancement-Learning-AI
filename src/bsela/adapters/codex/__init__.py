"""Codex CLI adapter: rollout transcript discovery and canonicalization."""

from bsela.adapters.codex.rollout import (
    SOURCE,
    default_session_roots,
    discover_rollouts,
    find_rollout,
    is_rollout_path,
    is_user_rollout,
    normalize_event,
    read_session_meta,
    session_id_from_path,
    strip_injected_context,
)

__all__ = [
    "SOURCE",
    "default_session_roots",
    "discover_rollouts",
    "find_rollout",
    "is_rollout_path",
    "is_user_rollout",
    "normalize_event",
    "read_session_meta",
    "session_id_from_path",
    "strip_injected_context",
]
