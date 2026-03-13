"""
Kodo Resilience Module

Provides resilience patterns for agent orchestration:
- Circuit Breaker: Prevents cascading failures
- Retry Strategy: Handles transient failures with backoff
- Failure Recovery: Automatic detection and recovery
- Deadlock Detection: Identifies and prevents deadlocks
"""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitState,
)

from .retry_strategy import (
    RetryStrategy,
    RetryConfig,
    BackoffStrategy,
    RetryExhausted,
)

from .failure_recovery import (
    FailureDetector,
    RecoveryManager,
    RollbackManager,
    FailureEvent,
    FailureType,
    RecoveryStrategy,
    RecoveryAction,
    StateSnapshot,
)

from .deadlock_detection import (
    DeadlockDetector,
    DeadlockPrevention,
    DeadlockAvoidanceMonitor,
    ResourceType,
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitBreakerConfig",
    "CircuitBreakerOpen",
    "CircuitState",
    # Retry
    "RetryStrategy",
    "RetryConfig",
    "BackoffStrategy",
    "RetryExhausted",
    # Failure Recovery
    "FailureDetector",
    "RecoveryManager",
    "RollbackManager",
    "FailureEvent",
    "FailureType",
    "RecoveryStrategy",
    "RecoveryAction",
    "StateSnapshot",
    # Deadlock Detection
    "DeadlockDetector",
    "DeadlockPrevention",
    "DeadlockAvoidanceMonitor",
    "ResourceType",
]
