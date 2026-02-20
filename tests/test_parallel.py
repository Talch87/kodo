"""Tests for parallel agent execution with dependency tracking.

Covers: ParallelTask, DispatchResult, ParallelDispatcher, dependency ordering,
parallelism correctness, timing metrics, and edge cases.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from kodo import log
from kodo.agent import Agent
from kodo.parallel import (
    DispatchResult,
    ParallelDispatcher,
    ParallelTask,
    TaskStatus,
    identify_parallelizable,
)
from kodo.sessions.base import QueryResult, SessionStats


# ── Helpers ──────────────────────────────────────────────────────────────


class ParallelFakeSession:
    """Session stub that sleeps for a configurable duration."""

    def __init__(self, response_text: str = "done", delay: float = 0.0):
        self._response_text = response_text
        self._delay = delay
        self._stats = SessionStats()
        self._call_count = 0
        self._lock = threading.Lock()

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def cost_bucket(self) -> str:
        return "test"

    @property
    def session_id(self) -> str | None:
        return "parallel-test-session"

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        time.sleep(self._delay)
        with self._lock:
            self._call_count += 1
            self._stats.queries += 1
        return QueryResult(
            text=self._response_text,
            elapsed_s=self._delay,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

    def reset(self) -> None:
        self._stats = SessionStats()

    @property
    def call_count(self) -> int:
        return self._call_count


class ErrorSession(ParallelFakeSession):
    """Session that always raises."""

    def query(self, prompt, project_dir, *, max_turns):
        raise RuntimeError("Agent crashed")


def make_team(
    delay: float = 0.05,
) -> dict[str, Agent]:
    """Create a test team with fake sessions."""
    return {
        "architect": Agent(
            ParallelFakeSession(response_text="architecture reviewed", delay=delay),
            "Test architect",
            max_turns=10,
            checkpoint_enabled=False,
        ),
        "worker_smart": Agent(
            ParallelFakeSession(response_text="feature implemented", delay=delay),
            "Test smart worker",
            max_turns=10,
            checkpoint_enabled=False,
        ),
        "worker_fast": Agent(
            ParallelFakeSession(response_text="quick change done", delay=delay),
            "Test fast worker",
            max_turns=10,
            checkpoint_enabled=False,
        ),
    }


# ── ParallelTask unit tests ─────────────────────────────────────────────


class TestParallelTask:
    def test_creation(self) -> None:
        task = ParallelTask(
            task_id="t1",
            agent_name="worker_smart",
            directive="Do something",
        )
        assert task.task_id == "t1"
        assert task.status == TaskStatus.PENDING
        assert task.result is None
        assert task.depends_on == []

    def test_with_dependencies(self) -> None:
        task = ParallelTask(
            task_id="impl",
            agent_name="worker_smart",
            directive="Implement",
            depends_on=["survey"],
        )
        assert task.depends_on == ["survey"]

    def test_is_done(self) -> None:
        task = ParallelTask(task_id="t", agent_name="a", directive="d")
        assert not task.is_done
        task.status = TaskStatus.COMPLETED
        assert task.is_done
        task.status = TaskStatus.FAILED
        assert task.is_done
        task.status = TaskStatus.RUNNING
        assert not task.is_done

    def test_elapsed_s(self) -> None:
        task = ParallelTask(task_id="t", agent_name="a", directive="d")
        assert task.elapsed_s == 0.0
        task.start_time = time.monotonic()
        time.sleep(0.05)
        assert task.elapsed_s > 0.04
        task.end_time = time.monotonic()
        elapsed = task.elapsed_s
        time.sleep(0.05)
        # After end_time is set, elapsed should not change
        assert abs(task.elapsed_s - elapsed) < 0.01


# ── DispatchResult unit tests ────────────────────────────────────────────


class TestDispatchResult:
    def test_all_succeeded(self) -> None:
        t1 = ParallelTask(task_id="a", agent_name="w", directive="d")
        t1.status = TaskStatus.COMPLETED
        t2 = ParallelTask(task_id="b", agent_name="w", directive="d")
        t2.status = TaskStatus.COMPLETED
        dr = DispatchResult(tasks=[t1, t2])
        assert dr.all_succeeded is True

    def test_not_all_succeeded(self) -> None:
        t1 = ParallelTask(task_id="a", agent_name="w", directive="d")
        t1.status = TaskStatus.COMPLETED
        t2 = ParallelTask(task_id="b", agent_name="w", directive="d")
        t2.status = TaskStatus.FAILED
        dr = DispatchResult(tasks=[t1, t2])
        assert dr.all_succeeded is False
        assert len(dr.failed_tasks) == 1

    def test_speedup(self) -> None:
        dr = DispatchResult(
            tasks=[],
            total_elapsed_s=5.0,
            sequential_elapsed_s=15.0,
        )
        assert dr.speedup == 3.0
        assert dr.time_saved_s == 10.0
        assert dr.time_saved_pct == pytest.approx(66.67, abs=0.1)

    def test_no_speedup(self) -> None:
        dr = DispatchResult(
            tasks=[],
            total_elapsed_s=10.0,
            sequential_elapsed_s=10.0,
        )
        assert dr.speedup == 1.0
        assert dr.time_saved_pct == 0.0

    def test_zero_time(self) -> None:
        dr = DispatchResult(tasks=[], total_elapsed_s=0.0, sequential_elapsed_s=0.0)
        assert dr.speedup == 1.0
        assert dr.time_saved_pct == 0.0


# ── ParallelDispatcher tests ────────────────────────────────────────────


class TestParallelDispatcher:
    def test_single_task(self, tmp_path: Path) -> None:
        log.init(tmp_path, run_id="parallel-single")
        team = make_team(delay=0.01)
        dispatcher = ParallelDispatcher(team, tmp_path)

        tasks = [
            ParallelTask("t1", "worker_smart", "Do something"),
        ]
        result = dispatcher.dispatch(tasks)

        assert result.all_succeeded
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[0].result is not None
        assert "feature implemented" in tasks[0].result.text

    def test_independent_tasks_run_parallel(self, tmp_path: Path) -> None:
        """Two independent tasks should run concurrently, not sequentially."""
        log.init(tmp_path, run_id="parallel-independent")
        delay = 0.15
        team = make_team(delay=delay)
        dispatcher = ParallelDispatcher(team, tmp_path, max_workers=3)

        tasks = [
            ParallelTask("t1", "worker_smart", "Task A"),
            ParallelTask("t2", "worker_fast", "Task B"),
        ]
        result = dispatcher.dispatch(tasks)

        assert result.all_succeeded
        # If truly parallel, total time should be < 2x single task time
        # Sequential would be ~0.3s, parallel should be ~0.15s
        assert result.total_elapsed_s < delay * 2.5
        assert result.speedup > 1.2  # at least some speedup

    def test_dependency_ordering(self, tmp_path: Path) -> None:
        """Tasks with dependencies wait for their dependencies to complete."""
        log.init(tmp_path, run_id="parallel-deps")
        team = make_team(delay=0.05)
        dispatcher = ParallelDispatcher(team, tmp_path, max_workers=3)

        tasks = [
            ParallelTask("survey", "architect", "Survey codebase"),
            ParallelTask("impl", "worker_smart", "Implement feature",
                         depends_on=["survey"]),
        ]
        result = dispatcher.dispatch(tasks)

        assert result.all_succeeded
        # impl must start after survey completes
        survey = tasks[0]
        impl = tasks[1]
        assert survey.end_time is not None
        assert impl.start_time is not None
        assert impl.start_time >= survey.end_time - 0.01  # small tolerance

    def test_diamond_dependencies(self, tmp_path: Path) -> None:
        """Diamond dependency: A -> B,C -> D."""
        log.init(tmp_path, run_id="parallel-diamond")
        team = make_team(delay=0.05)
        dispatcher = ParallelDispatcher(team, tmp_path, max_workers=3)

        tasks = [
            ParallelTask("a", "architect", "Survey"),
            ParallelTask("b", "worker_smart", "Feature B", depends_on=["a"]),
            ParallelTask("c", "worker_fast", "Feature C", depends_on=["a"]),
            # d depends on both b and c — must wait for both
            ParallelTask("d", "architect", "Final review", depends_on=["b", "c"]),
        ]
        result = dispatcher.dispatch(tasks)

        assert result.all_succeeded
        # d should start after both b and c
        d = tasks[3]
        b = tasks[1]
        c = tasks[2]
        assert d.start_time is not None
        assert b.end_time is not None
        assert c.end_time is not None
        assert d.start_time >= max(b.end_time, c.end_time) - 0.01

    def test_failed_task_detected(self, tmp_path: Path) -> None:
        """A failing agent results in a FAILED task status."""
        log.init(tmp_path, run_id="parallel-fail")
        team = {
            "worker_smart": Agent(
                ErrorSession(),
                "Crashing worker",
                max_turns=10,
                checkpoint_enabled=False,
            ),
        }
        dispatcher = ParallelDispatcher(team, tmp_path)

        tasks = [
            ParallelTask("t1", "worker_smart", "Do something that fails"),
        ]
        result = dispatcher.dispatch(tasks)

        assert not result.all_succeeded
        assert tasks[0].status == TaskStatus.FAILED
        assert tasks[0].error is not None

    def test_missing_agent(self, tmp_path: Path) -> None:
        """Task referencing non-existent agent should fail gracefully."""
        log.init(tmp_path, run_id="parallel-missing")
        team = make_team()
        dispatcher = ParallelDispatcher(team, tmp_path)

        tasks = [
            ParallelTask("t1", "nonexistent_agent", "Do something"),
        ]
        result = dispatcher.dispatch(tasks)

        assert not result.all_succeeded
        assert tasks[0].status == TaskStatus.FAILED
        assert "not found" in tasks[0].error

    def test_empty_task_list(self, tmp_path: Path) -> None:
        team = make_team()
        dispatcher = ParallelDispatcher(team, tmp_path)
        result = dispatcher.dispatch([])
        assert result.all_succeeded  # vacuously true
        assert result.total_elapsed_s == 0.0

    def test_three_parallel_workers(self, tmp_path: Path) -> None:
        """Three independent workers run in parallel."""
        log.init(tmp_path, run_id="parallel-three")
        delay = 0.1
        team = make_team(delay=delay)
        dispatcher = ParallelDispatcher(team, tmp_path, max_workers=3)

        tasks = [
            ParallelTask("t1", "architect", "Review A"),
            ParallelTask("t2", "worker_smart", "Feature B"),
            ParallelTask("t3", "worker_fast", "Feature C"),
        ]
        result = dispatcher.dispatch(tasks)

        assert result.all_succeeded
        # All 3 run in parallel: should take ~0.1s not 0.3s
        assert result.total_elapsed_s < delay * 2.5
        assert result.time_saved_pct > 30  # at least 30% time saved


# ── identify_parallelizable tests ────────────────────────────────────────


class TestIdentifyParallelizable:
    def test_architect_first(self) -> None:
        raw = [
            ("survey", "architect", "Survey the codebase"),
            ("impl_a", "worker_smart", "Feature A"),
            ("impl_b", "worker_fast", "Feature B"),
        ]
        tasks = identify_parallelizable(raw)
        assert len(tasks) == 3
        assert tasks[0].depends_on == []  # architect has no deps
        assert "survey" in tasks[1].depends_on  # workers depend on architect
        assert "survey" in tasks[2].depends_on

    def test_no_architect(self) -> None:
        raw = [
            ("a", "worker_smart", "Task A"),
            ("b", "worker_fast", "Task B"),
        ]
        tasks = identify_parallelizable(raw)
        assert tasks[0].depends_on == []
        assert tasks[1].depends_on == []  # no architect deps

    def test_multiple_architects(self) -> None:
        raw = [
            ("survey1", "architect", "Survey phase 1"),
            ("survey2", "architect", "Survey phase 2"),
            ("impl", "worker_smart", "Implement"),
        ]
        tasks = identify_parallelizable(raw)
        assert tasks[2].depends_on == ["survey1", "survey2"]

    def test_empty_list(self) -> None:
        assert identify_parallelizable([]) == []
