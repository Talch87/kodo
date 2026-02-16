"""Orchestrator protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from selfocode.agent import Agent


# Team is just a named dict of agents
TeamConfig = dict[str, Agent]


@dataclass
class CycleResult:
    """Result of a single orchestration cycle (one 'day of work')."""
    exchanges: int = 0
    total_cost_usd: float = 0.0
    finished: bool = False
    summary: str = ""


@dataclass
class RunResult:
    """Result of a full multi-cycle run."""
    cycles: list[CycleResult] = field(default_factory=list)

    @property
    def total_exchanges(self) -> int:
        return sum(c.exchanges for c in self.cycles)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.total_cost_usd for c in self.cycles)

    @property
    def finished(self) -> bool:
        return bool(self.cycles) and self.cycles[-1].finished

    @property
    def summary(self) -> str:
        return self.cycles[-1].summary if self.cycles else ""


ORCHESTRATOR_SYSTEM_PROMPT = """\
You are an orchestrator managing a team of AI agents working on a software project.

Your job:
1. Break the goal into steps and decide which team member should handle each one.
2. Review each agent's report. Decide if the work is done, needs a retry with hints, \
or if the plan needs revision.
3. When all work is complete, call the `done` tool with a summary.

Guidelines:
- Give clear, specific directives — not vague instructions.
- If an agent reports a problem, decide: is it confused (give a hint) or is the plan wrong (revise)?
- Don't repeat a failing directive more than twice — escalate to a different agent or revise the approach.
- Keep track of progress. Don't re-do completed work.
- Be concise in your reasoning.

Context management:
- Each agent tool result includes context stats (tokens used, queries in session).
- By default, agents continue their conversation (they remember prior work).
- Set `new_conversation: true` when an agent should start fresh — e.g. switching to an \
unrelated task, or if the agent's context is getting large (>100k tokens).
- If an agent's context was auto-reset (you'll see "[Context was reset: ...]" in the result), \
give it enough context in your next directive to continue effectively.
- Prefer continuing conversations for related sequential work — it's cheaper and the agent \
retains knowledge of what it already did.
"""


def build_team_tools(team: TeamConfig) -> list[dict]:
    """Build Anthropic-style tool definitions from a team config."""
    tools = []
    for name, agent in team.items():
        desc = agent.prompt.strip().split("\n")[0]
        tools.append({
            "name": f"ask_{name}",
            "description": f"Delegate a task to the {name} agent. {desc}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": f"The directive/task to give to {name}.",
                    },
                    "new_conversation": {
                        "type": "boolean",
                        "description": (
                            "If true, reset the agent's session before running "
                            "(start fresh, lose prior context). Default: false "
                            "(continue existing conversation)."
                        ),
                    },
                },
                "required": ["task"],
            },
        })

    tools.append({
        "name": "done",
        "description": "Signal that the goal is complete (or cannot be completed).",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished.",
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether the goal was achieved.",
                },
            },
            "required": ["summary", "success"],
        },
    })
    return tools


class Orchestrator(Protocol):
    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        """Run one cycle of orchestrated work."""
        ...

    def run(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        max_cycles: int = 5,
    ) -> RunResult:
        """Run multiple cycles until done or limit reached."""
        ...
