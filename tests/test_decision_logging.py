"""Tests for orchestrator decision logging and traceability."""

import pytest
from datetime import datetime, timezone
from kodo.orchestrators.decision_logging import (
    OrchestratorDecision,
    DecisionSequence,
    DecisionQuality,
    build_decision,
    assess_decision_quality,
)


class TestOrchestratorDecision:
    """Test individual orchestrator decisions."""
    
    def test_create_decision(self):
        """Create a basic decision."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Implement feature X",
        )
        
        assert decision.agent_name == "worker"
        assert decision.task_description == "Implement feature X"
        assert decision.quality == DecisionQuality.UNKNOWN
    
    def test_decision_with_alternatives(self):
        """Decision tracking alternatives considered."""
        decision = OrchestratorDecision(
            agent_name="worker_smart",
            task_description="Complex task",
            alternatives_considered=["worker_fast", "tester"],
        )
        
        assert decision.alternatives_considered == ["worker_fast", "tester"]
    
    def test_decision_confidence_bounds(self):
        """Confidence values are bounded 0-1."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.75,
        )
        
        assert 0.0 <= decision.confidence <= 1.0
    
    def test_decision_serialization(self):
        """Decision can be serialized to dict."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Implement API",
            confidence=0.85,
            cycle_number=1,
            exchange_number=5,
        )
        
        d = decision.to_dict()
        
        assert d["agent"] == "worker"
        assert d["confidence"] == 0.85
        assert d["cycle"] == 1
        assert d["exchange"] == 5
        assert "timestamp" in d
    
    def test_decision_timestamps(self):
        """Decisions are timestamped."""
        before = datetime.now(timezone.utc)
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
        )
        after = datetime.now(timezone.utc)
        
        assert before <= decision.timestamp <= after
    
    def test_decision_with_outcome(self):
        """Decision outcome can be recorded."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
        )
        
        decision.agent_success = True
        decision.agent_completion_time_s = 5.2
        decision.quality = DecisionQuality.CORRECT
        
        assert decision.agent_success is True
        assert decision.agent_completion_time_s == 5.2
        assert decision.quality == DecisionQuality.CORRECT


class TestDecisionSequence:
    """Test sequences of orchestrator decisions."""
    
    def test_create_sequence(self):
        """Create a decision sequence."""
        sequence = DecisionSequence(run_id="run-123")
        
        assert sequence.run_id == "run-123"
        assert sequence.decision_count == 0
    
    def test_add_decisions(self):
        """Add decisions to sequence."""
        sequence = DecisionSequence(run_id="run-123")
        
        d1 = OrchestratorDecision(agent_name="worker_smart", task_description="Task 1")
        d2 = OrchestratorDecision(agent_name="tester", task_description="Task 2")
        
        sequence.add_decision(d1)
        sequence.add_decision(d2)
        
        assert sequence.decision_count == 2
    
    def test_agent_counts(self):
        """Count how many times each agent was chosen."""
        sequence = DecisionSequence(run_id="run-123")
        
        sequence.add_decision(OrchestratorDecision(agent_name="worker_smart", task_description="T1"))
        sequence.add_decision(OrchestratorDecision(agent_name="worker_smart", task_description="T2"))
        sequence.add_decision(OrchestratorDecision(agent_name="tester", task_description="T3"))
        
        counts = sequence.agent_counts
        
        assert counts["worker_smart"] == 2
        assert counts["tester"] == 1
    
    def test_decision_quality_counts(self):
        """Count decisions by quality."""
        sequence = DecisionSequence(run_id="run-123")
        
        d1 = OrchestratorDecision(agent_name="worker", task_description="T1")
        d1.quality = DecisionQuality.CORRECT
        
        d2 = OrchestratorDecision(agent_name="worker", task_description="T2")
        d2.quality = DecisionQuality.WRONG
        
        d3 = OrchestratorDecision(agent_name="worker", task_description="T3")
        # d3 stays UNKNOWN
        
        sequence.add_decision(d1)
        sequence.add_decision(d2)
        sequence.add_decision(d3)
        
        counts = sequence.decision_quality_counts
        
        assert counts["correct"] == 1
        assert counts["wrong"] == 1
        assert counts["unknown"] == 1
    
    def test_average_confidence(self):
        """Calculate average confidence."""
        sequence = DecisionSequence(run_id="run-123")
        
        sequence.add_decision(OrchestratorDecision(
            agent_name="worker",
            task_description="T1",
            confidence=0.9,
        ))
        sequence.add_decision(OrchestratorDecision(
            agent_name="worker",
            task_description="T2",
            confidence=0.7,
        ))
        
        # (0.9 + 0.7) / 2 = 0.8
        assert sequence.average_confidence == 0.8
    
    def test_average_agent_time(self):
        """Calculate average agent completion time."""
        sequence = DecisionSequence(run_id="run-123")
        
        d1 = OrchestratorDecision(agent_name="worker", task_description="T1")
        d1.agent_completion_time_s = 10.0
        
        d2 = OrchestratorDecision(agent_name="worker", task_description="T2")
        d2.agent_completion_time_s = 20.0
        
        sequence.add_decision(d1)
        sequence.add_decision(d2)
        
        # (10 + 20) / 2 = 15
        assert sequence.average_agent_time_s == 15.0
    
    def test_success_rate(self):
        """Calculate success rate."""
        sequence = DecisionSequence(run_id="run-123")
        
        d1 = OrchestratorDecision(agent_name="worker", task_description="T1")
        d1.agent_success = True
        
        d2 = OrchestratorDecision(agent_name="worker", task_description="T2")
        d2.agent_success = True
        
        d3 = OrchestratorDecision(agent_name="worker", task_description="T3")
        d3.agent_success = False
        
        sequence.add_decision(d1)
        sequence.add_decision(d2)
        sequence.add_decision(d3)
        
        # 2 successes / 3 total = 66.7%
        assert sequence.success_rate == pytest.approx(66.7, rel=0.1)
    
    def test_duration(self):
        """Track sequence duration."""
        sequence = DecisionSequence(run_id="run-123")
        
        # Should have some duration even before marking complete
        import time
        time.sleep(0.01)
        sequence.mark_complete()
        
        assert sequence.duration_s >= 0.01
    
    def test_summary(self):
        """Get run summary statistics."""
        sequence = DecisionSequence(run_id="run-123")
        
        d = OrchestratorDecision(agent_name="worker", task_description="Task")
        d.agent_success = True
        d.agent_completion_time_s = 5.0
        d.quality = DecisionQuality.CORRECT
        
        sequence.add_decision(d)
        sequence.mark_complete()
        
        summary = sequence.get_summary()
        
        assert summary["run_id"] == "run-123"
        assert summary["decisions_made"] == 1
        assert summary["success_rate"] == 100.0
        assert summary["agents_used"]["worker"] == 1


