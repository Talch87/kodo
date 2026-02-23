"""Tests for kodo.sessions.gemini_cli.GeminiCliSession."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kodo import log
from kodo.log import RunDir
from kodo.sessions.gemini_cli import GeminiCliSession
from tests.mocks.gemini_cli_process import MockGeminiCliProcess


def _make_popen_factory(**defaults):
    """Return a factory that creates MockGeminiCliProcess with given defaults."""

    def factory(cmd, **kwargs):
        return MockGeminiCliProcess(cmd, **defaults, **kwargs)

    return factory


def test_query_returns_result(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "gemini_test"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="All done!"),
    ):
        result = session.query("do stuff", tmp_path, max_turns=10)

    assert result.text == "All done!"
    assert result.is_error is False
    assert session.stats.queries == 1


def test_resume_on_subsequent_queries(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "gemini_resume"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="ok"),
    ):
        session.query("first", tmp_path, max_turns=10)

    assert session.session_id == "last"

    # Second query should include --resume
    calls = []
    original_factory = _make_popen_factory(result_text="ok2")

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return original_factory(cmd, **kwargs)

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("second", tmp_path, max_turns=10)

    assert "--resume" in calls[0]


def test_system_prompt_prepended_once(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "gemini_sysprompt"))
    session = GeminiCliSession(model="gemini-2.5-flash", system_prompt="Be helpful.")

    procs = []

    def capturing_factory(cmd, **kwargs):
        proc = MockGeminiCliProcess(cmd, result_text="ok", **kwargs)
        procs.append(proc)
        return proc

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("task1", tmp_path, max_turns=10)
        session.query("task2", tmp_path, max_turns=10)

    # First query should have system prompt in the prompt
    assert procs[0].prompt is not None
    assert "Be helpful." in procs[0].prompt

    # Second query should NOT have system prompt
    assert procs[1].prompt is not None
    assert "Be helpful." not in procs[1].prompt


def test_error_on_nonzero_returncode(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "gemini_error"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="", returncode=1, stderr_text="fatal error\n"),
    ):
        result = session.query("fail", tmp_path, max_turns=10)

    assert result.is_error is True
    assert "fatal error" in result.text


def test_reset_starts_fresh_session(tmp_path: Path):
    """After reset(), the next query starts a new session (no --resume)."""
    log.init(RunDir.create(tmp_path, "gemini_reset"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(result_text="ok"),
    ):
        session.query("task", tmp_path, max_turns=10)

    assert session.stats.queries == 1
    assert session.session_id is not None

    session.reset()
    assert session.stats.queries == 0
    assert session.session_id is None

    # After reset, next query should NOT have --resume
    calls = []
    original_factory = _make_popen_factory(result_text="ok2")

    def capturing_factory(cmd, **kwargs):
        calls.append(cmd)
        return original_factory(cmd, **kwargs)

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("new task", tmp_path, max_turns=10)

    assert "--resume" not in calls[0]


def test_tokens_extracted(tmp_path: Path):
    log.init(RunDir.create(tmp_path, "gemini_tokens"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    with patch(
        "kodo.sessions.base.subprocess.Popen",
        _make_popen_factory(
            result_text="done",
            input_tokens=500,
            output_tokens=200,
        ),
    ):
        result = session.query("task", tmp_path, max_turns=10)

    assert result.input_tokens == 500
    assert result.output_tokens == 200
    assert session.stats.total_input_tokens == 500
    assert session.stats.total_output_tokens == 200


def test_cwd_set_to_project_dir(tmp_path: Path):
    """Gemini CLI uses cwd instead of --cd flag."""
    log.init(RunDir.create(tmp_path, "gemini_cwd"))
    session = GeminiCliSession(model="gemini-2.5-flash")

    kwargs_captured = []

    def capturing_factory(cmd, **kwargs):
        kwargs_captured.append(kwargs)
        return MockGeminiCliProcess(cmd, result_text="ok", **kwargs)

    with patch("kodo.sessions.base.subprocess.Popen", capturing_factory):
        session.query("task", tmp_path, max_turns=10)

    assert kwargs_captured[0]["cwd"] == str(tmp_path)
