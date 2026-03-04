"""Team JSON configuration — load user-defined team compositions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from kodo import make_session
from kodo.agent import Agent
from kodo.factory import available_backends
from kodo.orchestrators.base import TeamConfig
from kodo.schemas import TeamConfigSchema, validate_team_config

logger = logging.getLogger(__name__)

# Backend name → key in available_backends()
_BACKEND_MAP = {
    "claude": "claude",
    "cursor": "cursor",
    "codex": "codex",
    "gemini-cli": "gemini-cli",
}

# Defaults for optional agent fields
_AGENT_DEFAULTS = {
    "max_turns": 15,
    "timeout_s": None,
    "chrome": False,
    "description": "",
    "system_prompt": None,
    "fallback_model": None,
}


def load_team_config(name: str, project_dir: Path) -> dict | None:
    """Find and load a team JSON config by mode name.

    Priority:
    1. {project_dir}/.kodo/team.json — project-level override
    2. ~/.kodo/teams/{name}.json — user's named team
    3. None — fall back to hardcoded default
    """
    # 1. Project-level
    project_team = project_dir / ".kodo" / "team.json"
    if project_team.is_file():
        return _load_json(project_team)

    # 2. User-level named team
    user_team = Path.home() / ".kodo" / "teams" / f"{name}.json"
    if user_team.is_file():
        return _load_json(user_team)

    return None


def _load_json(path: Path) -> dict:
    """Load and validate team config JSON structure.
    
    Validates against TeamConfigSchema, providing detailed error messages.
    """
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    
    # Validate against schema
    try:
        validated = validate_team_config(data)
        # Return the validated data as dict for backward compatibility
        return {
            "name": validated.name,
            "agents": {
                name: {
                    "backend": agent.backend.value,
                    "model": agent.model,
                    "description": agent.description,
                    "max_turns": agent.max_turns,
                    "timeout_s": agent.timeout_s,
                    "system_prompt": agent.system_prompt,
                    "fallback_model": agent.fallback_model,
                }
                for name, agent in validated.agents.items()
            },
        }
    except ValidationError as exc:
        # Provide detailed validation error messages
        error_details = []
        for error in exc.errors():
            loc = " → ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            error_details.append(f"  {loc}: {msg}")
        
        raise ValueError(
            f"Invalid team config in {path}:\n" + "\n".join(error_details)
        ) from exc


def build_team_from_json(config: dict) -> TeamConfig:
    """Build a TeamConfig from a parsed team JSON config.

    Skips agents whose backends are unavailable (with a warning).
    Raises RuntimeError if no agents remain after skipping.
    """
    backends = available_backends()
    team: TeamConfig = {}

    for agent_key, agent_cfg in config["agents"].items():
        if not isinstance(agent_cfg, dict):
            logger.warning("Skipping agent %r: config must be a dict", agent_key)
            continue

        backend = agent_cfg.get("backend")
        model = agent_cfg.get("model")
        if not backend or not model:
            raise ValueError(
                f"Agent {agent_key!r} must have 'backend' and 'model' fields"
            )

        # Check backend availability
        backend_key = _BACKEND_MAP.get(backend)
        if backend_key is None:
            raise ValueError(
                f"Agent {agent_key!r} has unknown backend {backend!r}. "
                f"Valid backends: {', '.join(_BACKEND_MAP.keys())}"
            )
        if not backends.get(backend_key, False):
            logger.warning(
                "Skipping agent %r: backend %r not available", agent_key, backend
            )
            continue

        # Build session
        description = agent_cfg.get("description", _AGENT_DEFAULTS["description"])
        system_prompt = agent_cfg.get("system_prompt", _AGENT_DEFAULTS["system_prompt"])
        max_turns = agent_cfg.get("max_turns", _AGENT_DEFAULTS["max_turns"])
        timeout_s = agent_cfg.get("timeout_s", _AGENT_DEFAULTS["timeout_s"])
        chrome = agent_cfg.get("chrome", _AGENT_DEFAULTS["chrome"])
        fallback_model = agent_cfg.get(
            "fallback_model", _AGENT_DEFAULTS["fallback_model"]
        )

        session = make_session(
            backend,
            model,
            system_prompt=system_prompt,
            chrome=chrome,
            fallback_model=fallback_model,
        )

        team[agent_key] = Agent(
            session,
            description,
            max_turns=max_turns,
            timeout_s=timeout_s,
        )

    if not team:
        raise RuntimeError(
            "No agents available after checking backends. "
            "Install at least one of: claude, cursor-agent, codex, or gemini."
        )

    return team
