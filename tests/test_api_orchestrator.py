"""Tests for kodo.orchestrators.api.ApiOrchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kodo import log
from kodo.orchestrators.api import ApiOrchestrator, _messages_to_text
from tests.conftest import FakeRunResult

def test_cycle_done_returns_finished(tmp_path: Path):
    log.init(tmp_path, run_id="api_done")

    def fake_run_sync(prompt, *, usage_limits=None):
        # Find the done tool among the agent's tools and call it
        for tool in agent_tools:
            if tool.name == "done":
                tool.function(summary="all done", success=True)
                break
        return FakeRunResult()

    agent_tools = []

    def fake_agent_init(self, model, *, system_prompt=None, tools=None):
        nonlocal agent_tools
        agent_tools = tools or []
        self.run_sync = fake_run_sync

    team = _make_fake_team()

    with patch("kodo.orchestrators.api.Agent.__init__", fake_agent_init), \
         patch("kodo.orchestrators.api.verify_done", return_value=None):
        orch = ApiOrchestrator(model="claude-opus-4-6")
        result = orch.cycle("build feature", tmp_path, team, max_exchanges=10)

    assert result.finished is True
    assert result.summary == "all done"


def test_cycle_no_done_returns_summary(tmp_path: Path):
    log.init(tmp_path, run_id="api_nodone")

    def fake_run_sync(prompt, *, usage_limits=None):
        return FakeRunResult(output="partial progress")

    def fake_agent_init(self, model, *, system_prompt=None, tools=None):
        self.run_sync = fake_run_sync

    team = _make_fake_team()

    with patch("kodo.orchestrators.api.Agent.__init__", fake_agent_init), \
         patch.object(ApiOrchestrator, "_summarize", return_value="summary of work"):
        orch = ApiOrchestrator(model="claude-opus-4-6")
        result = orch.cycle("build feature", tmp_path, team, max_exchanges=10)

    assert result.finished is False
    assert result.summary == "summary of work"


def test_usage_limit_exceeded(tmp_path: Path):
    log.init(tmp_path, run_id="api_limit")
    from pydantic_ai.exceptions import UsageLimitExceeded

    def fake_agent_init(self, model, *, system_prompt=None, tools=None):
        def fake_run_sync(prompt, *, usage_limits=None):
            raise UsageLimitExceeded("limit hit")
        self.run_sync = fake_run_sync

    team = _make_fake_team()

    with patch("kodo.orchestrators.api.Agent.__init__", fake_agent_init):
        orch = ApiOrchestrator(model="claude-opus-4-6")
        result = orch.cycle("build feature", tmp_path, team, max_exchanges=5)

    assert result.finished is False


def test_529_fallback(tmp_path: Path):
    log.init(tmp_path, run_id="api_529")
    from pydantic_ai.exceptions import ModelHTTPError

    call_count = [0]

    def fake_agent_init(self, model, *, system_prompt=None, tools=None):
        def fake_run_sync(prompt, *, usage_limits=None):
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 1:
                raise ModelHTTPError(status_code=529, model_name="test", body="overloaded")
            return FakeRunResult()
        self.run_sync = fake_run_sync

    team = _make_fake_team()

    with patch("kodo.orchestrators.api.Agent.__init__", fake_agent_init), \
         patch.object(ApiOrchestrator, "_summarize", return_value="done"):
        orch = ApiOrchestrator(
            model="claude-opus-4-6",
            fallback_model="claude-sonnet-4-5-20250929",
        )
        result = orch.cycle("build feature", tmp_path, team, max_exchanges=10)

    # Should have retried with fallback and succeeded
    assert call_count[0] == 2


def test_messages_to_text():
    """Unit test the _messages_to_text helper with mock message objects."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    messages = [
        ModelRequest(parts=[UserPromptPart(content="hello", timestamp="2024-01-01T00:00:00Z")]),
        ModelResponse(
            parts=[TextPart(part_kind="text", content="hi there")],
            model_name="test",
            timestamp="2024-01-01T00:00:00Z",
        ),
    ]
    text = _messages_to_text(messages)
    assert "[user] hello" in text
    assert "[assistant] hi there" in text


# ── shared helpers ───────────────────────────────────────────────────────

def _make_fake_team():
    """Create a minimal fake TeamConfig for orchestrator tests."""
    from kodo.agent import Agent
    from tests.conftest import FakeSession

    session = FakeSession(response_text="ok")
    agent = Agent(session, "test agent", max_turns=5)
    return {"worker": agent}
