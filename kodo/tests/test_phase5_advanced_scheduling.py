"""
Phase 5: Advanced Scheduling - Comprehensive Test Suite

Tests for:
1. Priority queue with custom policies
2. Resource constraint enforcement
3. Adaptive scheduling
4. Cost/performance optimization
5. Scheduling policy DSL
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from kodo.advanced_scheduling import (
    TaskPriority,
    ResourceType,
    ResourceRequest,
    ResourceQuota,
    ScheduledTask,
    ResourceUsage,
    SchedulingPolicy,
    PriorityPolicy,
    DeadlinePolicy,
    CostOptimizationPolicy,
    AdaptivePolicy,
    AdvancedScheduler,
    SchedulingPolicyDSL,
)


# ============================================================================
# Tests: ResourceRequest
# ============================================================================

class TestResourceRequest:
    """Tests for ResourceRequest"""
    
    def test_create_resource_request(self):
        """Test creating a resource request"""
        req = ResourceRequest(
            cpu_cores=2.0,
            memory_mb=512.0,
            tokens=5000,
            api_calls=10
        )
        
        assert req.cpu_cores == 2.0
        assert req.memory_mb == 512.0
        assert req.tokens == 5000
        assert req.api_calls == 10
    
    def test_scale_resource_request(self):
        """Test scaling a resource request"""
        req = ResourceRequest(cpu_cores=2.0, memory_mb=512.0, tokens=1000)
        scaled = req.scale(2.0)
        
        assert scaled.cpu_cores == 4.0
        assert scaled.memory_mb == 1024.0
        assert scaled.tokens == 2000
    
    def test_resource_request_to_dict(self):
        """Test converting resource request to dict"""
        req = ResourceRequest(cpu_cores=1.0, memory_mb=256.0)
        data = req.to_dict()
        
        assert data["cpu_cores"] == 1.0
        assert data["memory_mb"] == 256.0
        assert "tokens" in data


# ============================================================================
# Tests: ResourceQuota
# ============================================================================

class TestResourceQuota:
    """Tests for ResourceQuota"""
    
    def test_create_quota(self):
        """Test creating a resource quota"""
        quota = ResourceQuota(
            max_cpu_cores=50.0,
            max_memory_mb=5000.0,
            max_concurrent_tasks=50
        )
        
        assert quota.max_cpu_cores == 50.0
        assert quota.max_concurrent_tasks == 50
    
    def test_quota_to_dict(self):
        """Test converting quota to dict"""
        quota = ResourceQuota()
        data = quota.to_dict()
        
        assert "max_cpu_cores" in data
        assert "max_memory_mb" in data
        assert "max_tokens_per_hour" in data


# ============================================================================
# Tests: ScheduledTask
# ============================================================================

class TestScheduledTask:
    """Tests for ScheduledTask"""
    
    def test_create_task(self):
        """Test creating a scheduled task"""
        task = ScheduledTask(
            task_id="task-1",
            task_name="Test Task",
            priority=TaskPriority.HIGH,
            estimated_cost=1.5
        )
        
        assert task.task_id == "task-1"
        assert task.priority == TaskPriority.HIGH
        assert task.estimated_cost == 1.5
    
    def test_task_comparison(self):
        """Test task comparison for priority"""
        high_task = ScheduledTask(
            task_id="high",
            task_name="High Priority",
            priority=TaskPriority.HIGH
        )
        normal_task = ScheduledTask(
            task_id="normal",
            task_name="Normal Priority",
            priority=TaskPriority.NORMAL
        )
        
        assert high_task < normal_task
    
    def test_task_deadline_comparison(self):
        """Test task comparison with deadlines"""
        now = datetime.utcnow()
        soon = ScheduledTask(
            task_id="soon",
            task_name="Soon",
            priority=TaskPriority.NORMAL,
            deadline=now + timedelta(seconds=60)
        )
        later = ScheduledTask(
            task_id="later",
            task_name="Later",
            priority=TaskPriority.NORMAL,
            deadline=now + timedelta(seconds=300)
        )
        
        assert soon < later
    
    def test_task_to_dict(self):
        """Test converting task to dict"""
        task = ScheduledTask(
            task_id="task-1",
            task_name="Test Task"
        )
        data = task.to_dict()
        
        assert data["task_id"] == "task-1"
        assert data["task_name"] == "Test Task"
        assert data["priority"] == "NORMAL"


# ============================================================================
# Tests: ResourceUsage
# ============================================================================

class TestResourceUsage:
    """Tests for ResourceUsage"""
    
    def test_create_usage(self):
        """Test creating resource usage tracker"""
        usage = ResourceUsage()
        
        assert usage.cpu_used == 0.0
        assert usage.memory_used == 0.0
        assert usage.concurrent_tasks == 0
    
    def test_hourly_reset(self):
        """Test hourly quota reset"""
        usage = ResourceUsage()
        usage.tokens_used_this_hour = 50000
        usage.api_calls_this_hour = 100
        
        # Manually set last_reset to > 1 hour ago
        import time
        usage.last_reset = datetime.utcnow() - timedelta(hours=2)
        
        usage.reset_hourly_if_needed()
        
        assert usage.tokens_used_this_hour == 0
        assert usage.api_calls_this_hour == 0
    
    def test_usage_to_dict(self):
        """Test converting usage to dict"""
        usage = ResourceUsage(cpu_used=10.0, memory_used=2048.0)
        data = usage.to_dict()
        
        assert data["cpu_used"] == 10.0
        assert data["memory_used"] == 2048.0


# ============================================================================
# Tests: SchedulingPolicies
# ============================================================================

class TestSchedulingPolicies:
    """Tests for different scheduling policies"""
    
    def test_priority_policy(self):
        """Test priority-based scheduling policy"""
        policy = PriorityPolicy()
        
        high_task = ScheduledTask(
            task_id="high",
            task_name="High",
            priority=TaskPriority.HIGH
        )
        low_task = ScheduledTask(
            task_id="low",
            task_name="Low",
            priority=TaskPriority.LOW
        )
        
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        high_score = policy.score_task(high_task, usage, quota)
        low_score = policy.score_task(low_task, usage, quota)
        
        assert high_score > low_score
        assert policy.name() == "priority"
    
    def test_deadline_policy(self):
        """Test deadline-based (EDF) scheduling policy"""
        policy = DeadlinePolicy()
        
        now = datetime.utcnow()
        urgent = ScheduledTask(
            task_id="urgent",
            task_name="Urgent",
            deadline=now + timedelta(seconds=10)
        )
        less_urgent = ScheduledTask(
            task_id="less_urgent",
            task_name="Less Urgent",
            deadline=now + timedelta(seconds=100)
        )
        
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        urgent_score = policy.score_task(urgent, usage, quota)
        less_urgent_score = policy.score_task(less_urgent, usage, quota)
        
        assert urgent_score > less_urgent_score
        assert policy.name() == "deadline"
    
    def test_cost_optimization_policy(self):
        """Test cost optimization policy"""
        policy = CostOptimizationPolicy()
        
        cheap_task = ScheduledTask(
            task_id="cheap",
            task_name="Cheap",
            estimated_cost=0.1,
            estimated_duration=1.0
        )
        expensive_task = ScheduledTask(
            task_id="expensive",
            task_name="Expensive",
            estimated_cost=10.0,
            estimated_duration=1.0
        )
        
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        cheap_score = policy.score_task(cheap_task, usage, quota)
        expensive_score = policy.score_task(expensive_task, usage, quota)
        
        assert cheap_score > expensive_score
        assert policy.name() == "cost_optimization"
    
    def test_adaptive_policy(self):
        """Test adaptive scheduling policy"""
        policy = AdaptivePolicy()
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            priority=TaskPriority.NORMAL
        )
        
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        score = policy.score_task(task, usage, quota)
        assert isinstance(score, float)
        assert policy.name() == "adaptive"
    
    def test_adaptive_policy_records_history(self):
        """Test adaptive policy records task results"""
        policy = AdaptivePolicy()
        
        policy.record_task_result("task-1", 1.5, 2.0, True)
        policy.record_task_result("task-2", 2.5, 3.0, False)
        
        assert len(policy.task_history) == 2
        assert policy.task_history[0]["actual_cost"] == 1.5
        assert policy.task_history[1]["success"] == False


# ============================================================================
# Tests: AdvancedScheduler
# ============================================================================

class TestAdvancedScheduler:
    """Tests for the AdvancedScheduler"""
    
    def test_create_scheduler(self):
        """Test creating an advanced scheduler"""
        scheduler = AdvancedScheduler()
        
        assert scheduler.total_tasks_scheduled == 0
        assert len(scheduler.task_queue) == 0
        assert scheduler.active_policy.name() == "adaptive"
    
    def test_enqueue_task(self):
        """Test enqueueing a task"""
        scheduler = AdvancedScheduler()
        task = ScheduledTask(task_id="task-1", task_name="Task 1")
        
        scheduler.enqueue_task(task)
        
        assert len(scheduler.task_queue) == 1
        assert task.scheduled_at is not None
    
    def test_set_scheduling_policy(self):
        """Test switching scheduling policies"""
        scheduler = AdvancedScheduler()
        
        scheduler.set_scheduling_policy("priority")
        assert scheduler.active_policy.name() == "priority"
        
        scheduler.set_scheduling_policy("deadline")
        assert scheduler.active_policy.name() == "deadline"
    
    def test_set_invalid_policy_raises(self):
        """Test setting an invalid policy raises error"""
        scheduler = AdvancedScheduler()
        
        with pytest.raises(ValueError):
            scheduler.set_scheduling_policy("nonexistent")
    
    def test_can_allocate_resources_success(self):
        """Test resource allocation when sufficient"""
        scheduler = AdvancedScheduler(quota=ResourceQuota(
            max_cpu_cores=10.0,
            max_memory_mb=2048.0
        ))
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(cpu_cores=2.0, memory_mb=512.0)
        )
        
        assert scheduler.can_allocate_resources(task) == True
    
    def test_can_allocate_resources_fails_cpu(self):
        """Test resource allocation fails when insufficient CPU"""
        scheduler = AdvancedScheduler(quota=ResourceQuota(max_cpu_cores=1.0))
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(cpu_cores=2.0)
        )
        
        assert scheduler.can_allocate_resources(task) == False
    
    def test_can_allocate_resources_fails_memory(self):
        """Test resource allocation fails when insufficient memory"""
        scheduler = AdvancedScheduler(quota=ResourceQuota(max_memory_mb=256.0))
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(memory_mb=512.0)
        )
        
        assert scheduler.can_allocate_resources(task) == False
    
    def test_can_allocate_resources_fails_concurrent(self):
        """Test resource allocation fails when concurrent limit exceeded"""
        scheduler = AdvancedScheduler(quota=ResourceQuota(max_concurrent_tasks=1))
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(concurrent_slots=2)
        )
        
        assert scheduler.can_allocate_resources(task) == False
    
    def test_allocate_resources(self):
        """Test allocating resources"""
        scheduler = AdvancedScheduler()
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(cpu_cores=2.0, memory_mb=512.0)
        )
        
        success = scheduler.allocate_resources(task)
        
        assert success == True
        assert scheduler.resource_usage.cpu_used == 2.0
        assert scheduler.resource_usage.memory_used == 512.0
    
    def test_release_resources(self):
        """Test releasing resources"""
        scheduler = AdvancedScheduler()
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            resources=ResourceRequest(cpu_cores=2.0, memory_mb=512.0)
        )
        
        scheduler.allocate_resources(task)
        scheduler.release_resources(task)
        
        assert scheduler.resource_usage.cpu_used == 0.0
        assert scheduler.resource_usage.memory_used == 0.0
    
    def test_get_next_task_by_priority(self):
        """Test getting next task by priority"""
        scheduler = AdvancedScheduler(default_policy="priority")
        
        normal_task = ScheduledTask(
            task_id="normal",
            task_name="Normal",
            priority=TaskPriority.NORMAL
        )
        high_task = ScheduledTask(
            task_id="high",
            task_name="High",
            priority=TaskPriority.HIGH
        )
        
        scheduler.enqueue_task(normal_task)
        scheduler.enqueue_task(high_task)
        
        next_task = scheduler.get_next_task()
        assert next_task.task_id == "high"
    
    def test_get_next_task_by_deadline(self):
        """Test getting next task by deadline"""
        scheduler = AdvancedScheduler(default_policy="deadline")
        
        now = datetime.utcnow()
        later = ScheduledTask(
            task_id="later",
            task_name="Later",
            deadline=now + timedelta(seconds=300)
        )
        soon = ScheduledTask(
            task_id="soon",
            task_name="Soon",
            deadline=now + timedelta(seconds=10)
        )
        
        scheduler.enqueue_task(later)
        scheduler.enqueue_task(soon)
        
        next_task = scheduler.get_next_task()
        assert next_task.task_id == "soon"
    
    def test_execute_task_success(self):
        """Test executing a task successfully"""
        scheduler = AdvancedScheduler()
        callback = Mock()
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            estimated_cost=1.5,
            callback=callback
        )
        
        result = asyncio.run(scheduler.execute_task(task))
        
        assert result["success"] == True
        assert result["task_id"] == "task-1"
        assert callback.called
    
    def test_execute_task_async(self):
        """Test executing async task"""
        scheduler = AdvancedScheduler()
        
        async def async_callback():
            await asyncio.sleep(0.01)
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            callback=async_callback
        )
        
        result = asyncio.run(scheduler.execute_task(task))
        
        assert result["success"] == True
        assert result["task_id"] == "task-1"
    
    def test_execute_task_failure(self):
        """Test executing a task that fails"""
        scheduler = AdvancedScheduler()
        
        def failing_callback():
            raise RuntimeError("Task failed")
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            callback=failing_callback
        )
        
        result = asyncio.run(scheduler.execute_task(task))
        
        assert result["success"] == False
        assert "error" in result
    
    def test_get_metrics(self):
        """Test getting scheduler metrics"""
        scheduler = AdvancedScheduler()
        
        task = ScheduledTask(task_id="task-1", task_name="Task 1")
        scheduler.enqueue_task(task)
        
        metrics = scheduler.get_metrics()
        
        assert "total_tasks_scheduled" in metrics
        assert "queued_tasks" in metrics
        assert metrics["queued_tasks"] == 1
        assert metrics["current_policy"] == "adaptive"
    
    def test_export_metrics(self, tmp_path):
        """Test exporting metrics to file"""
        scheduler = AdvancedScheduler()
        task = ScheduledTask(task_id="task-1", task_name="Task 1")
        scheduler.enqueue_task(task)
        
        filepath = tmp_path / "metrics.json"
        scheduler.export_metrics(str(filepath))
        
        assert filepath.exists()
        
        import json
        with open(filepath) as f:
            data = json.load(f)
        
        assert "total_tasks_scheduled" in data


# ============================================================================
# Tests: SchedulingPolicyDSL
# ============================================================================

class TestSchedulingPolicyDSL:
    """Tests for scheduling policy DSL"""
    
    def test_create_custom_policy(self):
        """Test creating a custom policy with DSL"""
        def custom_rule(task, usage, quota):
            return -task.priority.value + task.estimated_cost
        
        policy = SchedulingPolicyDSL.create_custom_policy("custom", custom_rule)
        
        assert policy.name() == "custom"
        
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            priority=TaskPriority.HIGH,
            estimated_cost=2.0
        )
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        score = policy.score_task(task, usage, quota)
        assert isinstance(score, float)
    
    def test_create_weighted_policy(self):
        """Test creating a weighted policy with DSL"""
        weights = {
            "priority": 0.5,
            "deadline_urgency": 0.3,
            "cost": 0.2
        }
        
        policy = SchedulingPolicyDSL.create_weighted_policy("weighted", weights)
        
        assert policy.name() == "weighted"
        
        now = datetime.utcnow()
        task = ScheduledTask(
            task_id="task-1",
            task_name="Task 1",
            priority=TaskPriority.HIGH,
            deadline=now + timedelta(seconds=60),
            estimated_cost=1.0
        )
        usage = ResourceUsage()
        quota = ResourceQuota()
        
        score = policy.score_task(task, usage, quota)
        assert isinstance(score, float)


# ============================================================================
# Integration Tests
# ============================================================================

class TestAdvancedSchedulerIntegration:
    """Integration tests for advanced scheduler"""
    
    def test_mixed_priority_and_deadline(self):
        """Test scheduling with mixed priority and deadline constraints"""
        scheduler = AdvancedScheduler(default_policy="adaptive")
        
        now = datetime.utcnow()
        
        # Enqueue tasks with different priorities and deadlines
        t1 = ScheduledTask(
            task_id="t1",
            task_name="Critical",
            priority=TaskPriority.CRITICAL,
            deadline=now + timedelta(seconds=300)
        )
        t2 = ScheduledTask(
            task_id="t2",
            task_name="Urgent",
            priority=TaskPriority.NORMAL,
            deadline=now + timedelta(seconds=10)
        )
        t3 = ScheduledTask(
            task_id="t3",
            task_name="Low",
            priority=TaskPriority.LOW,
            deadline=now + timedelta(seconds=100)
        )
        
        scheduler.enqueue_task(t1)
        scheduler.enqueue_task(t2)
        scheduler.enqueue_task(t3)
        
        # Get next task should consider both factors
        next_task = scheduler.get_next_task()
        assert next_task is not None  # Should pick one based on adaptive scoring
    
    def test_resource_exhaustion_prevents_scheduling(self):
        """Test that resource exhaustion prevents task scheduling"""
        scheduler = AdvancedScheduler(quota=ResourceQuota(max_cpu_cores=2.0))
        
        # Enqueue first task and allocate resources
        t1 = ScheduledTask(
            task_id="t1",
            task_name="Task 1",
            resources=ResourceRequest(cpu_cores=2.0)
        )
        scheduler.enqueue_task(t1)
        scheduler.allocate_resources(t1)
        
        # Try to schedule second task (should fail)
        t2 = ScheduledTask(
            task_id="t2",
            task_name="Task 2",
            resources=ResourceRequest(cpu_cores=1.0)
        )
        
        assert scheduler.can_allocate_resources(t2) == False
        assert scheduler.get_next_task() is None
    
    def test_multiple_tasks_execution(self):
        """Test executing multiple tasks in sequence"""
        scheduler = AdvancedScheduler()
        
        executed_tasks = []
        
        def create_callback(task_id):
            def callback():
                executed_tasks.append(task_id)
            return callback
        
        t1 = ScheduledTask(
            task_id="t1",
            task_name="Task 1",
            callback=create_callback("t1")
        )
        t2 = ScheduledTask(
            task_id="t2",
            task_name="Task 2",
            callback=create_callback("t2")
        )
        
        asyncio.run(scheduler.execute_task(t1))
        asyncio.run(scheduler.execute_task(t2))
        
        assert len(executed_tasks) == 2
        assert scheduler.total_tasks_scheduled == 2
    
    def test_cost_optimization_with_constraints(self):
        """Test cost optimization while respecting resource constraints"""
        scheduler = AdvancedScheduler(
            quota=ResourceQuota(max_tokens_per_hour=10000),
            default_policy="cost_optimization"
        )
        
        cheap = ScheduledTask(
            task_id="cheap",
            task_name="Cheap Task",
            estimated_cost=0.5,
            resources=ResourceRequest(tokens=1000)
        )
        expensive = ScheduledTask(
            task_id="expensive",
            task_name="Expensive Task",
            estimated_cost=5.0,
            resources=ResourceRequest(tokens=5000)
        )
        
        scheduler.enqueue_task(expensive)
        scheduler.enqueue_task(cheap)
        
        # Should prefer cheap task
        next_task = scheduler.get_next_task()
        assert next_task.task_id == "cheap"
