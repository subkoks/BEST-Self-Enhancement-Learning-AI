# launchd templates

macOS launchd templates for periodic BSELA jobs. These plists are
templates — they hard-code the author's `/Users/black.terminal/...`
paths because launchd does not expand `${HOME}` inside `<string>`
values. Fork and rewrite the paths before loading on another machine.

## Available jobs

### `com.blackterminal.bsela.process.plist` (P4+, active)

Runs `bsela process --limit 20` every Monday at 08:00 local time —
one hour before the audit job. Batch-distills recent sessions using
`OPENROUTER_API_KEY` (or `ANTHROPIC_API_KEY`) sourced from the shell
environment. Writes stdout/stderr to `~/.bsela/logs/process.*.log`.

```bash
cp config/launchd/com.blackterminal.bsela.process.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.blackterminal.bsela.process.plist
```

Verify it's queued:

```bash
launchctl list | grep bsela.process
```

Unload:

```bash
launchctl unload -w ~/Library/LaunchAgents/com.blackterminal.bsela.process.plist
```

### `com.blackterminal.bsela.report.plist` (P4, active)

Runs `bsela report` every Monday at 09:00 local time. Writes the
rolling dogfood markdown to `~/.bsela/reports/dogfood.md` and appends
stdout/stderr to `~/.bsela/logs/report.*.log`.

```bash
cp config/launchd/com.blackterminal.bsela.report.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.blackterminal.bsela.report.plist
```

Verify it's queued:

```bash
launchctl list | grep bsela.report
```

Unload:

```bash
launchctl unload -w ~/Library/LaunchAgents/com.blackterminal.bsela.report.plist
```

### `com.blackterminal.bsela.audit.plist` (P5, active)

Runs `bsela audit --weekly` every Monday at 09:00 local time. Writes
the 30-day digest to `~/.bsela/reports/audit.md` and appends
stdout/stderr to `~/.bsela/logs/audit.*.log`. Exits non-zero on any
active alert (cost burn, drift, ADR hygiene) so the stderr log
surfaces the signal.

```bash
cp config/launchd/com.blackterminal.bsela.audit.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.blackterminal.bsela.audit.plist
```

Verify it's queued:

```bash
launchctl list | grep bsela.audit
```

Unload:

```bash
launchctl unload -w ~/Library/LaunchAgents/com.blackterminal.bsela.audit.plist
```

## Notes

* All plists use `/bin/zsh -lc` so `$PATH` from `~/.zprofile` /
  `~/.zshrc` is available and `bsela` resolves the way it does in an
  interactive terminal. `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY`
  must be exported in `~/.zprofile` (not only `~/.zshrc`) so the
  non-interactive login shell picks them up.
* `RunAtLoad` and `KeepAlive` are both `false` — we only want the
  scheduled firing, not a daemon-style process.
* The logs directory must exist before the first run. Create it once:

  ```bash
  mkdir -p ~/.bsela/logs ~/.bsela/reports
  ```
