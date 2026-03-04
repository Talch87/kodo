"""Tests for configuration schema validation."""

import pytest
from pydantic import ValidationError

from kodo.schemas import (
    AgentConfigSchema,
    TeamConfigSchema,
    UserConfigSchema,
    GoalStageSchema,
    GoalPlanSchema,
    BackendType,
    validate_team_config,
    validate_user_config,
    validate_goal_plan,
)


class TestAgentConfigSchema:
    """Test individual agent configuration validation."""

    def test_valid_agent_config(self):
        """Valid agent config passes validation."""
        config = AgentConfigSchema(
            backend=BackendType.CLAUDE,
            model="opus",
            description="Smart worker",
            max_turns=30,
        )
        
        assert config.backend == BackendType.CLAUDE
        assert config.model == "opus"
        assert config.max_turns == 30

    def test_minimal_agent_config(self):
        """Minimal required fields."""
        config = AgentConfigSchema(
            backend=BackendType.CLAUDE,
            model="sonnet",
        )
        
        assert config.backend == BackendType.CLAUDE
        assert config.description == ""
        assert config.max_turns == 15  # default

    def test_invalid_backend(self):
        """Invalid backend should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigSchema(
                backend="invalid",  # type: ignore
                model="opus",
            )
        assert "Input should be 'claude', 'cursor', 'gemini' or 'codex'" in str(exc_info.value)

    def test_invalid_model_empty_string(self):
        """Empty model string should fail."""
        with pytest.raises(ValidationError):
            AgentConfigSchema(
                backend=BackendType.CLAUDE,
                model="",
            )

    def test_max_turns_constraints(self):
        """max_turns must be between 1 and 200."""
        # Valid bounds
        config = AgentConfigSchema(backend=BackendType.CLAUDE, model="opus", max_turns=1)
        assert config.max_turns == 1
        
        config = AgentConfigSchema(backend=BackendType.CLAUDE, model="opus", max_turns=200)
        assert config.max_turns == 200
        
        # Invalid: too low
        with pytest.raises(ValidationError):
            AgentConfigSchema(backend=BackendType.CLAUDE, model="opus", max_turns=0)
        
        # Invalid: too high
        with pytest.raises(ValidationError):
            AgentConfigSchema(backend=BackendType.CLAUDE, model="opus", max_turns=201)

    def test_timeout_constraints(self):
        """timeout_s must be >= 10 if set."""
        config = AgentConfigSchema(
            backend=BackendType.CLAUDE,
            model="opus",
            timeout_s=60,
        )
        assert config.timeout_s == 60
        
        # Invalid: too low
        with pytest.raises(ValidationError):
            AgentConfigSchema(
                backend=BackendType.CLAUDE,
                model="opus",
                timeout_s=5,
            )


class TestTeamConfigSchema:
    """Test team configuration validation."""

    def test_valid_team_config(self):
        """Valid team config with multiple agents."""
        config = TeamConfigSchema(
            name="test-team",
            agents={
                "worker": AgentConfigSchema(
                    backend=BackendType.CLAUDE,
                    model="opus",
                ),
                "tester": AgentConfigSchema(
                    backend=BackendType.CURSOR,
                    model="gpt-4",
                ),
            },
        )
        
        assert config.name == "test-team"
        assert len(config.agents) == 2
        assert config.get_agent("worker") is not None
        assert config.get_agent("nonexistent") is None

    def test_all_backends(self):
        """Identify all backends in team."""
        config = TeamConfigSchema(
            name="multi-backend",
            agents={
                "worker": AgentConfigSchema(
                    backend=BackendType.CLAUDE,
                    model="opus",
                ),
                "worker2": AgentConfigSchema(
                    backend=BackendType.CURSOR,
                    model="gpt-4",
                ),
                "worker3": AgentConfigSchema(
                    backend=BackendType.CLAUDE,
                    model="sonnet",
                ),
            },
        )
        
        backends = config.all_backends()
        assert backends == {"claude", "cursor"}

    def test_team_requires_at_least_one_agent(self):
        """Team must have at least one agent."""
        with pytest.raises(ValidationError) as exc_info:
            TeamConfigSchema(
                name="empty-team",
                agents={},
            )
        assert "Team must have at least one agent" in str(exc_info.value)

    def test_team_requires_name(self):
        """Team must have a non-empty name."""
        with pytest.raises(ValidationError):
            TeamConfigSchema(
                name="",
                agents={
                    "worker": AgentConfigSchema(
                        backend=BackendType.CLAUDE,
                        model="opus",
                    ),
                },
            )


class TestUserConfigSchema:
    """Test user configuration validation."""

    def test_valid_user_config(self):
        """Valid user config."""
        config = UserConfigSchema(
            preferred_orchestrator="api",
            preferred_orchestrator_model="gemini-flash",
            default_exchanges=50,
            default_cycles=3,
        )
        
        assert config.preferred_orchestrator == "api"
        assert config.default_exchanges == 50

    def test_user_config_defaults(self):
        """User config has sensible defaults."""
        config = UserConfigSchema()
        
        assert config.preferred_orchestrator == "api"
        assert config.preferred_orchestrator_model == "gemini-flash"
        assert config.default_mode == "saga"
        assert config.default_exchanges == 30
        assert config.default_cycles == 5

    def test_invalid_orchestrator(self):
        """Invalid orchestrator should fail."""
        with pytest.raises(ValidationError):
            UserConfigSchema(preferred_orchestrator="invalid")  # type: ignore

    def test_exchanges_constraints(self):
        """default_exchanges must be 5-500."""
        config = UserConfigSchema(default_exchanges=5)
        assert config.default_exchanges == 5
        
        config = UserConfigSchema(default_exchanges=500)
        assert config.default_exchanges == 500
        
        with pytest.raises(ValidationError):
            UserConfigSchema(default_exchanges=4)
        
        with pytest.raises(ValidationError):
            UserConfigSchema(default_exchanges=501)

    def test_cycles_constraints(self):
        """default_cycles must be 1-100."""
        config = UserConfigSchema(default_cycles=1)
        assert config.default_cycles == 1
        
        config = UserConfigSchema(default_cycles=100)
        assert config.default_cycles == 100
        
        with pytest.raises(ValidationError):
            UserConfigSchema(default_cycles=0)
        
        with pytest.raises(ValidationError):
            UserConfigSchema(default_cycles=101)


class TestGoalPlanSchema:
    """Test goal plan validation."""

    def test_valid_goal_plan(self):
        """Valid goal plan with multiple stages."""
        plan = GoalPlanSchema(
            context="Python 3.10+ project using FastAPI",
            stages=[
                GoalStageSchema(
                    index=1,
                    name="Setup",
                    description="Initialize project",
                    acceptance_criteria="README exists",
                ),
                GoalStageSchema(
                    index=2,
                    name="Implement",
                    description="Build API",
                ),
            ],
        )
        
        assert plan.context == "Python 3.10+ project using FastAPI"
        assert len(plan.stages) == 2

    def test_plan_requires_stages(self):
        """Goal plan must have at least one stage."""
        with pytest.raises(ValidationError) as exc_info:
            GoalPlanSchema(
                context="Test",
                stages=[],
            )
        assert "at least 1" in str(exc_info.value).lower()

    def test_stage_index_required(self):
        """Stage index must be >= 1."""
        with pytest.raises(ValidationError):
            GoalStageSchema(
                index=0,
                name="Test",
                description="Test stage",
            )

    def test_parallel_group(self):
        """Parallel group field for worktree isolation."""
        stage = GoalStageSchema(
            index=1,
            name="Test",
            description="Description",
            parallel_group=2,
        )
        
        assert stage.parallel_group == 2

    def test_browser_testing_flag(self):
        """Browser testing flag can be set."""
        stage = GoalStageSchema(
            index=1,
            name="E2E Tests",
            description="Run browser tests",
            browser_testing=True,
        )
        
        assert stage.browser_testing is True


class TestValidationFunctions:
    """Test high-level validation functions."""

    def test_validate_team_config(self):
        """validate_team_config parses and validates dict."""
        data = {
            "name": "test",
            "agents": {
                "worker": {
                    "backend": "claude",
                    "model": "opus",
                },
            },
        }
        
        config = validate_team_config(data)
        assert isinstance(config, TeamConfigSchema)
        assert config.name == "test"

    def test_validate_team_config_invalid(self):
        """validate_team_config raises on invalid data."""
        data = {
            "name": "",  # Invalid: empty name
            "agents": {},
        }
        
        with pytest.raises(ValidationError):
            validate_team_config(data)

    def test_validate_user_config(self):
        """validate_user_config parses and validates dict."""
        data = {
            "preferred_orchestrator": "api",
            "default_exchanges": 100,
        }
        
        config = validate_user_config(data)
        assert isinstance(config, UserConfigSchema)
        assert config.default_exchanges == 100

    def test_validate_goal_plan(self):
        """validate_goal_plan parses and validates dict."""
        data = {
            "context": "Test project",
            "stages": [
                {
                    "index": 1,
                    "name": "Setup",
                    "description": "Setup project",
                },
            ],
        }
        
        plan = validate_goal_plan(data)
        assert isinstance(plan, GoalPlanSchema)
        assert len(plan.stages) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
