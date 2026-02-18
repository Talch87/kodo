"""Structured JSONL logging for run reconstruction.

Every event is a single JSON line with at least: timestamp, event, and contextual fields.
Log file is created per run in the project directory under .kodo/logs/.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log_file: Path | None = None
_run_id: str | None = None
_start_time: float | None = None
_lock = threading.Lock()


def init(project_dir: Path, run_id: str | None = None) -> Path:
    """Initialize logging for a run. Returns the log file path."""
    global _log_file, _run_id, _start_time

    from kodo import __version__

    _run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _start_time = time.monotonic()

    log_dir = project_dir / ".kodo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = log_dir / f"{_run_id}.jsonl"

    emit("run_init", project_dir=str(project_dir), version=__version__)
    return _log_file


def get_log_file() -> Path | None:
    """Return the current log file path, or None if not initialized."""
    return _log_file


def emit(event: str, **data: Any) -> None:
    """Write a single log event."""
    if _log_file is None:
        return

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "t": round(time.monotonic() - (_start_time or 0), 3),
        "event": event,
        **data,
    }

    with _lock:
        with open(_log_file, "a") as f:
            f.write(json.dumps(record, default=_serialize) + "\n")


def tprint(msg: str) -> None:
    """Print with elapsed time prefix, e.g. '[  12.3s] ...'."""
    if _start_time is not None:
        elapsed = time.monotonic() - _start_time
        print(f"  [{elapsed:7.1f}s] {msg}")
    else:
        print(f"  {msg}")


def _serialize(obj: Any) -> Any:
    """JSON fallback serializer."""
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return repr(obj)
