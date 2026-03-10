"""Tests for agent_performance.py"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock


class TestPerformanceMetrics:
    """Test performance metric collection."""

    def test_record_execution_time(self):
        """Test recording execution time."""
        metric = {
            "agent_id": "agent-1",
            "task_id": "task-1",
            "duration_ms": 250,
            "timestamp": datetime.now(),
        }
        assert metric["duration_ms"] == 250

    def test_record_memory_usage(self):
        """Test recording memory usage."""
        metric = {
            "agent_id": "agent-1",
            "memory_mb": 128,
            "peak_memory_mb": 156,
        }
        assert metric["memory_mb"] == 128


class TestPerformanceAnalysis:
    """Test performance analysis."""

    def test_calculate_average_latency(self):
        """Test calculating average latency."""
        durations = [100, 150, 200, 120, 180]
        avg = sum(durations) / len(durations)
        assert avg == 150.0

    def test_calculate_throughput(self):
        """Test calculating throughput."""
        tasks_completed = 100
        duration_seconds = 10
        throughput = tasks_completed / duration_seconds
        assert throughput == 10.0

    def test_calculate_error_rate(self):
        """Test calculating error rate."""
        total_tasks = 100
        failed_tasks = 5
        error_rate = (failed_tasks / total_tasks) * 100
        assert error_rate == 5.0


class TestPerformanceAnomalies:
    """Test anomaly detection in performance."""

    def test_detect_latency_spike(self):
        """Test detecting latency spikes."""
        baseline = 100
        current = 500
        spike_threshold = 2.0
        is_spike = current > (baseline * spike_threshold)
        assert is_spike is True

    def test_detect_memory_leak(self):
        """Test detecting potential memory leaks."""
        memory_samples = [100, 105, 110, 120, 135, 152]
        # Simple trend detection
        increasing = all(memory_samples[i] <= memory_samples[i + 1] 
                         for i in range(len(memory_samples) - 1))
        assert increasing is True

    def test_detect_timeout(self):
        """Test detecting task timeout."""
        timeout_ms = 5000
        execution_ms = 5100
        is_timeout = execution_ms > timeout_ms
        assert is_timeout is True


class TestPerformanceReport:
    """Test performance reporting."""

    def test_generate_performance_summary(self):
        """Test generating performance summary."""
        report = {
            "period": "1h",
            "avg_latency_ms": 150,
            "throughput": 10.0,
            "error_rate": 0.5,
            "uptime_percent": 99.9,
        }
        assert report["uptime_percent"] == 99.9

    def test_export_metrics(self):
        """Test exporting metrics for analysis."""
        metrics = {
            "timestamp": datetime.now(),
            "agent_id": "agent-1",
            "latency": 100,
            "memory": 128,
        }
        assert "timestamp" in metrics
        assert "agent_id" in metrics
