"""Orchestrator using the Anthropic API directly with tool_use."""

from __future__ import annotations

from pathlib import Path

import anthropic

from selfocode.orchestrators.base import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    CycleResult,
    RunResult,
    TeamConfig,
    build_team_tools,
)


def _messages_to_text(messages: list[dict]) -> str:
    """Flatten messages to text for summarization."""
    parts = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            parts.append(f"[{role}] {content[:500]}")
        elif isinstance(content, list):
            for item in content:
                if hasattr(item, "text"):
                    parts.append(f"[{role}] {item.text[:300]}")
                elif hasattr(item, "name"):
                    parts.append(f"[{role}] tool_use: {item.name}")
                elif isinstance(item, dict) and item.get("type") == "tool_result":
                    text = str(item.get("content", ""))[:300]
                    parts.append(f"[{role}] tool_result: {text}")
    return "\n".join(parts)


class ApiOrchestrator:
    """Orchestrator backed by direct Anthropic API calls with tool_use."""

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        max_context_tokens: int | None = None,
    ):
        self.model = model
        self.max_context_tokens = max_context_tokens
        self._client = anthropic.Anthropic()

    def cycle(
        self,
        goal: str,
        project_dir: Path,
        team: TeamConfig,
        *,
        max_exchanges: int = 30,
        prior_summary: str = "",
    ) -> CycleResult:
        tools = build_team_tools(team)
        result = CycleResult()

        prompt = f"# Goal\n\n{goal}\n\nProject directory: {project_dir}"
        if prior_summary:
            prompt += f"\n\n# Previous progress\n\n{prior_summary}\n\nContinue working toward the goal."
        messages = [{"role": "user", "content": prompt}]

        for exchange in range(1, max_exchanges + 1):
            result.exchanges = exchange

            # Check orchestrator context limit
            if self.max_context_tokens:
                est_tokens = len(_messages_to_text(messages)) // 3
                if est_tokens >= self.max_context_tokens:
                    print(f"  [orchestrator] context limit reached (~{est_tokens:,} tokens)")
                    result.summary = self._summarize(messages)
                    break

            print(f"\n  [orchestrator] thinking... (exchange {exchange}/{max_exchanges})")

            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=ORCHESTRATOR_SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            if response.usage:
                inp = response.usage.input_tokens
                out = response.usage.output_tokens
                result.total_cost_usd += (inp * 3 + out * 15) / 1_000_000

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    print(f"  [orchestrator] {block.text.strip()[:200]}")

            if response.stop_reason != "tool_use":
                print("  [orchestrator] stopped without calling a tool")
                result.finished = True
                result.summary = self._summarize(messages)
                break

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                if block.name == "done":
                    print(f"  [orchestrator] DONE: {block.input.get('summary', '')}")
                    result.finished = True
                    result.summary = block.input.get("summary", "")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Acknowledged.",
                    })
                    messages.append({"role": "user", "content": tool_results})
                    return result

                agent_name = block.name.removeprefix("ask_")
                agent = team.get(agent_name)
                if not agent:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: no agent named '{agent_name}'",
                        "is_error": True,
                    })
                    continue

                task = block.input.get("task", "")
                new_conversation = block.input.get("new_conversation", False)
                print(f"  [orchestrator] → {agent_name}: {task[:100]}...")
                if new_conversation:
                    print(f"  [orchestrator]   (new conversation)")

                agent_result = agent.run(task, project_dir, new_conversation=new_conversation)

                print(f"  [{agent_name}] done ({agent_result.elapsed_s:.1f}s) | session: {agent_result.session_tokens:,} tokens")
                if agent_result.is_error:
                    print(f"  [{agent_name}] reported error")
                if agent_result.context_reset:
                    print(f"  [{agent_name}] context reset: {agent_result.context_reset_reason}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": agent_result.format_report()[:10000],
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            result.summary = self._summarize(messages)
            print(f"  [orchestrator] exchange limit reached ({max_exchanges})")

        return result

    def _summarize(self, messages: list[dict]) -> str:
        """Compress conversation into a summary."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=(
                "Summarize this orchestration conversation concisely. "
                "Include: what was accomplished, what's pending, any known issues."
            ),
            messages=[
                {"role": "user", "content": f"Conversation:\n\n{_messages_to_text(messages)}"},
            ],
        )
        return response.content[0].text

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
