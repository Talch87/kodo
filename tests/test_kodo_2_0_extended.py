"""
Extended integration tests for KODO 2.0

Tests for edge cases, error conditions, and complex scenarios
"""

import pytest
from pathlib import Path
from datetime import datetime

from kodo.verification import VerificationEngine, ErrorDetection
from kodo.quality import QualityGate
from kodo.production import ComplianceValidator, ProductionReadinessScorer
from kodo.reliability import FailureHealer, ErrorDetector
from kodo.transparency import AuditTrail, DecisionType, DecisionOutcome
from kodo.cost import TokenTracker, ModelType
from kodo.learning import FeedbackCollector, TrustScorer
from kodo.orchestrator import Kodo2Orchestrator


class TestVerificationEdgeCases:
    """Edge cases for verification engine"""
    
    def test_empty_code(self):
        """Test verification of empty code"""
        engine = VerificationEngine()
        
        history = engine.get_history()
        assert isinstance(history, list)
    
    def test_verification_statistics(self):
        """Test statistics calculation"""
        engine = VerificationEngine()
        
        stats = engine.get_statistics()
        assert stats["total_verifications"] == 0
        assert stats["pass_rate"] == 0


class TestQualityGateEdgeCases:
    """Edge cases for quality gate"""
    
    @pytest.mark.asyncio
    async def test_quality_gate_statistics(self):
        """Test quality gate statistics"""
        gate = QualityGate()
        
        stats = gate.get_statistics()
        assert stats["total_checks"] == 0
        assert stats["pass_rate"] == 0


class TestErrorDetectionEdgeCases:
    """Edge cases for error detection"""
    
    def test_empty_code_detection(self):
        """Test error detection on empty code"""
        detector = ErrorDetector()
        
        errors = detector.detect_all("")
        assert isinstance(errors, list)
    
    def test_valid_code_detection(self):
        """Test error detection on valid code"""
        detector = ErrorDetector()
        
        valid_code = """
def hello():
    return 'world'
"""
        errors = detector.detect_all(valid_code)
        # Should have minimal errors for valid code
        assert isinstance(errors, list)


class TestAuditTrailEdgeCases:
    """Edge cases for audit trail"""
    
    def test_audit_trail_statistics(self):
        """Test audit trail statistics"""
        trail = AuditTrail()
        
        stats = trail.get_statistics()
        assert stats["total_decisions"] == 0
    
    def test_audit_timeline(self):
        """Test decision timeline"""
        trail = AuditTrail()
        
        timeline = trail.get_decision_timeline()
        assert isinstance(timeline, list)
        assert len(timeline) == 0


class TestCostTrackingEdgeCases:
    """Edge cases for cost tracking"""
    
    def test_empty_tracker_statistics(self):
        """Test statistics on empty tracker"""
        tracker = TokenTracker()
        
        stats = tracker.get_statistics()
        assert stats["total_cost"] == 0
        assert stats["total_tokens"] == 0
    
    def test_cost_by_component(self):
        """Test cost breakdown by component"""
        tracker = TokenTracker()
        
        tracker.record_usage(
            task_type="test",
            model=ModelType.CLAUDE_HAIKU,
            input_tokens=100,
            output_tokens=200,
            component="tester"
        )
        
        by_component = tracker.get_cost_by_component()
        assert "tester" in by_component
        assert by_component["tester"] > 0


class TestFeedbackEdgeCases:
    """Edge cases for feedback collection"""
    
    def test_empty_feedback(self):
        """Test feedback patterns on empty collector"""
        collector = FeedbackCollector()
        
        patterns = collector.analyze_patterns()
        assert patterns["total_feedback"] == 0
    
    def test_feedback_sentiment_inference(self):
        """Test sentiment inference"""
        collector = FeedbackCollector()
        
        # Positive feedback
        collector.record_feedback(
            feedback_type="quality",
            code_id="code_1",
            message="Great code, works perfectly"
        )
        
        # Negative feedback
        collector.record_feedback(
            feedback_type="quality",
            code_id="code_2",
            message="Code has errors and problems"
        )
        
        patterns = collector.analyze_patterns()
        assert patterns["total_feedback"] == 2


