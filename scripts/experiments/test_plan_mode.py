"""Experiment: what happens when an agent enters plan mode in SDK mode?

Tests different scenarios:
1. bypassPermissions mode, agent enters plan mode voluntarily
2. bypassPermissions mode with EnterPlanMode disallowed
3. What the response looks like
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Allow running inside a Claude Code session
os.environ.pop("CLAUDECODE", None)

# Use the SDK directly
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

PROJECT_DIR = Path("/tmp/test-plan-mode")
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# Capture ALL messages, not just ResultMessage
all_messages = []


async def run_query(
    prompt: str,
    *,
    disallowed_tools: list[str] | None = None,
    permission_mode: str = "bypassPermissions",
    model: str = "haiku",
) -> None:
    """Run a single query and print all messages."""
    print(f"\n{'=' * 60}")
    print(f"Permission mode: {permission_mode}")
    print(f"Disallowed tools: {disallowed_tools}")
    print(f"Prompt: {prompt[:100]}")
    print(f"{'=' * 60}")

    options = ClaudeAgentOptions(
        permission_mode=permission_mode,
        cwd=PROJECT_DIR,
        disallowed_tools=disallowed_tools or ["AskUserQuestion"],
        model=model,
        debug_stderr=None,
        stderr=lambda msg: print(f"  [stderr] {msg}", file=sys.stderr),
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
                # Print first 500 chars
                for line in result_text[:500].splitlines():
                    print(f"    > {line}")
                if len(result_text) > 500:
                    print(f"    > ... ({len(result_text)} chars total)")
            else:
                # Print other message types
                attrs = {
                    k: v
                    for k, v in vars(message).items()
                    if v is not None and k != "usage"
                }
                print(f" | {attrs}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main():
    test = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    if test in (0, 1):
        # Test 1: bypassPermissions - agent enters plan mode voluntarily
        print("\n\n### TEST 1: bypassPermissions + ask to plan ###")
        await run_query(
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/hello.py, then implement it.",
            permission_mode="bypassPermissions",
        )

    if test in (0, 2):
        # Test 2: "plan" permission mode
        print("\n\n### TEST 2: plan permission mode + ask to plan ###")
        await run_query(
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/hello2.py, then implement it.",
            permission_mode="plan",
        )

    if test in (0, 3):
        # Test 3: bypassPermissions with EnterPlanMode disallowed
        print("\n\n### TEST 3: bypassPermissions + EnterPlanMode disallowed ###")
        await run_query(
            "Use plan mode to plan how to create a hello world Python script "
            "at /tmp/test-plan-mode/hello3.py, then implement it.",
            permission_mode="bypassPermissions",
            disallowed_tools=["AskUserQuestion", "EnterPlanMode"],
        )


if __name__ == "__main__":
    asyncio.run(main())
