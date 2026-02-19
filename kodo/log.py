"""Structured JSONL logging for run reconstruction.

Every event is a single JSON line with at least: timestamp, event, and contextual fields.
Log file is created per run in the project directory under .kodo/logs/.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log_file: Path | None = None
_run_id: str | None = None
_start_time: float | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Live run statistics
# ---------------------------------------------------------------------------


@dataclass
class _AgentStats:
    calls: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    errors: int = 0
    cost_bucket: str = ""


@dataclass
class RunStats:
    """Accumulates per-agent and per-bucket cost stats during a run."""

    agents: dict[str, _AgentStats] = field(default_factory=dict)
    orchestrator_cost_usd: float = 0.0
    orchestrator_bucket: str = "api"

    def record_agent(
        self,
        agent: str,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        elapsed_s: float,
        is_error: bool,
        cost_bucket: str,
    ) -> None:
        if agent not in self.agents:
            self.agents[agent] = _AgentStats(cost_bucket=cost_bucket)
        s = self.agents[agent]
        s.calls += 1
        s.cost_usd += cost_usd
        s.input_tokens += input_tokens
        s.output_tokens += output_tokens
        s.elapsed_s += elapsed_s
        if is_error:
            s.errors += 1
        if cost_bucket:
            s.cost_bucket = cost_bucket

    def record_orchestrator(self, cost_usd: float, bucket: str = "api") -> None:
        self.orchestrator_cost_usd += cost_usd
        self.orchestrator_bucket = bucket

    @property
    def total_exchanges(self) -> int:
        return sum(s.calls for s in self.agents.values())

    def cost_by_bucket(self) -> dict[str, float]:
        buckets: dict[str, float] = defaultdict(float)
        for s in self.agents.values():
            buckets[s.cost_bucket] += s.cost_usd
        buckets[self.orchestrator_bucket] += self.orchestrator_cost_usd
        return dict(buckets)

    def total_cost(self) -> float:
        return (
            sum(s.cost_usd for s in self.agents.values()) + self.orchestrator_cost_usd
        )


_run_stats = RunStats()


def init(project_dir: Path, run_id: str | None = None) -> Path:
    """Initialize logging for a run. Returns the log file path."""
    global _log_file, _run_id, _start_time, _run_stats

    from kodo import __version__

    _run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _start_time = time.monotonic()
    _run_stats = RunStats()

    log_dir = project_dir / ".kodo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = log_dir / f"{_run_id}.jsonl"

    emit("run_init", project_dir=str(project_dir), version=__version__)
    return _log_file


def get_run_stats() -> RunStats:
    """Return the live run statistics accumulator."""
    return _run_stats


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


def _fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    m = int(s // 60)
    sec = s % 60
    if m < 60:
        return f"{m}m{sec:02.0f}s"
    return f"{m // 60}h{m % 60:02d}m"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def _fmt_cost(c: float) -> str:
    if c < 0.005:
        return "  -"
    return f"${c:.2f}"


def _bucket_label(b: str) -> str:
    return {
        "api": "API",
        "claude_subscription": "Claude sub",
        "cursor_subscription": "Cursor sub",
    }.get(b, b)


def print_stats_table(final: bool = False) -> None:
    """Print a compact stats table to the terminal.

    Called periodically during a run and once at termination.
    """
    stats = _run_stats
    if not stats.agents:
        return

    elapsed = time.monotonic() - (_start_time or time.monotonic())

    # Header
    sep = "-" * 88
    label = "FINAL STATS" if final else "PROGRESS"
    print(f"\n  {sep}")
    print(f"  | {label:<84} |")
    print(
        f"  | {'Agent':<24} {'Bucket':<12} {'#':>3} {'Cost':>8}"
        f" {'In':>6} {'Out':>6} {'Time':>7} {'Err':>3} |"
    )
    print(f"  |{sep[1:-1]}|")

    for agent, s in sorted(stats.agents.items()):
        print(
            f"  | {agent:<24} {_bucket_label(s.cost_bucket):<12}"
            f" {s.calls:>3} {_fmt_cost(s.cost_usd):>8}"
            f" {_fmt_tokens(s.input_tokens):>6} {_fmt_tokens(s.output_tokens):>6}"
            f" {_fmt_time(s.elapsed_s):>7} {s.errors:>3} |"
        )

    # Orchestrator row
    if stats.orchestrator_cost_usd > 0:
        print(
            f"  | {'orchestrator':<24} {_bucket_label(stats.orchestrator_bucket):<12}"
            f" {'':>3} {_fmt_cost(stats.orchestrator_cost_usd):>8}"
            f" {'':>6} {'':>6} {'':>7} {'':>3} |"
        )

    print(f"  |{sep[1:-1]}|")

    # Totals by bucket
    buckets = stats.cost_by_bucket()
    api = buckets.get("api", 0)
    sub = sum(v for k, v in buckets.items() if k != "api")
    total = stats.total_cost()
    print(
        f"  | {'Total':<24} {'':12} {stats.total_exchanges:>3}"
        f" {_fmt_cost(total):>8} {'':>6} {'':>6}"
        f" {_fmt_time(elapsed):>7} {'':>3} |"
    )
    print(
        f"  |   Real API: {_fmt_cost(api):<10}"
        f"  Subscription: {_fmt_cost(sub):<10}"
        f"  Wall: {_fmt_time(elapsed):<25}|"
    )
    print(f"  {sep}\n")


def get_run_id() -> str | None:
    """Return the current run ID, or None if not initialized."""
    return _run_id


# ---------------------------------------------------------------------------
# JSONL log parsing for resume support
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    """Parsed state of a run from its JSONL log file."""

    run_id: str
    log_file: Path
    goal: str
    orchestrator: str
    model: str
    project_dir: str
    max_exchanges: int
    max_cycles: int
    team: list[str]
    completed_cycles: int
    last_summary: str
    finished: bool
    agent_session_ids: dict[str, str]  # agent_name → last session_id
    mode: str = ""
    budget_per_step: float | None = None


def parse_run(log_file: Path) -> RunState | None:
    """Parse a JSONL log file into a RunState. Returns None if no run_start found."""
    run_start: dict | None = None
    cli_args: dict | None = None
    completed_cycles = 0
    last_summary = ""
    finished = False
    agent_session_ids: dict[str, str] = {}

    for raw_line in log_file.read_text().splitlines():
        try:
            evt = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue  # tolerate corrupt lines

        event = evt.get("event")
        if event == "run_start":
            run_start = evt
        elif event == "cli_args":
            cli_args = evt
        elif event == "cycle_end":
            completed_cycles += 1
            last_summary = evt.get("summary", "")
        elif event == "run_end":
            finished = True
        elif event == "session_query_end":
            # Build agent_session_ids from session query logs.
            # The agent_name is logged in agent_run_start/end but session_query_end
            # logs have session="claude"/"cursor". We track by session type + model
            # but more usefully we correlate via the agent_run events.
            sid = evt.get("session_id") or evt.get("chat_id")
            if sid:
                # Use session type as key; will be correlated with agent names
                # via the orchestrator_tool_call events
                session_key = evt.get("session", "unknown")
                agent_session_ids[session_key] = sid
        elif event == "orchestrator_tool_call":
            # Track which agent name maps to which session
            pass
        elif event == "agent_run_end":
            # After an agent run, the most recent session_query_end's session_id
            # belongs to this agent
            agent_name = evt.get("agent", "")
            if agent_name:
                # Check for the latest session_id we've seen
                for key in list(agent_session_ids.keys()):
                    if key in ("claude", "cursor"):
                        agent_session_ids[agent_name] = agent_session_ids.pop(key)

    if run_start is None:
        return None

    return RunState(
        run_id=log_file.stem,
        log_file=log_file,
        goal=run_start.get("goal", ""),
        orchestrator=run_start.get("orchestrator", ""),
        model=run_start.get("model", ""),
        project_dir=run_start.get("project_dir", ""),
        max_exchanges=run_start.get("max_exchanges", 30),
        max_cycles=run_start.get("max_cycles", 5),
        team=run_start.get("team", []),
        completed_cycles=completed_cycles,
        last_summary=last_summary,
        finished=finished,
        agent_session_ids=agent_session_ids,
        mode=cli_args.get("mode", "") if cli_args else "",
        budget_per_step=cli_args.get("budget_per_step") if cli_args else None,
    )


def find_incomplete_runs(project_dir: Path) -> list[RunState]:
    """Scan .kodo/logs/*.jsonl for incomplete runs, newest first.

    An incomplete run has a run_start + at least 1 cycle_end but no run_end.
    """
    log_dir = project_dir / ".kodo" / "logs"
    if not log_dir.exists():
        return []

    runs: list[RunState] = []
    for f in sorted(log_dir.glob("*.jsonl"), reverse=True):
        state = parse_run(f)
        if state is None:
            continue
        if not state.finished and state.completed_cycles >= 1:
            runs.append(state)

    return runs


def init_append(log_file: Path) -> Path:
    """Set module globals to append to an existing log file. Emits run_resumed marker."""
    global _log_file, _run_id, _start_time, _run_stats

    _log_file = log_file
    _run_id = log_file.stem
    _start_time = time.monotonic()
    _run_stats = RunStats()

    emit("run_resumed", log_file=str(log_file))
    return log_file


def _serialize(obj: Any) -> Any:
    """JSON fallback serializer."""
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return repr(obj)
