"""
Kodo Benchmark Framework - Test improvements against baseline metrics
"""

import time
import subprocess
from typing import Dict, Tuple
from pathlib import Path

class KodoBenchmark:
    """Benchmark Kodo's improvements."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.baseline = {}
        self.results = {}
    
    def measure_build_time(self) -> float:
        """Measure how long build takes."""
        start = time.time()
        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=120,
                text=True
            )
            return time.time() - start if result.returncode == 0 else None
        except subprocess.TimeoutExpired:
            return None
    
    def measure_test_time(self) -> float:
        """Measure how long tests take."""
        start = time.time()
        try:
            result = subprocess.run(
                ["npm", "test"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=180,
                text=True
            )
            return time.time() - start if result.returncode == 0 else None
        except subprocess.TimeoutExpired:
            return None
    
    def measure_code_size(self) -> int:
        """Measure total lines of code."""
        total_lines = 0
        for py_file in self.project_dir.glob("**/*.py"):
            if "/.git" not in str(py_file) and "node_modules" not in str(py_file):
                try:
                    total_lines += len(py_file.read_text().splitlines())
                except:
                    pass
        return total_lines
    
    def measure_import_time(self) -> float:
        """Measure how long it takes to import Kodo."""
        start = time.time()
        try:
            result = subprocess.run(
                ["python3", "-c", "from kodo.autonomous import create_system; import time; time.sleep(0.1)"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=10,
                text=True
            )
            return time.time() - start
        except:
            return None
    
    def measure_git_performance(self) -> float:
        """Measure git operation speed."""
        start = time.time()
        try:
            subprocess.run(
                ["git", "status"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=5,
                text=True
            )
            return time.time() - start
        except:
            return None
    
    def run_baseline(self) -> Dict:
        """Establish baseline metrics."""
        self.baseline = {
            'build_time': self.measure_build_time(),
            'test_time': self.measure_test_time(),
            'code_size': self.measure_code_size(),
            'import_time': self.measure_import_time(),
            'git_performance': self.measure_git_performance(),
        }
        return self.baseline
    
    def run_current(self) -> Dict:
        """Measure current metrics."""
        self.results = {
            'build_time': self.measure_build_time(),
            'test_time': self.measure_test_time(),
            'code_size': self.measure_code_size(),
            'import_time': self.measure_import_time(),
            'git_performance': self.measure_git_performance(),
        }
        return self.results
    
    def compare(self) -> Dict:
        """Compare current metrics to baseline."""
        if not self.baseline:
            return {'status': 'no_baseline'}
        
        comparison = {}
        for metric in self.baseline:
            baseline_val = self.baseline.get(metric)
            current_val = self.results.get(metric)
            
            if baseline_val and current_val and baseline_val > 0:
                pct_change = ((current_val - baseline_val) / baseline_val) * 100
                comparison[metric] = {
                    'baseline': baseline_val,
                    'current': current_val,
                    'change_percent': pct_change,
                    'improved': pct_change < 0  # Lower is better for time/size
                }
            else:
                comparison[metric] = {'status': 'unmeasurable'}
        
        return comparison
    
    def improvement_score(self) -> float:
        """Calculate overall improvement score (0-100)."""
        comparison = self.compare()
        improved_count = sum(1 for m in comparison.values() if m.get('improved'))
        total_count = len([m for m in comparison.values() if 'improved' in m])
        
        if total_count == 0:
            return 50.0  # No data
        
        return (improved_count / total_count) * 100
    
    def report(self) -> str:
        """Generate benchmark report."""
        comparison = self.compare()
        score = self.improvement_score()
        
        report = f"""
=== KODO BENCHMARK REPORT ===
Overall Improvement Score: {score:.1f}%

Metrics:
"""
        for metric, data in comparison.items():
            if 'improved' in data:
                symbol = "✅" if data['improved'] else "❌"
                report += f"{symbol} {metric}: {data['current']:.2f}s (baseline: {data['baseline']:.2f}s, change: {data['change_percent']:+.1f}%)\n"
            else:
                report += f"⚠️ {metric}: {data['status']}\n"
        
        return report

if __name__ == "__main__":
    bench = KodoBenchmark(Path("."))
    bench.run_baseline()
    print("Baseline metrics recorded")
    bench.run_current()
    print(bench.report())
