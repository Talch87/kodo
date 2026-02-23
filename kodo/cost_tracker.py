"""Cost Tracking - Monitor API spending per agent, task, and cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Claude pricing (as of Feb 2024)
PRICING = {
    "claude-opus": {"input": 0.015, "output": 0.075},         # per 1K tokens
    "claude-sonnet": {"input": 0.003, "output": 0.015},       # per 1K tokens
    "claude-haiku": {"input": 0.00080, "output": 0.0024},     # per 1K tokens
}


@dataclass
class CostEntry:
    """Single API call cost entry."""
    timestamp: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    task_type: Optional[str] = None
    cycle_number: int = 0


@dataclass
class CycleCost:
    """Aggregated costs for a single cycle."""
    cycle_number: int
    timestamp: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    
    agents_used: Dict[str, float] = field(default_factory=dict)  # agent -> cost
    models_used: Dict[str, float] = field(default_factory=dict)  # model -> cost
    tasks_used: Dict[str, float] = field(default_factory=dict)   # task -> cost
    entry_count: int = 0


class CostTracker:
    """Track and analyze API costs."""
    
    def __init__(self, data_dir: Path = Path(".kodo/cost_metrics")):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.entries_file = self.data_dir / "cost_entries.jsonl"
        self.cycles_file = self.data_dir / "cycle_costs.json"
        self.budget_file = self.data_dir / "budget.json"
        
        self.budget_usd = self._load_budget()
        self.spent_usd = 0.0
        self.cycles: Dict[int, CycleCost] = {}
        self._load_history()
    
    def record_api_call(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: Optional[str] = None,
        cycle_number: int = 0,
    ) -> CostEntry:
        """Record an API call and calculate its cost."""
        total_tokens = input_tokens + output_tokens
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        
        entry = CostEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            task_type=task_type,
            cycle_number=cycle_number,
        )
        
        # Append to JSONL
        with open(self.entries_file, "a") as f:
            f.write(json.dumps({
                "timestamp": entry.timestamp,
                "agent_name": entry.agent_name,
                "model": entry.model,
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "total_tokens": entry.total_tokens,
                "cost_usd": entry.cost_usd,
                "task_type": entry.task_type,
                "cycle_number": entry.cycle_number,
            }) + "\n")
        
        # Update cycle cost
        if cycle_number not in self.cycles:
            self.cycles[cycle_number] = CycleCost(
                cycle_number=cycle_number,
                timestamp=datetime.now().isoformat(),
            )
        
        cycle = self.cycles[cycle_number]
        cycle.total_input_tokens += input_tokens
        cycle.total_output_tokens += output_tokens
        cycle.total_cost_usd += cost
        cycle.entry_count += 1
        
        cycle.agents_used[agent_name] = cycle.agents_used.get(agent_name, 0) + cost
        cycle.models_used[model] = cycle.models_used.get(model, 0) + cost
        if task_type:
            cycle.tasks_used[task_type] = cycle.tasks_used.get(task_type, 0) + cost
        
        self.spent_usd += cost
        self._save_cycles()
        
        return entry
    
    def get_cycle_cost(self, cycle_number: int) -> Optional[CycleCost]:
        """Get costs for a specific cycle."""
        return self.cycles.get(cycle_number)
    
    def get_total_spent(self) -> float:
        """Get total spending across all cycles."""
        return self.spent_usd
    
    def get_remaining_budget(self) -> float:
        """Get remaining budget."""
        return max(0.0, self.budget_usd - self.spent_usd)
    
    def get_budget_status(self) -> Dict:
        """Get budget utilization."""
        pct_used = (self.spent_usd / self.budget_usd * 100) if self.budget_usd > 0 else 0
        return {
            "budget_usd": self.budget_usd,
            "spent_usd": round(self.spent_usd, 4),
            "remaining_usd": round(self.get_remaining_budget(), 4),
            "percent_used": round(pct_used, 1),
        }
    
    def set_budget(self, budget_usd: float) -> None:
        """Set the monthly budget."""
        self.budget_usd = budget_usd
        with open(self.budget_file, "w") as f:
            json.dump({"budget_usd": budget_usd}, f)
    
    def get_cost_by_agent(self) -> Dict[str, float]:
        """Get total cost per agent."""
        costs = {}
        for cycle in self.cycles.values():
            for agent, cost in cycle.agents_used.items():
                costs[agent] = costs.get(agent, 0) + cost
        return dict(sorted(costs.items(), key=lambda x: x[1], reverse=True))
    
    def get_cost_by_model(self) -> Dict[str, float]:
        """Get total cost per model."""
        costs = {}
        for cycle in self.cycles.values():
            for model, cost in cycle.models_used.items():
                costs[model] = costs.get(model, 0) + cost
        return dict(sorted(costs.items(), key=lambda x: x[1], reverse=True))
    
    def get_cost_by_task(self) -> Dict[str, float]:
        """Get total cost per task type."""
        costs = {}
        for cycle in self.cycles.values():
            for task, cost in cycle.tasks_used.items():
                costs[task] = costs.get(task, 0) + cost
        return dict(sorted(costs.items(), key=lambda x: x[1], reverse=True))
    
    def get_cost_trend(self) -> List[Dict]:
        """Get cost per cycle (for trending/visualization)."""
        trend = []
        for cycle_num in sorted(self.cycles.keys()):
            cycle = self.cycles[cycle_num]
            trend.append({
                "cycle": cycle_num,
                "cost_usd": round(cycle.total_cost_usd, 4),
                "input_tokens": cycle.total_input_tokens,
                "output_tokens": cycle.total_output_tokens,
                "entries": cycle.entry_count,
            })
        return trend
    
    def generate_report(self) -> str:
        """Generate a cost report."""
        status = self.get_budget_status()
        by_agent = self.get_cost_by_agent()
        by_model = self.get_cost_by_model()
        by_task = self.get_cost_by_task()
        
        lines = [
            "# Kodo Cost Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Budget Status",
            f"- Total Budget: ${status['budget_usd']:.2f}",
            f"- Spent: ${status['spent_usd']:.2f} ({status['percent_used']:.1f}%)",
            f"- Remaining: ${status['remaining_usd']:.2f}",
            "",
            "## Cost by Agent (Top 10)",
            ""
        ]
        
        for i, (agent, cost) in enumerate(list(by_agent.items())[:10], 1):
            lines.append(f"{i}. {agent}: ${cost:.4f}")
        
        lines.extend(["", "## Cost by Model", ""])
        for model, cost in by_model.items():
            pct = (cost / status['spent_usd'] * 100) if status['spent_usd'] > 0 else 0
            lines.append(f"- {model}: ${cost:.4f} ({pct:.1f}%)")
        
        if by_task:
            lines.extend(["", "## Cost by Task Type", ""])
            for task, cost in by_task.items():
                pct = (cost / status['spent_usd'] * 100) if status['spent_usd'] > 0 else 0
                lines.append(f"- {task}: ${cost:.4f} ({pct:.1f}%)")
        
        return "\n".join(lines)
    
    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for an API call."""
        pricing = PRICING.get(model, PRICING["claude-haiku"])
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        return input_cost + output_cost
    
    def _load_budget(self) -> float:
        """Load budget from file."""
        if self.budget_file.exists():
            with open(self.budget_file) as f:
                return json.load(f).get("budget_usd", 100.0)
        return 100.0  # Default to $100/month
    
    def _load_history(self) -> None:
        """Load cost history from files."""
        if self.cycles_file.exists():
            with open(self.cycles_file) as f:
                data = json.load(f)
                for cycle_data in data:
                    cycle = CycleCost(
                        cycle_number=cycle_data["cycle_number"],
                        timestamp=cycle_data["timestamp"],
                        total_input_tokens=cycle_data["total_input_tokens"],
                        total_output_tokens=cycle_data["total_output_tokens"],
                        total_cost_usd=cycle_data["total_cost_usd"],
                        agents_used=cycle_data.get("agents_used", {}),
                        models_used=cycle_data.get("models_used", {}),
                        tasks_used=cycle_data.get("tasks_used", {}),
                        entry_count=cycle_data["entry_count"],
                    )
                    self.cycles[cycle.cycle_number] = cycle
                    self.spent_usd += cycle.total_cost_usd
    
    def _save_cycles(self) -> None:
        """Save cycle costs to JSON file."""
        data = [
            {
                "cycle_number": cycle.cycle_number,
                "timestamp": cycle.timestamp,
                "total_input_tokens": cycle.total_input_tokens,
                "total_output_tokens": cycle.total_output_tokens,
                "total_cost_usd": round(cycle.total_cost_usd, 4),
                "agents_used": cycle.agents_used,
                "models_used": cycle.models_used,
                "tasks_used": cycle.tasks_used,
                "entry_count": cycle.entry_count,
            }
            for cycle in sorted(self.cycles.values(), key=lambda c: c.cycle_number)
        ]
        
        with open(self.cycles_file, "w") as f:
            json.dump(data, f, indent=2)
