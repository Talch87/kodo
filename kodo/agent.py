"""Agent — a prompt + session, ready to run."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path

from kodo.sessions.base import QueryResult, RetryStrategy, Session, SessionCheckpoint
from kodo import log


@dataclass
class AgentResult:
    """Agent run result with context metadata."""

    query: QueryResult
    context_reset: bool = False  # was the session reset before this run?
    context_reset_reason: str = ""  # why it was reset
    session_tokens: int = 0  # cumulative session tokens after this run
    session_queries: int = 0  # cumulative session queries after this run

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
        description: str = "",
        *,
        max_turns: int = 15,
        timeout_s: float | None = None,
        checkpoint_enabled: bool = True,
        retry_strategy: RetryStrategy | None = None,
    ):
        self.session = session
        self.description = description  # kept for tool description extraction
        self.max_turns = max_turns
        self.timeout_s = timeout_s
        self.checkpoint_enabled = checkpoint_enabled
        self.retry_strategy = retry_strategy or RetryStrategy()
        self.last_checkpoint: SessionCheckpoint | None = None

    def run(
        self,
        goal: str,
        project_dir: Path,
        *,
        new_conversation: bool = False,
        agent_name: str = "",
    ) -> AgentResult:
        context_reset = False
        context_reset_reason = ""
        label = agent_name or "agent"

        log.emit(
            "agent_run_start",
            agent=label,
            new_conversation=new_conversation,
            goal=goal,
            session_tokens=self.session.stats.total_tokens,
            session_queries=self.session.stats.queries,
        )

        # Explicit reset requested by orchestrator
        if new_conversation:
            self.session.reset()
            context_reset = True
            context_reset_reason = "orchestrator requested new conversation"
            log.emit("agent_session_reset", agent=label, reason=context_reset_reason)

        log.emit("agent_query", agent=label, prompt=goal)

        def _do_query():
            """Wrapper that applies retry strategy to session.query."""
            return self.retry_strategy.execute(
                self.session.query,
                goal,
                project_dir,
                max_turns=self.max_turns,
            )

        if self.timeout_s is not None:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_do_query)
                try:
                    query_result = future.result(timeout=self.timeout_s)
                except FuturesTimeoutError:
                    log.emit("agent_timeout", agent=label, timeout_s=self.timeout_s)
                    # Kill the underlying session to stop burning tokens.
                    self.session.reset()
                    query_result = QueryResult(
                        text=f"Agent timed out after {self.timeout_s}s",
                        elapsed_s=self.timeout_s,
                        is_error=True,
                    )
        else:
            query_result = _do_query()

        bucket = self.session.cost_bucket
        log.emit(
            "agent_run_end",
            agent=label,
            elapsed_s=query_result.elapsed_s,
            is_error=query_result.is_error,
            turns=query_result.turns,
            input_tokens=query_result.input_tokens,
            output_tokens=query_result.output_tokens,
            cost_usd=query_result.cost_usd,
            cost_bucket=bucket,
            response_text=query_result.text,
            context_reset=context_reset,
            context_reset_reason=context_reset_reason,
            session_tokens=self.session.stats.total_tokens,
            session_queries=self.session.stats.queries,
        )

        log.get_run_stats().record_agent(
            agent=label,
            cost_usd=query_result.cost_usd or 0,
            input_tokens=query_result.input_tokens or 0,
            output_tokens=query_result.output_tokens or 0,
            elapsed_s=query_result.elapsed_s or 0,
            is_error=query_result.is_error,
            cost_bucket=bucket,
        )

        # Auto-checkpoint after each successful agent turn
        if self.checkpoint_enabled and not query_result.is_error:
            self._save_checkpoint(label, project_dir, query_result)

        return AgentResult(
            query=query_result,
            context_reset=context_reset,
            context_reset_reason=context_reset_reason,
            session_tokens=self.session.stats.total_tokens,
            session_queries=self.session.stats.queries,
        )

    def _save_checkpoint(
        self, agent_name: str, project_dir: Path, query_result: QueryResult
    ) -> None:
        """Persist a checkpoint after a successful agent turn."""
        run_id = log.get_run_id()
        if not run_id:
            return  # logging not initialised — skip checkpoint

        summary = (query_result.text or "")[:500]
        checkpoint = SessionCheckpoint(
            agent_name=agent_name,
            session_id=self.session.session_id,
            run_id=run_id,
            tokens_used=self.session.stats.total_tokens,
            queries_completed=self.session.stats.queries,
            cost_usd=self.session.stats.total_cost_usd,
            conversation_summary=summary,
        )
        try:
            checkpoint.save(project_dir)
            self.last_checkpoint = checkpoint
            log.emit(
                "checkpoint_saved",
                agent=agent_name,
                run_id=run_id,
                tokens=checkpoint.tokens_used,
                queries=checkpoint.queries_completed,
            )
        except OSError as exc:
            log.emit("checkpoint_save_error", agent=agent_name, error=str(exc))

    def close(self) -> None:
        """Clean up the underlying session if it supports it."""
        if hasattr(self.session, "close"):
            self.session.close()
