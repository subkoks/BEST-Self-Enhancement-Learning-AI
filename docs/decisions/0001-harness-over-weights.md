# ADR 0001 — Improve the harness and context, not the weights

- **Status:** Accepted
- **Date:** 2026-04-17

## Context

The overarching objective is continuous self-improvement for coding AI agents (Claude Code, Codex, Windsurf, Cursor). There are three layers where improvement can happen, per the LangChain continual-learning framing:

1. **Model weights** — retrain or fine-tune the base LLM.
2. **System harness** — the code / hooks / routers / gates around the model.
3. **Persistent context** — memory, rules, lessons carried across sessions.

## Decision

BSELA will only operate on layers 2 and 3. Layer 1 is out of scope.

## Consequences

- **Cost:** orders of magnitude cheaper than training. No GPUs, no datasets, no eval infra.
- **Speed:** improvements ship in minutes, not weeks.
- **Safety:** no risk of degrading base model capabilities; all changes are reversible git commits.
- **Leverage:** works uniformly across any LLM provider the user adopts later (Anthropic, OpenAI, local models).

## Rejected Alternatives

- **Fine-tune a Claude / GPT derivative** — prohibitive cost for a single-operator tool; retraining cadence incompatible with daily coding sessions; vendor lock-in.
- **Train a small local model** (Llama 3.x / Qwen) — infra burden, inferior to frontier models for the tasks that matter, and still requires layers 2 and 3 to be useful.

## References

- LangChain — "Continual learning for AI agents" (referenced in `docs/research/references.md`).
- Anthropic Skills pattern, Karpathy skills repository — both operate on layer 3.
