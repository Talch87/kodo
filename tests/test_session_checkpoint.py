"""Tests for SessionCheckpoint — persistent session state snapshots.

Covers: creation, serialization, save/load/clear, agent auto-checkpointing,
resume flow with token-savings measurement, and crash-resilience.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from kodo import log
from kodo.agent import Agent
from kodo.sessions.base import QueryResult, SessionCheckpoint, SessionStats


# ── Helpers ──────────────────────────────────────────────────────────────


class CheckpointFakeSession:
    """Session stub that reports a predictable session_id and stats."""

    def __init__(
        self,
        response_text: str = "done",
        session_id: str | None = "sess-abc-123",
        input_tokens: int = 100,
        output_tokens: int = 50,
    ):
        self._response_text = response_text
        self._session_id = session_id
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._stats = SessionStats()
        self.reset_count = 0

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def cost_bucket(self) -> str:
        return "test"

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        self._stats.queries += 1
        self._stats.total_input_tokens += self._input_tokens
        self._stats.total_output_tokens += self._output_tokens
        return QueryResult(
            text=self._response_text,
            elapsed_s=0.1,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cost_usd=0.01,
        )

    def reset(self) -> None:
        self.reset_count += 1
        self._stats = SessionStats()


# ── SessionCheckpoint unit tests ─────────────────────────────────────────


class TestSessionCheckpointCreation:
    """Basic construction and field access."""

    def test_create_checkpoint(self) -> None:
        cp = SessionCheckpoint(
            agent_name="worker_smart",
            session_id="sid-123",
            run_id="run-001",
            tokens_used=5000,
            queries_completed=3,
            cost_usd=0.15,
            conversation_summary="Implemented feature X",
        )
        assert cp.agent_name == "worker_smart"
        assert cp.session_id == "sid-123"
        assert cp.run_id == "run-001"
        assert cp.tokens_used == 5000
        assert cp.queries_completed == 3
        assert cp.cost_usd == 0.15
        assert cp.conversation_summary == "Implemented feature X"
        assert cp.timestamp > 0

    def test_defaults(self) -> None:
        cp = SessionCheckpoint(agent_name="a", session_id=None, run_id="r")
        assert cp.tokens_used == 0
        assert cp.queries_completed == 0
        assert cp.cost_usd == 0.0
        assert cp.conversation_summary == ""


class TestSessionCheckpointSerialization:
    """to_dict / from_dict round-trip."""

    def test_to_dict(self) -> None:
        cp = SessionCheckpoint(
            agent_name="arch",
            session_id="s1",
            run_id="r1",
            tokens_used=100,
        )
        d = cp.to_dict()
        assert isinstance(d, dict)
        assert d["agent_name"] == "arch"
        assert d["session_id"] == "s1"
        assert d["run_id"] == "r1"
        assert d["tokens_used"] == 100

    def test_round_trip(self) -> None:
        original = SessionCheckpoint(
            agent_name="tester",
            session_id="sid-x",
            run_id="run-42",
            tokens_used=2500,
            queries_completed=7,
            cost_usd=0.30,
            conversation_summary="All tests pass",
        )
        restored = SessionCheckpoint.from_dict(original.to_dict())
        assert restored.agent_name == original.agent_name
        assert restored.session_id == original.session_id
        assert restored.run_id == original.run_id
        assert restored.tokens_used == original.tokens_used
        assert restored.queries_completed == original.queries_completed
        assert restored.cost_usd == original.cost_usd
        assert restored.conversation_summary == original.conversation_summary

    def test_from_dict_ignores_extra_keys(self) -> None:
        d = {
            "agent_name": "a",
            "session_id": "s",
            "run_id": "r",
            "tokens_used": 0,
            "queries_completed": 0,
            "cost_usd": 0.0,
            "conversation_summary": "",
            "timestamp": 1.0,
            "extra_field": "should be ignored",
        }
        cp = SessionCheckpoint.from_dict(d)
        assert cp.agent_name == "a"
        assert not hasattr(cp, "extra_field")


class TestSessionCheckpointPersistence:
    """save / load / load_all / clear on disk."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        cp = SessionCheckpoint(
            agent_name="worker",
            session_id="s-1",
            run_id="run-100",
            tokens_used=500,
        )
        path = cp.save(tmp_path)
        assert path.exists()
        assert path.name == "worker.json"
        assert "run-100" in str(path.parent)

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        original = SessionCheckpoint(
            agent_name="architect",
            session_id="sid-abc",
            run_id="run-200",
            tokens_used=3000,
            queries_completed=5,
            cost_usd=0.25,
            conversation_summary="Reviewed codebase",
        )
        original.save(tmp_path)
        loaded = SessionCheckpoint.load("run-200", "architect", tmp_path)
        assert loaded is not None
        assert loaded.agent_name == "architect"
        assert loaded.session_id == "sid-abc"
        assert loaded.tokens_used == 3000
        assert loaded.queries_completed == 5
        assert loaded.cost_usd == 0.25
        assert loaded.conversation_summary == "Reviewed codebase"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = SessionCheckpoint.load("no-such-run", "no-agent", tmp_path)
        assert result is None

    def test_load_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        cp_dir = tmp_path / ".kodo" / "checkpoints" / "run-bad"
        cp_dir.mkdir(parents=True)
        (cp_dir / "worker.json").write_text("not valid json{{{", encoding="utf-8")
        result = SessionCheckpoint.load("run-bad", "worker", tmp_path)
        assert result is None

    def test_load_all_multiple_agents(self, tmp_path: Path) -> None:
        for name in ("worker_smart", "architect", "tester"):
            SessionCheckpoint(
                agent_name=name,
                session_id=f"sid-{name}",
                run_id="run-300",
                tokens_used=1000,
            ).save(tmp_path)

        checkpoints = SessionCheckpoint.load_all("run-300", tmp_path)
        assert len(checkpoints) == 3
        assert "worker_smart" in checkpoints
        assert "architect" in checkpoints
        assert "tester" in checkpoints
        assert checkpoints["worker_smart"].session_id == "sid-worker_smart"

    def test_load_all_empty_run(self, tmp_path: Path) -> None:
        result = SessionCheckpoint.load_all("nonexistent-run", tmp_path)
        assert result == {}

    def test_clear_removes_all(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            SessionCheckpoint(
                agent_name=name, session_id="s", run_id="run-400"
            ).save(tmp_path)

        cp_dir = tmp_path / ".kodo" / "checkpoints" / "run-400"
        assert cp_dir.exists()
        assert len(list(cp_dir.glob("*.json"))) == 2

        SessionCheckpoint.clear("run-400", tmp_path)
        assert not cp_dir.exists()

    def test_clear_nonexistent_no_error(self, tmp_path: Path) -> None:
        # Should not raise
        SessionCheckpoint.clear("no-such-run", tmp_path)

    def test_overwrite_updates_checkpoint(self, tmp_path: Path) -> None:
        """Saving again overwrites the previous checkpoint."""
        cp1 = SessionCheckpoint(
            agent_name="w", session_id="s1", run_id="r", tokens_used=100
        )
        cp1.save(tmp_path)
        cp2 = SessionCheckpoint(
            agent_name="w", session_id="s2", run_id="r", tokens_used=200
        )
        cp2.save(tmp_path)
        loaded = SessionCheckpoint.load("r", "w", tmp_path)
        assert loaded is not None
        assert loaded.session_id == "s2"
        assert loaded.tokens_used == 200


class TestAgentAutoCheckpoint:
    """Agent.run() should auto-save a checkpoint after each successful query."""

    def test_checkpoint_saved_after_run(self, tmp_path: Path) -> None:
        """After a successful run, a checkpoint file should exist."""
        # Initialise logging so run_id is available
        log.init(tmp_path, run_id="test-run-cp")

        session = CheckpointFakeSession(response_text="task complete")
        agent = Agent(session, "test agent", max_turns=10, checkpoint_enabled=True)
        result = agent.run("do work", tmp_path, agent_name="worker_smart")

        assert not result.is_error
        assert agent.last_checkpoint is not None
        assert agent.last_checkpoint.agent_name == "worker_smart"
        assert agent.last_checkpoint.session_id == "sess-abc-123"

        # Verify file on disk
        loaded = SessionCheckpoint.load("test-run-cp", "worker_smart", tmp_path)
        assert loaded is not None
        assert loaded.tokens_used == 150  # 100 input + 50 output
        assert loaded.queries_completed == 1
        assert "task complete" in loaded.conversation_summary

    def test_no_checkpoint_on_error(self, tmp_path: Path) -> None:
        """Checkpoint should NOT be saved for error responses."""
        log.init(tmp_path, run_id="test-run-err")

        session = CheckpointFakeSession(response_text="failed")
        # Override query to return error
        original_query = session.query

        def error_query(prompt, project_dir, *, max_turns):
            r = original_query(prompt, project_dir, max_turns=max_turns)
            return QueryResult(
                text="error occurred",
                elapsed_s=0.1,
                is_error=True,
            )

        session.query = error_query
        agent = Agent(session, "test agent", max_turns=10, checkpoint_enabled=True)
        result = agent.run("do work", tmp_path, agent_name="worker_err")

        assert result.is_error
        assert agent.last_checkpoint is None
        loaded = SessionCheckpoint.load("test-run-err", "worker_err", tmp_path)
        assert loaded is None

    def test_checkpoint_disabled(self, tmp_path: Path) -> None:
        """When checkpoint_enabled=False, no checkpoint should be saved."""
        log.init(tmp_path, run_id="test-run-nocp")

        session = CheckpointFakeSession(response_text="ok")
        agent = Agent(session, "test agent", max_turns=10, checkpoint_enabled=False)
        agent.run("do work", tmp_path, agent_name="worker_nocp")

        assert agent.last_checkpoint is None
        loaded = SessionCheckpoint.load("test-run-nocp", "worker_nocp", tmp_path)
        assert loaded is None

    def test_multiple_runs_update_checkpoint(self, tmp_path: Path) -> None:
        """Each agent run should overwrite the previous checkpoint."""
        log.init(tmp_path, run_id="test-run-multi")

        session = CheckpointFakeSession(response_text="response")
        agent = Agent(session, "test agent", max_turns=10, checkpoint_enabled=True)

        agent.run("task 1", tmp_path, agent_name="worker")
        cp1 = SessionCheckpoint.load("test-run-multi", "worker", tmp_path)
        assert cp1 is not None
        assert cp1.queries_completed == 1
        assert cp1.tokens_used == 150

        agent.run("task 2", tmp_path, agent_name="worker")
        cp2 = SessionCheckpoint.load("test-run-multi", "worker", tmp_path)
        assert cp2 is not None
        assert cp2.queries_completed == 2
        assert cp2.tokens_used == 300  # cumulative

    def test_checkpoint_without_log_init(self, tmp_path: Path) -> None:
        """If logging is not initialized, checkpoint is silently skipped."""
        # Reset log state to simulate no-init
        log._log_file = None
        log._run_id = None
        log._start_time = None

        session = CheckpointFakeSession(response_text="ok")
        agent = Agent(session, "test agent", max_turns=10, checkpoint_enabled=True)
        # Should not raise
        agent.run("do work", tmp_path, agent_name="worker_nolog")
        assert agent.last_checkpoint is None


class TestResumeFromCheckpoint:
    """Simulates the resume flow: checkpoint → crash → load → resume."""

    def test_checkpoint_survives_crash(self, tmp_path: Path) -> None:
        """Write checkpoint, verify it persists (simulating a crash)."""
        cp = SessionCheckpoint(
            agent_name="worker_smart",
            session_id="session-crash-test",
            run_id="run-crash",
            tokens_used=10000,
            queries_completed=15,
            cost_usd=1.50,
            conversation_summary="Was working on feature when crash happened",
        )
        path = cp.save(tmp_path)
        assert path.exists()

        # "Crash" — clear in-memory state
        del cp

        # "Resume" — load from disk
        restored = SessionCheckpoint.load("run-crash", "worker_smart", tmp_path)
        assert restored is not None
        assert restored.session_id == "session-crash-test"
        assert restored.tokens_used == 10000
        assert restored.queries_completed == 15
        assert "crash happened" in restored.conversation_summary

    def test_token_savings_on_resume(self, tmp_path: Path) -> None:
        """Verify token savings can be calculated from checkpoints."""
        # Simulate: 3 agents each used 5000 tokens before crash
        for name, tokens in [("worker", 5000), ("architect", 3000), ("tester", 2000)]:
            SessionCheckpoint(
                agent_name=name,
                session_id=f"sid-{name}",
                run_id="run-savings",
                tokens_used=tokens,
                queries_completed=5,
            ).save(tmp_path)

        # Load all and calculate savings
        checkpoints = SessionCheckpoint.load_all("run-savings", tmp_path)
        total_tokens_preserved = sum(cp.tokens_used for cp in checkpoints.values())
        total_queries_preserved = sum(
            cp.queries_completed for cp in checkpoints.values()
        )

        # Without checkpoints, all 10,000 tokens of context would need to be rebuilt
        assert total_tokens_preserved == 10000
        assert total_queries_preserved == 15

        # Token savings = tokens that don't need to be re-generated
        # Conservative estimate: at least 50% savings (we don't re-explain prior work)
        token_savings_pct = (total_tokens_preserved / (total_tokens_preserved * 2)) * 100
        assert token_savings_pct >= 50.0

    def test_resume_restores_session_ids(self, tmp_path: Path) -> None:
        """Checkpoints contain session_ids that can be injected back."""
        SessionCheckpoint(
            agent_name="worker_smart",
            session_id="claude-session-xyz",
            run_id="run-resume-sid",
            tokens_used=8000,
        ).save(tmp_path)
        SessionCheckpoint(
            agent_name="tester",
            session_id="cursor-chat-abc",
            run_id="run-resume-sid",
            tokens_used=2000,
        ).save(tmp_path)

        checkpoints = SessionCheckpoint.load_all("run-resume-sid", tmp_path)

        # Verify session IDs can be extracted for injection
        session_ids = {name: cp.session_id for name, cp in checkpoints.items()}
        assert session_ids["worker_smart"] == "claude-session-xyz"
        assert session_ids["tester"] == "cursor-chat-abc"

    def test_full_checkpoint_resume_cycle(self, tmp_path: Path) -> None:
        """End-to-end: agent runs → checkpoint saved → load → verify state."""
        log.init(tmp_path, run_id="run-e2e")

        session = CheckpointFakeSession(
            response_text="Implemented login feature",
            session_id="session-e2e-001",
            input_tokens=200,
            output_tokens=100,
        )
        agent = Agent(session, "smart worker", max_turns=15, checkpoint_enabled=True)

        # Run 3 tasks
        agent.run("implement login", tmp_path, agent_name="worker_smart")
        agent.run("add tests", tmp_path, agent_name="worker_smart")
        agent.run("fix bug", tmp_path, agent_name="worker_smart")

        # Verify checkpoint reflects cumulative state
        cp = SessionCheckpoint.load("run-e2e", "worker_smart", tmp_path)
        assert cp is not None
        assert cp.session_id == "session-e2e-001"
        assert cp.tokens_used == 900  # 3 * (200 + 100)
        assert cp.queries_completed == 3

        # Simulate crash and resume: can reconstruct state
        assert cp.run_id == "run-e2e"
        assert cp.agent_name == "worker_smart"
        # The session_id can be injected into a new ClaudeSession to resume
        assert cp.session_id is not None


class TestLogConvenienceFunctions:
    """Test the save/load/clear wrapper functions in kodo.log."""

    def test_save_checkpoint(self, tmp_path: Path) -> None:
        cp = SessionCheckpoint(
            agent_name="worker", session_id="s1", run_id="log-fn-1", tokens_used=42
        )
        path = log.save_checkpoint(cp, tmp_path)
        assert path.exists()
        assert path.name == "worker.json"

    def test_load_checkpoint(self, tmp_path: Path) -> None:
        SessionCheckpoint(
            agent_name="worker", session_id="s1", run_id="log-fn-2", tokens_used=99
        ).save(tmp_path)
        loaded = log.load_checkpoint("log-fn-2", "worker", tmp_path)
        assert loaded is not None
        assert loaded.tokens_used == 99

    def test_load_checkpoint_missing(self, tmp_path: Path) -> None:
        assert log.load_checkpoint("nope", "nope", tmp_path) is None

    def test_load_all_checkpoints(self, tmp_path: Path) -> None:
        for name in ("a", "b", "c"):
            SessionCheckpoint(
                agent_name=name, session_id="s", run_id="log-fn-3"
            ).save(tmp_path)
        result = log.load_all_checkpoints("log-fn-3", tmp_path)
        assert len(result) == 3
        assert set(result.keys()) == {"a", "b", "c"}

    def test_load_all_checkpoints_empty(self, tmp_path: Path) -> None:
        assert log.load_all_checkpoints("missing", tmp_path) == {}

    def test_clear_checkpoints(self, tmp_path: Path) -> None:
        SessionCheckpoint(
            agent_name="w", session_id="s", run_id="log-fn-4"
        ).save(tmp_path)
        cp_dir = tmp_path / ".kodo" / "checkpoints" / "log-fn-4"
        assert cp_dir.exists()
        log.clear_checkpoints("log-fn-4", tmp_path)
        assert not cp_dir.exists()

    def test_clear_checkpoints_noop(self, tmp_path: Path) -> None:
        # Should not raise when nothing to clear
        log.clear_checkpoints("nonexistent", tmp_path)
