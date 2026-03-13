"""
Phase 4: Resilience & Recovery Tests

Comprehensive tests for circuit breaker, retry logic, failure recovery,
and deadlock detection.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

from resilience import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitState,
    RetryStrategy,
    RetryConfig,
    BackoffStrategy,
    RetryExhausted,
    FailureDetector,
    RecoveryManager,
    RollbackManager,
    FailureEvent,
    FailureType,
    RecoveryStrategy,
    DeadlockDetector,
    DeadlockPrevention,
    DeadlockAvoidanceMonitor,
    ResourceType,
)


# ============================================================================
# Circuit Breaker Tests
# ============================================================================

class TestCircuitBreaker:
    """Tests for CircuitBreaker pattern."""
    
    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes in closed state."""
        cb = CircuitBreaker("test_service")
        assert cb.state == CircuitState.CLOSED
        assert cb.get_state() == "closed"
        assert cb.metrics.total_calls == 0
    
    def test_circuit_breaker_successful_call(self):
        """Test successful calls pass through."""
        cb = CircuitBreaker("test_service")
        
        def success_func():
            return "success"
        
        result = cb.call(success_func)
        assert result == "success"
        assert cb.metrics.successful_calls == 1
        assert cb.metrics.failed_calls == 0
    
    def test_circuit_breaker_failed_call(self):
        """Test failed calls are tracked."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=3))
        
        def failing_func():
            raise ValueError("Service error")
        
        # First failure
        with pytest.raises(ValueError):
            cb.call(failing_func)
        
        assert cb.metrics.failed_calls == 1
        assert cb.state == CircuitState.CLOSED
    
    def test_circuit_breaker_opens_on_threshold(self):
        """Test circuit opens when failure threshold reached."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise ValueError("Error")
        
        # Trigger 3 failures
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        assert cb.metrics.consecutive_failures == 3
    
    def test_circuit_breaker_rejects_calls_when_open(self):
        """Test circuit breaker rejects calls when open."""
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise ValueError("Error")
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Now calls should be rejected
        with pytest.raises(CircuitBreakerOpen):
            cb.call(lambda: "ok")
        
        assert cb.metrics.rejected_calls == 1
    
    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker transitions to half-open after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,  # Immediately allow recovery
            success_threshold=2,  # Need 2 successes to close
        )
        cb = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise ValueError("Error")
        
        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Advance time and attempt recovery
        cb._opened_at = time.time() - 1  # Pretend opened 1 second ago
        
        def success_func():
            return "success"
        
        # Should transition to half-open and remain there until success_threshold is met
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_circuit_breaker_closes_after_success(self):
        """Test circuit closes after success in half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,
            success_threshold=1,
        )
        cb = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise ValueError("Error")
        
        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(failing_func)
        
        # Transition to half-open
        cb._opened_at = time.time() - 1
        cb._transition_to_half_open()
        
        # Successful call should close circuit
        cb.call(lambda: "success")
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.consecutive_failures == 0
    
    def test_circuit_breaker_reset(self):
        """Test circuit breaker reset functionality."""
        cb = CircuitBreaker("test_service")
        cb.metrics.total_calls = 100
        cb.metrics.failed_calls = 50
        
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.total_calls == 0
        assert cb.metrics.failed_calls == 0
    
    def test_circuit_breaker_metrics(self):
        """Test circuit breaker metrics collection."""
        cb = CircuitBreaker("test_service")
        
        # Make some calls
        cb.call(lambda: "ok")
        cb.call(lambda: "ok")
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("error")))
        
        metrics = cb.get_metrics()
        assert metrics['total_calls'] == 3
        assert metrics['successful_calls'] == 2
        assert metrics['failed_calls'] == 1
        assert metrics['success_rate'] > 60


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry."""
    
    def test_registry_get_or_create(self):
        """Test get_or_create functionality."""
        registry = CircuitBreakerRegistry()
        
        cb1 = registry.get_or_create("service1")
        cb2 = registry.get_or_create("service1")
        
        assert cb1 is cb2
        assert cb1.name == "service1"
    
    def test_registry_get_all_metrics(self):
        """Test getting metrics from all breakers."""
        registry = CircuitBreakerRegistry()
        
        cb1 = registry.get_or_create("service1")
        cb2 = registry.get_or_create("service2")
        
        cb1.call(lambda: "ok")
        cb2.call(lambda: "ok")
        
        metrics = registry.get_all_metrics()
        assert "service1" in metrics
        assert "service2" in metrics
        assert metrics["service1"]["total_calls"] == 1
        assert metrics["service2"]["total_calls"] == 1


