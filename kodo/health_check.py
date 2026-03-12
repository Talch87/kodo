"""Health check and status monitoring for Kodo."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentStatus(str, Enum):
    """Component status."""
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: ComponentStatus
    last_check: str
    response_time_ms: float
    error: Optional[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


@dataclass
class SystemHealth:
    """Overall system health status."""
    timestamp: str
    status: HealthStatus
    components: Dict[str, ComponentHealth]
    uptime_hours: float
    request_count: int
    error_count: int
    avg_latency_ms: float
    memory_usage_percent: float


class HealthChecker:
    """Monitor and report system health."""
    
    def __init__(self):
        self.components: Dict[str, ComponentHealth] = {}
        self.start_time = datetime.now()
        self.request_count = 0
        self.error_count = 0
        self.latencies: List[float] = []
    
    def register_component(self, name: str) -> None:
        """Register a component for health monitoring."""
        self.components[name] = ComponentHealth(
            name=name,
            status=ComponentStatus.UP,
            last_check=datetime.now().isoformat(),
            response_time_ms=0,
        )
    
    def update_component_status(
        self,
        name: str,
        status: ComponentStatus,
        response_time_ms: float,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update component health status."""
        if name not in self.components:
            self.register_component(name)
        
        self.components[name] = ComponentHealth(
            name=name,
            status=status,
            last_check=datetime.now().isoformat(),
            response_time_ms=response_time_ms,
            error=error,
            details=details,
        )
    
    def record_request(self, latency_ms: float, success: bool) -> None:
        """Record a request."""
        self.request_count += 1
        self.latencies.append(latency_ms)
        if not success:
            self.error_count += 1
        
        # Keep only recent latencies for memory efficiency
        if len(self.latencies) > 10000:
            self.latencies = self.latencies[-5000:]
    
    def get_system_health(self) -> SystemHealth:
        """Get overall system health."""
        # Calculate status
        down_count = sum(
            1 for c in self.components.values()
            if c.status == ComponentStatus.DOWN
        )
        degraded_count = sum(
            1 for c in self.components.values()
            if c.status == ComponentStatus.DEGRADED
        )
        
        if down_count > 0:
            status = HealthStatus.UNHEALTHY
        elif degraded_count > len(self.components) * 0.25:  # >25% degraded
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        
        # Calculate metrics
        uptime = (datetime.now() - self.start_time).total_seconds() / 3600
        avg_latency = (
            sum(self.latencies) / len(self.latencies)
            if self.latencies
            else 0
        )
        
        # Note: memory usage would need psutil in real implementation
        memory_usage = 0
        
        return SystemHealth(
            timestamp=datetime.now().isoformat(),
            status=status,
            components=self.components,
            uptime_hours=uptime,
            request_count=self.request_count,
            error_count=self.error_count,
            avg_latency_ms=avg_latency,
            memory_usage_percent=memory_usage,
        )
    
    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        health = self.get_system_health()
        return health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
    
    def get_error_rate(self) -> float:
        """Get error rate as percentage."""
        if self.request_count == 0:
            return 0
        return (self.error_count / self.request_count) * 100
    
    def get_health_summary(self) -> str:
        """Get a human-readable health summary."""
        health = self.get_system_health()
        error_rate = self.get_error_rate()
        
        lines = [
            "KODO HEALTH CHECK",
            f"Status: {health.status.value.upper()}",
            f"Timestamp: {health.timestamp}",
            f"Uptime: {health.uptime_hours:.1f} hours",
            f"Requests: {health.request_count}",
            f"Errors: {health.error_count} ({error_rate:.1f}%)",
            f"Avg Latency: {health.avg_latency_ms:.1f}ms",
            "",
            "Components:",
        ]
        
        for name, component in sorted(self.components.items()):
            status_symbol = {
                ComponentStatus.UP: "✓",
                ComponentStatus.DEGRADED: "⚠",
                ComponentStatus.DOWN: "✗",
            }[component.status]
            
            lines.append(
                f"  {status_symbol} {name}: {component.status.value} "
                f"({component.response_time_ms:.1f}ms)"
            )
            if component.error:
                lines.append(f"    Error: {component.error}")
        
        return "\n".join(lines)


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the global health checker."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
