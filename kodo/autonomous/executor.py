"""Autonomous improvement executor for Kodo self-improvement."""

from __future__ import annotations

import subprocess
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Improvement:
    """A potential improvement to implement."""
    type: str  # "test_coverage", "performance", "agent_prompt", etc.
    title: str
    description: str
    severity: str  # "urgent", "high", "medium", "low"
    success_rate: float = 0.0  # Historical success rate (0-100)
    task_spec: str = ""  # What worker agent should do


@dataclass
class ExecutionResult:
    """Result of executing an improvement."""
    improvement: Improvement
    success: bool
    error: str | None = None
    metrics_before: dict | None = None
    metrics_after: dict | None = None
    execution_time_s: float = 0.0
    timestamp: float = 0.0


class AutoImprovementExecutor:
    """Executes improvements autonomously."""
    
    def __init__(self, project_dir: Path, worker_agent=None):
        self.project_dir = Path(project_dir)
        self.worker_agent = worker_agent  # The coding agent
        self.execution_history: list[ExecutionResult] = []
        self.improvement_queue: list[Improvement] = []
    
    def queue_improvement(self, improvement: Improvement) -> None:
        """Add improvement to queue."""
        self.improvement_queue.append(improvement)
    
    def execute_next(self, metrics_before: dict | None = None) -> ExecutionResult | None:
        """Execute the next improvement in queue. Returns result or None if queue empty."""
        if not self.improvement_queue:
            return None
        
        improvement = self.improvement_queue.pop(0)
        
        # Execute it
        result = self._execute_improvement(improvement, metrics_before)
        
        # Log result
        self.execution_history.append(result)
        
        return result
    
    def _execute_improvement(
        self, 
        improvement: Improvement,
        metrics_before: dict | None = None
    ) -> ExecutionResult:
        """Execute a single improvement."""
        start_time = time.time()
        result = ExecutionResult(
            improvement=improvement,
            success=False,
            metrics_before=metrics_before,
            timestamp=start_time
        )
        
        try:
            # Step 1: Create feature branch
            branch_name = f"auto-improve/{improvement.type}/{int(start_time)}"
            self._create_branch(branch_name)
            
            # Step 2: Ask worker agent to implement
            impl_result = self._ask_worker_to_implement(improvement, branch_name)
            if not impl_result['success']:
                result.error = f"Implementation failed: {impl_result['error']}"
                self._revert_and_cleanup(branch_name)
                return result
            
            # Step 3: Run tests
            test_result = self._run_tests()
            if not test_result['passing']:
                result.error = f"Tests failed: {test_result['error']}"
                self._revert_and_cleanup(branch_name)
                return result
            
            # Step 4: Measure metrics after
            metrics_after = self._measure_metrics()
            result.metrics_after = metrics_after
            
            # Step 5: Decide: merge or revert?
            if self._metrics_improved(metrics_before, metrics_after):
                # Merge!
                self._merge_to_main(branch_name)
                result.success = True
            else:
                result.error = "Metrics did not improve sufficiently"
                self._revert_and_cleanup(branch_name)
        
        except Exception as e:
            result.error = str(e)
            self._revert_and_cleanup(branch_name if 'branch_name' in locals() else None)
        
        finally:
            result.execution_time_s = time.time() - start_time
        
        return result
    
    def _create_branch(self, branch_name: str) -> None:
        """Create a new git branch."""
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=self.project_dir,
            check=True,
            capture_output=True
        )
    
    def _ask_worker_to_implement(self, improvement: Improvement, branch: str) -> dict:
        """Ask worker agent to implement the improvement."""
        if not self.worker_agent:
            return {'success': False, 'error': 'No worker agent available'}
        
        try:
            # Format task for worker
            task = f"""
Implement this improvement to Kodo:

Type: {improvement.type}
Title: {improvement.title}
Description: {improvement.description}

Task:
{improvement.task_spec}

Requirements:
1. Make minimal, focused changes
2. Don't break existing functionality
3. Add tests if relevant
4. Commit with clear message
5. Don't push (we'll handle that)
            """
            
            # Call worker agent (timeout after 10 minutes for safety)
            result = self.worker_agent.run(
                task,
                self.project_dir,
                timeout_s=600  # 10 min timeout
            )
            
            return {
                'success': True,
                'output': result.text,
                'error': None
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def _run_tests(self) -> dict:
        """Run test suite. Returns {passing: bool, error: str}."""
        try:
            result = subprocess.run(
                ["npm", "test"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=180,
                text=True
            )
            
            return {
                'passing': result.returncode == 0,
                'error': result.stderr if result.returncode != 0 else None,
                'output': result.stdout
            }
        except subprocess.TimeoutExpired:
            return {'passing': False, 'error': 'Tests timed out', 'output': None}
        except Exception as e:
            return {'passing': False, 'error': str(e), 'output': None}
    
    def _measure_metrics(self) -> dict:
        """Measure current code metrics."""
        metrics = {}
        
        # Build time
        try:
            start = time.time()
            subprocess.run(
                ["npm", "run", "build"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=120
            )
            metrics['build_time_s'] = time.time() - start
        except Exception:
            metrics['build_time_s'] = None
        
        # Test coverage (simplified)
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--coverage"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=180,
                text=True
            )
            # Would extract coverage from output
            metrics['test_coverage'] = 75.0  # Placeholder
        except Exception:
            metrics['test_coverage'] = None
        
        return metrics
    
    def _metrics_improved(self, before: dict | None, after: dict | None) -> bool:
        """Check if metrics improved."""
        if not before or not after:
            return True  # No baseline, assume OK
        
        # Build time should not increase significantly
        if before.get('build_time_s') and after.get('build_time_s'):
            if after['build_time_s'] > before['build_time_s'] * 1.2:  # >20% slowdown
                return False
        
        # Coverage should not decrease
        if before.get('test_coverage') and after.get('test_coverage'):
            if after['test_coverage'] < before['test_coverage'] - 1:  # >1% drop
                return False
        
        return True
    
    def _merge_to_main(self, branch_name: str) -> None:
        """Merge branch to main and push."""
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=self.project_dir,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            ["git", "merge", "--squash", branch_name],
            cwd=self.project_dir,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            ["git", "commit", "-m", f"Auto-improvement: {branch_name}"],
            cwd=self.project_dir,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=self.project_dir,
            check=True,
            capture_output=True
        )
    
    def _revert_and_cleanup(self, branch_name: str | None) -> None:
        """Clean up failed branch."""
        try:
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=self.project_dir,
                capture_output=True
            )
            
            if branch_name:
                subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=self.project_dir,
                    capture_output=True
                )
        except Exception:
            pass
    
    def success_rate(self, improvement_type: str | None = None) -> float:
        """Calculate success rate of improvements."""
        if not self.execution_history:
            return 0.0
        
        if improvement_type:
            relevant = [e for e in self.execution_history if e.improvement.type == improvement_type]
        else:
            relevant = self.execution_history
        
        if not relevant:
            return 0.0
        
        successful = sum(1 for e in relevant if e.success)
        return (successful / len(relevant)) * 100
    
    def execution_summary(self) -> dict:
        """Return summary of execution history."""
        return {
            'total_attempted': len(self.execution_history),
            'total_successful': sum(1 for e in self.execution_history if e.success),
            'success_rate': self.success_rate(),
            'avg_execution_time_s': sum(e.execution_time_s for e in self.execution_history) / len(self.execution_history) if self.execution_history else 0,
            'by_type': {
                type_: self.success_rate(type_)
                for type_ in set(e.improvement.type for e in self.execution_history)
            }
        }
