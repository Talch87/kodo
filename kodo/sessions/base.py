"""Session protocol and shared types."""

from __future__ import annotations

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
