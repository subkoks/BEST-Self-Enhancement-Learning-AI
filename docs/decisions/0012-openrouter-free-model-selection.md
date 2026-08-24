# ADR 0012 — OpenRouter free-model selection for judge/distiller

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

BSELA's keyless lesson loop (the `openrouter` fallback in `config/models.toml`)
drives the judge + distiller via OpenRouter free-tier models. It was pinned to
`openai/gpt-oss-20b:free`. On 2026-08-24 the nightly `bsela process` run showed
`distilled=0 lessons=0` with every session failing:

```
distill failed ... OpenRouter API error 404:
"This model is unavailable for free. The paid version is available now -
 use this slug instead: openai/gpt-oss-20b"
```

OpenRouter had delisted `openai/gpt-oss-20b:free` from the free tier. A first
attempt to repoint at `openai/gpt-oss-120b:free` also 404'd — that slug was
delisted too (the error now points at the paid `openai/gpt-oss-120b`). The
keyless distillation pipeline had therefore been silently broken since the
free 20B went away; the stale memory note ("lesson-creation paused, needs LLM
key") was inaccurate — the key was fine, the model slug was dead.

Verified-live free text models as of 2026-08-24 (via `GET /api/v1/models`
with the operator key, filtering `pricing.prompt == 0` and
`pricing.completion == 0`): 19 entries, including
`google/gemma-4-31b-it:free`, `nvidia/nemotron-3-super-120b-a12b:free`,
`openrouter/free`, `z-ai/glm-5.2:free`. Live completion tests:

- `nvidia/nemotron-3-super-120b-a12b:free` → HTTP 200 with a real completion
  (chosen: 120B class, reliable, coding-capable, clean JSON).
- `google/gemma-4-31b-it:free` → reachable but intermittently 429 (upstream
  shared-pool rate limit); kept as a documented fallback only.

A latent trap was also found: `~/.config/secrets/agents.env` held a *dead*
OpenRouter key (`401 User not found`), while the launchd jobs actually run
with the valid key inherited from the user environment (`~/.config/opencode/.env`).
`bsela doctor` and any interactive shell that sources `agents.env` first would
authenticate against the dead key. The `agents.env` key was replaced with the
valid one (HTTP 200 after swap).

## Decision

1. **Pin the `openrouter` judge + distiller to
   `nvidia/nemotron-3-super-120b-a12b:free`** in `config/models.toml`. This is
   the authoritative source (the editable install resolves `bsela/_config`
   back to this repo's `config/`), so the change survives `uv tool upgrade`
   without patching the venv copy.

2. **Document live free alternatives in the same block** so the next delisting
   is a one-line fix, not a rediscovery exercise:
   `google/gemma-4-31b-it:free` (sometimes upstream-rate-limited),
   `openrouter/free` (router), `z-ai/glm-5.2:free`.

3. **Keep the OpenRouter key in `~/.config/secrets/agents.env` in sync with the
   valid operator key.** The reproducible source of truth for the key is
   `~/.config/opencode/.env` (the one launchd jobs use).

4. **Do not hard-wire a recurring mission to any single `:free` endpoint.**
   Free models are delisted without notice (this is the second such incident).
   If distillation rate-limits persist at volume, the fallback lever is to route
   the judge role through the already-set `ANTHROPIC_API_KEY` (Haiku), per the
   existing `[judge]`/`[distiller]` Anthropic roles — not to chase another free
   slug.

## Consequences

- `bsela process` distills successfully again: after the fix,
  `processed=3 distilled=3 errors=0` (was `distilled=0 errors=7`).
- `bsela doctor` reports all checks passed.
- The nightly Mon 08:00 `process` + 09:00 `audit` launchd jobs resume
  generating lessons.
- Free-tier shared-pool throttling (429) remains a possible future failure
  mode at high volume; the decision records the Anthropic-Haiku fallback path.
- The `agents.env` dead-key trap is resolved; interactive and launchd runs now
  use the same valid key.

## Rejected alternatives

- **Chase `gpt-oss-120b:free`.** Also delisted (404) by the time of the fix;
  would have been a second broken commit.
- **Switch the whole pipeline to the Anthropic paid key permanently.** Higher
  cost; the free OpenRouter path works and the AGENTS.md invariant is
  "keyless loop" by design. Kept as a fallback only.
- **Edit the venv copy of `models.toml` directly.** Gets wiped on
  `uv tool upgrade`; the repo `config/models.toml` is the resolved source.

## References

- `config/models.toml` — `[openrouter]` judge_model / distiller_model (changed).
- `bsela/utils/config.py:100` — `BSELA_CONFIG_DIR`; editable install resolves
  `bsela/_config` to the repo `config/`.
- `bsela/llm/client.py:184` — OpenRouter client reads `[openrouter]` from
  `load_models()`.
- `~/.config/secrets/agents.env` — OpenRouter key synced to the valid key.
- Commit `1955159 fix(config): repoint openrouter free models to live nemotron-120b`.
