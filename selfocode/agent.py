"""Agent — a prompt + session, ready to run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from selfocode.sessions.base import QueryResult, Session


@dataclass
class AgentResult:
    """Agent run result with context metadata."""
    query: QueryResult
    context_reset: bool = False          # was the session reset before this run?
    context_reset_reason: str = ""       # why it was reset
    session_tokens: int = 0              # cumulative session tokens after this run
    session_queries: int = 0             # cumulative session queries after this run

    @property
    def text(self) -> str:
        return self.query.text

    @property
    def is_error(self) -> bool:
        return self.query.is_error

    @property
    def elapsed_s(self) -> float:
        return self.query.elapsed_s

    def format_report(self) -> str:
        """Format the result with context metadata for the orchestrator."""
        parts = []

        if self.context_reset:
            parts.append(f"[Context was reset: {self.context_reset_reason}]")

        parts.append(self.query.text or "(no output)")

        parts.append(
            f"\n---\n"
            f"[Context: {self.session_tokens:,} tokens used"
            f" | {self.session_queries} queries in session]"
        )

        return "\n".join(parts)


class Agent:
    def __init__(
        self,
        session: Session,
        prompt: str,
        *,
        max_turns: int = 15,
        max_context_tokens: int | None = None,
    ):
        self.session = session
        self.prompt = prompt
        self.max_turns = max_turns
        self.max_context_tokens = max_context_tokens

    def run(
        self,
        goal: str,
        project_dir: Path,
        *,
        new_conversation: bool = False,
    ) -> AgentResult:
        context_reset = False
        context_reset_reason = ""

        # Explicit reset requested by orchestrator
        if new_conversation:
            self.session.reset()
            context_reset = True
            context_reset_reason = "orchestrator requested new conversation"

        # Auto-reset if context exceeds limit
        elif self.max_context_tokens and self.session.stats.total_tokens >= self.max_context_tokens:
            self.session.reset()
            context_reset = True
            context_reset_reason = f"auto-reset at {self.session.stats.total_tokens:,} tokens (limit: {self.max_context_tokens:,})"

        full_prompt = f"{self.prompt}\n\n# Project Goal\n\n{goal}"
        query_result = self.session.query(full_prompt, project_dir, max_turns=self.max_turns)

        return AgentResult(
            query=query_result,
            context_reset=context_reset,
            context_reset_reason=context_reset_reason,
            session_tokens=self.session.stats.total_tokens,
            session_queries=self.session.stats.queries,
        )
