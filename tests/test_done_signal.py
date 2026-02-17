"""Tests for the done tool handler in ClaudeCodeOrchestrator's MCP server."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

from selfocode.orchestrators.claude_code import _DoneSignal, _build_mcp_server
from selfocode.summarizer import Summarizer
from tests.conftest import make_agent


def _make_done_handler(team, project_dir, goal="Build X"):
    """Build the MCP server and extract the `done` handler function."""
    signal = _DoneSignal()
    with patch("selfocode.summarizer._probe_ollama", return_value=None), \
         patch("selfocode.summarizer._probe_gemini", return_value=None):
        summarizer = Summarizer()
    mcp = _build_mcp_server(team, project_dir, summarizer, signal, goal)

    # Extract the done handler from FastMCP's registered tools
    # The done function is the last tool added
    done_fn = None
    for tool_name, tool in mcp._tool_manager._tools.items():
        if tool_name == "done":
            done_fn = tool.fn
            break

    assert done_fn is not None, "done tool not found in MCP server"
    return done_fn, signal


class TestDoneHandlerAccepted:
    def test_accepted_when_all_pass(self, tmp_project: Path) -> None:
        team = {
            "worker": make_agent("done"),
            "tester": make_agent("ALL CHECKS PASS"),
            "architect": make_agent("ALL CHECKS PASS"),
        }
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("Built everything", True)

        assert signal.called is True
        assert signal.success is True
        assert signal.summary == "Built everything"
        assert "accepted" in result.lower() or "pass" in result.lower()

    def test_signal_not_set_on_rejection(self, tmp_project: Path) -> None:
        team = {
            "worker": make_agent("done"),
            "tester": make_agent("ImportError: missing module"),
            "architect": make_agent("ALL CHECKS PASS"),
        }
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("Built everything", True)

        assert signal.called is False
        assert "REJECTED" in result

    def test_unsuccessful_skips_verification(self, tmp_project: Path) -> None:
        """success=False bypasses verification entirely."""
        tester = make_agent("ALL CHECKS PASS")
        team = {
            "worker": make_agent("done"),
            "tester": tester,
        }
        done_fn, signal = _make_done_handler(team, tmp_project)

        with patch.object(tester, "run", wraps=tester.run) as mock_run:
            result = done_fn("Gave up, blocked on API key", False)
            mock_run.assert_not_called()

        assert signal.called is True
        assert signal.success is False
        assert "unsuccessful" in result.lower()


class TestDoneHandlerRejection:
    def test_tester_rejection_includes_report(self, tmp_project: Path) -> None:
        team = {
            "tester": make_agent("Server returns 500 on /api/health"),
            "architect": make_agent("ALL CHECKS PASS"),
        }
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("All done", True)

        assert "REJECTED" in result
        assert "500" in result
        assert "/api/health" in result

    def test_architect_rejection_includes_report(self, tmp_project: Path) -> None:
        team = {
            "tester": make_agent("ALL CHECKS PASS"),
            "architect": make_agent("SQL injection in user_handler.py:42"),
        }
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("All done", True)

        assert "REJECTED" in result
        assert "SQL injection" in result

    def test_both_rejections_included(self, tmp_project: Path) -> None:
        team = {
            "tester": make_agent("App crashes on startup"),
            "architect": make_agent("Missing auth middleware"),
        }
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("All done", True)

        assert "App crashes" in result
        assert "Missing auth" in result

    def test_rejection_tells_to_fix(self, tmp_project: Path) -> None:
        team = {"tester": make_agent("broken")}
        done_fn, signal = _make_done_handler(team, tmp_project)
        result = done_fn("All done", True)

        assert "fix" in result.lower()
        assert "done again" in result.lower()


class TestDoneSignal:
    def test_initial_state(self) -> None:
        signal = _DoneSignal()
        assert signal.called is False
        assert signal.summary == ""
        assert signal.success is False
