"""Adversarial tests for factory — based on expected interface behavior."""

from __future__ import annotations

from kodo.factory import build_orchestrator


def test_full_model_id_passed_through():
    """If you pass a full model ID (not an alias), it should be used as-is."""
    orch = build_orchestrator("api", model="claude-opus-4-6")
    assert orch.model == "claude-opus-4-6"


def test_unknown_model_alias_used_as_is():
    """An unrecognized model string should be passed through, not rejected."""
    orch = build_orchestrator("api", model="some-future-model-2026")
    assert orch.model == "some-future-model-2026"


def test_build_orchestrator_with_custom_system_prompt():
    """Custom system_prompt should be forwarded to the orchestrator."""
    orch = build_orchestrator("api", system_prompt="You are a pirate.")
    assert orch._system_prompt == "You are a pirate."


def test_build_orchestrator_fallback_model_resolved():
    """Fallback model alias should be resolved to full ID."""
    orch = build_orchestrator("api", model="opus", fallback_model="sonnet")
    assert "sonnet" in orch._fallback_model  # Should be resolved to full ID
