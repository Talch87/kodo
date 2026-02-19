"""Team and orchestrator construction helpers.

Centralises the duplicated team-building logic from main.py and cli.py.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from kodo import (
    TESTER_PROMPT,
    TESTER_BROWSER_PROMPT,
    ARCHITECT_PROMPT,
    make_session,
)
from kodo.agent import Agent
from kodo.orchestrators.base import ORCHESTRATOR_SYSTEM_PROMPT, TeamConfig


# ---------------------------------------------------------------------------
# Backend availability detection
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def available_backends() -> dict[str, bool]:
    """Detect which worker backends are installed and on PATH."""
    return {
        "claude": shutil.which("claude") is not None,
        "cursor": shutil.which("cursor-agent") is not None,
    }


def has_claude() -> bool:
    return available_backends()["claude"]


def has_cursor() -> bool:
    return available_backends()["cursor"]


def check_api_key(orchestrator: str, model: str) -> str | None:
    """Return an error message if the required API key is missing, else None."""
    import os

    if orchestrator == "claude-code":
        return None

    _GEMINI_ALIASES = {
        "gemini-pro", "gemini-flash",
        "gemini-3-pro-preview", "gemini-3-flash-preview",
    }
    if model in _GEMINI_ALIASES or model.startswith("gemini"):
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
            return "GEMINI_API_KEY (or GOOGLE_API_KEY) not set — required for Gemini models"
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY not set — required for API orchestrator with Claude models"
    return None


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------


@dataclass
class Mode:
    """Bundles a team composition, orchestrator prompt, and default params."""

    name: str
    description: str
    system_prompt: str
    build_team: Callable[[float | None], TeamConfig]
    default_max_exchanges: int
    default_max_cycles: int


# ---------------------------------------------------------------------------
# Team builders
# ---------------------------------------------------------------------------


def _build_team_saga(
    budget: float | None = None,
    *,
    worker_timeout_s: float | None = 1800,
    tester_timeout_s: float | None = 1800,
    architect_timeout_s: float | None = 600,
) -> TeamConfig:
    """Create the saga team, skipping workers whose backends are unavailable."""
    _has_cursor = has_cursor()
    _has_claude = has_claude()
    if not _has_cursor and not _has_claude:
        raise RuntimeError(
            "No worker backends available. Install at least one of: "
            "claude (Claude Code CLI) or cursor-agent (Cursor CLI)."
        )

    team: TeamConfig = {}

    if _has_cursor:
        worker_fast_session = make_session("cursor", "composer-1.5", budget)
        team["worker_fast"] = Agent(
            worker_fast_session,
            "A fast coding agent (Cursor) for straightforward implementation tasks.\n"
            "Best for: writing new code, simple refactors, adding features with clear specs, "
            "file edits, and any task where speed matters more than deep reasoning.\n"
            "It can read and navigate existing codebases, run tests, and execute git commands "
            "on your behalf (commit, revert, branch, etc.).\n"
            "Give it a SHORT directive (2-5 sentences) describing the desired behavior, "
            "not the implementation — it is a skilled coder.\n"
            "Each task should be ONE feature or change that can be built and tested independently.\n"
            "If it seems stuck or unproductive, set new_conversation=true and give "
            "a clear, fresh directive. Don't repeat a failing directive more than twice.\n"
            "If the result contains [Context was reset: ...], give enough context in your "
            "next directive for the worker to continue effectively.",
            max_turns=30,
            timeout_s=worker_timeout_s,
        )

        tester_session = make_session(
            "cursor", "composer-1.5", budget, system_prompt=TESTER_PROMPT
        )
        team["tester"] = Agent(
            tester_session,
            "A testing agent that verifies features work end-to-end.\n"
            "After 1-2 worker steps, ask the tester to verify with a user-experience "
            'description (e.g. "a user should be able to...").\n'
            "Fix any issues the tester finds before moving on to the next feature.\n"
            "The tester runs the app, checks output, and reports what works and what's broken. "
            "It does not fix anything.",
            max_turns=20,
            timeout_s=tester_timeout_s,
        )

        tester_browser_session = make_session(
            "cursor",
            "composer-1.5",
            budget,
            system_prompt=TESTER_BROWSER_PROMPT,
            chrome=True,
        )
        team["tester_browser"] = Agent(
            tester_browser_session,
            "A testing agent with browser access for web applications.\n"
            "Use this instead of the regular tester when the project has a web UI. "
            "It opens the app in a real browser, interacts with it, and takes screenshots.\n"
            "Give it a user-experience description to verify. It reports issues but does not "
            "fix anything.",
            max_turns=20,
            timeout_s=tester_timeout_s,
        )

    if _has_claude:
        worker_smart_session = make_session(
            "claude", "opus", None, fallback_model="sonnet"
        )
        team["worker_smart"] = Agent(
            worker_smart_session,
            "A powerful reasoning agent (Claude Code) for complex tasks requiring deep thinking.\n"
            "Best for: debugging tricky issues, architectural decisions, complex refactors, "
            "tasks requiring understanding of large codebases, and anything where the fast "
            "worker struggled.\n"
            "It can read and navigate existing codebases, run tests, and execute git commands "
            "on your behalf (commit, revert, branch, etc.).\n"
            "Give it a SHORT directive (2-5 sentences) describing the desired behavior, "
            "not the implementation — it is a skilled coder.\n"
            "Each task should be ONE feature or change that can be built and tested independently.\n"
            "If the result contains [PROPOSED PLAN], review it. If good, tell the worker: "
            '"Plan approved, proceed with implementation." If you want changes, describe them.\n'
            "If it seems stuck or unproductive, set new_conversation=true and give "
            "a clear, fresh directive. Don't repeat a failing directive more than twice.\n"
            "If the result contains [Context was reset: ...], give enough context in your "
            "next directive for the worker to continue effectively.",
            max_turns=30,
            timeout_s=worker_timeout_s,
        )

        architect_session = make_session(
            "claude",
            "opus",
            None,
            system_prompt=ARCHITECT_PROMPT,
            fallback_model="sonnet",
        )
        team["architect"] = Agent(
            architect_session,
            "A code reviewer that reads the codebase and identifies bugs and structural issues.\n"
            "Use this to survey an existing codebase before planning work, to get a second "
            "opinion before calling done, or when you suspect architectural problems.\n"
            "It provides a brief actionable critique with specific file/line references. "
            "It does not make changes.",
            max_turns=10,
            timeout_s=architect_timeout_s,
        )

    return team


def _build_team_mission(budget: float | None = None) -> TeamConfig:
    """Create a mission team, skipping workers whose backends are unavailable."""
    _has_cursor = has_cursor()
    _has_claude = has_claude()
    if not _has_cursor and not _has_claude:
        raise RuntimeError(
            "No worker backends available. Install at least one of: "
            "claude (Claude Code CLI) or cursor-agent (Cursor CLI)."
        )

    team: TeamConfig = {}

    if _has_cursor:
        worker_fast_session = make_session("cursor", "composer-1.5", budget)
        team["worker_fast"] = Agent(
            worker_fast_session,
            "A fast coding agent (Cursor) for straightforward implementation tasks.\n"
            "Best for: writing new code, simple refactors, adding features with clear specs, "
            "file edits, and any task where speed matters more than deep reasoning.\n"
            "It can read and navigate existing codebases, run tests, and execute git commands "
            "on your behalf (commit, revert, branch, etc.).\n"
            "Give it a SHORT directive (2-5 sentences) describing the desired behavior, "
            "not the implementation — it is a skilled coder.\n"
            "If it seems stuck or unproductive, set new_conversation=true and give "
            "a clear, fresh directive. Don't repeat a failing directive more than twice.\n"
            "If the result contains [Context was reset: ...], give enough context in your "
            "next directive for the worker to continue effectively.",
            max_turns=30,
            timeout_s=1800,
        )

    if _has_claude:
        worker_smart_session = make_session(
            "claude",
            "opus",
            None,
            fallback_model="sonnet",
        )
        team["worker_smart"] = Agent(
            worker_smart_session,
            "A powerful reasoning agent (Claude Code) for complex tasks requiring deep thinking.\n"
            "Best for: debugging tricky issues, architectural decisions, complex refactors, "
            "tasks requiring understanding of large codebases, and anything where the fast "
            "worker struggled.\n"
            "It can read and navigate existing codebases, run tests, and execute git commands "
            "on your behalf (commit, revert, branch, etc.).\n"
            "Give it a SHORT directive (2-5 sentences) describing the desired behavior, "
            "not the implementation — it is a skilled coder.\n"
            "If it seems stuck or unproductive, set new_conversation=true and give "
            "a clear, fresh directive. Don't repeat a failing directive more than twice.\n"
            "If the result contains [Context was reset: ...], give enough context in your "
            "next directive for the worker to continue effectively.",
            max_turns=30,
            timeout_s=1800,
        )

    return team


# ---------------------------------------------------------------------------
# Mission orchestrator prompt
# ---------------------------------------------------------------------------


def _mission_system_prompt() -> str:
    """Build the mission system prompt based on available backends."""
    _has_cursor = has_cursor()
    _has_claude = has_claude()

    if _has_cursor and _has_claude:
        workers_desc = (
            "You have a fast worker (Cursor) and a smart worker "
            "(Claude Code). Use the fast worker for straightforward tasks and the smart "
            "worker for complex reasoning or when the fast worker struggles."
        )
    elif _has_cursor:
        workers_desc = "You have a fast worker (Cursor). Use it for all coding tasks."
    else:
        workers_desc = (
            "You have a smart worker (Claude Code). Use it for all coding tasks."
        )

    return f"""\
