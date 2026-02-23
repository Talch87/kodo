"""Experiment: test the plan-review flow with deny+interrupt on first ExitPlanMode.

Simulates the orchestrator reviewing a worker's plan:
1. Worker enters plan mode, creates plan, calls ExitPlanMode → denied, interrupted
2. We send a follow-up "Plan approved, implement it"
3. Worker calls ExitPlanMode again → approved, implements
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Any

os.environ.pop("CLAUDECODE", None)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

PROJECT_DIR = Path("/tmp/test-plan-review")
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

pending_plan: str | None = None
plan_reviewed: bool = False


async def can_use_tool(
    tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    global pending_plan, plan_reviewed

    if tool_name == "ExitPlanMode":
        if plan_reviewed:
            print("  [callback] ExitPlanMode → APPROVED (post-review)")
            plan_reviewed = False
            return PermissionResultAllow()
        else:
            pending_plan = tool_input.get("plan", "")
            print("  [callback] ExitPlanMode → DENIED+INTERRUPT (capturing plan)")
            return PermissionResultDeny(
                message="Plan submitted for orchestrator review. Stop and wait for feedback.",
                interrupt=True,
            )

    return PermissionResultAllow()


async def run_query(client: ClaudeSDKClient, prompt: str) -> str:
    """Run a query and return result text."""
    await client.query(prompt)

    result_text = ""
    t0 = time.monotonic()
    async for message in client.receive_response():
        elapsed = time.monotonic() - t0
        msg_type = type(message).__name__

        if isinstance(message, ResultMessage):
            result_text = message.result or "(empty)"
            print(
                f"  [{elapsed:5.1f}s] {msg_type} | is_error={message.is_error}"
                f" | turns={message.num_turns}"
                f" | cost=${message.total_cost_usd or 0:.4f}"
            )
            for line in result_text[:300].splitlines():
                print(f"    > {line}")
            if len(result_text) > 300:
                print(f"    > ... ({len(result_text)} chars total)")

    return result_text


async def main():
    global pending_plan, plan_reviewed

    print("\n=== Plan Review Flow Test ===\n")

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        cwd=PROJECT_DIR,
        disallowed_tools=["AskUserQuestion"],
        model="haiku",
        debug_stderr=None,
        stderr=lambda msg: None,
        can_use_tool=can_use_tool,
    )

    client = ClaudeSDKClient(options=options)
    try:
        await client.connect()

        # Step 1: Ask worker to plan
        print("--- STEP 1: Worker plans (ExitPlanMode will be denied) ---")
        await run_query(
            client,
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-review/reviewed.py. Do NOT implement yet — just plan.",
        )

        if pending_plan:
            print(f"\n  [orchestrator] Captured plan ({len(pending_plan)} chars):")
            for line in pending_plan[:200].splitlines():
                print(f"    | {line}")
            if len(pending_plan) > 200:
                print(f"    | ... ({len(pending_plan)} chars total)")
        else:
            print("\n  [orchestrator] WARNING: No plan captured!")
            return

        # Step 2: Orchestrator reviews and approves
        print("\n--- STEP 2: Orchestrator approves, worker implements ---")
        plan_reviewed = True  # Signal that orchestrator has reviewed
        pending_plan = None

        await run_query(
            client,
            "Plan approved. Proceed with implementation.",
        )

        # Verify file was created
        target = PROJECT_DIR / "reviewed.py"
        if target.exists():
            print(f"\n  SUCCESS: {target} was created!")
            print(f"  Content: {target.read_text()!r}")
        else:
            print(f"\n  FAILURE: {target} was NOT created")

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
