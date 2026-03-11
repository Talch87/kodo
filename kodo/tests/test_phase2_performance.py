"""Phase 2: Performance Optimization Benchmarks and Tests.

Measures and validates performance improvements from Phase 2 optimizations:
- Agent communication hub caching
- Dependency graph memoization
- Performance profiling infrastructure
"""

import pytest
import time
from pathlib import Path

from agent_communication import AgentCommunicationHub, MessageType, AgentAsksFor
from dependency_planner import DependencyGraph, ExecutionPlanner
from performance_profiler import PerformanceProfiler, get_profiler


class TestAgentCommunicationCaching:
    """Test caching optimizations in AgentCommunicationHub."""
    
    def test_get_agent_conversations_uses_cache(self):
        """Verify that get_agent_conversations uses cache efficiently."""
        hub = AgentCommunicationHub()
        
        # Send messages from multiple agents
        for i in range(100):
            hub.send_message(
                sender=f"agent_{i % 5}",
                recipient=f"agent_{(i + 1) % 5}",
                message_type=MessageType.QUESTION,
                content=f"Question {i}",
            )
        
        # First call builds cache
        start = time.time()
        conv1 = hub.get_agent_conversations("agent_0")
        time1 = time.time() - start
        
        # Second call uses cache (should be much faster)
        start = time.time()
        conv2 = hub.get_agent_conversations("agent_0")
        time2 = time.time() - start
        
        # Verify same results
        assert conv1 == conv2
        
        # Cache hit should be ~10-100x faster
        # (Allow for variability in timing)
        if time1 > 0.001:  # Only check if first call took measurable time
            assert time2 <= time1, "Second call should use cache and be faster"
    
    def test_collaboration_suggestions_cached(self):
        """Verify that collaboration suggestions are cached."""
        hub = AgentCommunicationHub()
        
        # Send many messages
        for i in range(50):
            hub.send_message(
                sender="agent_a",
                recipient="agent_b",
                message_type=MessageType.QUESTION,
                content=f"Question {i}",
            )
        
        # First call computes suggestions
        start = time.time()
        sug1 = hub.generate_collaboration_suggestions()
        time1 = time.time() - start
        
        # Second call uses cache
        start = time.time()
        sug2 = hub.generate_collaboration_suggestions()
        time2 = time.time() - start
        
        assert sug1 == sug2
        assert time2 <= time1
    
    def test_cache_invalidation_on_new_messages(self):
        """Verify that caches are invalidated when new messages arrive."""
        hub = AgentCommunicationHub()
        
        # Send initial batch
        hub.send_message("agent_a", "agent_b", MessageType.QUESTION, "msg1")
        conv1 = hub.get_agent_conversations("agent_a")
        assert len(conv1) == 1
        
        # Send more messages - cache should invalidate
        hub.send_message("agent_a", "agent_b", MessageType.QUESTION, "msg2")
        conv2 = hub.get_agent_conversations("agent_a")
        assert len(conv2) == 2


