"""Pydantic schemas for configuration validation.

Ensures configs are valid before runtime, provides self-documenting schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class BackendType(str, Enum):
    """Supported agent backend types."""
    CLAUDE = "claude"
    CURSOR = "cursor"
    GEMINI = "gemini"
    CODEX = "codex"


class ModelType(str, Enum):
    """Common LLM model names."""
    CLAUDE_OPUS = "opus"
    CLAUDE_SONNET = "sonnet"
    CLAUDE_HAIKU = "haiku"
    GEMINI_PRO = "gemini-pro"
    GEMINI_FLASH = "gemini-flash"


class AgentConfigSchema(BaseModel):
    """Schema for an individual agent in a team.
    
    Example:
        {
            "backend": "claude",
            "model": "opus",
            "description": "Smart implementer for complex tasks",
            "max_turns": 30,
            "timeout_s": 600,
            "system_prompt": "You are an expert developer..."
        }
    """
    
    backend: BackendType = Field(
        ...,
        description="Which backend runs this agent (claude, cursor, gemini, codex)"
    )
    model: str = Field(
        ...,
        description="Model name (opus, sonnet, haiku, gemini-pro, gemini-flash, etc.)"
    )
    description: str = Field(
        default="",
        description="What this agent does (used in orchestrator prompts)"
    )
    max_turns: int = Field(
        default=15,
        ge=1,
        le=200,
        description="Max number of turns this agent gets per task"
    )
    timeout_s: Optional[float] = Field(
        default=None,
        ge=10,
        description="Timeout in seconds (None = no limit)"
    )
    system_prompt: str = Field(
        default="",
        description="Custom system prompt override"
    )
    fallback_model: Optional[str] = Field(
        default=None,
        description="Fallback model if primary fails"
    )
    
    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Ensure backend is known."""
        if v not in [b.value for b in BackendType]:
            raise ValueError(f"Unknown backend: {v}. Must be one of: {[b.value for b in BackendType]}")
        return v
    
    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Basic model name validation."""
        if not v or not isinstance(v, str):
            raise ValueError("model must be a non-empty string")
        return v


class TeamConfigSchema(BaseModel):
    """Schema for a team configuration (team.json).
    
    Example:
        {
            "name": "saga-with-designer",
            "agents": {
                "worker_fast": {
                    "backend": "cursor",
                    "model": "gpt-4",
                    "description": "..."
                },
                "worker_smart": {...},
                "architect": {...},
                "tester": {...}
            }
        }
    """
    
    name: str = Field(
        ...,
        min_length=1,
        description="Team name for display"
    )
    agents: dict[str, AgentConfigSchema] = Field(
        ...,
        min_length=1,
        description="Map of agent names to their configs"
    )
    
    @field_validator("agents")
    @classmethod
    def validate_required_agents(cls, agents: dict) -> dict:
        """Ensure essential agents are present."""
        # These are the minimum required for an orchestrator to function
        # Note: could be made configurable based on orchestrator type
        # For now, just require at least one agent
        if not agents:
            raise ValueError("Team must have at least one agent")
        return agents
    
    def get_agent(self, name: str) -> AgentConfigSchema | None:
        """Get agent config by name."""
        return self.agents.get(name)
    
    def all_backends(self) -> set[str]:
        """Get all unique backends in this team."""
        return {agent.backend.value for agent in self.agents.values()}


class UserConfigSchema(BaseModel):
    """Schema for user-level settings (~/.kodo/config.json).
    
    Example:
        {
            "preferred_orchestrator": "api",
            "preferred_orchestrator_model": "gemini-flash",
            "api_key_provider": "env",
            "default_exchanges": 30,
            "default_cycles": 5
        }
    """
    
    preferred_orchestrator: Literal["api", "claude-code"] = Field(
        default="api",
        description="Default orchestrator to use"
    )
    preferred_orchestrator_model: str = Field(
        default="gemini-flash",
        description="Default orchestrator model"
    )
    default_mode: Literal["saga", "mission"] = Field(
        default="saga",
        description="Default run mode"
    )
    default_exchanges: int = Field(
        default=30,
        ge=5,
        le=500,
        description="Default max exchanges per cycle"
    )
    default_cycles: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Default max cycles"
    )


class GoalStageSchema(BaseModel):
    """Schema for a goal stage (from goal-plan.json).
    
    Stages break down a goal into sequential steps.
    """
    
    index: int = Field(..., ge=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    acceptance_criteria: str = Field(default="")
    browser_testing: bool = Field(default=False)
    parallel_group: int = Field(
        default=0,
        ge=0,
        description="If >0, this stage runs parallel with others in same group (git worktree isolation)"
    )


class GoalPlanSchema(BaseModel):
    """Schema for a goal plan (goal-plan.json).
    
    Produced by intake stage, consumed by orchestrator.
    """
    
    context: str = Field(
        ...,
        description="Shared context about the project (tech stack, conventions, etc.)"
    )
    stages: list[GoalStageSchema] = Field(
        ...,
        min_length=1,
        description="Ordered stages to complete the goal"
    )


# Validators for type checking config files at load time

def validate_team_config(data: dict) -> TeamConfigSchema:
    """Validate a team config dict, raising if invalid."""
    return TeamConfigSchema(**data)


def validate_user_config(data: dict) -> UserConfigSchema:
    """Validate user config dict."""
    return UserConfigSchema(**data)


def validate_goal_plan(data: dict) -> GoalPlanSchema:
    """Validate goal plan dict."""
    return GoalPlanSchema(**data)
