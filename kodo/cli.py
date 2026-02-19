"""kodo interactive CLI — guided project setup and launch."""

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

from kodo import log, __version__
from kodo.factory import MODES, get_mode, build_orchestrator, has_claude, has_cursor
from kodo.orchestrators.base import ResumeState


def _print_banner() -> None:
    print(f"\n  kodo v{__version__} — autonomous multi-agent coding")
    print(f"  https://github.com/ikamen/kodo\n")

INTAKE_PROMPT = """\
You are a project intake interviewer. The user has provided a high-level goal \
for a software project. Your job is to:

1. Read the goal from .kodo/goal.md
2. Ask clarifying questions about constraints, tech choices, edge cases, \
   architecture preferences, and scope
3. Have a natural conversation to refine the goal
4. When you have enough clarity, write a refined, detailed goal to \
   .kodo/goal-refined.md

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
        selfo_dir = project_dir / ".kodo"
        transcript_path = selfo_dir / "intake-transcript.md"
        transcript_path.write_text(
            f"# Intake Interview Transcript\n\n"
            f"*Session ID: {session_id}*\n\n---\n\n" + "\n".join(lines)
        )


def run_intake(project_dir: Path, goal_text: str) -> str:
    """Write goal.md, launch interactive Claude session for intake, read back refined goal."""
    selfo_dir = project_dir / ".kodo"
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

    # Show available backends
    _claude = has_claude()
    _cursor = has_cursor()
    if not _claude and not _cursor:
        print("Error: no worker backends found.")
        print("  Install at least one of:")
        print("    Claude Code CLI  — https://docs.anthropic.com/en/docs/claude-code")
        print("    Cursor CLI       — https://docs.cursor.com/agent")
        sys.exit(1)
    parts = []
    parts.append(f"Claude Code: {'yes' if _claude else 'not found'}")
    parts.append(f"Cursor: {'yes' if _cursor else 'not found'}")
    print(f"  Backends: {' | '.join(parts)}\n")

    # Mode selection
    mode_options = [f"{name} — {m.description}" for name, m in MODES.items()]
    mode_choice = _select_one("Mode:", mode_options)
    mode_name = mode_choice.split(" — ")[0]
    mode = get_mode(mode_name)

    orch_model = _select_one(
        "Orchestrator model:", ["opus", "sonnet", "gemini-pro", "gemini-flash"]
    )
    if orch_model.startswith("gemini"):
        orchestrator = "api"
    elif not has_claude():
        # claude-code orchestrator requires the claude CLI
        orchestrator = "api"
        print("  (Using API orchestrator — Claude Code CLI not found)")
    else:
        orchestrator = _select_one(
            "Orchestrator:",
            [
                "claude-code (free on Max subscription)",
                "api (pay-per-token)",
            ],
        ).split(" (")[0]

    print("\n  An exchange = one orchestrator turn: think, delegate to agent, read result.")
    exchange_presets = ["20", "30", "50"]
    default_ex = str(mode.default_max_exchanges)
    ex_default_idx = exchange_presets.index(default_ex) if default_ex in exchange_presets else 1
    max_exchanges = _select_numeric(
        "Max exchanges per cycle:", exchange_presets, default_index=ex_default_idx
    )

    print("\n  A cycle = one full orchestrator session. If it doesn't finish,")
    print("  a new cycle starts with a summary of prior progress.")
    cycle_presets = ["1", "3", "5", "10"]
    default_cy = str(mode.default_max_cycles)
    cy_default_idx = cycle_presets.index(default_cy) if default_cy in cycle_presets else 2
    max_cycles = _select_numeric("Max cycles:", cycle_presets, default_index=cy_default_idx)

    print("\n  Budget per step limits spending on each agent call.")
    print("  Only matters for API-billed sessions; ignored on subscription.")
    budget_raw = _select_numeric(
        "Budget per step (USD):", ["None", "1.00", "5.00"], type_fn=float
    )

    budget = None if budget_raw == "None" else float(budget_raw)

    return {
        "mode": mode_name,
        "orchestrator": orchestrator,
        "orchestrator_model": orch_model,
        "max_exchanges": int(max_exchanges),
        "max_cycles": int(max_cycles),
        "budget_per_step": budget,
    }


def _config_path(project_dir: Path) -> Path:
    return project_dir / ".kodo" / "last-config.json"


def _save_config(project_dir: Path, params: dict) -> None:
    path = _config_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params, indent=2))


def _load_or_select_params(project_dir: Path) -> dict:
    """Offer to reuse previous config, or run interactive selection."""
    cfg_path = _config_path(project_dir)
    if cfg_path.exists():
        try:
            prev = json.loads(cfg_path.read_text())
            mode = get_mode(prev["mode"])
            print(f"\n  Previous config found:")
            print(f"    Mode:         {mode.name} — {mode.description}")
            print(f"    Orchestrator: {prev['orchestrator']} ({prev['orchestrator_model']})")
            print(f"    Exchanges:    {prev['max_exchanges']}/cycle, {prev['max_cycles']} cycles")
            if prev.get("budget_per_step"):
                print(f"    Budget/step:  ${prev['budget_per_step']:.2f}")
            reuse = input("\n  Reuse this config? [Y/n] ").strip().lower()
            if not reuse or reuse == "y":
                return prev
        except (json.JSONDecodeError, KeyError):
            pass  # corrupt config, fall through to interactive

    params = select_params()
    _save_config(project_dir, params)
    return params


def launch_run(project_dir: Path, goal_text: str, params: dict) -> None:
    """Build team + orchestrator and run."""
    log_path = log.init(project_dir)
    log.emit("cli_args", **params, goal_text=goal_text)

    mode = get_mode(params["mode"])
    team = mode.build_team(params["budget_per_step"])
    orchestrator = build_orchestrator(
        params["orchestrator"],
        params["orchestrator_model"],
        system_prompt=mode.system_prompt,
    )

    print(f"\nMode: {mode.name} — {mode.description}")
    print(f"Orchestrator: {params['orchestrator']} ({orchestrator.model})")
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


def launch_resume(project_dir: Path, state: log.RunState) -> None:
    """Resume an interrupted run from its parsed RunState."""
    log.init_append(state.log_file)

    # Reconstruct params from RunState
    params = {
        "mode": state.mode or "saga",
        "orchestrator": "api" if state.orchestrator == "api" else "claude-code",
        "orchestrator_model": state.model,
        "max_exchanges": state.max_exchanges,
        "max_cycles": state.max_cycles,
        "budget_per_step": state.budget_per_step,
    }

    mode = get_mode(params["mode"])
    team = mode.build_team(params["budget_per_step"])
    orchestrator = build_orchestrator(
        params["orchestrator"],
        params["orchestrator_model"],
        system_prompt=mode.system_prompt,
    )

    resume = ResumeState(
        completed_cycles=state.completed_cycles,
        prior_summary=state.last_summary,
        agent_session_ids=state.agent_session_ids,
    )

    print(f"\nResuming run: {state.run_id}")
    print(f"Mode: {mode.name} — {mode.description}")
    print(f"Orchestrator: {params['orchestrator']} ({orchestrator.model})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Completed cycles: {state.completed_cycles}/{state.max_cycles}")
    if state.agent_session_ids:
        print(f"Resuming sessions: {', '.join(state.agent_session_ids.keys())}")
    print(f"Log: {state.log_file}")
    print()

    result = orchestrator.run(
        state.goal,
        Path(state.project_dir),
        team,
        max_exchanges=params["max_exchanges"],
        max_cycles=params["max_cycles"],
        resume=resume,
    )

    total_cycles = state.completed_cycles + len(result.cycles)
    print(f"\n{'=' * 50}")
    print(
        f"Done: {total_cycles} total cycle(s), {result.total_exchanges} exchanges (this session), "
        f"${result.total_cost_usd:.4f}"
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
    parser = argparse.ArgumentParser(
        description="kodo — autonomous multi-agent coding",
    )
    parser.add_argument(
        "--version", action="version", version=f"kodo {__version__}"
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const="__latest__",
        default=None,
        metavar="RUN_ID",
        help="Resume an interrupted run. No value = latest incomplete run.",
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )
    args = parser.parse_args()

    _print_banner()

    project_dir = Path(args.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_dir = project_dir.resolve()
    print(f"  Project: {project_dir}")

    # Handle --resume
    if args.resume is not None:
        if args.resume == "__latest__":
            runs = log.find_incomplete_runs(project_dir)
            if not runs:
                print("No incomplete runs found.")
                sys.exit(1)
            state = runs[0]
        else:
            log_file = project_dir / ".kodo" / "logs" / f"{args.resume}.jsonl"
            if not log_file.exists():
                print(f"Log file not found: {log_file}")
                sys.exit(1)
            state = log.parse_run(log_file)
            if state is None:
                print(f"Could not parse run from {log_file}")
                sys.exit(1)

        print(f"  Goal: {state.goal[:80]}{'...' if len(state.goal) > 80 else ''}")
        print(f"  Cycles completed: {state.completed_cycles}/{state.max_cycles}")
        confirm = input("\nResume this run? [Y/n] ").strip().lower()
        if confirm and confirm != "y":
            print("Aborted.")
            sys.exit(0)

        launch_resume(project_dir, state)
        return

    # 1. Get goal
    goal_file = next(
        (p for p in project_dir.iterdir() if p.name.lower() == "goal.md"), None
    )

    if goal_file is not None:
        goal_text = goal_file.read_text().strip()
        print(f"\nFound existing goal in {goal_file}:")
        print("-" * 40)
        print(goal_text[:500])
        if len(goal_text) > 500:
            print("...")
        print("-" * 40)
        use_existing = input("Use this goal? [Y/n] ").strip().lower()
        if use_existing and use_existing != "y":
            goal_text = get_goal()
    else:
        goal_text = get_goal()

    # 2. Intake interview (requires Claude Code CLI)
    if has_claude():
        skip = input("\nRefine goal with Claude? [Y/n] ").strip().lower()
        if not skip or skip == "y":
            goal_text = run_intake(project_dir, goal_text)
    else:
        print("\nSkipping intake interview (Claude Code CLI not found).")

    # 3. Select parameters (or reuse previous config)
    params = _load_or_select_params(project_dir)

    # 4. Confirm
    mode = get_mode(params["mode"])
    print("\n" + "=" * 60)
    print("  READY TO LAUNCH")
    print("=" * 60)
    print(f"  Project:      {project_dir}")
    print(f"  Goal:         {goal_text[:80]}{'...' if len(goal_text) > 80 else ''}")
    print(f"  Mode:         {mode.name} — {mode.description}")
    print(f"  Orchestrator: {params['orchestrator']} ({params['orchestrator_model']})")
    print(f"  Exchanges:    {params['max_exchanges']}/cycle, {params['max_cycles']} cycles")
    if params["budget_per_step"]:
        print(f"  Budget/step:  ${params['budget_per_step']:.2f}")
    print()
    print("  WARNING: Agents run with full permissions (bypass mode).")
    print("  They will create, modify, and delete files — primarily in")
    print(f"  {project_dir}")
    print("  but they CAN access any file on your system (install deps,")
    print("  edit configs, etc). Make sure you have a git commit or backup.")
    print()

    confirm = input("Proceed? [Y/n] ").strip().lower()
    if confirm and confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # 5. Launch
    launch_run(project_dir, goal_text, params)


if __name__ == "__main__":
    main()
