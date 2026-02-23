"""Experiment: does can_use_tool intercept ExitPlanMode?

Tests whether we can auto-approve plan mode transitions via the callback.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Allow running inside a Claude Code session
os.environ.pop("CLAUDECODE", None)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

PROJECT_DIR = Path("/tmp/test-plan-mode")
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# Track which tools trigger the callback
tool_calls_seen: list[str] = []


async def can_use_tool(
    tool_name: str, tool_input: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Callback that logs all tool permission requests and auto-approves."""
    tool_calls_seen.append(tool_name)
    print(f"  [can_use_tool] tool={tool_name} input={tool_input}")
    return PermissionResultAllow()


async def run_test(
    test_num: int,
    prompt: str,
    *,
    permission_mode: str = "bypassPermissions",
    use_callback: bool = True,
    model: str = "haiku",
) -> None:
    print(f"\n{'=' * 60}")
    print(
        f"TEST {test_num}: permission_mode={permission_mode}, callback={use_callback}"
    )
    print(f"Prompt: {prompt[:100]}")
    print(f"{'=' * 60}")

    tool_calls_seen.clear()

    options = ClaudeAgentOptions(
        permission_mode=permission_mode,
        cwd=PROJECT_DIR,
        disallowed_tools=["AskUserQuestion"],
        model=model,
        debug_stderr=None,
        stderr=lambda msg: print(f"  [stderr] {msg}", file=sys.stderr),
        can_use_tool=can_use_tool if use_callback else None,
    )

    client = ClaudeSDKClient(options=options)
    try:
        await client.connect()
        await client.query(prompt)

        t0 = time.monotonic()
        async for message in client.receive_response():
            elapsed = time.monotonic() - t0
            msg_type = type(message).__name__
            print(f"  [{elapsed:5.1f}s] {msg_type}", end="")

            if isinstance(message, ResultMessage):
                print(
                    f" | is_error={message.is_error}"
                    f" | turns={message.num_turns}"
                    f" | cost=${message.total_cost_usd or 0:.4f}"
                )
                result_text = message.result or "(empty)"
                for line in result_text[:300].splitlines():
                    print(f"    > {line}")
                if len(result_text) > 300:
                    print(f"    > ... ({len(result_text)} chars total)")
            else:
                attrs = {
                    k: v
                    for k, v in vars(message).items()
                    if v is not None and k != "usage"
                }
                print(f" | {attrs}")

        print(f"\n  Tools that triggered can_use_tool: {tool_calls_seen}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main():
    test = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    if test in (0, 1):
        # Test 1: bypassPermissions WITH can_use_tool callback
        # Q: Does ExitPlanMode trigger the callback in bypassPermissions mode?
        await run_test(
            1,
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/callback1.py, then implement it.",
            permission_mode="bypassPermissions",
            use_callback=True,
        )

    if test in (0, 2):
        # Test 2: "default" mode WITH can_use_tool callback (approve everything)
        # Q: Does using default mode + callback work better than bypassPermissions?
        await run_test(
            2,
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/callback2.py, then implement it.",
            permission_mode="default",
            use_callback=True,
        )

    if test in (0, 3):
        # Test 3: "plan" mode WITH can_use_tool callback
        # Q: Can we start in plan mode and auto-approve ExitPlanMode?
        await run_test(
            3,
            "Plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/callback3.py, then implement it.",
            permission_mode="plan",
            use_callback=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
