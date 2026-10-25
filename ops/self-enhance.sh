#!/usr/bin/env zsh
# Self-enhancement workflow.
# Runs local ingestion/review/reporting; model processing belongs to launchd.
# Usage: self-enhance.sh [--ingest-only | --process-only | --review-only | --full]
set -euo pipefail

SELF="$(basename "$0")"
DATE_STAMP="$(date -u +%Y%m%d)"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STATUS=0

BSELA_CLI="$(which bsela 2>/dev/null || echo "$HOME/Projects/Current/Active/BEST-Self-Enhancement-Learning-AI/.venv/bin/bsela")"
MODE="${1:---full}"

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME")"
AGENT_DIR="$PROJECT_ROOT/.agent"
ENHANCE_DIR="$AGENT_DIR/enhancements"
mkdir -p "$ENHANCE_DIR"

REPORT="$ENHANCE_DIR/${DATE_STAMP}.md"

log() { echo "[$SELF] $*"; }
error() { echo "[$SELF] ERROR: $*" >&2; STATUS=1; }
warn() { echo "[$SELF] WARN: $*" >&2; STATUS=1; }

log "Self-enhancement loop starting (mode=$MODE)"

cat > "$REPORT" <<EOF
# Self-Enhancement Report — $DATE_STAMP

**Generated:** $TIMESTAMP
**Mode:** $MODE

EOF

# --- Phase: Ingestion ---
run_ingest() {
  log "Phase 1: Session ingestion"
  echo "## 1. Session Ingestion" >> "$REPORT"
  if [[ ! -x "$BSELA_CLI" ]]; then
    echo "BSELA CLI not found at $BSELA_CLI" >> "$REPORT"
    warn "BSELA CLI not available — skipping ingest"
    echo "" >> "$REPORT"
    return
  fi

  local session_dir="$HOME/.claude/projects"
  local ingested=0

  # Auto-discover session transcripts from all project dirs
  # Limit to last 7 days to avoid re-processing everything
  local cut_date
  cut_date=$(date -u -v-7d +%s 2>/dev/null || echo "")

  echo "Looking for recent sessions in $session_dir" >> "$REPORT"
  while IFS= read -r session_file; do
    local file_date
    file_date=$(stat -f "%m" "$session_file" 2>/dev/null || echo "0")
    if [[ -n "$cut_date" && "$file_date" -lt "$cut_date" ]]; then
      continue
    fi
    local ingest_out
    ingest_out=$("$BSELA_CLI" ingest "$session_file" --source "claude_code" 2>&1) || warn "bsela ingest returned non-zero"
    if echo "$ingest_out" | grep -qi "captured\|ingested\|stored\|created"; then
      echo "  ingested: $(basename "$(dirname "$session_file")")/$(basename "$session_file")" >> "$REPORT"
      ingested=$((ingested + 1))
    fi
  done < <(find "$session_dir" -name '*.jsonl' -type f 2>/dev/null)

  if [[ $ingested -eq 0 ]]; then
    echo "No new sessions found in last 7 days." >> "$REPORT"
    log "No new sessions to ingest"
  else
    echo "Ingested $ingested session(s)." >> "$REPORT"
    log "Ingested $ingested sessions"
  fi
  echo "" >> "$REPORT"
}

# --- Phase: Process (detect -> judge -> distill) ---
run_process() {
  log "Phase 2: Model processing delegated to the BSELA process LaunchAgent"
  {
    echo "## 2. Batch Processing"
    echo "Scheduled independently at 08:00; this helper makes no model calls."
    echo ""
  } >> "$REPORT"
}

# --- Phase: Review gate ---
run_review() {
  log "Phase 3: Review gate"
  echo "## 3. Review Gate" >> "$REPORT"
  if [[ -x "$BSELA_CLI" ]]; then
    local review_out
    review_out=$("$BSELA_CLI" review 2>&1) || warn "bsela review returned non-zero"
    {
      echo '```'
      echo "$review_out"
      echo '```'
    } >> "$REPORT"
    log "Review complete"
  else
    echo "BSELA CLI not found." >> "$REPORT"
    warn "BSELA CLI not found"
  fi
  echo "" >> "$REPORT"
}

# --- Phase: Audit ---
run_audit() {
  log "Phase 4: BSELA audit"
  echo "## 4. BSELA Audit" >> "$REPORT"
  if [[ -x "$BSELA_CLI" ]]; then
    local audit_out
    audit_out=$("$BSELA_CLI" audit 2>&1) || warn "bsela audit returned non-zero"
    {
      echo '```'
      echo "$audit_out"
      echo '```'
    } >> "$REPORT"
    log "Audit complete"
  else
    echo "BSELA CLI not found." >> "$REPORT"
    warn "BSELA CLI not found"
  fi
  echo "" >> "$REPORT"
}

# --- Phase: governance check (agents-md) ---
run_governance() {
  log "Phase 5: Governance drift check"
  echo "## 5. Governance Drift Check" >> "$REPORT"
  local GOV_SCRIPT="$HOME/Projects/Current/Active/agents-md/scripts/check-local-drift.sh"
  if [[ -x "$GOV_SCRIPT" ]]; then
    local gov_out
    gov_out=$("$GOV_SCRIPT" 2>&1) || warn "governance drift check returned non-zero"
    {
      echo '```'
      echo "$gov_out"
      echo '```'
    } >> "$REPORT"
  else
    echo "Governance script not found at $GOV_SCRIPT (optional)" >> "$REPORT"
  fi
  echo "" >> "$REPORT"
}

# --- Execute phases based on mode ---
case "$MODE" in
  --ingest-only)
    run_ingest
    ;;
  --process-only)
    run_process
    ;;
  --review-only)
    run_review
    ;;
  --full|"")
    run_ingest
    run_process
    run_review
    run_audit
    run_governance
    ;;
  *)
    error "Unknown mode: $MODE"
    echo "Usage: $SELF [--ingest-only | --process-only | --review-only | --full]"
    exit 1
    ;;
esac

# --- Summary ---
cat >> "$REPORT" <<EOF
## Summary
$([[ $STATUS -eq 0 ]] && echo "**Status:** Completed successfully" || echo "**Status:** Completed with warnings (see above)")

**Next steps:**
- Review proposed lessons: \`bsela review propose <id>\`
- Run weekly audit: \`bsela audit\`
- Check agent memory: \`hacker-agent dashboard\`

---
*Generated by self-enhance.sh*
EOF

log "Enhancement report written to $REPORT"
exit $STATUS
