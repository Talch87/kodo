"""Claude session using claude-agent-sdk with conversation continuity."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from selfocode.sessions.base import QueryResult, SessionStats


def _extract_tokens(usage: dict | None) -> tuple[int | None, int | None]:
    """Pull input/output token counts from the raw usage dict."""
    if not usage:
        return None, None
    inp = usage.get("input_tokens") or usage.get("prompt_tokens")
    out = usage.get("output_tokens") or usage.get("completion_tokens")
    return inp, out


class ClaudeSession:
    def __init__(self, model: str = "sonnet", max_budget_usd: float | None = None):
        self.model = model
        self.max_budget_usd = max_budget_usd
        self._client = None
        self._project_dir: Path | None = None
        self._stats = SessionStats()
        self._loop = asyncio.new_event_loop()

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _ensure_client(self, project_dir: Path) -> None:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        if self._client is not None and self._project_dir == project_dir:
            return

        self._disconnect()
        self._project_dir = project_dir

        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=project_dir,
            disallowed_tools=["AskUserQuestion"],
            model=self.model,
            max_budget_usd=self.max_budget_usd,
        )
        self._client = ClaudeSDKClient(options=options)
        self._run(self._client.connect())

    def _disconnect(self) -> None:
        if self._client is not None:
            self._run(self._client.disconnect())
            self._client = None

    def reset(self) -> None:
        self._disconnect()
        self._stats = SessionStats()

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        from claude_agent_sdk import ResultMessage

        self._ensure_client(project_dir)

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
        return result
