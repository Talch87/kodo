"""Orchestrator using Claude Code session with in-process MCP tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from selfocode.orchestrators.base import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    CycleResult,
    RunResult,
    TeamConfig,
)


def _build_mcp_server(team: TeamConfig, project_dir: Path):
    """Build a FastMCP server exposing each team agent as a tool."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("team")

    for name, agent in team.items():
        desc = agent.prompt.strip().split("\n")[0]

        def _make_handler(agent_name, agent_obj):
            def handler(task: str, new_conversation: bool = False) -> str:
                """Delegate a task to this agent."""
                if new_conversation:
                    print(f"  [{agent_name}] new conversation requested")

                result = agent_obj.run(task, project_dir, new_conversation=new_conversation)

                print(f"  [{agent_name}] done ({result.elapsed_s:.1f}s) | session: {result.session_tokens:,} tokens")
                if result.is_error:
                    print(f"  [{agent_name}] reported error")
                if result.context_reset:
                    print(f"  [{agent_name}] context reset: {result.context_reset_reason}")

                return result.format_report()[:10000]
            handler.__name__ = f"ask_{agent_name}"
            handler.__doc__ = (
                f"Delegate a task to the {agent_name} agent. {desc} "
                f"Set new_conversation=true to start a fresh session (lose prior context)."
            )
            return handler

        mcp.add_tool(_make_handler(name, agent), name=f"ask_{name}")

    def done(summary: str, success: bool) -> str:
        """Signal that the goal is complete (or cannot be completed)."""
        print(f"  [orchestrator] DONE (success={success}): {summary}")
        return "Acknowledged."

    mcp.add_tool(done)
    return mcp


class ClaudeCodeOrchestrator:
    """Orchestrator backed by a Claude Code session with MCP tools for agents."""

    def __init__(self, model: str = "opus"):
        self.model = model
        self._loop = asyncio.new_event_loop()

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

        mcp = _build_mcp_server(team, project_dir)

        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=project_dir,
            disallowed_tools=["AskUserQuestion"],
            model=self.model,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            max_turns=max_exchanges,
            mcp_servers={
                "team": {
                    "type": "sdk",
                    "name": "team",
                    "instance": mcp._mcp_server,
                }
            },
        )

        client = ClaudeSDKClient(options=options)
        result = CycleResult()

        prompt = f"# Goal\n\n{goal}\n\nProject directory: {project_dir}"
        if prior_summary:
            prompt += f"\n\n# Previous progress\n\n{prior_summary}\n\nContinue working toward the goal."

        try:
            self._run(client.connect())
            print(f"  [orchestrator] starting cycle...")
            self._run(client.query(prompt))

            async def _collect():
                async for message in client.receive_response():
                    if isinstance(message, ResultMessage):
                        result.exchanges = message.num_turns or 0
                        result.total_cost_usd = message.total_cost_usd or 0.0
                        result.finished = not message.is_error
                        result.summary = message.result or ""
                        if message.is_error:
                            print(f"  [orchestrator] error: {message.result}")
                        else:
                            print(f"  [orchestrator] cycle done: {(message.result or '')[:200]}")

            self._run(_collect())
        finally:
            self._run(client.disconnect())

        return result

    def run(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        max_cycles: int = 5,
    ) -> RunResult:
        result = RunResult()
        prior_summary = ""

        for i in range(1, max_cycles + 1):
            if i > 1:
                print(f"\n  [orchestrator] === CYCLE {i}/{max_cycles} ===")

            cycle_result = self.cycle(
                goal, project_dir, team,
                max_exchanges=max_exchanges,
                prior_summary=prior_summary,
            )
            result.cycles.append(cycle_result)

            if cycle_result.finished:
                break

            prior_summary = cycle_result.summary

        return result
