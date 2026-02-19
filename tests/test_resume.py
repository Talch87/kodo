"""Tests for JSONL log parsing and resume support."""

from __future__ import annotations

import json
from pathlib import Path

from kodo import log


def _write_events(log_file: Path, events: list[dict]) -> None:
    """Write a list of event dicts as JSONL lines."""
    lines = []
    for evt in events:
        lines.append(json.dumps({"ts": "2025-01-01T00:00:00Z", "t": 0, **evt}))
    log_file.write_text("\n".join(lines) + "\n")


def test_parse_run_incomplete(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "run_start", "goal": "build it", "orchestrator": "api",
         "model": "opus", "project_dir": "/proj", "max_exchanges": 20,
         "max_cycles": 5, "team": ["worker"]},
        {"event": "cycle_end", "summary": "did stuff", "finished": False},
    ])
    state = log.parse_run(f)
    assert state is not None
    assert state.goal == "build it"
    assert state.completed_cycles == 1
    assert state.last_summary == "did stuff"
    assert state.finished is False
    assert state.orchestrator == "api"
    assert state.model == "opus"
    assert state.max_exchanges == 20
    assert state.max_cycles == 5
    assert state.team == ["worker"]


def test_parse_run_finished(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "opus", "project_dir": "/p", "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cycle_end", "summary": "all done", "finished": True},
        {"event": "run_end"},
    ])
    state = log.parse_run(f)
    assert state is not None
    assert state.finished is True


def test_parse_run_no_run_start(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "cycle_end", "summary": "orphan"},
    ])
    assert log.parse_run(f) is None


def test_parse_run_multiple_cycles(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "opus", "project_dir": "/p", "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cycle_end", "summary": "first cycle"},
        {"event": "cycle_end", "summary": "second cycle"},
        {"event": "cycle_end", "summary": "third cycle"},
    ])
    state = log.parse_run(f)
    assert state is not None
    assert state.completed_cycles == 3
    assert state.last_summary == "third cycle"


def test_parse_run_captures_session_ids(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "opus", "project_dir": "/p", "max_exchanges": 30,
         "max_cycles": 5, "team": ["worker_fast", "worker_smart"]},
        {"event": "session_query_end", "session": "claude", "session_id": "ses-abc"},
        {"event": "agent_run_end", "agent": "worker_smart"},
        {"event": "session_query_end", "session": "cursor", "chat_id": "chat-xyz"},
        {"event": "agent_run_end", "agent": "worker_fast"},
        {"event": "cycle_end", "summary": "done"},
    ])
    state = log.parse_run(f)
    assert state is not None
    assert state.agent_session_ids.get("worker_smart") == "ses-abc"
    assert state.agent_session_ids.get("worker_fast") == "chat-xyz"


def test_parse_run_corrupt_lines_tolerated(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    content = (
        '{"ts":"t","t":0,"event":"run_start","goal":"g","orchestrator":"api",'
        '"model":"m","project_dir":"/p","max_exchanges":30,"max_cycles":5,"team":[]}\n'
        "this is not json\n"
        '{"truncated\n'
        '{"ts":"t","t":0,"event":"cycle_end","summary":"ok"}\n'
    )
    f.write_text(content)
    state = log.parse_run(f)
    assert state is not None
    assert state.completed_cycles == 1
    assert state.last_summary == "ok"


def test_find_incomplete_runs_newest_first(tmp_path: Path):
    log_dir = tmp_path / ".kodo" / "logs"
    log_dir.mkdir(parents=True)

    # Completed run — should not appear
    _write_events(log_dir / "run_complete.jsonl", [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "m", "project_dir": str(tmp_path), "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cycle_end", "summary": "done"},
        {"event": "run_end"},
    ])

    # Incomplete with 0 cycles — should not appear (no cycle_end)
    _write_events(log_dir / "run_nocycles.jsonl", [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "m", "project_dir": str(tmp_path), "max_exchanges": 30,
         "max_cycles": 5, "team": []},
    ])

    # Two incomplete runs with cycles
    _write_events(log_dir / "aaa_older.jsonl", [
        {"event": "run_start", "goal": "g1", "orchestrator": "api",
         "model": "m", "project_dir": str(tmp_path), "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cycle_end", "summary": "older"},
    ])
    _write_events(log_dir / "zzz_newer.jsonl", [
        {"event": "run_start", "goal": "g2", "orchestrator": "api",
         "model": "m", "project_dir": str(tmp_path), "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cycle_end", "summary": "newer"},
    ])

    runs = log.find_incomplete_runs(tmp_path)
    assert len(runs) == 2
    # Sorted by filename descending: zzz before aaa
    assert runs[0].run_id == "zzz_newer"
    assert runs[1].run_id == "aaa_older"


def test_init_append_preserves_existing(tmp_path: Path):
    log_dir = tmp_path / ".kodo" / "logs"
    log_dir.mkdir(parents=True)
    f = log_dir / "test_run.jsonl"
    f.write_text('{"event":"run_start"}\n')

    # init_append needs _start_time to be set for emit() to work
    result = log.init_append(f)
    assert result == f

    content = f.read_text()
    lines = [l for l in content.strip().split("\n") if l]
    assert len(lines) == 2  # original + run_resumed
    last = json.loads(lines[-1])
    assert last["event"] == "run_resumed"


def test_parse_run_with_cli_args(tmp_path: Path):
    f = tmp_path / "run.jsonl"
    _write_events(f, [
        {"event": "run_start", "goal": "g", "orchestrator": "api",
         "model": "opus", "project_dir": "/p", "max_exchanges": 30,
         "max_cycles": 5, "team": []},
        {"event": "cli_args", "mode": "mission", "budget_per_step": 2.5},
        {"event": "cycle_end", "summary": "done"},
    ])
    state = log.parse_run(f)
    assert state is not None
    assert state.mode == "mission"
    assert state.budget_per_step == 2.5