You are an orchestrator guiding AI workers to solve one focused issue
in an existing codebase. {workers_desc}

Your job:
1. Give a worker a clear, focused directive based on the goal.
2. If the worker gets stuck or goes in the wrong direction — unblock it:
   clarify intent, suggest an approach, or narrow the scope.
3. When the worker says it's done, critically review:
   - Does it actually solve the stated goal?
   - Is the code clean and correct?
   - Did anything break?
4. If quality isn't there, send the worker back with specific feedback.
5. Call done only when the issue is genuinely solved.

Keep directives short (2-5 sentences). Don't micromanage implementation.
The workers are skilled coders — focus on WHAT and WHY, not HOW."""


# ---------------------------------------------------------------------------
# Mode registry
# ---------------------------------------------------------------------------


def _describe_backends() -> str:
    """Human-readable summary of available backends for mode descriptions."""
    parts = []
    if has_cursor():
        parts.append("Cursor")
    if has_claude():
        parts.append("Claude Code")
    return " + ".join(parts) if parts else "none"


def _saga_description() -> str:
    agents = []
    if has_cursor():
        agents.append("fast worker")
    if has_claude():
        agents.append("smart worker")
    if has_cursor():
        agents.append("tester")
        agents.append("browser tester")
    if has_claude():
        agents.append("architect")
    return f"Full team ({_describe_backends()}): {', '.join(agents)}"


def _mission_description() -> str:
    workers = []
    if has_cursor():
        workers.append("fast")
    if has_claude():
        workers.append("smart")
    label = " + ".join(workers) if workers else "no"
    return f"{label.title()} worker(s) ({_describe_backends()}) solving one issue, orchestrator as quality gate"


def get_modes() -> dict[str, Mode]:
    """Build the mode registry based on available backends."""
    return {
        "saga": Mode(
            name="saga",
            description=_saga_description(),
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            build_team=_build_team_saga,
            default_max_exchanges=30,
            default_max_cycles=5,
        ),
        "mission": Mode(
            name="mission",
            description=_mission_description(),
            system_prompt=_mission_system_prompt(),
            build_team=_build_team_mission,
            default_max_exchanges=20,
            default_max_cycles=1,
        ),
    }


# Keep MODES as a lazy accessor for backward compat
MODES = get_modes()


def get_mode(name: str) -> Mode:
    """Look up a mode by name. Raises KeyError if not found."""
    return MODES[name]


# ---------------------------------------------------------------------------
# Orchestrator construction
# ---------------------------------------------------------------------------

# Maps short names ("opus", "sonnet") to full API model IDs.
_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "gemini-pro": "gemini-3-pro-preview",
    "gemini-flash": "gemini-3-flash-preview",
}


def build_orchestrator(
    name: str,
    model: str | None = None,
    system_prompt: str | None = None,
    fallback_model: str | None = None,
):
    """Construct an orchestrator by name ('api' or 'claude-code').

    *model* can be a short alias ("opus") or a full model ID.
    *system_prompt* is forwarded to the orchestrator; defaults to the base prompt.
    *fallback_model* is used when the primary model returns 529.
    """
    if name == "api":
        from kodo.orchestrators.api import ApiOrchestrator

        orch_model = _MODEL_ALIASES.get(model, model) if model else "claude-opus-4-6"
        fb_model = (
            _MODEL_ALIASES.get(fallback_model, fallback_model)
            if fallback_model
            else None
        )
        return ApiOrchestrator(
            model=orch_model,
            system_prompt=system_prompt,
            fallback_model=fb_model,
        )

    from kodo.orchestrators.claude_code import ClaudeCodeOrchestrator

    orch_model = model or "opus"
    return ClaudeCodeOrchestrator(model=orch_model, system_prompt=system_prompt)
