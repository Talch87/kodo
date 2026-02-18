"""Orchestrator using Pydantic AI with tool_use (Anthropic, Gemini, etc.)."""

from __future__ import annotations

from pathlib import Path

import time

from pydantic_ai import Agent, Tool
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits

from kodo import log
from kodo.summarizer import Summarizer
from kodo.orchestrators.base import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    CycleResult,
    OrchestratorBase,
    TeamConfig,
    verify_done,
)

# Per-1M-token pricing: (input, output)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (5, 25),
    "claude-sonnet-4-5-20250929": (3, 15),
    "gemini-3-pro-preview": (2.0, 12.0),
    "gemini-3-flash-preview": (0.50, 3.0),
}

# Map our model IDs to pydantic-ai model strings (provider:model).
_PYDANTIC_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6": "anthropic:claude-opus-4-6",
    "claude-sonnet-4-5-20250929": "anthropic:claude-sonnet-4-5-20250929",
    "gemini-3-pro-preview": "google-gla:gemini-3-pro-preview",
    "gemini-3-flash-preview": "google-gla:gemini-3-flash-preview",
}


class _DoneSignal:
    """Shared mutable to communicate between the `done` tool and the cycle."""

    def __init__(self) -> None:
        self.called = False
        self.summary = ""
        self.success = False


