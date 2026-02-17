"""Orchestrator implementations for multi-agent coordination."""

from selfocode.orchestrators.base import (
    CycleResult, Orchestrator, OrchestratorBase, RunResult, TeamConfig,
)

__all__ = [
    "CycleResult", "RunResult", "Orchestrator", "OrchestratorBase", "TeamConfig",
    "ApiOrchestrator", "ClaudeCodeOrchestrator",
]


def __getattr__(name: str):
    if name == "ApiOrchestrator":
        from selfocode.orchestrators.api import ApiOrchestrator
        return ApiOrchestrator
    if name == "ClaudeCodeOrchestrator":
        from selfocode.orchestrators.claude_code import ClaudeCodeOrchestrator
        return ClaudeCodeOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
