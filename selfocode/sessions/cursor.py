"""Cursor session using cursor-agent CLI subprocess."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from selfocode.sessions.base import QueryResult, SessionStats


class CursorSession:
    def __init__(self, model: str = "composer-1.5"):
        self.model = model
        self._stats = SessionStats()
        self._chat_id: str | None = None

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def reset(self) -> None:
        self._chat_id = None
        self._stats = SessionStats()

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        cmd = [
            "cursor-agent",
            "-p",
            "-f",
            "--output-format", "stream-json",
            "--model", self.model,
            "--workspace", str(project_dir),
        ]

        if self._chat_id:
            cmd.extend(["--resume", self._chat_id])

        cmd.append(prompt)

        t0 = time.monotonic()
        result_text = ""
        duration_ms = 0

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "result":
                result_text = msg.get("result", "")
                duration_ms = msg.get("duration_ms", 0)
            # Capture chat ID from any message that reports it
            if "chatId" in msg:
                self._chat_id = msg["chatId"]
            elif "chat_id" in msg:
                self._chat_id = msg["chat_id"]
            elif "session_id" in msg:
                self._chat_id = msg["session_id"]

        proc.wait()
        elapsed = time.monotonic() - t0

        is_error = proc.returncode != 0
        stderr_text = ""
        if is_error and proc.stderr:
            stderr_text = proc.stderr.read()

        self._stats.queries += 1
        return QueryResult(
            text=result_text or stderr_text,
            elapsed_s=elapsed,
            is_error=is_error,
        )
