"""Trace collection system for distributed observability."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import time


@dataclass
class Span:
    """A single trace span representing an operation."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    component: str
    start_time: str
    end_time: str
    duration_ms: float
    status: str  # "success", "error", "timeout"
    tags: Dict[str, str]
    logs: List[Dict[str, Any]]
    error: Optional[str] = None


@dataclass
class Trace:
    """A collection of related spans."""
    trace_id: str
    start_time: str
    end_time: str
    duration_ms: float
    service: str
    root_operation: str
    spans: List[Span]
    metadata: Dict[str, Any]


class TraceCollector:
    """Collect and manage distributed traces."""
    
    def __init__(self, traces_dir: Path = Path(".kodo/traces")):
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_spans: Dict[str, Span] = {}
        self._traces: Dict[str, Trace] = {}
        self._span_counter = 0
    
    def start_span(
        self,
        trace_id: str,
        operation_name: str,
        component: str,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Start a new span in a trace."""
        self._span_counter += 1
        span_id = f"span-{self._span_counter}"
        
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            component=component,
            start_time=datetime.now().isoformat(),
            end_time="",
            duration_ms=0,
            status="pending",
            tags=tags or {},
            logs=[],
        )
        
        self._current_spans[span_id] = span
        return span_id
    
    def end_span(
        self,
        span_id: str,
        status: str = "success",
        error: Optional[str] = None,
    ) -> None:
        """End a span."""
        if span_id not in self._current_spans:
            return
        
        span = self._current_spans[span_id]
        span.end_time = datetime.now().isoformat()
        
        # Calculate duration
        start = datetime.fromisoformat(span.start_time)
        end = datetime.fromisoformat(span.end_time)
        span.duration_ms = (end - start).total_seconds() * 1000
        
        span.status = status
        span.error = error
    
    def log_to_span(
        self,
        span_id: str,
        message: str,
        level: str = "info",
        **kwargs
    ) -> None:
        """Add a log entry to a span."""
        if span_id not in self._current_spans:
            return
        
        span = self._current_spans[span_id]
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "fields": kwargs,
        }
        span.logs.append(log_entry)
    
    def create_trace(
        self,
        trace_id: str,
        service: str,
        root_operation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new trace."""
        self._traces[trace_id] = Trace(
            trace_id=trace_id,
            start_time=datetime.now().isoformat(),
            end_time="",
            duration_ms=0,
            service=service,
            root_operation=root_operation,
            spans=[],
            metadata=metadata or {},
        )
    
    def finalize_trace(self, trace_id: str) -> Optional[Trace]:
        """Finalize a trace and save it."""
        if trace_id not in self._traces:
            return None
        
        trace = self._traces[trace_id]
        
        # Collect all spans for this trace
        trace_spans = [
            span for span in self._current_spans.values()
            if span.trace_id == trace_id
        ]
        trace.spans = trace_spans
        
        # Calculate trace duration
        if trace_spans:
            start_times = [
                datetime.fromisoformat(s.start_time) for s in trace_spans
            ]
            end_times = [
                datetime.fromisoformat(s.end_time) for s in trace_spans
                if s.end_time
            ]
            
            if start_times and end_times:
                trace.start_time = min(start_times).isoformat()
                trace.end_time = max(end_times).isoformat()
                
                start = datetime.fromisoformat(trace.start_time)
                end = datetime.fromisoformat(trace.end_time)
                trace.duration_ms = (end - start).total_seconds() * 1000
        
        # Save trace to file
        self._save_trace(trace)
        
        # Clean up spans
        for span in trace_spans:
            del self._current_spans[span.span_id]
        
        return trace
    
    def _save_trace(self, trace: Trace) -> None:
        """Save a trace to file."""
        filename = f"trace_{trace.trace_id}_{int(time.time())}.json"
        filepath = self.traces_dir / filename
        
        data = {
            "trace": asdict(trace),
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_trace_summary(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a summary of a trace."""
        trace = self._traces.get(trace_id)
        if not trace:
            return None
        
        spans_by_component = {}
        for span in trace.spans:
            if span.component not in spans_by_component:
                spans_by_component[span.component] = []
            spans_by_component[span.component].append(span)
        
        return {
            "trace_id": trace.trace_id,
            "service": trace.service,
            "root_operation": trace.root_operation,
            "duration_ms": trace.duration_ms,
            "span_count": len(trace.spans),
            "components": list(spans_by_component.keys()),
            "spans_by_component": {
                comp: [
                    {
                        "span_id": s.span_id,
                        "operation": s.operation_name,
                        "duration_ms": s.duration_ms,
                        "status": s.status,
                    }
                    for s in spans
                ]
                for comp, spans in spans_by_component.items()
            },
        }
    
    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent traces."""
        traces = list(self._traces.values())
        traces.sort(
            key=lambda t: t.start_time,
            reverse=True,
        )
        
        return [
            {
                "trace_id": t.trace_id,
                "service": t.service,
                "root_operation": t.root_operation,
                "duration_ms": t.duration_ms,
                "start_time": t.start_time,
                "span_count": len(t.spans),
            }
            for t in traces[:limit]
        ]
    
    def get_slow_traces(self, threshold_ms: float = 1000, limit: int = 10) -> List[Dict[str, Any]]:
        """Get traces slower than threshold."""
        traces = [
            t for t in self._traces.values()
            if t.duration_ms >= threshold_ms
        ]
        traces.sort(
            key=lambda t: t.duration_ms,
            reverse=True,
        )
        
        return [
            {
                "trace_id": t.trace_id,
                "service": t.service,
                "root_operation": t.root_operation,
                "duration_ms": t.duration_ms,
                "start_time": t.start_time,
            }
            for t in traces[:limit]
        ]


# Global trace collector instance
_collector: Optional[TraceCollector] = None


def get_trace_collector() -> TraceCollector:
    """Get or create the global trace collector."""
    global _collector
    if _collector is None:
        _collector = TraceCollector()
    return _collector