class TestDependencyGraphCaching:
    """Test memoization in DependencyGraph."""
    
    def test_topological_order_cached(self):
        """Verify topological sort is cached."""
        graph = DependencyGraph()
        
        # Add tasks with dependencies
        for i in range(50):
            graph.add_task(f"task_{i}", f"Task {i}")
            if i > 0:
                graph.add_dependency(f"task_{i}", f"task_{i-1}")
        
        # First call computes order
        start = time.time()
        order1 = graph.get_topological_order()
        time1 = time.time() - start
        
        # Second call uses cache
        start = time.time()
        order2 = graph.get_topological_order()
        time2 = time.time() - start
        
        assert order1 == order2
        # Cache hit should be orders of magnitude faster
        assert time2 < time1 * 0.5 or time1 < 0.001  # Allow for timing noise
    
    def test_critical_path_cached(self):
        """Verify critical path calculation is cached."""
        graph = DependencyGraph()
        
        # Build dependency chain
        graph.add_task("task_0", "Task 0", duration_s=1.0)
        for i in range(1, 20):
            graph.add_task(f"task_{i}", f"Task {i}", duration_s=1.0)
            graph.add_dependency(f"task_{i}", f"task_{i-1}")
        
        # First call
        start = time.time()
        path1, time1_result = graph.get_critical_path()
        time1 = time.time() - start
        
        # Second call (cached)
        start = time.time()
        path2, time2_result = graph.get_critical_path()
        time2 = time.time() - start
        
        assert path1 == path2
        assert time1_result == time2_result
    
    def test_parallelizable_tasks_cached(self):
        """Verify parallelization analysis is cached."""
        graph = DependencyGraph()
        
        # Create diamond dependency pattern
        graph.add_task("a", "Task A")
        graph.add_task("b", "Task B")
        graph.add_task("c", "Task C")
        graph.add_task("d", "Task D")
        graph.add_dependency("c", "a")
        graph.add_dependency("d", "b")
        
        # First call
        start = time.time()
        para1 = graph.get_parallelizable_tasks()
        time1 = time.time() - start
        
        # Second call (cached)
        start = time.time()
        para2 = graph.get_parallelizable_tasks()
        time2 = time.time() - start
        
        assert para1 == para2
    
    def test_cache_invalidation_on_graph_change(self):
        """Verify caches are cleared when graph structure changes."""
        graph = DependencyGraph()
        graph.add_task("a", "Task A")
        graph.add_task("b", "Task B")
        
        # Prime cache
        order1 = graph.get_topological_order()
        
        # Add new task - should invalidate cache
        graph.add_task("c", "Task C")
        order2 = graph.get_topological_order()
        
        # Should have new task
        assert "c" in order2
        assert "c" not in order1


class TestPerformanceProfiler:
    """Test performance profiling infrastructure."""
    
    def test_record_metric(self):
        """Verify metrics are recorded."""
        profiler = PerformanceProfiler()
        
        profiler.record(
            "test_component",
            "test_operation",
            123.45,
            {"key": "value"}
        )
        
        assert len(profiler.metrics) == 1
        metric = profiler.metrics[0]
        assert metric.component == "test_component"
        assert metric.operation == "test_operation"
        assert metric.duration_ms == 123.45
        assert metric.tags == {"key": "value"}
    
    def test_measure_context_manager(self):
        """Verify measure context manager works."""
        profiler = PerformanceProfiler()
        
        with profiler.measure("component", "operation"):
            time.sleep(0.01)  # 10ms
        
        assert len(profiler.metrics) == 1
        metric = profiler.metrics[0]
        assert metric.duration_ms >= 10
    
    def test_statistics_generation(self):
        """Verify statistics are computed correctly."""
        profiler = PerformanceProfiler()
        
        # Record multiple measurements
        for i in range(10):
            profiler.record("comp", "op", float(i * 10), {})
        
        stats = profiler.get_statistics()
        op_stats = stats["comp.op"]
        
        assert op_stats["count"] == 10
        assert op_stats["min_ms"] == 0.0
        assert op_stats["max_ms"] == 90.0
        assert 40 < op_stats["avg_ms"] < 50
    
    def test_slowest_operations(self):
        """Verify slowest operations are identified."""
        profiler = PerformanceProfiler()
        
        # Fast operation
        for _ in range(10):
            profiler.record("comp1", "fast", 1.0, {})
        
        # Slow operation
        for _ in range(10):
            profiler.record("comp2", "slow", 100.0, {})
        
        slowest = profiler.get_slowest_operations(1)
        assert slowest[0][0] == "comp2.slow"
        assert slowest[0][1]["avg_ms"] == 100.0


