"""
Correctness Scorer: Score test results and code quality
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class ScoringCategory(str, Enum):
    """Scoring categories"""
    UNIT_TESTS = "unit_tests"
    INTEGRATION_TESTS = "integration_tests"
    EDGE_CASES = "edge_cases"
    ERROR_HANDLING = "error_handling"
    PERFORMANCE = "performance"


@dataclass
class ScoreMetrics:
    """Metrics used for scoring"""
    overall_score: float  # 0-100
    test_pass_rate: float  # 0-1
    test_count: int
    passed_count: int
    failed_count: int
    error_count: int
    average_duration_ms: float
    slowest_test_ms: float
    fastest_test_ms: float
    category_scores: dict = None  # Category -> score mapping

    def __post_init__(self):
        if self.category_scores is None:
            self.category_scores = {}


class CorrectnessScorer:
    """
    Scores code correctness based on test results
    
    Scoring factors:
    - Test pass rate (weight: 50%)
    - Test coverage (weight: 20%)
    - Error rate (weight: 15%)
    - Performance (weight: 15%)
    """

    def __init__(
        self,
        pass_rate_weight: float = 0.50,
        coverage_weight: float = 0.20,
        error_weight: float = 0.15,
        performance_weight: float = 0.15,
    ):
        """Initialize scorer with weights"""
        self.pass_rate_weight = pass_rate_weight
        self.coverage_weight = coverage_weight
        self.error_weight = error_weight
        self.performance_weight = performance_weight

    def score(self, test_results: List) -> ScoreMetrics:
        """
        Score test results
        
        Args:
            test_results: List of TestScore objects
            
        Returns:
            ScoreMetrics with overall score
        """
        if not test_results:
            return ScoreMetrics(
                overall_score=0,
                test_pass_rate=0,
                test_count=0,
                passed_count=0,
                failed_count=0,
                error_count=0,
                average_duration_ms=0,
                slowest_test_ms=0,
                fastest_test_ms=0,
            )

        # Basic metrics
        test_count = len(test_results)
        passed_count = sum(1 for t in test_results if t.passed)
        failed_count = test_count - passed_count
        error_count = sum(1 for t in test_results if t.error)

        # Pass rate score
        pass_rate = passed_count / test_count if test_count > 0 else 0
        pass_score = pass_rate * 100

        # Coverage score (based on test count, normalized to 0-100)
        # Assume good coverage with 20+ tests
        coverage_score = min((test_count / 20) * 100, 100)

        # Error score (inverse of error rate)
        error_rate = error_count / test_count if test_count > 0 else 0
        error_score = (1 - error_rate) * 100

        # Performance score (based on duration consistency)
        durations = [t.duration_ms for t in test_results if t.duration_ms > 0]
        if durations:
            avg_duration = sum(durations) / len(durations)
            slowest = max(durations)
            fastest = min(durations)
            
            # Penalize tests that are too slow (>10s)
            # or inconsistent (slowest > 10x fastest)
            duration_ratio = slowest / fastest if fastest > 0 else 1
            consistency_score = 100 if duration_ratio < 10 else 50
            
            # Penalty for very slow tests
            speed_score = 100 if avg_duration < 10000 else max(0, 100 - (avg_duration - 10000) / 100)
            
            performance_score = (consistency_score + speed_score) / 2
        else:
            performance_score = 50
            slowest = 0
            fastest = 0
            avg_duration = 0

        # Calculate overall score
        overall_score = (
            pass_score * self.pass_rate_weight
            + coverage_score * self.coverage_weight
            + error_score * self.error_weight
            + performance_score * self.performance_weight
        )

        # Clamp to 0-100
        overall_score = max(0, min(100, overall_score))

        return ScoreMetrics(
            overall_score=overall_score,
            test_pass_rate=pass_rate,
            test_count=test_count,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            average_duration_ms=avg_duration,
            slowest_test_ms=slowest,
            fastest_test_ms=fastest,
            category_scores={
                "pass_rate": pass_score,
                "coverage": coverage_score,
                "error_handling": error_score,
                "performance": performance_score,
            },
        )

    def score_category(
        self,
        test_results: List,
        category: ScoringCategory,
    ) -> float:
        """
        Score a specific category of tests
        
        Args:
            test_results: List of TestScore objects
            category: Category to score
            
        Returns:
            Score for the category (0-100)
        """
        if not test_results:
            return 0

        # Filter tests by category (based on test name)
        category_tests = [
            t for t in test_results
            if category.value.lower() in t.name.lower()
        ]

        if not category_tests:
            return 0

        # Score the filtered tests
        passed = sum(1 for t in category_tests if t.passed)
        score = (passed / len(category_tests)) * 100
        return score

    @staticmethod
    def calculate_confidence_interval(
        score: float,
        test_count: int,
        confidence_level: float = 0.95,
    ) -> tuple:
        """
        Calculate confidence interval for score
        
        Args:
            score: The score (0-100)
            test_count: Number of tests
            confidence_level: Confidence level (0.95 = 95%)
            
        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        # Using binomial proportion confidence interval
        # For simplicity, use normal approximation
        
        if test_count < 2:
            return (max(0, score - 25), min(100, score + 25))

        # Standard error
        p = score / 100
        se = ((p * (1 - p)) / test_count) ** 0.5 * 100

        # Z-score for 95% confidence ≈ 1.96
        z = 1.96 if confidence_level == 0.95 else 1.645

        margin = z * se
        lower = max(0, score - margin)
        upper = min(100, score + margin)

        return (lower, upper)
