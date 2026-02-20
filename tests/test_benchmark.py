"""Tests for the performance benchmarking framework.

Covers: BenchmarkSample, CycleBenchmark, BenchmarkBaseline, BenchmarkStore,
comparison logic, formatting, and persistence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from improvements.benchmark import (
    BenchmarkBaseline,
    BenchmarkComparison,
    BenchmarkSample,
    BenchmarkStore,
    CycleBenchmark,
    compare_to_baseline,
    format_comparison_table,
)


# ── BenchmarkSample ──────────────────────────────────────────────────────


class TestBenchmarkSample:
    def test_creation(self) -> None:
        s = BenchmarkSample(metric="tokens_per_task", value=1500, unit="tokens")
        assert s.metric == "tokens_per_task"
        assert s.value == 1500
        assert s.unit == "tokens"
        assert s.timestamp  # auto-generated

    def test_with_metadata(self) -> None:
        s = BenchmarkSample(
            metric="execution_time_s",
            value=120.5,
            unit="seconds",
            metadata={"agent": "worker_smart"},
        )
        assert s.metadata["agent"] == "worker_smart"


# ── CycleBenchmark ───────────────────────────────────────────────────────


class TestCycleBenchmark:
    def test_add_sample(self) -> None:
        cb = CycleBenchmark(cycle_id="1", cycle_name="checkpointing")
        cb.add_sample("tokens_per_task", 1500, "tokens")
        cb.add_sample("execution_time_s", 120, "seconds")
        assert len(cb.samples) == 2

    def test_get_metric(self) -> None:
        cb = CycleBenchmark(cycle_id="1", cycle_name="test")
        cb.add_sample("tokens_per_task", 1500, "tokens")
        cb.add_sample("tokens_per_task", 1200, "tokens")  # updated
        assert cb.get_metric("tokens_per_task") == 1200  # latest

    def test_get_metric_not_found(self) -> None:
        cb = CycleBenchmark(cycle_id="1", cycle_name="test")
        assert cb.get_metric("nonexistent") is None

    def test_get_all_metrics(self) -> None:
        cb = CycleBenchmark(cycle_id="1", cycle_name="test")
        cb.add_sample("a", 10, "x")
        cb.add_sample("b", 20, "y")
        cb.add_sample("a", 15, "x")  # overwrites
        metrics = cb.get_all_metrics()
        assert metrics == {"a": 15, "b": 20}


# ── BenchmarkBaseline ────────────────────────────────────────────────────


class TestBenchmarkBaseline:
    def test_set_metric(self) -> None:
        b = BenchmarkBaseline(version="0.4.9")
        b.set_metric("tokens_per_task", 2000, "tokens")
        assert b.metrics["tokens_per_task"] == 2000
        assert b.units["tokens_per_task"] == "tokens"


# ── BenchmarkStore persistence ───────────────────────────────────────────


class TestBenchmarkStore:
    def test_save_and_load_baseline(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        baseline = BenchmarkBaseline(version="0.4.9")
        baseline.set_metric("tokens_per_task", 2000, "tokens")
        baseline.set_metric("execution_time_s", 300, "seconds")

        store.save_baseline(baseline)
        loaded = store.load_baseline()

        assert loaded is not None
        assert loaded.version == "0.4.9"
        assert loaded.metrics["tokens_per_task"] == 2000
        assert loaded.units["execution_time_s"] == "seconds"

    def test_load_baseline_nonexistent(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        assert store.load_baseline() is None

    def test_save_and_load_cycle(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        cb = CycleBenchmark(cycle_id="1", cycle_name="checkpointing")
        cb.add_sample("tokens_per_task", 1500, "tokens")
        cb.add_sample("test_coverage", 85.0, "%")

        store.save_cycle(cb)
        loaded = store.load_cycle("1")

        assert loaded is not None
        assert loaded.cycle_id == "1"
        assert loaded.cycle_name == "checkpointing"
        assert loaded.get_metric("tokens_per_task") == 1500
        assert loaded.get_metric("test_coverage") == 85.0

    def test_load_cycle_nonexistent(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        assert store.load_cycle("nonexistent") is None

    def test_list_cycles(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        for i in range(3):
            cb = CycleBenchmark(cycle_id=str(i), cycle_name=f"cycle_{i}")
            store.save_cycle(cb)

        cycles = store.list_cycles()
        assert cycles == ["0", "1", "2"]

    def test_list_cycles_empty(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        assert store.list_cycles() == []

    def test_load_all_cycles(self, tmp_path: Path) -> None:
        store = BenchmarkStore(tmp_path)
        for i in range(3):
            cb = CycleBenchmark(cycle_id=str(i), cycle_name=f"cycle_{i}")
            cb.add_sample("metric", float(i), "unit")
            store.save_cycle(cb)

        all_cycles = store.load_all_cycles()
        assert len(all_cycles) == 3
        assert all_cycles[0].cycle_id == "0"
        assert all_cycles[2].get_metric("metric") == 2.0


# ── Comparison logic ─────────────────────────────────────────────────────


class TestCompareToBaseline:
    def test_lower_is_better_improved(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("tokens_per_task", 2000, "tokens")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="opt")
        cycle.add_sample("tokens_per_task", 1400, "tokens")

        comps = compare_to_baseline(baseline, cycle)
        assert len(comps) == 1
        assert comps[0].improved is True
        assert comps[0].improvement_pct == 30.0  # 30% reduction

    def test_lower_is_better_regressed(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("execution_time_s", 100, "seconds")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="slow")
        cycle.add_sample("execution_time_s", 150, "seconds")

        comps = compare_to_baseline(baseline, cycle)
        assert comps[0].improved is False
        assert comps[0].improvement_pct == -50.0  # 50% slower

    def test_higher_is_better_improved(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("test_coverage", 60.0, "%")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="coverage")
        cycle.add_sample("test_coverage", 85.0, "%")

        comps = compare_to_baseline(baseline, cycle)
        assert comps[0].improved is True
        assert comps[0].improvement_pct == pytest.approx(41.67, abs=0.1)

    def test_higher_is_better_regressed(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("test_coverage", 80.0, "%")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="broken")
        cycle.add_sample("test_coverage", 60.0, "%")

        comps = compare_to_baseline(baseline, cycle)
        assert comps[0].improved is False

    def test_no_change(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("tokens_per_task", 1500, "tokens")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="same")
        cycle.add_sample("tokens_per_task", 1500, "tokens")

        comps = compare_to_baseline(baseline, cycle)
        assert comps[0].change_direction == "unchanged"

    def test_missing_metrics_skipped(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("tokens_per_task", 2000, "tokens")
        baseline.set_metric("code_quality", 80, "score")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="partial")
        cycle.add_sample("tokens_per_task", 1500, "tokens")
        # code_quality not measured in cycle

        comps = compare_to_baseline(baseline, cycle)
        assert len(comps) == 1  # only tokens_per_task

    def test_multiple_metrics(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("tokens_per_task", 2000, "tokens")
        baseline.set_metric("execution_time_s", 300, "seconds")
        baseline.set_metric("test_coverage", 70, "%")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="all")
        cycle.add_sample("tokens_per_task", 1400, "tokens")
        cycle.add_sample("execution_time_s", 200, "seconds")
        cycle.add_sample("test_coverage", 85, "%")

        comps = compare_to_baseline(baseline, cycle)
        assert len(comps) == 3
        assert all(c.improved for c in comps)

    def test_zero_baseline(self) -> None:
        baseline = BenchmarkBaseline(version="v0")
        baseline.set_metric("error_rate", 0, "%")

        cycle = CycleBenchmark(cycle_id="1", cycle_name="test")
        cycle.add_sample("error_rate", 5, "%")

        comps = compare_to_baseline(baseline, cycle)
        assert comps[0].improvement_pct == 0.0  # can't compute from zero


# ── BenchmarkComparison ──────────────────────────────────────────────────


class TestBenchmarkComparison:
    def test_change_direction_improved(self) -> None:
        c = BenchmarkComparison(
            metric="x",
            baseline_value=100,
            current_value=80,
            unit="",
            improvement_pct=20.0,
            improved=True,
        )
        assert c.change_direction == "improved"

    def test_change_direction_regressed(self) -> None:
        c = BenchmarkComparison(
            metric="x",
            baseline_value=100,
            current_value=120,
            unit="",
            improvement_pct=-20.0,
            improved=False,
        )
        assert c.change_direction == "regressed"

    def test_change_direction_unchanged(self) -> None:
        c = BenchmarkComparison(
            metric="x",
            baseline_value=100,
            current_value=100.5,
            unit="",
            improvement_pct=0.5,
            improved=False,
        )
        assert c.change_direction == "unchanged"


# ── Formatting ───────────────────────────────────────────────────────────


class TestFormatComparisonTable:
    def test_empty_comparisons(self) -> None:
        result = format_comparison_table([])
        assert "No comparable" in result

    def test_table_format(self) -> None:
        comps = [
            BenchmarkComparison(
                metric="tokens_per_task",
                baseline_value=2000,
                current_value=1400,
                unit="tokens",
                improvement_pct=30.0,
                improved=True,
            ),
            BenchmarkComparison(
                metric="test_coverage",
                baseline_value=70,
                current_value=85,
                unit="%",
                improvement_pct=21.4,
                improved=True,
            ),
        ]
        table = format_comparison_table(comps)
        assert "tokens_per_task" in table
        assert "test_coverage" in table
        assert "✅" in table
        assert "30.0%" in table

    def test_regression_shown(self) -> None:
        comps = [
            BenchmarkComparison(
                metric="speed",
                baseline_value=100,
                current_value=120,
                unit="ms",
                improvement_pct=-20.0,
                improved=False,
            ),
        ]
        table = format_comparison_table(comps)
        assert "⚠️" in table
        assert "-20.0%" in table


# ── End-to-end workflow ──────────────────────────────────────────────────


class TestBenchmarkWorkflow:
    def test_full_cycle(self, tmp_path: Path) -> None:
        """End-to-end: establish baseline → run cycles → compare."""
        store = BenchmarkStore(tmp_path)

        # 1. Establish baseline
        baseline = BenchmarkBaseline(version="0.4.9")
        baseline.set_metric("tokens_per_task", 2000, "tokens")
        baseline.set_metric("execution_time_s", 300, "seconds")
        baseline.set_metric("test_coverage", 70, "%")
        baseline.set_metric("error_rate", 10, "%")
        store.save_baseline(baseline)

        # 2. Run improvement cycles
        for i, (name, tokens, time_s, coverage, errors) in enumerate(
            [
                ("checkpointing", 1800, 280, 75, 8),
                ("retry_logic", 1600, 260, 80, 5),
                ("task_routing", 1400, 240, 85, 3),
            ]
        ):
            cb = CycleBenchmark(cycle_id=str(i + 1), cycle_name=name)
            cb.add_sample("tokens_per_task", tokens, "tokens")
            cb.add_sample("execution_time_s", time_s, "seconds")
            cb.add_sample("test_coverage", coverage, "%")
            cb.add_sample("error_rate", errors, "%")
            store.save_cycle(cb)

        # 3. Load and compare
        loaded_baseline = store.load_baseline()
        assert loaded_baseline is not None

        all_cycles = store.load_all_cycles()
        assert len(all_cycles) == 3

        # Compare latest cycle to baseline
        latest = all_cycles[-1]
        comps = compare_to_baseline(loaded_baseline, latest)

        # All metrics should show improvement
        assert len(comps) == 4
        assert all(c.improved for c in comps)

        # Format the table
        table = format_comparison_table(comps)
        assert "✅" in table
        assert "tokens_per_task" in table

        # Verify specific improvements
        token_comp = next(c for c in comps if c.metric == "tokens_per_task")
        assert token_comp.improvement_pct == 30.0
        assert token_comp.current_value == 1400

        coverage_comp = next(c for c in comps if c.metric == "test_coverage")
        assert coverage_comp.improvement_pct == pytest.approx(21.43, abs=0.1)
