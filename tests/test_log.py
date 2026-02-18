"""Tests for kodo.log module."""

from __future__ import annotations

import json
from pathlib import Path

from kodo import log


def test_init_creates_log_file(tmp_path: Path):
    log_file = log.init(tmp_path, run_id="test_run")
    assert log_file.exists()
    assert log_file.parent == tmp_path / ".kodo" / "logs"
    assert log_file.name == "test_run.jsonl"


def test_emit_writes_json_lines(tmp_path: Path):
    log.init(tmp_path, run_id="emit_test")
    log.emit("my_event", foo="bar", count=42)
    log_file = log.get_log_file()
    lines = log_file.read_text().strip().split("\n")
    # First line is run_init from init(), second is our event
    record = json.loads(lines[-1])
    assert record["event"] == "my_event"
    assert record["foo"] == "bar"
    assert record["count"] == 42
    assert "ts" in record
    assert "t" in record
