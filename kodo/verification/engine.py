"""
Self-Verification Engine: Auto-test code, score correctness, auto-reject if <90%
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from .scorer import CorrectnessScorer, ScoreMetrics
from .test_runner import TestRunner, TestResult


class VerificationStatus(str, Enum):
    """Status of verification"""
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    REJECTED = "rejected"


@dataclass
class TestScore:
    """Score of a single test"""
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    output: str = ""
    confidence: float = 1.0  # 0-1, how confident are we in this test result


@dataclass
class VerificationResult:
    """Result of verification for code"""
    code_id: str
    timestamp: datetime
    status: VerificationStatus
    correctness_score: float  # 0-100
    confidence_level: float  # 0-100
    test_results: List[TestScore] = field(default_factory=list)
    metrics: Optional[ScoreMetrics] = None
    decision: str = ""  # Why was it accepted/rejected
    auto_rejected: bool = False  # Was it auto-rejected due to low score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "code_id": self.code_id,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "correctness_score": self.correctness_score,
            "confidence_level": self.confidence_level,
            "test_results": [
                {
                    "name": t.name,
                    "passed": t.passed,
                    "duration_ms": t.duration_ms,
                    "error": t.error,
                    "output": t.output[:200],  # Truncate output
                    "confidence": t.confidence,
                }
                for t in self.test_results
            ],
            "metrics": asdict(self.metrics) if self.metrics else None,
            "decision": self.decision,
            "auto_rejected": self.auto_rejected,
        }


class VerificationEngine:
    """
    Core verification engine: runs tests, scores code, auto-rejects if <90%
    """

    def __init__(
        self,
        min_pass_score: float = 90.0,
        test_runner: Optional[TestRunner] = None,
        scorer: Optional[CorrectnessScorer] = None,
    ):
        """
        Initialize verification engine
        
        Args:
            min_pass_score: Minimum score to pass (0-100), default 90%
            test_runner: Custom test runner, uses default if not provided
            scorer: Custom scorer, uses default if not provided
        """
        if not 0 <= min_pass_score <= 100:
            raise ValueError("min_pass_score must be between 0 and 100")
        
        self.min_pass_score = min_pass_score
        self.test_runner = test_runner or TestRunner()
        self.scorer = scorer or CorrectnessScorer()
        self.verification_history: List[VerificationResult] = []

    async def verify(
        self,
        code: str,
        code_id: str,
        test_code: str,
        test_files: Optional[List[Path]] = None,
    ) -> VerificationResult:
        """
        Verify code by running tests and scoring
        
        Args:
            code: Code to verify
            code_id: Unique identifier for code
            test_code: Test code to run
            test_files: Optional test files to run
            
        Returns:
            VerificationResult with score and decision
        """
        timestamp = datetime.now()
        
        try:
            # Run tests
            test_results = await self.test_runner.run_tests(
                code=code,
                test_code=test_code,
                test_files=test_files,
            )
            
            # Score results
            metrics = self.scorer.score(test_results)
            correctness_score = metrics.overall_score
            
            # Make decision
            auto_rejected = correctness_score < self.min_pass_score
            
            if auto_rejected:
                status = VerificationStatus.REJECTED
                decision = f"Auto-rejected: score {correctness_score:.1f}% < {self.min_pass_score}%"
            elif correctness_score >= self.min_pass_score:
                status = VerificationStatus.PASSED
                decision = f"Passed: score {correctness_score:.1f}% >= {self.min_pass_score}%"
            else:
                status = VerificationStatus.PARTIAL
                decision = f"Partial: some tests failed but above minimum threshold"
            
            # Calculate confidence based on test consistency
            confidence = self._calculate_confidence(test_results, metrics)
            
            result = VerificationResult(
                code_id=code_id,
                timestamp=timestamp,
                status=status,
                correctness_score=correctness_score,
                confidence_level=confidence,
                test_results=test_results,
                metrics=metrics,
                decision=decision,
                auto_rejected=auto_rejected,
            )
            
            self.verification_history.append(result)
            return result
            
        except Exception as e:
            # Handle verification errors
            result = VerificationResult(
                code_id=code_id,
                timestamp=timestamp,
                status=VerificationStatus.FAILED,
                correctness_score=0,
                confidence_level=0,
                decision=f"Verification failed: {str(e)}",
                auto_rejected=True,
            )
            self.verification_history.append(result)
            return result

    def _calculate_confidence(
        self,
        test_results: List[TestScore],
        metrics: ScoreMetrics,
    ) -> float:
        """
        Calculate confidence level (0-100) based on test results
        
        Factors:
        - Test pass rate consistency
        - Test duration variance (too fast = might be mocked)
        - Number of tests
        - Error patterns
        """
        if not test_results:
            return 0.0
        
        # Pass rate consistency
        pass_count = sum(1 for t in test_results if t.passed)
        pass_rate = pass_count / len(test_results)
        
        # Penalize extreme pass rates (0% or 100%) slightly as they might indicate issues
        rate_confidence = min(pass_rate, 1.0 - pass_rate) * 100 if pass_rate != 0.5 else 100
        
        # Test count confidence (more tests = higher confidence, up to 20 tests)
        test_count_confidence = min(len(test_results) / 20, 1.0) * 100
        
        # Duration variance check
        durations = [t.duration_ms for t in test_results if t.duration_ms > 0]
        if len(durations) > 1:
            avg_duration = sum(durations) / len(durations)
            variance = sum((d - avg_duration) ** 2 for d in durations) / len(durations)
            std_dev = variance ** 0.5
            # If std dev is 0, suspicious (all same duration)
            duration_confidence = min(std_dev / avg_duration * 50, 100) if std_dev > 0 else 50
        else:
            duration_confidence = 50  # Neutral if we can't calculate variance
        
        # Error rate confidence
        error_rate = sum(1 for t in test_results if t.error) / len(test_results)
        error_confidence = (1.0 - error_rate) * 100
        
        # Overall confidence (weighted average)
        confidence = (
            pass_rate * 0.4 +  # Pass rate is most important
            test_count_confidence * 0.2 / 100 +
            duration_confidence * 0.2 / 100 +
            error_confidence * 0.2 / 100
        ) * 100
        
        return min(max(confidence, 0), 100)

    def get_history(self) -> List[VerificationResult]:
        """Get verification history"""
        return self.verification_history.copy()

    def clear_history(self) -> None:
        """Clear verification history"""
        self.verification_history.clear()

    def export_results(self, filepath: Path) -> None:
        """Export verification results to JSON"""
        results = [r.to_dict() for r in self.verification_history]
        with open(filepath, "w") as f:
            json.dump(results, f, indent=2)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics from verification history"""
        if not self.verification_history:
            return {
                "total_verifications": 0,
                "passed": 0,
                "failed": 0,
                "average_score": 0,
                "auto_rejected": 0,
            }
        
        passed = sum(1 for r in self.verification_history if not r.auto_rejected)
        failed = sum(1 for r in self.verification_history if r.auto_rejected)
        avg_score = sum(r.correctness_score for r in self.verification_history) / len(
            self.verification_history
        )
        
        return {
            "total_verifications": len(self.verification_history),
            "passed": passed,
            "failed": failed,
            "average_score": avg_score,
            "auto_rejected": failed,
            "pass_rate": passed / len(self.verification_history),
        }
