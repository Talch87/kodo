"""Metrics collection and tracking utilities for Kodo execution."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class Metric:
    """A single metric record."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TimerRecord:
    """A timer record for tracking execution duration."""
    name: str
    start_time: float
    end_time: Optional[float] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Get the duration in seconds, or None if timer not stopped."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time


class MetricsCollector:
    """Collects and tracks execution metrics for Kodo operations."""
    
    def __init__(self):
        """Initialize the metrics collector."""
        self.metrics: List[Metric] = []
        self.timers: Dict[str, TimerRecord] = {}
        self.counters: Dict[str, int] = {}
        self.created_at = datetime.now()
    
    def start_timer(self, name: str) -> None:
        """Start a named timer.
        
        Args:
            name: The name of the timer.
        
        Raises:
            ValueError: If a timer with this name is already running.
        """
        if name in self.timers and self.timers[name].end_time is None:
            raise ValueError(f"Timer '{name}' is already running")
        
        self.timers[name] = TimerRecord(
            name=name,
            start_time=time.time()
        )
    
    def end_timer(self, name: str) -> Optional[float]:
        """End a named timer and return its duration.
        
        Args:
            name: The name of the timer.
        
        Returns:
            The duration in seconds, or None if timer doesn't exist.
        
        Raises:
            ValueError: If the timer is not running.
        """
        if name not in self.timers:
            raise ValueError(f"Timer '{name}' does not exist")
        
        timer = self.timers[name]
        if timer.end_time is not None:
            raise ValueError(f"Timer '{name}' is not running")
        
        timer.end_time = time.time()
        return timer.duration
    
    def record_metric(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a metric value.
        
        Args:
            name: The name of the metric.
            value: The numeric value.
            tags: Optional dictionary of tags for the metric.
        """
        metric = Metric(
            name=name,
            value=value,
            tags=tags or {}
        )
        self.metrics.append(metric)
    
    def increment_counter(
        self,
        name: str,
        amount: int = 1
    ) -> int:
        """Increment a counter.
        
        Args:
            name: The name of the counter.
            amount: The amount to increment by (default: 1).
        
        Returns:
            The new counter value.
        """
        self.counters[name] = self.counters.get(name, 0) + amount
        return self.counters[name]
    
    def record_success(self) -> None:
        """Record a successful operation."""
        self.increment_counter("successes")
    
    def record_failure(self, error: Optional[str] = None) -> None:
        """Record a failed operation.
        
        Args:
            error: Optional error message.
        """
        self.increment_counter("failures")
        if error:
            self.record_metric("last_error", 1.0, {"error": error})
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all collected metrics.
        
        Returns:
            A dictionary containing:
            - counters: All counter values
            - timers: Timer durations (only for completed timers)
            - metrics: List of recorded metric values
            - created_at: When the collector was created
            - collected_at: When this summary was generated
        """
        timer_summary = {}
        for name, timer in self.timers.items():
            if timer.duration is not None:
                timer_summary[name] = timer.duration
        
        metrics_list = [
            {
                "name": m.name,
                "value": m.value,
                "timestamp": m.timestamp.isoformat(),
                "tags": m.tags
            }
            for m in self.metrics
        ]
        
        return {
            "counters": self.counters.copy(),
            "timers": timer_summary,
            "metrics": metrics_list,
            "created_at": self.created_at.isoformat(),
            "collected_at": datetime.now().isoformat(),
            "total_metrics_recorded": len(self.metrics),
            "total_counters": len(self.counters),
            "total_timers": len(self.timers)
        }
    
    def get_counter(self, name: str) -> int:
        """Get the current value of a counter.
        
        Args:
            name: The counter name.
        
        Returns:
            The counter value (0 if not found).
        """
        return self.counters.get(name, 0)
    
    def get_timer_duration(self, name: str) -> Optional[float]:
        """Get the duration of a completed timer.
        
        Args:
            name: The timer name.
        
        Returns:
            The duration in seconds, or None if timer not found or not completed.
        """
        if name not in self.timers:
            return None
        return self.timers[name].duration
    
    def reset(self) -> None:
        """Reset all collected metrics."""
        self.metrics.clear()
        self.timers.clear()
        self.counters.clear()
        self.created_at = datetime.now()
