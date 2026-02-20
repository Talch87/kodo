"""Mock replacement for subprocess.Popen used by CodexSession."""

from __future__ import annotations

import io
import json
from typing import Any


class MockCodexProcess:
    """Mimics subprocess.Popen for codex exec.

    Produces JSONL events on stdout matching the Codex CLI --json format:
    thread.started, item.completed (assistant message), turn.completed (usage).
    """

    def __init__(
        self,
        cmd: list[str],
        *,
        result_text: str = "Task completed.",
        session_id: str = "thread-abc-123",
        returncode: int = 0,
        input_tokens: int = 100,
        output_tokens: int = 50,
        extra_messages: list[dict[str, Any]] | None = None,
        stderr_text: str = "",
        **kwargs: Any,
    ):
        self.cmd = cmd
        self.returncode = returncode
        self._build_stdout(
            result_text,
            session_id,
            input_tokens,
            output_tokens,
            extra_messages or [],
        )
        self.stderr = io.StringIO(stderr_text)
        self.pid = 12345

    def _build_stdout(
        self,
        result_text: str,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        extra_messages: list[dict[str, Any]],
    ) -> None:
        lines: list[str] = []

        # thread.started — provides session ID
        lines.append(
            json.dumps(
                {
                    "type": "thread.started",
                    "thread_id": session_id,
                }
            )
        )

        # Extra messages (e.g. tool calls, intermediate items)
        for msg in extra_messages:
            lines.append(json.dumps(msg))

        # item.completed — assistant response
        lines.append(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": result_text}],
                    },
                }
            )
        )

        # turn.completed — usage stats
        lines.append(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                }
            )
        )

        self.stdout = io.StringIO("\n".join(lines) + "\n")

    def wait(self) -> int:
        return self.returncode
