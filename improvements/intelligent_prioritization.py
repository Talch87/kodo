"""
Intelligent Prioritization - Smart improvement ordering
"""

from typing import List, Dict

class ImprovementPrioritizer:
    """Prioritize improvements by impact and effort."""
    
    def __init__(self):
        self.impact_scores = {}
        self.effort_estimates = {}
        self.dependency_graph = {}
    
    def prioritize(self, improvements: List[str]) -> List[str]:
        """Sort improvements by ROI (impact/effort)."""
        improvements_with_scores = [
            (imp, self.calculate_score(imp))
            for imp in improvements
        ]
        
        # Sort by score descending
        sorted_improvements = sorted(
            improvements_with_scores,
            key=lambda x: x[1],
            reverse=True
        )
        
        return [imp for imp, score in sorted_improvements]
    
    def calculate_score(self, improvement: str) -> float:
        """Calculate improvement priority score."""
        impact = self.get_impact(improvement)
        effort = self.get_effort(improvement)
        
        # ROI = Impact / Effort
        return impact / (effort + 0.1) if effort else 0
    
    def get_impact(self, improvement: str) -> float:
        """Estimate improvement impact."""
        impact_map = {
            'performance': 9,
            'reliability': 8,
            'usability': 6,
            'documentation': 3,
            'testing': 7,
            'optimization': 8,
            'scalability': 9
        }
        
        for key, score in impact_map.items():
            if key in improvement.lower():
                return float(score)
        
        return 5.0  # Default medium impact
    
    def get_effort(self, improvement: str) -> float:
        """Estimate effort required."""
        effort_map = {
            'simple': 1,
            'quick': 1,
            'major': 8,
            'complex': 7,
            'optimization': 5,
            'documentation': 2
        }
        
        for key, effort in effort_map.items():
            if key in improvement.lower():
                return float(effort)
        
        return 3.0  # Default medium effort
    
    def check_dependencies(self, improvement: str) -> List[str]:
        """Check if improvement has dependencies."""
        return self.dependency_graph.get(improvement, [])
    
    def schedule_improvements(self, improvements: List[str]) -> List[str]:
        """Schedule improvements respecting dependencies."""
        scheduled = []
        remaining = set(improvements)
        
        while remaining:
            # Find improvements with no unmet dependencies
            ready = [
                imp for imp in remaining
                if all(dep in scheduled for dep in self.check_dependencies(imp))
            ]
            
            if not ready:
                # No ready improvements, just take highest priority
                ready = [max(remaining, key=self.calculate_score)]
            
            # Add highest priority ready improvement
            best = max(ready, key=self.calculate_score)
            scheduled.append(best)
            remaining.remove(best)
        
        return scheduled

class AdaptiveStrategy:
    """Adapt strategy based on recent results."""
    
    def __init__(self):
        self.recent_results = []
        self.strategy = "balanced"
    
    def record_result(self, improvement: str, success: bool, time_taken: float):
        """Record improvement result."""
        self.recent_results.append({
            'improvement': improvement,
            'success': success,
            'time': time_taken
        })
        
        # Keep only recent 20 results
        if len(self.recent_results) > 20:
            self.recent_results = self.recent_results[-20:]
    
    def analyze_trends(self) -> Dict:
        """Analyze recent trends."""
        if not self.recent_results:
            return {"trend": "unknown"}
        
        success_rate = sum(1 for r in self.recent_results if r['success']) / len(self.recent_results)
        avg_time = sum(r['time'] for r in self.recent_results) / len(self.recent_results)
        
        return {
            "success_rate": success_rate,
            "avg_time": avg_time,
            "trend": "improving" if success_rate > 0.8 else "stable" if success_rate > 0.5 else "declining"
        }
    
    def update_strategy(self):
        """Update execution strategy based on trends."""
        trends = self.analyze_trends()
        
        if trends['trend'] == 'improving':
            self.strategy = "aggressive"  # Make more improvements
        elif trends['trend'] == 'declining':
            self.strategy = "conservative"  # Fewer, safer improvements
        else:
            self.strategy = "balanced"
    
    def get_strategy(self):
        """Get current strategy."""
        self.update_strategy()
        return self.strategy
