"""Structured logging for Kodo observability."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class LogEntry:
    """Structured log entry with context."""
    timestamp: str
    level: str
    component: str
    operation: str
    message: str
    duration_ms: Optional[float] = None
    agent_id: Optional[str] = None
    cost: Optional[float] = None
    tags: Dict[str, str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}


class StructuredLogger:
    """Logger that emits structured JSON logs with performance context."""
    
    def __init__(self, log_file: Path = Path(".kodo/structured_logs.jsonl")):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Also set up standard Python logging
        self.logger = logging.getLogger("kodo")
        if not self.logger.handlers:
            handler = logging.FileHandler(log_file.with_suffix(".log"))
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
        
        self.entries = []
    
    def info(
        self,
        component: str,
        operation: str,
        message: str,
        **kwargs
    ) -> None:
        """Log info level structured message."""
        self._log("INFO", component, operation, message, **kwargs)
    
    def error(
        self,
        component: str,
        operation: str,
        message: str,
        error: Optional[Exception] = None,
        **kwargs
    ) -> None:
        """Log error level structured message."""
        error_str = None
        if error:
            error_str = f"{error.__class__.__name__}: {str(error)}"
        self._log("ERROR", component, operation, message, error=error_str, **kwargs)
    
    def warning(
        self,
        component: str,
        operation: str,
        message: str,
        **kwargs
    ) -> None:
        """Log warning level structured message."""
        self._log("WARNING", component, operation, message, **kwargs)
    
    def debug(
        self,
        component: str,
        operation: str,
        message: str,
        **kwargs
    ) -> None:
        """Log debug level structured message."""
        self._log("DEBUG", component, operation, message, **kwargs)
    
    def _log(
        self,
        level: str,
        component: str,
        operation: str,
        message: str,
        duration_ms: Optional[float] = None,
        agent_id: Optional[str] = None,
        cost: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
        error: Optional[str] = None,
        **kwargs
    ) -> None:
        """Internal log implementation."""
        # Handle additional kwargs as tags
        if tags is None:
            tags = {}
        tags.update({k: str(v) for k, v in kwargs.items()})
        
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            component=component,
            operation=operation,
            message=message,
            duration_ms=duration_ms,
            agent_id=agent_id,
            cost=cost,
            tags=tags,
            error=error,
        )
        
        self.entries.append(entry)
        self._write_entry(entry)
        
        # Also log to standard logger
        log_msg = f"[{component}] {operation}: {message}"
        if duration_ms:
            log_msg += f" ({duration_ms:.2f}ms)"
        if cost:
            log_msg += f" ($${cost:.4f})"
        
        getattr(self.logger, level.lower())(log_msg)
    
    def _write_entry(self, entry: LogEntry) -> None:
        """Write entry to structured log file."""
        with open(self.log_file, "a") as f:
            data = asdict(entry)
            f.write(json.dumps(data) + "\n")
    
    def get_entries_by_component(self, component: str) -> list[LogEntry]:
        """Get all entries for a component."""
        return [e for e in self.entries if e.component == component]
    
    def get_errors(self) -> list[LogEntry]:
        """Get all error entries."""
        return [e for e in self.entries if e.level == "ERROR"]
    
    def get_cost_summary(self) -> Dict[str, float]:
        """Get total cost by component."""
        summary = {}
        for entry in self.entries:
            if entry.cost and entry.component:
                if entry.component not in summary:
                    summary[entry.component] = 0
                summary[entry.component] += entry.cost
        return summary


# Global logger instance
_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    """Get or create the global structured logger."""
    global _logger
    if _logger is None:
        _logger = StructuredLogger()
    return _logger
