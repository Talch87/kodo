# selfocode

Experiment in explicit multi-agent orchestration on top of Claude Code and Cursor.

An Opus "tech lead" directs Sonnet "developers" through persistent sessions, with controllable work cycles and cross-backend coordination.

## When to use this over plain Claude Code

- **Role and model separation** — Opus orchestrator making judgment calls, Sonnet workers building code. Claude Code doesn't offer this split.
- **Cross-backend teams** — mix Claude and Cursor agents on the same goal.
- **Programmatic work cycles** — run one cycle, inspect, commit, decide whether to continue. The `cycle()` API gives you clean checkpoints.
- **Persistent agent memory** — agents maintain conversation state across multiple tasks within a session, unlike Claude Code's ephemeral sub-agents.

## When to just use Claude Code directly

- Most tasks. Seriously. Claude Code is good at what it does, and adding an orchestration layer on top adds latency, cost, and complexity.
- Single-session work that fits in one context window.
- When you don't need cross-backend coordination.

This is a research tool for exploring whether explicit team structures and persistent agent sessions produce better results on ambitious projects. It's not a replacement for Claude Code — it's built on top of it.

## Quick start

```bash
# Install
uv sync

# Run with defaults: Opus orchestrator + Sonnet workers (free on Max subscription)
.venv/bin/python main.py goal.md ./my-project

# Single cycle ("one day of work")
.venv/bin/python main.py goal.md ./my-project --max-cycles 1

# Cursor workers with Claude orchestrator
.venv/bin/python main.py goal.md ./my-project --backend cursor --model composer-1.5

# API orchestrator (pay-per-token, useful outside Max subscription)
.venv/bin/python main.py goal.md ./my-project --orchestrator api

# Limit agent context windows
.venv/bin/python main.py goal.md ./my-project --max-context-tokens 150000
```

## Architecture

```
main.py                        CLI entry point
selfocode/
  agent.py                     Agent (prompt + session → run())
  sessions/
    base.py                    Session protocol, QueryResult, SessionStats
    claude.py                  ClaudeSession (claude-agent-sdk, persistent)
    cursor.py                  CursorSession (cursor-agent CLI, persistent)
  orchestrators/
    base.py                    Orchestrator protocol, CycleResult, RunResult
    api.py                     ApiOrchestrator (Anthropic API + tool_use)
    claude_code.py             ClaudeCodeOrchestrator (Claude Code + in-process MCP)
examples/
  naive_loop.py                Simple plan-execute loop using primitives
```

**Key concepts:**

- **Session** — a stateful conversation with a backend (Claude or Cursor). Tracks token usage, supports reset.
- **Agent** — a prompt + session + turn budget. Call `agent.run(task, project_dir)` to get work done.
- **Orchestrator** — an LLM that delegates to a team of agents via tool calls. Two implementations with the same interface:
  - `ClaudeCodeOrchestrator` — runs on Claude Code with agents exposed as MCP tools. Free on Max subscription.
  - `ApiOrchestrator` — runs on the Anthropic API directly. Pay-per-token, any model.
- **Cycle** — one unit of orchestrated work. The orchestrator gets a goal, delegates to agents, returns a summary. Think of it as one dev session.
- **Run** — multiple cycles until done. Each cycle gets the previous cycle's summary as context.

## Programmatic usage

```python
from selfocode import Agent
from selfocode.sessions import ClaudeSession
from selfocode.orchestrators import ClaudeCodeOrchestrator

session = ClaudeSession(model="sonnet")
team = {
    "worker": Agent(session, "You are a developer. Implement the task given to you.", max_turns=30),
    "reviewer": Agent(ClaudeSession(model="sonnet"), "You are a code reviewer. Review for bugs and simplicity.", max_turns=10),
}

orch = ClaudeCodeOrchestrator(model="opus")

# One cycle
result = orch.cycle("Build a REST API for todos", project_dir, team)
print(result.summary)

# Or let it run
result = orch.run("Build a REST API for todos", project_dir, team, max_cycles=3)
```

## Context management

Three layers:

1. **Agent level** — each agent auto-resets its session when `max_context_tokens` is exceeded. The orchestrator can also request `new_conversation: true` per tool call to start an agent fresh.
2. **Tool results** — every agent response includes context stats (tokens used, session total) so the orchestrator can reason about when to reset.
3. **Orchestrator level** — each cycle is a bounded context. Between cycles, progress is compressed into a summary that seeds the next cycle.

## What's honestly worse than plain Claude Code

- More moving parts. Claude Code is one process that just works.
- Orchestrator overhead — every agent call round-trips through the orchestrator's context window.
- Claude Code's built-in context compression is more battle-tested.
- Bad orchestrator delegation wastes entire agent calls. Claude Code's internal routing is tighter.
