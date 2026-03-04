"""Session protocol and shared types."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
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


@dataclass
class SessionCheckpoint:
    """Persistent snapshot of an agent's session state.

    Saved after each successful agent turn so that a crashed run can
    resume without re-building context from scratch.
    """

    agent_name: str
    session_id: str | None
    run_id: str
    timestamp: float = field(default_factory=time.time)
    tokens_used: int = 0
    queries_completed: int = 0
    cost_usd: float = 0.0
    conversation_summary: str = ""

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionCheckpoint":
        """Deserialize from a dict (e.g. loaded from JSON)."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, project_dir: Path) -> Path:
        """Persist this checkpoint to disk.

        Writes to ``<project_dir>/.kodo/checkpoints/<run_id>/<agent_name>.json``.
        Returns the path of the written file.
        """
        cp_dir = project_dir / ".kodo" / "checkpoints" / self.run_id
        cp_dir.mkdir(parents=True, exist_ok=True)
        path = cp_dir / f"{self.agent_name}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(
        cls, run_id: str, agent_name: str, project_dir: Path
    ) -> "SessionCheckpoint | None":
        """Load a previously saved checkpoint, or *None* if not found."""
        path = project_dir / ".kodo" / "checkpoints" / run_id / f"{agent_name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    @classmethod
    def load_all(
        cls, run_id: str, project_dir: Path
    ) -> dict[str, "SessionCheckpoint"]:
        """Load every agent checkpoint for *run_id*.

        Returns ``{agent_name: checkpoint}`` — empty dict when no checkpoints exist.
        """
        cp_dir = project_dir / ".kodo" / "checkpoints" / run_id
        if not cp_dir.exists():
            return {}
        result: dict[str, SessionCheckpoint] = {}
        for path in cp_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cp = cls.from_dict(data)
                result[cp.agent_name] = cp
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return result

    @classmethod
    def clear(cls, run_id: str, project_dir: Path) -> None:
        """Remove all checkpoints for *run_id*."""
        import shutil

        cp_dir = project_dir / ".kodo" / "checkpoints" / run_id
        if cp_dir.exists():
            shutil.rmtree(cp_dir)


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


<<<<<<< HEAD
# ---------------------------------------------------------------------------
# Retry strategy for transient failures (429 rate limits, 529 overloads)
# ---------------------------------------------------------------------------
=======
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
>>>>>>> a7b8d01 (PR #3: Add session retry integration with exponential backoff)


@dataclass
class RetryStrategy:
    """Exponential backoff configuration for transient API failures.

    When a session query raises a retryable error (HTTP 429, 529, or
    transient network issues), the strategy will retry up to
    ``max_retries`` times with exponential backoff starting at
    ``initial_delay_s`` and capped at ``max_delay_s``.

    Usage::

        strategy = RetryStrategy()
        result = strategy.execute(session.query, prompt, project_dir, max_turns=10)
    """

    max_retries: int = 5
    initial_delay_s: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_s: float = 32.0
    retryable_substrings: tuple[str, ...] = (
        "429",
        "rate limit",
        "rate_limit",
        "too many requests",
        "overloaded",
        "529",
        "capacity",
    )

    def is_retryable(self, error: Exception) -> bool:
        """Return True if the error looks like a transient rate-limit."""
        error_str = str(error).lower()

        # Check for known retryable status codes in the error
        for substr in self.retryable_substrings:
            if substr in error_str:
                return True

        # Check for status_code attribute (e.g. ModelHTTPError)
        status = getattr(error, "status_code", None)
        if status in (429, 529, 503):
            return True

        return False

    def compute_delay(self, attempt: int) -> float:
        """Compute backoff delay for the given attempt (0-indexed)."""
        delay = self.initial_delay_s * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_s)

    def execute(
        self,
        fn,
        *args,
        **kwargs,
    ) -> "QueryResult":
        """Call *fn* with retries on transient errors.

<<<<<<< HEAD
        Parameters
        ----------
        fn : callable
            Typically ``session.query``.
        *args, **kwargs :
            Forwarded to *fn*.

        Returns
        -------
        QueryResult
            The result of the first successful call.

        Raises
        ------
        Exception
            The last error if all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not self.is_retryable(exc) or attempt >= self.max_retries:
                    raise
                last_error = exc
                delay = self.compute_delay(attempt)
                time.sleep(delay)

        # Should never reach here, but satisfy type checker
        assert last_error is not None
        raise last_error
=======
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
>>>>>>> a7b8d01 (PR #3: Add session retry integration with exponential backoff)
