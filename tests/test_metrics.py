"""Tests for the metrics collection utility module."""

import time
import pytest
from datetime import datetime

from kodo.utils.metrics import MetricsCollector, Metric, TimerRecord


class TestMetric:
    """Tests for the Metric dataclass."""
    
    def test_metric_creation(self):
        """Test creating a metric."""
        metric = Metric(name="test", value=42.0)
        assert metric.name == "test"
        assert metric.value == 42.0
        assert isinstance(metric.timestamp, datetime)
    
    def test_metric_with_tags(self):
        """Test metric with tags."""
        metric = Metric(
            name="latency",
            value=100.5,
            tags={"endpoint": "/api/test"}
        )
        assert metric.tags == {"endpoint": "/api/test"}


class TestTimerRecord:
    """Tests for the TimerRecord dataclass."""
    
    def test_timer_record_creation(self):
        """Test creating a timer record."""
        start = time.time()
        timer = TimerRecord(name="test_timer", start_time=start)
        assert timer.name == "test_timer"
        assert timer.start_time == start
        assert timer.end_time is None
        assert timer.duration is None
    
    def test_timer_record_duration(self):
        """Test timer record duration calculation."""
        start = time.time()
        timer = TimerRecord(name="test_timer", start_time=start)
        time.sleep(0.1)
        timer.end_time = time.time()
        
        assert timer.duration is not None
        assert timer.duration >= 0.1


