"""Tests for selfocode.sessions.claude.ClaudeSession."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from selfocode import log
from selfocode.sessions.claude import ClaudeSession, _extract_tokens
from tests.mocks.claude_sdk import (
    MockClaudeAgentOptions,
    MockClaudeSDKClient,
    MockPermissionResultAllow,
    MockPermissionResultDeny,
    MockResultMessage,
)


def _install_mock_sdk(responses=None):
    """Install a fake claude_agent_sdk module and return the mock client that will be created."""
    mock_client = MockClaudeSDKClient(responses=responses)

    fake_mod = ModuleType("claude_agent_sdk")
    fake_mod.ClaudeAgentOptions = MockClaudeAgentOptions
    fake_mod.ClaudeSDKClient = lambda options=None: mock_client
    fake_mod.ResultMessage = MockResultMessage

    fake_types = ModuleType("claude_agent_sdk.types")
    fake_types.PermissionResultAllow = MockPermissionResultAllow
    fake_types.PermissionResultDeny = MockPermissionResultDeny

    return mock_client, {"claude_agent_sdk": fake_mod, "claude_agent_sdk.types": fake_types}


def test_query_returns_result(tmp_path: Path):
    log.init(tmp_path, run_id="claude_query")
    resp = MockResultMessage(result="Hello world", num_turns=2, total_cost_usd=0.05,
                             usage={"input_tokens": 200, "output_tokens": 100})
    mock_client, fake_modules = _install_mock_sdk(responses=[resp])

    with patch.dict(sys.modules, fake_modules):
        session = ClaudeSession(model="sonnet", use_api_key=True)
        try:
            result = session.query("say hello", tmp_path, max_turns=10)
        finally:
            session._loop.call_soon_threadsafe(session._loop.stop)
            session._thread.join(timeout=5)

    assert result.text == "Hello world"
    assert result.is_error is False
    assert result.turns == 2
    assert result.cost_usd == 0.05
    assert result.input_tokens == 200
    assert result.output_tokens == 100


def test_stats_accumulate(tmp_path: Path):
    log.init(tmp_path, run_id="claude_stats")
    r1 = MockResultMessage(result="r1", total_cost_usd=0.01,
                           usage={"input_tokens": 100, "output_tokens": 50})
    r2 = MockResultMessage(result="r2", total_cost_usd=0.02,
                           usage={"input_tokens": 200, "output_tokens": 80})

    # We need two separate clients for two queries since _ensure_client caches
    call_count = [0]

    def make_client(options=None):
        nonlocal call_count
        responses = [r1] if call_count[0] == 0 else [r2]
        call_count[0] += 1
        return MockClaudeSDKClient(options=options, responses=responses)

    fake_mod = ModuleType("claude_agent_sdk")
    fake_mod.ClaudeAgentOptions = MockClaudeAgentOptions
    fake_mod.ClaudeSDKClient = make_client
    fake_mod.ResultMessage = MockResultMessage
    fake_types = ModuleType("claude_agent_sdk.types")
    fake_types.PermissionResultAllow = MockPermissionResultAllow
    fake_types.PermissionResultDeny = MockPermissionResultDeny

    with patch.dict(sys.modules, {
        "claude_agent_sdk": fake_mod,
        "claude_agent_sdk.types": fake_types,
    }):
        session = ClaudeSession(model="sonnet", use_api_key=True)
        try:
            session.query("q1", tmp_path, max_turns=10)
            # Force reconnect for second query to get fresh client with r2
            session._client = None
            session._project_dir = None
            session.query("q2", tmp_path, max_turns=10)
        finally:
            session._loop.call_soon_threadsafe(session._loop.stop)
            session._thread.join(timeout=5)

    assert session.stats.queries == 2
    assert session.stats.total_input_tokens == 300
    assert session.stats.total_output_tokens == 130
    assert abs(session.stats.total_cost_usd - 0.03) < 1e-9


def test_reset_disconnects(tmp_path: Path):
    log.init(tmp_path, run_id="claude_reset")
    mock_client, fake_modules = _install_mock_sdk()

    with patch.dict(sys.modules, fake_modules):
        session = ClaudeSession(model="sonnet", use_api_key=True)
        try:
            session.query("q", tmp_path, max_turns=10)
            assert session.stats.queries == 1
            session.reset()
            assert session.stats.queries == 0
            assert session._client is None
        finally:
            session._loop.call_soon_threadsafe(session._loop.stop)
            session._thread.join(timeout=5)


def test_extract_tokens_variants():
    assert _extract_tokens({"input_tokens": 10, "output_tokens": 5}) == (10, 5)
    assert _extract_tokens({"prompt_tokens": 10, "completion_tokens": 5}) == (10, 5)
    assert _extract_tokens(None) == (None, None)
    assert _extract_tokens({}) == (None, None)


def test_api_key_stripped_by_default(tmp_path: Path, monkeypatch):
    log.init(tmp_path, run_id="claude_key_strip")

    keys_during_init = []

    class TrackingOptions(MockClaudeAgentOptions):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            keys_during_init.append(os.environ.get("ANTHROPIC_API_KEY"))

    mock_client = MockClaudeSDKClient()
    fake_mod = ModuleType("claude_agent_sdk")
    fake_mod.ClaudeAgentOptions = TrackingOptions
    fake_mod.ClaudeSDKClient = lambda options=None: mock_client
    fake_mod.ResultMessage = MockResultMessage
    fake_types = ModuleType("claude_agent_sdk.types")
    fake_types.PermissionResultAllow = MockPermissionResultAllow
    fake_types.PermissionResultDeny = MockPermissionResultDeny

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret")

    with patch.dict(sys.modules, {
        "claude_agent_sdk": fake_mod,
        "claude_agent_sdk.types": fake_types,
    }):
        session = ClaudeSession(model="sonnet", use_api_key=False)
        try:
            session.query("q", tmp_path, max_turns=10)
        finally:
            session._loop.call_soon_threadsafe(session._loop.stop)
            session._thread.join(timeout=5)

    # Key should have been stripped during _ensure_client
    assert keys_during_init[0] is None
    # Key should be restored after
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-test-secret"


def test_api_key_kept_when_explicit(tmp_path: Path, monkeypatch):
    log.init(tmp_path, run_id="claude_key_keep")

    keys_during_init = []

    class TrackingOptions(MockClaudeAgentOptions):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            keys_during_init.append(os.environ.get("ANTHROPIC_API_KEY"))

    mock_client = MockClaudeSDKClient()
    fake_mod = ModuleType("claude_agent_sdk")
    fake_mod.ClaudeAgentOptions = TrackingOptions
    fake_mod.ClaudeSDKClient = lambda options=None: mock_client
    fake_mod.ResultMessage = MockResultMessage
    fake_types = ModuleType("claude_agent_sdk.types")
    fake_types.PermissionResultAllow = MockPermissionResultAllow
    fake_types.PermissionResultDeny = MockPermissionResultDeny

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret")

    with patch.dict(sys.modules, {
        "claude_agent_sdk": fake_mod,
        "claude_agent_sdk.types": fake_types,
    }):
        session = ClaudeSession(model="sonnet", use_api_key=True)
        try:
            session.query("q", tmp_path, max_turns=10)
        finally:
            session._loop.call_soon_threadsafe(session._loop.stop)
            session._thread.join(timeout=5)

    assert keys_during_init[0] == "sk-test-secret"
