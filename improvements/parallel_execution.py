"""
Parallel Execution Capability - Run improvements concurrently
"""

import concurrent.futures
from typing import List, Callable

class ParallelExecutor:
    """Execute improvements in parallel."""
    
    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    
    def execute_batch(self, improvements: List[str]) -> List[str]:
        """Execute multiple improvements in parallel."""
        futures = [
            self.executor.submit(self.execute_improvement, imp)
            for imp in improvements
        ]
        
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
        
        return results
    
    def execute_improvement(self, improvement: str) -> str:
        """Execute a single improvement."""
        return f"Executed: {improvement}"
    
    def shutdown(self):
        """Shutdown executor."""
        self.executor.shutdown(wait=True)

class AdaptiveExecutor:
    """Adapt execution strategy based on performance."""
    
    def __init__(self):
        self.performance_history = []
        self.optimal_batch_size = 3
        self.optimal_workers = 4
    
    def analyze_performance(self):
        """Analyze execution performance and adjust."""
        if len(self.performance_history) > 10:
            avg_time = sum(self.performance_history[-10:]) / 10
            if avg_time > 5.0:
                self.optimal_workers = min(8, self.optimal_workers + 1)
            elif avg_time < 1.0:
                self.optimal_workers = max(2, self.optimal_workers - 1)
    
    def get_optimal_configuration(self):
        """Get optimal execution configuration."""
        self.analyze_performance()
        return {
            "workers": self.optimal_workers,
            "batch_size": self.optimal_batch_size,
            "strategy": "parallel"
        }

class FailoverExecutor:
    """Execute with automatic failover."""
    
    def execute_with_fallback(self, improvement, primary_fn, fallback_fn):
        """Try primary execution, fallback to secondary."""
        try:
            return primary_fn(improvement)
        except Exception as e:
            print(f"Primary execution failed: {e}, using fallback")
            return fallback_fn(improvement)
