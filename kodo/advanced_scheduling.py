"""
Phase 5: Advanced Scheduling System for Kodo

Implements:
1. Enhanced priority queue with custom scheduling policies
2. Resource constraint modeling and enforcement
3. Adaptive scheduling based on performance metrics
4. Scheduling policy language (DSL)
5. Cost vs performance tradeoff optimization
"""

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from abc import ABC, abstractmethod
import json
import logging

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    DEFERRED = 4


class ResourceType(Enum):
    """Types of resources that can be constrained"""
    CPU = "cpu"
    MEMORY = "memory"
    BANDWIDTH = "bandwidth"
    TOKENS = "tokens"
    API_CALLS = "api_calls"
    CONCURRENT_TASKS = "concurrent_tasks"


@dataclass
class ResourceRequest:
    """Represents resource requirements for a task"""
    cpu_cores: float = 0.1  # Fractional cores
    memory_mb: float = 256.0
    bandwidth_mbps: float = 1.0
    tokens: int = 1000
    api_calls: int = 1
    concurrent_slots: int = 1
    
    def scale(self, factor: float) -> "ResourceRequest":
        """Scale all resource requests by a factor"""
        return ResourceRequest(
            cpu_cores=self.cpu_cores * factor,
            memory_mb=self.memory_mb * factor,
            bandwidth_mbps=self.bandwidth_mbps * factor,
            tokens=int(self.tokens * factor),
            api_calls=int(self.api_calls * factor),
            concurrent_slots=max(1, int(self.concurrent_slots * factor))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "bandwidth_mbps": self.bandwidth_mbps,
            "tokens": self.tokens,
            "api_calls": self.api_calls,
            "concurrent_slots": self.concurrent_slots,
        }


@dataclass
class ResourceQuota:
    """Resource limits for a system or tenant"""
    max_cpu_cores: float = 100.0
    max_memory_mb: float = 10000.0
    max_bandwidth_mbps: float = 1000.0
    max_tokens_per_hour: int = 1_000_000
    max_api_calls_per_hour: int = 10000
    max_concurrent_tasks: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_cpu_cores": self.max_cpu_cores,
            "max_memory_mb": self.max_memory_mb,
            "max_bandwidth_mbps": self.max_bandwidth_mbps,
            "max_tokens_per_hour": self.max_tokens_per_hour,
            "max_api_calls_per_hour": self.max_api_calls_per_hour,
            "max_concurrent_tasks": self.max_concurrent_tasks,
        }


@dataclass
class ScheduledTask:
    """Represents a task in the scheduler"""
    task_id: str
    task_name: str
    priority: TaskPriority = TaskPriority.NORMAL
    resources: ResourceRequest = field(default_factory=ResourceRequest)
    deadline: Optional[datetime] = None
    estimated_cost: float = 0.0
    estimated_duration: float = 1.0  # seconds
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other: "ScheduledTask") -> bool:
        """Comparison for heap queue"""
        # Lower priority value = higher priority
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        
        # If same priority, earlier deadline wins
        if self.deadline and other.deadline:
            return self.deadline < other.deadline
        elif self.deadline:
            return True
        elif other.deadline:
            return False
        
        # Fall back to creation time (FIFO for same priority)
        return self.created_at < other.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "priority": self.priority.name,
            "resources": self.resources.to_dict(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "estimated_cost": self.estimated_cost,
            "estimated_duration": self.estimated_duration,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


@dataclass
class ResourceUsage:
    """Current resource usage tracking"""
    cpu_used: float = 0.0
    memory_used: float = 0.0
    bandwidth_used: float = 0.0
    tokens_used_this_hour: int = 0
    api_calls_this_hour: int = 0
    concurrent_tasks: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)
    
    def reset_hourly_if_needed(self):
        """Reset hourly quotas if an hour has passed"""
        now = datetime.utcnow()
        if (now - self.last_reset).total_seconds() >= 3600:
            self.tokens_used_this_hour = 0
            self.api_calls_this_hour = 0
            self.last_reset = now
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_used": self.cpu_used,
            "memory_used": self.memory_used,
            "bandwidth_used": self.bandwidth_used,
            "tokens_used_this_hour": self.tokens_used_this_hour,
            "api_calls_this_hour": self.api_calls_this_hour,
            "concurrent_tasks": self.concurrent_tasks,
            "last_reset": self.last_reset.isoformat(),
        }


