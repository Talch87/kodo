"""Goal intake — interactive interview, non-interactive planning, auto-refinement."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from kodo import log, make_session
from kodo.log import RunDir
from kodo.orchestrators.base import GoalPlan, GoalStage
from kodo.ui import (
    DIM,
    GREEN,
    BOLD,
    RESET,
    Spinner,
    print_agent,
    print_separator,
    select_one,
)
from kodo.factory import has_claude, has_cursor


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_INTAKE_PREAMBLE = """\
You are refining a software project goal{purpose}.

Ask 2-3 clarifying questions about constraints, tech choices, and scope.
When clear enough, write {output}."""

_INTAKE_STAGES_SUFFIX = """

JSON format:
{{
  "context": "Shared context — tech stack, key files, conventions",
  "stages": [
    {{
      "index": 1,
      "name": "Short label",
      "description": "What this stage accomplishes",
      "acceptance_criteria": "Verifiable definition of done",
      "browser_testing": false
    }}
  ]
}}

Set browser_testing=true only for stages with web UI to verify in a browser.
Break into 2-5 independently verifiable stages, ordered by dependency."""

_AUTO_REFINE_PROMPT = """\
Review this goal before implementation:

{goal}

Concisely answer (2-3 sentences each):
1. **Implicit constraints** — what does this goal imply that isn't stated?
2. **Simplest architecture** — one specific approach, not options.
3. **Common traps** — most likely over-engineering mistake?