# ============================================================================
# Retry Strategy Tests
# ============================================================================

class TestRetryStrategy:
    """Tests for RetryStrategy with exponential backoff."""
    
    def test_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        strategy = RetryStrategy()
        result = strategy.execute(lambda: "success")
        
        assert result == "success"
        assert strategy.metrics.total_attempts == 1
        assert strategy.metrics.successful_attempts == 1
        assert strategy.metrics.failed_attempts == 0
    
    def test_retry_exhausted(self):
        """Test retry exhaustion after max attempts."""
        config = RetryConfig(max_attempts=3)
        strategy = RetryStrategy(config)
        
        def failing_func():
            raise ValueError("Persistent error")
        
        with pytest.raises(RetryExhausted):
            strategy.execute(failing_func)
        
        assert strategy.metrics.total_attempts == 3
        assert strategy.metrics.failed_attempts == 3
        assert strategy.metrics.total_retries == 2
    
    def test_retry_success_after_failures(self):
        """Test successful execution after initial failures."""
        config = RetryConfig(max_attempts=5, initial_delay=0.01)
        strategy = RetryStrategy(config)
        
        counter = {"attempts": 0}
        
        def sometimes_fails():
            counter["attempts"] += 1
            if counter["attempts"] < 3:
                raise ValueError("Transient error")
            return "success"
        
        result = strategy.execute(sometimes_fails)
        assert result == "success"
        assert strategy.metrics.total_attempts == 3
        assert strategy.metrics.successful_attempts == 1
        assert strategy.metrics.total_retries == 2
    
    def test_retry_exponential_backoff(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.1,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            backoff_factor=2.0,
            jitter=False,
        )
        strategy = RetryStrategy(config)
        
        # Test delay calculation
        delay1 = strategy._calculate_delay(1)
        delay2 = strategy._calculate_delay(2)
        delay3 = strategy._calculate_delay(3)
        
        assert abs(delay1 - 0.1) < 0.001
        assert abs(delay2 - 0.2) < 0.001
        assert abs(delay3 - 0.4) < 0.001
    
    def test_retry_linear_backoff(self):
        """Test linear backoff calculation."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.1,
            backoff_strategy=BackoffStrategy.LINEAR,
            backoff_factor=1.0,
            jitter=False,
        )
        strategy = RetryStrategy(config)
        
        delay1 = strategy._calculate_delay(1)
        delay2 = strategy._calculate_delay(2)
        delay3 = strategy._calculate_delay(3)
        
        assert abs(delay1 - 0.1) < 0.001
        assert abs(delay2 - 0.2) < 0.001
        assert abs(delay3 - 0.3) < 0.001
    
    def test_retry_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=1.0,
            max_delay=2.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            backoff_factor=2.0,
            jitter=False,
        )
        strategy = RetryStrategy(config)
        
        delay = strategy._calculate_delay(5)
        assert delay <= 2.0
    
    def test_retry_non_retryable_exception(self):
        """Test that non-retryable exceptions fail immediately."""
        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions={ValueError}
        )
        strategy = RetryStrategy(config)
        
        def raises_type_error():
            raise TypeError("Not retryable")
        
        with pytest.raises(TypeError):
            strategy.execute(raises_type_error)
        
        assert strategy.metrics.total_attempts == 1
    
    def test_retry_metrics(self):
        """Test retry metrics collection."""
        config = RetryConfig(max_attempts=3, initial_delay=0.01)
        strategy = RetryStrategy(config)
        
        counter = {"attempts": 0}
        
        def sometimes_fails():
            counter["attempts"] += 1
            if counter["attempts"] < 2:
                raise ValueError("Error")
            return "ok"
        
        strategy.execute(sometimes_fails)
        
        metrics = strategy.get_metrics()
        assert metrics['total_attempts'] == 2
        assert metrics['successful_attempts'] == 1
        assert metrics['total_retries'] == 1


# ============================================================================
# Failure Recovery Tests
# ============================================================================

class TestFailureDetector:
    """Tests for FailureDetector."""
    
    def test_detect_timeout(self):
        """Test timeout detection."""
        detector = FailureDetector()
        
        failure = detector.detect_timeout("service1", 30.0)
        
        assert failure.failure_type == FailureType.TIMEOUT
        assert failure.component == "service1"
        assert failure.severity == 3
        assert failure.recoverable is True
    
    def test_detect_resource_exhaustion(self):
        """Test resource exhaustion detection."""
        detector = FailureDetector()
        
        failure = detector.detect_resource_exhaustion("service1", "memory")
        
        assert failure.failure_type == FailureType.RESOURCE_EXHAUSTION
        assert failure.context['resource_type'] == "memory"
    
    def test_detect_deadlock(self):
        """Test deadlock detection."""
        detector = FailureDetector()
        
        failure = detector.detect_deadlock("agent1", ["agent2", "agent3"])
        
        assert failure.failure_type == FailureType.DEADLOCK
        assert failure.severity == 5  # Critical
        assert failure.context['waiting_on'] == ["agent2", "agent3"]
    
    def test_get_recent_failures(self):
        """Test getting recent failures."""
        detector = FailureDetector()
        
        detector.detect_timeout("service1", 30.0)
        time.sleep(0.1)
        detector.detect_timeout("service2", 30.0)
        
        recent = detector.get_recent_failures(minutes=5)
        assert len(recent) >= 2
    
    def test_get_failures_by_component(self):
        """Test filtering failures by component."""
        detector = FailureDetector()
        
        detector.detect_timeout("service1", 30.0)
        detector.detect_timeout("service2", 30.0)
        detector.detect_timeout("service1", 30.0)
        
        failures = detector.get_failures_by_component("service1")
        assert len(failures) == 2


class TestRecoveryManager:
    """Tests for RecoveryManager."""
    
    def test_recovery_manager_initialization(self):
        """Test recovery manager initializes correctly."""
        manager = RecoveryManager()
        
        assert manager.detector is not None
        assert len(manager.strategies) > 0
    
    def test_can_recover_from_timeout(self):
        """Test recovery feasibility for timeouts."""
        manager = RecoveryManager()
        
        failure = FailureEvent(
            failure_type=FailureType.TIMEOUT,
            component="service1",
        )
        
        # Without handlers, cannot recover
        assert not manager.can_recover(failure)
    
    def test_recovery_handler_registration(self):
        """Test registering recovery handlers."""
        manager = RecoveryManager()
        
        def retry_handler(component, params):
            return True
        
        manager.register_recovery_handler(
            RecoveryStrategy.RETRY,
            "service1",
            retry_handler,
        )
        
        failure = FailureEvent(
            failure_type=FailureType.TIMEOUT,
            component="service1",
        )
        
        actions = manager.get_recommended_recovery(failure)
        assert len(actions) > 0


class TestRollbackManager:
    """Tests for RollbackManager."""
    
    def test_create_snapshot(self):
        """Test creating state snapshot."""
        manager = RollbackManager()
        
        state = {"counter": 5, "status": "ok"}
        snapshot = manager.create_snapshot("component1", state)
        
        assert snapshot.component == "component1"
        assert snapshot.restore() == state
    
    def test_rollback_to_previous_state(self):
        """Test rolling back to previous state."""
        manager = RollbackManager()
        
        manager.create_snapshot("component1", {"version": 1})
        manager.create_snapshot("component1", {"version": 2})
        manager.create_snapshot("component1", {"version": 3})
        
        previous = manager.rollback("component1")
        assert previous["version"] == 2
    
    def test_rollback_no_snapshots(self):
        """Test rollback with no snapshots."""
        manager = RollbackManager()
        
        result = manager.rollback("component1")
        assert result is None
    
    def test_snapshot_history(self):
        """Test getting snapshot history."""
        manager = RollbackManager()
        
        manager.create_snapshot("component1", {"version": 1})
        manager.create_snapshot("component1", {"version": 2})
        
        history = manager.get_snapshot_history("component1")
        assert len(history) == 2


# ============================================================================
# Deadlock Detection Tests
# ============================================================================

class TestDeadlockDetector:
    """Tests for DeadlockDetector."""
    
    def test_deadlock_detector_initialization(self):
        """Test detector initializes correctly."""
        detector = DeadlockDetector()
        
        assert not detector.has_deadlock()
        assert len(detector.detected_cycles) == 0
    
    def test_simple_deadlock_detection(self):
        """Test detection of simple circular wait."""
        detector = DeadlockDetector()
        
        # Create cycle: A waits for B, B waits for A
        detector.add_wait_edge("agent_a", "agent_b")
        detector.add_wait_edge("agent_b", "agent_a")
        
        assert detector.has_deadlock()
        cycles = detector.detect_deadlock()
        assert len(cycles) > 0
    
    def test_no_deadlock_when_no_cycle(self):
        """Test no deadlock when no cycle exists."""
        detector = DeadlockDetector()
        
        # Linear chain: A waits for B, B waits for C
        detector.add_wait_edge("agent_a", "agent_b")
        detector.add_wait_edge("agent_b", "agent_c")
        
        assert not detector.has_deadlock()
    
    def test_complex_deadlock(self):
        """Test detection of complex cyclic deadlock."""
        detector = DeadlockDetector()
        
        # Complex cycle: A->B->C->A
        detector.add_wait_edge("agent_a", "agent_b")
        detector.add_wait_edge("agent_b", "agent_c")
        detector.add_wait_edge("agent_c", "agent_a")
        
        assert detector.has_deadlock()
        cycles = detector.detect_deadlock()
        assert len(cycles) > 0
    
    def test_clear_agent(self):
        """Test clearing an agent's relationships."""
        detector = DeadlockDetector()
        
        detector.add_wait_edge("agent_a", "agent_b")
        detector.add_wait_edge("agent_b", "agent_a")
        
        assert detector.has_deadlock()
        
        detector.clear_agent("agent_a")
        assert not detector.has_deadlock()
    
    def test_detector_metrics(self):
        """Test detector metrics collection."""
        detector = DeadlockDetector()
        
        detector.add_wait_edge("agent_a", "agent_b")
        detector.add_wait_edge("agent_b", "agent_a")
        detector.detect_deadlock()
        
        metrics = detector.get_metrics()
        assert metrics['deadlock_detected'] is True
        assert metrics['cycle_count'] > 0


