"""Structured error types for agent runs and session failures.

Enables programmatic error handling, retry decisions, and better observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    """Classification of error types for better handling."""
    
    # Transient errors — safe to retry
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TEMPORARY_API_FAILURE = "temporary_api_failure"
    NETWORK_ERROR = "network_error"
    CONTEXT_OVERFLOW = "context_overflow"  # Session-specific
    
    # Permanent errors — don't retry blindly
    AUTHENTICATION_FAILURE = "auth_failure"
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    RESOURCE_NOT_FOUND = "resource_not_found"
    
    # Unknown — log and escalate
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    """How critical the error is."""
    
    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Rich context for understanding failures."""
    
    agent_name: str = ""
    task_summary: str = ""
    step_number: int = 0
    session_tokens_used: int = 0
    session_queries_count: int = 0
    
    # For context overflow: what triggered the reset
    context_reset_reason: str = ""
    
    # For tool errors: what tool failed
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    
    # Custom context
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentError:
    """Structured representation of an agent failure.
    
    Use this instead of raw exception messages for better error handling,
    logging, and debugging.
    """
    
    error_type: ErrorType
    message: str
    retriable: bool  # Safe to retry?
    severity: ErrorSeverity = ErrorSeverity.ERROR
    context: ErrorContext = field(default_factory=ErrorContext)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Technical details for debugging
    exception_type: str = ""  # e.g., "TimeoutError"
    exception_traceback: str = ""  # Full traceback
    
    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        context: ErrorContext | None = None,
    ) -> AgentError:
        """Create structured error from a raw exception."""
        import traceback
        
        error_type = _classify_exception(exc)
        retriable = error_type in {
            ErrorType.TIMEOUT,
            ErrorType.RATE_LIMIT,
            ErrorType.TEMPORARY_API_FAILURE,
            ErrorType.NETWORK_ERROR,
            ErrorType.CONTEXT_OVERFLOW,
        }
        
        return cls(
            error_type=error_type,
            message=str(exc),
            retriable=retriable,
            severity=ErrorSeverity.ERROR,
            context=context or ErrorContext(),
            exception_type=type(exc).__name__,
            exception_traceback=traceback.format_exc(),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON logging."""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "retriable": self.retriable,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "exception_type": self.exception_type,
            "context": {
                "agent": self.context.agent_name,
                "task": self.context.task_summary,
                "step": self.context.step_number,
                "tokens_used": self.context.session_tokens_used,
                "queries": self.context.session_queries_count,
                **self.context.extra,
            },
        }


def _classify_exception(exc: Exception) -> ErrorType:
    """Classify an exception into an ErrorType."""
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()
    
    # Timeout
    if "timeout" in exc_type.lower() or "timed out" in exc_str:
        return ErrorType.TIMEOUT
    
    # Rate limiting
    if "rate" in exc_str or "429" in exc_str:
        return ErrorType.RATE_LIMIT
    
    # Network issues
    if any(x in exc_type.lower() for x in ["connection", "socket", "dns"]):
        return ErrorType.NETWORK_ERROR
    if "connection" in exc_str or "network" in exc_str:
        return ErrorType.NETWORK_ERROR
    
    # Authentication
    if any(x in exc_str for x in ["401", "403", "auth", "unauthorized", "forbidden"]):
        return ErrorType.AUTHENTICATION_FAILURE
    
    # Context/memory overflow
    if "context" in exc_str or "token" in exc_str and "limit" in exc_str:
        return ErrorType.CONTEXT_OVERFLOW
    
    # Tool execution
    if "tool" in exc_str.lower():
        return ErrorType.TOOL_EXECUTION_FAILURE
    
    # Invalid input
    if any(x in exc_type.lower() for x in ["value", "type", "attribute"]):
        return ErrorType.INVALID_INPUT
    
    return ErrorType.UNKNOWN


class RetryPolicy:
    """Strategy for retrying failed operations."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_s: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay_s: float = 30.0,
    ):
        self.max_retries = max_retries
        self.initial_delay_s = initial_delay_s
        self.backoff_multiplier = backoff_multiplier
        self.max_delay_s = max_delay_s
    
    def should_retry(self, error: AgentError, attempt: int) -> bool:
        """Decide if we should retry based on error type and attempt count."""
        if attempt >= self.max_retries:
            return False
        return error.retriable
    
    def get_delay_s(self, attempt: int) -> float:
        """Get delay before next retry (exponential backoff)."""
        delay = self.initial_delay_s * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_s)


# Default retry policies for different scenarios
DEFAULT_RETRY = RetryPolicy(max_retries=3, initial_delay_s=1.0)
AGGRESSIVE_RETRY = RetryPolicy(max_retries=5, initial_delay_s=0.5, backoff_multiplier=1.5)
NO_RETRY = RetryPolicy(max_retries=0)
