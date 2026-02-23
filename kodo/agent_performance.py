"""Agent Performance Tracking - Learn which agents excel at different tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum


class TaskType(Enum):
    """Classification of task types."""
    ARCHITECTURE = "architecture"       # Reviewing/planning code structure
    IMPLEMENTATION = "implementation"   # Writing new code
    TESTING = "testing"                # Writing/running tests
    DEBUGGING = "debugging"            # Fixing bugs
    OPTIMIZATION = "optimization"      # Performance/efficiency improvements
    REFACTORING = "refactoring"        # Code quality improvements
    DOCUMENTATION = "documentation"    # Writing docs/comments
    VERIFICATION = "verification"      # Reviewing work of others
    OTHER = "other"                    # Unclassified


@dataclass
class AgentRunMetrics:
    """Metrics from a single agent run."""
    agent_name: str
    agent_type: str                    # "worker", "architect", "tester", etc.
    task_type: TaskType
    timestamp: str
    duration_seconds: float
    tokens_used: int
    success: bool                      # Did it complete successfully?
    accepted_by_verifiers: bool        # Did reviewers approve?
    rejection_reason: Optional[str] = None
    cycles_to_success: int = 1         # How many attempts to get verified?
    
    def score(self) -> float:
        """Simple score: 0-100, higher is better."""
        base = 50.0
        
        if not self.success:
            return 0.0
        
        if not self.accepted_by_verifiers:
            return 25.0
        
        # Bonus for efficiency
        efficiency = 1.0 / (self.duration_seconds / 60.0 + 1)  # Normalize to minutes
        efficiency_bonus = efficiency * 20
        
        # Bonus for token efficiency
        token_efficiency = 1.0 / ((self.tokens_used or 10000) / 1000)
        token_bonus = token_efficiency * 10
        
        return min(100.0, base + efficiency_bonus + token_bonus)


@dataclass
class AgentStats:
    """Aggregated statistics for an agent."""
    agent_name: str
    agent_type: str
    task_type: TaskType
    
    runs: int = 0
    successes: int = 0
    failures: int = 0
    rejections: int = 0
    
    avg_duration_seconds: float = 0.0
    avg_tokens_used: int = 0
    avg_cycles_to_success: float = 1.0
    
    common_rejection_reasons: Dict[str, int] = field(default_factory=dict)
    overall_score: float = 0.0           # 0-100
    reliability: float = 0.0             # % of runs that succeeded
    
    def update(self, metric: AgentRunMetrics) -> None:
        """Update stats with a new run."""
        self.runs += 1
        
        if metric.success:
            self.successes += 1
            self.avg_duration_seconds = (
                (self.avg_duration_seconds * (self.runs - 1) + metric.duration_seconds) 
                / self.runs
            )
            self.avg_tokens_used = int(
                (self.avg_tokens_used * (self.runs - 1) + metric.tokens_used)
                / self.runs
            )
            self.avg_cycles_to_success = (
                (self.avg_cycles_to_success * (self.runs - 1) + metric.cycles_to_success)
                / self.runs
            )
            
            if not metric.accepted_by_verifiers:
                self.rejections += 1
                if metric.rejection_reason:
                    self.common_rejection_reasons[metric.rejection_reason] = (
                        self.common_rejection_reasons.get(metric.rejection_reason, 0) + 1
                    )
        else:
            self.failures += 1
        
        self.reliability = (self.successes / self.runs * 100) if self.runs > 0 else 0.0
        self.overall_score = self._calculate_score()
    
    def _calculate_score(self) -> float:
        """Calculate overall performance score."""
        if self.runs == 0:
            return 0.0
        
        base = (self.reliability / 100) * 50  # Reliability counts for 50%
        efficiency = (100 - min(100, self.avg_duration_seconds)) * 0.25  # Speed for 25%
        acceptance = ((self.successes - self.rejections) / self.runs * 100) * 0.25  # Acceptance for 25%
        
        return max(0.0, base + efficiency + acceptance)


class AgentPerformanceTracker:
    """Track and analyze agent performance across runs."""
    
    def __init__(self, data_dir: Path = Path(".kodo/agent_metrics")):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.metrics_file = self.data_dir / "agent_runs.jsonl"
        self.stats_file = self.data_dir / "agent_stats.json"
        
        # In-memory cache
        self.stats: Dict[tuple, AgentStats] = {}
        self._load_stats()
    
    def record_run(self, metric: AgentRunMetrics) -> None:
        """Record a single agent run."""
        # Append to JSONL file
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps({
                "agent_name": metric.agent_name,
                "agent_type": metric.agent_type,
                "task_type": metric.task_type.value,
                "timestamp": metric.timestamp,
                "duration_seconds": metric.duration_seconds,
                "tokens_used": metric.tokens_used,
                "success": metric.success,
                "accepted_by_verifiers": metric.accepted_by_verifiers,
                "rejection_reason": metric.rejection_reason,
                "cycles_to_success": metric.cycles_to_success,
            }) + "\n")
        
        # Update in-memory stats
        key = (metric.agent_name, metric.task_type.value)
        if key not in self.stats:
            self.stats[key] = AgentStats(
                agent_name=metric.agent_name,
                agent_type=metric.agent_type,
                task_type=metric.task_type,
            )
        
        self.stats[key].update(metric)
        self._save_stats()
    
    def get_best_agent_for_task(self, task_type: TaskType, agent_type: Optional[str] = None) -> Optional[str]:
        """Find the best agent for a specific task type."""
        candidates = [
            (name, stats) for (name, task), stats in self.stats.items()
            if task == task_type.value
            and (agent_type is None or stats.agent_type == agent_type)
            and stats.runs >= 2  # Need at least 2 runs for confidence
        ]
        
        if not candidates:
            return None
        
        return max(candidates, key=lambda x: x[1].overall_score)[0]
    
    def get_agent_stats(self, agent_name: str, task_type: Optional[TaskType] = None) -> List[AgentStats]:
        """Get stats for an agent, optionally filtered by task type."""
        return [
            stats for (name, task), stats in self.stats.items()
            if name == agent_name
            and (task_type is None or task == task_type.value)
        ]
    
    def get_failure_analysis(self) -> Dict[str, int]:
        """Analyze common failure patterns."""
        failures = {}
        for stats in self.stats.values():
            for reason, count in stats.common_rejection_reasons.items():
                failures[reason] = failures.get(reason, 0) + count
        
        return dict(sorted(failures.items(), key=lambda x: x[1], reverse=True))
    
    def get_leaderboard(self, task_type: Optional[TaskType] = None, limit: int = 10) -> List[tuple]:
        """Get top-performing agents, optionally filtered by task type."""
        candidates = [
            (name, stats) for (name, task), stats in self.stats.items()
            if (task_type is None or task == task_type.value)
            and stats.runs >= 2
        ]
        
        candidates.sort(key=lambda x: x[1].overall_score, reverse=True)
        return candidates[:limit]
    
    def _load_stats(self) -> None:
        """Load stats from JSON file."""
        if self.stats_file.exists():
            with open(self.stats_file) as f:
                data = json.load(f)
                for key, stat_data in data.items():
                    task_type = TaskType(stat_data["task_type"])
                    stat = AgentStats(
                        agent_name=stat_data["agent_name"],
                        agent_type=stat_data["agent_type"],
                        task_type=task_type,
                        runs=stat_data["runs"],
                        successes=stat_data["successes"],
                        failures=stat_data["failures"],
                        rejections=stat_data["rejections"],
                        avg_duration_seconds=stat_data["avg_duration_seconds"],
                        avg_tokens_used=stat_data["avg_tokens_used"],
                        avg_cycles_to_success=stat_data["avg_cycles_to_success"],
                        common_rejection_reasons=stat_data["common_rejection_reasons"],
                        overall_score=stat_data["overall_score"],
                        reliability=stat_data["reliability"],
                    )
                    self.stats[(stat_data["agent_name"], stat_data["task_type"])] = stat
    
    def _save_stats(self) -> None:
        """Save stats to JSON file."""
        data = {}
        for (name, task_type), stats in self.stats.items():
            key = f"{name}:{task_type}"
            data[key] = {
                "agent_name": stats.agent_name,
                "agent_type": stats.agent_type,
                "task_type": stats.task_type.value,
                "runs": stats.runs,
                "successes": stats.successes,
                "failures": stats.failures,
                "rejections": stats.rejections,
                "avg_duration_seconds": stats.avg_duration_seconds,
                "avg_tokens_used": stats.avg_tokens_used,
                "avg_cycles_to_success": stats.avg_cycles_to_success,
                "common_rejection_reasons": stats.common_rejection_reasons,
                "overall_score": stats.overall_score,
                "reliability": stats.reliability,
            }
        
        with open(self.stats_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def generate_report(self) -> str:
        """Generate a human-readable performance report."""
        lines = [
            "# Kodo Agent Performance Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Leaderboard (Overall)",
            ""
        ]
        
        for i, (name, stats) in enumerate(self.get_leaderboard(limit=10), 1):
            lines.append(f"{i}. **{name}** (Type: {stats.agent_type})")
            lines.append(f"   - Score: {stats.overall_score:.1f}/100")
            lines.append(f"   - Reliability: {stats.reliability:.1f}%")
            lines.append(f"   - Runs: {stats.runs} | Successes: {stats.successes}")
            lines.append(f"   - Avg Duration: {stats.avg_duration_seconds:.1f}s | Avg Tokens: {stats.avg_tokens_used:,}")
            lines.append("")
        
        # Failure analysis
        failures = self.get_failure_analysis()
        if failures:
            lines.append("## Common Failure Patterns")
            lines.append("")
            for reason, count in failures.items():
                lines.append(f"- {reason}: {count} occurrences")
            lines.append("")
        
        return "\n".join(lines)
