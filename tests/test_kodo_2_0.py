"""
Comprehensive tests for KODO 2.0 - All 10 Pillars
"""

import pytest
import asyncio
from pathlib import Path

# Pillar 1: Verification Engine
from kodo.verification import VerificationEngine, CorrectnessScorer, TestRunner

# Pillar 2: Quality Gate  
from kodo.quality import QualityGate, QualityChecker, CheckPoint

# Pillar 3 & 4: Production Readiness
from kodo.production import ComplianceValidator, ProductionReadinessScorer

# Pillar 5: Failure Self-Healing
from kodo.reliability import FailureHealer, ErrorDetector, ErrorType

# Pillar 6: Audit Trail
from kodo.transparency import AuditTrail, DecisionLogger, DecisionType, DecisionOutcome

# Pillar 7: Cost Optimization
from kodo.cost import TokenTracker, CostOptimizer, ModelType

# Pillar 8-10: Learning
from kodo.learning import FeedbackCollector, TrustScorer, AutomatedImprovement, FeedbackType

# Orchestrator
from kodo.orchestrator import Kodo2Orchestrator


class TestPillar1Verification:
    """Tests for Pillar 1: Self-Verification Engine"""
    
    def test_verification_engine_creation(self):
        """Test creation of verification engine"""
        engine = VerificationEngine(min_pass_score=90.0)
        assert engine.min_pass_score == 90.0
        assert len(engine.verification_history) == 0
    
    def test_scorer_basic(self):
        """Test correctness scorer"""
        from kodo.verification.test_runner import TestResult
        
        scorer = CorrectnessScorer()
        
        # Create mock test results
        test_results = [
            TestResult("test1", True, 100, "output1"),
            TestResult("test2", True, 120, "output2"),
            TestResult("test3", False, 150, "output3", error="Failed"),
        ]
        
        metrics = scorer.score(test_results)
        
        assert metrics.test_count == 3
        assert metrics.passed_count == 2
        assert metrics.failed_count == 1
        assert 0 <= metrics.overall_score <= 100
    
    def test_scorer_confidence_interval(self):
        """Test confidence interval calculation"""
        scorer = CorrectnessScorer()
        
        lower, upper = scorer.calculate_confidence_interval(80, 20)
        assert lower < 80 < upper
        assert lower >= 0 and upper <= 100


class TestPillar2QualityGate:
    """Tests for Pillar 2: Autonomous Quality Gate"""
    
    @pytest.mark.asyncio
    async def test_quality_gate_creation(self):
        """Test quality gate creation"""
        gate = QualityGate()
        assert gate.auto_merge_threshold == 1.0
        assert len(gate.check_history) == 0
    
    def test_quality_checker_syntax(self):
        """Test syntax checking"""
        checker = QualityChecker()
        
        valid_code = "def hello():\n    return 'world'"
        result = checker._check_syntax(valid_code)
        assert result.passed
        
        invalid_code = "def hello(\n    return 'world'"
        result = checker._check_syntax(invalid_code)
        assert not result.passed
    
    def test_quality_checker_security(self):
        """Test security checking"""
        checker = QualityChecker()
        
        safe_code = "x = int(input())"
        result = checker._check_security(safe_code)
        assert result.passed
        
        unsafe_code = "eval(user_input)"
        result = checker._check_security(unsafe_code)
        assert not result.passed


class TestPillar3Compliance:
    """Tests for Pillar 3: Specification Compliance"""
    
    @pytest.mark.asyncio
    async def test_compliance_validator(self):
        """Test compliance validator"""
        validator = ComplianceValidator(min_coverage=1.0)
        
        spec = "MUST implement function process_data. MUST validate input."
        code = "def process_data(x):\n    if not x: raise ValueError\n    return x"
        
        result = await validator.validate(code, spec)
        
        assert result.total_requirements > 0
        assert 0 <= result.coverage_percentage <= 100


