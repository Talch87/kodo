"""Tests for RetryStrategy — exponential backoff for transient API failures.

Covers: configuration, retryable error detection, delay computation,
execution with retries, integration with Agent, and edge cases.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kodo import log
from kodo.agent import Agent
from kodo.sessions.base import QueryResult, RetryStrategy, SessionStats


# ── Helpers ──────────────────────────────────────────────────────────────


class RateLimitError(Exception):
    """Simulates an HTTP 429 rate limit error."""

    def __init__(self, message: str = "429 Too Many Requests"):
        super().__init__(message)
        self.status_code = 429


class OverloadError(Exception):
    """Simulates an HTTP 529 overloaded error."""

    def __init__(self, message: str = "529 overloaded"):
        super().__init__(message)
        self.status_code = 529


class ServiceUnavailableError(Exception):
    """Simulates an HTTP 503 service unavailable."""

    def __init__(self, message: str = "503 Service Unavailable"):
        super().__init__(message)
        self.status_code = 503


class PermanentError(Exception):
    """Non-retryable error."""

    def __init__(self, message: str = "400 Bad Request"):
        super().__init__(message)
        self.status_code = 400


class RetryFakeSession:
    """Session stub that can be configured to fail N times then succeed."""

    def __init__(
        self,
        fail_count: int = 0,
        error_class: type = RateLimitError,
        response_text: str = "success",
    ):
        self._fail_count = fail_count
        self._error_class = error_class
        self._response_text = response_text
        self._attempt = 0
        self._stats = SessionStats()
        self.reset_count = 0

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def cost_bucket(self) -> str:
        return "test"

    @property
    def session_id(self) -> str | None:
        return "test-session"

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        self._attempt += 1
        if self._attempt <= self._fail_count:
            raise self._error_class()
        self._stats.queries += 1
        return QueryResult(
            text=self._response_text,
            elapsed_s=0.1,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

    def reset(self) -> None:
        self.reset_count += 1
        self._stats = SessionStats()

    @property
    def attempts(self) -> int:
        return self._attempt


# ── RetryStrategy unit tests ────────────────────────────────────────────


class TestRetryStrategyConfig:
    """Configuration defaults and customization."""

    def test_defaults(self) -> None:
        s = RetryStrategy()
        assert s.max_retries == 5
        assert s.initial_delay_s == 1.0
        assert s.backoff_multiplier == 2.0
        assert s.max_delay_s == 32.0

    def test_custom_config(self) -> None:
        s = RetryStrategy(
            max_retries=3,
            initial_delay_s=0.5,
            backoff_multiplier=3.0,
            max_delay_s=10.0,
        )
        assert s.max_retries == 3
        assert s.initial_delay_s == 0.5
        assert s.backoff_multiplier == 3.0
        assert s.max_delay_s == 10.0


class TestRetryStrategyRetryableDetection:
    """is_retryable() correctly identifies transient errors."""

    def test_429_by_status_code(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(RateLimitError()) is True

    def test_529_by_status_code(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(OverloadError()) is True

    def test_503_by_status_code(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(ServiceUnavailableError()) is True

    def test_400_not_retryable(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(PermanentError()) is False

    def test_rate_limit_in_message(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(Exception("rate limit exceeded")) is True

    def test_too_many_requests_in_message(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(Exception("Too Many Requests")) is True

    def test_overloaded_in_message(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(Exception("API overloaded, try again")) is True

    def test_generic_error_not_retryable(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(ValueError("bad value")) is False

    def test_capacity_in_message(self) -> None:
        s = RetryStrategy()
        assert s.is_retryable(Exception("insufficient capacity")) is True


class TestRetryStrategyDelay:
    """compute_delay() computes correct exponential backoff."""

    def test_first_attempt(self) -> None:
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        assert s.compute_delay(0) == 1.0

    def test_second_attempt(self) -> None:
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        assert s.compute_delay(1) == 2.0

    def test_third_attempt(self) -> None:
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        assert s.compute_delay(2) == 4.0

    def test_capped_at_max(self) -> None:
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0, max_delay_s=32.0)
        # attempt 6 = 1 * 2^6 = 64 → capped at 32
        assert s.compute_delay(6) == 32.0

    def test_custom_initial(self) -> None:
        s = RetryStrategy(initial_delay_s=0.5, backoff_multiplier=2.0)
        assert s.compute_delay(0) == 0.5
        assert s.compute_delay(1) == 1.0
        assert s.compute_delay(2) == 2.0

    def test_delay_sequence(self) -> None:
        """Verify the exact sequence: 1, 2, 4, 8, 16, 32, 32..."""
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0, max_delay_s=32.0)
        expected = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 32.0]
        actual = [s.compute_delay(i) for i in range(7)]
        assert actual == expected


class TestRetryStrategyExecution:
    """execute() retries correctly on transient errors."""

    @patch("kodo.sessions.base.time.sleep")
    def test_immediate_success(self, mock_sleep) -> None:
        """No retries needed when first call succeeds."""
        s = RetryStrategy()
        session = RetryFakeSession(fail_count=0)
        result = s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert result.text == "success"
        assert session.attempts == 1
        mock_sleep.assert_not_called()

    @patch("kodo.sessions.base.time.sleep")
    def test_one_retry(self, mock_sleep) -> None:
        """Retries once after a 429 error."""
        s = RetryStrategy(initial_delay_s=1.0)
        session = RetryFakeSession(fail_count=1, error_class=RateLimitError)
        result = s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert result.text == "success"
        assert session.attempts == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("kodo.sessions.base.time.sleep")
    def test_three_consecutive_retries(self, mock_sleep) -> None:
        """Survives 3 consecutive 429 errors (the key acceptance criterion)."""
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        session = RetryFakeSession(fail_count=3, error_class=RateLimitError)
        result = s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert result.text == "success"
        assert session.attempts == 4
        # Delays: 1s, 2s, 4s
        assert mock_sleep.call_count == 3
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]

    @patch("kodo.sessions.base.time.sleep")
    def test_five_consecutive_retries(self, mock_sleep) -> None:
        """Survives 5 consecutive errors (max retries default)."""
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        session = RetryFakeSession(fail_count=5, error_class=RateLimitError)
        result = s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert result.text == "success"
        assert session.attempts == 6
        assert mock_sleep.call_count == 5

    @patch("kodo.sessions.base.time.sleep")
    def test_exhausted_retries_raises(self, mock_sleep) -> None:
        """When all retries are exhausted, the error is raised."""
        s = RetryStrategy(max_retries=3, initial_delay_s=0.1)
        session = RetryFakeSession(fail_count=10, error_class=RateLimitError)
        with pytest.raises(RateLimitError):
            s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert session.attempts == 4  # 1 initial + 3 retries

    @patch("kodo.sessions.base.time.sleep")
    def test_non_retryable_error_not_retried(self, mock_sleep) -> None:
        """Permanent errors are raised immediately without retry."""
        s = RetryStrategy()
        session = RetryFakeSession(fail_count=1, error_class=PermanentError)
        with pytest.raises(PermanentError):
            s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert session.attempts == 1
        mock_sleep.assert_not_called()

    @patch("kodo.sessions.base.time.sleep")
    def test_mixed_retryable_errors(self, mock_sleep) -> None:
        """Retries work with 529 errors too."""
        s = RetryStrategy(initial_delay_s=1.0, backoff_multiplier=2.0)
        session = RetryFakeSession(fail_count=2, error_class=OverloadError)
        result = s.execute(session.query, "prompt", Path("/tmp"), max_turns=10)
        assert result.text == "success"
        assert session.attempts == 3


class TestAgentRetryIntegration:
    """Agent.run() uses RetryStrategy for transient errors."""

    @patch("kodo.sessions.base.time.sleep")
    def test_agent_survives_rate_limit(self, mock_sleep, tmp_path: Path) -> None:
        """Agent survives a rate limit error and returns success."""
        log.init(tmp_path, run_id="test-retry-agent")
        session = RetryFakeSession(fail_count=2, error_class=RateLimitError)
        strategy = RetryStrategy(initial_delay_s=0.01)
        agent = Agent(
            session, "test agent", max_turns=10, retry_strategy=strategy
        )
        result = agent.run("do work", tmp_path, agent_name="worker")
        assert not result.is_error
        assert result.text == "success"
        assert session.attempts == 3

    @patch("kodo.sessions.base.time.sleep")
    def test_agent_exhausted_retries_raises(
        self, mock_sleep, tmp_path: Path
    ) -> None:
        """When retries exhausted, exception propagates to caller (e.g. verify_done)."""
        log.init(tmp_path, run_id="test-retry-exhaust")
        session = RetryFakeSession(fail_count=100, error_class=RateLimitError)
        strategy = RetryStrategy(max_retries=2, initial_delay_s=0.01)
        agent = Agent(
            session, "test agent", max_turns=10, retry_strategy=strategy
        )
        with pytest.raises(RateLimitError):
            agent.run("do work", tmp_path, agent_name="worker")

    @patch("kodo.sessions.base.time.sleep")
    def test_agent_with_timeout_and_retry(self, mock_sleep, tmp_path: Path) -> None:
        """Agent with timeout also gets retry protection."""
        log.init(tmp_path, run_id="test-retry-timeout")
        session = RetryFakeSession(fail_count=1, error_class=RateLimitError)
        strategy = RetryStrategy(initial_delay_s=0.01)
        agent = Agent(
            session,
            "test agent",
            max_turns=10,
            timeout_s=30.0,
            retry_strategy=strategy,
        )
        result = agent.run("do work", tmp_path, agent_name="worker")
        assert not result.is_error
        assert result.text == "success"

    def test_default_retry_strategy(self, tmp_path: Path) -> None:
        """Agent gets a default RetryStrategy if none provided."""
        session = RetryFakeSession()
        agent = Agent(session, "test agent", max_turns=10)
        assert agent.retry_strategy is not None
        assert isinstance(agent.retry_strategy, RetryStrategy)
        assert agent.retry_strategy.max_retries == 5
