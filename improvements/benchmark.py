"""Performance benchmarking framework for Kodo.

Measures agent execution time, token usage, code quality, and test coverage.
Supports baseline establishment and comparison across improvement cycles.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkSample:
    """A single measurement of a metric."""

    metric: str
    value: float
    unit: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CycleBenchmark:
    """Benchmark results for a single improvement cycle."""

    cycle_id: str
    cycle_name: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    samples: list[BenchmarkSample] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_sample(
        self,
        metric: str,
        value: float,
        unit: str,
        **metadata: Any,
    ) -> None:
        """Record a single metric measurement."""
        self.samples.append(
            BenchmarkSample(metric=metric, value=value, unit=unit, metadata=metadata)
        )

    def get_metric(self, metric: str) -> float | None:
        """Get the latest value for a named metric."""
        for sample in reversed(self.samples):
            if sample.metric == metric:
                return sample.value
        return None

    def get_all_metrics(self) -> dict[str, float]:
        """Get latest values for all metrics."""
        result: dict[str, float] = {}
        for sample in self.samples:
            result[sample.metric] = sample.value
        return result


@dataclass
class BenchmarkBaseline:
    """Baseline measurements for comparison."""

    version: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metrics: dict[str, float] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)

    def set_metric(self, name: str, value: float, unit: str) -> None:
        self.metrics[name] = value
        self.units[name] = unit


@dataclass
class BenchmarkComparison:
    """Comparison between a cycle's metrics and the baseline."""

    metric: str
    baseline_value: float
    current_value: float
    unit: str
    improvement_pct: float  # positive = improved
    improved: bool

    @property
    def change_direction(self) -> str:
        if self.improvement_pct > 1.0:
            return "improved"
        if self.improvement_pct < -1.0:
            return "regressed"
        return "unchanged"


class BenchmarkStore:
    """Persistent storage for benchmark data.

    Stores baselines and cycle benchmarks as JSON files in the
    ``improvements/benchmarks/`` directory.
    """

    def __init__(self, project_dir: Path):
        self.bench_dir = project_dir / "improvements" / "benchmarks"
        self.bench_dir.mkdir(parents=True, exist_ok=True)

    def save_baseline(self, baseline: BenchmarkBaseline) -> Path:
        """Save a baseline to disk."""
        path = self.bench_dir / "baseline.json"
        path.write_text(
            json.dumps(asdict(baseline), indent=2), encoding="utf-8"
        )
        return path

    def load_baseline(self) -> BenchmarkBaseline | None:
        """Load the current baseline, or None if not set."""
        path = self.bench_dir / "baseline.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BenchmarkBaseline(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save_cycle(self, benchmark: CycleBenchmark) -> Path:
        """Save a cycle benchmark to disk."""
        path = self.bench_dir / f"cycle_{benchmark.cycle_id}.json"
        path.write_text(
            json.dumps(asdict(benchmark), indent=2), encoding="utf-8"
        )
        return path

    def load_cycle(self, cycle_id: str) -> CycleBenchmark | None:
        """Load a specific cycle benchmark."""
        path = self.bench_dir / f"cycle_{cycle_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            samples = [BenchmarkSample(**s) for s in data.pop("samples", [])]
            return CycleBenchmark(**data, samples=samples)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def list_cycles(self) -> list[str]:
        """List all stored cycle IDs, sorted chronologically."""
        ids = []
        for path in sorted(self.bench_dir.glob("cycle_*.json")):
            cycle_id = path.stem.replace("cycle_", "")
            ids.append(cycle_id)
        return ids

    def load_all_cycles(self) -> list[CycleBenchmark]:
        """Load all cycle benchmarks, sorted by ID."""
        return [
            cb
            for cid in self.list_cycles()
            if (cb := self.load_cycle(cid)) is not None
        ]


def compare_to_baseline(
    baseline: BenchmarkBaseline,
    cycle: CycleBenchmark,
    *,
    lower_is_better: set[str] | None = None,
) -> list[BenchmarkComparison]:
    """Compare cycle metrics to the baseline.

    Parameters
    ----------
    baseline : BenchmarkBaseline
        The reference measurements.
    cycle : CycleBenchmark
        The current cycle's measurements.
    lower_is_better : set[str], optional
        Metrics where lower values are improvements (e.g., "tokens_per_task",
        "execution_time_s"). Default: {"tokens_per_task", "execution_time_s",
        "error_rate", "bug_escape_rate"}.

    Returns
    -------
    list[BenchmarkComparison]
        One entry per shared metric.
    """
    if lower_is_better is None:
        lower_is_better = {
            "tokens_per_task",
            "execution_time_s",
            "error_rate",
            "bug_escape_rate",
            "rework_rate",
        }

    comparisons: list[BenchmarkComparison] = []
    current_metrics = cycle.get_all_metrics()

    for metric, baseline_val in baseline.metrics.items():
        if metric not in current_metrics:
            continue
        current_val = current_metrics[metric]
        unit = baseline.units.get(metric, "")

        if baseline_val == 0:
            pct = 0.0
        elif metric in lower_is_better:
            # Lower is better: improvement = (baseline - current) / baseline
            pct = ((baseline_val - current_val) / abs(baseline_val)) * 100
        else:
            # Higher is better: improvement = (current - baseline) / baseline
            pct = ((current_val - baseline_val) / abs(baseline_val)) * 100

        comparisons.append(
            BenchmarkComparison(
                metric=metric,
                baseline_value=baseline_val,
                current_value=current_val,
                unit=unit,
                improvement_pct=round(pct, 2),
                improved=pct > 1.0,
            )
        )

    return comparisons


def format_comparison_table(comparisons: list[BenchmarkComparison]) -> str:
    """Format comparisons as a readable markdown table."""
    if not comparisons:
        return "No comparable metrics found."

    lines = [
        "| Metric | Baseline | Current | Change | Status |",
        "|--------|----------|---------|--------|--------|",
    ]
    for c in comparisons:
        status = "✅" if c.improved else ("⚠️" if c.improvement_pct < -1 else "➖")
        sign = "+" if c.improvement_pct > 0 else ""
        lines.append(
            f"| {c.metric} | {c.baseline_value:.2f} {c.unit} "
            f"| {c.current_value:.2f} {c.unit} "
            f"| {sign}{c.improvement_pct:.1f}% | {status} |"
        )

    return "\n".join(lines)
