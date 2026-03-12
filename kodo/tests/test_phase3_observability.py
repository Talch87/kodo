"""Tests for Phase 3: Enhanced Observability."""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from structured_logging import StructuredLogger, LogEntry
from metrics_export import MetricsExporter
from trace_collector import TraceCollector, Trace
from health_check import HealthChecker, ComponentStatus, HealthStatus
from performance_profiler import PerformanceProfiler


class TestStructuredLogging:
    """Test structured logging system."""
    
    def test_logger_creation(self):
        """Test logger is created correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            assert logger is not None
            assert logger.log_file.parent.exists()
    
    def test_info_logging(self):
        """Test info level logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            logger.info("test_component", "test_op", "Test message")
            
            assert len(logger.entries) == 1
            entry = logger.entries[0]
            assert entry.component == "test_component"
            assert entry.operation == "test_op"
            assert entry.message == "Test message"
            assert entry.level == "INFO"
    
    def test_error_logging(self):
        """Test error level logging with exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            try:
                raise ValueError("Test error")
            except ValueError as e:
                logger.error("test_component", "test_op", "Error occurred", error=e)
            
            assert len(logger.entries) == 1
            entry = logger.entries[0]
            assert entry.level == "ERROR"
            assert "ValueError" in entry.error
    
    def test_logging_with_tags(self):
        """Test logging with custom tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            logger.info(
                "component",
                "op",
                "Message",
                agent_id="agent-1",
                cost=0.01,
            )
            
            entry = logger.entries[0]
            assert entry.agent_id == "agent-1"
            assert entry.cost == 0.01
    
    def test_get_entries_by_component(self):
        """Test filtering entries by component."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            logger.info("comp1", "op", "msg")
            logger.info("comp2", "op", "msg")
            logger.info("comp1", "op", "msg")
            
            comp1_entries = logger.get_entries_by_component("comp1")
            assert len(comp1_entries) == 2
            assert all(e.component == "comp1" for e in comp1_entries)
    
    def test_get_errors(self):
        """Test getting error entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            logger.info("comp", "op", "msg")
            logger.error("comp", "op", "error msg")
            logger.warning("comp", "op", "warning msg")
            
            errors = logger.get_errors()
            assert len(errors) == 1
            assert errors[0].level == "ERROR"
    
    def test_cost_summary(self):
        """Test cost tracking per component."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            logger.info("comp1", "op", "msg", cost=0.01)
            logger.info("comp1", "op", "msg", cost=0.02)
            logger.info("comp2", "op", "msg", cost=0.05)
            
            summary = logger.get_cost_summary()
            assert summary["comp1"] == pytest.approx(0.03)
            assert summary["comp2"] == pytest.approx(0.05)
    
    def test_structured_logs_written_to_file(self):
        """Test that structured logs are written to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "logs.jsonl"
            logger = StructuredLogger(log_file)
            logger.info("test", "op", "message")
            
            assert log_file.exists()
            with open(log_file) as f:
                lines = f.readlines()
                assert len(lines) > 0
                data = json.loads(lines[0])
                assert data["component"] == "test"


