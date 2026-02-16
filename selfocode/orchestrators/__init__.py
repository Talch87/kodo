"""Orchestrator implementations for multi-agent coordination."""

from selfocode.orchestrators.base import CycleResult, Orchestrator, RunResult, TeamConfig
from selfocode.orchestrators.api import ApiOrchestrator
from selfocode.orchestrators.claude_code import ClaudeCodeOrchestrator

__all__ = [
    "CycleResult", "RunResult", "Orchestrator", "TeamConfig",
    "ApiOrchestrator", "ClaudeCodeOrchestrator",
]
