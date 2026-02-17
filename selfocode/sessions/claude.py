"""Claude session using claude-agent-sdk with conversation continuity."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

from selfocode import log
from selfocode.sessions.base import QueryResult, SessionStats


def _extract_tokens(usage: dict | None) -> tuple[int | None, int | None]:
    """Pull input/output token counts from the raw usage dict."""
    if not usage:
        return None, None
    inp = usage.get("input_tokens") or usage.get("prompt_tokens")
    out = usage.get("output_tokens") or usage.get("completion_tokens")
    return inp, out


class ClaudeSession:
    def __init__(
        self,
        model: str = "sonnet",
        max_budget_usd: float | None = None,
        system_prompt: str | None = None,
        chrome: bool = False,
    ):
        self.model = model
        self.max_budget_usd = max_budget_usd
        self.system_prompt = system_prompt
        self.chrome = chrome
        self._client = None
        self._project_dir: Path | None = None
        self._stats = SessionStats()
        # Plan-mode review state: when a worker calls ExitPlanMode, we capture
        # the plan and interrupt so the orchestrator can review it.  On the
        # *next* query (which carries orchestrator feedback) we auto-approve.
        self._pending_plan: str | None = None
        self._plan_reviewed: bool = False
        # Dedicated thread+loop so we never conflict with a caller's event loop
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    async def _can_use_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: Any,
    ) -> Any:
        """Handle tool permission requests.

        For ExitPlanMode: deny the first call (so the orchestrator can review
        the plan), then approve on the follow-up query after review.
        All other tools are auto-approved.
        """
        from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

        if tool_name == "ExitPlanMode":
            if self._plan_reviewed:
                # Orchestrator already reviewed — let the worker proceed.
                self._plan_reviewed = False
                return PermissionResultAllow()
            # First attempt: capture plan, interrupt so orchestrator can review.
            self._pending_plan = tool_input.get("plan", tool_input.get("content", ""))
            return PermissionResultDeny(
                message=(
                    "Plan submitted for orchestrator review. "
                    "Stop and wait for feedback."
                ),
                interrupt=True,
            )

        return PermissionResultAllow()

    def _run(self, coro):
        """Submit a coroutine to our background loop and block until it completes."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def _ensure_client(self, project_dir: Path) -> None:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        if self._client is not None and self._project_dir == project_dir:
            return

        self._disconnect()
        self._project_dir = project_dir

        extra_args = {}
        if self.chrome:
            extra_args["--chrome"] = None

        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=project_dir,
            disallowed_tools=["AskUserQuestion"],
            model=self.model,
            max_budget_usd=self.max_budget_usd,
            extra_args=extra_args,
            debug_stderr=None,
            stderr=lambda _: None,
            can_use_tool=self._can_use_tool,
            **({"system_prompt": self.system_prompt} if self.system_prompt else {}),
        )
        self._client = ClaudeSDKClient(options=options)
        self._run(self._client.connect())

    def _disconnect(self) -> None:
        if self._client is not None:
            self._run(self._client.disconnect())
            self._client = None

    def close(self) -> None:
        """Stop the event loop and join the background thread."""
        self._disconnect()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()

    def reset(self) -> None:
        log.emit(
            "session_reset",
            session="claude",
            model=self.model,
            tokens_before=self._stats.total_tokens,
            queries_before=self._stats.queries,
        )
        self._disconnect()
        self._stats = SessionStats()

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        from claude_agent_sdk import ResultMessage

        self._ensure_client(project_dir)

        # If a plan was captured in the previous query, the orchestrator has
        # now had a chance to review it (this new query carries its feedback).
        # Allow the next ExitPlanMode call to succeed.
        if self._pending_plan is not None:
            self._plan_reviewed = True
            self._pending_plan = None

        log.emit(
            "session_query_start",
            session="claude",
            model=self.model,
            prompt=prompt,
            max_turns=max_turns,
            project_dir=str(project_dir),
        )

        t0 = time.monotonic()
        self._run(self._client.query(prompt))

        result = QueryResult(text="", elapsed_s=0.0)

        async def _collect():
            nonlocal result
            async for message in self._client.receive_response():
                if isinstance(message, ResultMessage):
                    inp, out = _extract_tokens(message.usage)
                    result = QueryResult(
                        text=message.result or "",
                        elapsed_s=time.monotonic() - t0,
                        turns=message.num_turns,
                        cost_usd=message.total_cost_usd,
                        is_error=message.is_error,
                        input_tokens=inp,
                        output_tokens=out,
                        usage_raw=message.usage,
                    )
                    self._stats.queries += 1
                    self._stats.total_input_tokens += inp or 0
                    self._stats.total_output_tokens += out or 0
                    self._stats.total_cost_usd += message.total_cost_usd or 0.0

        self._run(_collect())

        # If a plan was captured during this query, prepend it to the result
        # so the orchestrator can see and review it.
        if self._pending_plan:
            result = QueryResult(
                text=f"[PROPOSED PLAN]\n{self._pending_plan}\n\n"
                f"[Agent is in plan mode, awaiting review]\n{result.text}",
                elapsed_s=result.elapsed_s,
                turns=result.turns,
                cost_usd=result.cost_usd,
                is_error=False,  # Not an error — plan review is expected
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                usage_raw=result.usage_raw,
            )

        log.emit(
            "session_query_end",
            session="claude",
            model=self.model,
            elapsed_s=result.elapsed_s,
            is_error=result.is_error,
            turns=result.turns,
            cost_usd=result.cost_usd,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            response_text=result.text,
            usage_raw=result.usage_raw,
        )
        return result