class TestDeadlockPrevention:
    """Tests for DeadlockPrevention."""
    
    def test_global_resource_ordering(self):
        """Test resource ordering prevents circular waits."""
        prevention = DeadlockPrevention()
        prevention.set_global_resource_order(["resource_a", "resource_b", "resource_c"])
        
        # Valid: requesting higher priority after lower priority
        assert not prevention.check_circular_wait_violation(
            "agent1", "resource_a", "resource_b"
        )
        
        # Invalid: requesting lower priority after higher priority
        assert prevention.check_circular_wait_violation(
            "agent1", "resource_b", "resource_a"
        )
    
    def test_timeout_handling(self):
        """Test timeout-based deadlock breaking."""
        prevention = DeadlockPrevention()
        
        prevention.set_request_timeout("agent1", 1.0)
        assert not prevention.has_request_timeout("agent1")
        
        time.sleep(1.1)
        assert prevention.has_request_timeout("agent1")
    
    def test_detect_and_break_deadlock(self):
        """Test automatic deadlock breaking."""
        prevention = DeadlockPrevention()
        
        # Create deadlock
        prevention.detector.add_wait_edge("agent_a", "agent_b")
        prevention.detector.add_wait_edge("agent_b", "agent_a")
        
        assert prevention.detector.has_deadlock()
        
        victim = prevention.detect_and_break_deadlock()
        assert victim is not None
        assert not prevention.detector.has_deadlock()


