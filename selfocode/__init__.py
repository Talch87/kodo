"""selfocode — autonomous goal-driven coding agent."""

__version__ = "0.4.0"

from selfocode import log
from selfocode.agent import Agent, AgentResult
from selfocode.sessions.base import QueryResult, Session, SessionStats
from selfocode.orchestrators.base import (
    CycleResult,
    Orchestrator,
    RunResult,
    TeamConfig,
)

# ---------------------------------------------------------------------------
# Shared agent prompts — imported by main.py and cli.py
# ---------------------------------------------------------------------------

TESTER_PROMPT = """\
You are a tester agent. You receive a description of the desired user experience \
and verify it works end-to-end. Figure out yourself how to test — run the app, \
call APIs, check files exist, verify imports, run scripts. Report what works \
and what's broken with specific error messages. Don't fix anything — just report."""

TESTER_BROWSER_PROMPT = """\
You are a tester agent with browser access. You receive a description of the \
desired user experience and verify it works by opening the app in a real browser. \
Navigate the UI, click buttons, fill forms, check that pages render correctly. \
Report what works and what's broken with specific error messages and screenshots \
if helpful. Don't fix anything — just report."""

ARCHITECT_PROMPT = """\
You are a code reviewer. Read the codebase, identify bugs and structural issues, \
and provide a brief actionable critique with specific file/line references."""


def make_session(
    backend: str,
    model: str,
    budget: float | None,
    system_prompt: str | None = None,
    chrome: bool = False,
    fallback_model: str | None = None,
    use_api_key: bool = False,
) -> Session:
    """Create a worker session for the given backend.

    *use_api_key*: when False (default), ANTHROPIC_API_KEY is stripped from the
    environment before spawning the Claude SDK client so the session bills
    through the Claude.ai subscription, not the API.  Set True only when you
    explicitly want API billing for this session.
    """
    from selfocode.sessions.claude import ClaudeSession
    from selfocode.sessions.cursor import CursorSession

    if backend == "cursor":
        return CursorSession(model=model, system_prompt=system_prompt)
    return ClaudeSession(
        model=model,
        max_budget_usd=budget,
        system_prompt=system_prompt,
        chrome=chrome,
        fallback_model=fallback_model,
        use_api_key=use_api_key,
    )


__all__ = [
    "log",
    "Agent",
    "AgentResult",
    "QueryResult",
    "Session",
    "SessionStats",
    "CycleResult",
    "RunResult",
    "Orchestrator",
    "TeamConfig",
    "TESTER_PROMPT",
    "TESTER_BROWSER_PROMPT",
    "ARCHITECT_PROMPT",
    "make_session",
]
