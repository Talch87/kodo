#!/bin/bash
# Fixed Kodo Autonomous Runner - Uses claude-code orchestrator (avoids SDK rate_limit_event bug)

set -e

cd /tmp/kodo-fork

echo "🚀 Starting Kodo with Fixed Configuration"
echo "Orchestrator: claude-code (native, avoids SDK parsing bug)"
echo "Goal: Session Resumption, Retry Logic, Task Routing"
echo "Time: $(date)"
echo ""

# Run Kodo with claude-code orchestrator (avoids rate_limit_event bug)
# The issue was with 'api' orchestrator which uses SDK that can't parse rate_limit_event
# claude-code orchestrator runs Kodo's own orchestrator via Claude Code directly

kodo \
  --goal-file ./goal.md \
  . \
  --orchestrator claude-code \
  --max-cycles 3 \
  --max-exchanges 100 \
  --yes

echo ""
echo "✅ Kodo autonomous run completed"
echo "Timestamp: $(date)"
echo ""
echo "Git commits made:"
git log --oneline -10
echo ""
echo "Files created/modified:"
git diff --name-only HEAD~10..HEAD 2>/dev/null | head -20 || echo "No diffs available"
