# ADR 0006 — P6 MCP server + multi-editor adapters (TypeScript workspace)

- **Status:** Shipped
- **Date:** 2026-04-24
- **Shipped:** 2026-04-28 — `bsela_status` + `bsela_route` called via MCP stdio in a live Claude Code session; returned real store counts and routing decisions. Gate closed.

## Context

P5 scaffolding (router + auditor) landed behind ADR 0005 in parallel with P4 dogfood. The Python surface is now enough of a control plane to pilot dogfood: `bsela ingest`, `detect`, `distill`, `process`, `review`, `report`, `route`, `audit`, `decision`, `doctor`, `hook install`, plus the Claude Code Stop hook is registered and green.

The next structural gap is reach: today only Claude Code feeds BSELA. Codex, Windsurf, and any IDE that speaks MCP can't subscribe to the router or auditor. Per roadmap `P6 — MCP + Multi-editor`:

> MCP server (TypeScript); Codex + Windsurf adapters. 7 days.

Project AGENTS.md already says `TypeScript only for the future MCP server (P6+)`, so the language choice is pre-decided. The open questions are:

1. Where does the TS workspace live?
2. What surface does the MCP server expose first?
3. How does the MCP server talk to the Python core without re-implementing logic?
4. How do adapters layer on top?

## Decision

1. **TS workspace lives under `mcp/` inside this repo.** Single repo, two language stacks. Python is still the system of record for core logic (store, detector, distiller, router, auditor); TS is the transport + editor-facing layer. No monorepo tooling beyond pnpm + vitest — nothing Turbo / Nx-scale until three packages justify it.

2. **First MCP surface is read-only.** P6 exposes three tools that map 1:1 to existing `bsela` CLI commands:
   - `bsela_route(task: string)` → returns the `RouteDecision` JSON.
   - `bsela_audit(window_days?: number, stdout?: boolean)` → returns the audit markdown.
   - `bsela_status()` → returns session / error / lesson / pending counts.
   Write surfaces (`bsela ingest`, `review propose`, `decision add`, `hook install`) stay CLI-only until we have usage data from read surfaces. This caps the blast radius of the first TS code.
   - **Post-ship update (2026-05-02):** read-only surface now includes
     `bsela_lessons`; `bsela_audit` and `bsela_status` return typed JSON
     payloads from `bsela audit --json` and `bsela status --json`.

3. **The TS layer shells to the `bsela` binary.** `mcp/src/bsela-client.ts` spawns `bsela <args>` via `node:child_process` and parses JSON on stdout. Reasons:
   - Zero risk of logic drift — the Python code remains the one source of truth.
   - No FFI, no IPC server, no shared SQLite driver between Python + TS.
   - Bsela must be on `PATH` — same requirement the Claude Code Stop hook already has, so `bsela doctor` already gates it.
   - Startup cost per tool call ≈ Python interpreter boot (≈ 200 ms on this machine); acceptable for infrequent MCP tool dispatches and revisitable if it becomes a bottleneck.

4. **Adapters ship after the MCP server, not before.** Codex / Windsurf adapters are config snippets + a short README each. They land in `adapters/<editor>/` in a follow-up commit once the MCP server has a stable tool schema.

5. **Tooling.** pnpm for deps (already on the machine via Homebrew). TypeScript strict mode. ESM only. Vitest for tests. Prettier + ESLint per AGENTS.md. Lockfile (`pnpm-lock.yaml`) committed. No global installs — everything stays inside `mcp/`.

6. **CI hook-up.** `mcp/` stays out of the Python gates. A new GitHub Actions job runs `pnpm install --frozen-lockfile && pnpm test` inside `mcp/` on any PR touching `mcp/**` — lands once the server code is real.

## Consequences

- **Multi-language repo.** Contributors now need Python 3.13 + Node 22 LTS + pnpm. This is already the author's machine setup per `~/AGENTS.md`; external contributors get a line in the README.
- **`bsela` must be on `PATH` for MCP.** Documented in `mcp/README.md` + enforced by the existing `bsela doctor` check.
- **JSON contract is the seam.** `bsela route --json`,
  `bsela audit --json`, `bsela status --json`, and
  `bsela lessons --json` (`review list --json` fallback for older CLIs)
  are the stable interfaces the TS side commits to. Breaking any of
  their shapes requires a matching TS-side update in the same commit.
- **Write tools are deferred.** Keeps P6 bounded; re-opens when read-side telemetry exists.

## Rejected Alternatives

- **Separate repo for the MCP server.** Rejected: the JSON contract binds the two tightly enough that splitting repos buys version-skew pain with zero modularity win at this size.
- **Python-implemented MCP server using an existing Python MCP SDK.** Rejected: project AGENTS.md explicitly dictates TS for P6+. Reopening that decision isn't worth the churn; TS also matches editor ecosystems better.
- **Embed bsela logic directly in TS.** Rejected: requires porting detector + router + auditor + store access. Guaranteed logic drift and doubles the maintenance surface.
- **IPC / long-lived subprocess.** Rejected for now: adds supervision, restart, backpressure concerns. Shell-out per call is good enough until we measure a bottleneck.
- **Start with adapters before the MCP server.** Rejected: without a server, adapters have nothing to adapt to. Order matters.

## Re-open Condition

Revisit when any of the following hold:

- Tool-call latency via child_process shows up as a UX issue (e.g. > 500 ms steady-state under real editor use). Move to a persistent Python sidecar or reimplement the minimal set in TS.
- A write surface (e.g. `bsela_review_propose`) is needed to close a real user loop. Escalate to an ADR 0007.
- More than two editor adapters exist — split `adapters/` into its own package or consolidate.

## References

- [AGENTS.md](../../AGENTS.md) — "Tech Stack" section (`TypeScript only for the future MCP server (P6+)`).
- [docs/roadmap.md](../roadmap.md) — P6 row.
- [config/models.toml](../../config/models.toml) — the role table the router publishes to MCP clients.
- ADR [0001 — Harness over weights](0001-harness-over-weights.md), [0005 — P5 Router + Auditor](0005-p5-router-and-auditor.md).
