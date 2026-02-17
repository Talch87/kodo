"""Tests for verify_done gate logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from selfocode.orchestrators.base import verify_done
from selfocode.agent import Agent
from tests.conftest import FakeSession, make_agent


GOAL = "Build a hello-world web server."
SUMMARY = "Implemented hello-world server on port 8000."


def test_all_pass(tmp_project: Path) -> None:
    """When both agents say ALL CHECKS PASS, verify_done returns None."""
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_tester_fails(tmp_project: Path) -> None:
    """When tester finds issues, verify_done returns rejection."""
    team = {
        "tester": make_agent("ImportError: no module named 'server'"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "DONE REJECTED" in result
    assert "tester found issues" in result
    assert "ImportError" in result


def test_architect_fails(tmp_project: Path) -> None:
    """When architect finds issues, verify_done returns rejection."""
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
        "architect": make_agent("Critical bug: SQL injection in query handler"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "DONE REJECTED" in result
    assert "Architect found issues" in result
    assert "SQL injection" in result


def test_both_fail(tmp_project: Path) -> None:
    """When both agents find issues, both are included in rejection."""
    team = {
        "tester": make_agent("Server crashes on startup"),
        "architect": make_agent("Missing error handling in routes"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "tester found issues" in result
    assert "Architect found issues" in result
    assert "Server crashes" in result
    assert "Missing error handling" in result


def test_case_insensitive_pass(tmp_project: Path) -> None:
    """ALL CHECKS PASS matching is case-insensitive."""
    team = {
        "tester": make_agent("all checks pass - looks good"),
        "architect": make_agent("All Checks Pass"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_no_tester_in_team(tmp_project: Path) -> None:
    """If there's no tester, only architect runs."""
    team = {
        "architect": make_agent("ALL CHECKS PASS"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_no_architect_in_team(tmp_project: Path) -> None:
    """If there's no architect, only tester runs."""
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_tester_browser_used_when_no_tester(tmp_project: Path) -> None:
    """tester_browser runs when tester is absent."""
    team = {
        "tester_browser": make_agent("ALL CHECKS PASS"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_tester_browser_fails(tmp_project: Path) -> None:
    """tester_browser rejection works the same as tester."""
    team = {
        "tester_browser": make_agent("Page returns 404"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "Page returns 404" in result


def test_both_testers_run_when_both_exist(tmp_project: Path) -> None:
    """BUG FIX: when both tester and tester_browser exist, both should run."""
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
        "tester_browser": make_agent("Button click does nothing"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "tester_browser found issues" in result
    assert "Button click" in result


def test_both_testers_pass(tmp_project: Path) -> None:
    """When both testers exist and both pass, verify_done returns None."""
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
        "tester_browser": make_agent("ALL CHECKS PASS"),
        "architect": make_agent("ALL CHECKS PASS"),
    }
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_empty_team(tmp_project: Path) -> None:
    """With no verification agents, done passes (nothing to check)."""
    team = {"worker": make_agent("done")}
    assert verify_done(GOAL, SUMMARY, team, tmp_project) is None


def test_agents_called_with_new_conversation(tmp_project: Path) -> None:
    """Verification agents are called with new_conversation=True."""
    tester = make_agent("ALL CHECKS PASS")
    architect = make_agent("ALL CHECKS PASS")
    team = {"tester": tester, "architect": architect}

    verify_done(GOAL, SUMMARY, team, tmp_project)

    # new_conversation=True triggers session.reset()
    assert tester.session.reset_count == 1
    assert architect.session.reset_count == 1


def test_goal_and_summary_in_prompt(tmp_project: Path) -> None:
    """Verification prompt includes the original goal and summary."""
    tester = make_agent("ALL CHECKS PASS")
    team = {"tester": tester}

    with patch.object(tester, "run", wraps=tester.run) as mock_run:
        verify_done(GOAL, SUMMARY, team, tmp_project)
        prompt = mock_run.call_args[0][0]
        assert GOAL in prompt
        assert SUMMARY in prompt


def test_report_truncated_at_3000(tmp_project: Path) -> None:
    """Long agent reports are truncated in the rejection message."""
    long_report = "x" * 5000
    team = {"tester": make_agent(long_report)}
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    # The tester report portion should be at most 3000 chars
    tester_section = result.split("found issues:**\n")[1].split("\n\nFix these")[0]
    assert len(tester_section) <= 3000


# --- Exception handling tests (Bug 1 fix) ---

class _CrashingSession(FakeSession):
    def query(self, prompt, project_dir, *, max_turns):
        raise RuntimeError("SDK connection lost")


def test_tester_exception_becomes_rejection(tmp_project: Path) -> None:
    """BUG FIX: agent crash should be a rejection, not an unhandled exception."""
    crashing_agent = Agent(_CrashingSession(), "Tester", max_turns=10)
    team = {
        "tester": crashing_agent,
        "architect": make_agent("ALL CHECKS PASS"),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "DONE REJECTED" in result
    assert "crashed" in result
    assert "SDK connection lost" in result


def test_architect_exception_becomes_rejection(tmp_project: Path) -> None:
    """BUG FIX: architect crash is a rejection, not a crash."""
    crashing_agent = Agent(_CrashingSession(), "Architect", max_turns=10)
    team = {
        "tester": make_agent("ALL CHECKS PASS"),
        "architect": crashing_agent,
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert "DONE REJECTED" in result
    assert "Architect crashed" in result


def test_both_crash(tmp_project: Path) -> None:
    """Both agents crashing produces two rejection items."""
    team = {
        "tester": Agent(_CrashingSession(), "T", max_turns=10),
        "architect": Agent(_CrashingSession(), "A", max_turns=10),
    }
    result = verify_done(GOAL, SUMMARY, team, tmp_project)
    assert result is not None
    assert result.count("crashed") == 2
