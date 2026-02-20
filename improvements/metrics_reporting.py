"""
Metrics & Reporting - Track and report system performance
"""

from datetime import datetime
from typing import Dict, List

class MetricsCollector:
    """Collect system metrics."""
    
    def __init__(self):
        self.metrics = {
            'cycles_completed': 0,
            'improvements_made': 0,
            'commits': 0,
            'errors': 0,
            'start_time': datetime.now(),
            'uptime_seconds': 0
        }
        self.history = []
    
    def record_cycle(self, success: bool, duration: float):
        """Record a cycle."""
        self.metrics['cycles_completed'] += 1
        
        if success:
            self.metrics['improvements_made'] += 1
            self.metrics['commits'] += 1
        else:
            self.metrics['errors'] += 1
        
        self.metrics['uptime_seconds'] = (
            datetime.now() - self.metrics['start_time']
        ).total_seconds()
        
        self.history.append({
            'timestamp': datetime.now(),
            'success': success,
            'duration': duration,
            'metrics': self.metrics.copy()
        })
    
    def get_metrics(self) -> Dict:
        """Get current metrics."""
        uptime = (datetime.now() - self.metrics['start_time']).total_seconds()
        cycles = self.metrics['cycles_completed']
        rate = cycles / (uptime / 3600) if uptime > 0 else 0
        
        return {
            **self.metrics,
            'uptime_seconds': uptime,
            'cycles_per_hour': rate,
            'success_rate': (
                self.metrics['improvements_made'] / max(cycles, 1) * 100
            )
        }
    
    def get_trend(self, window=10) -> Dict:
        """Get recent trend."""
        recent = self.history[-window:] if self.history else []
        
        if not recent:
            return {}
        
        success_count = sum(1 for r in recent if r['success'])
        avg_duration = sum(r['duration'] for r in recent) / len(recent)
        
        return {
            'recent_success_rate': success_count / len(recent) * 100,
            'recent_avg_duration': avg_duration,
            'trend_direction': 'up' if success_count > len(recent) / 2 else 'down'
        }

class PerformanceMonitor:
    """Monitor system performance."""
    
    def __init__(self):
        self.performance_targets = {
            'cycle_time_max': 5.0,  # seconds
            'success_rate_min': 95.0,  # percent
            'uptime_min': 99.9  # percent
        }
        self.alerts = []
    
    def check_performance(self, metrics: Dict) -> Dict:
        """Check if metrics meet targets."""
        status = {
            'cycle_time_ok': metrics.get('uptime_seconds', 0) < self.performance_targets['cycle_time_max'],
            'success_rate_ok': metrics.get('success_rate', 0) >= self.performance_targets['success_rate_min'],
            'uptime_ok': metrics.get('uptime_seconds', 0) > 0
        }
        
        return {
            'all_targets_met': all(status.values()),
            'status': status,
            'alerts': self.generate_alerts(status, metrics)
        }
    
    def generate_alerts(self, status: Dict, metrics: Dict) -> List[str]:
        """Generate performance alerts."""
        alerts = []
        
        if not status['cycle_time_ok']:
            alerts.append(f"⚠️ Slow cycles (>{self.performance_targets['cycle_time_max']}s)")
        
        if not status['success_rate_ok']:
            alerts.append(f"⚠️ Low success rate (<{self.performance_targets['success_rate_min']}%)")
        
        return alerts

class ProgressReporter:
    """Report progress and status."""
    
    def __init__(self):
        self.reports = []
    
    def generate_report(self, metrics: Dict, performance: Dict) -> str:
        """Generate progress report."""
        report = f"""
=== KODO SYSTEM REPORT ===
Cycles Completed: {metrics.get('cycles_completed', 0)}
Improvements Made: {metrics.get('improvements_made', 0)}
Commits: {metrics.get('commits', 0)}
Errors: {metrics.get('errors', 0)}
Success Rate: {metrics.get('success_rate', 0):.1f}%
Uptime: {metrics.get('uptime_seconds', 0):.0f}s ({metrics.get('uptime_seconds', 0)/3600:.1f}h)
Cycles/Hour: {metrics.get('cycles_per_hour', 0):.1f}

Alerts: {len(performance.get('alerts', []))}
Status: {'✅ All targets met' if performance.get('all_targets_met') else '⚠️ Some targets missed'}
"""
        self.reports.append(report)
        return report
    
    def get_summary(self) -> str:
        """Get system summary."""
        return f"Generated {len(self.reports)} reports"
