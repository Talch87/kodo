"""Tests for build_team_tools."""

from __future__ import annotations

from selfocode.orchestrators.base import build_team_tools
from tests.conftest import make_agent


def test_generates_ask_tools_per_agent() -> None:
    team = {
        "worker": make_agent(prompt="A skilled coder."),
        "tester": make_agent(prompt="A tester agent."),
    }
    tools = build_team_tools(team)
    names = [t["name"] for t in tools]
    assert "ask_worker" in names
    assert "ask_tester" in names


def test_done_tool_always_present() -> None:
    team = {"worker": make_agent(prompt="Coder.")}
    tools = build_team_tools(team)
    names = [t["name"] for t in tools]
    assert "done" in names


def test_done_tool_mentions_verification() -> None:
    team = {"worker": make_agent(prompt="Coder.")}
    tools = build_team_tools(team)
    done_tool = next(t for t in tools if t["name"] == "done")
    assert "verification" in done_tool["description"].lower()


def test_agent_description_in_tool() -> None:
    team = {"worker": make_agent(prompt="A skilled coder.\nMore details here.")}
    tools = build_team_tools(team)
    worker_tool = next(t for t in tools if t["name"] == "ask_worker")
    assert "A skilled coder." in worker_tool["description"]
    # Full description is included
    assert "More details" in worker_tool["description"]


def test_tool_schema_has_required_task() -> None:
    team = {"worker": make_agent(prompt="Coder.")}
    tools = build_team_tools(team)
    worker_tool = next(t for t in tools if t["name"] == "ask_worker")
    assert "task" in worker_tool["input_schema"]["required"]


def test_empty_team_only_done() -> None:
    tools = build_team_tools({})
    assert len(tools) == 1
    assert tools[0]["name"] == "done"
