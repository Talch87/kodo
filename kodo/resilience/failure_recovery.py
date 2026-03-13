"""
Failure Recovery Procedures

Implements automatic recovery from failures, including detection,
diagnosis, and remediation strategies.
"""

from enum import Enum
from typing import Callable, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time


class FailureType(Enum):
    """Types of failures that can be detected and recovered."""
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    DATA_CORRUPTION = "data_corruption"
    STATE_INCONSISTENCY = "state_inconsistency"
    DEADLOCK = "deadlock"
    MEMORY_LEAK = "memory_leak"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Strategies for recovering from failures."""
    RETRY = "retry"
    FALLBACK = "fallback"
    RESET = "reset"
    ESCALATE = "escalate"
    ROLLBACK = "rollback"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"


@dataclass
class FailureEvent:
    """Represents a detected failure."""
    failure_type: FailureType
    timestamp: float = field(default_factory=time.time)
    component: str = ""
    message: str = ""
    severity: int = 1  # 1=low, 5=critical
    context: dict = field(default_factory=dict)
    recoverable: bool = True
    
    def age_seconds(self) -> float:
        """Get age of failure in seconds."""
        return time.time() - self.timestamp
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'failure_type': self.failure_type.value,
            'timestamp': datetime.fromtimestamp(self.timestamp).isoformat(),
            'component': self.component,
            'message': self.message,
            'severity': self.severity,
            'context': self.context,
            'recoverable': self.recoverable,
            'age_seconds': self.age_seconds(),
        }


@dataclass
class RecoveryAction:
    """Represents a recovery action to be taken."""
    strategy: RecoveryStrategy
    target_component: str
    parameters: dict = field(default_factory=dict)
    handler: Optional[Callable] = field(default=None)
    timeout: int = 30  # seconds
    
    async def execute(self) -> bool:
        """Execute the recovery action."""
        if self.handler is None:
            return False
        
        try:
            result = self.handler(self.target_component, self.parameters)
            return result if result is not None else True
        except Exception as e:
            print(f"Recovery action failed: {e}")
            return False


class FailureDetector:
    """Detects various types of failures."""
    
    def __init__(self):
        self.failures: List[FailureEvent] = []
        self.failure_handlers = {}
    
    def detect_timeout(self, component: str, timeout_seconds: float) -> Optional[FailureEvent]:
        """Detect timeout failure."""
        failure = FailureEvent(
            failure_type=FailureType.TIMEOUT,
            component=component,
            message=f"Operation exceeded {timeout_seconds}s timeout",
            severity=3,
            recoverable=True,
        )
        self.failures.append(failure)
        return failure
    
    def detect_resource_exhaustion(self, component: str, resource_type: str) -> Optional[FailureEvent]:
        """Detect resource exhaustion."""
        failure = FailureEvent(
            failure_type=FailureType.RESOURCE_EXHAUSTION,
            component=component,
            message=f"{resource_type} exhausted",
            severity=4,
            recoverable=True,
            context={'resource_type': resource_type},
        )
        self.failures.append(failure)
        return failure
    
    def detect_dependency_failure(self, component: str, dependency: str) -> Optional[FailureEvent]:
        """Detect dependency failure."""
        failure = FailureEvent(
            failure_type=FailureType.DEPENDENCY_FAILURE,
            component=component,
            message=f"Dependency '{dependency}' unavailable",
            severity=3,
            recoverable=True,
            context={'dependency': dependency},
        )
        self.failures.append(failure)
        return failure
    
    def detect_state_inconsistency(self, component: str, expected: str, actual: str) -> Optional[FailureEvent]:
        """Detect state inconsistency."""
        failure = FailureEvent(
            failure_type=FailureType.STATE_INCONSISTENCY,
            component=component,
            message=f"State mismatch: expected {expected}, got {actual}",
            severity=4,
            recoverable=True,
            context={'expected': expected, 'actual': actual},
        )
        self.failures.append(failure)
        return failure
    
    def detect_deadlock(self, component: str, waiting_on: List[str]) -> Optional[FailureEvent]:
        """Detect potential deadlock."""
        failure = FailureEvent(
            failure_type=FailureType.DEADLOCK,
            component=component,
            message=f"Potential deadlock detected. Waiting on: {waiting_on}",
            severity=5,  # Critical
            recoverable=True,
            context={'waiting_on': waiting_on},
        )
        self.failures.append(failure)
        return failure
    
    def get_recent_failures(self, minutes: int = 5) -> List[FailureEvent]:
        """Get failures from the last N minutes."""
        cutoff_time = time.time() - (minutes * 60)
        return [f for f in self.failures if f.timestamp >= cutoff_time]
    
    def get_failures_by_component(self, component: str) -> List[FailureEvent]:
        """Get all failures for a component."""
        return [f for f in self.failures if f.component == component]
    
    def get_metrics(self) -> dict:
        """Get failure detection metrics."""
        recent = self.get_recent_failures(5)
        by_type = {}
        for failure in self.failures:
            ft = failure.failure_type.value
            by_type[ft] = by_type.get(ft, 0) + 1
        
        return {
            'total_failures': len(self.failures),
            'recent_failures_5m': len(recent),
            'failures_by_type': by_type,
            'critical_failures': sum(1 for f in self.failures if f.severity >= 4),
        }


class RecoveryManager:
    """Manages failure recovery."""
    
    def __init__(self):
        self.detector = FailureDetector()
        self.recovery_actions: List[RecoveryAction] = []
        self.strategies: dict[FailureType, List[RecoveryStrategy]] = {
            FailureType.TIMEOUT: [RecoveryStrategy.RETRY, RecoveryStrategy.FALLBACK],
            FailureType.RESOURCE_EXHAUSTION: [RecoveryStrategy.RESET, RecoveryStrategy.GRACEFUL_SHUTDOWN],
            FailureType.DEPENDENCY_FAILURE: [RecoveryStrategy.FALLBACK, RecoveryStrategy.RETRY],
            FailureType.STATE_INCONSISTENCY: [RecoveryStrategy.ROLLBACK, RecoveryStrategy.RESET],
            FailureType.DEADLOCK: [RecoveryStrategy.RESET, RecoveryStrategy.ESCALATE],
        }
    
    def register_recovery_handler(
        self,
        strategy: RecoveryStrategy,
        component: str,
        handler: Callable,
    ):
        """Register a handler for a specific recovery strategy."""
        self.recovery_actions.append(
            RecoveryAction(
                strategy=strategy,
                target_component=component,
                handler=handler,
            )
        )
    
    def get_recommended_recovery(self, failure: FailureEvent) -> List[RecoveryAction]:
        """Get recommended recovery actions for a failure."""
        strategies = self.strategies.get(failure.failure_type, [RecoveryStrategy.ESCALATE])
        
        actions = []
        for strategy in strategies:
            # Find registered handlers for this strategy and component
            matching = [
                action for action in self.recovery_actions
                if action.strategy == strategy and action.target_component == failure.component
            ]
            actions.extend(matching)
        
        return actions
    
    def can_recover(self, failure: FailureEvent) -> bool:
        """Check if a failure can be automatically recovered."""
        if not failure.recoverable:
            return False
        
        actions = self.get_recommended_recovery(failure)
        return len(actions) > 0
    
    def get_metrics(self) -> dict:
        """Get recovery metrics."""
        return {
            'detector_metrics': self.detector.get_metrics(),
            'registered_handlers': len(self.recovery_actions),
        }


class StateSnapshot:
    """Captures system state for rollback."""
    
    def __init__(self, component: str, state: dict):
        self.component = component
        self.state = state.copy()
        self.timestamp = time.time()
    
    def restore(self) -> dict:
        """Get the snapshot state."""
        return self.state.copy()


class RollbackManager:
    """Manages rollback operations."""
    
    def __init__(self):
        self.snapshots: dict[str, List[StateSnapshot]] = {}
    
    def create_snapshot(self, component: str, state: dict) -> StateSnapshot:
        """Create a state snapshot."""
        snapshot = StateSnapshot(component, state)
        if component not in self.snapshots:
            self.snapshots[component] = []
        self.snapshots[component].append(snapshot)
        return snapshot
    
    def rollback(self, component: str, target_time: Optional[float] = None) -> Optional[dict]:
        """
        Rollback to previous state.
        
        Args:
            component: Component to rollback
            target_time: Rollback to state before this timestamp (None = last)
        
        Returns:
            Previous state or None if no snapshots available
        """
        if component not in self.snapshots or not self.snapshots[component]:
            return None
        
        snapshots = self.snapshots[component]
        
        if target_time is None:
            # Rollback to last snapshot
            if len(snapshots) > 1:
                return snapshots[-2].restore()
            return None
        
        # Find snapshot before target time
        for snapshot in reversed(snapshots):
            if snapshot.timestamp < target_time:
                return snapshot.restore()
        
        return None
    
    def get_snapshot_history(self, component: str) -> List[dict]:
        """Get snapshot history for a component."""
        if component not in self.snapshots:
            return []
        
        return [
            {
                'timestamp': datetime.fromtimestamp(s.timestamp).isoformat(),
                'age_seconds': time.time() - s.timestamp,
            }
            for s in self.snapshots[component]
        ]
