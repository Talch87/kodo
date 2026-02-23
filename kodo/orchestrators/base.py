"""Orchestrator protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from kodo.agent import Agent


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


# NOTE: If the orchestrator still over-specifies tasks despite this prompt,
# the next step is to insert an LLM layer between the orchestrator and the
# team that strips implementation details from directives, passing through
# only the WHAT/WHY and letting agents decide HOW.
ORCHESTRATOR_SYSTEM_PROMPT = """
You are an orchestrator. Get the user's desired outcome.

Your agents have full codebase access and are expert coders. Every implementation
detail you specify risks making the result worse. Tell them WHAT, never HOW.

1. Define desired outcome (user-facing behavior, not code structure).
2. Delegate as small, verifiable goals.
3. Verify results match intent. Commit good work, revert bad iterations.

The team shares .kodo/architecture.md — the architect updates it, workers read it.

You decide: priorities, scope, what "done" looks like, when to revert.
Agents decide: code structure, libraries, patterns, file organization.
""".strip()


# ---------------------------------------------------------------------------
# Shared handler functions — used by both ApiOrchestrator and ClaudeCodeOrchestrator
# ---------------------------------------------------------------------------


def handle_agent_call(
    agent_name: str,
    agent_obj: "Agent",
    task: str,
    project_dir: Path,
    summarizer,
    *,
    new_conversation: bool = False,
    cycle_log: list[str] | None = None,
    orchestrator_tag: str | None = None,
) -> str:
    """Run an agent and return its report (or error string on crash).

    *cycle_log*: if provided, task/result snippets are appended (used by
    ApiOrchestrator for fallback model context).
    *orchestrator_tag*: if set, included as ``orchestrator=`` in log events.
    """
    from kodo import log

    tag = {"orchestrator": orchestrator_tag} if orchestrator_tag else {}

    log.tprint(f"[orchestrator] → {agent_name}: {task[:100]}...")
    if new_conversation:
        log.tprint("[orchestrator]   (new conversation)")

    if cycle_log is not None:
        cycle_log.append(f"→ {agent_name}: {task[:200]}")

    log.emit(
        "orchestrator_tool_call",
        **tag,
        agent=agent_name,
        task=task,
        new_conversation=new_conversation,
    )

    try:
        agent_result = agent_obj.run(
            task,
            project_dir,
            new_conversation=new_conversation,
            agent_name=agent_name,
        )
    except Exception as exc:
        error_msg = f"[ERROR] {agent_name} crashed: {type(exc).__name__}: {exc}"
        log.emit("agent_crash", agent=agent_name, error=str(exc))
        log.tprint(error_msg)
        if cycle_log is not None:
            cycle_log.append(f"← {agent_name}: {error_msg}")
        return error_msg

    report = agent_result.format_report()[:10000]
    log.emit(
        "orchestrator_tool_result",
        **tag,
        agent=agent_name,
        elapsed_s=agent_result.elapsed_s,
        is_error=agent_result.is_error,
        context_reset=agent_result.context_reset,
        session_tokens=agent_result.session_tokens,
        report=report,
    )

    done_msg = f"[{agent_name}] done ({agent_result.elapsed_s:.1f}s)"
    if agent_obj.session.cost_bucket != "cursor_subscription":
        done_msg += f" | session: {agent_result.session_tokens:,} tokens"
    log.tprint(done_msg)
    if agent_result.is_error:
        log.tprint(f"[{agent_name}] reported error")
    if agent_result.context_reset:
        log.tprint(f"[{agent_name}] context reset: {agent_result.context_reset_reason}")

    log.print_stats_table()

    if cycle_log is not None:
        cycle_log.append(f"← {agent_name}: {report[:500]}")

    summarizer.summarize(agent_name, task, report)
    return report


def _auto_commit(
    team: TeamConfig,
    project_dir: Path,
    summary: str,
) -> None:
    """Dispatch a worker to commit completed work after verification passes.

    Non-fatal: logs warnings on failure but never raises.
    """
    from kodo import log

    # Find a worker: prefer worker_fast, fall back to worker_smart, then any
    worker = (
        team.get("worker_fast")
        or team.get("worker_smart")
        or next((a for a in team.values()), None)
    )
    if worker is None:
        log.tprint("[auto-commit] no worker available, skipping")
        log.emit("auto_commit_skip", reason="no_worker")
        return

    worker_name = next((n for n, a in team.items() if a is worker), "worker")

    directive = (
        "Review `git diff` and `git status`. Stage the relevant changed files "
        "and commit with a clear, concise message describing what was accomplished. "
        "Do NOT push. Do NOT commit unrelated or generated files.\n\n"
        f"Summary of completed work:\n{summary}"
    )

    log.tprint(f"[auto-commit] dispatching {worker_name} to commit...")
    log.emit("auto_commit_start", worker=worker_name)

    try:
        result = worker.run(
            directive,
            project_dir,
            new_conversation=True,
            agent_name=f"{worker_name}_auto_commit",
        )
        report = (result.text or "")[:2000]
        log.emit("auto_commit_done", worker=worker_name, report=report)
        log.tprint(f"[auto-commit] {worker_name} finished")
    except Exception as exc:
        log.emit("auto_commit_error", worker=worker_name, error=str(exc))
        log.tprint(f"[auto-commit] {worker_name} failed: {exc}")


def handle_done(
    summary: str,
    success: bool,
    done_signal: "DoneSignal",
    goal: str,
    team: TeamConfig,
    project_dir: Path,
    *,
    verification_state: "VerificationState | None" = None,
    browser_testing: bool = False,
    verifiers: dict | None = None,
    orchestrator_tag: str | None = None,
    auto_commit: bool = False,
) -> str:
    """Shared done-handler logic for both orchestrators.

    Returns the string result to pass back to the orchestrator model.
    """
    from kodo import log

    tag = {"orchestrator": orchestrator_tag} if orchestrator_tag else {}

    log.emit("orchestrator_done_attempt", **tag, summary=summary, success=success)
    log.tprint(f"[orchestrator] DONE requested (success={success}): {summary}")

    if not success:
        done_signal.called = True
        done_signal.summary = summary
        done_signal.success = False
        return "Acknowledged (marked as unsuccessful)."

    rejection = verify_done(
        goal,
        summary,
        team,
        project_dir,
        state=verification_state,
        browser_testing=browser_testing,
        verifiers=verifiers,
    )
    if rejection:
        log.emit("orchestrator_done_rejected", **tag, rejection=rejection[:5000])
        log.tprint("[done] REJECTED — verification found issues")
        return rejection

    # Auto-commit after successful verification
    if auto_commit:
        _auto_commit(team, project_dir, summary)

    done_signal.called = True
    done_signal.summary = summary
    done_signal.success = True
    log.emit("orchestrator_done_accepted", **tag, summary=summary)
    log.tprint("[done] ACCEPTED — all checks pass")
    return "Verified and accepted. All checks pass."


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
    verifiers: dict | None = None,
) -> str | None:
    """Run tester + architect to verify the goal is met.

    Returns None if all checks pass, or a rejection message with issues found.
    *browser_testing*: when False, browser testers are skipped even if configured.
    *verifiers*: optional dict with ``testers``, ``browser_testers``, ``reviewers``
    lists referencing agent keys in *team*.  When ``None``, falls back to legacy
    hardcoded key lookups (``"tester"``, ``"tester_browser"``, ``"architect"``).
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

    # Resolve which agents to use for each verifier role
    if verifiers is not None:
        tester_keys = verifiers.get("testers", [])
        browser_tester_keys = verifiers.get("browser_testers", [])
        reviewer_keys = verifiers.get("reviewers", [])
    else:
        # Legacy fallback — same behavior as before
        tester_keys = ["tester"] if "tester" in team else []
        browser_tester_keys = ["tester_browser"] if "tester_browser" in team else []
        reviewer_keys = ["architect"] if "architect" in team else []

    # Collect tester agents — include browser testers only when requested
    tester_agents: list[tuple[str, Agent]] = []
    for key in tester_keys:
        if key in team:
            tester_agents.append((key, team[key]))
    if browser_testing:
        for key in browser_tester_keys:
            if key in team:
                tester_agents.append((key, team[key]))

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

    # Run reviewer agents
    for reviewer_key in reviewer_keys:
        reviewer_agent = team.get(reviewer_key)
        if not reviewer_agent:
            continue
        try:
            log.tprint(
                f"[done] running {reviewer_key} verification (attempt {attempt})..."
            )
            reviewer_result = reviewer_agent.run(
                verification_prompt
                + "Review the codebase for critical bugs, missing features, "
                "or deviations from the goal. Report ONLY issues found. "
                "If everything looks good, say 'ALL CHECKS PASS'.",
                project_dir,
                new_conversation=reset_session,
                agent_name=f"{reviewer_key}_verification",
            )
            reviewer_report = reviewer_result.text or ""
            log.emit(
                "done_verification", agent=reviewer_key, report=reviewer_report[:5000]
            )
            if not _check_passed(reviewer_report):
                label = reviewer_key.replace("_", " ").title()
                issues.append(f"**{label} found issues:**\n{reviewer_report[:3000]}")
        except Exception as exc:
            log.emit("done_verification_error", agent=reviewer_key, error=str(exc))
            label = reviewer_key.replace("_", " ").title()
            issues.append(f"**{label} crashed:** {exc}")

    # Fallback: if no dedicated verifiers exist, use a worker in a fresh session
    has_dedicated_verifiers = (
        bool(tester_agents)
        or bool(
            browser_tester_keys
        )  # exist even if skipped due to browser_testing=False
        or bool(reviewer_keys)
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
    pending_exchanges: list[dict] = field(default_factory=list)


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
        verifiers: dict | None = None,
        auto_commit: bool = False,
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
        verifiers: dict | None = None,
        auto_commit: bool = False,
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
        verifiers: dict | None = None,
        auto_commit: bool = False,
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
        verifiers: dict | None = None,
        auto_commit: bool = False,
    ) -> RunResult:
        from kodo import log
        from kodo.sessions.claude import ClaudeSession
        from kodo.sessions.codex import CodexSession
        from kodo.sessions.cursor import CursorSession
        from kodo.sessions.gemini_cli import GeminiCliSession

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
                elif isinstance(sess, CodexSession):
                    sess._session_id = sid
                elif isinstance(sess, GeminiCliSession):
                    sess._resume_next = True

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
            team={
                name: {
                    "backend": agent.session.__class__.__name__,
                    "model": getattr(agent.session, "model", "?"),
                }
                for name, agent in team.items()
            },
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
                    verifiers=verifiers,
                    auto_commit=auto_commit,
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
                    verifiers=verifiers,
                    auto_commit=auto_commit,
                )
        finally:
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
                stages_completed=len(result.stage_results),
            )
            log.print_stats_table(final=True)

            # Open the HTML log viewer for easy inspection
            log_file = log.get_log_file()
            if log_file and log_file.exists():
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
        verifiers: dict | None = None,
        auto_commit: bool = False,
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
                verifiers=verifiers,
                auto_commit=auto_commit,
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
        verifiers: dict | None = None,
        auto_commit: bool = False,
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
                    verifiers=verifiers,
                    auto_commit=auto_commit,
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
