"""selfocode interactive CLI — guided project setup and launch."""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from simple_term_menu import TerminalMenu

from selfocode import log
from selfocode.factory import build_team, build_orchestrator

INTAKE_PROMPT = """\
You are a project intake interviewer. The user has provided a high-level goal \
for a software project. Your job is to:

1. Read the goal from .selfocode/goal.md
2. Ask clarifying questions about constraints, tech choices, edge cases, \
   architecture preferences, and scope
3. Have a natural conversation to refine the goal
4. When you have enough clarity, write a refined, detailed goal to \
   .selfocode/goal-refined.md

Keep the conversation focused and practical. When you feel the goal is \
sufficiently clarified, write the refined goal file and tell the user \
they can type /exit to proceed."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_goal() -> str:
    """Prompt user for a multiline goal. Empty line finishes input."""
    print("\nWhat's your goal? (Enter an empty line to finish)")
    print("-" * 40)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        print("No goal provided. Exiting.")
        sys.exit(1)
    return text


def _extract_intake_transcript(project_dir: Path, session_id: str) -> None:
    """Extract human-readable transcript from a Claude Code session file."""
    # Claude stores sessions under ~/.claude/projects/<escaped-path>/<session-id>.jsonl
    escaped = str(project_dir).replace("/", "-")
    session_file = (
        Path.home() / ".claude" / "projects" / escaped / f"{session_id}.jsonl"
    )
    if not session_file.exists():
        return

    lines = []
    for raw in session_file.read_text().splitlines():
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg_type = d.get("type")
        if msg_type not in ("user", "assistant"):
            continue

        content = (
            d.get("message", {}).get("content", "")
            if isinstance(d.get("message"), dict)
            else ""
        )

        # Skip system/command messages
        if isinstance(content, str) and content.startswith("<"):
            continue

        # Flatten content blocks
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        parts.append(f"*[Tool: {block['name']}]*")
                    elif block.get("type") == "tool_result":
                        parts.append("*[Tool result]*")
                else:
                    parts.append(str(block))
            content = "\n".join(parts)

        if not content or not content.strip():
            continue

        role = "User" if msg_type == "user" else "Claude"
        lines.append(f"### {role}\n{content.strip()}\n")

    if lines:
        selfo_dir = project_dir / ".selfocode"
        transcript_path = selfo_dir / "intake-transcript.md"
        transcript_path.write_text(
            f"# Intake Interview Transcript\n\n"
            f"*Session ID: {session_id}*\n\n---\n\n" + "\n".join(lines)
        )


def run_intake(project_dir: Path, goal_text: str) -> str:
    """Write goal.md, launch interactive Claude session for intake, read back refined goal."""
    selfo_dir = project_dir / ".selfocode"
    selfo_dir.mkdir(parents=True, exist_ok=True)

    goal_path = selfo_dir / "goal.md"
    goal_path.write_text(goal_text)
    print(f"\nGoal saved to {goal_path}")

    session_id = str(uuid.uuid4())
    print("\n--- Intake interview (chat with Claude, /exit when done) ---\n")
    proc = subprocess.run(
        [
            "claude",
            "--session-id",
            session_id,
            "--system-prompt",
            INTAKE_PROMPT,
            "--permission-mode",
            "acceptEdits",
        ],
        cwd=project_dir,
        env={k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
    )
    if proc.returncode != 0:
        print(f"\nWarning: claude exited with code {proc.returncode}")

    # Save session ID and extract transcript
    (selfo_dir / "intake-session-id.txt").write_text(session_id)
    _extract_intake_transcript(project_dir, session_id)

    refined_path = selfo_dir / "goal-refined.md"
    if refined_path.exists():
        refined = refined_path.read_text().strip()
        print(f"\nRefined goal read from {refined_path}")
        return refined

    print("\nNo refined goal written; using original goal.")
    return goal_text


def _select_one(title: str, options: list[str], default_index: int = 0) -> str:
    """Arrow-key single selection. Returns the chosen string."""
    menu = TerminalMenu(
        options,
        title=title,
        cursor_index=default_index,
    )
    idx = menu.show()
    if idx is None:
        print("Cancelled.")
        sys.exit(1)
    return options[idx]


def _select_numeric(
    title: str, presets: list[str], default_index: int = 0, type_fn: type = int
) -> str:
    """Arrow-key selection with a 'Custom...' option for numeric values."""
    choices = presets + ["Custom..."]
    menu = TerminalMenu(
        choices,
        title=title,
        cursor_index=default_index,
    )
    idx = menu.show()
    if idx is None:
        print("Cancelled.")
        sys.exit(1)
    if choices[idx] != "Custom...":
        return choices[idx]
    while True:
        raw = input("  Enter value: ").strip()
        try:
            type_fn(raw)
            return raw
        except (ValueError, TypeError):
            print(f"  Invalid input. Expected {type_fn.__name__}.")


def select_params() -> dict:
    """Interactive arrow-key parameter selection. Returns config dict."""
    print("\n--- Configuration ---\n")

    backend = _select_one("Backend:", ["claude", "cursor"])
    if backend == "cursor":
        model = _select_one("Worker model:", ["composer-1.5", "sonnet", "opus"])
    else:
        model = _select_one("Worker model:", ["sonnet", "opus"])
    orchestrator = _select_one("Orchestrator:", ["claude-code", "api"])
    orch_model = _select_one(
        "Orchestrator model:", ["opus", "sonnet", "gemini-pro", "gemini-flash"]
    )
    print("  Each exchange is one orchestrator turn: it thinks, delegates to an")
    print("  agent, and reads the result. More exchanges = more work per cycle.")
    max_exchanges = _select_numeric(
        "Max exchanges per cycle:", ["20", "30", "50"], default_index=1
    )
    print("  A cycle is one full orchestrator session. If it doesn't finish,")
    print("  a new cycle starts with a summary of prior progress.")
    max_cycles = _select_numeric("Max cycles:", ["3", "5", "10"], default_index=1)
    budget_raw = _select_numeric(
        "Budget per step (USD):", ["None", "1.00", "5.00"], type_fn=float
    )

    budget = None if budget_raw == "None" else float(budget_raw)

    return {
        "backend": backend,
        "model": model,
        "orchestrator": orchestrator,
        "orchestrator_model": orch_model,
        "max_exchanges": int(max_exchanges),
        "max_cycles": int(max_cycles),
        "budget_per_step": budget,
    }


def launch_run(project_dir: Path, goal_text: str, params: dict) -> None:
    """Build team + orchestrator and run."""
    log_path = log.init(project_dir)
    log.emit("cli_args", **params, goal_text=goal_text)

    team = build_team(params["backend"], params["model"], params["budget_per_step"])
    orchestrator = build_orchestrator(
        params["orchestrator"], params["orchestrator_model"]
    )

    print(f"\nOrchestrator: {params['orchestrator']} ({orchestrator.model})")
    print(f"Workers: {params['backend']} ({params['model']})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Project dir: {project_dir}")
    print(
        f"Max: {params['max_exchanges']} exchanges/cycle, {params['max_cycles']} cycles"
    )
    print(f"Log: {log_path}")
    print()

    result = orchestrator.run(
        goal_text,
        project_dir,
        team,
        max_exchanges=params["max_exchanges"],
        max_cycles=params["max_cycles"],
    )

    print(f"\n{'=' * 50}")
    print(
        f"Done: {len(result.cycles)} cycle(s), {result.total_exchanges} exchanges, ${result.total_cost_usd:.4f}"
    )
    if result.summary:
        print(f"  {result.summary[:300]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        _main_inner()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


def _main_inner() -> None:
    from selfocode import __version__

    parser = argparse.ArgumentParser(
        description="Interactive selfocode launcher",
    )
    parser.add_argument(
        "--version", action="version", version=f"selfocode {__version__}"
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_dir = project_dir.resolve()
    print(f"Project directory: {project_dir}")

    # 1. Get goal
    goal_text = get_goal()

    # 2. Intake interview
    skip = input("\nRefine goal with Claude? [Y/n] ").strip().lower()
    if not skip or skip == "y":
        goal_text = run_intake(project_dir, goal_text)
    else:
        selfo_dir = project_dir / ".selfocode"
        selfo_dir.mkdir(parents=True, exist_ok=True)
        (selfo_dir / "goal.md").write_text(goal_text)

    # 3. Select parameters
    params = select_params()

    # 4. Confirm
    print("\n--- Summary ---")
    print(f"  Project:      {project_dir}")
    print(f"  Goal:         {goal_text[:80]}{'...' if len(goal_text) > 80 else ''}")
    print(f"  Backend:      {params['backend']}")
    print(f"  Worker model: {params['model']}")
    print(f"  Orchestrator: {params['orchestrator']} ({params['orchestrator_model']})")
    print(f"  Exchanges:    {params['max_exchanges']}")
    print(f"  Cycles:       {params['max_cycles']}")
    print(f"  Budget/step:  {params['budget_per_step']}")
    print()

    confirm = input("Proceed? [Y/n] ").strip().lower()
    if confirm and confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # 5. Launch
    launch_run(project_dir, goal_text, params)


if __name__ == "__main__":
    main()