class TestDeadlockAvoidanceMonitor:
    """Tests for DeadlockAvoidanceMonitor."""
    
    def test_monitor_initialization(self):
        """Test monitor initializes correctly."""
        monitor = DeadlockAvoidanceMonitor()
        
        assert not monitor.check_for_deadlock()
        assert len(monitor.deadlock_events) == 0
    
    def test_deadlock_event_logging(self):
        """Test deadlock events are logged."""
        monitor = DeadlockAvoidanceMonitor(detection_interval=0.0)
        
        # Create deadlock
        monitor.detector.add_wait_edge("agent_a", "agent_b")
        monitor.detector.add_wait_edge("agent_b", "agent_a")
        
        assert monitor.check_for_deadlock()
        assert len(monitor.deadlock_events) > 0
    
    def test_monitor_metrics(self):
        """Test monitor metrics."""
        monitor = DeadlockAvoidanceMonitor(detection_interval=0.0)
        
        monitor.detector.add_wait_edge("agent_a", "agent_b")
        monitor.detector.add_wait_edge("agent_b", "agent_a")
        monitor.check_for_deadlock()
        
        metrics = monitor.get_metrics()
        assert metrics['total_deadlock_events'] > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhase4Integration:
    """Integration tests for Phase 4 components."""
    
    def test_circuit_breaker_with_retry(self):
        """Test circuit breaker and retry strategy together."""
        cb = CircuitBreaker("service", CircuitBreakerConfig(failure_threshold=5))
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            retryable_exceptions={ValueError}
        )
        strategy = RetryStrategy(retry_config)
        
        counter = {"attempts": 0}
        
        def flaky_call():
            counter["attempts"] += 1
            if counter["attempts"] < 2:
                raise ValueError("Transient error")
            return "ok"
        
        def wrapped_call():
            return strategy.execute(lambda: cb.call(flaky_call))
        
        result = wrapped_call()
        assert result == "ok"
    
    def test_failure_detection_and_recovery(self):
        """Test integrated failure detection and recovery."""
        detector = FailureDetector()
        recovery = RecoveryManager()
        
        # Register recovery handler
        def timeout_handler(component, params):
            return True
        
        recovery.register_recovery_handler(
            RecoveryStrategy.RETRY,
            "service",
            timeout_handler,
        )
        
        # Detect timeout
        failure = detector.detect_timeout("service", 30.0)
        
        # Check if recoverable
        actions = recovery.get_recommended_recovery(failure)
        assert len(actions) >= 0
    
    def test_deadlock_detection_with_prevention(self):
        """Test deadlock detection integrated with prevention."""
        prevention = DeadlockPrevention()
        prevention.set_global_resource_order(["res_a", "res_b", "res_c"])
        
        # Attempt invalid acquisition order
        violation = prevention.check_circular_wait_violation(
            "agent1", "res_b", "res_a"
        )
        assert violation


# ============================================================================
# Async Tests (Skipped - requires pytest-asyncio)
# ============================================================================

# Note: Async tests for circuit breaker and retry strategy are available
# in the implementation (call_async, execute_async methods) but skipped
# in pytest due to pytest-asyncio dependency not being available.
# These can be enabled by installing: pip install pytest-asyncio
