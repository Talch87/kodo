"""Tests for session retry logic with exponential backoff."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from kodo.sessions.base import (
    QueryResult,
    SessionStats,
    SessionRetryMixin,
)
from kodo.errors import AgentError, ErrorType


class MockSessionWithRetry(SessionRetryMixin):
    """Mock session for testing retry logic."""
    
    def __init__(self):
        self._stats = SessionStats()
        self.query_call_count = 0
        self.fail_count = 0  # How many times to fail before succeeding
    
    @property
    def stats(self) -> SessionStats:
        return self._stats
    
    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        """Mock query that can fail a configurable number of times."""
        self.query_call_count += 1
        
        if self.query_call_count <= self.fail_count:
            # Simulate failure
            raise TimeoutError("Query timed out")
        
        # Success
        self._stats.queries += 1
        self._stats.total_input_tokens += 100
        self._stats.total_output_tokens += 50
        self._stats.total_cost_usd += 0.001
        
        return QueryResult(
            text=f"Response to: {prompt[:50]}",
            elapsed_s=1.0,
            turns=1,
            cost_usd=0.001,
            is_error=False,
            input_tokens=100,
            output_tokens=50,
        )


class TestSessionRetryMixin:
    """Test automatic retry logic."""
    
    def test_query_succeeds_immediately(self):
        """Query that succeeds on first try doesn't retry."""
        session = MockSessionWithRetry()
        session.fail_count = 0  # Don't fail
        
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=3,
        )
        
        assert result.is_error is False
        assert "Response" in result.text
        assert session.query_call_count == 1  # Only called once
    
    def test_query_retries_once_then_succeeds(self):
        """Query that fails once then succeeds."""
        session = MockSessionWithRetry()
        session.fail_count = 1  # Fail once, then succeed
        
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=3,
        )
        
        assert result.is_error is False
        assert session.query_call_count == 2  # Failed once, succeeded on second
    
    def test_query_retries_multiple_times_then_succeeds(self):
        """Query that fails multiple times then succeeds."""
        session = MockSessionWithRetry()
        session.fail_count = 2  # Fail twice, then succeed
        
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=3,
        )
        
        assert result.is_error is False
        assert session.query_call_count == 3  # Failed twice, succeeded on third
    
    def test_query_exceeds_max_retries(self):
        """Query that exceeds max retries returns error."""
        session = MockSessionWithRetry()
        session.fail_count = 100  # Always fail
        
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=2,
        )
        
        assert result.is_error is True
        assert result.error is not None
        assert result.error.error_type == ErrorType.TIMEOUT
        assert session.query_call_count == 3  # Initial + 2 retries
    
    def test_error_contains_context(self):
        """Error result contains rich context."""
        session = MockSessionWithRetry()
        session.fail_count = 100  # Always fail
        
        result = session.query_with_retry(
            "Test prompt here",
            Path("/tmp"),
            max_turns=5,
            max_retries=1,
        )
        
        assert result.is_error is True
        assert result.error is not None
        assert "Test prompt" in result.error.context.task_summary
        assert result.error.context.session_queries_count == 0  # No successful queries
    
    def test_exponential_backoff_delay(self):
        """Backoff delays increase exponentially."""
        session = MockSessionWithRetry()
        session.fail_count = 3  # Fail 3 times, then succeed
        
        start = time.time()
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=3,
            initial_delay_s=0.05,  # Keep test fast
            backoff_multiplier=2.0,
        )
        elapsed = time.time() - start
        
        assert result.is_error is False
        
        # Should have slept: 0.05 + 0.1 + 0.2 = 0.35 seconds minimum
        # (Allow some margin for system variation)
        assert elapsed >= 0.3
    
    def test_retriable_vs_non_retriable_errors(self):
        """Non-retriable errors don't retry."""
        session = MockSessionWithRetry()
        
        # Create a non-retriable error (auth failure)
        with patch.object(session, 'query', side_effect=Exception("401 Unauthorized")):
            result = session.query_with_retry(
                "Test prompt",
                Path("/tmp"),
                max_turns=5,
                max_retries=3,
            )
        
        assert result.is_error is True
        assert result.error is not None
        assert result.error.error_type == ErrorType.AUTHENTICATION_FAILURE
        # Should not retry auth failures
        assert session.query_call_count == 1  # Only tried once
    
    def test_custom_max_retries(self):
        """Custom max_retries parameter is respected."""
        session = MockSessionWithRetry()
        session.fail_count = 100  # Always fail
        
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=5,
        )
        
        assert result.is_error is True
        assert session.query_call_count == 6  # Initial + 5 retries
    
    def test_custom_delay_parameters(self):
        """Custom delay parameters are used."""
        session = MockSessionWithRetry()
        session.fail_count = 2  # Fail twice, then succeed
        
        start = time.time()
        result = session.query_with_retry(
            "Test prompt",
            Path("/tmp"),
            max_turns=5,
            max_retries=3,
            initial_delay_s=0.02,
            backoff_multiplier=1.5,
        )
        elapsed = time.time() - start
        
        assert result.is_error is False
        
        # Should have slept: 0.02 + 0.03 = 0.05 seconds minimum
        assert elapsed >= 0.04
    
    def test_timeout_error_is_retriable(self):
        """Timeout errors trigger retries."""
        session = MockSessionWithRetry()
        
        call_count = 0
        def timeout_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Timed out")
            return QueryResult(text="Success", elapsed_s=1.0, is_error=False)
        
        with patch.object(session, 'query', side_effect=timeout_then_succeed):
            result = session.query_with_retry(
                "Test",
                Path("/tmp"),
                max_turns=5,
                max_retries=3,
            )
        
        assert result.is_error is False
        assert call_count == 2  # Called twice
    
    def test_network_error_is_retriable(self):
        """Network errors trigger retries."""
        session = MockSessionWithRetry()
        
        call_count = 0
        def network_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network unreachable")
            return QueryResult(text="Success", elapsed_s=1.0, is_error=False)
        
        with patch.object(session, 'query', side_effect=network_then_succeed):
            result = session.query_with_retry(
                "Test",
                Path("/tmp"),
                max_turns=5,
                max_retries=3,
            )
        
        assert result.is_error is False
        assert call_count == 2
    
    def test_rate_limit_error_is_retriable(self):
        """Rate limit (429) errors trigger retries."""
        session = MockSessionWithRetry()
        
        call_count = 0
        def rate_limit_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("HTTP 429: Too many requests")
            return QueryResult(text="Success", elapsed_s=1.0, is_error=False)
        
        with patch.object(session, 'query', side_effect=rate_limit_then_succeed):
            result = session.query_with_retry(
                "Test",
                Path("/tmp"),
                max_turns=5,
                max_retries=3,
            )
        
        assert result.is_error is False
        assert call_count == 2


class TestSessionRetryEdgeCases:
    """Edge case tests for session retry."""
    
    def test_zero_retries(self):
        """With max_retries=0, no retries occur."""
        session = MockSessionWithRetry()
        session.fail_count = 100  # Always fail
        
        result = session.query_with_retry(
            "Test",
            Path("/tmp"),
            max_turns=5,
            max_retries=0,
        )
        
        assert result.is_error is True
        assert session.query_call_count == 1  # No retries
    
    def test_long_prompt_truncated_in_context(self):
        """Long prompts are truncated in error context."""
        session = MockSessionWithRetry()
        session.fail_count = 100  # Always fail
        
        long_prompt = "x" * 1000
        result = session.query_with_retry(
            long_prompt,
            Path("/tmp"),
            max_turns=5,
            max_retries=1,
        )
        
        assert result.error is not None
        # Should be truncated to 100 chars
        assert len(result.error.context.task_summary) <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