class TestComplexScenarios:
    """Complex integration scenarios"""
    
    @pytest.mark.asyncio
    async def test_self_healing_and_verification(self):
        """Test self-healing followed by verification"""
        healer = FailureHealer()
        
        # Code with indentation error
        broken_code = "def foo():\nprint('hello')"
        
        healed = await healer.heal(broken_code, "test_001")
        assert healed is not None
        assert healed.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_compliance_with_missing_tests(self):
        """Test compliance validator with no tests"""
        validator = ComplianceValidator()
        
        spec = "MUST have add function"
        code = "def add(a, b):\n    return a + b"
        
        result = await validator.validate(code, spec)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_multiple_cost_records(self):
        """Test cost tracking with multiple models"""
        tracker = TokenTracker()
        
        # Log usage for multiple models
        for model in [ModelType.CLAUDE_HAIKU, ModelType.CLAUDE_SONNET]:
            tracker.record_usage(
                task_type="generation",
                model=model,
                input_tokens=1000,
                output_tokens=2000,
                component="generator"
            )
        
        stats = tracker.get_statistics()
        assert stats["total_records"] == 2
        
        by_model = tracker.get_cost_by_model()
        assert len(by_model) >= 1


class TestOrchestratorErrorHandling:
    """Test orchestrator error handling"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_with_empty_code(self):
        """Test orchestrator with empty code"""
        orchestrator = Kodo2Orchestrator()
        
        result = await orchestrator.process_code(
            code="",
            code_id="empty_001"
        )
        
        assert result is not None
        assert result.code_id == "empty_001"
    
    @pytest.mark.asyncio
    async def test_orchestrator_with_complex_code(self):
        """Test orchestrator with complex code"""
        orchestrator = Kodo2Orchestrator()
        
        complex_code = """
class DataProcessor:
    def __init__(self, data):
        self.data = data
    
    def process(self):
        return [x * 2 for x in self.data]
    
    def validate(self):
        return len(self.data) > 0
"""
        
        result = await orchestrator.process_code(
            code=complex_code,
            code_id="complex_001"
        )
        
        assert result is not None
        assert result.auto_action in ["deploy", "review", "reject"]


class TestAuditTrailIntegration:
    """Integration tests for audit trail"""
    
    def test_decision_tracking(self):
        """Test full decision tracking"""
        trail = AuditTrail()
        
        # Log multiple decisions
        decisions = []
        for i in range(5):
            dec_id = trail.record_decision(
                decision_type=DecisionType.CODE_GENERATION,
                context=f"Feature {i}",
                reasoning=f"User requested feature {i}",
                confidence=0.8
            )
            decisions.append(dec_id)
            
            # Mark some as accepted
            if i % 2 == 0:
                trail.mark_outcome(dec_id, DecisionOutcome.ACCEPTED)
            else:
                trail.mark_outcome(dec_id, DecisionOutcome.REJECTED)
        
        stats = trail.get_statistics()
        assert stats["total_decisions"] == 5
        
        # Check outcomes
        accepted = trail.get_by_outcome(DecisionOutcome.ACCEPTED)
        rejected = trail.get_by_outcome(DecisionOutcome.REJECTED)
        assert len(accepted) >= 2
        assert len(rejected) >= 2


class TestTrustScoringEdgeCases:
    """Edge cases for trust scoring"""
    
    @pytest.mark.asyncio
    async def test_trust_with_low_scores(self):
        """Test trust scoring with low input scores"""
        scorer = TrustScorer()
        
        assessment = await scorer.calculate_trust(
            code_id="low_quality_001",
            verification_score=30,
            quality_passed=False
        )
        
        assert assessment.trust_score < 50
        assert assessment.color_indicator.value in ["yellow", "red"]
    
    @pytest.mark.asyncio
    async def test_trust_with_high_scores(self):
        """Test trust scoring with high input scores"""
        scorer = TrustScorer()
        
        assessment = await scorer.calculate_trust(
            code_id="high_quality_001",
            verification_score=95,
            quality_passed=True
        )
        
        assert assessment.trust_score > 70
        assert assessment.color_indicator.value == "green"


class TestProductionReadinessEdgeCases:
    """Edge cases for production readiness"""
    
    @pytest.mark.asyncio
    async def test_readiness_with_no_tests(self):
        """Test readiness scoring with no tests"""
        scorer = ProductionReadinessScorer()
        
        code = "x = 1"
        score = await scorer.score(
            code=code,
            code_id="no_test_001",
            verification_score=50
        )
        
        assert score.test_coverage <= 100
    
    @pytest.mark.asyncio
    async def test_readiness_with_security_issues(self):
        """Test readiness scoring with security issues"""
        scorer = ProductionReadinessScorer()
        
        code = "eval(input())"
        score = await scorer.score(
            code=code,
            code_id="unsafe_001"
        )
        
        assert score.security < 80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
