"""Tests for kodo.sessions.cursor.CursorSession."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kodo import log
from kodo.log import RunDir
from kodo.sessions.cursor import CursorSession
from tests.mocks.cursor_process import MockCursorProcess


def _make_popen_factory(**defaults):
    """Return a factory that creates MockCursorProcess with given defaults."""

    def factory(cmd, **kwargs):
        return MockCursorProcess(cmd, **defaults, **kwargs)

    return factory


def test_query_returns_result(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "cursor_test"))
    session = CursorSession(model="composer-1.5")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="All done!", chat_id="c1"),
    ):
        result = session.query("do stuff", tmp_path, max_turns=10)

    assert result.text == "All done!"
    assert result.is_error is False
    assert session.stats.queries == 1


def test_chat_id_captured_for_resume(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "cursor_resume"))
    session = CursorSession(model="composer-1.5")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="ok", chat_id="chat-xyz"),
    ):
        session.query("first", tmp_path, max_turns=10)

    # Second query should include --resume
    calls = []
    original_factory = _make_popen_factory(result_text="ok2", chat_id="chat-xyz")

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return original_factory(cmd, **kwargs)

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("second", tmp_path, max_turns=10)

    assert "--resume" in calls[0]
    assert "chat-xyz" in calls[0]


def test_system_prompt_prepended_once(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "cursor_sysprompt"))
    session = CursorSession(model="composer-1.5", system_prompt="Be helpful.")

    procs = []

    def capturing_factory(cmd, **kwargs):
        proc = MockCursorProcess(cmd, result_text="ok", chat_id="c1", **kwargs)
        procs.append(proc)
        return proc

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("task1", tmp_path, max_turns=10)
        session.query("task2", tmp_path, max_turns=10)

    # First query should have system prompt in the prompt
    assert "Be helpful." in procs[0].prompt
    # Second query should NOT have system prompt
    assert "Be helpful." not in procs[1].prompt


def test_error_on_nonzero_returncode(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "cursor_error"))
    session = CursorSession(model="composer-1.5")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(
            result_text="", chat_id="c1", returncode=1, stderr_text="fatal error\n"
        ),
    ):
        result = session.query("fail", tmp_path, max_turns=10)

    assert result.is_error is True


def test_reset_starts_fresh_session(tmp_path: Path):
    """After reset(), the next query starts a new chat (no --resume flag)."""
    log.init(RunDir.create(tmp_path, "cursor_reset"))
    session = CursorSession(model="composer-1.5")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="ok", chat_id="c1"),
    ):
        session.query("task", tmp_path, max_turns=10)

    assert session.stats.queries == 1
    assert session.session_id == "c1"

    session.reset()
    assert session.stats.queries == 0

    # After reset, next query should NOT resume the old chat
    calls = []
    original_factory = _make_popen_factory(result_text="ok2", chat_id="c2")

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return original_factory(cmd, **kwargs)

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("new task", tmp_path, max_turns=10)

    assert "--resume" not in calls[0]
