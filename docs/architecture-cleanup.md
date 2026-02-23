# Architecture Cleanup Proposals

## Priority 1 — `SubprocessSession` base class

`CursorSession`, `CodexSession`, `GeminiCliSession` all duplicate `_drain_stderr`, system-prompt prepend, and `proc.wait()` patterns. An intermediate base class removes ~80 lines of copy-paste.

## Priority 2 — Decouple resume from concrete session types

`OrchestratorBase.run()` does `isinstance(sess, ClaudeSession)` etc. to inject resume state. Instead, add `set_session_id(id)` to the `Session` protocol — the base class calls it without knowing the concrete type.

## Priority 3 — Split `log.py` responsibilities

`log.py` conflates logging, run directory management, statistics, and log parsing/replay. Split out `runs.py` or `history.py` for `parse_run()`, `list_runs()`, `find_incomplete_runs()`, `RunState`.

## Priority 4 — Smaller issues

- **Duplicated workers**: `_build_team_saga()` and `_build_team_mission()` share ~60 lines — extract `_build_workers()`
- **Eager module-level evaluation**: `MODES = get_modes()` in `factory.py` runs PATH detection at import time
- **Fragile plan-mode**: `ClaudeSession.query()` uses keyword string matching — brittle and untested
- **Model aliases scattered**: `_MODEL_ALIASES`, reverse lookup in `cli.py`, `_PYDANTIC_MODEL_MAP` + `_MODEL_PRICING` — consolidate
