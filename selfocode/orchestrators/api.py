"""Orchestrator using the Anthropic API directly with tool_use."""

from __future__ import annotations

from pathlib import Path

import anthropic

from selfocode import log
from selfocode.summarizer import Summarizer
from selfocode.orchestrators.base import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    CycleResult,
    OrchestratorBase,
    RunResult,
    TeamConfig,
    build_team_tools,
    verify_done,
)

# Per-1M-token pricing: (input, output)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15, 75),
    "claude-sonnet-4-5-20250929": (3, 15),
}


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


class ApiOrchestrator(OrchestratorBase):
    """Orchestrator backed by direct Anthropic API calls with tool_use."""

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        max_context_tokens: int | None = None,
    ):
        self.model = model
        self._orchestrator_name = "api"
        self.max_context_tokens = max_context_tokens
        self._client = anthropic.Anthropic()
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
        tools = build_team_tools(team)
        result = CycleResult()

        prompt = f"# Goal\n\n{goal}\n\nProject directory: {project_dir}"
        if prior_summary:
            prompt += f"\n\n# Previous progress\n\n{prior_summary}\n\nContinue working toward the goal."
        messages = [{"role": "user", "content": prompt}]

        log.emit("cycle_start", orchestrator="api", model=self.model,
                 goal=goal, project_dir=str(project_dir),
                 max_exchanges=max_exchanges, has_prior_summary=bool(prior_summary),
                 prior_summary=prior_summary or None)

        for exchange in range(1, max_exchanges + 1):
            result.exchanges = exchange

            # Check orchestrator context limit
            if self.max_context_tokens:
                est_tokens = len(_messages_to_text(messages)) // 3
                if est_tokens >= self.max_context_tokens:
                    log.tprint(f"[orchestrator] context limit reached (~{est_tokens:,} tokens)")
                    log.emit("cycle_context_limit", est_tokens=est_tokens,
                             limit=self.max_context_tokens)
                    result.summary = self._summarize(messages)
                    break

            log.tprint(f"\n[orchestrator] thinking... (exchange {exchange}/{max_exchanges})")

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
                price_in, price_out = _MODEL_PRICING.get(self.model, (0, 0))
                result.total_cost_usd += (inp * price_in + out * price_out) / 1_000_000

            assistant_content = response.content

            # Log raw orchestrator response
            raw_blocks = []
            for block in assistant_content:
                if block.type == "text":
                    raw_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    raw_blocks.append({"type": "tool_use", "name": block.name,
                                       "id": block.id, "input": block.input})
            log.emit("orchestrator_response", exchange=exchange,
                     stop_reason=response.stop_reason,
                     input_tokens=getattr(response.usage, "input_tokens", None),
                     output_tokens=getattr(response.usage, "output_tokens", None),
                     content=raw_blocks)

            messages.append({"role": "assistant", "content": assistant_content})

            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    log.tprint(f"[orchestrator] {block.text.strip()[:200]}")

            if response.stop_reason != "tool_use":
                log.tprint("[orchestrator] stopped without calling a tool (done not called)")
                result.summary = self._summarize(messages)
                log.emit("cycle_end", reason="stop_no_tool", exchanges=exchange,
                         finished=False, summary=result.summary,
                         cost_usd=result.total_cost_usd)
                break

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                if block.name == "done":
                    done_summary = block.input.get("summary", "")
                    done_success = block.input.get("success", True)
                    log.tprint(f"[orchestrator] DONE requested: {done_summary}")
                    log.emit("orchestrator_done_attempt", summary=done_summary,
                             success=done_success, exchanges=exchange)

                    if done_success:
                        rejection = verify_done(goal, done_summary, team, project_dir)
                        if rejection:
                            log.emit("orchestrator_done_rejected", rejection=rejection[:5000])
                            log.tprint(f"[done] REJECTED — verification found issues")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": rejection,
                            })
                            continue

                    result.finished = True
                    result.success = done_success
                    result.summary = done_summary
                    log.emit("orchestrator_done_accepted", summary=done_summary,
                             success=done_success, exchanges=exchange,
                             cost_usd=result.total_cost_usd)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Verified and accepted. All checks pass.",
                    })
                    messages.append({"role": "user", "content": tool_results})
                    return result

                agent_name = block.name.removeprefix("ask_")
                agent = team.get(agent_name)
                if not agent:
                    log.emit("orchestrator_tool_error", agent=agent_name,
                             error=f"no agent named '{agent_name}'")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: no agent named '{agent_name}'",
                        "is_error": True,
                    })
                    continue

                task = block.input.get("task", "")
                new_conversation = block.input.get("new_conversation", False)
                log.tprint(f"[orchestrator] → {agent_name}: {task[:100]}...")
                if new_conversation:
                    log.tprint(f"[orchestrator]   (new conversation)")

                log.emit("orchestrator_tool_call", agent=agent_name, task=task,
                         new_conversation=new_conversation, tool_use_id=block.id)

                agent_result = agent.run(task, project_dir,
                                         new_conversation=new_conversation,
                                         agent_name=agent_name)

                report = agent_result.format_report()[:10000]
                log.emit("orchestrator_tool_result", agent=agent_name,
                         elapsed_s=agent_result.elapsed_s,
                         is_error=agent_result.is_error,
                         context_reset=agent_result.context_reset,
                         session_tokens=agent_result.session_tokens,
                         report=report)

                log.tprint(f"[{agent_name}] done ({agent_result.elapsed_s:.1f}s) | session: {agent_result.session_tokens:,} tokens")
                if agent_result.is_error:
                    log.tprint(f"[{agent_name}] reported error")
                if agent_result.context_reset:
                    log.tprint(f"[{agent_name}] context reset: {agent_result.context_reset_reason}")

                self._summarizer.summarize(agent_name, task, report)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": report,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            result.summary = self._summarize(messages)
            log.tprint(f"[orchestrator] exchange limit reached ({max_exchanges})")
            log.emit("cycle_end", reason="exchange_limit", exchanges=max_exchanges,
                     finished=False, summary=result.summary,
                     cost_usd=result.total_cost_usd)

        return result

    def _summarize(self, messages: list[dict]) -> str:
        """Compress conversation into a summary."""
        log.emit("summarize_start", message_count=len(messages))
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
        summary = response.content[0].text
        log.emit("summarize_end", summary=summary)
        return summary

