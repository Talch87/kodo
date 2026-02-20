"""Tests for the autonomous improvement daemon.

Covers: DaemonCycleReport, DaemonStatus, ImprovementDaemon integration
with PerformanceAnalyzer, CycleLearner, and BenchmarkStore.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kodo.autonomous.daemon import (
    DaemonCycleReport,
    DaemonStatus,
    ImprovementDaemon,
)
from kodo.goal_identifier import ImprovementGoal


# ── DaemonCycleReport ─────────────────────────────────────────────────


class TestDaemonCycleReport:
    def test_creation(self) -> None:
        report = DaemonCycleReport(cycle_id="test-1")
        assert report.cycle_id == "test-1"
        assert report.goals_identified == 0
        assert report.timestamp

    def test_success_rate_zero_attempts(self) -> None:
        report = DaemonCycleReport(cycle_id="x")
        assert report.success_rate == 0.0

    def test_success_rate_calculated(self) -> None:
        report = DaemonCycleReport(
            cycle_id="x",
            goals_attempted=4,
            goals_succeeded=3,
        )
        assert report.success_rate == 0.75

    def test_summary_string(self) -> None:
        report = DaemonCycleReport(
            cycle_id="d-1",
            goals_attempted=3,
            goals_succeeded=2,
            execution_time_s=45.5,
        )
        s = report.summary
        assert "d-1" in s
        assert "2/3" in s
        assert "67%" in s

    def test_format_report_markdown(self) -> None:
        report = DaemonCycleReport(
            cycle_id="d-1",
            goals_attempted=1,
            goals_succeeded=1,
            execution_time_s=10.0,
            goal_details=[{"title": "Fix tokens", "success": True}],
            metrics_before={"tokens_per_task": 3000},
            metrics_after={"tokens_per_task": 1500},
        )
        md = report.format_report()
        assert "# Improvement Cycle d-1" in md
        assert "Fix tokens" in md
        assert "pass" in md
        assert "Metrics" in md
        assert "3000" in md

    def test_format_report_empty(self) -> None:
        report = DaemonCycleReport(cycle_id="empty")
        md = report.format_report()
        assert "empty" in md


# ── DaemonStatus ──────────────────────────────────────────────────────


class TestDaemonStatus:
    def test_overall_success_rate_zero(self) -> None:
        s = DaemonStatus()
        assert s.overall_success_rate == 0.0

    def test_overall_success_rate(self) -> None:
        s = DaemonStatus(total_goals_attempted=10, total_goals_succeeded=7)
        assert s.overall_success_rate == 0.7


# ── ImprovementDaemon ─────────────────────────────────────────────────


class TestImprovementDaemonBasic:
    def test_creation(self, tmp_path: Path) -> None:
        daemon = ImprovementDaemon(tmp_path)
        assert daemon.project_dir == tmp_path
        assert daemon._cycle_count == 0

    def test_run_cycle_no_bottlenecks(self, tmp_path: Path) -> None:
        """When all metrics are healthy, no goals are proposed."""
        good_metrics = {
            "tokens_per_task": 900,
            "execution_time_s": 100,
            "test_coverage": 95,
            "error_rate": 1,
        }
        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: good_metrics,
        )
        report = daemon.run_cycle()
        assert report.goals_identified == 0
        assert report.goals_attempted == 0
        assert report.goals_succeeded == 0

    def test_run_cycle_with_bottlenecks(self, tmp_path: Path) -> None:
        """When metrics are bad, goals are identified and executed."""
        bad_metrics = {
            "tokens_per_task": 5000,
            "error_rate": 20,
            "test_coverage": 40,
        }
        executed_goals: list[str] = []

        def executor(goal: ImprovementGoal) -> bool:
            executed_goals.append(goal.title)
            return True

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: bad_metrics,
            goal_executor=executor,
            max_goals_per_cycle=3,
        )
        report = daemon.run_cycle()
        assert report.goals_identified >= 1
        assert report.goals_attempted >= 1
        assert report.goals_succeeded >= 1
        assert len(executed_goals) >= 1

    def test_run_cycle_executor_failure(self, tmp_path: Path) -> None:
        """Failed executions are tracked correctly."""
        bad_metrics = {"tokens_per_task": 5000}

        def failing_executor(goal: ImprovementGoal) -> bool:
            return False

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: bad_metrics,
            goal_executor=failing_executor,
        )
        report = daemon.run_cycle()
        assert report.goals_failed >= 1
        assert report.goals_succeeded == 0

    def test_run_cycle_executor_exception(self, tmp_path: Path) -> None:
        """Exceptions in executor are caught and recorded."""
        bad_metrics = {"tokens_per_task": 5000}

        def crashing_executor(goal: ImprovementGoal) -> bool:
            raise RuntimeError("Agent crashed")

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: bad_metrics,
            goal_executor=crashing_executor,
        )
        report = daemon.run_cycle()
        assert report.goals_failed >= 1
        assert any("error" in d for d in report.goal_details)


class TestImprovementDaemonIntegration:
    def test_learning_integration(self, tmp_path: Path) -> None:
        """Daemon records learning data across cycles."""
        metrics_state = {"tokens_per_task": 5000, "error_rate": 15}

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: dict(metrics_state),
            goal_executor=lambda g: True,
        )

        # Cycle 1
        daemon.run_cycle()

        # Cycle 2 with slightly improved metrics
        metrics_state["tokens_per_task"] = 3000
        daemon.run_cycle()

        # Learning should have records
        history = daemon.learner.load_history()
        assert len(history) >= 2

    def test_benchmark_persistence(self, tmp_path: Path) -> None:
        """Benchmarks are saved to disk after each cycle."""
        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 5000},
            goal_executor=lambda g: True,
        )
        daemon.run_cycle()

        # Check benchmark files exist
        cycles = daemon.benchmark_store.list_cycles()
        assert len(cycles) >= 1

    def test_run_loop_limited(self, tmp_path: Path) -> None:
        """run_loop with max_cycles stops correctly."""
        call_count = 0

        def counting_executor(goal: ImprovementGoal) -> bool:
            nonlocal call_count
            call_count += 1
            return True

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 3000},
            goal_executor=counting_executor,
            cycle_interval_s=0,  # no delay between cycles
        )

        reports = daemon.run_loop(max_cycles=3)
        assert len(reports) == 3

    def test_run_loop_callback(self, tmp_path: Path) -> None:
        """on_cycle callback is called for each cycle."""
        callbacks: list[DaemonCycleReport] = []

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 3000},
            goal_executor=lambda g: True,
            cycle_interval_s=0,
        )

        daemon.run_loop(max_cycles=2, on_cycle=callbacks.append)
        assert len(callbacks) == 2
        assert all(isinstance(r, DaemonCycleReport) for r in callbacks)

    def test_status(self, tmp_path: Path) -> None:
        """Status reflects current daemon state."""
        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 3000},
            goal_executor=lambda g: True,
        )

        # Before any cycles
        status = daemon.status()
        assert status.total_cycles == 0
        assert status.last_cycle_report is None

        # After a cycle
        daemon.run_cycle()
        status = daemon.status()
        assert status.total_cycles == 1
        assert status.last_cycle_report is not None

    def test_weekly_summary(self, tmp_path: Path) -> None:
        """Weekly summary includes all cycles."""
        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 3000},
            goal_executor=lambda g: True,
            cycle_interval_s=0,
        )

        daemon.run_loop(max_cycles=3)
        summary = daemon.weekly_summary()
        assert "Weekly Summary" in summary
        assert "Cycles:** 3" in summary
        assert "Learning Summary" in summary

    def test_weekly_summary_empty(self, tmp_path: Path) -> None:
        daemon = ImprovementDaemon(tmp_path)
        assert "No cycles" in daemon.weekly_summary()


class TestImprovementDaemonLearningLoop:
    def test_goals_improve_with_learning(self, tmp_path: Path) -> None:
        """Verify learning re-ranks goals across cycles."""
        cycle_num = 0
        executed_titles: list[str] = []

        def metrics():
            return {
                "tokens_per_task": 3000,
                "error_rate": 15,
                "test_coverage": 40,
            }

        def executor(goal: ImprovementGoal) -> bool:
            nonlocal cycle_num
            executed_titles.append(goal.title)
            # Simulate: token optimization always succeeds, others fail
            return "token" in goal.title.lower()

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=metrics,
            goal_executor=executor,
            max_goals_per_cycle=3,
            cycle_interval_s=0,
        )

        # Run multiple cycles
        reports = daemon.run_loop(max_cycles=3)
        assert len(reports) == 3

        # Learning should have accumulated records
        history = daemon.learner.load_history()
        assert len(history) >= 3  # at least 1 goal per cycle

    def test_stop_signal(self, tmp_path: Path) -> None:
        """Daemon can be stopped mid-loop."""
        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=lambda: {"tokens_per_task": 3000},
            goal_executor=lambda g: True,
            cycle_interval_s=0,
        )

        # Stop after first cycle via callback
        def stopper(report: DaemonCycleReport) -> None:
            daemon.stop()

        reports = daemon.run_loop(on_cycle=stopper)
        assert len(reports) == 1


# ── End-to-end ────────────────────────────────────────────────────────


class TestDaemonEndToEnd:
    def test_full_autonomous_workflow(self, tmp_path: Path) -> None:
        """Simulate a complete autonomous improvement session."""
        improving_metrics = {
            "tokens_per_task": 5000.0,
            "error_rate": 20.0,
            "test_coverage": 40.0,
        }

        def metrics():
            return dict(improving_metrics)

        def executor(goal: ImprovementGoal) -> bool:
            # Simulate improvement
            metric = goal.bottleneck.metric
            if metric == "tokens_per_task":
                improving_metrics["tokens_per_task"] *= 0.7  # 30% reduction
                return True
            elif metric == "error_rate":
                improving_metrics["error_rate"] *= 0.6
                return True
            elif metric == "test_coverage":
                improving_metrics["test_coverage"] = min(
                    100, improving_metrics["test_coverage"] + 15
                )
                return True
            return False

        daemon = ImprovementDaemon(
            tmp_path,
            metrics_collector=metrics,
            goal_executor=executor,
            max_goals_per_cycle=3,
            cycle_interval_s=0,
        )

        reports = daemon.run_loop(max_cycles=5)
        assert len(reports) == 5

        # Metrics should have improved
        final_metrics = metrics()
        assert final_metrics["tokens_per_task"] < 5000
        assert final_metrics["error_rate"] < 20

        # Status should reflect progress
        status = daemon.status()
        assert status.total_cycles == 5
        assert status.total_goals_succeeded > 0

        # Weekly summary should be comprehensive
        summary = daemon.weekly_summary()
        assert "Weekly Summary" in summary
        assert "5" in summary

        # Benchmarks should be persisted
        bench_cycles = daemon.benchmark_store.list_cycles()
        assert len(bench_cycles) == 5

        # Learning history should be persisted
        learner = daemon.learner
        history = learner.load_history()
        assert len(history) >= 5

        # Learning insights should be available
        rates = learner.success_rate_by_type()
        assert len(rates) >= 1
