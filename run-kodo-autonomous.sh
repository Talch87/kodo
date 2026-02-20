#!/bin/bash
# Autonomous Kodo Self-Improvement Runner
# Runs without interactive prompts, logs output, sends report to user

set -e

cd /tmp/kodo-fork

echo "🚀 Starting Kodo Autonomous Self-Improvement"
echo "Goal: Session Resumption, Retry Logic, Task Routing (3 cycles)"
echo "Time: $(date)"
echo ""

# Run Kodo with all non-interactive flags
# --goal-file: use the roadmap
# --mode saga: full team (smart worker, architect, designer, browser)
# --orchestrator api: use API-based orchestrator (sonnet model)
# --max-cycles 3: run 3 improvement cycles
# --yes: skip confirmation prompts

kodo \
  --goal-file ./goal.md \
  . \
  --mode saga \
  --orchestrator api \
  --orchestrator-model sonnet \
  --max-cycles 3 \
  --max-exchanges 100 \
  --yes

echo ""
echo "✅ Kodo run completed"
echo "Timestamp: $(date)"
echo ""
echo "Results:"
git log --oneline -10
echo ""
echo "Artifacts:"
ls -lh improvements/ 2>/dev/null | tail -5 || echo "No improvements directory"
ls -lh tests/ 2>/dev/null | tail -5 || echo "No tests directory"
