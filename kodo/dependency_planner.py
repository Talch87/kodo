"""Dependency Graph Pre-Planning - Analyze task dependencies and optimize execution order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum
import json
from pathlib import Path
from datetime import datetime


class TaskStatus(Enum):
    """Status of a task in the execution plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class Task:
    """Atomic task in the execution plan."""
    task_id: str
    description: str
    assigned_agent: Optional[str] = None
    estimated_duration_s: float = 0.0
    complexity: str = "medium"  # simple, medium, complex
    
    dependencies: Set[str] = field(default_factory=set)  # task IDs this depends on
    status: TaskStatus = TaskStatus.PENDING
    
    # Execution tracking
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_s: float = 0.0
    success: bool = False
    error: Optional[str] = None


class DependencyGraph:
    """Represents task dependencies as a DAG (Directed Acyclic Graph)."""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.execution_log: Path = Path(".kodo/execution_plan.jsonl")
    
    def add_task(
        self,
        task_id: str,
        description: str,
        agent: Optional[str] = None,
        duration_s: float = 0.0,
        complexity: str = "medium",
        depends_on: Optional[List[str]] = None,
    ) -> Task:
        """Add a task to the graph."""
        task = Task(
            task_id=task_id,
            description=description,
            assigned_agent=agent,
            estimated_duration_s=duration_s,
            complexity=complexity,
            dependencies=set(depends_on or []),
        )
        self.tasks[task_id] = task
        return task
    
    def add_dependency(self, task_id: str, depends_on: str) -> None:
        """Add a dependency between tasks."""
        if task_id in self.tasks:
            self.tasks[task_id].dependencies.add(depends_on)
    
    def is_valid_dag(self) -> Tuple[bool, Optional[str]]:
        """Check if the graph is a valid DAG (no cycles)."""
        visited = set()
        rec_stack = set()
        
        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            for dep in self.tasks[task_id].dependencies:
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    return False, f"Cycle detected involving {task_id}"
        
        return True, None
    
    def get_topological_order(self) -> List[str]:
        """Get tasks in topological order (respecting dependencies)."""
        visited = set()
        order = []
        
        def dfs(task_id: str):
            if task_id in visited:
                return
            visited.add(task_id)
            
            # Visit dependencies first
            for dep in self.tasks[task_id].dependencies:
                dfs(dep)
            
            order.append(task_id)
        
        for task_id in self.tasks:
            dfs(task_id)
        
        return order
    
    def get_critical_path(self) -> Tuple[List[str], float]:
        """
        Find the critical path (longest path through dependencies).
        Critical path determines minimum time to completion.
        """
        # This is simplified - real implementation would use more sophisticated algorithm
        order = self.get_topological_order()
        
        max_time = 0
        max_path = []
        
        # Simple calculation: just sum dependencies
        for task_id in order:
            task = self.tasks[task_id]
            if task.dependencies:
                dep_time = sum(
                    self.tasks[dep].estimated_duration_s
                    for dep in task.dependencies
                )
                total = dep_time + task.estimated_duration_s
                if total > max_time:
                    max_time = total
                    max_path = list(task.dependencies) + [task_id]
        
        return max_path, max_time
    
    def get_parallelizable_tasks(self) -> List[Set[str]]:
        """
        Find groups of tasks that can run in parallel.
        Returns list of sets, each set can run simultaneously.
        """
        order = self.get_topological_order()
        levels = []
        processed = set()
        
        while len(processed) < len(self.tasks):
            # Find tasks whose dependencies are all processed
            current_level = set()
            for task_id in order:
                if task_id not in processed:
                    if self.tasks[task_id].dependencies.issubset(processed):
                        current_level.add(task_id)
            
            if current_level:
                levels.append(current_level)
                processed.update(current_level)
            else:
                break
        
        return levels
    
    def get_bottleneck_tasks(self) -> List[Tuple[str, int]]:
        """
        Find tasks that many other tasks depend on.
        These are bottlenecks in the execution plan.
        """
        dependency_count = {}
        
        for task_id, task in self.tasks.items():
            for dep in task.dependencies:
                dependency_count[dep] = dependency_count.get(dep, 0) + 1
        
        # Return sorted by dependency count
        return sorted(dependency_count.items(), key=lambda x: x[1], reverse=True)
    
    def generate_execution_plan(self) -> str:
        """Generate a human-readable execution plan."""
        is_valid, error = self.is_valid_dag()
        if not is_valid:
            return f"ERROR: Invalid task graph - {error}"
        
        order = self.get_topological_order()
        critical_path, critical_time = self.get_critical_path()
        parallelizable = self.get_parallelizable_tasks()
        bottlenecks = self.get_bottleneck_tasks()
        
        lines = [
            "# Execution Plan",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Summary",
            f"- Total Tasks: {len(self.tasks)}",
            f"- Estimated Duration: {critical_time:.1f}s (critical path)",
            f"- Parallelization Levels: {len(parallelizable)}",
            "",
            "## Task Execution Order",
            ""
        ]
        
        for i, task_id in enumerate(order, 1):
            task = self.tasks[task_id]
            deps_str = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
            lines.append(f"{i}. {task.description}{deps_str}")
            lines.append(f"   - Agent: {task.assigned_agent or 'unassigned'}")
            lines.append(f"   - Duration: {task.estimated_duration_s:.1f}s")
            lines.append(f"   - Complexity: {task.complexity}")
        
        lines.extend([
            "",
            "## Parallelization Opportunities",
            f"These task groups can run in parallel ({len(parallelizable)} phases):",
            ""
        ])
        
        for i, level in enumerate(parallelizable, 1):
            lines.append(f"Phase {i}: {', '.join(level)}")
        
        if bottlenecks:
            lines.extend([
                "",
                "## Bottleneck Tasks",
                "These tasks are heavily depended upon - optimize these first:",
                ""
            ])
            for task_id, count in bottlenecks[:3]:
                task = self.tasks[task_id]
                lines.append(f"- {task_id} ({count} tasks depend on it)")
                lines.append(f"  '{task.description}'")
        
        lines.extend([
            "",
            "## Critical Path",
            f"Longest chain: {' → '.join(critical_path)}",
            f"Duration: {critical_time:.1f}s",
        ])
        
        return "\n".join(lines)


class ExecutionPlanner:
    """Plan optimal execution of Kodo goals."""
    
    def __init__(self):
        self.graph = DependencyGraph()
    
    def parse_goal_into_tasks(self, goal: str, context: str = "") -> List[Task]:
        """
        Parse a goal into subtasks with dependencies.
        This would ideally be done by an AI agent to break down the goal.
        """
        # Placeholder - in real implementation, would call an agent
        tasks = []
        return tasks
    
    def assign_agents_to_tasks(self, tasks: List[Task], available_agents: List[str]) -> None:
        """Intelligently assign agents to tasks based on capability and load."""
        # Simple round-robin for now
        for i, task in enumerate(tasks):
            task.assigned_agent = available_agents[i % len(available_agents)]
    
    def optimize_for_parallelism(self) -> List[Set[str]]:
        """Get task groups optimized for parallel execution."""
        return self.graph.get_parallelizable_tasks()
    
    def optimize_for_cost(self) -> None:
        """Reorder tasks to minimize cost (e.g., use cheaper models first)."""
        # Would factor in model costs, agent performance, etc.
        pass
    
    def optimize_for_speed(self) -> None:
        """Reorder tasks to minimize total execution time."""
        # Would prioritize critical path
        pass
