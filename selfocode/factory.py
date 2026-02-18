"""Team and orchestrator construction helpers.

Centralises the duplicated team-building logic from main.py and cli.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from selfocode import (
    TESTER_PROMPT,
    TESTER_BROWSER_PROMPT,
    ARCHITECT_PROMPT,
    make_session,
)
from selfocode.agent import Agent
from selfocode.orchestrators.base import ORCHESTRATOR_SYSTEM_PROMPT, TeamConfig


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
    """Create the standard team with two workers (fast + smart) and support agents."""
    worker_fast_session = make_session("cursor", "composer-1.5", budget)
    worker_smart_session = make_session(
        "claude", "opus", None, fallback_model="sonnet"
    )
    tester_session = make_session(
        "cursor", "composer-1.5", budget, system_prompt=TESTER_PROMPT
    )
    tester_browser_session = make_session(
        "cursor",
        "composer-1.5",
        budget,
        system_prompt=TESTER_BROWSER_PROMPT,
        chrome=True,
    )
    architect_session = make_session(
        "claude", "opus", None,
        system_prompt=ARCHITECT_PROMPT, fallback_model="sonnet",
    )

    return {
        "worker_fast": Agent(
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
        ),
        "worker_smart": Agent(
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
        ),
        "tester": Agent(
            tester_session,
            "A testing agent that verifies features work end-to-end.\n"
            "After 1-2 worker steps, ask the tester to verify with a user-experience "
            'description (e.g. "a user should be able to...").\n'
            "Fix any issues the tester finds before moving on to the next feature.\n"
            "The tester runs the app, checks output, and reports what works and what's broken. "
            "It does not fix anything.",
            max_turns=20,
            timeout_s=tester_timeout_s,
        ),
        "tester_browser": Agent(
            tester_browser_session,
            "A testing agent with browser access for web applications.\n"
            "Use this instead of the regular tester when the project has a web UI. "
            "It opens the app in a real browser, interacts with it, and takes screenshots.\n"
            "Give it a user-experience description to verify. It reports issues but does not "
            "fix anything.",
            max_turns=20,
            timeout_s=tester_timeout_s,
        ),
        "architect": Agent(
            architect_session,
            "A code reviewer that reads the codebase and identifies bugs and structural issues.\n"
            "Use this to survey an existing codebase before planning work, to get a second "
            "opinion before calling done, or when you suspect architectural problems.\n"
            "It provides a brief actionable critique with specific file/line references. "
            "It does not make changes.",
            max_turns=10,
            timeout_s=architect_timeout_s,
        ),
    }


def _build_team_mission(budget: float | None = None) -> TeamConfig:
    """Create a two-worker team (fast + smart) for the mission mode."""
    worker_fast_session = make_session("cursor", "composer-1.5", budget)
    worker_smart_session = make_session(
        "claude", "opus", None, fallback_model="sonnet",
    )
    return {
        "worker_fast": Agent(
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
        ),
        "worker_smart": Agent(
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
        ),
    }


# ---------------------------------------------------------------------------
# Mission orchestrator prompt
# ---------------------------------------------------------------------------

MISSION_SYSTEM_PROMPT = """\
You are an orchestrator guiding AI workers to solve one focused issue
in an existing codebase. You have a fast worker (Cursor) and a smart worker
(Claude Code). Use the fast worker for straightforward tasks and the smart
worker for complex reasoning or when the fast worker struggles.

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

MODES: dict[str, Mode] = {
    "saga": Mode(
        name="saga",
        description="Full team: two workers (fast + smart), tester, browser tester, architect",
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        build_team=_build_team_saga,
        default_max_exchanges=30,
        default_max_cycles=5,
    ),
    "mission": Mode(
        name="mission",
        description="Two workers (fast + smart) solving one issue, orchestrator as quality gate",
        system_prompt=MISSION_SYSTEM_PROMPT,
        build_team=_build_team_mission,
        default_max_exchanges=20,
        default_max_cycles=1,
    ),
}


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
        from selfocode.orchestrators.api import ApiOrchestrator

        orch_model = _MODEL_ALIASES.get(model, model) if model else "claude-opus-4-6"
        fb_model = (
            _MODEL_ALIASES.get(fallback_model, fallback_model) if fallback_model else None
        )
        return ApiOrchestrator(
            model=orch_model, system_prompt=system_prompt, fallback_model=fb_model,
        )

    from selfocode.orchestrators.claude_code import ClaudeCodeOrchestrator

    orch_model = model or "opus"
    return ClaudeCodeOrchestrator(model=orch_model, system_prompt=system_prompt)