class SchedulingPolicy(ABC):
    """Abstract base for scheduling policies"""
    
    @abstractmethod
    def score_task(self, task: ScheduledTask, resource_usage: ResourceUsage, 
                   quota: ResourceQuota) -> float:
        """Score a task for scheduling (higher = better to run now)"""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Policy name"""
        pass


class PriorityPolicy(SchedulingPolicy):
    """Simple priority-based scheduling"""
    
    def score_task(self, task: ScheduledTask, resource_usage: ResourceUsage,
                   quota: ResourceQuota) -> float:
        """Score based on priority level"""
        return -task.priority.value  # Negative priority for higher score
    
    def name(self) -> str:
        return "priority"


class DeadlinePolicy(SchedulingPolicy):
    """Earliest deadline first (EDF) scheduling"""
    
    def score_task(self, task: ScheduledTask, resource_usage: ResourceUsage,
                   quota: ResourceQuota) -> float:
        """Score based on urgency (how close to deadline)"""
        if not task.deadline:
            return 0.0
        
        now = datetime.utcnow()
        time_remaining = (task.deadline - now).total_seconds()
        
        if time_remaining <= 0:
            return 1000.0  # Critical urgency
        
        # Closer deadline = higher score
        return 1.0 / max(1.0, time_remaining)
    
    def name(self) -> str:
        return "deadline"


class CostOptimizationPolicy(SchedulingPolicy):
    """Optimize for cost while meeting deadlines"""
    
    def score_task(self, task: ScheduledTask, resource_usage: ResourceUsage,
                   quota: ResourceQuota) -> float:
        """Score based on cost-efficiency"""
        # Lower cost per duration = higher priority
        if task.estimated_duration <= 0:
            return 0.0
        
        cost_per_sec = task.estimated_cost / task.estimated_duration
        
        # Cheaper tasks get higher priority
        return -cost_per_sec
    
    def name(self) -> str:
        return "cost_optimization"


class AdaptivePolicy(SchedulingPolicy):
    """Adaptive policy that adjusts based on system metrics"""
    
    def __init__(self, history_window: int = 100):
        self.history_window = history_window
        self.task_history: List[Dict[str, Any]] = []
    
    def record_task_result(self, task_id: str, actual_cost: float,
                          actual_duration: float, success: bool):
        """Record task execution results for learning"""
        self.task_history.append({
            "task_id": task_id,
            "actual_cost": actual_cost,
            "actual_duration": actual_duration,
            "success": success,
            "timestamp": datetime.utcnow(),
        })
        
        # Keep only recent history
        if len(self.task_history) > self.history_window:
            self.task_history = self.task_history[-self.history_window:]
    
    def score_task(self, task: ScheduledTask, resource_usage: ResourceUsage,
                   quota: ResourceQuota) -> float:
        """Adaptive scoring based on historical performance"""
        # Start with priority
        score = -task.priority.value
        
        # Adjust for deadline urgency if present
        if task.deadline:
            now = datetime.utcnow()
            time_remaining = (task.deadline - now).total_seconds()
            if time_remaining > 0:
                score += 1.0 / (1.0 + time_remaining)
        
        # Adjust for resource availability
        cpu_headroom = (quota.max_cpu_cores - resource_usage.cpu_used) / quota.max_cpu_cores
        memory_headroom = (quota.max_memory_mb - resource_usage.memory_used) / quota.max_memory_mb
        
        # Higher headroom = higher score for resource-intensive tasks
        if task.resources.cpu_cores > 0:
            score += 0.1 * cpu_headroom
        if task.resources.memory_mb > 0:
            score += 0.1 * memory_headroom
        
        return score
    
    def name(self) -> str:
        return "adaptive"


class AdvancedScheduler:
    """
    Advanced task scheduler with:
    - Priority queue with multiple scheduling policies
    - Resource constraint enforcement
    - Adaptive scheduling based on metrics
    - Cost/performance optimization
    """
    
    def __init__(self, quota: Optional[ResourceQuota] = None,
                 default_policy: str = "adaptive"):
        self.quota = quota or ResourceQuota()
        self.resource_usage = ResourceUsage()
        self.task_queue: List[ScheduledTask] = []
        self.active_tasks: Dict[str, ScheduledTask] = {}
        self.completed_tasks: List[ScheduledTask] = []
        
        # Scheduling policies
        self.policies: Dict[str, SchedulingPolicy] = {
            "priority": PriorityPolicy(),
            "deadline": DeadlinePolicy(),
            "cost_optimization": CostOptimizationPolicy(),
            "adaptive": AdaptivePolicy(),
        }
        self.active_policy = self.policies.get(default_policy, self.policies["adaptive"])
        
        # Metrics
        self.total_tasks_scheduled = 0
        self.total_cost = 0.0
        self.scheduling_decisions: List[Dict[str, Any]] = []
    
    def enqueue_task(self, task: ScheduledTask) -> None:
        """Add a task to the scheduling queue"""
        task.scheduled_at = datetime.utcnow()
        heapq.heappush(self.task_queue, task)
        logger.info(f"Task enqueued: {task.task_id} (priority={task.priority.name})")
    
    def set_scheduling_policy(self, policy_name: str) -> None:
        """Switch to a different scheduling policy"""
        if policy_name not in self.policies:
            raise ValueError(f"Unknown policy: {policy_name}")
        
        self.active_policy = self.policies[policy_name]
        logger.info(f"Scheduling policy changed to: {policy_name}")
    
    def can_allocate_resources(self, task: ScheduledTask) -> bool:
        """Check if resources can be allocated for a task"""
        # Check instantaneous limits
        if (self.resource_usage.cpu_used + task.resources.cpu_cores
                > self.quota.max_cpu_cores):
            return False
        
        if (self.resource_usage.memory_used + task.resources.memory_mb
                > self.quota.max_memory_mb):
            return False
        
        if (self.resource_usage.concurrent_tasks + task.resources.concurrent_slots
                > self.quota.max_concurrent_tasks):
            return False
        
        # Check hourly limits
        self.resource_usage.reset_hourly_if_needed()
        
        if (self.resource_usage.tokens_used_this_hour + task.resources.tokens
                > self.quota.max_tokens_per_hour):
            return False
        
        if (self.resource_usage.api_calls_this_hour + task.resources.api_calls
                > self.quota.max_api_calls_per_hour):
            return False
        
        return True
    
    def allocate_resources(self, task: ScheduledTask) -> bool:
        """Allocate resources for a task"""
        if not self.can_allocate_resources(task):
            return False
        
        self.resource_usage.cpu_used += task.resources.cpu_cores
        self.resource_usage.memory_used += task.resources.memory_mb
        self.resource_usage.bandwidth_used += task.resources.bandwidth_mbps
        self.resource_usage.tokens_used_this_hour += task.resources.tokens
        self.resource_usage.api_calls_this_hour += task.resources.api_calls
        self.resource_usage.concurrent_tasks += task.resources.concurrent_slots
        
        return True
    
    def release_resources(self, task: ScheduledTask) -> None:
        """Release resources allocated to a task"""
        self.resource_usage.cpu_used = max(0, self.resource_usage.cpu_used - task.resources.cpu_cores)
        self.resource_usage.memory_used = max(0, self.resource_usage.memory_used - task.resources.memory_mb)
        self.resource_usage.bandwidth_used = max(0, self.resource_usage.bandwidth_used - task.resources.bandwidth_mbps)
        self.resource_usage.concurrent_tasks = max(0, self.resource_usage.concurrent_tasks - task.resources.concurrent_slots)
    
    def get_next_task(self) -> Optional[ScheduledTask]:
        """Get the next task to execute based on active policy"""
        # Remove completed/cancelled tasks
        while self.task_queue and self.task_queue[0] in self.completed_tasks:
            heapq.heappop(self.task_queue)
        
        if not self.task_queue:
            return None
        
        # Score all queued tasks and pick the best one that can be scheduled
        candidates = []
        for task in self.task_queue:
            score = self.active_policy.score_task(task, self.resource_usage, self.quota)
            if self.can_allocate_resources(task):
                candidates.append((score, task))
        
        if not candidates:
            return None
        
        # Sort by score (descending) and return the best
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    
    async def execute_task(self, task: ScheduledTask) -> Dict[str, Any]:
        """Execute a task with resource tracking"""
        if not self.allocate_resources(task):
            logger.warning(f"Failed to allocate resources for task: {task.task_id}")
            return {"success": False, "reason": "resource_allocation_failed"}
        
        task.started_at = datetime.utcnow()
        self.active_tasks[task.task_id] = task
        
        start_time = time.time()
        try:
            # Execute the task callback if provided
            if task.callback:
                result = task.callback()
                if asyncio.iscoroutine(result):
                    await result
            
            actual_duration = time.time() - start_time
            task.completed_at = datetime.utcnow()
            
            # Update metrics
            self.total_tasks_scheduled += 1
            self.total_cost += task.estimated_cost
            
            self.active_tasks.pop(task.task_id, None)
            self.completed_tasks.append(task)
            self.release_resources(task)
            
            # Record adaptive policy learning
            if isinstance(self.active_policy, AdaptivePolicy):
                self.active_policy.record_task_result(
                    task.task_id, task.estimated_cost, actual_duration, True
                )
            
            logger.info(f"Task completed: {task.task_id} (duration={actual_duration:.2f}s, cost={task.estimated_cost})")
            
            return {
                "success": True,
                "task_id": task.task_id,
                "actual_duration": actual_duration,
                "actual_cost": task.estimated_cost,
            }
        
        except Exception as e:
            logger.error(f"Task failed: {task.task_id}: {e}")
            
            self.active_tasks.pop(task.task_id, None)
            self.release_resources(task)
            
            # Record failure in adaptive policy
            if isinstance(self.active_policy, AdaptivePolicy):
                self.active_policy.record_task_result(
                    task.task_id, task.estimated_cost, 
                    (datetime.utcnow() - task.started_at).total_seconds(), False
                )
            
            return {
                "success": False,
                "task_id": task.task_id,
                "error": str(e),
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get scheduler metrics"""
        return {
            "total_tasks_scheduled": self.total_tasks_scheduled,
            "total_cost": self.total_cost,
            "queued_tasks": len(self.task_queue),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "current_policy": self.active_policy.name(),
            "resource_usage": self.resource_usage.to_dict(),
            "resource_quota": self.quota.to_dict(),
            "utilization": {
                "cpu": self.resource_usage.cpu_used / self.quota.max_cpu_cores,
                "memory": self.resource_usage.memory_used / self.quota.max_memory_mb,
                "concurrent": self.resource_usage.concurrent_tasks / self.quota.max_concurrent_tasks,
            }
        }
    
    def export_metrics(self, filepath: str) -> None:
        """Export scheduler metrics to JSON"""
        metrics = self.get_metrics()
        with open(filepath, 'w') as f:
            json.dump(metrics, f, indent=2, default=str)
        logger.info(f"Metrics exported to {filepath}")