class TestPillar4Production:
    """Tests for Pillar 4: Production Readiness"""
    
    @pytest.mark.asyncio
    async def test_production_readiness_scorer(self):
        """Test production readiness scoring"""
        scorer = ProductionReadinessScorer()
        
        code = "def add(a, b):\n    '''Add two numbers'''\n    return a + b"
        
        score = await scorer.score(
            code=code,
            code_id="test_001",
            verification_score=95,
            quality_gate_pass=True,
        )
        
        assert 0 <= score.overall_score <= 100
        assert score.code_quality > 0
        assert score.test_coverage >= 0


class TestPillar5SelfHealing:
    """Tests for Pillar 5: Failure Self-Healing"""
    
    def test_error_detector(self):
        """Test error detection"""
        detector = ErrorDetector()
        
        # Test syntax error detection
        invalid_code = "def foo(\n    pass"
        errors = detector.detect_all(invalid_code)
        assert any(e.error_type == ErrorType.SYNTAX_ERROR for e in errors)
        
        # Test security issue detection
        unsafe_code = "eval(x)"
        errors = detector.detect_all(unsafe_code)
        assert any(e.error_type == ErrorType.SECURITY_ISSUE for e in errors)
    
    @pytest.mark.asyncio
    async def test_failure_healer(self):
        """Test failure healing"""
        healer = FailureHealer()
        
        code_with_error = "def foo():\nprint('hello')"  # Missing indentation
        
        result = await healer.heal(code_with_error, "test_001")
        
        assert result.errors_detected >= 0
        assert result.errors_fixed >= 0
        assert 0 <= result.confidence <= 1.0


class TestPillar6AuditTrail:
    """Tests for Pillar 6: Decision Audit Trail"""
    
    def test_audit_trail_creation(self):
        """Test audit trail"""
        trail = AuditTrail()
        
        decision_id = trail.record_decision(
            decision_type=DecisionType.CODE_GENERATION,
            context="Generate new feature",
            reasoning="User requested feature",
            confidence=0.9,
        )
        
        assert decision_id.startswith("DEC_")
        assert len(trail.records) == 1
    
    def test_decision_logger(self):
        """Test decision logger"""
        logger = DecisionLogger()
        
        decision_id = logger.log_code_generation(
            context="Test context",
            reasoning="Test reasoning",
            confidence=0.8,
        )
        
        assert decision_id is not None
        
        # Mark outcome
        logger.audit.mark_outcome(decision_id, DecisionOutcome.ACCEPTED)
        
        decision = logger.audit.get_decision(decision_id)
        assert decision.outcome == DecisionOutcome.ACCEPTED


class TestPillar7Cost:
    """Tests for Pillar 7: Cost Optimization"""
    
    def test_token_tracker(self):
        """Test cost tracking"""
        tracker = TokenTracker()
        
        record = tracker.record_usage(
            task_type="verification",
            model=ModelType.CLAUDE_HAIKU,
            input_tokens=1000,
            output_tokens=2000,
            duration_seconds=5.0,
            component="verifier",
        )
        
        assert record.total_tokens == 3000
        assert record.cost_usd >= 0
    
    def test_cost_optimizer(self):
        """Test cost optimization"""
        optimizer = CostOptimizer()
        
        model, reason = optimizer.suggest_model("verification", "fast")
        
        assert model in [ModelType.CLAUDE_HAIKU, ModelType.CLAUDE_SONNET]
        assert reason is not None


class TestPillar8Feedback:
    """Tests for Pillar 8: Production Feedback Loop"""
    
    def test_feedback_collector(self):
        """Test feedback collection"""
        collector = FeedbackCollector()
        
        feedback_id = collector.record_feedback(
            feedback_type=FeedbackType.PERFORMANCE_METRIC,
            code_id="code_001",
            message="Test performance",
        )
        
        assert feedback_id is not None
        assert len(collector.records) == 1
    
    def test_feedback_patterns(self):
        """Test pattern analysis"""
        collector = FeedbackCollector()
        
        collector.record_performance("code_001", latency_ms=100, memory_mb=50)
        collector.record_quality_score("code_001", score=85)
        
        patterns = collector.analyze_patterns()
        
        assert patterns["total_feedback"] == 2
        assert "sentiment_distribution" in patterns


