"""Tests for self-improvement goal identification.

Covers: BottleneckAnalysis, ImprovementGoal, PerformanceAnalyzer,
goal proposals, formatting, and edge cases.
"""

from __future__ import annotations

import pytest

from kodo.goal_identifier import (
    BottleneckAnalysis,
    ImprovementGoal,
    PerformanceAnalyzer,
)


# ── BottleneckAnalysis ───────────────────────────────────────────────────


class TestBottleneckAnalysis:
    def test_gap_pct(self) -> None:
        b = BottleneckAnalysis(
            metric="tokens_per_task",
            current_value=2000,
            unit="tokens",
            target_value=1000,
            severity=1.0,
            description="Too many tokens",
            suggested_action="Optimize",
        )
        assert b.gap_pct == 100.0  # 100% over target

    def test_gap_pct_close_to_target(self) -> None:
        b = BottleneckAnalysis(
            metric="test_coverage",
            current_value=85,
            unit="%",
            target_value=90,
            severity=0.1,
            description="Coverage low",
            suggested_action="Add tests",
        )
        assert b.gap_pct == pytest.approx(5.56, abs=0.1)

    def test_gap_pct_zero_target(self) -> None:
        b = BottleneckAnalysis(
            metric="x",
            current_value=5,
            unit="",
            target_value=0,
            severity=0.5,
            description="d",
            suggested_action="a",
        )
        assert b.gap_pct == 0.0


# ── ImprovementGoal ─────────────────────────────────────────────────────


class TestImprovementGoal:
    def test_format_proposal(self) -> None:
        bottleneck = BottleneckAnalysis(
            metric="tokens_per_task",
            current_value=2000,
            unit="tokens",
            target_value=1000,
            severity=1.0,
            description="High token usage",
            suggested_action="Optimize prompts",
        )
        goal = ImprovementGoal(
            title="Reduce Token Usage",
            description="Optimize prompt efficiency",
            priority=1,
            estimated_impact="Reduce by 50%",
            bottleneck=bottleneck,
            acceptance_criteria=["Reach 1000 tokens/task", "Tests pass"],
        )
        proposal = goal.format_proposal()
        assert "Priority 1" in proposal
        assert "Reduce Token Usage" in proposal
        assert "2000.00 tokens" in proposal
        assert "1000.00 tokens" in proposal
        assert "Reach 1000 tokens/task" in proposal


# ── PerformanceAnalyzer ──────────────────────────────────────────────────


