"""Mock replacement for subprocess.Popen used by CursorSession."""

from __future__ import annotations

import io
import json
from typing import Any


class MockCursorProcess:
    """Mimics subprocess.Popen for cursor-agent.

    Produces stream-json lines on stdout including a result message
    with configurable result_text, chat_id, and returncode.
    """

    def __init__(
        self,
        cmd: list[str],
        *,
        result_text: str = "Task completed.",
        chat_id: str = "chat-abc-123",
        returncode: int = 0,
        extra_messages: list[dict[str, Any]] | None = None,
        stderr_text: str = "",
        **kwargs: Any,
    ):
        self.cmd = cmd
        self.returncode = returncode
        self._build_stdout(result_text, chat_id, extra_messages or [])
        self.stderr = io.StringIO(stderr_text)
        self.pid = 12345

    def _build_stdout(
        self,
        result_text: str,
        chat_id: str,
        extra_messages: list[dict[str, Any]],
    ) -> None:
        lines: list[str] = []
        for msg in extra_messages:
            lines.append(json.dumps(msg))
        result_msg = {
            "type": "result",
            "result": result_text,
            "chatId": chat_id,
            "duration_ms": 1234,
        }
        lines.append(json.dumps(result_msg))
        self.stdout = io.StringIO("\n".join(lines) + "\n")

    def wait(self) -> int:
        return self.returncode
