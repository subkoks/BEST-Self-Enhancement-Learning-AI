# ADR 0009 — Do not adopt `claude-agent-sdk` for BSELA V1 core

- **Status:** Accepted
- **Date:** 2026-05-03

## Context

Anthropic ships the **Claude Agent SDK for Python** ([`claude-agent-sdk` on PyPI](https://pypi.org/project/claude-agent-sdk/), source [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)). It provides an in-process agent loop, tool execution, hooks, and session management—aimed at autonomous assistants and CI automation that drive Claude with local tools.

BSELA V1 already depends on the **`anthropic`** Python SDK for judge/distill calls via a thin [`LLMClient`](../../src/bsela/llm/client.py) abstraction (`AnthropicClient`, `FakeLLMClient`, OpenRouter path).

Separately, this repository’s “orchestrator” is defined under [`docs/orchestrator/`](../orchestrator/README.md) as **markdown-only, human-directed roles** (see [ADR 0008](0008-developer-orchestrator-workflow.md)), not a second Python runtime inside `bsela`.

## Decision

**Do not add `claude-agent-sdk` as a dependency** and **do not route the capture → detect → distill → update pipeline through the Agent SDK** for V1.

V1 continues to use:

- The **single-process typed pipeline** from [ADR 0002](0002-single-agent-v1.md).
- **Direct Messages API** usage through `anthropic` (or OpenRouter) behind `LLMClient`, with structured JSON validated at the boundary.

Evaluating the Agent SDK against the optional markdown orchestrator: the Agent SDK does **not** replace `docs/orchestrator/`—that layer is intentionally out-of-process (separate sessions / explicit context loads). The Agent SDK would instead introduce an **in-process** agent scheduler, which is the class of complexity ADR 0002 deferred.

## Consequences

- **Simpler dependency surface:** one LLM client stack, no parallel agent-runtime dependency to upgrade or secure.
- **Clear product boundary:** BSELA remains a harness + typed store + distillation pipeline, not a hosted autonomous coding agent inside the same package.
- **Revisit triggers:** Re-open if [ADR 0002](0002-single-agent-v1.md) re-open conditions apply (e.g. genuine need for concurrent agent workers with shared state), or if a **new**, explicitly scoped product (e.g. experimental CI agent) is approved—**outside** the core pipeline—with its own ADR and cost/safety gates.

## References

- [ADR 0002 — Single-agent pipeline for V1](0002-single-agent-v1.md)
- [ADR 0008 — Repo-local developer orchestrator](0008-developer-orchestrator-workflow.md)
- [Agent SDK overview — Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview)
