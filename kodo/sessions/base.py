"""Session protocol and shared types."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from kodo.errors import AgentError


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
    error: AgentError | None = field(default=None, repr=False)

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


class RetryableSession(Protocol):
    """Session that supports automatic retry with exponential backoff."""
    
    def query_with_retry(
        self,
        prompt: str,
        project_dir: Path,
        *,
        max_turns: int,
        max_retries: int = 3,
        initial_delay_s: float = 1.0,
    ) -> QueryResult:
        """Execute query with automatic retry on retriable errors.
        
        Uses exponential backoff with jitter for transient failures.
        """
        ...


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


class SessionRetryMixin:
    """Mixin to add automatic retry logic with exponential backoff to any session.
    
    Example usage:
        class MySession(SubprocessSession, SessionRetryMixin):
            def query(self, ...): ...
        
        session = MySession(model="gpt-4")
        result = session.query_with_retry(prompt, project_dir, max_turns=30)
    """
    
    def query_with_retry(
        self,
        prompt: str,
        project_dir: Path,
        *,
        max_turns: int,
        max_retries: int = 3,
        initial_delay_s: float = 1.0,
        backoff_multiplier: float = 2.0,
    ) -> QueryResult:
        """Execute query with automatic retry on retriable errors.
        
        Args:
            prompt: The query prompt
            project_dir: Project directory for context
            max_turns: Max turns for the query
            max_retries: Maximum retry attempts (default: 3)
            initial_delay_s: Initial backoff delay in seconds (default: 1.0)
            backoff_multiplier: Exponential backoff multiplier (default: 2.0)
        
        Returns:
            QueryResult with error field populated if error occurred
        
        Retries automatically on:
            - Timeout errors
            - Rate limit (429) errors
            - Temporary API failures
            - Network errors
            - Context overflow errors
        
        Does not retry on:
            - Authentication failures
            - Invalid input
            - Resource not found
            - Unsupported operations
        """
        from kodo.errors import AgentError, ErrorContext
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                result = self.query(prompt, project_dir, max_turns=max_turns)  # type: ignore
                return result
            
            except Exception as e:
                # Classify the error
                error = AgentError.from_exception(
                    e,
                    context=ErrorContext(
                        task_summary=prompt[:100],
                        step_number=attempt,
                        session_tokens_used=self.stats.total_tokens,  # type: ignore
                        session_queries_count=self.stats.queries,  # type: ignore
                    ),
                )
                last_error = error
                
                # Check if we should retry
                if attempt >= max_retries or not error.retriable:
                    # Return error result
                    return QueryResult(
                        text=str(e),
                        elapsed_s=0.0,
                        is_error=True,
                        turns=0,
                        error=error,
                    )
                
                # Calculate backoff delay
                delay = initial_delay_s * (backoff_multiplier ** attempt)
                
                # Log retry attempt
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Query failed ({error.error_type.value}), retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                
                # Sleep before retry
                time.sleep(delay)
        
        # Shouldn't reach here, but just in case
        assert last_error is not None
        return QueryResult(
            text=f"Failed after {max_retries} retries: {last_error.message}",
            elapsed_s=0.0,
            is_error=True,
            turns=0,
            error=last_error,
        )
