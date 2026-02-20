"""kodo interactive CLI — guided project setup and launch."""

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import questionary

from kodo import log, make_session, __version__
from kodo.factory import (
    MODES,
    get_mode,
    build_orchestrator,
    has_claude,
    has_cursor,
    check_api_key,
)
from kodo.orchestrators.base import GoalPlan, GoalStage, ResumeState


def _print_banner() -> None:
    print(f"\n  kodo v{__version__} — autonomous multi-agent coding")
    print("  https://github.com/ikamen/kodo\n")


_INTAKE_PREAMBLE = """\
You are a project intake interviewer helping refine a software project goal{purpose}.

The user will give you their goal as the first message. Your job:
1. Read it carefully
2. Ask 2-3 focused clarifying questions about constraints, tech choices, \
edge cases, architecture preferences, and scope
3. Have a natural conversation to fill in gaps
4. When you have enough clarity, write {output}

Start by acknowledging the goal briefly, then ask your first questions.
Keep the conversation focused and practical — don't over-interview."""

INTAKE_PROMPT = _INTAKE_PREAMBLE.format(
    purpose="",
    output="a refined, detailed goal to .kodo/goal-refined.md",
)

INTAKE_STAGES_PROMPT = (
    _INTAKE_PREAMBLE.format(
        purpose=" into an ordered list of stages",
        output="a structured goal plan to .kodo/goal-plan.json",
    )
    + """

The JSON format MUST be:
{
  "context": "Shared architectural context — tech stack, key files, conventions",
  "stages": [
    {
      "index": 1,
      "name": "Short label",
      "description": "Full prose description of what this stage accomplishes",
      "acceptance_criteria": "Verifiable definition of done for this stage",
      "browser_testing": false
    }
  ]
}

Set "browser_testing" to true ONLY for stages that build or modify a web UI \
that should be verified in a real browser. Default is false.

Guidelines for staging:
- Break non-trivial goals into 2-5 stages
- Each stage should be independently verifiable
- Order stages so later ones build on earlier ones
- Trivially simple goals can be a single stage
- Each stage should be completable in 1-3 orchestrator cycles"""
)


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


def run_intake_chat(
    backend: str,
    project_dir: Path,
    goal_text: str,
    staged: bool = False,
) -> GoalPlan | str | None:
    """Interactive intake chat using the Session abstraction.

    Returns GoalPlan if staged + file written, refined goal string if
    single + file written, or None if user bailed.
    """
    selfo_dir = project_dir / ".kodo"
    selfo_dir.mkdir(parents=True, exist_ok=True)

    goal_path = selfo_dir / "goal.md"
    goal_path.write_text(goal_text)
    print(f"\nGoal saved to {goal_path}")

    prompt = INTAKE_STAGES_PROMPT if staged else INTAKE_PROMPT
    model = "opus" if backend == "claude" else "composer-1.5"
    session = make_session(backend, model, budget=None, system_prompt=prompt)

    output_file = selfo_dir / ("goal-plan.json" if staged else "goal-refined.md")

    print("\n--- Intake interview (type /done or empty line to finish) ---\n")

    # First message
    initial = f"Here's my project goal:\n\n{goal_text}"
    result = session.query(initial, project_dir, max_turns=10)
    print(f"\n{result.text}\n")

    # Check if output was already written on first turn
    if output_file.exists():
        return _read_intake_output(output_file, staged)

    # Conversation loop
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input or user_input == "/done":
            break

        result = session.query(user_input, project_dir, max_turns=10)
        print(f"\n{result.text}\n")

        if output_file.exists():
            return _read_intake_output(output_file, staged)

    # Check one last time
    if output_file.exists():
        return _read_intake_output(output_file, staged)

    print("\nNo output file written; using original goal.")
    return None


def _read_intake_output(output_file: Path, staged: bool) -> GoalPlan | str | None:
    """Read the intake output file and return the appropriate type."""
    if staged:
        try:
            raw = json.loads(output_file.read_text())
            plan = _parse_goal_plan(raw)
            if plan.stages:
                print(f"\nGoal plan read from {output_file}")
                print(f"  {len(plan.stages)} stage(s):")
                for s in plan.stages:
                    print(f"    {s.index}. {s.name}")
                return plan
        except json.JSONDecodeError as exc:
            print(f"\nWarning: invalid JSON in {output_file}: {exc}")
        return None
    else:
        refined = output_file.read_text().strip()
        if refined:
            print(f"\nRefined goal read from {output_file}")
            return refined
        return None


def _looks_staged(goal_text: str) -> bool:
    """Heuristic: detect if goal text has numbered steps or bullet lists."""
    numbered = re.findall(r"^\s*\d+[\.\)]\s+", goal_text, re.MULTILINE)
    return len(numbered) >= 2


