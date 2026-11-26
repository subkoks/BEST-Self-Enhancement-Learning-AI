# BSELA launchd jobs

Templates are workstation-specific. Processing uses Codex ChatGPT login;
DeepSeek is manually selected and never used by scheduled fallback.

| Job | Europe/London schedule | Behavior |
|---|---|---|
| scan | Daily 19:00 | Local capture backstop |
| process | Daily 19:00 | `bsela process --scheduled --provider codex`: 3 sessions Mon–Sat, 10 Sun |
| report | Sunday 19:00 | Write dogfood report |
| audit | Sunday 19:00 | Write audit; nonzero on blocking alerts |

Job environments contain only non-secret settings. Processing reads the
reviewed deployed configuration in `~/.bsela/config`; no shell startup is
needed for credentials. Self-enhance no longer performs model processing.

## Rollout

Complete the offline and approved live gates in `docs/provider-maintenance.md`.
The installer requires `~/.bsela/reports/provider-canary.json` with matching
models and all named checks true. It backs up affected files, creates the
separate live configuration and bootstraps the four BSELA jobs. It does not
kickstart model processing. Run `ops/install-launchd.sh` only for an authorized
rollout. Check loaded jobs with `launchctl print gui/$(id -u)/<label>`.

Calendar counters, log timestamps and actual outcomes establish execution;
a fresh report produced manually does not prove the calendar fired. On the
first eligible Sunday, verify the 19:00 dogfood/audit artifacts and the
process outcome after it exits. The jobs can run concurrently. If a timer
misses, query bounded launchd
unified logs for the exact labels. An empty log does not establish a cause.

## Rollback

Use the installer-reported backup directory. Boot out the four affected labels,
restore their individually backed-up plists plus the previous self-enhance and
configuration files, and bootstrap the previous definitions. Restore the
previous application revision without discarding unrelated work. Keep ledger
rows and existing data; never overwrite the live database automatically.
