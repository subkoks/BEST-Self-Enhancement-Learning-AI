# Provider maintenance and rollout

Codex CLI is the primary integration, using GPT-6.1 Sol, medium reasoning and
the existing ChatGPT login. DeepSeek Flash is available only with explicit
`--provider deepseek`. No authentication or quota failure switches providers.
Capture, detection, reporting and audit remain local.

## Evaluation outcomes and repeat runs

Processing reports each session as `judge_healthy`, `distiller_skipped`,
`no_lessons`, `duplicates_only`, `distilled`, or a failure. A distiller skip
does not mean the judge found the session healthy. Provider failures include
fixed operator-facing reasons without raw provider output or transcript text.

Successful persisted evaluations now write a checkpoint in the additive
`session_evaluations` table, including successful zero-lesson outcomes.
Checkpoints contain only an input fingerprint, session ID, outcome and time.
Session content, detector evidence, provider/model settings, prompts, response
schemas and evaluation policy determine the fingerprint. Changed input is
eligible again; recent lesson changes alone do not invalidate the checkpoint.
Use `bsela process --rerun` for deliberate reconsideration. Old lesson-based
skips are retained for sessions with no checkpoint history.

Dry-runs, `--no-persist`, replay runs and failed evaluations do not write
checkpoints. Skipped sessions do not consume the batch's model-call allowance.
The store creates the new table using its existing additive schema setup;
existing tables and rows are not rewritten. Preserve a SQLite backup before
first use against an existing store. Rolling back these source changes leaves
the extra table inert; do not overwrite the live database to remove it.

## Configuration and offline commands

Source defaults deliberately disable live calls. This protects the editable
installation while the live gates are pending. Do not enable scheduling just
because tests pass.

```sh
uv sync --frozen --extra dev
make check
COREPACK_NPM_REGISTRY=https://registry.npmjs.org make mcp-check
COREPACK_NPM_REGISTRY=https://registry.npmjs.org make mcp-parity
uv run --frozen bsela process --dry-run --scheduled
uv run --frozen bsela route "review authentication" --json
```

Use GIT_CONFIG_COUNT=1, GIT_CONFIG_KEY_0=commit.gpgsign and
GIT_CONFIG_VALUE_0=false for the test gate when workstation SSH signing is
unavailable. This isolates test commits without changing global Git settings.

Provider/model selection is validated; old provider environment keys do not
select a client. Codex invocations ignore personal runtime configuration, use
an isolated temporary directory, stdin, ephemeral sessions and strict JSON
schemas. Tools, hooks, plugins, MCP/apps, browser/search and delegation are
disabled; tool events or incomplete turns fail closed. The installed Codex
version must accept all isolation flags during the approved live canary.

DeepSeek uses the named macOS Keychain service
`com.blackterminal.codex.deepseek`, account `black.terminal`, in-process.
No credential is exported or passed in arguments. No global shell changes
are required. Auth checks themselves require credential-access approval.

## Approved live checks

Obtain exact authorization for existing ChatGPT login access, named Keychain
retrieval, scrubbed data sent to both providers, and an aggregate DeepSeek
canary allowance of $0.10. Include synthetic checks, one eligible session
and three representative replays per provider in that scope.

Create a temporary reviewed configuration copied from config/, setting
live_enabled=true and cost.per_run_budget_usd=0.10. For the entire approved
canary batch, also set monthly_budget_usd to existing calendar-month spending
plus $0.10 (never above $5); this imposes an aggregate cap across separate CLI
runs, not just a per-command cap. Include unresolved reservations in the
starting amount; if any exist, stop and reconcile first. Set BSELA_CONFIG_DIR
only for those commands. Never modify production defaults to bypass the gate.

Run provider-aware `bsela doctor --provider codex --auth-check --live`
and its explicit DeepSeek equivalent. Then run
`bsela distill --provider PROVIDER --session-id ID --no-persist` for a verified
eligible, scrubbed session. Preview help first: --no-persist distillation still
calls the selected model, but does not persist lessons.
Run `bsela replay ID --provider PROVIDER` on three representative eligible
sessions; preserve existing replay rows. Record provider-specific new
baseline artifacts and human findings about evidence, duplicates and usefulness.

