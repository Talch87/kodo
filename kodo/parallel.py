"""Parallel agent execution with dependency tracking.

Enables running independent agent tasks concurrently while respecting
dependencies between tasks (e.g., architect survey must complete before
worker_smart starts its implementation).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from kodo.agent import Agent, AgentResult
from kodo import log


class TaskStatus(Enum):
    """Lifecycle status of a parallel task."""

    PENDING = "pending"
    WAITING = "waiting"  # waiting on dependencies
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParallelTask:
    """A unit of work that can be dispatched in parallel.

    Attributes
    ----------
    task_id : str
        Unique identifier for this task.
    agent_name : str
        Name of the agent to run this task (must exist in the team).
    directive : str
        The task directive / prompt to send to the agent.
    depends_on : list[str]
        Task IDs that must complete before this task can start.
    status : TaskStatus
        Current execution status.
    result : AgentResult | None
        Result after completion, None if not yet run.
    """

    task_id: str
    agent_name: str
    directive: str
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: AgentResult | None = None
    error: str | None = None
    start_time: float | None = None
    end_time: float | None = None

    @property
    def elapsed_s(self) -> float:
        """Wall-clock time for this task (0 if not yet started)."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.monotonic()
        return end - self.start_time

    @property
    def is_done(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)


@dataclass
class DispatchResult:
    """Result of a parallel dispatch batch."""

    tasks: list[ParallelTask]
    total_elapsed_s: float = 0.0
    sequential_elapsed_s: float = 0.0

    @property
    def all_succeeded(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks)

    @property
    def failed_tasks(self) -> list[ParallelTask]:
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    @property
    def speedup(self) -> float:
        """Ratio of sequential time to parallel time (>1 means faster)."""
        if self.total_elapsed_s == 0:
            return 1.0
        return self.sequential_elapsed_s / self.total_elapsed_s

    @property
    def time_saved_s(self) -> float:
        """Seconds saved by running in parallel."""
        return self.sequential_elapsed_s - self.total_elapsed_s

    @property
    def time_saved_pct(self) -> float:
        """Percentage of time saved."""
        if self.sequential_elapsed_s == 0:
            return 0.0
        return (self.time_saved_s / self.sequential_elapsed_s) * 100


class ParallelDispatcher:
    """Dispatches agent tasks in parallel, respecting dependency ordering.

    Usage::

        dispatcher = ParallelDispatcher(team, project_dir, max_workers=3)

        tasks = [
            ParallelTask("survey", "architect", "Survey the codebase"),
            ParallelTask("impl_a", "worker_smart", "Implement feature A",
                         depends_on=["survey"]),
            ParallelTask("impl_b", "worker_fast", "Implement feature B",
                         depends_on=["survey"]),
        ]

        result = dispatcher.dispatch(tasks)
        # "survey" runs first, then "impl_a" and "impl_b" run in parallel
    """

    def __init__(
        self,
        team: dict[str, Agent],
        project_dir: Path,
        *,
        max_workers: int = 4,
    ):
        self.team = team
        self.project_dir = project_dir
        self.max_workers = max_workers
        self._lock = threading.Lock()

    def dispatch(self, tasks: list[ParallelTask]) -> DispatchResult:
        """Execute tasks respecting dependencies, parallelizing where possible.

        Tasks with no dependencies (or whose dependencies are already complete)
        are dispatched immediately. As tasks complete, dependent tasks become
        eligible for execution.

        Returns a DispatchResult with timing metrics.
        """
        if not tasks:
            return DispatchResult(tasks=[], total_elapsed_s=0.0)

        task_map = {t.task_id: t for t in tasks}
        batch_start = time.monotonic()

        log.emit(
            "parallel_dispatch_start",
            task_count=len(tasks),
            max_workers=self.max_workers,
            task_ids=[t.task_id for t in tasks],
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures: dict[Future, ParallelTask] = {}
            completed_ids: set[str] = set()

            def _submit_ready():
                """Submit all tasks whose dependencies are satisfied."""
                for task in tasks:
                    if task.status != TaskStatus.PENDING:
                        continue
                    deps_met = all(d in completed_ids for d in task.depends_on)
                    if deps_met:
                        task.status = TaskStatus.RUNNING
                        task.start_time = time.monotonic()
                        future = pool.submit(self._run_task, task)
                        futures[future] = task
                        log.emit(
                            "parallel_task_submitted",
                            task_id=task.task_id,
                            agent=task.agent_name,
                        )

            # Initial submission of tasks with no dependencies
            _submit_ready()

            # Process completions and submit newly-eligible tasks
            while futures:
                # Wait for the next completion
                done_futures = []
                for future in as_completed(futures):
                    done_futures.append(future)
                    break  # process one at a time to re-check dependencies

                for future in done_futures:
                    task = futures.pop(future)
                    try:
                        future.result()  # raises if task raised
                    except Exception as exc:
                        task.status = TaskStatus.FAILED
                        task.error = str(exc)
                        task.end_time = time.monotonic()
                        log.emit(
                            "parallel_task_failed",
                            task_id=task.task_id,
                            error=str(exc),
                        )

                    completed_ids.add(task.task_id)
                    log.emit(
                        "parallel_task_completed",
                        task_id=task.task_id,
                        status=task.status.value,
                        elapsed_s=task.elapsed_s,
                    )

                    # Submit newly-eligible tasks
                    _submit_ready()

        batch_elapsed = time.monotonic() - batch_start
        sequential_time = sum(t.elapsed_s for t in tasks)

        log.emit(
            "parallel_dispatch_end",
            total_elapsed_s=batch_elapsed,
            sequential_elapsed_s=sequential_time,
            speedup=sequential_time / batch_elapsed if batch_elapsed > 0 else 1.0,
        )

        return DispatchResult(
            tasks=tasks,
            total_elapsed_s=batch_elapsed,
            sequential_elapsed_s=sequential_time,
        )

    def _run_task(self, task: ParallelTask) -> None:
        """Execute a single task using the appropriate agent."""
        agent = self.team.get(task.agent_name)
        if agent is None:
            task.status = TaskStatus.FAILED
            task.error = f"Agent '{task.agent_name}' not found in team"
            task.end_time = time.monotonic()
            return

        try:
            result = agent.run(
                task.directive,
                self.project_dir,
                agent_name=task.agent_name,
            )
            task.result = result
            if result.is_error:
                task.status = TaskStatus.FAILED
                task.error = result.text
            else:
                task.status = TaskStatus.COMPLETED
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
        finally:
            task.end_time = time.monotonic()


def identify_parallelizable(
    tasks: list[tuple[str, str, str]],
) -> list[ParallelTask]:
    """Convert a list of (task_id, agent_name, directive) to ParallelTasks.

    Simple heuristic: architect tasks run first, then all worker tasks
    can run in parallel (if they don't modify the same files).

    Parameters
    ----------
    tasks : list of (task_id, agent_name, directive) tuples

    Returns
    -------
    list[ParallelTask]
        Tasks with dependency annotations.
    """
    result: list[ParallelTask] = []
    architect_ids: list[str] = []

    for task_id, agent_name, directive in tasks:
        if agent_name == "architect":
            pt = ParallelTask(
                task_id=task_id,
                agent_name=agent_name,
                directive=directive,
            )
            architect_ids.append(task_id)
        else:
            # Workers depend on all architect tasks
            pt = ParallelTask(
                task_id=task_id,
                agent_name=agent_name,
                directive=directive,
                depends_on=list(architect_ids),
            )
        result.append(pt)

    return result
