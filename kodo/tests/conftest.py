"""Pytest configuration and fixtures."""

import pytest
import asyncio
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, AsyncMock

# Try to import pytest_asyncio, fall back to anyio
try:
    import pytest_asyncio
except ImportError:
    # Use anyio's async support
    pass


@pytest.fixture
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def pytest_configure(config):
    """Configure pytest for async testing."""
    if not any(p.startswith("pytest-asyncio") or p.startswith("anyio") for p in dir()):
        # If pytest-asyncio not available, use anyio
        pytest_plugins = ['anyio']


@pytest.fixture
def mock_agent() -> Mock:
    """Create mock agent for testing."""
    agent = Mock()
    agent.id = "test-agent-1"
    agent.name = "Test Agent"
    agent.status = "idle"
    agent.capabilities = ["process", "learn", "communicate"]
    return agent


@pytest.fixture
def mock_config() -> dict:
    """Create mock configuration."""
    return {
        "orchestrator": {
            "max_agents": 100,
            "timeout_seconds": 30,
            "retry_attempts": 3,
        },
        "logging": {
            "level": "INFO",
            "format": "json",
        },
        "performance": {
            "track_metrics": True,
            "cost_tracking_enabled": True,
        },
    }


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "tests").mkdir()
    return project_dir
