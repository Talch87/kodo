"""User-level configuration from ~/.kodo/config.json."""

from __future__ import annotations

import functools
import json
from pathlib import Path

_USER_CONFIG_PATH = Path.home() / ".kodo" / "config.json"


@functools.lru_cache(maxsize=1)
def load_user_config() -> dict:
    """Load ~/.kodo/config.json. Returns empty dict if missing or invalid."""
    if not _USER_CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(_USER_CONFIG_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_user_default(key: str, default=None):
    """Get a user preference, e.g. get_user_default("fallback_model")."""
    return load_user_config().get(key, default)
