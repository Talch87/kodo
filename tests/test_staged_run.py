"""Tests for staged goal execution (GoalPlan, compose_stage_goal, staged run)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kodo import log
from kodo.orchestrators.base import (
    CycleResult,
    GoalPlan,
    GoalStage,
    OrchestratorBase,
    ResumeState,
    StageResult,
    compose_stage_goal,
)
from tests.conftest import make_agent


# ── compose_stage_goal tests ─────────────────────────────────────────────


def _make_plan(num_stages: int = 3) -> GoalPlan:
    return GoalPlan(
        context="Python web app using Flask",
        stages=[
            GoalStage(
                index=i + 1,
                name=f"Stage {i + 1}",
                description=f"Description for stage {i + 1}",
                acceptance_criteria=f"Tests pass for stage {i + 1}",
            )
            for i in range(num_stages)
        ],
    )


def test_compose_stage_goal_first_stage():
    plan = _make_plan()
    goal = compose_stage_goal(plan, 1, [])

    assert "Python web app using Flask" in goal
    assert "Stage 1" in goal
    assert "Description for stage 1" in goal
    assert "Tests pass for stage 1" in goal
    # Should have next stage preview
    assert "Stage 2" in goal
    # No completed stages section
    assert "Completed Stages" not in goal


def test_compose_stage_goal_middle_stage_with_summaries():
    plan = _make_plan()
    summaries = ["Stage 1 is done: built the models"]
    goal = compose_stage_goal(plan, 2, summaries)

    assert "Completed Stages" in goal
    assert "Stage 1 is done: built the models" in goal
    assert "Stage 2" in goal
    assert "Description for stage 2" in goal
    # Next stage preview
    assert "Stage 3" in goal


def test_compose_stage_goal_last_stage_no_next():
    plan = _make_plan()
    summaries = ["s1 done", "s2 done"]
    goal = compose_stage_goal(plan, 3, summaries)

    assert "Description for stage 3" in goal
    # No next stage preview for last stage
    assert "Next Stage Preview" not in goal


def test_compose_stage_goal_single_stage():
    plan = GoalPlan(
        context="Simple script",
        stages=[
            GoalStage(index=1, name="Do it", description="Build the thing", acceptance_criteria="It works"),
        ],
    )
    goal = compose_stage_goal(plan, 1, [])
    assert "Simple script" in goal
    assert "Do it" in goal
    assert "Next Stage Preview" not in goal


# ── Staged run() tests ──────────────────────────────────────────────────


class FakeOrchestrator(OrchestratorBase):
    """Minimal orchestrator for testing staged run() logic."""

    def __init__(self, cycle_results: list[CycleResult] | None = None):
        self.model = "test-model"
        self._orchestrator_name = "test"
        self._summarizer = MagicMock()
        self._cycle_results = list(cycle_results or [])
        self._cycle_calls: list[dict] = []

    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        self._cycle_calls.append(
            {
                "goal": goal,
                "prior_summary": prior_summary,
            }
        )
        if self._cycle_results:
            return self._cycle_results.pop(0)
        return CycleResult(summary="cycle done")


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    log.init(tmp_path)
    return tmp_path


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_all_stages_complete(mock_viewer, tmp_project):
    """Each stage finishes in 1 cycle; all 3 stages should complete."""
    plan = _make_plan(3)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="stage 1 done", finished=True),
            CycleResult(summary="stage 2 done", finished=True),
            CycleResult(summary="stage 3 done", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "overall goal", tmp_project, team,
            max_cycles=10, plan=plan,
        )

    assert len(result.stage_results) == 3
    assert all(sr.finished for sr in result.stage_results)
    assert len(result.cycles) == 3
    assert result.finished  # last cycle was finished


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_stage_takes_multiple_cycles(mock_viewer, tmp_project):
    """Stage 1 takes 2 cycles; stage 2 takes 1 cycle."""
    plan = _make_plan(2)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="partial s1"),
            CycleResult(summary="stage 1 done", finished=True),
            CycleResult(summary="stage 2 done", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=10, plan=plan,
        )

    assert len(result.stage_results) == 2
    assert result.stage_results[0].finished
    assert len(result.stage_results[0].cycles) == 2
    assert result.stage_results[1].finished
    assert len(result.stage_results[1].cycles) == 1


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_budget_exhausted(mock_viewer, tmp_project):
    """With max_cycles=2 and 3 stages, run stops when budget exhausted."""
    plan = _make_plan(3)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="stage 1 done", finished=True),
            CycleResult(summary="partial s2"),
            # No more cycles available
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=2, plan=plan,
        )

    assert len(result.stage_results) == 2
    assert result.stage_results[0].finished
    assert not result.stage_results[1].finished  # budget ran out


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_stage_failure_stops_run(mock_viewer, tmp_project):
    """If stage 1 uses all budget without finishing, run stops."""
    plan = _make_plan(2)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="partial"),
            CycleResult(summary="still partial"),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=2, plan=plan,
        )

    # Only stage 1 was attempted, and it didn't finish
    assert len(result.stage_results) == 1
    assert not result.stage_results[0].finished


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_no_plan_uses_single_mode(mock_viewer, tmp_project):
    """With plan=None, staged run is not used (backward compat)."""
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="done", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=5, plan=None,
        )

    assert len(result.cycles) == 1
    assert result.finished
    assert result.stage_results == []


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_cycle_has_stage_index(mock_viewer, tmp_project):
    """Cycle results from staged runs should have stage_index set."""
    plan = _make_plan(2)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="s1 done", finished=True),
            CycleResult(summary="s2 done", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=10, plan=plan,
        )

    assert result.cycles[0].stage_index == 1
    assert result.cycles[1].stage_index == 2


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_run_goal_includes_completed_summaries(mock_viewer, tmp_project):
    """After stage 1 completes, stage 2's goal should include stage 1's summary."""
    plan = _make_plan(2)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="built the models", finished=True),
            CycleResult(summary="added the API", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    with patch("kodo.viewer.open_viewer", create=True):
        orch.run("goal", tmp_project, team, max_cycles=10, plan=plan)

    # Second cycle's goal should mention stage 1's summary
    stage2_goal = orch._cycle_calls[1]["goal"]
    assert "built the models" in stage2_goal


# ── Staged resume tests ─────────────────────────────────────────────────


@patch("kodo.orchestrators.base.open_viewer", create=True)
def test_staged_resume_skips_completed_stages(mock_viewer, tmp_project):
    """Resuming after stage 1 completed should start at stage 2."""
    plan = _make_plan(3)
    orch = FakeOrchestrator(
        cycle_results=[
            CycleResult(summary="stage 2 done", finished=True),
            CycleResult(summary="stage 3 done", finished=True),
        ]
    )
    team = {"worker": make_agent()}

    resume = ResumeState(
        completed_cycles=1,
        prior_summary="",
        agent_session_ids={},
        completed_stages=[1],
        stage_summaries=["stage 1 was done"],
        current_stage_cycles=0,
    )

    with patch("kodo.viewer.open_viewer", create=True):
        result = orch.run(
            "goal", tmp_project, team,
            max_cycles=5, plan=plan, resume=resume,
        )

    # Should have started at stage 2, completed stages 2 and 3
    assert len(result.stage_results) == 2
    assert result.stage_results[0].stage_index == 2
    assert result.stage_results[1].stage_index == 3
    # Stage 2's goal should include stage 1's summary from resume
    assert "stage 1 was done" in orch._cycle_calls[0]["goal"]


# ── Log parsing tests ────────────────────────────────────────────────────


def _cli_args_event(**overrides):
    return {"ts": "t", "t": 0.1, "event": "cli_args",
            "mode": "saga", "budget_per_step": None, **overrides}


def test_log_parse_stages(tmp_path):
    """parse_run() should extract stage tracking info from log events."""
    log_file = tmp_path / "test.jsonl"
    events = [
        {"ts": "t", "t": 0, "event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "m", "project_dir": "/p", "max_exchanges": 10, "max_cycles": 5,
         "team": [], "has_stages": True, "num_stages": 2},
        _cli_args_event(),
        {"ts": "t", "t": 1, "event": "stage_start", "stage_index": 1, "stage_name": "S1"},
        {"ts": "t", "t": 2, "event": "cycle_end", "summary": "partial"},
        {"ts": "t", "t": 3, "event": "stage_end", "stage_index": 1, "stage_name": "S1",
         "finished": True, "summary": "s1 done"},
        {"ts": "t", "t": 4, "event": "stage_start", "stage_index": 2, "stage_name": "S2"},
        {"ts": "t", "t": 5, "event": "cycle_end", "summary": "partial s2"},
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in events))

    state = log.parse_run(log_file)
    assert state is not None
    assert state.has_stages is True
    assert state.completed_stages == [1]
    assert state.stage_summaries == ["s1 done"]
    assert state.completed_cycles == 2


def test_log_parse_no_stages(tmp_path):
    """parse_run() with no stage events should have empty stage fields."""
    log_file = tmp_path / "test.jsonl"
    events = [
        {"ts": "t", "t": 0, "event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "m", "project_dir": "/p", "max_exchanges": 10, "max_cycles": 5,
         "team": []},
        _cli_args_event(),
        {"ts": "t", "t": 1, "event": "cycle_end", "summary": "done"},
        {"ts": "t", "t": 2, "event": "run_end"},
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in events))

    state = log.parse_run(log_file)
    assert state is not None
    assert state.has_stages is False
    assert state.completed_stages == []
    assert state.stage_summaries == []


# ── CLI helper tests ─────────────────────────────────────────────────────


def test_looks_staged():
    from kodo.cli import _looks_staged

    assert _looks_staged("1. Do X\n2. Do Y\n3. Do Z") is True
    assert _looks_staged("1) First\n2) Second") is True
    assert _looks_staged("Build a web app with authentication") is False
    assert _looks_staged("Just one thing") is False


def test_parse_goal_plan():
    from kodo.cli import _parse_goal_plan

    raw = {
        "context": "Flask app",
        "stages": [
            {"index": 1, "name": "Models", "description": "Build models",
             "acceptance_criteria": "Tests pass"},
            {"index": 2, "name": "API", "description": "Build API",
             "acceptance_criteria": "Endpoints respond"},
        ],
    }
    plan = _parse_goal_plan(raw)
    assert plan.context == "Flask app"
    assert len(plan.stages) == 2
    assert plan.stages[0].name == "Models"
    assert plan.stages[0].acceptance_criteria == "Tests pass"
    assert plan.stages[1].acceptance_criteria == "Endpoints respond"


def test_parse_goal_plan_skips_incomplete_stages():
    from kodo.cli import _parse_goal_plan

    raw = {
        "context": "Test",
        "stages": [
            {"index": 1, "name": "Good", "description": "Has all fields",
             "acceptance_criteria": "Verifiable"},
            {"index": 2, "name": "Missing desc",
             "acceptance_criteria": "X"},  # no description
            {"name": "No index", "description": "Missing index",
             "acceptance_criteria": "X"},  # no index
            {"index": 3, "name": "No AC", "description": "Missing AC"},  # no acceptance_criteria
            "not a dict",
        ],
    }
    plan = _parse_goal_plan(raw)
    assert len(plan.stages) == 1
    assert plan.stages[0].name == "Good"


def test_parse_goal_plan_no_context_returns_empty():
    from kodo.cli import _parse_goal_plan

    plan = _parse_goal_plan({"stages": [{"index": 1, "name": "S", "description": "D",
                                          "acceptance_criteria": "C"}]})
    assert plan.stages == []


def test_load_goal_plan(tmp_path):
    from kodo.cli import _load_goal_plan

    # No file → None
    assert _load_goal_plan(tmp_path) is None

    # Valid file
    kodo_dir = tmp_path / ".kodo"
    kodo_dir.mkdir()
    plan_data = {
        "context": "Test",
        "stages": [
            {"index": 1, "name": "S1", "description": "Do stuff",
             "acceptance_criteria": "Stuff is done"},
        ],
    }
    (kodo_dir / "goal-plan.json").write_text(json.dumps(plan_data))
    plan = _load_goal_plan(tmp_path)
    assert plan is not None
    assert len(plan.stages) == 1

    # Invalid JSON → None
    (kodo_dir / "goal-plan.json").write_text("not json")
    assert _load_goal_plan(tmp_path) is None
