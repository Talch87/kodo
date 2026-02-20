"""Timeout protection for all operations."""
import signal
from functools import wraps
from typing import Callable

def timeout_handler(seconds: int) -> Callable:
    """Decorator to add timeout to functions."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, timeout_error)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator

def timeout_error(signum, frame):
    """Handle timeout."""
    raise TimeoutError("Operation timed out")

@timeout_handler(5)
def safe_operation():
    """Example safe operation with timeout."""
    return "Completed safely"