# Example usage and DSL for scheduling policies
class SchedulingPolicyDSL:
    """Domain-specific language for defining custom scheduling policies"""
    
    @staticmethod
    def create_custom_policy(name: str, rule: Callable) -> SchedulingPolicy:
        """Create a custom scheduling policy from a scoring function"""
        
        class CustomPolicy(SchedulingPolicy):
            def score_task(self, task: ScheduledTask, usage: ResourceUsage, quota: ResourceQuota) -> float:
                return rule(task, usage, quota)
            
            def name(self) -> str:
                return name
        
        return CustomPolicy()
    
    @staticmethod
    def create_weighted_policy(name: str, weights: Dict[str, float]) -> SchedulingPolicy:
        """
        Create a weighted combination of scoring factors
        
        Example weights:
        {
            "priority": 0.4,
            "deadline_urgency": 0.3,
            "cost": 0.2,
            "resource_efficiency": 0.1
        }
        """
        
        class WeightedPolicy(SchedulingPolicy):
            def score_task(self, task: ScheduledTask, usage: ResourceUsage, quota: ResourceQuota) -> float:
                score = 0.0
                
                if weights.get("priority", 0) > 0:
                    priority_score = -task.priority.value
                    score += priority_score * weights["priority"]
                
                if weights.get("deadline_urgency", 0) > 0:
                    if task.deadline:
                        time_remaining = (task.deadline - datetime.utcnow()).total_seconds()
                        deadline_score = 1.0 / max(1.0, time_remaining) if time_remaining > 0 else 1000.0
                    else:
                        deadline_score = 0.0
                    score += deadline_score * weights["deadline_urgency"]
                
                if weights.get("cost", 0) > 0:
                    cost_score = -task.estimated_cost if task.estimated_cost > 0 else 0.0
                    score += cost_score * weights["cost"]
                
                if weights.get("resource_efficiency", 0) > 0:
                    cpu_headroom = (quota.max_cpu_cores - usage.cpu_used) / quota.max_cpu_cores
                    resource_score = cpu_headroom
                    score += resource_score * weights["resource_efficiency"]
                
                return score
            
            def name(self) -> str:
                return name
        
        return WeightedPolicy()
