"""Cursor session using cursor-agent CLI subprocess."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from kodo import log
from kodo.sessions.base import QueryResult, SessionStats


class CursorSession:
    def __init__(
        self,
        model: str = "composer-1.5",
        system_prompt: str | None = None,
        resume_chat_id: str | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self._stats = SessionStats()
        self._chat_id: str | None = resume_chat_id
        self._system_prompt_sent = False

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def cost_bucket(self) -> str:
        return "cursor_subscription"

    @property
    def session_id(self) -> str | None:
        return self._chat_id

    def reset(self) -> None:
        log.emit(
            "session_reset",
            session="cursor",
            model=self.model,
            chat_id=self._chat_id,
            queries_before=self._stats.queries,
        )
        self._chat_id = None
        self._stats = SessionStats()
        self._system_prompt_sent = False

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        # Cursor has no native system prompt — prepend to first query per session
        if self.system_prompt and not self._system_prompt_sent:
            prompt = f"{self.system_prompt}\n\n{prompt}"
            self._system_prompt_sent = True

        cmd = [
            "cursor-agent",
            "-p",
            "-f",
            "--output-format",
            "stream-json",
            "--model",
            self.model,
            "--workspace",
            str(project_dir),
        ]

        if self._chat_id:
            cmd.extend(["--resume", self._chat_id])

        cmd.append(prompt)

        log.emit(
            "session_query_start",
            session="cursor",
            model=self.model,
            prompt=prompt,
            chat_id=self._chat_id,
            project_dir=str(project_dir),
        )

        t0 = time.monotonic()
        result_text = ""
        duration_ms = 0
        raw_messages: list[dict] = []

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Drain stderr in a background thread to avoid deadlock when the
        # OS pipe buffer fills up while we're reading stdout.
        stderr_chunks: list[str] = []

        def _drain_stderr():
            for line in proc.stderr:
                stderr_chunks.append(line)

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            raw_messages.append(msg)

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
        stderr_thread.join(timeout=5)
        elapsed = time.monotonic() - t0

        is_error = proc.returncode != 0
        stderr_text = "".join(stderr_chunks) if is_error else ""

        self._stats.queries += 1

        log.emit(
            "session_query_end",
            session="cursor",
            model=self.model,
            elapsed_s=elapsed,
            is_error=is_error,
            chat_id=self._chat_id,
            returncode=proc.returncode,
            response_text=result_text or stderr_text,
            raw_messages=raw_messages,
        )

        return QueryResult(
            text=result_text or stderr_text,
            elapsed_s=elapsed,
            is_error=is_error,
        )
