"""selfocode — orchestrated multi-agent coding CLI."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from selfocode import log
from selfocode.factory import build_team, build_orchestrator

# Allow running from inside a Claude Code session
os.environ.pop("CLAUDECODE", None)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        _main_inner()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


def _main_inner() -> None:
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
    parser.add_argument(
        "--backend",
        choices=["claude", "cursor"],
        default="claude",
        help="Backend for worker agents (default: claude)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model for worker agents (default: sonnet / composer-1.5)",
    )
    parser.add_argument(
        "--budget-per-step",
        type=float,
        default=None,
        help="Max USD per agent query (claude only)",
    )
    # Orchestrator options
    parser.add_argument(
        "--orchestrator",
        choices=["api", "claude-code"],
        default="claude-code",
        help="Orchestrator implementation (default: claude-code)",
    )
    parser.add_argument(
        "--orchestrator-model",
        default=None,
        help="Model for orchestrator (default: opus)",
    )
    parser.add_argument(
        "--max-exchanges",
        type=int,
        default=30,
        help="Max exchanges per cycle (default: 30)",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=5, help="Max cycles (default: 5)"
    )

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

    # Initialize logging
    log_path = log.init(project_dir)
    log.emit(
        "cli_args",
        backend=args.backend,
        model=args.model,
        orchestrator=args.orchestrator,
        orchestrator_model=args.orchestrator_model,
        max_exchanges=args.max_exchanges,
        max_cycles=args.max_cycles,
        budget_per_step=args.budget_per_step,
        goal_file=str(goal),
        goal_text=goal_text,
    )

    team = build_team(args.backend, args.model, args.budget_per_step)
    orchestrator = build_orchestrator(args.orchestrator, args.orchestrator_model)

    print(f"Orchestrator: {args.orchestrator} ({orchestrator.model})")
    print(f"Workers: {args.backend} ({args.model})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Project dir: {project_dir}")
    print(f"Max: {args.max_exchanges} exchanges/cycle, {args.max_cycles} cycles")
    print(f"Log: {log_path}")

    result = orchestrator.run(
        goal_text,
        project_dir,
        team,
        max_exchanges=args.max_exchanges,
        max_cycles=args.max_cycles,
    )

    print(f"\n{'=' * 50}")
    print(
        f"Done: {len(result.cycles)} cycle(s), {result.total_exchanges} exchanges, ${result.total_cost_usd:.4f}"
    )
    if result.summary:
        print(f"  {result.summary[:300]}")


if __name__ == "__main__":
    main()
