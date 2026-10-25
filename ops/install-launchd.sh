#!/usr/bin/env bash
# Deploy reviewed BSELA jobs only after explicit live canary/quality evidence.
set -euo pipefail
IFS=$'\n\t'
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVIDENCE="$HOME/.bsela/reports/provider-canary.json"
command -v uv >/dev/null
uv run --frozen --project "$REPO_ROOT" python - "$EVIDENCE" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit('BLOCKED: provider canary evidence missing; deployment not attempted')
data = json.loads(p.read_text())
required = ('offline_gates', 'codex_auth', 'codex_isolation', 'codex_smoke', 'deepseek_smoke', 'quality_review')
if not all(data.get(k) is True for k in required):
    raise SystemExit('BLOCKED: canary/quality gates incomplete; deployment not attempted')
if data.get('codex_model') != 'gpt-6.1-sol' or data.get('deepseek_model') != 'deepseek-flash':
    raise SystemExit('BLOCKED: evidence model mismatch')
PY
BACKUP_ROOT="$(mktemp -d "$HOME/.agents/backups/bsela-deploy-XXXXXXXX")"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
CONFIG_ROOT="$HOME/.bsela/config"
mkdir -p "$HOME/.bsela/logs" "$HOME/.bsela/reports" "$LAUNCH_AGENTS"
for job in scan process report audit; do
    name="com.blackterminal.bsela.$job.plist"
    if [[ -f "$LAUNCH_AGENTS/$name" ]]; then cp -p "$LAUNCH_AGENTS/$name" "$BACKUP_ROOT/$name"; fi
    plutil -lint "$REPO_ROOT/config/launchd/$name" >/dev/null
done
if [[ -d "$CONFIG_ROOT" ]]; then cp -R "$CONFIG_ROOT" "$BACKUP_ROOT/config"; fi
cp -p "$HOME/.agents/scripts/self-enhance.sh" "$BACKUP_ROOT/self-enhance.sh"
mkdir -p "$CONFIG_ROOT"
cp "$REPO_ROOT/config/thresholds.toml" "$CONFIG_ROOT/thresholds.toml"
uv run --frozen --project "$REPO_ROOT" python - "$REPO_ROOT/config/models.toml" "$CONFIG_ROOT/models.toml" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
Path(sys.argv[2]).write_text(source.replace('live_enabled = false', 'live_enabled = true'))
PY
cp -p "$REPO_ROOT/ops/self-enhance.sh" "$HOME/.agents/scripts/self-enhance.sh"
DOMAIN="gui/$(id -u)"
for job in scan process report audit; do
    label="com.blackterminal.bsela.$job"
    if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then launchctl bootout "$DOMAIN/$label"; fi
    cp "$REPO_ROOT/config/launchd/$label.plist" "$LAUNCH_AGENTS/$label.plist"
    launchctl bootstrap "$DOMAIN" "$LAUNCH_AGENTS/$label.plist"
    launchctl print "$DOMAIN/$label" >/dev/null
    echo "Installed $label"
done
echo "Rollback files: $BACKUP_ROOT"
echo "Daily process 08:00; Sunday report/audit 09:00 Europe/London. No model job kickstarted."
