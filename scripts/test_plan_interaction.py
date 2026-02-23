#!/usr/bin/env python3
"""Observe: does plan mode capture + orchestrator review work?

Sets up a real Gemini Flash 3 orchestrator + real Claude Code worker.
The orchestrator explicitly tells the worker to enter plan mode with 3
approaches. We observe the [PROPOSED PLAN] → review → approve flow.

Usage:
    uv run python scripts/test_plan_interaction.py
    uv run python scripts/test_plan_interaction.py "your custom goal here"

Requires: GOOGLE_API_KEY (or GEMINI_API_KEY), claude CLI on PATH.
"""

import os
import sys
import tempfile
import textwrap
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ.pop("CLAUDECODE", None)

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from kodo import log, make_session
from kodo.agent import Agent
from kodo.log import RunDir
from kodo.orchestrators.api import ApiOrchestrator
from scripts.harness import (
    instrument_team,
    print_banner,
    print_log_summary,
    print_separator,
)

# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_GOAL = """\
Create a single-page web app that shows "Hello World" with a styled
background and a button that changes the greeting text when clicked.
"""

# Orchestrator prompt: explicitly asks worker to use plan mode
PLAN_FIRST_PROMPT = """\
You are an orchestrator. Your ONLY job is to get the user's desired outcome.

PROCESS — follow these steps using tool calls:

1. DESIGN PHASE: Call ask_worker and tell it to enter plan mode (using
   its built-in plan mode tool) and propose exactly 3 implementation
   approaches. Each approach should name the key technology choices and
   briefly explain trade-offs. The worker must NOT implement yet.

2. CHOOSE: The worker's result will contain [PROPOSED PLAN] with the
   options. Review them. Call ask_worker again telling it which approach
   you picked and why, and tell it to proceed with implementation.

3. DONE: After the worker implements, call the done tool.

IMPORTANT:
- You MUST make a second ask_worker call after reviewing options.
- Keep implementation directives to 1-3 sentences of desired behavior.
- Do NOT include implementation details — the worker is an expert coder.
""".strip()

WORKER_DESC = (
    "A coding agent (Claude Code) that can read/write files, run commands, "
    "and execute the full development workflow.\n"
    "Give it a SHORT directive (1-3 sentences) describing desired BEHAVIOR.\n"
    "If the result contains [PROPOSED PLAN], the worker entered plan mode "
    "and is waiting for your review. Tell it which approach to take.\n"
    "If it seems stuck, set new_conversation=true with a fresh directive."
)


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    goal = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL.strip()

    # Check prerequisites
    has_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not has_key:
        print(
            "ERROR: GOOGLE_API_KEY or GEMINI_API_KEY required for Gemini orchestrator"
        )
        sys.exit(1)

    # Sandbox: temp dir outside the kodo project so agents can't touch our files
    project_dir = Path(tempfile.mkdtemp(prefix="kodo-plan-test-"))

    print_banner("Plan Mode Interaction Test")
    print(f"  Goal:         {goal[:100]}{'...' if len(goal) > 100 else ''}")
    print(f"  Project:      {project_dir}")
    print("  Orchestrator: gemini-3-flash-preview")
    print("  Worker:       claude code (haiku)")

    # Initialize logging inside sandbox
    run_dir = RunDir.create(project_dir)
    log_path = log.init(run_dir)
    log.emit("harness_start", goal=goal, test="plan_interaction")
    print(f"  Log:          {log_path}")

    # Build real worker — haiku for speed, we're observing the pattern
    worker_session = make_session("claude", "haiku", budget=None)
    worker = Agent(worker_session, WORKER_DESC, max_turns=5, timeout_s=60)

    team = instrument_team({"worker": worker})

    # Build orchestrator — no verification team, so fallback verifier is used
    orchestrator = ApiOrchestrator(
        model="gemini-3-flash-preview",
        system_prompt=PLAN_FIRST_PROMPT,
        max_context_tokens=100_000,
    )

    print_separator("━")
    print("  Running single cycle. Observe plan mode capture + review.\n")

    try:
        result = orchestrator.cycle(
            goal,
            project_dir,
            team,
            max_exchanges=15,
        )

        print_banner("Cycle Result")
        print(f"  Finished:  {result.finished}")
        print(f"  Success:   {result.success}")
        print(f"  Exchanges: {result.exchanges}")
        print(f"  Cost:      ${result.total_cost_usd:.4f}")
        if result.summary:
            summary = result.summary
            if len(summary) > 1000:
                summary = summary[:1000] + "..."
            print(f"\n  Summary:\n{textwrap.indent(summary, '    ')}")

        # Replay the log for a clean decision-focused view
        print_log_summary(log_path)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as exc:
        print(f"\n\nERROR: {type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            worker.close()
        except Exception:
            pass

    print(f"\n  Log:     {log_path}")
    print(f"  Project: {project_dir}")
    print()


if __name__ == "__main__":
    main()
