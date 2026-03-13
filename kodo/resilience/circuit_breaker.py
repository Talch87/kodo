"""
Circuit Breaker Pattern Implementation

Protects against cascading failures by monitoring success/failure rates
and temporarily disabling calls when failure threshold is exceeded.
"""

import time
from enum import Enum
from typing import Callable, Any, TypeVar, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
from threading import Lock

T = TypeVar('T')


class CircuitState(Enum):
    """States of the circuit breaker."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: int = 60  # Seconds before attempting recovery
    success_threshold: int = 2  # Successes in half-open before closing
    window_size: int = 100  # Number of recent calls to track


@dataclass
class CircuitBreakerMetrics:
    """Metrics tracked by circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    consecutive_failures: int = 0
    state_changes: int = 0
    state_change_times: list = field(default_factory=list)
    
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.
    
    States:
    - CLOSED: Normal operation, all calls allowed
    - OPEN: Too many failures, all calls rejected
    - HALF_OPEN: Testing if service recovered, limited calls allowed
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self._lock = Lock()
        self._opened_at: Optional[float] = None
        self._half_open_successes = 0
        
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute a function through the circuit breaker.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        with self._lock:
            if self.state == CircuitState.OPEN:
                # Check if we should transition to half-open
                if self._should_attempt_recovery():
                    self._transition_to_half_open()
                else:
                    self.metrics.rejected_calls += 1
                    raise CircuitBreakerOpen(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service temporarily unavailable."
                    )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    async def call_async(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Async version of call()."""
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._transition_to_half_open()
                else:
                    self.metrics.rejected_calls += 1
                    raise CircuitBreakerOpen(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service temporarily unavailable."
                    )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.successful_calls += 1
            self.metrics.consecutive_failures = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.success_threshold:
                    self._transition_to_closed()
    
    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.failed_calls += 1
            self.metrics.last_failure_time = time.time()
            self.metrics.consecutive_failures += 1
            
            if self.state == CircuitState.HALF_OPEN:
                # Failure in half-open state, go back to open
                self._transition_to_open()
            elif self.metrics.consecutive_failures >= self.config.failure_threshold:
                self._transition_to_open()
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._opened_at is None:
            return False
        elapsed = time.time() - self._opened_at
        return elapsed >= self.config.recovery_timeout
    
    def _transition_to_open(self):
        """Transition to OPEN state."""
        if self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            self._opened_at = time.time()
            self.metrics.state_changes += 1
            self.metrics.state_change_times.append({
                'timestamp': datetime.now().isoformat(),
                'new_state': self.state.value
            })
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self._half_open_successes = 0
        self.metrics.state_changes += 1
        self.metrics.state_change_times.append({
            'timestamp': datetime.now().isoformat(),
            'new_state': self.state.value
        })
    
    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self._opened_at = None
        self._half_open_successes = 0
        self.metrics.consecutive_failures = 0
        self.metrics.state_changes += 1
        self.metrics.state_change_times.append({
            'timestamp': datetime.now().isoformat(),
            'new_state': self.state.value
        })
    
    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value
    
    def get_metrics(self) -> dict:
        """Get circuit breaker metrics."""
        with self._lock:
            return {
                'name': self.name,
                'state': self.state.value,
                'total_calls': self.metrics.total_calls,
                'successful_calls': self.metrics.successful_calls,
                'failed_calls': self.metrics.failed_calls,
                'rejected_calls': self.metrics.rejected_calls,
                'success_rate': self.metrics.success_rate(),
                'consecutive_failures': self.metrics.consecutive_failures,
                'last_failure_time': self.metrics.last_failure_time,
                'state_changes': self.metrics.state_changes,
            }
    
    def reset(self):
        """Reset circuit breaker to closed state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.metrics = CircuitBreakerMetrics()
            self._opened_at = None
            self._half_open_successes = 0


class CircuitBreakerRegistry:
    """Manages multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = Lock()
    
    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)
    
    def get_all_metrics(self) -> dict:
        """Get metrics for all circuit breakers."""
        return {
            name: breaker.get_metrics()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
