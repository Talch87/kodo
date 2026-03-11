"""Performance Profiler - Measure and track orchestration latency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import time
from functools import wraps
from pathlib import Path
import json


@dataclass
class PerformanceMetric:
    """Single performance measurement."""
    component: str
    operation: str
    duration_ms: float
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class PerformanceProfiler:
    """Collect and analyze performance metrics."""
    
    def __init__(self, metrics_log: Path = Path(".kodo/performance_metrics.jsonl")):
        self.metrics_log = metrics_log
        self.metrics_log.parent.mkdir(parents=True, exist_ok=True)
        
        self.metrics: List[PerformanceMetric] = []
        self.operation_times: Dict[str, List[float]] = {}
    
    def record(
        self,
        component: str,
        operation: str,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            component=component,
            operation=operation,
            duration_ms=duration_ms,
            tags=tags or {},
        )
        
        self.metrics.append(metric)
        
        # Track operation times for statistics
        key = f"{component}.{operation}"
        if key not in self.operation_times:
            self.operation_times[key] = []
        self.operation_times[key].append(duration_ms)
        
        # Log to file
        self._log_metric(metric)
    
    def measure(
        self,
        component: str,
        operation: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        """Context manager for measuring operation duration."""
        class Timer:
            def __init__(self, profiler, comp, op, tags):
                self.profiler = profiler
                self.component = comp
                self.operation = op
                self.tags = tags or {}
                self.start = None
            
            def __enter__(self):
                self.start = time.time()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = (time.time() - self.start) * 1000  # Convert to ms
                self.profiler.record(
                    self.component,
                    self.operation,
                    duration,
                    self.tags,
                )
        
        return Timer(self, component, operation, tags)
    
    def measure_async(
        self,
        component: str,
        operation: str,
    ):
        """Decorator for measuring async function duration."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs) -> Any:
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration = (time.time() - start) * 1000
                    self.record(component, operation, duration)
            return wrapper
        return decorator
    
    def get_statistics(self, component: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for recorded operations."""
        stats = {}
        
        for key, times in self.operation_times.items():
            comp, op = key.rsplit(".", 1)
            
            if component and comp != component:
                continue
            
            stats[key] = {
                "count": len(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "avg_ms": sum(times) / len(times),
                "median_ms": sorted(times)[len(times) // 2],
                "p95_ms": sorted(times)[int(len(times) * 0.95)],
                "p99_ms": sorted(times)[int(len(times) * 0.99)],
                "total_ms": sum(times),
            }
        
        return stats
    
    def get_slowest_operations(self, n: int = 10) -> List[tuple]:
        """Get the n slowest operations."""
        stats = self.get_statistics()
        
        # Sort by average time
        sorted_ops = sorted(
            stats.items(),
            key=lambda x: x[1]["avg_ms"],
            reverse=True,
        )
        
        return sorted_ops[:n]
    
    def generate_report(self) -> str:
        """Generate a performance report."""
        stats = self.get_statistics()
        slowest = self.get_slowest_operations()
        
        lines = [
            "# Performance Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            f"Total metrics recorded: {len(self.metrics)}",
            f"Unique operations: {len(stats)}",
            "",
            "## Slowest Operations (by average time)",
            ""
        ]
        
        for i, (op, data) in enumerate(slowest, 1):
            lines.append(f"{i}. {op}")
            lines.append(f"   - Count: {data['count']}")
            lines.append(f"   - Avg: {data['avg_ms']:.2f}ms")
            lines.append(f"   - Min: {data['min_ms']:.2f}ms")
            lines.append(f"   - Max: {data['max_ms']:.2f}ms")
            lines.append(f"   - P95: {data['p95_ms']:.2f}ms")
            lines.append(f"   - Total: {data['total_ms']:.2f}ms")
        
        lines.extend([
            "",
            "## All Operations",
            ""
        ])
        
        for op, data in sorted(stats.items()):
            lines.append(f"- {op}: {data['avg_ms']:.2f}ms (n={data['count']})")
        
        return "\n".join(lines)
    
    def _log_metric(self, metric: PerformanceMetric) -> None:
        """Log metric to file."""
        with open(self.metrics_log, "a") as f:
            data = {
                "component": metric.component,
                "operation": metric.operation,
                "duration_ms": metric.duration_ms,
                "timestamp": metric.timestamp,
                "tags": metric.tags,
            }
            f.write(json.dumps(data) + "\n")


# Global profiler instance
_profiler: Optional[PerformanceProfiler] = None


def get_profiler() -> PerformanceProfiler:
    """Get or create the global profiler."""
    global _profiler
    if _profiler is None:
        _profiler = PerformanceProfiler()
    return _profiler
