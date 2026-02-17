"""Shared fixtures for selfocode tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from selfocode.agent import Agent
from selfocode.sessions.base import QueryResult, SessionStats


class FakeSession:
    """Minimal Session implementation for testing."""

    def __init__(self, response_text: str = "done", is_error: bool = False):
        self._response_text = response_text
        self._is_error = is_error
        self._stats = SessionStats()
        self.reset_count = 0

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def query(self, prompt: str, project_dir: Path, *, max_turns: int) -> QueryResult:
        self._stats.queries += 1
        return QueryResult(
            text=self._response_text,
            elapsed_s=0.1,
            is_error=self._is_error,
        )

    def reset(self) -> None:
        self.reset_count += 1
        self._stats = SessionStats()


def make_agent(
    response_text: str = "done",
    prompt: str = "Test agent.",
    is_error: bool = False,
    max_turns: int = 10,
) -> Agent:
    """Create an Agent backed by a FakeSession."""
    session = FakeSession(response_text=response_text, is_error=is_error)
    return Agent(session, prompt, max_turns=max_turns)  # positional → description


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Return a temporary project directory."""
    return tmp_path
