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
    success: bool = False
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
1. Read the goal and pick ONE small, concrete thing to build first.
2. Delegate it to the worker with a SHORT directive (2-5 sentences). \
Describe the desired behavior, not the implementation. No file lists, \
no module structures, no code snippets — the worker is a skilled coder.
3. After 1-2 worker steps, ask the tester to verify ("a user should be able to...").
4. Fix any issues the tester finds before moving on.
5. Pick the NEXT small thing. Repeat until done, then call the `done` tool.

Task sizing:
- Each worker task should be ONE feature or change that can be built and tested independently.
Example: in a new TD game project
- BAD: "Set up the entire project with 12 modules, 5 tower types, 5 enemy types, \
full HUD layout, save/load, procedural generation, and input handling."
- GOOD: "Create a new Rust project with a terminal UI that shows a main menu \
with New Game and Quit options."
- Then GOOD next step: "Add a grid-based map that generates a winding path \
from the left edge to a crystal in the center."
- Let the worker make all implementation decisions (library choices, module structure, \
naming, architecture). Just describe what the user should see or experience.

Handling agent responses:
- If a worker result contains [PROPOSED PLAN], review it. \
If the plan looks good, tell the worker: "Plan approved, proceed with implementation." \
If you want changes, describe them clearly and the worker will revise.
- If a worker seems stuck or unproductive, reset its conversation \
(new_conversation=true) and give a clear, fresh directive.
- Don't repeat a failing directive more than twice — revise the approach.

Guidelines:
- Don't dictate implementation — describe the goal and let agents decide how.
- If a worker needs context about existing code, let it read the codebase (it can).
- If the project directory already has code, have the worker read it before making changes.

Context management:
- Each agent tool result includes context stats (tokens used, queries in session).
- If an agent's context was auto-reset (you'll see "[Context was reset: ...]" in the result), \
give it enough context in your next directive to continue effectively.
"""


def build_team_tools(team: TeamConfig) -> list[dict]:
    """Build Anthropic-style tool definitions from a team config."""
    tools = []
    for name, agent in team.items():
        desc = agent.description.strip().split("\n")[0]
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
                        "description": "Reset agent's session (rarely needed). Default: false.",
                    },
                },
                "required": ["task"],
            },
        })

    tools.append({
        "name": "done",
        "description": "Signal that the goal is complete (or cannot be completed). "
                       "This triggers automated verification by the tester and architect. "
                       "If they find issues, the call is rejected and you must fix them first.",
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


def verify_done(goal: str, summary: str, team: TeamConfig,
                project_dir: Path) -> str | None:
    """Run tester + architect to verify the goal is met.

    Returns None if all checks pass, or a rejection message with issues found.
    """
    from selfocode import log

    issues = []
    verification_prompt = (
        f"The orchestrator claims the following goal is complete:\n\n"
        f"# Goal\n{goal}\n\n"
        f"# Orchestrator's summary\n{summary}\n\n"
    )

    # Collect tester agents — run all that exist
    tester_agents: list[tuple[str, Agent]] = []
    if team.get("tester"):
        tester_agents.append(("tester", team["tester"]))
    if team.get("tester_browser"):
        tester_agents.append(("tester_browser", team["tester_browser"]))

    for tester_name, tester_agent in tester_agents:
        try:
            log.tprint(f"[done] running {tester_name} verification...")
            tester_result = tester_agent.run(
                verification_prompt + "Verify this works end-to-end. Report ONLY issues found. "
                "If everything works, say 'ALL CHECKS PASS'.",
                project_dir, new_conversation=True, agent_name=f"{tester_name}_verification")
            tester_report = tester_result.text or ""
            log.emit("done_verification", agent=tester_name, report=tester_report[:5000])
            if "ALL CHECKS PASS" not in tester_report.upper():
                issues.append(f"**{tester_name} found issues:**\n{tester_report[:3000]}")
        except Exception as exc:
            log.emit("done_verification_error", agent=tester_name, error=str(exc))
            issues.append(f"**{tester_name} crashed:** {exc}")

    architect_agent = team.get("architect")
    if architect_agent:
        try:
            log.tprint("[done] running architect verification...")
            architect_result = architect_agent.run(
                verification_prompt + "Review the codebase for critical bugs, missing features, "
                "or deviations from the goal. Report ONLY issues found. "
                "If everything looks good, say 'ALL CHECKS PASS'.",
                project_dir, new_conversation=True, agent_name="architect_verification")
            architect_report = architect_result.text or ""
            log.emit("done_verification", agent="architect", report=architect_report[:5000])
            if "ALL CHECKS PASS" not in architect_report.upper():
                issues.append(f"**Architect found issues:**\n{architect_report[:3000]}")
        except Exception as exc:
            log.emit("done_verification_error", agent="architect", error=str(exc))
            issues.append(f"**Architect crashed:** {exc}")

    if issues:
        return (
            "DONE REJECTED — verification found issues that must be fixed:\n\n"
            + "\n\n".join(issues)
            + "\n\nFix these issues and try calling done again."
        )
    return None


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


class OrchestratorBase:
    """Shared run() logic for all orchestrator implementations.

    Subclasses must set ``self.model``, ``self._summarizer``, and
    ``self._orchestrator_name`` before calling ``super().__init__()``,
    and implement ``cycle()``.
    """

    model: str
    _orchestrator_name: str

    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        raise NotImplementedError

    def run(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        max_cycles: int = 5,
    ) -> RunResult:
        from selfocode import log

        log.emit("run_start", orchestrator=self._orchestrator_name, model=self.model,
                 goal=goal, project_dir=str(project_dir),
                 max_exchanges=max_exchanges, max_cycles=max_cycles,
                 team=list(team.keys()))
        result = RunResult()
        prior_summary = ""

        for i in range(1, max_cycles + 1):
            if i > 1:
                log.tprint(f"\n[orchestrator] === CYCLE {i}/{max_cycles} ===")
            log.emit("run_cycle", orchestrator=self._orchestrator_name,
                     cycle=i, max_cycles=max_cycles)

            cycle_result = self.cycle(
                goal, project_dir, team,
                max_exchanges=max_exchanges,
                prior_summary=prior_summary,
            )
            result.cycles.append(cycle_result)

            if cycle_result.finished:
                break

            prior_summary = cycle_result.summary

        self._summarizer.shutdown()

        # Clean up agent sessions
        for agent in team.values():
            agent.close()

        log.emit("run_end", orchestrator=self._orchestrator_name,
                 total_cycles=len(result.cycles), finished=result.finished,
                 total_cost_usd=result.total_cost_usd,
                 total_exchanges=result.total_exchanges, summary=result.summary)
        return result
