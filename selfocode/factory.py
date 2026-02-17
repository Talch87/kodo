"""Team and orchestrator construction helpers.

Centralises the duplicated team-building logic from main.py and cli.py.
"""

from __future__ import annotations


from selfocode import (
    TESTER_PROMPT,
    TESTER_BROWSER_PROMPT,
    ARCHITECT_PROMPT,
    make_session,
)
from selfocode.agent import Agent
from selfocode.orchestrators.base import TeamConfig


def build_team(
    backend: str,
    model: str,
    budget: float | None = None,
    *,
    worker_timeout_s: float | None = 1800,
    tester_timeout_s: float | None = 1800,
    architect_timeout_s: float | None = 600,
) -> TeamConfig:
    """Create the standard 4-agent team."""
    worker_session = make_session(backend, model, budget)
    tester_session = make_session(backend, model, budget, system_prompt=TESTER_PROMPT)
    tester_browser_session = make_session(
        backend,
        model,
        budget,
        system_prompt=TESTER_BROWSER_PROMPT,
        chrome=True,
    )
    architect_session = make_session(
        backend, model, budget, system_prompt=ARCHITECT_PROMPT
    )

    return {
        "worker": Agent(
            worker_session,
            "A skilled coding agent that implements features and fixes bugs.\n"
            "Give it a SHORT directive (2-5 sentences) describing the desired behavior, "
            "not the implementation. No file lists, no module structures, no code snippets "
            "— the worker is a skilled coder who makes all implementation decisions.\n"
            "Each task should be ONE feature or change that can be built and tested independently.\n"
            "If the result contains [PROPOSED PLAN], review it. If good, tell the worker: "
            '"Plan approved, proceed with implementation." If you want changes, describe them.\n'
            "If the worker seems stuck or unproductive, set new_conversation=true and give "
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
            "Use this when you want a second opinion on the codebase before calling done, "
            "or when you suspect architectural problems.\n"
            "It provides a brief actionable critique with specific file/line references. "
            "It does not make changes.",
            max_turns=10,
            timeout_s=architect_timeout_s,
        ),
    }


# Maps short names ("opus", "sonnet") to full API model IDs.
_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "gemini-pro": "gemini-3-pro-preview",
    "gemini-flash": "gemini-3-flash-preview",
}


def build_orchestrator(name: str, model: str | None = None):
    """Construct an orchestrator by name ('api' or 'claude-code').

    *model* can be a short alias ("opus") or a full model ID.
    """
    if name == "api":
        from selfocode.orchestrators.api import ApiOrchestrator

        orch_model = _MODEL_ALIASES.get(model, model) if model else "claude-opus-4-6"
        return ApiOrchestrator(model=orch_model)

    from selfocode.orchestrators.claude_code import ClaudeCodeOrchestrator

    orch_model = model or "opus"
    return ClaudeCodeOrchestrator(model=orch_model)
