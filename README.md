# kodo

Autonomous multi-agent coding. An Opus "tech lead" directs Sonnet/Cursor "developers" through persistent sessions, with controllable work cycles and cross-backend coordination.

## Prerequisites

You need **at least one** agent backend installed:

| Backend | What it does | Install |
|---------|-------------|---------|
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) | Smart workers + architect (Claude Max subscription) | `npm install -g @anthropic-ai/claude-code` |
| [Cursor CLI](https://docs.cursor.com/agent) | Fast workers + testers (Cursor subscription) | Comes with Cursor; enable `cursor-agent` in settings |

Both are recommended. Claude Code handles complex reasoning, Cursor handles fast iteration and testing.

For the **API orchestrator** (Gemini or Claude API), set the relevant key in a `.env` file or environment:
```bash
GEMINI_API_KEY=...     # for gemini-flash/gemini-pro orchestrator
ANTHROPIC_API_KEY=...  # for API-billed Claude orchestrator
```

## Install

```bash
# 1. Install uv (Python package manager) — skip if you already have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install kodo as a global CLI tool
uv tool install git+https://github.com/ikamen/kodo

# Or from a local checkout:
git clone https://github.com/ikamen/kodo && cd kodo
uv tool install .
```

That's it. `kodo` is now on your PATH.

## Usage

```bash
# Interactive mode (recommended) — walks you through goal, config, launch
kodo                     # run in current directory
kodo ./my-project        # run in specific directory

# Non-interactive (for scripting)
python -m kodo.main goal.md ./my-project --mode saga --max-cycles 3
```

The interactive CLI will:
1. Ask for your goal (or reuse an existing `goal.md`)
2. Optionally refine it via a Claude interview
3. Let you pick mode, orchestrator, and limits
4. Show a summary and ask for confirmation before starting
5. Print a live progress table as agents work

**Heads up:** agents run with full permissions (`bypassPermissions` mode). They primarily work in your project directory but **can access any file on your system** (installing dependencies, editing configs, etc.). Make sure you have a git commit or backup before launching.

## When to use this over plain Claude Code

- **Role and model separation** — Opus orchestrator making judgment calls, Sonnet workers building code.
- **Cross-backend teams** — mix Claude and Cursor agents on the same goal.
- **Work cycles** — run one cycle, inspect, commit, decide whether to continue. Clean checkpoints.
- **Persistent agent memory** — agents maintain conversation state across multiple tasks within a session.

## When to just use Claude Code directly

- Most tasks. Seriously. Claude Code is good, and orchestration adds latency + cost.
- Single-session work that fits in one context window.
- When you don't need cross-backend coordination.

## Architecture

```
kodo/
  cli.py                     Interactive CLI (goal input → config → launch)
  agent.py                   Agent (prompt + session → run())
  sessions/
    base.py                  Session protocol, QueryResult, SessionStats
    claude.py                ClaudeSession (claude-agent-sdk, persistent)
    cursor.py                CursorSession (cursor-agent CLI, persistent)
  orchestrators/
    base.py                  Orchestrator protocol, CycleResult, RunResult
    api.py                   ApiOrchestrator (Pydantic AI — Anthropic, Gemini)
    claude_code.py           ClaudeCodeOrchestrator (Claude Code + MCP)
  log.py                     JSONL structured logging + live stats
  viewer.py / viewer.html    Browser-based log viewer
```

**Key concepts:**

- **Session** — a stateful conversation with a backend (Claude or Cursor). Tracks token usage, supports reset.
- **Agent** — a prompt + session + turn budget. Call `agent.run(task, project_dir)` to get work done.
- **Orchestrator** — an LLM that delegates to a team of agents via tool calls:
  - `ClaudeCodeOrchestrator` — runs on Claude Code with agents as MCP tools. Free on Max subscription.
  - `ApiOrchestrator` — runs on Anthropic/Gemini API. Pay-per-token.
- **Cycle** — one unit of orchestrated work. Think of it as one dev session.
- **Run** — multiple cycles until done, with summaries bridging context between cycles.

## Cost tracking

Kodo tracks costs in two buckets:

| Bucket | What | Example |
|--------|------|---------|
| **API** | Real money — pay-per-token orchestrator calls | Gemini Flash orchestrator: ~$0.13/run |
| **Subscription** | Covered by flat-rate subscription | Claude Max workers: reported but $0 actual |

The live progress table and final summary show both, so you always know your real spend.

## Analyzing past runs

```bash
# Open the interactive HTML viewer
python -m kodo.viewer .kodo/logs/20260218_205503.jsonl

# Or get a text summary
python analyze_run.py .kodo/logs/*.jsonl
```

## Programmatic usage

```python
from kodo import Agent
from kodo.sessions.claude import ClaudeSession
from kodo.orchestrators.claude_code import ClaudeCodeOrchestrator

session = ClaudeSession(model="sonnet")
team = {
    "worker": Agent(session, "Implement the task given to you.", max_turns=30),
    "reviewer": Agent(ClaudeSession(model="sonnet"), "Review for bugs.", max_turns=10),
}

orch = ClaudeCodeOrchestrator(model="opus")
result = orch.run("Build a REST API for todos", project_dir, team, max_cycles=3)
```
