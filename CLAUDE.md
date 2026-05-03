# BSELA — Claude Code entry

Canonical **project** rules live in [`AGENTS.md`](AGENTS.md). Personal overlay: `~/AGENTS.md`.

Rule changes belong in `~/Projects/Current/Active/agents-md`, not in editor-synced copies under `~/.claude/`.

**Claude Code setup (Stop hook, MCP, repo permissions):** see
[`adapters/claude/README.md`](adapters/claude/README.md).

**Multi-role dev workflow (optional):** lead + focused sub-sessions use
[`docs/orchestrator/ORCHESTRATOR.md`](docs/orchestrator/ORCHESTRATOR.md)
and [`docs/orchestrator/README.md`](docs/orchestrator/README.md) (ADR
[0008](docs/decisions/0008-developer-orchestrator-workflow.md); Agent SDK posture:
[0009](docs/decisions/0009-claude-agent-sdk-non-adoption.md)).

For **Cursor** (MCP wiring), see [`adapters/cursor/README.md`](adapters/cursor/README.md) and the editor index in [`adapters/README.md`](adapters/README.md).

For Codex CLI continuation from this repo, see [`CODEX.md`](CODEX.md).

## Last session — 2026-05-03

### Completed

1. **Hooks verified** — `bsela hook install --apply` confirmed no-op (hook already wired). `bsela doctor` all 7 checks pass.
2. **Full process run** — `bsela process --limit 200 --since-days 90` distilled 35 of 39 sessions (4 already done). 6 new lessons generated; 20 total in review.
3. **Review & promote** — Proposed 4 high-confidence pending lessons (fc6823a8 conf=0.92 AUTO, 01fe8c33 0.75, 8df0e144 0.70, 19681fb1 0.70). Rejected 2 low-confidence ones. Added 4 accepted rules to `AGENTS.md`. Fixed bug: `review_propose` was passing the raw prefix to `update_lesson_status` instead of `lesson.id` (commit `48a5196`).
4. **Report + audit saved** — `docs/reports/dogfood-2026-05-03.md`, `audit-2026-05-03.md`, `audit-2026-05-03.json` committed.

### Dogfood numbers (7-day window)

- Sessions: **128** captured (120 good, 8 quarantined — 6.2% rate)
- Lessons: **33** total (4 approved, 17 proposed, 12 rejected)
- Useful-lesson ratio: **0.16** (target ≥ 0.10 ✅)
- Cost: **$0.00** (OpenRouter free tier ✅)

### Audit status (30-day window)

- Alerts: **all clear**
- Budget burn: $0 / $50 (0%)
- Replay drift: **87.5%** — 7 of 8 replayed sessions drifted. **Watch this: threshold is 92%.** If the next replay pushes it over, the audit will alert. Consider running `bsela replay` on recent sessions and rolling back drifted lessons.
- ADR hygiene: all 9 ADRs carry `**Status:**` ✅

### Also shipped this session (CI fix + doc alignment)

- Fixed CI coverage gate (98% → 99.82%) by adding 14 targeted tests for uncovered error-path branches.
- Fixed stale "3/4 tools" docstrings in `mcp/src/server.ts`, `server-tools.ts`, and `mcp/README.md` (now correctly says 6).

### Remaining tasks for next session

- **Prompt 5** — Fix `.github/workflows/ci.yml` / `claude.yml` if any issues remain after today's CI run.
- **Prompt 6** — Tune `config/thresholds.toml` based on false-positive rate (12 of 33 lessons rejected = 36% rejection rate, above the target ~25%).
- **Prompt 7** — GitHub issue sweep: run `gh issue list` and triage open issues.
