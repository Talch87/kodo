"""kodo — orchestrated multi-agent coding CLI."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from kodo import log
from kodo.factory import MODES, get_mode, build_orchestrator

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
  # Default: saga mode — full team (two workers, tester, architect)
  python main.py goal.md ./project

  # Mission mode: single worker, orchestrator as quality gate
  python main.py goal.md ./project --mode mission

  # Single cycle (one "day of work")
  python main.py goal.md ./project --max-cycles 1

  # API orchestrator (pay-per-token, supports Gemini)
  python main.py goal.md ./project --orchestrator api --orchestrator-model gemini-pro
""",
    )
    parser.add_argument("goal", help="Path to goal .md file")
    parser.add_argument("project_dir", help="Path to project directory")

    parser.add_argument(
        "--mode",
        choices=list(MODES.keys()),
        default="saga",
        help="Run mode (default: saga)",
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
        default=None,
        help="Max exchanges per cycle (default: from mode)",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Max cycles (default: from mode)",
    )

    args = parser.parse_args()

    mode = get_mode(args.mode)
    max_exchanges = args.max_exchanges or mode.default_max_exchanges
    max_cycles = args.max_cycles or mode.default_max_cycles

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
        mode=mode.name,
        orchestrator=args.orchestrator,
        orchestrator_model=args.orchestrator_model,
        max_exchanges=max_exchanges,
        max_cycles=max_cycles,
        budget_per_step=args.budget_per_step,
        goal_file=str(goal),
        goal_text=goal_text,
    )

    team = mode.build_team(args.budget_per_step)
    orchestrator = build_orchestrator(
        args.orchestrator, args.orchestrator_model, system_prompt=mode.system_prompt
    )

    print(f"Mode: {mode.name} — {mode.description}")
    print(f"Orchestrator: {args.orchestrator} ({orchestrator.model})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Project dir: {project_dir}")
    print(f"Max: {max_exchanges} exchanges/cycle, {max_cycles} cycles")
    print(f"Log: {log_path}")

    result = orchestrator.run(
        goal_text,
        project_dir,
        team,
        max_exchanges=max_exchanges,
        max_cycles=max_cycles,
    )

    print(f"\n{'=' * 50}")
    print(
        f"Done: {len(result.cycles)} cycle(s), {result.total_exchanges} exchanges, ${result.total_cost_usd:.4f}"
    )
    if result.summary:
        print(f"  {result.summary[:300]}")


if __name__ == "__main__":
    main()
