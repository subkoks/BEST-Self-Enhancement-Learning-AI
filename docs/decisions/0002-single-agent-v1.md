# ADR 0002 — Single-agent pipeline for V1, not multi-agent orchestration

- **Status:** Accepted
- **Date:** 2026-04-17

## Context

Multi-agent orchestration (LangGraph / CrewAI / autogen) is fashionable and was suggested by several referenced systems (Beam.ai, deepagents). The question: do we adopt it now, or later, or never?

## Decision

V1 ships as a **single-process Python pipeline** with discrete typed stages (capture → detect → distill → update). No LangGraph. No supervisor+workers. No agent-to-agent messaging.

Sub-agents are reconsidered only after V1 dogfood data (P4) shows a specific bottleneck that parallelism actually solves — e.g., auditing many repos concurrently.

## Consequences

- **Legibility:** failures are traceable; every stage reads/writes a typed record.
- **Debuggability:** no message-bus mystery meat. One process, one stack trace.
- **Zero framework lock-in:** upgrading Anthropic SDK never cascades through orchestrator internals.
- **Bounded parallelism:** sequential pipeline. Fine for one user, one machine, one session at a time.

## Rejected Alternatives

- **LangGraph supervisor + workers** — heavy dependency, steep learning curve, hard to unit-test, adds a scheduler we don't need.
- **CrewAI role-based team** — encodes multi-agent patterns into config; obscures control flow; wrong abstraction for a pipeline.
- **Custom actor framework** — NIH; single-operator tool needs less, not more, infrastructure.

## Re-open Condition

Revisit when any of the following hold:
- Audit of >5 repos takes longer than the cron window.
- Distiller is bottlenecked by serial Opus calls and batching would help.
- A new use case genuinely requires concurrent agents with shared state.

## References

- Plan document §3 ("prove multi-agent beats single-agent before adopting it").
- `~/AGENTS.md` — "No over-engineering: minimum complexity for the current task."