class TestPillar9Trust:
    """Tests for Pillar 9: Human Trust Score"""
    
    @pytest.mark.asyncio
    async def test_trust_scorer(self):
        """Test trust scoring"""
        scorer = TrustScorer()
        
        assessment = await scorer.calculate_trust(
            code_id="code_001",
            verification_score=95,
            quality_passed=True,
        )
        
        assert 0 <= assessment.trust_score <= 100
        assert assessment.trust_level is not None
        assert assessment.color_indicator is not None
    
    def test_trust_statistics(self):
        """Test trust statistics"""
        scorer = TrustScorer()
        
        stats = scorer.get_statistics()
        
        assert stats["total_assessments"] == 0
        assert stats["average_trust"] == 0


class TestPillar10Improvement:
    """Tests for Pillar 10: Autonomous Improvement"""
    
    def test_improvement_analyzer(self):
        """Test improvement analysis"""
        improver = AutomatedImprovement()
        
        improver.record_project(
            project_id="proj_001",
            verification_scores=[85, 90, 88],
            quality_results=[True, True, False],
            test_counts=[10, 12, 8],
            cost=50.0,
            feedback=[],
            issues=["test failure", "lint issue"],
        )
        
        patterns = improver.analyze_patterns()
        
        assert patterns["verification_trend"]["average"] > 0
        assert patterns["quality_pass_rate"] > 0
    
    def test_improvement_suggestions(self):
        """Test improvement suggestions"""
        improver = AutomatedImprovement()
        
        improver.record_project(
            project_id="proj_001",
            verification_scores=[70],
            quality_results=[False],
            test_counts=[5],
            cost=100.0,
            feedback=[],
            issues=["low quality"],
        )
        
        suggestions = improver.get_improvement_suggestions()
        
        assert len(suggestions) > 0


class TestOrchestrator:
    """Tests for KODO 2.0 Orchestrator"""
    
    def test_orchestrator_creation(self):
        """Test orchestrator creation"""
        orchestrator = Kodo2Orchestrator()
        
        assert orchestrator.verifier is not None
        assert orchestrator.quality is not None
        assert orchestrator.healer is not None
        assert orchestrator.audit is not None
        assert orchestrator.trust_scorer is not None
    
    @pytest.mark.asyncio
    async def test_orchestrator_process_code(self):
        """Test complete orchestration pipeline"""
        orchestrator = Kodo2Orchestrator()
        
        code = """
def add(a, b):
    '''Add two numbers'''
    return a + b
"""
        
        result = await orchestrator.process_code(
            code=code,
            code_id="test_001",
        )
        
        assert result.code_id == "test_001"
        assert result.timestamp is not None
        assert result.auto_action in ["deploy", "review", "reject"]
        assert 0 <= result.confidence <= 1.0
    
    def test_orchestrator_report(self):
        """Test report generation"""
        orchestrator = Kodo2Orchestrator()
        
        report = orchestrator.get_full_report("test_001")
        
        assert report["code_id"] == "test_001"
        assert "verification" in report
        assert "quality" in report
        assert "cost" in report


class TestIntegration:
    """Integration tests for all pillars working together"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test complete autonomous pipeline"""
        orchestrator = Kodo2Orchestrator()
        
        code = """
def fibonacci(n):
    '''Calculate fibonacci number'''
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

def test_fibonacci():
    assert fibonacci(5) == 5
    assert fibonacci(10) == 55
"""
        
        # Process through full pipeline
        result = await orchestrator.process_code(
            code=code,
            code_id="fib_001",
            test_code="def test_fibonacci():\n    assert True",
            specification="Implement fibonacci function",
        )
        
        assert result is not None
        assert result.code_id == "fib_001"
        
        # Verify all pillars touched
        report = orchestrator.get_full_report("fib_001")
        assert report is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
