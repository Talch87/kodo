"""Mock replacements for claude_agent_sdk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockResultMessage:
    """Mimics claude_agent_sdk.ResultMessage."""

    result: str = ""
    is_error: bool = False
    num_turns: int | None = 1
    total_cost_usd: float | None = 0.0
    usage: dict | None = field(
        default_factory=lambda: {
            "input_tokens": 100,
            "output_tokens": 50,
        }
    )


class MockPermissionResultAllow:
    """Mimics claude_agent_sdk.types.PermissionResultAllow."""

    pass


class MockPermissionResultDeny:
    """Mimics claude_agent_sdk.types.PermissionResultDeny."""

    def __init__(self, message: str = "", interrupt: bool = False):
        self.message = message
        self.interrupt = interrupt


class MockClaudeAgentOptions:
    """Mimics claude_agent_sdk.ClaudeAgentOptions — stores kwargs as attrs."""

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockClaudeSDKClient:
    """Mimics claude_agent_sdk.ClaudeSDKClient.

    Tracks connect/disconnect/query calls and yields scripted responses.
    """

    def __init__(
        self,
        options: Any = None,
        responses: list[MockResultMessage] | None = None,
    ):
        self.options = options
        self._responses = responses or [MockResultMessage()]
        self.queries: list[str] = []
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        """Async generator yielding scripted MockResultMessage list."""
        for msg in self._responses:
            yield msg
