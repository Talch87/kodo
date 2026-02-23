"""Run launcher — build team/orchestrator and execute runs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from kodo import log
from kodo.factory import (
    build_orchestrator,
    get_mode,
    has_claude,
    has_cursor,
    check_api_key,
    model_alias_for_display,
    default_fallback,
    MODES,
)
from kodo.log import RunDir
from kodo.orchestrators.base import GoalPlan, ResumeState
from kodo.team_config import load_team_config, build_team_from_json
from kodo.user_config import get_user_default
from kodo.ui import (
    backend_label,
    select_one,
    select_numeric,
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _config_path(project_dir: Path) -> Path:
    return project_dir / ".kodo" / "config.json"


def save_config(project_dir: Path, params: dict) -> None:
    path = _config_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params, indent=2))


def load_or_select_params(project_dir: Path) -> dict:
    """Offer to reuse previous config, or run interactive selection."""
    cfg_path = _config_path(project_dir)
    # Legacy fallback
    if not cfg_path.exists():
        legacy = project_dir / ".kodo" / "last-config.json"
        if legacy.exists():
            cfg_path = legacy
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
            orch_str = f"{prev['orchestrator']} ({prev['orchestrator_model']})"
            if prev.get("fallback_model"):
                orch_str += f" → fallback: {prev['fallback_model']}"
            print(f"    Orchestrator: {orch_str}")
            print(
                f"    Exchanges:    {prev['max_exchanges']}/cycle, {prev['max_cycles']} cycles"
            )
            reuse = input("\n  Reuse this config? [Y/n] ").strip().lower()
            if not reuse or reuse == "y":
                return prev

    params = select_params()
    save_config(project_dir, params)
    return params


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
    mode_choice = select_one("Mode:", mode_options)
    mode_name = mode_choice.split(" — ")[0]
    mode = get_mode(mode_name)

    orch_model = select_one(
        "Orchestrator model:", ["opus", "sonnet", "gemini-pro", "gemini-flash"]
    )
    if orch_model.startswith("gemini"):
        orchestrator = "api"
    elif not has_claude():
        # claude-code orchestrator requires the claude CLI
        orchestrator = "api"
        print("  (Using API orchestrator — Claude Code CLI not found)")
    else:
        orchestrator = select_one(
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

    # Fallback orchestrator model (for transient errors like 529/503)
    fb_model: str | None = None
    if orchestrator == "api":
        auto_fb = default_fallback(orch_model)
        fb_options = []
        if auto_fb:
            fb_options.append(f"{model_alias_for_display(auto_fb)} (auto-detected)")
        fb_options.append("none")
        # Add other models not matching primary provider
        for name_ in ["opus", "sonnet", "gemini-pro", "gemini-flash"]:
            if name_ != orch_model and f"{name_} (auto-detected)" not in fb_options:
                fb_options.append(name_)
        fb_choice = select_one("Fallback orchestrator model:", fb_options)
        if fb_choice == "none":
            fb_model = None
        else:
            fb_model = fb_choice.split(" (")[0]  # strip "(auto-detected)"

    print(
        "\n  An exchange = one orchestrator turn: think, delegate to agent, read result."
    )
    exchange_presets = ["20", "30", "50"]
    default_ex = str(mode.default_max_exchanges)
    ex_default_idx = (
        exchange_presets.index(default_ex) if default_ex in exchange_presets else 1
    )
    max_exchanges = select_numeric(
        "Max exchanges per cycle:", exchange_presets, default_index=ex_default_idx
    )

    print("\n  A cycle = one full orchestrator session. If it doesn't finish,")
    print("  a new cycle starts with a summary of prior progress.")
    cycle_presets = ["1", "3", "5", "10"]
    default_cy = str(mode.default_max_cycles)
    cy_default_idx = (
        cycle_presets.index(default_cy) if default_cy in cycle_presets else 2
    )
    max_cycles = select_numeric(
        "Max cycles:", cycle_presets, default_index=cy_default_idx
    )

    params = {
        "mode": mode_name,
        "orchestrator": orchestrator,
        "orchestrator_model": orch_model,
        "max_exchanges": int(max_exchanges),
        "max_cycles": int(max_cycles),
    }
    if fb_model:
        params["fallback_model"] = fb_model
    return params


def build_params_from_flags(args, project_dir: Path) -> dict:
    """Build config dict from CLI flags, falling back to mode defaults."""
    mode_name = args.mode or "saga"
    mode = get_mode(mode_name)

    orch_model = args.orchestrator_model or "gemini-flash"

    if args.orchestrator:
        orchestrator = args.orchestrator
    elif orch_model.startswith("gemini"):
        orchestrator = "api"
    elif not has_claude():
        orchestrator = "api"
    else:
        orchestrator = "claude-code"

    key_err = check_api_key(orchestrator, orch_model)
    if key_err:
        print(f"Error: {key_err}")
        sys.exit(1)

    fb_model = args.fallback_model if hasattr(args, "fallback_model") else None
    if fb_model is None and orchestrator == "api":
        fb_model = default_fallback(orch_model)

    # Auto-commit: on by default, disabled with --no-auto-commit or user config
    auto_commit = get_user_default("auto_commit", True)
    if getattr(args, "no_auto_commit", False):
        auto_commit = False

    params = {
        "mode": mode_name,
        "orchestrator": orchestrator,
        "orchestrator_model": orch_model,
        "max_exchanges": args.exchanges or mode.default_max_exchanges,
        "max_cycles": args.cycles or mode.default_max_cycles,
        "auto_commit": auto_commit,
    }
    if fb_model:
        params["fallback_model"] = fb_model
    save_config(project_dir, params)
    return params


# ---------------------------------------------------------------------------
# Shared launch internals
# ---------------------------------------------------------------------------


@dataclass
class _RunSetup:
    """Everything needed to execute a run, built from params + project dir."""

    team: dict
    orchestrator: object
    mode: object
    max_exchanges: int
    max_cycles: int
    verifiers: list | None = None
    team_config: dict | None = None


def _build_run_setup(
    params: dict,
    project_dir: Path,
    *,
    agent_session_ids: dict[str, str] | None = None,
) -> _RunSetup:
    """Build team + orchestrator from params.

    *agent_session_ids*: when resuming, map agent_name -> session_id to inject
    into sessions before the run. Sessions are created with resume state at build time.
    """
    mode = get_mode(params["mode"])
    verifiers = None

    team_config = load_team_config(params["mode"], project_dir)
    if team_config:
        team = build_team_from_json(team_config)
        system_prompt = team_config.get("orchestrator_prompt") or mode.system_prompt
        verifiers = team_config.get("verifiers")
        max_exchanges = team_config.get("max_exchanges", params["max_exchanges"])
        max_cycles = team_config.get("max_cycles", params["max_cycles"])
    else:
        team = mode.build_team()
        system_prompt = mode.system_prompt
        max_exchanges = params["max_exchanges"]
        max_cycles = params["max_cycles"]

    if agent_session_ids:
        for agent_name, sid in agent_session_ids.items():
            agent = team.get(agent_name)
            if agent is not None:
                agent.session.resume_session_id = sid

    orchestrator = build_orchestrator(
        params["orchestrator"],
        params["orchestrator_model"],
        system_prompt=system_prompt,
        fallback_model=params.get("fallback_model"),
    )

    return _RunSetup(
        team=team,
        orchestrator=orchestrator,
        mode=mode,
        max_exchanges=max_exchanges,
        max_cycles=max_cycles,
        verifiers=verifiers,
        team_config=team_config,
    )


def _print_run_header(setup: _RunSetup, params: dict) -> None:
    """Print run configuration summary (mode, orchestrator, team)."""
    print(f"\nMode: {setup.mode.name} — {setup.mode.description}")
    if setup.team_config:
        team_name = setup.team_config.get("name", "custom")
        print(f"Team config: {team_name}")
    orch_label = f"{params['orchestrator']} ({setup.orchestrator.model})"
    if getattr(setup.orchestrator, "_fallback_model", None):
        orch_label += f" → fallback: {setup.orchestrator._fallback_model}"
    print(f"Orchestrator: {orch_label}")
    print("Team:")
    for k, a in setup.team.items():
        print(f"  {k} ({backend_label(a)} / {a.session.model})")


# ---------------------------------------------------------------------------
# Launch functions
# ---------------------------------------------------------------------------


def launch_run(
    run_dir: RunDir,
    goal_text: str,
    params: dict,
    plan: GoalPlan | None = None,
    json_mode: bool = False,
):
    """Build team + orchestrator and run. Returns the RunResult."""
    # Snapshot config and goal into the run directory
    run_dir.config_file.write_text(json.dumps(params, indent=2))
    if not run_dir.goal_file.exists():
        run_dir.goal_file.write_text(goal_text)

    log_path = log.init(run_dir)
    log.emit("cli_args", **params, goal_text=goal_text, has_plan=plan is not None)

    project_dir = run_dir.project_dir
    s = _build_run_setup(params, project_dir)

    if not json_mode:
        _print_run_header(s, params)
        print(f"Project dir: {project_dir}")
        if plan:
            print(f"Stages: {len(plan.stages)}")
        print(f"Max: {s.max_exchanges} exchanges/cycle, {s.max_cycles} cycles")
        print(f"Log: {log_path}")
        print()

    result = s.orchestrator.run(
        goal_text,
        project_dir,
        s.team,
        max_exchanges=s.max_exchanges,
        max_cycles=s.max_cycles,
        plan=plan,
        verifiers=s.verifiers,
        auto_commit=params.get("auto_commit", True),
    )

    if not json_mode:
        _print_result_summary(result)

    return result


def launch_resume(run_dir: RunDir, state: log.RunState):
    """Resume an interrupted run from its parsed RunState. Returns the RunResult."""
    log.init_append(state.log_file)

    project_dir = run_dir.project_dir

    # Reconstruct params from RunState
    params = {
        "mode": state.mode or "saga",
        "orchestrator": "api" if state.orchestrator == "api" else "claude-code",
        "orchestrator_model": state.model,
        "max_exchanges": state.max_exchanges,
        "max_cycles": state.max_cycles,
    }

    # Read fallback_model from saved config if available
    if run_dir.config_file.exists():
        try:
            saved = json.loads(run_dir.config_file.read_text())
            if saved.get("fallback_model"):
                params["fallback_model"] = saved["fallback_model"]
        except json.JSONDecodeError:
            pass

    s = _build_run_setup(params, project_dir, agent_session_ids=state.agent_session_ids)

    resume = ResumeState(
        completed_cycles=state.completed_cycles,
        prior_summary=state.last_summary,
        agent_session_ids=state.agent_session_ids,
        completed_stages=state.completed_stages,
        stage_summaries=state.stage_summaries,
        current_stage_cycles=state.current_stage_cycles,
        pending_exchanges=state.pending_exchanges,
    )

    # Load goal plan if this was a staged run
    from kodo.intake import load_goal_plan

    plan: GoalPlan | None = None
    if state.has_stages:
        plan = load_goal_plan(run_dir)

    print(f"\nResuming run: {state.run_id}")
    _print_run_header(s, params)
    print(f"Completed cycles: {state.completed_cycles}/{state.max_cycles}")
    if state.has_stages:
        print(
            f"Completed stages: {len(state.completed_stages)}"
            + (f"/{plan and len(plan.stages)}" if plan else "")
        )
    if state.agent_session_ids:
        print(f"Resuming sessions: {', '.join(state.agent_session_ids.keys())}")
    if state.pending_exchanges:
        print(
            f"Resuming mid-cycle: {len(state.pending_exchanges)} exchange(s) to restore"
        )
    print(f"Log: {state.log_file}")
    print()

    result = s.orchestrator.run(
        state.goal,
        Path(state.project_dir),
        s.team,
        max_exchanges=params["max_exchanges"],
        max_cycles=params["max_cycles"],
        resume=resume,
        plan=plan,
        verifiers=s.verifiers,
        auto_commit=params.get("auto_commit", True),
    )

    total_cycles = state.completed_cycles + len(result.cycles)
    print(f"\n{'=' * 50}")
    print(
        f"Done: {total_cycles} total cycle(s), {result.total_exchanges} exchanges (this session), "
        f"${result.total_cost_usd:.4f}"
    )
    if result.summary:
        print(f"  {result.summary[:300]}")

    return result


def _print_result_summary(result) -> None:
    """Print completion summary after a run."""
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


# ---------------------------------------------------------------------------
# JSON output helpers
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_PARTIAL = 2

# The real stdout, saved before --json redirects sys.stdout to stderr.
_original_stdout = None


def set_json_mode(stdout) -> None:
    """Save the real stdout for JSON output. Call before redirecting sys.stdout."""
    global _original_stdout
    _original_stdout = stdout


def fail(msg: str, code: int = 1) -> None:
    """Print error and exit. In JSON mode, outputs JSON to original stdout."""
    if _original_stdout is not None:
        sys.stdout = _original_stdout
        print(json.dumps(format_json_output(error=msg)))
        sys.exit(EXIT_ERROR)
    print(f"Error: {msg}")
    sys.exit(code)


def emit_json_and_exit(args, result) -> None:
    """If --json, emit result JSON to stdout and exit. Otherwise no-op."""
    if not args.json:
        return
    sys.stdout = _original_stdout
    print(json.dumps(format_json_output(result), indent=2))
    sys.exit(EXIT_SUCCESS if result.finished else EXIT_PARTIAL)


def format_json_output(result=None, error: str | None = None) -> dict:
    """Build the structured JSON output dict."""
    if error is not None:
        return {"status": "error", "error": error}

    if result.finished:
        status = "completed"
    elif result.cycles:
        status = "partial"
    else:
        status = "failed"

    output = {
        "status": status,
        "finished": result.finished,
        "cycles": len(result.cycles),
        "exchanges": result.total_exchanges,
        "cost_usd": round(result.total_cost_usd, 4),
        "summary": result.summary,
    }

    if result.stage_results:
        output["stages"] = [
            {
                "index": sr.stage_index,
                "name": sr.stage_name,
                "finished": sr.finished,
                "summary": sr.summary,
                "cycles": len(sr.cycles),
            }
            for sr in result.stage_results
        ]

    return output
