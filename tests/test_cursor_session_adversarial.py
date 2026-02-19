"""Adversarial tests for CursorSession — based on expected interface behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from kodo import log
from kodo.sessions.cursor import CursorSession
from tests.mocks.cursor_process import MockCursorProcess


def test_no_result_message_returns_empty_text(tmp_path: Path):
    """If cursor-agent produces output but no 'result' type message, text should be empty."""
    log.init(tmp_path, run_id="no_result")
    session = CursorSession()

    def factory(cmd, **kwargs):
        proc = MockCursorProcess(cmd, result_text="", chat_id="c1", **kwargs)
        # Replace stdout with only non-result messages
        import io

        messages = [
            json.dumps({"type": "progress", "message": "working..."}),
            json.dumps({"type": "status", "chatId": "c1"}),
        ]
        proc.stdout = io.StringIO("\n".join(messages) + "\n")
        return proc

    with patch("kodo.sessions.cursor.subprocess.Popen", factory):
        result = session.query("do something", tmp_path, max_turns=10)

    assert result.text == ""
    assert result.is_error is False


def test_empty_stdout_no_crash(tmp_path: Path):
    """If cursor-agent produces no output at all, should return empty result."""
    log.init(tmp_path, run_id="empty_out")
    session = CursorSession()

    def factory(cmd, **kwargs):
        import io

        proc = MockCursorProcess(cmd, result_text="", chat_id="c1", **kwargs)
        proc.stdout = io.StringIO("")
        return proc

    with patch("kodo.sessions.cursor.subprocess.Popen", factory):
        result = session.query("do something", tmp_path, max_turns=10)

    assert result.text == ""
    assert result.is_error is False


def test_chat_id_from_alternate_keys(tmp_path: Path):
    """cursor-agent might report chat_id or session_id instead of chatId."""
    log.init(tmp_path, run_id="alt_keys")

    for key in ["chat_id", "session_id"]:
        session = CursorSession()

        def factory(cmd, key=key, **kwargs):
            import io

            messages = [
                json.dumps({"type": "result", "result": "ok", key: f"id-{key}"}),
            ]
            proc = MockCursorProcess(cmd, result_text="ok", chat_id="c1", **kwargs)
            proc.stdout = io.StringIO("\n".join(messages) + "\n")
            return proc

        with patch("kodo.sessions.cursor.subprocess.Popen", factory):
            session.query("q", tmp_path, max_turns=10)

        assert session._chat_id == f"id-{key}"


def test_system_prompt_resent_after_reset(tmp_path: Path):
    """After reset(), the system prompt should be prepended to the next query again."""
    log.init(tmp_path, run_id="reset_sysprompt")
    session = CursorSession(system_prompt="Be careful.")

    calls = []

    def factory(cmd, **kwargs):
        calls.append(cmd)
        return MockCursorProcess(cmd, result_text="ok", chat_id="c1", **kwargs)

    with patch("kodo.sessions.cursor.subprocess.Popen", factory):
        session.query("first", tmp_path, max_turns=10)
        session.reset()
        session.query("second", tmp_path, max_turns=10)

    # Both first and post-reset queries should have system prompt
    assert "Be careful." in calls[0][-1]
    assert "Be careful." in calls[1][-1]


def test_large_result_text_not_truncated(tmp_path: Path):
    """Session should pass through large result text without truncating."""
    log.init(tmp_path, run_id="large_result")
    session = CursorSession()
    big_text = "x" * 100_000

    def factory(cmd, **kwargs):
        return MockCursorProcess(cmd, result_text=big_text, chat_id="c1", **kwargs)

    with patch("kodo.sessions.cursor.subprocess.Popen", factory):
        result = session.query("q", tmp_path, max_turns=10)

    assert len(result.text) == 100_000


def test_workspace_flag_matches_project_dir(tmp_path: Path):
    """The --workspace flag should be set to the project_dir."""
    log.init(tmp_path, run_id="workspace")
    session = CursorSession()
    calls = []

    def factory(cmd, **kwargs):
        calls.append(cmd)
        return MockCursorProcess(cmd, result_text="ok", chat_id="c1", **kwargs)

    with patch("kodo.sessions.cursor.subprocess.Popen", factory):
        session.query("q", tmp_path, max_turns=10)

    cmd = calls[0]
    ws_idx = cmd.index("--workspace")
    assert cmd[ws_idx + 1] == str(tmp_path)