class TestMetricsExporter:
    """Test metrics export functionality."""
    
    def test_export_json(self):
        """Test JSON export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiler = PerformanceProfiler(
                Path(tmpdir) / "metrics.jsonl"
            )
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            profiler.record("comp", "op", 10.0)
            profiler.record("comp", "op", 20.0)
            
            exporter = MetricsExporter(
                profiler,
                logger,
                Path(tmpdir),
            )
            
            result = exporter.export_json()
            assert result.exists()
            
            with open(result) as f:
                data = json.load(f)
                assert "timestamp" in data
                assert "metrics_count" in data
                assert data["metrics_count"] == 2
    
    def test_export_csv(self):
        """Test CSV export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiler = PerformanceProfiler(
                Path(tmpdir) / "metrics.jsonl"
            )
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            profiler.record("comp", "op", 15.0)
            profiler.record("comp", "op", 25.0)
            
            exporter = MetricsExporter(
                profiler,
                logger,
                Path(tmpdir),
            )
            
            result = exporter.export_csv()
            assert result.exists()
            
            with open(result) as f:
                content = f.read()
                assert "Operation" in content
                assert "comp.op" in content
    
    def test_export_prometheus(self):
        """Test Prometheus export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiler = PerformanceProfiler(
                Path(tmpdir) / "metrics.jsonl"
            )
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            profiler.record("comp", "op", 10.0)
            logger.info("comp", "op", "msg", cost=0.05)
            
            exporter = MetricsExporter(
                profiler,
                logger,
                Path(tmpdir),
            )
            
            result = exporter.export_prometheus()
            assert result.exists()
            
            with open(result) as f:
                content = f.read()
                assert "kodo_operation_count" in content
                assert "kodo_component_cost_usd" in content
    
    def test_export_all(self):
        """Test exporting all formats at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiler = PerformanceProfiler(
                Path(tmpdir) / "metrics.jsonl"
            )
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            profiler.record("comp", "op", 10.0)
            
            exporter = MetricsExporter(
                profiler,
                logger,
                Path(tmpdir),
            )
            
            results = exporter.export_all()
            assert "json" in results
            assert "csv" in results
            assert "prometheus" in results
            
            for path in results.values():
                assert path.exists()
    
    def test_generate_summary(self):
        """Test generating text summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiler = PerformanceProfiler(
                Path(tmpdir) / "metrics.jsonl"
            )
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            
            profiler.record("comp", "op", 10.0)
            logger.info("comp", "op", "msg", cost=0.05)
            logger.error("comp", "op", "error", error=Exception("test"))
            
            exporter = MetricsExporter(
                profiler,
                logger,
                Path(tmpdir),
            )
            
            summary = exporter.generate_summary()
            assert "KODO OBSERVABILITY METRICS SUMMARY" in summary
            assert "PERFORMANCE METRICS" in summary
            assert "COST METRICS" in summary


class TestTraceCollection:
    """Test trace collection system."""
    
    def test_create_trace(self):
        """Test creating a trace."""
        collector = TraceCollector()
        collector.create_trace("trace-1", "service", "operation")
        
        assert "trace-1" in collector._traces
        trace = collector._traces["trace-1"]
        assert trace.service == "service"
        assert trace.root_operation == "operation"
    
    def test_start_and_end_span(self):
        """Test span lifecycle."""
        collector = TraceCollector()
        collector.create_trace("trace-1", "service", "operation")
        
        span_id = collector.start_span(
            "trace-1",
            "operation",
            "component",
        )
        
        assert span_id in collector._current_spans
        span = collector._current_spans[span_id]
        assert span.component == "component"
        
        collector.end_span(span_id, status="success")
        assert span.status == "success"
        assert span.duration_ms > 0
    
    def test_parent_child_spans(self):
        """Test parent-child span relationships."""
        collector = TraceCollector()
        collector.create_trace("trace-1", "service", "operation")
        
        parent_span = collector.start_span(
            "trace-1", "parent", "comp"
        )
        child_span = collector.start_span(
            "trace-1", "child", "comp", parent_span_id=parent_span
        )
        
        span = collector._current_spans[child_span]
        assert span.parent_span_id == parent_span
    
    def test_log_to_span(self):
        """Test logging to spans."""
        collector = TraceCollector()
        collector.create_trace("trace-1", "service", "operation")
        
        span_id = collector.start_span("trace-1", "op", "comp")
        collector.log_to_span(span_id, "Test log", level="info")
        
        span = collector._current_spans[span_id]
        assert len(span.logs) == 1
        assert span.logs[0]["message"] == "Test log"
    
    def test_finalize_trace(self):
        """Test finalizing a trace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = TraceCollector(Path(tmpdir))
            collector.create_trace("trace-1", "service", "operation")
            
            span_id = collector.start_span("trace-1", "op", "comp")
            collector.end_span(span_id)
            
            trace = collector.finalize_trace("trace-1")
            assert trace is not None
            assert len(trace.spans) == 1
    
    def test_trace_summary(self):
        """Test trace summary generation."""
        collector = TraceCollector()
        collector.create_trace("trace-1", "service", "root_op")
        
        span1 = collector.start_span("trace-1", "op1", "comp1")
        collector.end_span(span1)
        
        span2 = collector.start_span("trace-1", "op2", "comp2")
        collector.end_span(span2)
        
        # Get trace before finalizing to check summary
        trace = collector._traces["trace-1"]
        
        # Manually add spans to trace for summary
        trace.spans = [collector._current_spans[span1], collector._current_spans[span2]]
        
        summary = collector.get_trace_summary("trace-1")
        assert summary["trace_id"] == "trace-1"
        assert summary["span_count"] == 2
        assert "comp1" in summary["components"]
        assert "comp2" in summary["components"]
    
    def test_recent_traces(self):
        """Test getting recent traces."""
        collector = TraceCollector()
        
        for i in range(5):
            collector.create_trace(f"trace-{i}", "service", "op")
        
        recent = collector.get_recent_traces(limit=3)
        assert len(recent) == 3
    
    def test_slow_traces(self):
        """Test identifying slow traces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = TraceCollector(Path(tmpdir))
            
            for i in range(3):
                collector.create_trace(f"trace-{i}", "service", "op")
                span_id = collector.start_span(f"trace-{i}", "op", "comp")
                collector.end_span(span_id)
            
            # Manually set one trace to be slow
            collector._traces["trace-1"].duration_ms = 2000
            
            slow = collector.get_slow_traces(threshold_ms=1000)
            assert len(slow) >= 1


class TestHealthChecking:
    """Test health checking system."""
    
    def test_register_component(self):
        """Test component registration."""
        checker = HealthChecker()
        checker.register_component("comp1")
        
        assert "comp1" in checker.components
        assert checker.components["comp1"].name == "comp1"
    
    def test_update_component_status(self):
        """Test updating component status."""
        checker = HealthChecker()
        checker.register_component("comp1")
        
        checker.update_component_status(
            "comp1",
            ComponentStatus.DEGRADED,
            response_time_ms=50.0,
        )
        
        component = checker.components["comp1"]
        assert component.status == ComponentStatus.DEGRADED
        assert component.response_time_ms == 50.0
    
    def test_record_request(self):
        """Test recording requests."""
        checker = HealthChecker()
        
        checker.record_request(10.0, success=True)
        checker.record_request(20.0, success=True)
        checker.record_request(15.0, success=False)
        
        assert checker.request_count == 3
        assert checker.error_count == 1
    
    def test_get_system_health(self):
        """Test getting system health."""
        checker = HealthChecker()
        checker.register_component("comp1")
        checker.register_component("comp2")
        
        checker.update_component_status(
            "comp1",
            ComponentStatus.UP,
            response_time_ms=10.0,
        )
        checker.update_component_status(
            "comp2",
            ComponentStatus.UP,
            response_time_ms=20.0,
        )
        
        checker.record_request(10.0, success=True)
        checker.record_request(20.0, success=True)
        
        health = checker.get_system_health()
        assert health.status == HealthStatus.HEALTHY
        assert health.request_count == 2
        assert health.error_count == 0
    
    def test_unhealthy_status(self):
        """Test unhealthy system status."""
        checker = HealthChecker()
        checker.register_component("comp1")
        
        checker.update_component_status(
            "comp1",
            ComponentStatus.DOWN,
            response_time_ms=0,
        )
        
        health = checker.get_system_health()
        assert health.status == HealthStatus.UNHEALTHY
    
    def test_error_rate(self):
        """Test error rate calculation."""
        checker = HealthChecker()
        
        for _ in range(90):
            checker.record_request(10.0, success=True)
        for _ in range(10):
            checker.record_request(10.0, success=False)
        
        error_rate = checker.get_error_rate()
        assert error_rate == 10.0
    
    def test_health_summary(self):
        """Test health summary generation."""
        checker = HealthChecker()
        checker.register_component("comp1")
        checker.update_component_status(
            "comp1",
            ComponentStatus.UP,
            response_time_ms=10.0,
        )
        
        summary = checker.get_health_summary()
        assert "KODO HEALTH CHECK" in summary
        assert "comp1" in summary


class TestPhase3Integration:
    """Integration tests for Phase 3."""
    
    def test_full_observability_pipeline(self):
        """Test full observability pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create all components
            profiler = PerformanceProfiler(Path(tmpdir) / "metrics.jsonl")
            logger = StructuredLogger(Path(tmpdir) / "logs.jsonl")
            collector = TraceCollector(Path(tmpdir) / "traces")
            checker = HealthChecker()
            
            # Simulate work
            profiler.record("orchestrator", "execute_task", 100.0)
            logger.info("orchestrator", "execute_task", "Task completed")
            checker.record_request(100.0, success=True)
            
            # Create trace
            collector.create_trace("task-1", "orchestrator", "execute_task")
            span = collector.start_span("task-1", "execute_task", "orchestrator")
            collector.log_to_span(span, "Task started")
            collector.end_span(span)
            collector.finalize_trace("task-1")
            
            # Export metrics
            exporter = MetricsExporter(profiler, logger, Path(tmpdir))
            exports = exporter.export_all()
            
            # Verify everything works
            assert len(profiler.metrics) > 0
            assert len(logger.entries) > 0
            assert len(collector._traces) > 0
            assert checker.request_count > 0
            
            for path in exports.values():
                assert path.exists()