Then write a refined goal to {output_path} incorporating the original intent \
plus implicit constraints. Keep it concise — an autonomous agent will read it.
"""


def _build_intake_prompt(output_path: str, staged: bool) -> str:
    """Build intake prompt with the correct output file path."""
    if staged:
        prompt = _INTAKE_PREAMBLE.format(
            purpose=" into an ordered list of stages",
            output=f"a structured goal plan to {output_path}",
        )
        return prompt + _INTAKE_STAGES_SUFFIX
    else:
        return _INTAKE_PREAMBLE.format(
            purpose="",
            output=f"a refined, detailed goal to {output_path}",
        )


# ---------------------------------------------------------------------------
# Goal text collection
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


# ---------------------------------------------------------------------------
# Goal plan parsing
# ---------------------------------------------------------------------------


def looks_staged(goal_text: str) -> bool:
    """Heuristic: detect if goal text has numbered steps or bullet lists."""
    numbered = re.findall(r"^\s*\d+[\.\)]\s+", goal_text, re.MULTILINE)
    return len(numbered) >= 2


def parse_goal_plan(raw: dict) -> GoalPlan:
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


def load_goal_plan(run_dir: RunDir) -> GoalPlan | None:
    """Load an existing goal-plan.json from the run directory."""
    plan_path = run_dir.goal_plan_file
    if not plan_path.exists():
        return None
    try:
        raw = json.loads(plan_path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    plan = parse_goal_plan(raw)
    return plan if plan.stages else None


# ---------------------------------------------------------------------------
# Intake output reading
# ---------------------------------------------------------------------------


def _read_intake_output(output_file: Path, staged: bool) -> GoalPlan | str | None:
    """Read the intake output file and return the appropriate type."""
    if staged:
        try:
            raw = json.loads(output_file.read_text())
            plan = parse_goal_plan(raw)
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


# ---------------------------------------------------------------------------
# Interactive intake
# ---------------------------------------------------------------------------


def run_intake_chat(
    backend: str,
    run_dir: RunDir,
    goal_text: str,
    staged: bool = False,
) -> GoalPlan | str | None:
    """Interactive intake chat using the Session abstraction.

    Returns GoalPlan if staged + file written, refined goal string if
    single + file written, or None if user bailed.
    """
    run_dir.root.mkdir(parents=True, exist_ok=True)
    log.init(run_dir)

    goal_path = run_dir.goal_file
    goal_path.write_text(goal_text)
    print(f"\nGoal saved to {goal_path}")

    output_file = run_dir.goal_plan_file if staged else run_dir.goal_refined_file
    prompt = _build_intake_prompt(str(output_file), staged)
    model = "opus" if backend == "claude" else "composer-1.5"
    session = make_session(backend, model, system_prompt=prompt)

    print(f"\n  {DIM}Intake interview — empty line to stop and ask follow-ups{RESET}")
    print_separator()

    # First message — agent explores the project and asks clarifying questions
    project_dir = run_dir.project_dir
    initial = f"Here's my project goal:\n\n{goal_text}"
    with Spinner("Reviewing project"):
        result = session.query(initial, project_dir, max_turns=10)
    log.emit(
        "intake_response",
        text=result.text,
        is_error=result.is_error,
        turns=result.turns,
    )
    print_agent(result.text, turns=result.turns)

    # Auto-exit if the agent already wrote the output file
    if output_file.exists():
        print_separator()
        return _read_intake_output(output_file, staged)

    _EXIT_COMMANDS = {"", "/done", "/exit", "/quit"}

    while True:
        try:
            user_input = input(f"  {GREEN}{BOLD}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input in _EXIT_COMMANDS:
            break

        if user_input.startswith("/"):
            print(f"  {DIM}Unknown command: {user_input}{RESET}")
            continue

        with Spinner("Thinking"):
            result = session.query(user_input, project_dir, max_turns=10)
        log.emit(
            "intake_response",
            text=result.text,
            is_error=result.is_error,
            turns=result.turns,
        )
        print_agent(result.text, turns=result.turns)

        # Auto-exit once the agent writes the output file
        if output_file.exists():
            break

    print_separator()

    if output_file.exists():
        return _read_intake_output(output_file, staged)

    # Agent hasn't written the file yet — ask it to finalize
    with Spinner("Finalizing"):
        result = session.query(
            "The user has ended the interview. Based on everything discussed, "
            "please write the output file now.",
            project_dir,
            max_turns=10,
        )
    print_agent(result.text, turns=result.turns)

    if output_file.exists():
        return _read_intake_output(output_file, staged)

    print("\nNo output file written; using original goal.")
    return None


# ---------------------------------------------------------------------------
# Non-interactive intake
# ---------------------------------------------------------------------------


def run_intake_noninteractive(
    run_dir: RunDir,
    goal_text: str,
) -> GoalPlan | None:
    """Non-interactive intake: send goal, get staged plan back, no conversation."""
    run_dir.root.mkdir(parents=True, exist_ok=True)

    goal_path = run_dir.goal_file
    goal_path.write_text(goal_text)

    if has_claude():
        backend, model = "claude", "opus"
    elif has_cursor():
        backend, model = "cursor", "composer-1.5"
    else:
        print("Skipping intake (no backends available).")
        return None

    output_file = run_dir.goal_plan_file
    prompt = _build_intake_prompt(str(output_file), staged=True) + (
        "\n\nIMPORTANT: This is a non-interactive session. "
        "Do NOT ask clarifying questions. Analyze the project and goal, "
        "make reasonable assumptions, and write the goal-plan.json file immediately."
    )
    session = make_session(backend, model, system_prompt=prompt)

    project_dir = run_dir.project_dir
    initial = f"Here's my project goal:\n\n{goal_text}"
    print("Running intake (non-interactive)...")
    with Spinner("Analyzing project and creating plan"):
        result = session.query(initial, project_dir, max_turns=10)
    print(f"\n{result.text}\n")

    if not output_file.exists():
        with Spinner("Finalizing plan"):
            result = session.query(
                "Please write the goal-plan.json file now based on your analysis.",
                project_dir,
                max_turns=10,
            )
        print(f"\n{result.text}\n")

    if output_file.exists():
        return _read_intake_output(output_file, staged=True)

    print("Warning: intake did not produce a plan. Proceeding without stages.")
    return None


# ---------------------------------------------------------------------------
# Auto-refine (no human in the loop)
# ---------------------------------------------------------------------------


def run_intake_auto(
    backend: str,
    run_dir: RunDir,
    goal_text: str,
) -> str | None:
    """Automated goal refinement — no human in the loop.

    Uses the same session as interactive intake but sends a single structured
    prompt instead of a conversation. Returns the refined goal string, or None
    if refinement failed.
    """
    run_dir.root.mkdir(parents=True, exist_ok=True)

    goal_path = run_dir.goal_file
    goal_path.write_text(goal_text)

    output_file = run_dir.goal_refined_file
    prompt = _AUTO_REFINE_PROMPT.format(goal=goal_text, output_path=str(output_file))
    model = "opus" if backend == "claude" else "composer-1.5"
    session = make_session(backend, model, system_prompt=prompt)

    project_dir = run_dir.project_dir
    print("\n--- Auto-refining goal (no human input) ---")

    with Spinner("Analyzing goal"):
        result = session.query(
            f"Here's the project goal to analyze:\n\n{goal_text}",
            project_dir,
            max_turns=10,
        )

    print(f"\n{result.text}\n")

    if output_file.exists():
        refined = output_file.read_text().strip()
        if refined:
            print(f"Refined goal written to {output_file}")
            return refined

    # LLM didn't write the file — use its response as the refinement
    analysis = (result.text or "").strip()
    if analysis:
        refined = f"{goal_text}\n\n# Pre-implementation analysis\n\n{analysis}"
        output_file.write_text(refined)
        print(f"Refined goal written to {output_file}")
        return refined

    print("Auto-refinement produced no output; using original goal.")
    return None


# ---------------------------------------------------------------------------
# Offer intake (interactive choice)
# ---------------------------------------------------------------------------


def offer_intake(run_dir: RunDir, goal_text: str) -> GoalPlan | str | None:
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
    choice = select_one("\nRefine goal with:", options)
    if choice == "Skip":
        return None

    backend = "claude" if choice == "Claude" else "cursor"

    staged = False
    if looks_staged(goal_text):
        print("This goal looks like it has multiple steps.")
        stage_choice = input("Break into stages? [Y/n] ").strip().lower()
        staged = not stage_choice or stage_choice == "y"
    else:
        stage_choice = input("Break into stages? [y/N] ").strip().lower()
        staged = stage_choice == "y"

    return run_intake_chat(backend, run_dir, goal_text, staged=staged)
