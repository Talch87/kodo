"""Decision logging and traceability for orchestrator choices.

Tracks why the orchestrator chose each agent for each task, enabling
post-run analysis and improvement of decision quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class DecisionQuality(str, Enum):
    """Quality assessment of orchestrator decision."""
    
    CORRECT = "correct"  # Decision led to successful outcome
    SUBOPTIMAL = "suboptimal"  # Worked but could have been better
    WRONG = "wrong"  # Led to failure or poor result
    UNKNOWN = "unknown"  # Not yet assessed (initial state)


@dataclass
class OrchestratorDecision:
    """A single orchestrator decision to delegate work to an agent.
    
    Tracks *why* an agent was chosen for a task, enabling:
    - Post-run analysis of orchestrator performance
    - Feedback loops for learning
    - Debugging of poor decisions
    - Audit trails for transparency
    """
    
    # What decision was made
    agent_name: str  # Which agent (e.g., "worker_smart", "tester")
    task_description: str  # What task was assigned
    task_index: int = 0  # Which task in the sequence
    
    # Why it was made
    reasoning: str = ""  # Explanation from orchestrator prompt
    alternatives_considered: list[str] = field(default_factory=list)  # Other agents
    confidence: float = 1.0  # 0.0-1.0 confidence in this choice
    
    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cycle_number: int = 0  # Which cycle of orchestration
    exchange_number: int = 0  # Exchange number within cycle
    
    # Outcome (filled later)
    quality: DecisionQuality = DecisionQuality.UNKNOWN
    actual_outcome: str = ""  # What actually happened
    feedback: str = ""  # Human feedback on decision
    agent_completion_time_s: float = 0.0  # How long agent took
    agent_success: bool = False  # Did agent succeed
    agent_error: str = ""  # If failed, what error
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize decision for JSON logging."""
        return {
            "agent": self.agent_name,
            "task": self.task_description[:100],  # Truncate for logs
            "reasoning": self.reasoning[:200],
            "confidence": self.confidence,
            "alternatives": self.alternatives_considered,
            "quality": self.quality.value,
            "timestamp": self.timestamp.isoformat(),
            "cycle": self.cycle_number,
            "exchange": self.exchange_number,
            "agent_success": self.agent_success,
            "agent_time_s": round(self.agent_completion_time_s, 2),
        }


@dataclass
class DecisionSequence:
    """A sequence of orchestrator decisions for a complete run.
    
    Tracks the full history of who did what and why, for post-run analysis.
    """
    
    run_id: str
    decisions: list[OrchestratorDecision] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    
    def add_decision(self, decision: OrchestratorDecision) -> None:
        """Add a decision to the sequence."""
        decision.timestamp = datetime.now(timezone.utc)
        self.decisions.append(decision)
    
    def mark_complete(self) -> None:
        """Mark the sequence as complete."""
        self.end_time = datetime.now(timezone.utc)
    
    @property
    def duration_s(self) -> float:
        """Total duration of the run."""
        end = self.end_time or datetime.now(timezone.utc)
        delta = end - self.start_time
        return delta.total_seconds()
    
    @property
    def decision_count(self) -> int:
        """Total number of decisions made."""
        return len(self.decisions)
    
    @property
    def agent_counts(self) -> dict[str, int]:
        """How many times each agent was chosen."""
        counts: dict[str, int] = {}
        for decision in self.decisions:
            counts[decision.agent_name] = counts.get(decision.agent_name, 0) + 1
        return counts
    
    @property
    def decision_quality_counts(self) -> dict[str, int]:
        """How many decisions were correct/wrong/unknown."""
        counts: dict[str, int] = {
            "correct": 0,
            "suboptimal": 0,
            "wrong": 0,
            "unknown": 0,
        }
        for decision in self.decisions:
            counts[decision.quality.value] += 1
        return counts
    
    @property
    def average_confidence(self) -> float:
        """Average confidence across all decisions."""
        if not self.decisions:
            return 0.0
        total = sum(d.confidence for d in self.decisions)
        return total / len(self.decisions)
    
    @property
    def average_agent_time_s(self) -> float:
        """Average time agents took."""
        if not self.decisions:
            return 0.0
        total = sum(d.agent_completion_time_s for d in self.decisions)
        return total / len(self.decisions)
    
    @property
    def success_rate(self) -> float:
        """Percentage of agents that succeeded."""
        if not self.decisions:
            return 0.0
        successes = sum(1 for d in self.decisions if d.agent_success)
        return (successes / len(self.decisions)) * 100
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the run."""
        return {
            "run_id": self.run_id,
            "duration_s": round(self.duration_s, 2),
            "decisions_made": self.decision_count,
            "agents_used": self.agent_counts,
            "decision_quality": self.decision_quality_counts,
            "confidence": round(self.average_confidence, 2),
            "success_rate": round(self.success_rate, 1),
            "avg_agent_time_s": round(self.average_agent_time_s, 2),
        }


def build_decision(
    agent_name: str,
    task_description: str,
    reasoning: str = "",
    alternatives: Optional[list[str]] = None,
    confidence: float = 1.0,
    cycle: int = 0,
    exchange: int = 0,
) -> OrchestratorDecision:
    """Build an orchestrator decision.
    
    Convenience function to create a decision with sensible defaults.
    """
    return OrchestratorDecision(
        agent_name=agent_name,
        task_description=task_description,
        reasoning=reasoning,
        alternatives_considered=alternatives or [],
        confidence=min(1.0, max(0.0, confidence)),  # Clamp to 0-1
        cycle_number=cycle,
        exchange_number=exchange,
    )


def assess_decision_quality(
    decision: OrchestratorDecision,
    agent_succeeded: bool,
    agent_error: Optional[str] = None,
) -> DecisionQuality:
    """Automatically assess decision quality based on outcome.
    
    Args:
        decision: The decision to assess
        agent_succeeded: Whether the agent completed successfully
        agent_error: If failed, the error message
    
    Returns:
        Quality assessment
    """
    decision.agent_success = agent_succeeded
    decision.agent_error = agent_error or ""
    
    if agent_succeeded:
        # Success - was it the right agent?
        if decision.confidence >= 0.8:
            decision.quality = DecisionQuality.CORRECT
        else:
            # Low confidence but still worked → suboptimal
            decision.quality = DecisionQuality.SUBOPTIMAL
    else:
        # Failed - was it a bad choice?
        if decision.confidence >= 0.8:
            # High confidence but failed → wrong choice
            decision.quality = DecisionQuality.WRONG
        else:
            # Low confidence and failed → suboptimal
            decision.quality = DecisionQuality.SUBOPTIMAL
    
    return decision.quality
