"""Adversarial tests for kodo.log — based on expected interface behavior."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from kodo import log


def test_emit_before_init_is_noop():
    """Emitting before init() should silently do nothing, not crash."""
    # _isolate_log fixture resets state, so we're in uninitialized state
    log._log_file = None
    log._run_id = None
    log._start_time = None
    log.emit("should_not_crash", key="value")
    # No exception = pass


def test_concurrent_emits_dont_corrupt(tmp_path: Path):
    """Multiple threads emitting simultaneously should produce valid JSONL."""
    log.init(tmp_path, run_id="concurrent")
    errors = []

    def writer(thread_id):
        try:
            for i in range(50):
                log.emit("thread_event", thread=thread_id, seq=i)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors

    lines = log.get_log_file().read_text().strip().split("\n")
    # 1 init line + 250 thread lines
    assert len(lines) == 251
    for line in lines:
        record = json.loads(line)  # Should not raise
        assert "event" in record


def test_init_twice_switches_log_file(tmp_path: Path):
    """Calling init a second time should switch to a new log file."""
    f1 = log.init(tmp_path, run_id="run1")
    log.emit("event_in_run1")
    f2 = log.init(tmp_path, run_id="run2")
    log.emit("event_in_run2")

    assert f1 != f2
    assert f1.exists()
    assert f2.exists()

    # run2 events should NOT appear in run1 file
    run1_text = f1.read_text()
    assert "event_in_run2" not in run1_text

    # run2 file should have its own init + event
    run2_lines = f2.read_text().strip().split("\n")
    events = [json.loads(l)["event"] for l in run2_lines]
    assert "run_init" in events
    assert "event_in_run2" in events


def test_emit_with_path_and_dataclass_values(tmp_path: Path):
    """emit should serialize Path objects and dataclasses without crashing."""
    from dataclasses import dataclass

    @dataclass
    class Info:
        name: str
        count: int

    log.init(tmp_path, run_id="serialize")
    log.emit("complex", path=tmp_path / "foo", info=Info(name="x", count=3))

    lines = log.get_log_file().read_text().strip().split("\n")
    record = json.loads(lines[-1])
    assert record["event"] == "complex"
    assert "foo" in record["path"]
    assert record["info"]["name"] == "x"
