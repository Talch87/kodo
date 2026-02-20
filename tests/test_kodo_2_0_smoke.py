"""KODO 2.0 Smoke Tests: Verify all 10 pillars exist and are importable

This is the integration test for KODO 2.0: Autonomous Development System.
It verifies that all 10 strategic pillars can be imported and instantiated.
"""

import pytest


def test_pillar_1_self_verification_imports():
    """Pillar 1: Self-Verification Engine - Auto-test code, score 0-100%"""
    from kodo.verification import VerificationEngine, CorrectnessScorer, TestRunner
    assert VerificationEngine is not None
    assert CorrectnessScorer is not None
    assert TestRunner is not None
    engine = VerificationEngine()
    assert engine is not None


def test_pillar_2_quality_gate_imports():
    """Pillar 2: Autonomous Quality Gate - 7-point checklist, auto-merge/reject"""
    from kodo.quality import QualityGate, QualityChecker, CheckPoint
    assert QualityGate is not None
    assert QualityChecker is not None
    assert CheckPoint is not None
    gate = QualityGate()
    assert gate is not None


def test_pillar_3_compliance_validator_imports():
    """Pillar 3: Specification Compliance Validator - Spec→Code→Test mapping"""
    from kodo.production import ComplianceValidator
    assert ComplianceValidator is not None
    validator = ComplianceValidator()
    assert validator is not None


def test_pillar_4_production_readiness_imports():
    """Pillar 4: Production Readiness Scorer - Composite scoring, confidence"""
    from kodo.production import ProductionReadinessScorer
    assert ProductionReadinessScorer is not None
    scorer = ProductionReadinessScorer()
    assert scorer is not None


def test_pillar_5_failure_healing_imports():
    """Pillar 5: Failure Self-Healing - Auto-detect & fix errors"""
    from kodo.reliability import FailureHealer, ErrorDetector, ErrorType, ErrorDetection
    assert FailureHealer is not None
    assert ErrorDetector is not None
    assert ErrorType is not None
    assert ErrorDetection is not None
    healer = FailureHealer()
    assert healer is not None


def test_pillar_6_audit_trail_imports():
    """Pillar 6: Decision Audit Trail - Log decisions with reasoning"""
    from kodo.transparency import (
        AuditTrail, DecisionLogger, DecisionType, DecisionOutcome
    )
    assert AuditTrail is not None
    assert DecisionLogger is not None
    assert DecisionType is not None
    assert DecisionOutcome is not None
    logger = DecisionLogger()
    assert logger is not None


def test_pillar_7_cost_optimization_imports():
    """Pillar 7: Cost Optimization - Track tokens, suggest models"""
    from kodo.cost import TokenTracker, CostOptimizer, ModelType
    assert TokenTracker is not None
    assert CostOptimizer is not None
    assert ModelType is not None
    tracker = TokenTracker()
    assert tracker is not None


def test_pillar_8_feedback_loop_imports():
    """Pillar 8: Production Feedback Loop - Collect metrics, analyze patterns"""
    from kodo.learning import FeedbackCollector, FeedbackType
    assert FeedbackCollector is not None
    assert FeedbackType is not None
    collector = FeedbackCollector()
    assert collector is not None


def test_pillar_9_trust_score_imports():
    """Pillar 9: Human Trust Score - 0-100% confidence, Green/Yellow/Red"""
    from kodo.learning import TrustScorer
    assert TrustScorer is not None
    scorer = TrustScorer()
    assert scorer is not None


def test_pillar_10_improvement_imports():
    """Pillar 10: Autonomous Improvement - Post-analysis, pattern extraction"""
    from kodo.learning import CycleRecord, CycleLearner, AutomatedImprovement
    assert CycleRecord is not None
    assert CycleLearner is not None
    assert AutomatedImprovement is not None
    learner = CycleLearner()
    assert learner is not None


def test_all_10_pillars_together():
    """Integration: All 10 pillars can be instantiated in sequence"""
    from kodo.verification import VerificationEngine
    from kodo.quality import QualityGate
    from kodo.production import ComplianceValidator, ProductionReadinessScorer
    from kodo.reliability import FailureHealer
    from kodo.transparency import DecisionLogger
    from kodo.cost import CostOptimizer
    from kodo.learning import FeedbackCollector, TrustScorer, CycleLearner
    
    # Instantiate all pillars
    pillars = {
        "Verification": VerificationEngine(),
        "QualityGate": QualityGate(),
        "Compliance": ComplianceValidator(),
        "Readiness": ProductionReadinessScorer(),
        "Healing": FailureHealer(),
        "Audit": DecisionLogger(),
        "Cost": CostOptimizer(),
        "Feedback": FeedbackCollector(),
        "Trust": TrustScorer(),
        "Improvement": CycleLearner(),
    }
    
    # Verify all are instantiated
    for name, pillar in pillars.items():
        assert pillar is not None, f"Pillar {name} failed to instantiate"
    
    assert len(pillars) == 10, "All 10 pillars should be present"


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v"])
