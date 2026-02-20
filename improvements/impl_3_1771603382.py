"""Metrics collection system."""
from datetime import datetime
from typing import Dict

class MetricsCollector:
    """Collect and track system metrics."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.cycles = 0
        self.improvements = 0
        self.errors = 0
    
    def record_cycle(self, success: bool):
        """Record cycle result."""
        self.cycles += 1
        if success:
            self.improvements += 1
        else:
            self.errors += 1
    
    def get_metrics(self) -> Dict:
        """Get current metrics."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        return {
            'cycles': self.cycles,
            'improvements': self.improvements,
            'errors': self.errors,
            'uptime_seconds': uptime,
            'success_rate': self.improvements / max(self.cycles, 1)
        }
