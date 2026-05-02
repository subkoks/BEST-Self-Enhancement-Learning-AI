# ADR 0008 — Repo-local developer orchestrator (role prompts)

- **Status:** Accepted
- **Date:** 2026-05-02

## Context

Operators use Claude Code, Codex, Cursor, and Windsurf against this repository. They sometimes want **clear handoffs**: one session coordinates, others implement, test, review, or ship with narrow scope. ADR 0002 forbids **in-process** multi-agent frameworks (LangGraph, CrewAI, message buses) for the BSELA **Python pipeline**.

The question: how do we support structured multi-session work without violating ADR 0002 or AGENTS.md’s “single-agent V1” product constraint?

## Decision

Add a **repo-local, markdown-only orchestrator**: prompts and templates under `docs/orchestrator/`. The “orchestrator” and “sub-agents” are **human-directed roles** (separate chat sessions, subagent invocations, or explicit context loads), not a second runtime inside `bsela`.

- No new Python scheduler, no LangGraph, no shared agent message bus.
- Optional external tooling (for example Composio `agent-orchestrator` and `agent-orchestrator.yaml`) remains **optional** and is not required to use the markdown workflow.

## Consequences

- **Alignment with ADR 0002:** the capture → detect → distill pipeline stays single-process; orchestration docs do not change core control flow.
- **Discoverability:** `CLAUDE.md` / `CODEX.md` / `README.md` point engineers to one canonical folder.
- **Disable:** ignore the folder or delete local handoff copies; no feature flags in code.

## References

- [ADR 0002 — Single-agent pipeline for V1](0002-single-agent-v1.md)
- [`docs/orchestrator/README.md`](../orchestrator/README.md)
