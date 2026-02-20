"""Tests for multi-cycle learning system.

Covers: CycleRecord, CycleLearner persistence, analytics,
recommendations, and end-to-end learning workflows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kodo.learning import CycleRecord, CycleLearner


# ── Helpers ────────────────────────────────────────────────────────────


def _make_record(
    cycle_id: str = "1",
    cycle_name: str = "test-cycle",
    improvement_type: str = "feature",
    agents_used: list[str] | None = None,
    success: bool = True,
    metrics_before: dict[str, float] | None = None,
    metrics_after: dict[str, float] | None = None,
    execution_time_s: float = 10.0,
    rework_cycles: int = 0,
) -> CycleRecord:
    return CycleRecord(
        cycle_id=cycle_id,
        cycle_name=cycle_name,
        improvement_type=improvement_type,
        agents_used=agents_used or ["worker_smart"],
        success=success,
        metrics_before=metrics_before or {},
        metrics_after=metrics_after or {},
        execution_time_s=execution_time_s,
        rework_cycles=rework_cycles,
    )


# ── CycleRecord ────────────────────────────────────────────────────────


class TestCycleRecord:
    def test_creation(self) -> None:
        rec = _make_record(cycle_id="c1", cycle_name="Session Checkpointing")
        assert rec.cycle_id == "c1"
        assert rec.cycle_name == "Session Checkpointing"
        assert rec.timestamp  # auto-generated

    def test_metric_delta(self) -> None:
        rec = _make_record(
            metrics_before={"tokens_per_task": 3000},
            metrics_after={"tokens_per_task": 1500},
        )
        assert rec.metric_delta("tokens_per_task") == -1500

    def test_metric_delta_missing(self) -> None:
        rec = _make_record()
        assert rec.metric_delta("nonexistent") is None

    def test_serialization_roundtrip(self) -> None:
        rec = _make_record(
            cycle_id="c2",
            agents_used=["architect", "worker_smart"],
            metrics_before={"error_rate": 10},
            metrics_after={"error_rate": 3},
        )
        data = rec.to_dict()
        restored = CycleRecord.from_dict(data)
        assert restored.cycle_id == rec.cycle_id
        assert restored.agents_used == rec.agents_used
        assert restored.metrics_after == rec.metrics_after


# ── CycleLearner Persistence ──────────────────────────────────────────


class TestCycleLearnerPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "learning.json"
        learner = CycleLearner(path)
        learner.record_cycle(_make_record(cycle_id="1"))
        learner.record_cycle(_make_record(cycle_id="2"))

        # Create fresh learner from same path
        learner2 = CycleLearner(path)
        history = learner2.load_history()
        assert len(history) == 2
        assert history[0].cycle_id == "1"
        assert history[1].cycle_id == "2"

    def test_empty_history(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        learner = CycleLearner(path)
        assert learner.load_history() == []

    def test_corrupt_file_handled(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json", encoding="utf-8")
        learner = CycleLearner(path)
        assert learner.load_history() == []

    def test_record_persists_immediately(self, tmp_path: Path) -> None:
        path = tmp_path / "persist.json"
        learner = CycleLearner(path)
        learner.record_cycle(_make_record(cycle_id="x"))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["cycle_id"] == "x"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "learn.json"
        learner = CycleLearner(path)
        learner.record_cycle(_make_record())
        assert path.exists()


# ── CycleLearner Analysis ─────────────────────────────────────────────


class TestCycleLearnerAnalysis:
    @pytest.fixture
    def learner(self, tmp_path: Path) -> CycleLearner:
        path = tmp_path / "learn.json"
        learner = CycleLearner(path)
        # 3 feature cycles: 2 success, 1 fail
        learner.record_cycle(
            _make_record(cycle_id="1", improvement_type="feature", success=True, agents_used=["worker_smart"])
        )
        learner.record_cycle(
            _make_record(cycle_id="2", improvement_type="feature", success=True, agents_used=["worker_smart"])
        )
        learner.record_cycle(
            _make_record(cycle_id="3", improvement_type="feature", success=False, agents_used=["worker_fast"])
        )
        # 2 refactor cycles: 1 success, 1 fail
        learner.record_cycle(
            _make_record(cycle_id="4", improvement_type="refactor", success=True, agents_used=["architect", "worker_smart"])
        )
        learner.record_cycle(
            _make_record(cycle_id="5", improvement_type="refactor", success=False, agents_used=["worker_fast"], rework_cycles=3)
        )
        return learner

    def test_success_rate_by_type(self, learner: CycleLearner) -> None:
        rates = learner.success_rate_by_type()
        assert rates["feature"] == pytest.approx(2 / 3)
        assert rates["refactor"] == pytest.approx(0.5)

    def test_success_rate_by_agent(self, learner: CycleLearner) -> None:
        rates = learner.success_rate_by_agent()
        assert rates["worker_smart"] == pytest.approx(1.0)
        assert rates["worker_fast"] == pytest.approx(0.0)
        assert rates["architect"] == pytest.approx(1.0)

    def test_best_agent_for_feature(self, learner: CycleLearner) -> None:
        # worker_smart: 2/2 success, worker_fast: 0/1 — worker_smart is best
        assert learner.best_agent_for_type("feature") == "worker_smart"

    def test_best_agent_for_refactor(self, learner: CycleLearner) -> None:
        best = learner.best_agent_for_type("refactor")
        assert best in ("architect", "worker_smart")

    def test_best_agent_unknown_type(self, learner: CycleLearner) -> None:
        assert learner.best_agent_for_type("unknown") is None

    def test_avg_rework_by_type(self, learner: CycleLearner) -> None:
        rework = learner.avg_rework_by_type()
        assert rework["feature"] == 0.0
        assert rework["refactor"] == pytest.approx(1.5)


# ── Metric Trends ─────────────────────────────────────────────────────


class TestCycleLearnerTrends:
    def test_metric_trends(self, tmp_path: Path) -> None:
        path = tmp_path / "trends.json"
        learner = CycleLearner(path)

        learner.record_cycle(
            _make_record(cycle_id="1", metrics_after={"tokens_per_task": 3000, "test_coverage": 50})
        )
        learner.record_cycle(
            _make_record(cycle_id="2", metrics_after={"tokens_per_task": 2000, "test_coverage": 70})
        )
        learner.record_cycle(
            _make_record(cycle_id="3", metrics_after={"tokens_per_task": 1200, "test_coverage": 85})
        )

        trends = learner.metric_trends()
        assert "tokens_per_task" in trends
        assert "test_coverage" in trends

        token_trend = trends["tokens_per_task"]
        assert len(token_trend) == 3
        assert token_trend[0] == ("1", 3000)
        assert token_trend[2] == ("3", 1200)

        cov_trend = trends["test_coverage"]
        assert cov_trend[-1] == ("3", 85)

    def test_empty_trends(self, tmp_path: Path) -> None:
        learner = CycleLearner(tmp_path / "empty.json")
        assert learner.metric_trends() == {}


# ── Recommendations ───────────────────────────────────────────────────


class TestCycleLearnerRecommendations:
    def test_recommend_team_with_history(self, tmp_path: Path) -> None:
        path = tmp_path / "recs.json"
        learner = CycleLearner(path)

        learner.record_cycle(
            _make_record(improvement_type="feature", success=True, agents_used=["worker_smart"])
        )
        learner.record_cycle(
            _make_record(improvement_type="feature", success=True, agents_used=["worker_smart"])
        )
        learner.record_cycle(
            _make_record(improvement_type="feature", success=False, agents_used=["worker_fast"])
        )

        team = learner.recommend_team("feature")
        assert team[0] == "worker_smart"

    def test_recommend_team_no_history(self, tmp_path: Path) -> None:
        learner = CycleLearner(tmp_path / "norecs.json")
        team = learner.recommend_team("feature")
        assert "architect" in team
        assert "worker_smart" in team

    def test_rank_goals_with_learning(self, tmp_path: Path) -> None:
        from kodo.goal_identifier import BottleneckAnalysis, ImprovementGoal

        path = tmp_path / "rank.json"
        learner = CycleLearner(path)

        learner.record_cycle(
            _make_record(improvement_type="tokens_per_task", success=True)
        )
        learner.record_cycle(
            _make_record(improvement_type="tokens_per_task", success=True)
        )
        learner.record_cycle(
            _make_record(improvement_type="test_coverage", success=False)
        )
        learner.record_cycle(
            _make_record(improvement_type="test_coverage", success=False)
        )

        goal_tokens = ImprovementGoal(
            title="Reduce tokens",
            description="Optimize token usage",
            priority=2,
            estimated_impact="30% reduction",
            bottleneck=BottleneckAnalysis(
                metric="tokens_per_task",
                current_value=2000,
                unit="tokens",
                target_value=1000,
                severity=0.5,
                description="High token usage",
                suggested_action="Optimize",
            ),
        )
        goal_coverage = ImprovementGoal(
            title="Increase coverage",
            description="Add tests",
            priority=1,
            estimated_impact="40% increase",
            bottleneck=BottleneckAnalysis(
                metric="test_coverage",
                current_value=60,
                unit="%",
                target_value=90,
                severity=0.5,
                description="Low coverage",
                suggested_action="Add tests",
            ),
        )

        ranked = learner.rank_goals_with_learning([goal_coverage, goal_tokens])
        assert ranked[0].title == "Reduce tokens"
        assert ranked[0].priority == 1

    def test_rank_goals_empty_history(self, tmp_path: Path) -> None:
        from kodo.goal_identifier import BottleneckAnalysis, ImprovementGoal

        learner = CycleLearner(tmp_path / "empty_rank.json")

        goal1 = ImprovementGoal(
            title="A",
            description="",
            priority=1,
            estimated_impact="",
            bottleneck=BottleneckAnalysis(
                metric="m1", current_value=10, unit="", target_value=5,
                severity=0.8, description="", suggested_action="",
            ),
        )
        goal2 = ImprovementGoal(
            title="B",
            description="",
            priority=2,
            estimated_impact="",
            bottleneck=BottleneckAnalysis(
                metric="m2", current_value=10, unit="", target_value=5,
                severity=0.3, description="", suggested_action="",
            ),
        )

        ranked = learner.rank_goals_with_learning([goal2, goal1])
        assert ranked[0].title == "A"


# ── Effectiveness Summary ──────────────────────────────────────────────


class TestEffectivenessSummary:
    def test_empty_summary(self, tmp_path: Path) -> None:
        learner = CycleLearner(tmp_path / "empty.json")
        summary = learner.effectiveness_summary()
        assert "No cycle history" in summary

    def test_summary_with_data(self, tmp_path: Path) -> None:
        path = tmp_path / "summ.json"
        learner = CycleLearner(path)
        learner.record_cycle(
            _make_record(
                cycle_id="1",
                improvement_type="feature",
                success=True,
                agents_used=["worker_smart"],
                execution_time_s=45.0,
                metrics_after={"tokens_per_task": 2000},
            )
        )
        learner.record_cycle(
            _make_record(
                cycle_id="2",
                improvement_type="feature",
                success=False,
                agents_used=["worker_fast"],
                execution_time_s=30.0,
                metrics_after={"tokens_per_task": 1500},
            )
        )

        summary = learner.effectiveness_summary()
        assert "Total Cycles:** 2" in summary
        assert "50%" in summary
        assert "feature" in summary
        assert "worker_smart" in summary
        assert "Metric Trends" in summary

    def test_summary_has_recommendations(self, tmp_path: Path) -> None:
        path = tmp_path / "recs.json"
        learner = CycleLearner(path)
        learner.record_cycle(_make_record(improvement_type="feature", success=True))
        learner.record_cycle(_make_record(improvement_type="bugfix", success=False))
        summary = learner.effectiveness_summary()
        assert "Recommendations" in summary
        assert "Most effective" in summary


# ── End-to-End Workflow ────────────────────────────────────────────────


class TestLearningWorkflow:
    def test_full_learning_cycle(self, tmp_path: Path) -> None:
        """Simulate 6 cycles of learning and verify insights improve."""
        path = tmp_path / "workflow.json"
        learner = CycleLearner(path)

        learner.record_cycle(_make_record(
            cycle_id="1", cycle_name="Session Checkpointing",
            improvement_type="feature", agents_used=["architect", "worker_smart"],
            success=True, execution_time_s=120,
            metrics_before={"tokens_per_task": 3000, "test_coverage": 50},
            metrics_after={"tokens_per_task": 2500, "test_coverage": 60},
        ))

        learner.record_cycle(_make_record(
            cycle_id="2", cycle_name="Retry Logic",
            improvement_type="feature", agents_used=["worker_fast"],
            success=False, execution_time_s=60, rework_cycles=2,
            metrics_before={"tokens_per_task": 2500, "test_coverage": 60},
            metrics_after={"tokens_per_task": 2500, "test_coverage": 60},
        ))

        learner.record_cycle(_make_record(
            cycle_id="3", cycle_name="Retry Logic (retry)",
            improvement_type="feature", agents_used=["worker_smart"],
            success=True, execution_time_s=90,
            metrics_before={"tokens_per_task": 2500, "test_coverage": 60},
            metrics_after={"tokens_per_task": 2000, "test_coverage": 70},
        ))

        learner.record_cycle(_make_record(
            cycle_id="4", cycle_name="Task Routing",
            improvement_type="refactor", agents_used=["architect", "worker_smart"],
            success=True, execution_time_s=150,
            metrics_before={"tokens_per_task": 2000, "test_coverage": 70},
            metrics_after={"tokens_per_task": 1500, "test_coverage": 80},
        ))

        learner.record_cycle(_make_record(
            cycle_id="5", cycle_name="Token Optimization",
            improvement_type="optimization", agents_used=["worker_smart"],
            success=True, execution_time_s=100,
            metrics_before={"tokens_per_task": 1500, "test_coverage": 80},
            metrics_after={"tokens_per_task": 1000, "test_coverage": 85},
        ))

        learner.record_cycle(_make_record(
            cycle_id="6", cycle_name="Add Tests",
            improvement_type="testing", agents_used=["worker_fast"],
            success=True, execution_time_s=30,
            metrics_before={"tokens_per_task": 1000, "test_coverage": 85},
            metrics_after={"tokens_per_task": 1000, "test_coverage": 92},
        ))

        # Verify learning insights
        history = learner.load_history()
        assert len(history) == 6

        rates = learner.success_rate_by_type()
        assert rates["feature"] == pytest.approx(2 / 3)
        assert rates["refactor"] == 1.0
        assert rates["optimization"] == 1.0
        assert rates["testing"] == 1.0

        agent_rates = learner.success_rate_by_agent()
        assert agent_rates["worker_smart"] > agent_rates.get("worker_fast", 0)

        # architect (1/1=100%) and worker_smart (2/2=100%) both have perfect rates
        best = learner.best_agent_for_type("feature")
        assert best in ("worker_smart", "architect")

        trends = learner.metric_trends()
        tokens_trend = trends["tokens_per_task"]
        assert tokens_trend[0][1] > tokens_trend[-1][1]

        coverage_trend = trends["test_coverage"]
        assert coverage_trend[0][1] < coverage_trend[-1][1]

        team = learner.recommend_team("feature")
        assert team[0] in ("worker_smart", "architect")

        summary = learner.effectiveness_summary()
        assert "Learning Summary" in summary
        assert "Total Cycles:** 6" in summary

    def test_persistence_across_sessions(self, tmp_path: Path) -> None:
        """Verify learning persists and loads correctly across instances."""
        path = tmp_path / "persist.json"

        learner1 = CycleLearner(path)
        learner1.record_cycle(_make_record(cycle_id="a", success=True))
        learner1.record_cycle(_make_record(cycle_id="b", success=False))

        learner2 = CycleLearner(path)
        assert len(learner2.load_history()) == 2

        learner2.record_cycle(_make_record(cycle_id="c", success=True))

        learner3 = CycleLearner(path)
        assert len(learner3.load_history()) == 3
        rates = learner3.success_rate_by_type()
        assert rates["feature"] == pytest.approx(2 / 3)