class TestBuildDecision:
    """Test decision builder function."""
    
    def test_build_minimal_decision(self):
        """Build decision with minimal arguments."""
        decision = build_decision(
            agent_name="worker",
            task_description="Task",
        )
        
        assert decision.agent_name == "worker"
        assert decision.task_description == "Task"
    
    def test_build_with_alternatives(self):
        """Build decision with alternatives."""
        decision = build_decision(
            agent_name="worker_smart",
            task_description="Complex task",
            alternatives=["worker_fast", "tester"],
        )
        
        assert decision.alternatives_considered == ["worker_fast", "tester"]
    
    def test_build_with_confidence(self):
        """Build decision with confidence."""
        decision = build_decision(
            agent_name="worker",
            task_description="Task",
            confidence=0.85,
        )
        
        assert decision.confidence == 0.85
    
    def test_build_with_cycle_info(self):
        """Build decision with cycle information."""
        decision = build_decision(
            agent_name="worker",
            task_description="Task",
            cycle=2,
            exchange=5,
        )
        
        assert decision.cycle_number == 2
        assert decision.exchange_number == 5
    
    def test_build_clamps_confidence(self):
        """Builder clamps invalid confidence values."""
        decision = build_decision(
            agent_name="worker",
            task_description="Task",
            confidence=1.5,  # Invalid: > 1.0
        )
        
        assert decision.confidence == 1.0
        
        decision = build_decision(
            agent_name="worker",
            task_description="Task",
            confidence=-0.5,  # Invalid: < 0.0
        )
        
        assert decision.confidence == 0.0


class TestAssessQuality:
    """Test decision quality assessment."""
    
    def test_assess_success_high_confidence(self):
        """High confidence + success = CORRECT."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.9,
        )
        
        quality = assess_decision_quality(
            decision=decision,
            agent_succeeded=True,
        )
        
        assert quality == DecisionQuality.CORRECT
        assert decision.agent_success is True
    
    def test_assess_success_low_confidence(self):
        """Low confidence + success = SUBOPTIMAL."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.5,
        )
        
        quality = assess_decision_quality(
            decision=decision,
            agent_succeeded=True,
        )
        
        assert quality == DecisionQuality.SUBOPTIMAL
    
    def test_assess_failure_high_confidence(self):
        """High confidence + failure = WRONG."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.9,
        )
        
        quality = assess_decision_quality(
            decision=decision,
            agent_succeeded=False,
            agent_error="Timeout",
        )
        
        assert quality == DecisionQuality.WRONG
        assert decision.agent_error == "Timeout"
    
    def test_assess_failure_low_confidence(self):
        """Low confidence + failure = SUBOPTIMAL."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.3,
        )
        
        quality = assess_decision_quality(
            decision=decision,
            agent_succeeded=False,
        )
        
        assert quality == DecisionQuality.SUBOPTIMAL
    
    def test_assess_with_error_details(self):
        """Assessment captures error details."""
        decision = OrchestratorDecision(
            agent_name="worker",
            task_description="Task",
            confidence=0.8,
        )
        
        error_msg = "Context overflow"
        assess_decision_quality(
            decision=decision,
            agent_succeeded=False,
            agent_error=error_msg,
        )
        
        assert decision.agent_error == error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
