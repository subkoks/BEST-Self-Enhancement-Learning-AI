# ADR 0003 — SQLite for storage, not Postgres or a vector DB

- **Status:** Accepted
- **Date:** 2026-04-17

## Context

BSELA stores sessions, errors, lessons, decisions, metrics. Candidates considered: Postgres, SQLite, DuckDB, Qdrant/Chroma (vector-native), plain JSONL files.

## Decision

All structured data lives in a single SQLite database (via `sqlmodel`, WAL mode). Raw session transcripts are appended as JSONL under `~/.bsela/sessions/`. Embedding vectors, when needed, live as BLOBs in the same SQLite DB using `sqlite-vec` or equivalent.

## Consequences

- **Zero services to manage.** No Postgres daemon, no Redis, no connection pool.
- **Single-file portability.** `~/.bsela/bsela.db` is the whole store — trivial to back up, move, diff.
- **Typed access.** `sqlmodel` + Pydantic give us compile-time schema + runtime validation.
- **Scale ceiling understood.** Single-operator tool, dozens of sessions per day. SQLite handles this forever.

## Rejected Alternatives

- **Postgres** — operationally expensive (daemon, auth, migrations). Zero benefit at this scale.
- **DuckDB** — excellent for analytics, weak for mutable row-level writes on the hot path.
- **Dedicated vector DB (Qdrant/Chroma)** — separate service, separate backup/restore, separate schema drift. Overkill for dedup-by-similarity on a few hundred lessons. Add only if retrieval quality provably degrades.
- **Plain JSONL files only** — fast to write, terrible to query, no joins, no indexes.

## Re-open Condition

Move off SQLite only if: (a) multiple users/machines need shared state, (b) per-query latency on the lessons table degrades below usable even after indexing, or (c) vector retrieval quality demands an ANN index that `sqlite-vec` can't provide.

## References

- Plan document §4.5.
- SQLite WAL mode documentation.