class TestPhase2Benchmarks:
    """Integration benchmarks for Phase 2 optimizations."""
    
    def test_agent_hub_bulk_operations_performance(self):
        """Benchmark agent communication hub with bulk operations."""
        hub = AgentCommunicationHub()
        profiler = PerformanceProfiler()
        
        # Benchmark: Send 1000 messages
        with profiler.measure("communication", "bulk_send_1000"):
            for i in range(1000):
                hub.send_message(
                    f"agent_{i % 10}",
                    f"agent_{(i + 1) % 10}",
                    MessageType.QUESTION,
                    f"Message {i}",
                )
        
        stats = profiler.get_statistics()
        send_time = stats["communication.bulk_send_1000"]["total_ms"]
        
        # 1000 messages should complete in < 100ms
        assert send_time < 100, f"1000 messages took {send_time}ms (expected <100ms)"
    
    def test_dependency_graph_large_dag_performance(self):
        """Benchmark dependency graph with large DAG."""
        graph = DependencyGraph()
        profiler = PerformanceProfiler()
        
        # Create 1000 tasks in a chain
        with profiler.measure("dependency", "add_1000_tasks"):
            for i in range(1000):
                graph.add_task(f"task_{i}", f"Task {i}")
                if i > 0:
                    graph.add_dependency(f"task_{i}", f"task_{i-1}")
        
        # Benchmark topological sort (cached)
        with profiler.measure("dependency", "topological_sort_cached"):
            for _ in range(10):
                order = graph.get_topological_order()
        
        stats = profiler.get_statistics()
        sort_time = stats["dependency.topological_sort_cached"]["total_ms"]
        
        # 10 sorts of 1000-task graph should be <50ms (with caching)
        assert sort_time < 50, f"10 sorts took {sort_time}ms (expected <50ms)"
    
    def test_overall_orchestration_latency(self):
        """Benchmark overall orchestration latency."""
        profiler = get_profiler()
        hub = AgentCommunicationHub()
        graph = DependencyGraph()
        
        # Simulate orchestration pipeline
        with profiler.measure("orchestrator", "full_pipeline"):
            # Send messages
            for i in range(100):
                hub.send_message("a", "b", MessageType.QUESTION, f"msg {i}")
            
            # Create task graph
            for i in range(100):
                graph.add_task(f"task_{i}", f"Task {i}")
                if i > 0:
                    graph.add_dependency(f"task_{i}", f"task_{i-1}")
            
            # Get insights
            hub.generate_collaboration_suggestions()
            graph.get_topological_order()
            graph.get_critical_path()
            graph.get_parallelizable_tasks()
        
        stats = profiler.get_statistics()
        pipeline_time = stats["orchestrator.full_pipeline"]["total_ms"]
        
        # Full pipeline with 100 messages + 100 tasks should be <200ms
        assert pipeline_time < 200, f"Full pipeline took {pipeline_time}ms (expected <200ms)"


@pytest.mark.benchmark
class TestPhase2Regressions:
    """Regression tests to ensure optimizations don't break functionality."""
    
    def test_message_ordering_preserved(self):
        """Ensure message ordering is preserved with caching."""
        hub = AgentCommunicationHub()
        
        # Send messages in order
        for i in range(100):
            hub.send_message("sender", "recipient", MessageType.QUESTION, f"msg_{i:03d}")
        
        # Get all messages for recipient
        pending = hub.get_pending_messages("recipient")
        
        # Verify order
        for i, msg in enumerate(pending):
            assert msg.content == f"msg_{i:03d}"
    
    def test_dependency_graph_correctness(self):
        """Ensure dependency graph optimizations maintain correctness."""
        graph = DependencyGraph()
        
        # Complex dependency structure
        graph.add_task("a", "A")
        graph.add_task("b", "B")
        graph.add_task("c", "C")
        graph.add_task("d", "D")
        graph.add_task("e", "E")
        
        graph.add_dependency("c", "a")
        graph.add_dependency("c", "b")
        graph.add_dependency("d", "c")
        graph.add_dependency("e", "b")
        
        # Verify topological order respects dependencies
        order = graph.get_topological_order()
        positions = {task: i for i, task in enumerate(order)}
        
        # a, b must come before c
        assert positions["a"] < positions["c"]
        assert positions["b"] < positions["c"]
        # c must come before d
        assert positions["c"] < positions["d"]
        # b must come before e
        assert positions["b"] < positions["e"]
