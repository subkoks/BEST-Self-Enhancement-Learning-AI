# ADR 0013 — Codex primary and explicit DeepSeek alternative

**Status:** Accepted for implementation; live activation gated

**Date:** 2026-10-01

## Decision

Use Codex CLI with `gpt-6.1-sol`, medium reasoning and ChatGPT login as
BSELA's default provider for judge, distill and replay. Use the direct
DeepSeek API with `deepseek-flash` only on explicit manual selection.
Retire Anthropic/OpenRouter adapters and active defaults. Keep historical
records, capture formats and credentials intact.

No provider is selected by the presence of a credential. Never fall back to
paid API calls after Codex authentication or quota failure. Model output is
validated before lesson persistence; global/safety lessons retain human gates.

DeepSeek budgets are $0.10 per session, $0.50 per run and $5 per UTC calendar
month, including retries. Reservations use published peak rates and conservative
UTF-8 input bounds. Unknown charges stay reserved and block further paid calls.
A ledger records subscription usage separately; it does not assign a fabricated
API dollar cost to ChatGPT subscription calls.

A single model-processing job runs at 08:00 Europe/London: at most three
sessions Monday–Saturday, ten on Sunday. Daily scan stays at 07:30. Weekly
report/audit run Sunday at 09:00. Self-enhance delegates processing to this job.
All model commands share a non-blocking file lock and a 20-minute deadline.

## Deployment gate

Source defaults have `live_enabled = false` because the workstation uses an
editable installation. Enable only a separate deployed configuration after
explicit credential/live-use authorization, offline gates, isolated Codex
canaries, both provider smokes and human learning-quality review. No job
installation is allowed before those gates. Do not rewrite generic shell
startup, global provider selection or the existing credential stores.

## Consequences

Sol consumes the existing shared ChatGPT allowance; model/plan eligibility must
be proven on this account. DeepSeek consumes existing API credit and requires
Keychain availability. Losing either provider produces an actionable failure.
Database additions preserve previous tables. Rollback restores application/job
files and preserves the call ledger instead of restoring an old live database.
