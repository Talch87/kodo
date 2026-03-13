"""
Retry Strategy with Exponential Backoff

Implements configurable retry logic with exponential backoff for
handling transient failures gracefully.
"""

import time
import asyncio
import random
from enum import Enum
from typing import Callable, Any, Optional, TypeVar, Set, Type
from dataclasses import dataclass
from datetime import datetime

T = TypeVar('T')


class BackoffStrategy(Enum):
    """Backoff strategies for retries."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"
    RANDOM = "random"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 0.1  # seconds
    max_delay: float = 60.0     # seconds
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_factor: float = 2.0  # For exponential/linear backoff
    jitter: bool = True  # Add random jitter to delays
    retryable_exceptions: Set[Type[Exception]] = None
    
    def __post_init__(self):
        if self.retryable_exceptions is None:
            self.retryable_exceptions = {Exception}


@dataclass
class RetryMetrics:
    """Metrics for retry operations."""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    total_retries: int = 0
    total_delay: float = 0.0
    last_exception: Optional[Exception] = None
    last_retry_time: Optional[float] = None


class RetryStrategy:
    """Implements retry logic with exponential backoff."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.metrics = RetryMetrics()
        self._fibonacci_cache = self._build_fibonacci_cache()
    
    def _build_fibonacci_cache(self) -> list[int]:
        """Build Fibonacci sequence for use in backoff."""
        fib = [0, 1]
        for _ in range(20):  # Generate enough for reasonable max_attempts
            fib.append(fib[-1] + fib[-2])
        return fib
    
    def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from func
            
        Raises:
            RetryExhausted: If all retries fail
        """
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                self.metrics.total_attempts += 1
                result = func(*args, **kwargs)
                self.metrics.successful_attempts += 1
                return result
            except Exception as e:
                self.metrics.failed_attempts += 1
                self.metrics.last_exception = e
                last_exception = e
                
                if not self._is_retryable(e):
                    raise
                
                if attempt < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    self.metrics.total_retries += 1
                    self.metrics.total_delay += delay
                    self.metrics.last_retry_time = time.time()
                    time.sleep(delay)
        
        self.metrics.last_exception = last_exception
        raise RetryExhausted(
            f"Failed after {self.config.max_attempts} attempts. "
            f"Last error: {last_exception}"
        )
    
    async def execute_async(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Async version of execute()."""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                self.metrics.total_attempts += 1
                result = await func(*args, **kwargs)
                self.metrics.successful_attempts += 1
                return result
            except Exception as e:
                self.metrics.failed_attempts += 1
                self.metrics.last_exception = e
                last_exception = e
                
                if not self._is_retryable(e):
                    raise
                
                if attempt < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    self.metrics.total_retries += 1
                    self.metrics.total_delay += delay
                    self.metrics.last_retry_time = time.time()
                    await asyncio.sleep(delay)
        
        self.metrics.last_exception = last_exception
        raise RetryExhausted(
            f"Failed after {self.config.max_attempts} attempts. "
            f"Last error: {last_exception}"
        )
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        if self.config.backoff_strategy == BackoffStrategy.LINEAR:
            delay = self.config.initial_delay * attempt
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.config.initial_delay * (
                self.config.backoff_factor ** (attempt - 1)
            )
        elif self.config.backoff_strategy == BackoffStrategy.FIBONACCI:
            if attempt - 1 < len(self._fibonacci_cache):
                delay = self.config.initial_delay * self._fibonacci_cache[attempt - 1]
            else:
                delay = self.config.initial_delay * self._fibonacci_cache[-1]
        elif self.config.backoff_strategy == BackoffStrategy.RANDOM:
            delay = random.uniform(
                self.config.initial_delay,
                self.config.initial_delay * (self.config.backoff_factor ** (attempt - 1))
            )
        else:
            delay = self.config.initial_delay
        
        # Cap at max delay
        delay = min(delay, self.config.max_delay)
        
        # Add jitter if enabled
        if self.config.jitter:
            jitter = random.uniform(0, delay * 0.1)
            delay += jitter
        
        return delay
    
    def _is_retryable(self, exception: Exception) -> bool:
        """Check if exception is retryable."""
        return any(
            isinstance(exception, exc_type)
            for exc_type in self.config.retryable_exceptions
        )
    
    def get_metrics(self) -> dict:
        """Get retry metrics."""
        return {
            'total_attempts': self.metrics.total_attempts,
            'successful_attempts': self.metrics.successful_attempts,
            'failed_attempts': self.metrics.failed_attempts,
            'total_retries': self.metrics.total_retries,
            'total_delay': self.metrics.total_delay,
            'average_delay': (
                self.metrics.total_delay / self.metrics.total_retries
                if self.metrics.total_retries > 0 else 0
            ),
            'last_exception': str(self.metrics.last_exception),
        }
    
    def reset(self):
        """Reset metrics."""
        self.metrics = RetryMetrics()


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""
    pass
