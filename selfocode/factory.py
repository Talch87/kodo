"""Team and orchestrator construction helpers.

Centralises the duplicated team-building logic from main.py and cli.py.
"""

from __future__ import annotations

from pathlib import Path

from selfocode import (
    TESTER_PROMPT, TESTER_BROWSER_PROMPT, ARCHITECT_PROMPT, make_session,
)
from selfocode.agent import Agent
from selfocode.orchestrators.base import TeamConfig


def build_team(
    backend: str,
    model: str,
    budget: float | None = None,
    *,
    worker_timeout_s: float | None = 300,
    tester_timeout_s: float | None = 300,
    architect_timeout_s: float | None = 120,
) -> TeamConfig:
    """Create the standard 4-agent team."""
    worker_session = make_session(backend, model, budget)
    tester_session = make_session(backend, model, budget, system_prompt=TESTER_PROMPT)
    tester_browser_session = make_session(
        backend, model, budget, system_prompt=TESTER_BROWSER_PROMPT, chrome=True,
    )
    architect_session = make_session(backend, model, budget, system_prompt=ARCHITECT_PROMPT)

    return {
        "worker": Agent(
            worker_session,
            "A skilled coding agent that implements features and fixes bugs.",
            max_turns=30, timeout_s=worker_timeout_s,
        ),
        "tester": Agent(
            tester_session, TESTER_PROMPT, max_turns=20, timeout_s=tester_timeout_s,
        ),
        "tester_browser": Agent(
            tester_browser_session, TESTER_BROWSER_PROMPT, max_turns=20,
            timeout_s=tester_timeout_s,
        ),
        "architect": Agent(
            architect_session, ARCHITECT_PROMPT, max_turns=10,
            timeout_s=architect_timeout_s,
        ),
    }


# Maps short names ("opus", "sonnet") to full API model IDs.
_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
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