Record the Codex thread IDs from the isolated synthetic calls locally and
confirm no persisted session rollout, hook execution or BSELA ingestion.
Offline argument inspection alone is not proof of runtime isolation. An
unavailable model, expired login, quota error or unsupported flag is a failed
gate. Confirm DeepSeek ledger usage and total allowance after each step.

The call ledger stores no prompt or credential. DeepSeek reservations use
peak rates and a UTF-8 byte bound with framing overhead. Successful usage
is reconciled conservatively at peak rates, including cache hits; this is
a usage-derived upper estimate, not a provider invoice. Off-peak savings
are not used to widen budgets. Missing usage, interrupted calls and ambiguous
server/network failures retain their reservation and block further paid calls.
Resolve those individual ledger rows only against provider billing evidence;
never delete them or assume an uncertain request was free.

Codex usage is subscription calls/tokens; monetary cost is unmeasured.
Legacy metrics remain separate historical records; new calls are counted
only from the additive llm_calls table.

## Install and observe

Write ~/.bsela/reports/provider-canary.json only after all checks actually
pass, with true values for offline_gates, codex_auth, codex_isolation,
codex_smoke, deepseek_smoke and quality_review, plus codex_model=gpt-6.1-sol
and deepseek_model=deepseek-flash. Keep the detailed evidence beside it.
This is an operator attestation; the installer does not independently perform
live checks. Run ops/install-launchd.sh only under rollout authorization.

The installer backs up live files, enables a separate ~/.bsela/config and
loads four jobs without kickstarting model calls. Processing has one owner:
08:00 daily, 3 sessions Monday-Saturday and 10 Sunday. Scan stays at 07:30;
report/audit run Sunday 09:00. Self-enhance performs no model processing.
The host must use Europe/London local time: launchd calendar jobs follow
the host timezone, not the child process TZ variable. Verify that before
installation and after timezone changes.

Check `launchctl print gui/$(id -u)/com.blackterminal.bsela.process`, other
labels, actual process summaries/ledger outcomes and fresh dogfood/audit files.
Observe a daily run and the first Sunday after 09:10 BST (October 4 if
installed in time). Exit zero alone cannot establish success or processing.
If a timer recurs without running, query bounded launchd unified logs from
Terminal.app for the exact label. An unavailable log probe is not evidence
that launchd ran.

## Lesson evidence acceptance

New persisted distillation candidates must cite an inclusive two-integer
transcript line range within the captured file and overlapping a supplied
detector error. A supplied session id must match the request; old dictionary
clients may omit it and inherit the request id. Invalid or unmatched evidence
rejects the whole response before lesson writes or evaluation checkpoints.
When several errors overlap, the earliest line and then error id determine
the link. This checks citation structure and attribution, not the truth of
every natural-language claim; human review gates still apply.

Each new lesson and its citation are saved in one transaction. The additive
`lesson_evidence` table preserves the session id and range without rewriting
historical lessons. `bsela review show` exposes this metadata; legacy lessons
have no validated citation (`evidence: null` in JSON). Unpersisted preview and
replay drafts remain unverified and never create citation records.

Detector matching now requires standalone runtime diagnostic lines and ignores
fenced examples. Structured HTTP error bodies remain detectable under exit-zero
shell wrappers. Empty-input `write_stdin` polling is excluded from repeated-write
loops. These are bounded heuristics, not proof of agent misconduct; ambiguous
quoted text can still require review. No historical rescan is implied.

To roll back this repair, restore only its changed source files from the
preservation backup. Retain the additive table and database; older application
versions can ignore it. Do not overwrite a live database with the backup.

## Rollback

Use the initial preservation backup and installer backup paths. Restore
affected plists, self-enhance and configuration, then bootstrap the previous
jobs. Return to the previous application revision without resetting unrelated
work. A partial installer failure requires this same explicit file-by-file
rollback before retrying. Preserve the new ledger and historical data;
do not restore an old database over the live store or reconnect retired
providers. No credential cleanup or global lesson application is authorized.
