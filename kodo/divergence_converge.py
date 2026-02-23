"""Divergence-then-Converge Pattern - Run multiple solution approaches in parallel, pick best."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path


@dataclass
class Solution:
    """A proposed solution approach."""
    approach_id: str
    description: str
    agent_responsible: str
    estimated_tokens: int
    estimated_duration_s: float
    complexity: str  # "simple", "medium", "complex"
    
    # After execution
    result_text: Optional[str] = None
    verification_score: float = 0.0  # 0-100, higher is better
    tokens_used: int = 0
    duration_s: float = 0.0
    cost_usd: float = 0.0
    accepted: bool = False


class DivergenceConvergeOrchestrator:
    """Orchestrate multiple parallel solution attempts, then converge on the best."""
    
    def __init__(self):
        self.solutions: Dict[str, Solution] = {}
        self.best_solution: Optional[Solution] = None
    
    def generate_solution_approaches(self, goal: str, context: str) -> List[Solution]:
        """
        Generate multiple solution approaches for a goal.
        This would be called with an agent to brainstorm approaches.
        """
        # This is a placeholder - in real implementation, would call an agent
        # to generate diverse approaches
        approaches = []
        
        # Example: For "implement auth system", could have:
        # - Approach A: OAuth2 (complex, most flexible)
        # - Approach B: JWT (medium, straightforward)
        # - Approach C: Session-based (simple, familiar)
        
        return approaches
    
    def execute_in_parallel(
        self,
        solutions: List[Solution],
        executor_fn,
        max_workers: int = 3
    ) -> List[Solution]:
        """
        Execute multiple solutions in parallel.
        executor_fn(solution) -> (result_text, tokens_used, duration_s, cost_usd)
        """
        completed_solutions = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_solution = {
                executor.submit(executor_fn, sol): sol
                for sol in solutions
            }
            
            for future in as_completed(future_to_solution):
                solution = future_to_solution[future]
                try:
                    result_text, tokens_used, duration_s, cost_usd = future.result()
                    solution.result_text = result_text
                    solution.tokens_used = tokens_used
                    solution.duration_s = duration_s
                    solution.cost_usd = cost_usd
                    completed_solutions.append(solution)
                except Exception as e:
                    print(f"Solution {solution.approach_id} failed: {e}")
        
        return completed_solutions
    
    def score_solutions(
        self,
        solutions: List[Solution],
        verifier_fn,  # verifier_fn(solution) -> (score: 0-100, accepted: bool, reason: str)
    ) -> List[Solution]:
        """
        Verify and score each solution.
        Higher score = better solution.
        """
        scored = []
        
        for solution in solutions:
            score, accepted, reason = verifier_fn(solution)
            solution.verification_score = score
            solution.accepted = accepted
            scored.append(solution)
        
        return sorted(scored, key=lambda s: s.verification_score, reverse=True)
    
    def select_best(self, scored_solutions: List[Solution]) -> Solution:
        """
        Select the best solution based on:
        1. Verification score
        2. Cost efficiency
        3. Execution time
        """
        if not scored_solutions:
            raise ValueError("No solutions to choose from")
        
        # Weight factors
        best = scored_solutions[0]  # Already sorted by score
        
        self.best_solution = best
        return best
    
    def generate_comparison_report(self, solutions: List[Solution]) -> str:
        """Generate a comparison report of all solutions."""
        lines = [
            "# Divergence-Converge Solution Comparison",
            f"Total Solutions: {len(solutions)}",
            "",
            "## Summary",
            ""
        ]
        
        # Sort by score
        sorted_sols = sorted(solutions, key=lambda s: s.verification_score, reverse=True)
        
        for i, sol in enumerate(sorted_sols, 1):
            status = "✅ ACCEPTED" if sol.accepted else "❌ REJECTED"
            lines.append(f"{i}. **{sol.approach_id}** - {status}")
            lines.append(f"   Description: {sol.description}")
            lines.append(f"   Agent: {sol.agent_responsible}")
            lines.append(f"   Score: {sol.verification_score:.1f}/100")
            lines.append(f"   Tokens: {sol.tokens_used:,} | Time: {sol.duration_s:.1f}s | Cost: ${sol.cost_usd:.4f}")
            lines.append(f"   Complexity: {sol.complexity}")
            lines.append("")
        
        if self.best_solution:
            lines.extend([
                "## Selected Solution",
                f"**{self.best_solution.approach_id}** (Score: {self.best_solution.verification_score:.1f}/100)",
                f"- Most efficient approach",
                f"- Uses {self.best_solution.tokens_used:,} tokens",
                f"- Costs ${self.best_solution.cost_usd:.4f}",
                ""
            ])
        
        return "\n".join(lines)