class TestMetricsCollector:
    """Tests for the MetricsCollector class."""
    
    def test_collector_initialization(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()
        assert len(collector.metrics) == 0
        assert len(collector.timers) == 0
        assert len(collector.counters) == 0
        assert isinstance(collector.created_at, datetime)
    
    # Timer tests
    def test_start_timer(self):
        """Test starting a timer."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        assert "operation" in collector.timers
        assert collector.timers["operation"].end_time is None
    
    def test_end_timer(self):
        """Test ending a timer."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        time.sleep(0.05)
        duration = collector.end_timer("operation")
        
        assert duration is not None
        assert duration >= 0.05
        assert collector.timers["operation"].end_time is not None
    
    def test_end_timer_nonexistent(self):
        """Test ending a non-existent timer raises error."""
        collector = MetricsCollector()
        with pytest.raises(ValueError, match="does not exist"):
            collector.end_timer("nonexistent")
    
    def test_start_already_running_timer(self):
        """Test starting an already running timer raises error."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        with pytest.raises(ValueError, match="already running"):
            collector.start_timer("operation")
    
    def test_end_already_stopped_timer(self):
        """Test ending an already stopped timer raises error."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        collector.end_timer("operation")
        with pytest.raises(ValueError, match="not running"):
            collector.end_timer("operation")
    
    def test_get_timer_duration(self):
        """Test retrieving timer duration."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        time.sleep(0.05)
        collector.end_timer("operation")
        
        duration = collector.get_timer_duration("operation")
        assert duration is not None
        assert duration >= 0.05
    
    def test_get_timer_duration_not_ended(self):
        """Test getting duration of not-yet-ended timer returns None."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        duration = collector.get_timer_duration("operation")
        assert duration is None
    
    def test_get_timer_duration_nonexistent(self):
        """Test getting duration of nonexistent timer returns None."""
        collector = MetricsCollector()
        duration = collector.get_timer_duration("nonexistent")
        assert duration is None
    
    # Metric recording tests
    def test_record_metric(self):
        """Test recording a metric."""
        collector = MetricsCollector()
        collector.record_metric("requests", 100.0)
        
        assert len(collector.metrics) == 1
        assert collector.metrics[0].name == "requests"
        assert collector.metrics[0].value == 100.0
    
    def test_record_metric_with_tags(self):
        """Test recording a metric with tags."""
        collector = MetricsCollector()
        collector.record_metric(
            "latency",
            50.5,
            tags={"endpoint": "/api/v1", "method": "GET"}
        )
        
        metric = collector.metrics[0]
        assert metric.tags == {"endpoint": "/api/v1", "method": "GET"}
    
    def test_record_multiple_metrics(self):
        """Test recording multiple metrics."""
        collector = MetricsCollector()
        collector.record_metric("metric1", 1.0)
        collector.record_metric("metric2", 2.0)
        collector.record_metric("metric3", 3.0)
        
        assert len(collector.metrics) == 3
        assert [m.value for m in collector.metrics] == [1.0, 2.0, 3.0]
    
    # Counter tests
    def test_increment_counter(self):
        """Test incrementing a counter."""
        collector = MetricsCollector()
        value = collector.increment_counter("requests")
        assert value == 1
        assert collector.get_counter("requests") == 1
    
    def test_increment_counter_multiple_times(self):
        """Test incrementing counter multiple times."""
        collector = MetricsCollector()
        collector.increment_counter("requests")
        collector.increment_counter("requests")
        value = collector.increment_counter("requests")
        
        assert value == 3
        assert collector.get_counter("requests") == 3
    
    def test_increment_counter_custom_amount(self):
        """Test incrementing counter by custom amount."""
        collector = MetricsCollector()
        value = collector.increment_counter("requests", 5)
        assert value == 5
        value = collector.increment_counter("requests", 3)
        assert value == 8
    
    def test_get_counter_default(self):
        """Test getting counter that doesn't exist returns 0."""
        collector = MetricsCollector()
        value = collector.get_counter("nonexistent")
        assert value == 0
    
    # Success/Failure tracking
    def test_record_success(self):
        """Test recording a success."""
        collector = MetricsCollector()
        collector.record_success()
        collector.record_success()
        
        assert collector.get_counter("successes") == 2
    
    def test_record_failure(self):
        """Test recording a failure."""
        collector = MetricsCollector()
        collector.record_failure()
        collector.record_failure("Connection timeout")
        
        assert collector.get_counter("failures") == 2
    
    def test_record_failure_with_error(self):
        """Test recording failure stores error message."""
        collector = MetricsCollector()
        collector.record_failure("Database error")
        
        assert collector.get_counter("failures") == 1
        # Check that error was recorded in metrics
        error_metrics = [m for m in collector.metrics if "error" in m.tags]
        assert len(error_metrics) == 1
        assert error_metrics[0].tags["error"] == "Database error"
    
    # Summary tests
    def test_get_summary(self):
        """Test getting a summary of metrics."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        time.sleep(0.01)
        collector.end_timer("operation")
        collector.record_metric("memory", 256.0)
        collector.increment_counter("requests", 5)
        
        summary = collector.get_summary()
        
        assert "timers" in summary
        assert "metrics" in summary
        assert "counters" in summary
        assert "created_at" in summary
        assert "collected_at" in summary
        assert summary["counters"]["requests"] == 5
        assert summary["total_metrics_recorded"] == 1
        assert summary["total_counters"] == 1
        assert summary["total_timers"] == 1
    
    def test_summary_structure(self):
        """Test structure of summary output."""
        collector = MetricsCollector()
        collector.record_metric("test", 100.0)
        collector.increment_counter("count", 5)
        
        summary = collector.get_summary()
        
        assert isinstance(summary["counters"], dict)
        assert isinstance(summary["timers"], dict)
        assert isinstance(summary["metrics"], list)
        assert isinstance(summary["created_at"], str)
        assert isinstance(summary["collected_at"], str)
    
    def test_summary_metrics_contain_timestamp(self):
        """Test that metrics in summary include timestamps."""
        collector = MetricsCollector()
        collector.record_metric("test", 100.0)
        
        summary = collector.get_summary()
        metric = summary["metrics"][0]
        
        assert "timestamp" in metric
        assert "name" in metric
        assert "value" in metric
        assert "tags" in metric
    
    # Reset tests
    def test_reset(self):
        """Test resetting all metrics."""
        collector = MetricsCollector()
        collector.start_timer("operation")
        collector.record_metric("test", 100.0)
        collector.increment_counter("requests", 5)
        
        collector.reset()
        
        assert len(collector.metrics) == 0
        assert len(collector.timers) == 0
        assert len(collector.counters) == 0
    
    # Integration tests
    def test_complete_workflow(self):
        """Test a complete metrics collection workflow."""
        collector = MetricsCollector()
        
        # Start operation
        collector.start_timer("total_time")
        
        # Simulate some work with metrics
        collector.increment_counter("api_calls", 3)
        collector.record_metric("tokens_used", 1500.0)
        
        # Record sub-timers
        collector.start_timer("processing")
        time.sleep(0.01)
        collector.end_timer("processing")
        
        # Track outcomes
        collector.record_success()
        collector.record_success()
        collector.record_failure("One error occurred")
        
        # End operation
        collector.end_timer("total_time")
        
        # Get summary
        summary = collector.get_summary()
        
        assert summary["counters"]["api_calls"] == 3
        assert summary["counters"]["successes"] == 2
        assert summary["counters"]["failures"] == 1
        assert "processing" in summary["timers"]
        assert "total_time" in summary["timers"]
        assert summary["total_metrics_recorded"] == 2  # tokens_used + last_error
    
    def test_metrics_with_same_name_different_tags(self):
        """Test recording multiple metrics with same name but different tags."""
        collector = MetricsCollector()
        collector.record_metric("latency", 100.0, {"endpoint": "/api/v1"})
        collector.record_metric("latency", 200.0, {"endpoint": "/api/v2"})
        
        assert len(collector.metrics) == 2
        latencies = [m for m in collector.metrics if m.name == "latency"]
        assert len(latencies) == 2
        assert latencies[0].tags["endpoint"] == "/api/v1"
        assert latencies[1].tags["endpoint"] == "/api/v2"
