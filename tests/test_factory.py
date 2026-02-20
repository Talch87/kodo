"""Tests for kodo.factory module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from kodo.factory import get_mode, build_orchestrator


def test_get_mode_invalid():
    with pytest.raises(KeyError):
        get_mode("nonexistent_mode")


def test_build_orchestrator_api():
    with patch("kodo.orchestrators.api.Summarizer"):
        orch = build_orchestrator("api", model="opus")
    assert type(orch).__name__ == "ApiOrchestrator"
    assert orch.model == "claude-opus-4-6"