def _build_tools(
    team: TeamConfig,
    project_dir: Path,
    summarizer: Summarizer,
    done_signal: _DoneSignal,
    goal: str,
) -> list[Tool]:
    """Build pydantic-ai Tool objects for each team agent + the done tool."""
    tools: list[Tool] = []

    for name, agent in team.items():

        def _make_handler(agent_name: str, agent_obj):
            def handler(task: str, new_conversation: bool = False) -> str:
                log.tprint(f"[orchestrator] → {agent_name}: {task[:100]}...")
                if new_conversation:
                    log.tprint("[orchestrator]   (new conversation)")

                log.emit(
                    "orchestrator_tool_call",
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
                    return error_msg

                report = agent_result.format_report()[:10000]
                log.emit(
                    "orchestrator_tool_result",
                    agent=agent_name,
                    elapsed_s=agent_result.elapsed_s,
                    is_error=agent_result.is_error,
                    context_reset=agent_result.context_reset,
                    session_tokens=agent_result.session_tokens,
                    report=report,
                )

                log.tprint(
                    f"[{agent_name}] done ({agent_result.elapsed_s:.1f}s)"
                    f" | session: {agent_result.session_tokens:,} tokens"
                )
                if agent_result.is_error:
                    log.tprint(f"[{agent_name}] reported error")
                if agent_result.context_reset:
                    log.tprint(
                        f"[{agent_name}] context reset: {agent_result.context_reset_reason}"
                    )

                summarizer.summarize(agent_name, task, report)
                return report

            return handler

        tools.append(
            Tool(
                _make_handler(name, agent),
                name=f"ask_{name}",
                description=f"Delegate a task to the {name} agent.\n{agent.description.strip()}",
                takes_ctx=False,
            )
        )

    def done(summary: str, success: bool) -> str:
        """Signal that the goal is complete (or cannot be completed).
        This triggers automated verification by the tester and architect.
        If they find issues, the call is rejected and you must fix them first."""
        log.emit("orchestrator_done_attempt", summary=summary, success=success)
        log.tprint(f"[orchestrator] DONE requested (success={success}): {summary}")

        if not success:
            done_signal.called = True
            done_signal.summary = summary
            done_signal.success = False
            return "Acknowledged (marked as unsuccessful)."

        rejection = verify_done(goal, summary, team, project_dir)
        if rejection:
            log.emit("orchestrator_done_rejected", rejection=rejection[:5000])
            log.tprint("[done] REJECTED — verification found issues")
            return rejection

        done_signal.called = True
        done_signal.summary = summary
        done_signal.success = True
        log.emit("orchestrator_done_accepted", summary=summary)
        log.tprint("[done] ACCEPTED — all checks pass")
        return "Verified and accepted. All checks pass."

    tools.append(Tool(done, takes_ctx=False))
    return tools


def _messages_to_text(messages: list) -> str:
    """Flatten pydantic-ai message history to text for summarization."""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if hasattr(part, "content") and isinstance(part.content, str):
                    parts.append(f"[user] {part.content[:500]}")
                elif isinstance(part, ToolReturnPart):
                    parts.append(
                        f"[user] tool_result({part.tool_name}): {str(part.content)[:300]}"
                    )
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    parts.append(f"[assistant] {part.content[:300]}")
                elif isinstance(part, ToolCallPart):
                    parts.append(f"[assistant] tool_use: {part.tool_name}")
    return "\n".join(parts)


class ApiOrchestrator(OrchestratorBase):
    """Orchestrator backed by Pydantic AI (supports Anthropic, Gemini, etc.)."""

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        max_context_tokens: int | None = None,
        system_prompt: str | None = None,
        fallback_model: str | None = None,
    ):
        self.model = model
        self._orchestrator_name = "api"
        self.max_context_tokens = max_context_tokens
        self._system_prompt = system_prompt or ORCHESTRATOR_SYSTEM_PROMPT
        self._pydantic_model = _PYDANTIC_MODEL_MAP.get(model, model)
        self._fallback_model = fallback_model
        self._fallback_pydantic = (
            _PYDANTIC_MODEL_MAP.get(fallback_model, fallback_model)
            if fallback_model
            else None
        )
        self._summarizer = Summarizer()

    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        done_signal = _DoneSignal()
        tools = _build_tools(team, project_dir, self._summarizer, done_signal, goal)
        result = CycleResult()

        prompt = f"# Goal\n\n{goal}\n\nProject directory: {project_dir}"
        if prior_summary:
            prompt += (
                f"\n\n# Previous progress\n\n{prior_summary}"
                "\n\nContinue working toward the goal."
            )

        log.emit(
            "cycle_start",
            orchestrator="api",
            model=self.model,
            goal=goal,
            project_dir=str(project_dir),
            max_exchanges=max_exchanges,
            has_prior_summary=bool(prior_summary),
            prior_summary=prior_summary or None,
        )

        agent = Agent(
            self._pydantic_model,
            system_prompt=self._system_prompt,
            tools=tools,
        )

        log.tprint(f"\n[orchestrator] starting cycle (max {max_exchanges} requests)...")

        max_retries = 3
        run_result = None
        for attempt in range(max_retries):
            try:
                run_result = agent.run_sync(
                    prompt,
                    usage_limits=UsageLimits(request_limit=max_exchanges),
                )
                break
            except UsageLimitExceeded:
                log.tprint(f"[orchestrator] request limit reached ({max_exchanges})")
                break
            except ModelHTTPError as exc:
                if exc.status_code != 529:
                    raise
                if self._fallback_pydantic and attempt == 0:
                    log.tprint(f"[orchestrator] 529 on {self.model}, falling back to {self._fallback_model}")
                    log.emit("orchestrator_fallback", primary=self.model, fallback=self._fallback_model)
                    agent = Agent(
                        self._fallback_pydantic,
                        system_prompt=self._system_prompt,
                        tools=tools,
                    )
                elif attempt < max_retries - 1:
                    wait = 30 * (attempt + 1)
                    log.tprint(f"[orchestrator] 529 overloaded, retrying in {wait}s...")
                    log.emit("orchestrator_retry", status_code=529, attempt=attempt + 1, wait_s=wait)
                    time.sleep(wait)
                else:
                    raise

        if run_result is not None:
            usage = run_result.usage()
            price_in, price_out = _MODEL_PRICING.get(self.model, (0, 0))
            result.total_cost_usd = (
                usage.input_tokens * price_in + usage.output_tokens * price_out
            ) / 1_000_000
            result.exchanges = usage.requests

        if done_signal.called:
            result.finished = True
            result.success = done_signal.success
            result.summary = done_signal.summary
            log.emit(
                "cycle_end",
                reason="done",
                exchanges=result.exchanges,
                finished=True,
                summary=result.summary,
                cost_usd=result.total_cost_usd,
            )
        else:
            # Model stopped without calling done — summarize for next cycle.
            if run_result is not None:
                result.summary = self._summarize(run_result.all_messages())
            else:
                # UsageLimitExceeded — use accumulated agent summaries.
                accumulated = self._summarizer.get_accumulated_summary()
                result.summary = (
                    f"[Cycle ended: hit request limit after {max_exchanges} requests. "
                    f"Work so far:]\n{accumulated}"
                    if accumulated
                    else "[Cycle ended: hit request limit. No summary available.]"
                )
            log.emit(
                "cycle_end",
                reason="stop_no_done" if run_result else "request_limit",
                exchanges=result.exchanges,
                finished=False,
                summary=result.summary,
                cost_usd=result.total_cost_usd,
            )

        return result

    def _summarize(self, messages: list) -> str:
        """Compress conversation into a summary using a simple agent."""
        log.emit("summarize_start", message_count=len(messages))

        summarizer_agent = Agent(
            self._pydantic_model,
            system_prompt=(
                "Summarize this orchestration conversation concisely. "
                "Include: what was accomplished, what's pending, any known issues."
            ),
        )
        summary_result = summarizer_agent.run_sync(
            f"Conversation:\n\n{_messages_to_text(messages)}",
        )
        summary = summary_result.output
        log.emit("summarize_end", summary=summary)
        return summary
