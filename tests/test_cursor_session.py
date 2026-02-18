"""Tests for selfocode.sessions.cursor.CursorSession."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from selfocode import log
from selfocode.sessions.cursor import CursorSession
from tests.mocks.cursor_process import MockCursorProcess


def _make_popen_factory(**defaults):
    """Return a factory that creates MockCursorProcess with given defaults."""
    def factory(cmd, **kwargs):
        return MockCursorProcess(cmd, **defaults, **kwargs)
    return factory


def test_query_returns_result(tmp_path: Path):
    log.init(tmp_path, run_id="cursor_test")
    session = CursorSession(model="composer-1.5")

    with patch("selfocode.sessions.cursor.subprocess.Popen",
               _make_popen_factory(result_text="All done!", chat_id="c1")):
        result = session.query("do stuff", tmp_path, max_turns=10)

    assert result.text == "All done!"
    assert result.is_error is False
    assert session.stats.queries == 1


def test_chat_id_captured_for_resume(tmp_path: Path):
    log.init(tmp_path, run_id="cursor_resume")
    session = CursorSession(model="composer-1.5")

    with patch("selfocode.sessions.cursor.subprocess.Popen",
               _make_popen_factory(result_text="ok", chat_id="chat-xyz")):
        session.query("first", tmp_path, max_turns=10)

    # Second query should include --resume
    calls = []
    original_factory = _make_popen_factory(result_text="ok2", chat_id="chat-xyz")

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return original_factory(cmd, **kwargs)

    with patch("selfocode.sessions.cursor.subprocess.Popen", capturing_factory):
        session.query("second", tmp_path, max_turns=10)

    assert "--resume" in calls[0]
    assert "chat-xyz" in calls[0]


def test_system_prompt_prepended_once(tmp_path: Path):
    log.init(tmp_path, run_id="cursor_sysprompt")
    session = CursorSession(model="composer-1.5", system_prompt="Be helpful.")

    calls = []

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return MockCursorProcess(cmd, result_text="ok", chat_id="c1", **kwargs)

    with patch("selfocode.sessions.cursor.subprocess.Popen", capturing_factory):
        session.query("task1", tmp_path, max_turns=10)
        session.query("task2", tmp_path, max_turns=10)

    # First command should have system prompt prepended
    assert "Be helpful." in calls[0][-1]
    # Second command should NOT have system prompt
    assert "Be helpful." not in calls[1][-1]


def test_error_on_nonzero_returncode(tmp_path: Path):
    log.init(tmp_path, run_id="cursor_error")
    session = CursorSession(model="composer-1.5")

    with patch("selfocode.sessions.cursor.subprocess.Popen",
               _make_popen_factory(
                   result_text="", chat_id="c1", returncode=1,
                   stderr_text="fatal error\n")):
        result = session.query("fail", tmp_path, max_turns=10)

    assert result.is_error is True


def test_reset_clears_state(tmp_path: Path):
    log.init(tmp_path, run_id="cursor_reset")
    session = CursorSession(model="composer-1.5")

    with patch("selfocode.sessions.cursor.subprocess.Popen",
               _make_popen_factory(result_text="ok", chat_id="c1")):
        session.query("task", tmp_path, max_turns=10)

    assert session.stats.queries == 1
    assert session._chat_id == "c1"

    session.reset()

    assert session.stats.queries == 0
    assert session._chat_id is None
    assert session._system_prompt_sent is False
