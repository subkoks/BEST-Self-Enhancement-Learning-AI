"""Tests for session capture (ingest) — including long-transcript behavior."""

from __future__ import annotations

import hashlib
from pathlib import Path

from bsela.core.capture import ingest_file
from bsela.memory.store import get_session


def test_ingest_streaming_hash_matches_full_file_digest(
    tmp_bsela_home: Path,
) -> None:
    """Large JSONL transcripts must hash like read_bytes() without OOM risk."""
    pad = "x" * 450
    line = f'{{"type":"user","ts":"2025-01-01T00:00:00Z","p":"{pad}"}}\n'
    n = 3500
    path = tmp_bsela_home / "sessions" / "long.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (line * n).encode("utf-8")
    path.write_bytes(body)
    assert len(body) > 1024 * 1024, "fixture should exceed one hash chunk"

    expected = hashlib.sha256(body).hexdigest()
    result = ingest_file(path, auto_detect=False)
    session = get_session(result.session_id)
    assert session is not None
    assert session.content_hash == expected
