"""selfocode — orchestrated multi-agent coding CLI."""

import argparse
import os
import sys
from pathlib import Path

from selfocode.agent import Agent
from selfocode.sessions.claude import ClaudeSession
from selfocode.sessions.cursor import CursorSession

# Allow running from inside a Claude Code session
os.environ.pop("CLAUDECODE", None)

# ---------------------------------------------------------------------------
# Agent prompts
# ---------------------------------------------------------------------------

PLAN_PROMPT = """\
You are an autonomous planning agent. You will be given a project goal and the current state of a project directory.

Your job:
1. Read the goal carefully.
2. Examine the current project state (files, code, tests, etc.).
3. Write or update `plan.md` in the project directory with a concrete, ordered list of next steps.

Each step in plan.md should be a checkbox item like:
- [ ] Step description
- [x] Completed step

Mark steps that are already done as [x]. Focus on the next actionable steps.
Only write/update plan.md — do not implement anything."""

EXECUTE_PROMPT = """\
You are an autonomous execution agent. You will be given a project goal and a plan.

Your job:
1. Read `plan.md` in the project directory.
2. Find the FIRST unchecked step (- [ ]).
3. Implement that step fully — write code, create files, run commands, run tests, etc.
4. After completing the step, update `plan.md` to mark it as done (- [x]).

Only do ONE step per invocation. Be thorough — make sure the step actually works."""

ARCHITECT_PROMPT = """\
You are a software architect reviewing a project for simplicity and correctness.

Your job:
1. Read the current codebase and plan.md.
2. Identify unnecessary complexity, missing abstractions, or wrong approaches.
3. Provide a brief, actionable critique — what should change and why.

Be concise. Focus on structural issues, not style."""

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _make_session(backend: str, model: str, budget: float | None):
    if backend == "cursor":
        return CursorSession(model=model)
    return ClaudeSession(model=model, max_budget_usd=budget)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrated multi-agent coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # Default: Opus orchestrator + Sonnet workers (all free on Max)
  python main.py goal.md ./project

  # Single cycle (one "day of work")
  python main.py goal.md ./project --max-cycles 1

  # Cursor workers with Claude orchestrator
  python main.py goal.md ./project --backend cursor --model composer-1.5

  # API orchestrator (pay-per-token)
  python main.py goal.md ./project --orchestrator api
""",
    )
    parser.add_argument("goal", help="Path to goal .md file")
    parser.add_argument("project_dir", help="Path to project directory")

    # Worker options
    parser.add_argument("--backend", choices=["claude", "cursor"], default="claude",
                        help="Backend for worker agents (default: claude)")
    parser.add_argument("--model", default=None,
                        help="Model for worker agents (default: sonnet / composer-1.5)")
    parser.add_argument("--budget-per-step", type=float, default=None,
                        help="Max USD per agent query (claude only)")
    parser.add_argument("--max-context-tokens", type=int, default=None,
                        help="Auto-reset agent session at this token count")

    # Orchestrator options
    parser.add_argument("--orchestrator", choices=["api", "claude-code"], default="claude-code",
                        help="Orchestrator implementation (default: claude-code)")
    parser.add_argument("--orchestrator-model", default=None,
                        help="Model for orchestrator (default: opus)")
    parser.add_argument("--max-exchanges", type=int, default=30,
                        help="Max exchanges per cycle (default: 30)")
    parser.add_argument("--max-cycles", type=int, default=5,
                        help="Max cycles (default: 5)")

    args = parser.parse_args()

    if args.model is None:
        args.model = "sonnet" if args.backend == "claude" else "composer-1.5"

    goal = Path(args.goal)
    if not goal.exists():
        print(f"Error: goal file not found: {args.goal}")
        sys.exit(1)
    goal_text = goal.read_text()

    project_dir = Path(args.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_dir = project_dir.resolve()

    # Build team — each role gets its own session for isolation
    ctx_limit = args.max_context_tokens
    worker_session = _make_session(args.backend, args.model, args.budget_per_step)
    architect_session = _make_session(args.backend, args.model, args.budget_per_step)
    planner_session = _make_session(args.backend, args.model, args.budget_per_step)

    team = {
        "worker": Agent(worker_session, EXECUTE_PROMPT, max_turns=30, max_context_tokens=ctx_limit),
        "architect": Agent(architect_session, ARCHITECT_PROMPT, max_turns=10, max_context_tokens=ctx_limit),
        "planner": Agent(planner_session, PLAN_PROMPT, max_turns=15, max_context_tokens=ctx_limit),
    }

    # Build orchestrator
    if args.orchestrator == "api":
        from selfocode.orchestrators.api import ApiOrchestrator
        orch_model = args.orchestrator_model or "claude-opus-4-6"
        orchestrator = ApiOrchestrator(model=orch_model, max_context_tokens=ctx_limit)
    else:
        from selfocode.orchestrators.claude_code import ClaudeCodeOrchestrator
        orch_model = args.orchestrator_model or "opus"
        orchestrator = ClaudeCodeOrchestrator(model=orch_model)

    print(f"Orchestrator: {args.orchestrator} ({orch_model})")
    print(f"Workers: {args.backend} ({args.model})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Project dir: {project_dir}")
    print(f"Max: {args.max_exchanges} exchanges/cycle, {args.max_cycles} cycles")
    if ctx_limit:
        print(f"Agent context limit: {ctx_limit:,} tokens")

    result = orchestrator.run(
        goal_text, project_dir, team,
        max_exchanges=args.max_exchanges,
        max_cycles=args.max_cycles,
    )

    print(f"\n{'='*50}")
    print(f"Done: {len(result.cycles)} cycle(s), {result.total_exchanges} exchanges, ${result.total_cost_usd:.4f}")
    if result.summary:
        print(f"  {result.summary[:300]}")


if __name__ == "__main__":
    main()
