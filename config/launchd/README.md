# launchd templates

macOS launchd templates for periodic BSELA jobs. These plists are
templates — they hard-code the author's `/Users/black.terminal/...`
paths because launchd does not expand `${HOME}` inside `<string>`
values. Fork and rewrite the paths before loading on another machine.

## Available jobs

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

### `com.blackterminal.bsela.audit.plist` (P5, reserved)

Reserved for the P5 weekly auditor (`bsela audit --weekly`). The
command does not yet exist — keep this plist on disk but do not load
it until P5 ships.

## Notes

* Both plists use `/bin/zsh -lc` so `$PATH` from `~/.zprofile` /
  `~/.zshrc` is available and `bsela` resolves the way it does in an
  interactive terminal.
* `RunAtLoad` and `KeepAlive` are both `false` — we only want the
  scheduled firing, not a daemon-style process.
* The logs directory must exist before the first run. Create it once:

  ```bash
  mkdir -p ~/.bsela/logs ~/.bsela/reports
  ```
