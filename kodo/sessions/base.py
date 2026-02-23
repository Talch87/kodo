"""Session protocol and shared types."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class QueryResult:
    text: str
    elapsed_s: float
    turns: int | None = None
    cost_usd: float | None = None
    is_error: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_raw: dict | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.text = self.text.strip()


@dataclass
class SessionStats:
    """Cumulative stats for the current session."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    queries: int = 0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class Session(Protocol):
    @property
    def stats(self) -> SessionStats: ...

    @property
    def cost_bucket(self) -> str:
        """Billing bucket: 'api', 'claude_subscription', or 'cursor_subscription'."""
        ...

    @property
    def session_id(self) -> str | None:
        """Backend session ID for resume support. None if not yet established."""
        return None

    def query(
        self, prompt: str, project_dir: Path, *, max_turns: int
    ) -> QueryResult: ...

    def reset(self) -> None: ...


class SubprocessSession:
    """Base for subprocess-backed sessions (Cursor, Codex, Gemini CLI).

    Provides shared init, stats, system-prompt prepend, subprocess spawn/wait,
    and reset logic.  Subclasses keep their own ``query()`` and override
    ``reset()`` (calling ``super().reset()``) to clear session-specific state.
    """

    _session_label: str  # set by each subclass

    def __init__(self, model: str, system_prompt: str | None = None):
        self.model = model
        self.system_prompt = system_prompt
        self._stats = SessionStats()
        self._system_prompt_sent = False

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def _prepend_system_prompt(self, prompt: str) -> str:
        """Prepend system prompt to the first query, then set flag."""
        if self.system_prompt and not self._system_prompt_sent:
            prompt = f"{self.system_prompt}\n\n{prompt}"
            self._system_prompt_sent = True
        return prompt

    def _spawn(
        self, cmd: list[str], *, cwd: str | None = None
    ) -> tuple[subprocess.Popen, list[str], threading.Thread]:
        """Spawn subprocess with a stderr-drain thread.

        Returns ``(proc, stderr_chunks, thread)``.
        """
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        stderr_chunks: list[str] = []

        def _drain() -> None:
            for line in proc.stderr:
                stderr_chunks.append(line)

        thread = threading.Thread(target=_drain, daemon=True)
        thread.start()
        return proc, stderr_chunks, thread

    def _wait(
        self,
        proc: subprocess.Popen,
        stderr_chunks: list[str],
        thread: threading.Thread,
    ) -> str:
        """Wait for process and join drain thread.  Returns stderr text."""
        proc.wait()
        thread.join(timeout=5)
        return "".join(stderr_chunks)

    def reset(self) -> None:
        """Reset shared state.  Subclasses should log, clear their own state,
        then call ``super().reset()``."""
        self._stats = SessionStats()
        self._system_prompt_sent = False