def _parse_goal_plan(raw: dict) -> GoalPlan:
    """Convert a raw dict (from JSON) into a GoalPlan dataclass.

    Skips stages that are missing required fields rather than crashing.
    """
    context = raw.get("context")
    if not context:
        return GoalPlan(context="", stages=[])  # malformed input, return empty
    stages = []
    for s in raw.get("stages", []):
        if not isinstance(s, dict):
            continue
        index = s.get("index")
        name = s.get("name")
        description = s.get("description")
        acceptance_criteria = s.get("acceptance_criteria")
        if not index or not name or not description or acceptance_criteria is None:
            continue
        stages.append(
            GoalStage(
                index=index,
                name=name,
                description=description,
                acceptance_criteria=acceptance_criteria,
                browser_testing=bool(s.get("browser_testing", False)),
            )
        )
    return GoalPlan(context=context, stages=stages)


def _load_goal_plan(project_dir: Path) -> GoalPlan | None:
    """Load an existing goal-plan.json if present and valid."""
    plan_path = project_dir / ".kodo" / "goal-plan.json"
    if not plan_path.exists():
        return None
    try:
        raw = json.loads(plan_path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    plan = _parse_goal_plan(raw)
    return plan if plan.stages else None


def _select_one(title: str, options: list[str], default_index: int = 0) -> str:
    """Arrow-key single selection. Returns the chosen string."""
    default = options[default_index] if default_index < len(options) else None
    result = questionary.select(title, choices=options, default=default).ask()
    if result is None:
        print("Cancelled.")
        sys.exit(1)
    return result


def _select_numeric(
    title: str, presets: list[str], default_index: int = 0, type_fn: type = int
) -> str:
    """Arrow-key selection with a 'Custom...' option for numeric values."""
    choices = presets + ["Custom..."]
    default = choices[default_index] if default_index < len(choices) else None
    result = questionary.select(title, choices=choices, default=default).ask()
    if result is None:
        print("Cancelled.")
        sys.exit(1)
    if result != "Custom...":
        return result
    while True:
        raw = questionary.text("  Enter value:").ask()
        if raw is None:
            print("Cancelled.")
            sys.exit(1)
        raw = raw.strip()
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

    # Validate API key early
    key_err = check_api_key(orchestrator, orch_model)
    if key_err:
        print(f"\n  Error: {key_err}")
        print("  Set the key in your environment or .env file and try again.")
        sys.exit(1)

    print(
        "\n  An exchange = one orchestrator turn: think, delegate to agent, read result."
    )
    exchange_presets = ["20", "30", "50"]
    default_ex = str(mode.default_max_exchanges)
    ex_default_idx = (
        exchange_presets.index(default_ex) if default_ex in exchange_presets else 1
    )
    max_exchanges = _select_numeric(
        "Max exchanges per cycle:", exchange_presets, default_index=ex_default_idx
    )

    print("\n  A cycle = one full orchestrator session. If it doesn't finish,")
    print("  a new cycle starts with a summary of prior progress.")
    cycle_presets = ["1", "3", "5", "10"]
    default_cy = str(mode.default_max_cycles)
    cy_default_idx = (
        cycle_presets.index(default_cy) if default_cy in cycle_presets else 2
    )
    max_cycles = _select_numeric(
        "Max cycles:", cycle_presets, default_index=cy_default_idx
    )

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
    required_keys = {
        "mode",
        "orchestrator",
        "orchestrator_model",
        "max_exchanges",
        "max_cycles",
    }
    if cfg_path.exists():
        try:
            prev = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            prev = None
        if isinstance(prev, dict) and required_keys <= prev.keys():
            mode = get_mode(prev["mode"])
            print("\n  Previous config found:")
            print(f"    Mode:         {mode.name} — {mode.description}")
            print(
                f"    Orchestrator: {prev['orchestrator']} ({prev['orchestrator_model']})"
            )
            print(
                f"    Exchanges:    {prev['max_exchanges']}/cycle, {prev['max_cycles']} cycles"
            )
            if prev.get("budget_per_step"):
                print(f"    Budget/step:  ${prev['budget_per_step']:.2f}")
            reuse = input("\n  Reuse this config? [Y/n] ").strip().lower()
            if not reuse or reuse == "y":
                return prev

    params = select_params()
    _save_config(project_dir, params)
    return params


def launch_run(
    project_dir: Path,
    goal_text: str,
    params: dict,
    plan: GoalPlan | None = None,
) -> None:
    """Build team + orchestrator and run."""
    log_path = log.init(project_dir)
    log.emit("cli_args", **params, goal_text=goal_text, has_plan=plan is not None)

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
    if plan:
        print(f"Stages: {len(plan.stages)}")
    print(f"Log: {log_path}")
    print()

    result = orchestrator.run(
        goal_text,
        project_dir,
        team,
        max_exchanges=params["max_exchanges"],
        max_cycles=params["max_cycles"],
        plan=plan,
    )

    print(f"\n{'=' * 50}")
    if result.stage_results:
        completed = sum(1 for sr in result.stage_results if sr.finished)
        print(
            f"Done: {completed}/{len(result.stage_results)} stage(s) completed, "
            f"{len(result.cycles)} cycle(s), {result.total_exchanges} exchanges, "
            f"${result.total_cost_usd:.4f}"
        )
    else:
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
        completed_stages=state.completed_stages,
        stage_summaries=state.stage_summaries,
        current_stage_cycles=state.current_stage_cycles,
    )

    # Load goal plan if this was a staged run
    plan: GoalPlan | None = None
    if state.has_stages:
        plan = _load_goal_plan(Path(state.project_dir))

    print(f"\nResuming run: {state.run_id}")
    print(f"Mode: {mode.name} — {mode.description}")
    print(f"Orchestrator: {params['orchestrator']} ({orchestrator.model})")
    print(f"Team: {', '.join(team.keys())}")
    print(f"Completed cycles: {state.completed_cycles}/{state.max_cycles}")
    if state.has_stages:
        print(
            f"Completed stages: {len(state.completed_stages)}"
            + (f"/{plan and len(plan.stages)}" if plan else "")
        )
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
        plan=plan,
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


