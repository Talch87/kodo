#!/bin/bash
# Continuous Kodo Autonomous Self-Improvement Daemon
# Runs improvement cycles indefinitely with auto-restart on crash

set -e

cd /tmp/kodo-fork

# Set PATH to include kodo/node binaries
export PATH="/home/clawd/.local/bin:/home/clawd/.npm-global/bin:$PATH"

# FORCE Kodo to use Claude Code Max subscription (bundled agents)
# DO NOT use API key - unbundle only
unset ANTHROPIC_API_KEY

LOG_FILE="/tmp/kodo-daemon-$(date +%Y%m%d).log"
PID_FILE="/tmp/kodo-daemon.pid"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cleanup() {
    log "Shutdown signal received"
    rm -f "$PID_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT

log "🚀 Starting Kodo Continuous Daemon"
log "Improvement cycles will run indefinitely"
log "Log: $LOG_FILE"

echo $$ > "$PID_FILE"

CYCLE_COUNT=0

while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    log "=========================================="
    log "Starting improvement cycle #$CYCLE_COUNT"
    log "=========================================="
    
    # Run Kodo with continuous improvement goal (cheap: haiku orchestrator)
    if kodo \
        --goal-file ./goal-continuous.md \
        . \
        --orchestrator claude-code \
        --orchestrator-model haiku \
        --max-cycles 2 \
        --max-exchanges 50 \
        --no-intake \
        --yes >> "$LOG_FILE" 2>&1; then
        
        log "✅ Cycle #$CYCLE_COUNT completed successfully"
        
        # Get latest commits
        COMMITS=$(git log --oneline -3 | head -1)
        log "Latest: $COMMITS"
        
    else
        EXIT_CODE=$?
        log "⚠️ Cycle #$CYCLE_COUNT exited with code $EXIT_CODE"
    fi
    
    # Wait before next cycle (2 hours)
    log "Waiting 2 hours before next cycle..."
    sleep 7200
done