class TestPerformanceAnalyzerAnalyze:
    def test_identifies_high_token_usage(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({"tokens_per_task": 3000})
        assert len(bottlenecks) >= 1
        token_bn = next(b for b in bottlenecks if b.metric == "tokens_per_task")
        assert token_bn.severity > 0.5
        assert token_bn.current_value == 3000
        assert token_bn.target_value == 1000

    def test_identifies_low_coverage(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({"test_coverage": 50})
        assert len(bottlenecks) >= 1
        cov_bn = next(b for b in bottlenecks if b.metric == "test_coverage")
        assert cov_bn.severity > 0.3

    def test_identifies_high_error_rate(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({"error_rate": 15})
        assert len(bottlenecks) >= 1
        err_bn = next(b for b in bottlenecks if b.metric == "error_rate")
        assert err_bn.severity > 0.5

    def test_no_bottlenecks_when_all_good(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({
            "tokens_per_task": 900,
            "execution_time_s": 100,
            "test_coverage": 95,
            "error_rate": 1,
        })
        assert len(bottlenecks) == 0

    def test_severity_ordering(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({
            "tokens_per_task": 5000,  # very high → high severity
            "test_coverage": 85,  # slightly low → low severity
            "error_rate": 20,  # very high → high severity
        })
        # Should be sorted by severity (highest first)
        assert len(bottlenecks) >= 2
        for i in range(len(bottlenecks) - 1):
            assert bottlenecks[i].severity >= bottlenecks[i + 1].severity

    def test_unknown_metric_skipped(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({"unknown_metric": 999})
        assert len(bottlenecks) == 0

    def test_severity_capped_at_one(self) -> None:
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze({"tokens_per_task": 100000})
        assert all(b.severity <= 1.0 for b in bottlenecks)

    def test_custom_targets(self) -> None:
        analyzer = PerformanceAnalyzer(
            targets={"my_metric": (50, "units", True)}
        )
        bottlenecks = analyzer.analyze({"my_metric": 100})
        assert len(bottlenecks) == 1
        assert bottlenecks[0].metric == "my_metric"
        assert bottlenecks[0].target_value == 50


class TestPerformanceAnalyzerGoals:
    def test_propose_goals_basic(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({
            "tokens_per_task": 3000,
            "error_rate": 15,
        })
        assert len(goals) >= 1
        assert goals[0].priority == 1
        assert goals[0].bottleneck.severity > 0

    def test_propose_goals_max_three(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({
            "tokens_per_task": 5000,
            "execution_time_s": 600,
            "test_coverage": 30,
            "error_rate": 25,
            "bug_escape_rate": 20,
        }, max_goals=3)
        assert len(goals) <= 3

    def test_propose_goals_priority_order(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({
            "tokens_per_task": 5000,
            "test_coverage": 40,
            "error_rate": 20,
        })
        for i in range(len(goals) - 1):
            assert goals[i].priority < goals[i + 1].priority

    def test_propose_goals_with_acceptance_criteria(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({"tokens_per_task": 3000})
        assert len(goals) >= 1
        assert len(goals[0].acceptance_criteria) >= 3
        assert any("tokens_per_task" in c for c in goals[0].acceptance_criteria)
        assert any("tests pass" in c.lower() for c in goals[0].acceptance_criteria)

    def test_propose_goals_empty_when_all_good(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({
            "tokens_per_task": 900,
            "execution_time_s": 100,
            "test_coverage": 95,
            "error_rate": 1,
        })
        assert len(goals) == 0

    def test_propose_goals_custom_max(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals(
            {"tokens_per_task": 5000, "error_rate": 20, "test_coverage": 30},
            max_goals=1,
        )
        assert len(goals) == 1


class TestPerformanceAnalyzerFormat:
    def test_format_proposal_empty(self) -> None:
        analyzer = PerformanceAnalyzer()
        result = analyzer.format_proposal([])
        assert "No Improvements Needed" in result

    def test_format_proposal_with_goals(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({
            "tokens_per_task": 3000,
            "error_rate": 15,
        })
        proposal = analyzer.format_proposal(goals)
        assert "Proposed Improvement Goals" in proposal
        assert "Priority" in proposal
        assert "Acceptance Criteria" in proposal

    def test_format_proposal_valid_markdown(self) -> None:
        analyzer = PerformanceAnalyzer()
        goals = analyzer.propose_goals({"tokens_per_task": 5000})
        proposal = analyzer.format_proposal(goals)
        # Should be valid markdown (has headers)
        assert proposal.startswith("#")
        assert "##" in proposal


# ── End-to-end workflow ──────────────────────────────────────────────────


class TestGoalIdentificationWorkflow:
    def test_full_cycle(self) -> None:
        """Simulate: collect metrics → analyze → propose → format."""
        # 1. Collect current metrics (simulated)
        metrics = {
            "tokens_per_task": 2500,
            "execution_time_s": 250,
            "test_coverage": 65,
            "error_rate": 12,
            "bug_escape_rate": 8,
        }

        # 2. Analyze
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.analyze(metrics)
        assert len(bottlenecks) >= 3  # at least 3 bottlenecks

        # 3. Propose goals
        goals = analyzer.propose_goals(metrics, max_goals=3)
        assert len(goals) == 3
        assert goals[0].priority == 1  # highest priority first

        # 4. Format proposal
        proposal = analyzer.format_proposal(goals)
        assert "Proposed Improvement Goals" in proposal
        assert "3" in proposal  # mentions 3 improvements

        # 5. Verify goals are actionable
        for goal in goals:
            assert len(goal.acceptance_criteria) >= 3
            assert goal.bottleneck.severity > 0
            assert goal.title  # has a title
            assert goal.description  # has a description

    def test_incremental_improvement(self) -> None:
        """Simulate successive improvements narrowing the bottleneck list."""
        analyzer = PerformanceAnalyzer()

        # Cycle 1: many issues
        metrics_v1 = {
            "tokens_per_task": 3000,
            "test_coverage": 50,
            "error_rate": 15,
        }
        goals_v1 = analyzer.propose_goals(metrics_v1)
        assert len(goals_v1) == 3

        # Cycle 2: improved tokens and errors
        metrics_v2 = {
            "tokens_per_task": 1100,  # close to target
            "test_coverage": 50,  # still low
            "error_rate": 3,  # close to target
        }
        goals_v2 = analyzer.propose_goals(metrics_v2)
        # Fewer goals needed now
        assert len(goals_v2) < len(goals_v1)

        # Cycle 3: all near target
        metrics_v3 = {
            "tokens_per_task": 950,
            "test_coverage": 89,
            "error_rate": 2,
        }
        goals_v3 = analyzer.propose_goals(metrics_v3)
        # Very few or no goals
        assert len(goals_v3) <= 1
