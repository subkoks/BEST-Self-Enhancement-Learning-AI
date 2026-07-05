# OpenCode adapter

Wires OpenCode session capture into BSELA via `bsela hook opencode-stop`.

## Flow

1. OpenCode plugin fires on `session.idle` with `{ sessionID }`.
2. Hook exports messages from `~/.local/share/opencode/opencode.db` → JSONL.
3. `ingest_file(..., source="opencode")` runs scrub + detector (same as Claude).

## Manual test

```bash
echo '{"sessionID":"ses_..."}' | bsela hook opencode-stop
bsela status
```

Override DB path: `bsela hook opencode-stop --db /path/to/opencode.db`

## Notes

- Export path: `~/.bsela/opencode-transcripts/<session_id>.jsonl` (dedup on unchanged hash).
- Requires `bsela` on PATH and a built OpenCode DB with `message` + `part` rows.
