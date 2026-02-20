"""Orchestrator protocol and shared types."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from kodo.agent import Agent
from kodo.sessions.base import SessionCheckpoint


# Team is just a named dict of agents
TeamConfig = dict[str, Agent]


@dataclass
class GoalStage:
    """One stage in a multi-stage goal plan."""

    index: int  # 1-based
    name: str  # short label
    description: str  # full prose for orchestrator
    acceptance_criteria: str  # verifiable "done" definition
    browser_testing: bool = False  # whether this stage needs browser verification


@dataclass
class GoalPlan:
    """Ordered list of stages with shared architectural context."""

    context: str  # shared architectural context
    stages: list[GoalStage]


@dataclass
class StageResult:
    """Groups cycles and outcome for a single stage."""

    stage_index: int
    stage_name: str
    cycles: list["CycleResult"] = field(default_factory=list)
    finished: bool = False
    summary: str = ""


@dataclass
class CycleResult:
    """Result of a single orchestration cycle (one 'day of work')."""

    exchanges: int = 0
    total_cost_usd: float = 0.0
    finished: bool = False
    success: bool = False
    summary: str = ""
    stage_index: int | None = None


@dataclass
class RunResult:
    """Result of a full multi-cycle run."""

    cycles: list[CycleResult] = field(default_factory=list)
    stage_results: list[StageResult] = field(default_factory=list)

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
 - right user experience being built. When modifying user-facing features, consult the designer agent early to validate UX patterns.
The insight behind is: worker AI can implement almost any well-formulated feature,
but its risk is building the wrong thing. 
 
2) quality control and incremental improvements.
 - you build tools to control quality along the way. You try to boldly test things user will care about and experience.
 - you have strong unit test suite
 - you use git to commit only useful work, you can revert if some iteration just can't get to a good place.
 - Therefore you work in small iterations, putting small goals, verifying they are accomplished well w/o technical debt.
 - For TypeScript/JavaScript projects: ALWAYS verify `npm run build` succeeds after code modifications. If build fails, ask agent to fix it before committing.

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

### TypeScript-Specific Quality Rules

For TypeScript/JavaScript codebases:
- When you identify a code pattern error (e.g., missing interface body), do NOT ask the agent to fix just one instance
- Instead: ask the agent to find ALL instances of that pattern and fix them all
- Verification: run `npm run build` BEFORE marking work as done
- If build fails, examine the error, understand the root cause, and ask the agent to re-fix properly
- Only commit when `npm run build` passes completely
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


# Verification signal strings — used in agent prompts and _check_passed()
PASS_SIGNAL = "ALL CHECKS PASS"
MINOR_SIGNAL = "MINOR ISSUES FIXED"


class DoneSignal:
    """Shared mutable to communicate between the ``done`` tool and the cycle loop."""

    def __init__(self) -> None:
        self.called = False
        self.summary = ""
        self.success = False


def build_cycle_prompt(goal: str, project_dir: Path, prior_summary: str = "") -> str:
    """Build the user-turn prompt sent to the orchestrator each cycle."""
    prompt = f"# Goal\n\n{goal}\n\nProject directory: {project_dir}"
    if prior_summary:
        prompt += (
            f"\n\n# Previous progress\n\n{prior_summary}"
            "\n\nContinue working toward the goal."
        )
    return prompt


@dataclass
class VerificationState:
    """Tracks verification attempts within a single cycle.

    Created fresh each ``cycle()`` call. First ``done()`` resets verifier
    sessions for a clean baseline; subsequent calls reuse the session so
    verifiers have persistent context from prior reviews.
    """

    done_attempt: int = 0


def _check_passed(report: str) -> bool:
    """Return True if a verifier report signals acceptance."""
    upper = report.upper()
    return PASS_SIGNAL in upper or MINOR_SIGNAL in upper


def verify_done(
    goal: str,
    summary: str,
    team: TeamConfig,
    project_dir: Path,
    *,
    state: VerificationState | None = None,
    browser_testing: bool = False,
) -> str | None:
    """Run tester + architect to verify the goal is met.

    Returns None if all checks pass, or a rejection message with issues found.
    *browser_testing*: when False, ``tester_browser`` is skipped even if present
    in the team.
    """
    from kodo import log

    if state is None:
        state = VerificationState()

    state.done_attempt += 1
    attempt = state.done_attempt
    reset_session = attempt == 1

    issues = []
    verification_prompt = (
        f"The orchestrator claims the following goal is complete:\n\n"
        f"# Goal\n{goal}\n\n"
        f"# Orchestrator's summary\n{summary}\n\n"
    )

    # Collect tester agents — include tester_browser only when requested
    tester_agents: list[tuple[str, Agent]] = []
    if team.get("tester"):
        tester_agents.append(("tester", team["tester"]))
    if team.get("tester_browser") and browser_testing:
        tester_agents.append(("tester_browser", team["tester_browser"]))
    elif team.get("tester_browser") and not browser_testing:
        log.tprint("[done] skipping tester_browser (not needed for this stage)")

    for tester_name, tester_agent in tester_agents:
        try:
            log.tprint(
                f"[done] running {tester_name} verification (attempt {attempt})..."
            )
            tester_result = tester_agent.run(
                verification_prompt
                + "Verify this works end-to-end. Report ONLY issues found. "
                "If everything works, say 'ALL CHECKS PASS'.",
                project_dir,
                new_conversation=reset_session,
                agent_name=f"{tester_name}_verification",
            )
            tester_report = tester_result.text or ""
            log.emit(
                "done_verification", agent=tester_name, report=tester_report[:5000]
            )
            if not _check_passed(tester_report):
                issues.append(
                    f"**{tester_name} found issues:**\n{tester_report[:3000]}"
                )
        except Exception as exc:
            log.emit("done_verification_error", agent=tester_name, error=str(exc))
            issues.append(f"**{tester_name} crashed:** {exc}")

    architect_agent = team.get("architect")
    if architect_agent:
        try:
            log.tprint(f"[done] running architect verification (attempt {attempt})...")
            architect_result = architect_agent.run(
                verification_prompt
                + "Review the codebase for critical bugs, missing features, "
                "or deviations from the goal. Report ONLY issues found. "
                "If everything looks good, say 'ALL CHECKS PASS'.",
                project_dir,
                new_conversation=reset_session,
                agent_name="architect_verification",
            )
            architect_report = architect_result.text or ""
            log.emit(
                "done_verification", agent="architect", report=architect_report[:5000]
            )
            if not _check_passed(architect_report):
                issues.append(f"**Architect found issues:**\n{architect_report[:3000]}")
        except Exception as exc:
            log.emit("done_verification_error", agent="architect", error=str(exc))
            issues.append(f"**Architect crashed:** {exc}")

    # Fallback: if no dedicated verifiers exist, use a worker in a fresh session
    has_dedicated_verifiers = (
        bool(tester_agents)
        or team.get("tester_browser") is not None  # exists even if skipped
        or architect_agent is not None
    )
    if not has_dedicated_verifiers:
        # Prefer worker_smart, fall back to any worker
        verifier = (
            team.get("worker_smart")
            or team.get("worker")
            or next((a for a in team.values()), None)
        )
        if verifier:
            verifier_name = next(
                (n for n, a in team.items() if a is verifier), "worker"
            )
            try:
                log.tprint(
                    f"[done] running {verifier_name} as verifier (fresh session)..."
                )
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
                    "done_verification",
                    agent=verifier_name,
                    report=verify_report[:5000],
                )
                if not _check_passed(verify_report):
                    issues.append(
                        f"**{verifier_name} (verifier) found issues:**\n{verify_report[:3000]}"
                    )
            except Exception as exc:
                log.emit("done_verification_error", agent=verifier_name, error=str(exc))
                issues.append(f"**{verifier_name} (verifier) crashed:** {exc}")

    if issues:
        return (
            f"DONE REJECTED (attempt {attempt}) — verification found issues that must be fixed:\n\n"
            + "\n\n".join(issues)
            + "\n\nFix these issues and try calling done again."
        )
    return None


def compose_stage_goal(
    plan: GoalPlan,
    stage_index: int,
    completed_summaries: list[str],
) -> str:
    """Build the goal string for a specific stage.

    Includes project context, current stage description + acceptance criteria,
    summaries of completed stages, and a hint about the next stage.
    """
    stage = plan.stages[stage_index - 1]  # 1-based index
    total = len(plan.stages)

    parts: list[str] = []

    # Project context
    parts.append(f"# Project Context\n{plan.context}")

    # Progress so far
    if completed_summaries:
        parts.append("# Completed Stages")
        for i, summary in enumerate(completed_summaries, 1):
            parts.append(f"## Stage {i} — completed\n{summary}")

    # Current stage
    parts.append(
        f"# Current Stage ({stage.index}/{total}): {stage.name}\n{stage.description}"
    )
    if stage.acceptance_criteria:
        parts.append(f"## Acceptance Criteria\n{stage.acceptance_criteria}")

    # Hint about next stage
    if stage.index < total:
        next_stage = plan.stages[stage.index]  # 0-based for next
        parts.append(
            f"## Next Stage Preview\n"
            f"After this stage, the next stage will be: "
            f"**{next_stage.name}** — {next_stage.description[:200]}"
        )

    return "\n\n".join(parts)


@dataclass
class ResumeState:
    """State for resuming a previously interrupted run."""

    completed_cycles: int
    prior_summary: str
    agent_session_ids: dict[str, str]
    completed_stages: list[int]
    stage_summaries: list[str]
    current_stage_cycles: int


class Orchestrator(Protocol):
    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
        browser_testing: bool = False,
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
        resume: ResumeState | None = None,
        plan: GoalPlan | None = None,
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
        browser_testing: bool = False,
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
        resume: ResumeState | None = None,
        plan: GoalPlan | None = None,
    ) -> RunResult:
        from kodo import log
        from kodo.sessions.claude import ClaudeSession
        from kodo.sessions.cursor import CursorSession

        # Inject resume session IDs into agents before starting
        if resume:
            for agent_name, sid in resume.agent_session_ids.items():
                agent = team.get(agent_name)
                if agent is None:
                    continue
                sess = agent.session
                if isinstance(sess, ClaudeSession):
                    sess.resume_session_id = sid
                elif isinstance(sess, CursorSession):
                    sess._chat_id = sid

            # Load checkpoints and log token savings from resume
            checkpoints = SessionCheckpoint.load_all(
                resume.prior_summary[:64] if resume.prior_summary else "unknown",
                project_dir,
            )
            # Try loading by run_id from the log file
            run_id = log.get_run_id()
            if run_id:
                checkpoints = SessionCheckpoint.load_all(run_id, project_dir)

            if checkpoints:
                saved_tokens = sum(cp.tokens_used for cp in checkpoints.values())
                saved_queries = sum(
                    cp.queries_completed for cp in checkpoints.values()
                )
                log.emit(
                    "checkpoint_resume",
                    agents_resumed=list(checkpoints.keys()),
                    total_tokens_in_checkpoints=saved_tokens,
                    total_queries_in_checkpoints=saved_queries,
                    estimated_token_savings=saved_tokens,
                )
                log.tprint(
                    f"[orchestrator] Resumed {len(checkpoints)} agent(s) from "
                    f"checkpoints — ~{saved_tokens:,} tokens preserved"
                )

        start_cycle = (resume.completed_cycles if resume else 0) + 1
        prior_summary = resume.prior_summary if resume else ""

        log.emit(
            "run_start",
            orchestrator=self._orchestrator_name,
            model=self.model,
            goal=goal,
            project_dir=str(project_dir),
            max_exchanges=max_exchanges,
            max_cycles=max_cycles,
            team=list(team.keys()),
            resumed=resume is not None,
            resume_from_cycle=start_cycle if resume else None,
            has_stages=plan is not None and len(plan.stages) > 0,
            num_stages=len(plan.stages) if plan else 0,
        )
        result = RunResult()

        try:
            if plan and plan.stages:
                self._run_staged(
                    goal,
                    project_dir,
                    team,
                    plan,
                    result,
                    max_exchanges=max_exchanges,
                    max_cycles=max_cycles,
                    resume=resume,
                )
            else:
                self._run_single(
                    goal,
                    project_dir,
                    team,
                    result,
                    max_exchanges=max_exchanges,
                    max_cycles=max_cycles,
                    start_cycle=start_cycle,
                    prior_summary=prior_summary,
                )
        finally:
            self._summarizer.shutdown()

            # Clean up agent sessions
            for agent in team.values():
                agent.close()

            # Clean up checkpoints on successful completion
            if result.finished:
                run_id = log.get_run_id()
                if run_id:
                    SessionCheckpoint.clear(run_id, project_dir)
                    log.emit("checkpoints_cleared", run_id=run_id, reason="run_completed")

            log.emit(
                "run_end",
                orchestrator=self._orchestrator_name,
                total_cycles=len(result.cycles),
                finished=result.finished,
                total_cost_usd=result.total_cost_usd,
                total_exchanges=result.total_exchanges,
                summary=result.summary,
                stages_completed=len(result.stage_results),
            )
            log.print_stats_table(final=True)

            # Open the HTML log viewer for easy inspection
            log_file = log.get_log_file()
            if log_file and log_file.exists() and not os.environ.get("KODO_NO_VIEWER"):
                from kodo.viewer import open_viewer

                open_viewer(log_file)

        return result

    def _run_single(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        result: RunResult,
        *,
        max_exchanges: int,
        max_cycles: int,
        start_cycle: int,
        prior_summary: str,
    ) -> None:
        """Original single-goal execution loop."""
        from kodo import log

        for i in range(start_cycle, max_cycles + 1):
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

    def _run_staged(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        plan: GoalPlan,
        result: RunResult,
        *,
        max_exchanges: int,
        max_cycles: int,
        resume: ResumeState | None = None,
    ) -> None:
        """Staged execution: iterate over plan stages with a shared cycle budget."""
        from kodo import log

        global_cycle = 0
        stage_summaries: list[str] = []

        # Resume support: skip completed stages
        start_stage_idx = 0
        if resume and resume.completed_stages:
            start_stage_idx = len(resume.completed_stages)
            stage_summaries = list(resume.stage_summaries)
            global_cycle = resume.completed_cycles

        for stage in plan.stages[start_stage_idx:]:
            log.emit(
                "stage_start",
                stage_index=stage.index,
                stage_name=stage.name,
                global_cycle=global_cycle,
                max_cycles=max_cycles,
            )
            log.tprint(
                f"\n[orchestrator] === STAGE {stage.index}/{len(plan.stages)}: "
                f"{stage.name} ==="
            )

            stage_goal = compose_stage_goal(plan, stage.index, stage_summaries)
            prior_summary = ""
            stage_res = StageResult(
                stage_index=stage.index,
                stage_name=stage.name,
            )

            # Resume: if we're resuming mid-stage, use the prior summary
            if (
                resume
                and resume.current_stage_cycles > 0
                and stage.index == start_stage_idx + 1
            ):
                prior_summary = resume.prior_summary

            stage_finished = False
            while global_cycle < max_cycles:
                global_cycle += 1
                cycle_num = global_cycle

                log.tprint(
                    f"\n[orchestrator] === CYCLE {cycle_num}/{max_cycles} "
                    f"(stage {stage.index}) ==="
                )
                log.emit(
                    "run_cycle",
                    orchestrator=self._orchestrator_name,
                    cycle=cycle_num,
                    max_cycles=max_cycles,
                    stage_index=stage.index,
                )

                cycle_result = self.cycle(
                    stage_goal,
                    project_dir,
                    team,
                    max_exchanges=max_exchanges,
                    prior_summary=prior_summary,
                    browser_testing=stage.browser_testing,
                )
                cycle_result.stage_index = stage.index
                result.cycles.append(cycle_result)
                stage_res.cycles.append(cycle_result)

                if cycle_result.finished:
                    stage_finished = True
                    stage_res.finished = True
                    stage_res.summary = cycle_result.summary
                    stage_summaries.append(cycle_result.summary)
                    log.emit(
                        "stage_end",
                        stage_index=stage.index,
                        stage_name=stage.name,
                        finished=True,
                        summary=cycle_result.summary[:1000],
                        cycles_used=len(stage_res.cycles),
                    )
                    log.tprint(
                        f"[orchestrator] Stage {stage.index} ({stage.name}) "
                        f"completed in {len(stage_res.cycles)} cycle(s)"
                    )
                    break

                prior_summary = cycle_result.summary
            else:
                # max_cycles exhausted
                stage_res.summary = prior_summary
                log.emit(
                    "stage_end",
                    stage_index=stage.index,
                    stage_name=stage.name,
                    finished=False,
                    summary=prior_summary[:1000],
                    cycles_used=len(stage_res.cycles),
                    reason="max_cycles_exhausted",
                )
                log.tprint(
                    f"[orchestrator] Stage {stage.index} ({stage.name}) "
                    f"— budget exhausted after {len(stage_res.cycles)} cycle(s)"
                )

            result.stage_results.append(stage_res)

            if not stage_finished:
                # Stage failed or budget exhausted — stop the run
                log.tprint("[orchestrator] Stopping run — stage did not complete")
                break
