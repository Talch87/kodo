"""Export performance metrics in multiple formats."""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from performance_profiler import PerformanceProfiler, PerformanceMetric
from structured_logging import StructuredLogger


class MetricsExporter:
    """Export metrics to various formats for observability."""
    
    def __init__(
        self,
        profiler: PerformanceProfiler,
        logger: StructuredLogger,
        output_dir: Path = Path(".kodo/metrics"),
    ):
        self.profiler = profiler
        self.logger = logger
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_json(self, filename: str = "metrics.json") -> Path:
        """Export metrics to JSON format."""
        output_path = self.output_dir / filename
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "metrics_count": len(self.profiler.metrics),
            "operations": self.profiler.get_statistics(),
            "slowest": [
                {
                    "operation": op,
                    "stats": stats,
                }
                for op, stats in self.profiler.get_slowest_operations()
            ],
        }
        
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        return output_path
    
    def export_csv(self, filename: str = "metrics.csv") -> Path:
        """Export metrics to CSV format."""
        output_path = self.output_dir / filename
        
        # Get statistics
        stats = self.profiler.get_statistics()
        
        rows = []
        for operation, data in sorted(stats.items()):
            rows.append({
                "Operation": operation,
                "Count": data["count"],
                "Min (ms)": f"{data['min_ms']:.2f}",
                "Max (ms)": f"{data['max_ms']:.2f}",
                "Avg (ms)": f"{data['avg_ms']:.2f}",
                "Median (ms)": f"{data['median_ms']:.2f}",
                "P95 (ms)": f"{data['p95_ms']:.2f}",
                "P99 (ms)": f"{data['p99_ms']:.2f}",
                "Total (ms)": f"{data['total_ms']:.2f}",
            })
        
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "Operation", "Count", "Min (ms)", "Max (ms)", "Avg (ms)",
                "Median (ms)", "P95 (ms)", "P99 (ms)", "Total (ms)"
            ])
            writer.writeheader()
            writer.writerows(rows)
        
        return output_path
    
    def export_prometheus(self, filename: str = "metrics.prom") -> Path:
        """Export metrics in Prometheus text format."""
        output_path = self.output_dir / filename
        
        lines = [
            f"# HELP kodo_performance_metrics Performance metrics for Kodo orchestration",
            f"# TYPE kodo_performance_metrics gauge",
            f"# Generated: {datetime.now().isoformat()}",
            "",
        ]
        
        stats = self.profiler.get_statistics()
        
        for operation, data in sorted(stats.items()):
            # Sanitize operation name for Prometheus
            op_name = operation.replace(".", "_").replace("-", "_")
            
            lines.extend([
                f'kodo_operation_count{{operation="{op_name}"}} {data["count"]}',
                f'kodo_operation_min_ms{{operation="{op_name}"}} {data["min_ms"]:.2f}',
                f'kodo_operation_max_ms{{operation="{op_name}"}} {data["max_ms"]:.2f}',
                f'kodo_operation_avg_ms{{operation="{op_name}"}} {data["avg_ms"]:.2f}',
                f'kodo_operation_p95_ms{{operation="{op_name}"}} {data["p95_ms"]:.2f}',
                f'kodo_operation_p99_ms{{operation="{op_name}"}} {data["p99_ms"]:.2f}',
                "",
            ])
        
        # Add cost metrics if available
        cost_summary = self.logger.get_cost_summary()
        for component, cost in sorted(cost_summary.items()):
            comp_name = component.replace(".", "_").replace("-", "_")
            lines.append(
                f'kodo_component_cost_usd{{component="{comp_name}"}} {cost:.4f}'
            )
        
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        
        return output_path
    
    def export_all(self) -> Dict[str, Path]:
        """Export metrics in all formats."""
        return {
            "json": self.export_json(),
            "csv": self.export_csv(),
            "prometheus": self.export_prometheus(),
        }
    
    def generate_summary(self) -> str:
        """Generate a text summary of metrics."""
        stats = self.profiler.get_statistics()
        errors = self.logger.get_errors()
        cost_summary = self.logger.get_cost_summary()
        
        lines = [
            "=" * 60,
            "KODO OBSERVABILITY METRICS SUMMARY",
            "=" * 60,
            f"Generated: {datetime.now().isoformat()}",
            "",
            "PERFORMANCE METRICS",
            "-" * 60,
            f"Total operations recorded: {len(self.profiler.metrics)}",
            f"Unique operations: {len(stats)}",
            "",
        ]
        
        slowest = self.profiler.get_slowest_operations(5)
        if slowest:
            lines.append("Slowest operations (by average):")
            for i, (op, data) in enumerate(slowest, 1):
                lines.append(
                    f"  {i}. {op}: {data['avg_ms']:.2f}ms "
                    f"(n={data['count']}, p99={data['p99_ms']:.2f}ms)"
                )
            lines.append("")
        
        lines.extend([
            "COST METRICS",
            "-" * 60,
        ])
        
        if cost_summary:
            total_cost = sum(cost_summary.values())
            lines.append(f"Total cost: ${total_cost:.4f}")
            lines.append("Cost by component:")
            for component, cost in sorted(cost_summary.items(), key=lambda x: -x[1]):
                lines.append(f"  - {component}: ${cost:.4f}")
        else:
            lines.append("No cost data recorded")
        
        lines.extend([
            "",
            "ERROR METRICS",
            "-" * 60,
            f"Total errors: {len(errors)}",
        ])
        
        if errors:
            lines.append("Recent errors:")
            for error in errors[-5:]:
                lines.append(f"  - [{error.component}] {error.message}")
                if error.error:
                    lines.append(f"    Error: {error.error}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
