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


ORCHESTRATOR_SYSTEM_PROMPT = """
You are an orchestrator managing a team of AI agents working on a software project.

Your strategy: leverage the AI workers to solve low level problems, you ensure 
1) right direction: 
 - sound architecture, 
 - right libraries, 
 - right user experience being built.
The insight behind is: worker AI can implement almost any well-formulated feature,
but its risk is building the wrong thing. 
 
2) quality control and incremental improvements.
 - you build tools to control quality along the way. You try to boldly test things user will care about and experience.
 - you have strong unit test suite
 - you use git to commit only useful work, you can revert if some iteration just can't get to a good place.
 - Therefore you work in small iterations, putting small goals, verifying they are accomplished well w/o technical debt.

Insight: sometimes iterations of work are 
not helpful - code comes out too complex, either because the task turns out to have contradictions /
technical obstacles or just because worker AI lacked good architectural insight or was sloppy.
You ensure each iteration moves the project forward: 
more clarify, better core abstractions, more useful testing tools.

1. You study the goal and draft a final vision of where you want to get. 
2. You break it down into checkpoints - the verifiable states your product will go through on the path to the final desired state.
3. You break work towards closest checkpoint down into small incremental tasks. You control completion of incremental tasks. You commit them.
4. You revisit your plan as you discover facts about the domain and technology and adapt.

When communicating with agents, give high level goals and let them figure out details.
""".strip()


def build_team_tools(team: TeamConfig) -> list[dict]:
    """Build Anthropic-style tool definitions from a team config."""
    tools = []
    for name, agent in team.items():
        tools.append(
            {
                "name": f"ask_{name}",
                "description": f"Delegate a task to the {name} agent.\n{agent.description.strip()}",
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
            }
        )

    tools.append(
        {
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
        }
    )
    return tools


def verify_done(
    goal: str, summary: str, team: TeamConfig, project_dir: Path
) -> str | None:
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
                verification_prompt
                + "Verify this works end-to-end. Report ONLY issues found. "
                "If everything works, say 'ALL CHECKS PASS'.",
                project_dir,
                new_conversation=True,
                agent_name=f"{tester_name}_verification",
            )
            tester_report = tester_result.text or ""
            log.emit(
                "done_verification", agent=tester_name, report=tester_report[:5000]
            )
            if "ALL CHECKS PASS" not in tester_report.upper():
                issues.append(
                    f"**{tester_name} found issues:**\n{tester_report[:3000]}"
                )
        except Exception as exc:
            log.emit("done_verification_error", agent=tester_name, error=str(exc))
            issues.append(f"**{tester_name} crashed:** {exc}")

    architect_agent = team.get("architect")
    if architect_agent:
        try:
            log.tprint("[done] running architect verification...")
            architect_result = architect_agent.run(
                verification_prompt
                + "Review the codebase for critical bugs, missing features, "
                "or deviations from the goal. Report ONLY issues found. "
                "If everything looks good, say 'ALL CHECKS PASS'.",
                project_dir,
                new_conversation=True,
                agent_name="architect_verification",
            )
            architect_report = architect_result.text or ""
            log.emit(
                "done_verification", agent="architect", report=architect_report[:5000]
            )
            if "ALL CHECKS PASS" not in architect_report.upper():
                issues.append(f"**Architect found issues:**\n{architect_report[:3000]}")
        except Exception as exc:
            log.emit("done_verification_error", agent="architect", error=str(exc))
            issues.append(f"**Architect crashed:** {exc}")

    # Fallback: if no dedicated verifiers exist, use a worker in a fresh session
    has_dedicated_verifiers = bool(tester_agents) or architect_agent is not None
    if not has_dedicated_verifiers:
        # Prefer worker_smart, fall back to any worker
        verifier = team.get("worker_smart") or team.get("worker") or next(
            (a for a in team.values()), None
        )
        if verifier:
            verifier_name = next(
                (n for n, a in team.items() if a is verifier), "worker"
            )
            try:
                log.tprint(f"[done] running {verifier_name} as verifier (fresh session)...")
                verify_result = verifier.run(
                    verification_prompt
                    + "You are reviewing work done by another agent. "
                    "In a FRESH context, review the codebase changes against the goal. "
                    "Check: does it solve the goal? Is the code correct? Did anything break? "
                    "Run tests if available. Report ONLY issues found. "
                    "If everything looks good, say 'ALL CHECKS PASS'.",
                    project_dir,
                    new_conversation=True,
                    agent_name=f"{verifier_name}_verification",
                )
                verify_report = verify_result.text or ""
                log.emit(
                    "done_verification", agent=verifier_name, report=verify_report[:5000]
                )
                if "ALL CHECKS PASS" not in verify_report.upper():
                    issues.append(
                        f"**{verifier_name} (verifier) found issues:**\n{verify_report[:3000]}"
                    )
            except Exception as exc:
                log.emit("done_verification_error", agent=verifier_name, error=str(exc))
                issues.append(f"**{verifier_name} (verifier) crashed:** {exc}")

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

        log.emit(
            "run_start",
            orchestrator=self._orchestrator_name,
            model=self.model,
            goal=goal,
            project_dir=str(project_dir),
            max_exchanges=max_exchanges,
            max_cycles=max_cycles,
            team=list(team.keys()),
        )
        result = RunResult()
        prior_summary = ""

        for i in range(1, max_cycles + 1):
            if i > 1:
                log.tprint(f"\n[orchestrator] === CYCLE {i}/{max_cycles} ===")
            log.emit(
                "run_cycle",
                orchestrator=self._orchestrator_name,
                cycle=i,
                max_cycles=max_cycles,
            )

            cycle_result = self.cycle(
                goal,
                project_dir,
                team,
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

        log.emit(
            "run_end",
            orchestrator=self._orchestrator_name,
            total_cycles=len(result.cycles),
            finished=result.finished,
            total_cost_usd=result.total_cost_usd,
            total_exchanges=result.total_exchanges,
            summary=result.summary,
        )

        # Open the HTML log viewer for easy inspection
        log_file = log.get_log_file()
        if log_file and log_file.exists():
            from selfocode.viewer import open_viewer

            open_viewer(log_file)

        return result
