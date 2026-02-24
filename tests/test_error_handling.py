"""Tests for structured error handling."""

import pytest
from datetime import datetime, timezone

from kodo.errors import (
    AgentError,
    ErrorType,
    ErrorContext,
    ErrorSeverity,
    RetryPolicy,
    DEFAULT_RETRY,
    AGGRESSIVE_RETRY,
    NO_RETRY,
    _classify_exception,
)


class TestErrorClassification:
    """Test exception classification into ErrorType."""

    def test_classify_timeout(self):
        """Timeout exceptions should be classified as TIMEOUT."""
        exc = TimeoutError("Operation timed out after 30s")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.TIMEOUT

    def test_classify_connection_error(self):
        """Connection errors should be classified as NETWORK_ERROR."""
        exc = ConnectionError("Failed to connect to server")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.NETWORK_ERROR

    def test_classify_auth_error(self):
        """Auth errors should be classified as AUTHENTICATION_FAILURE."""
        exc = Exception("401 Unauthorized")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.AUTHENTICATION_FAILURE

    def test_classify_rate_limit(self):
        """Rate limit errors should be classified as RATE_LIMIT."""
        exc = Exception("HTTP 429: Too many requests")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.RATE_LIMIT

    def test_classify_context_overflow(self):
        """Context window exceeded should be CONTEXT_OVERFLOW."""
        exc = Exception("Token limit exceeded")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.CONTEXT_OVERFLOW

    def test_classify_unknown(self):
        """Unknown errors fall back to UNKNOWN."""
        exc = ValueError("Something weird happened")
        error_type = _classify_exception(exc)
        assert error_type == ErrorType.UNKNOWN


class TestAgentError:
    """Test AgentError structured error creation."""

    def test_from_exception_basic(self):
        """Create AgentError from an exception."""
        exc = TimeoutError("Timeout")
        error = AgentError.from_exception(exc)
        
        assert error.error_type == ErrorType.TIMEOUT
        assert error.message == "Timeout"
        assert error.retriable is True
        assert error.exception_type == "TimeoutError"

    def test_from_exception_with_context(self):
        """Create AgentError with rich context."""
        exc = ValueError("Invalid task")
        context = ErrorContext(
            agent_name="worker_smart",
            task_summary="Implement feature X",
            step_number=5,
        )
        error = AgentError.from_exception(exc, context=context)
        
        assert error.context.agent_name == "worker_smart"
        assert error.context.task_summary == "Implement feature X"
        assert error.context.step_number == 5

    def test_retriable_errors(self):
        """Retriable errors are marked correctly."""
        timeout_error = AgentError.from_exception(TimeoutError())
        assert timeout_error.retriable is True
        
        auth_error = AgentError.from_exception(Exception("401 Unauthorized"))
        assert auth_error.retriable is False
        
        network_error = AgentError.from_exception(ConnectionError())
        assert network_error.retriable is True

    def test_to_dict_serialization(self):
        """AgentError can be serialized to JSON-compatible dict."""
        exc = TimeoutError("Timed out")
        context = ErrorContext(agent_name="tester")
        error = AgentError.from_exception(exc, context=context)
        
        d = error.to_dict()
        
        assert d["error_type"] == "timeout"
        assert d["message"] == "Timed out"
        assert d["retriable"] is True
        assert d["context"]["agent"] == "tester"
        assert "timestamp" in d


class TestRetryPolicy:
    """Test retry policy logic."""

    def test_should_retry_retriable_error(self):
        """Retriable errors within limit should be retried."""
        policy = DEFAULT_RETRY
        error = AgentError(
            error_type=ErrorType.TIMEOUT,
            message="Timeout",
            retriable=True,
        )
        
        assert policy.should_retry(error, attempt=0) is True
        assert policy.should_retry(error, attempt=1) is True
        assert policy.should_retry(error, attempt=2) is True
        # Exceed max_retries
        assert policy.should_retry(error, attempt=3) is False

    def test_should_retry_non_retriable_error(self):
        """Non-retriable errors should not be retried."""
        policy = DEFAULT_RETRY
        error = AgentError(
            error_type=ErrorType.AUTHENTICATION_FAILURE,
            message="Auth failed",
            retriable=False,
        )
        
        assert policy.should_retry(error, attempt=0) is False

    def test_exponential_backoff(self):
        """Delay should increase exponentially."""
        policy = RetryPolicy(initial_delay_s=1.0, backoff_multiplier=2.0)
        
        assert policy.get_delay_s(0) == 1.0
        assert policy.get_delay_s(1) == 2.0
        assert policy.get_delay_s(2) == 4.0

    def test_backoff_max_delay_cap(self):
        """Backoff should cap at max_delay_s."""
        policy = RetryPolicy(initial_delay_s=1.0, backoff_multiplier=2.0, max_delay_s=10.0)
        
        # 2^5 = 32, but should cap at 10
        assert policy.get_delay_s(5) == 10.0

    def test_no_retry_policy(self):
        """NO_RETRY should never retry."""
        error = AgentError(
            error_type=ErrorType.TIMEOUT,
            message="Timeout",
            retriable=True,
        )
        
        assert NO_RETRY.should_retry(error, attempt=0) is False

    def test_aggressive_retry_policy(self):
        """AGGRESSIVE_RETRY should allow more attempts."""
        error = AgentError(
            error_type=ErrorType.TIMEOUT,
            message="Timeout",
            retriable=True,
        )
        
        # AGGRESSIVE_RETRY has max_retries=5
        assert AGGRESSIVE_RETRY.should_retry(error, attempt=4) is True
        assert AGGRESSIVE_RETRY.should_retry(error, attempt=5) is False


class TestErrorContext:
    """Test error context storage."""

    def test_context_defaults(self):
        """ErrorContext should have sensible defaults."""
        ctx = ErrorContext()
        
        assert ctx.agent_name == ""
        assert ctx.step_number == 0
        assert ctx.tool_args == {}
        assert ctx.extra == {}

    def test_context_rich_metadata(self):
        """ErrorContext can store rich metadata."""
        ctx = ErrorContext(
            agent_name="worker",
            task_summary="Build API",
            step_number=5,
            session_tokens_used=2000,
            tool_name="run_tests",
            tool_args={"timeout": 30},
            extra={"branch": "feature/x", "retry_count": 2},
        )
        
        assert ctx.agent_name == "worker"
        assert ctx.session_tokens_used == 2000
        assert ctx.tool_name == "run_tests"
        assert ctx.extra["retry_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