def _offer_intake(project_dir: Path, goal_text: str) -> GoalPlan | str | None:
    """Offer intake interview, letting user pick backend. Returns result or None."""
    backends: list[str] = []
    if has_claude():
        backends.append("Claude")
    if has_cursor():
        backends.append("Cursor")

    if not backends:
        print("\nSkipping intake (no backends available).")
        return None

    options = backends + ["Skip"]
    choice = _select_one("\nRefine goal with:", options)
    if choice == "Skip":
        return None

    backend = "claude" if choice == "Claude" else "cursor"

    staged = False
    if _looks_staged(goal_text):
        print("This goal looks like it has multiple steps.")
        stage_choice = input("Break into stages? [Y/n] ").strip().lower()
        staged = not stage_choice or stage_choice == "y"
    else:
        stage_choice = input("Break into stages? [y/N] ").strip().lower()
        staged = stage_choice == "y"

    return run_intake_chat(backend, project_dir, goal_text, staged=staged)


def _main_inner() -> None:
    parser = argparse.ArgumentParser(
        description="kodo — autonomous multi-agent coding",
    )
    parser.add_argument("--version", action="version", version=f"kodo {__version__}")
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

    # 2. Select parameters (or reuse previous config)
    params = _load_or_select_params(project_dir)

    # 3. Intake interview (uses Session abstraction — works with any backend)
    plan: GoalPlan | None = None

    # Check for existing goal plan first
    existing_plan = _load_goal_plan(project_dir)
    if existing_plan:
        print(f"\nFound existing goal plan ({len(existing_plan.stages)} stages):")
        print("-" * 40)
        for s in existing_plan.stages:
            print(f"  {s.index}. {s.name}")
            if s.acceptance_criteria:
                print(f"     Done when: {s.acceptance_criteria[:100]}")
        print("-" * 40)
        use_plan = input("Use this goal plan? [Y/n] ").strip().lower()
        if not use_plan or use_plan == "y":
            plan = existing_plan
            # Also load the refined goal if present
            refined_path = project_dir / ".kodo" / "goal-refined.md"
            if refined_path.exists():
                goal_text = refined_path.read_text().strip() or goal_text

    if plan is None:
        refined_path = project_dir / ".kodo" / "goal-refined.md"
        if refined_path.exists():
            refined = refined_path.read_text().strip()
            if refined:
                print("\nFound refined goal from previous intake:")
                print("-" * 40)
                print(refined[:500])
                if len(refined) > 500:
                    print("...")
                print("-" * 40)
                use_refined = input("Use this refined goal? [Y/n] ").strip().lower()
                if not use_refined or use_refined == "y":
                    goal_text = refined
                else:
                    intake_result = _offer_intake(project_dir, goal_text)
                    if isinstance(intake_result, GoalPlan):
                        plan = intake_result
                    elif isinstance(intake_result, str):
                        goal_text = intake_result
        else:
            intake_result = _offer_intake(project_dir, goal_text)
            if isinstance(intake_result, GoalPlan):
                plan = intake_result
            elif isinstance(intake_result, str):
                goal_text = intake_result

    # 4. Confirm
    mode = get_mode(params["mode"])
    print("\n" + "=" * 60)
    print("  READY TO LAUNCH")
    print("=" * 60)
    print(f"  Project:      {project_dir}")
    print(f"  Goal:         {goal_text[:80]}{'...' if len(goal_text) > 80 else ''}")
    if plan:
        print(f"  Stages:       {len(plan.stages)}")
        for s in plan.stages:
            print(f"                  {s.index}. {s.name}")
    print(f"  Mode:         {mode.name} — {mode.description}")
    print(f"  Orchestrator: {params['orchestrator']} ({params['orchestrator_model']})")
    print(
        f"  Exchanges:    {params['max_exchanges']}/cycle, {params['max_cycles']} cycles"
    )
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
    launch_run(project_dir, goal_text, params, plan=plan)


if __name__ == "__main__":
    main()
