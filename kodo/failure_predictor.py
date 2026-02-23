"""Predictive Failure Detection - Estimate failure likelihood before verification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class RiskIndicator:
    """A risk factor that increases failure likelihood."""
    name: str
    weight: float  # 0.0-1.0, higher = more severe
    description: str
    mitigations: List[str] = None
    
    def __post_init__(self):
        if self.mitigations is None:
            self.mitigations = []


class FailurePredictor:
    """Predict likelihood of code failure before sending to verification."""
    
    # Common failure patterns with weights
    FAILURE_PATTERNS = {
        "resource_leak": {
            "weight": 0.8,
            "indicators": [
                "open(", ".connect(", "Thread(", "socket(", "file handle",
                "not closed", "cleanup", "finally", "context manager"
            ],
            "description": "Likely unclosed resources or file handles",
            "mitigations": ["Use 'with' statements", "Add cleanup in finally block", "Use context managers"]
        },
        "type_mismatch": {
            "weight": 0.7,
            "indicators": [
                "str +", "int +", "None", "type error", "isinstance(", "typevar",
                "Optional[", "Union[", "List[List[", "Dict[str, Any]"
            ],
            "description": "Possible type mismatches or None dereferencing",
            "mitigations": ["Add type hints", "Use mypy", "Add None checks", "Use type guards"]
        },
        "state_mutation": {
            "weight": 0.75,
            "indicators": [
                "self.", "global ", ".append(", ".pop(", "mutable", "class variable",
                "shared state", "concurrent", "thread", "race condition"
            ],
            "description": "Possible state mutation or race conditions",
            "mitigations": ["Use immutable structures", "Add locks", "Avoid class variables", "Use thread-safe collections"]
        },
        "boundary_error": {
            "weight": 0.6,
            "indicators": [
                "[0]", "[-1]", ".pop()", "range(", "len(", "IndexError",
                "out of bounds", "empty list", "empty string"
            ],
            "description": "Possible boundary or indexing errors",
            "mitigations": ["Add length checks", "Use safe indexing", "Handle empty cases"]
        },
        "circular_dependency": {
            "weight": 0.65,
            "indicators": [
                "import ", "from ", "circular", "cycle", "depends on",
                "A imports B", "B imports A"
            ],
            "description": "Possible circular imports or dependencies",
            "mitigations": ["Restructure imports", "Use local imports", "Refactor modules"]
        },
        "api_contract_violation": {
            "weight": 0.7,
            "indicators": [
                "TODO", "FIXME", "XXX", "hack", "workaround",
                "assumes", "expects", "depends on", "requires"
            ],
            "description": "Code that makes assumptions about APIs or contracts",
            "mitigations": ["Add assertions", "Validate inputs", "Document contracts"]
        },
        "performance_issue": {
            "weight": 0.5,
            "indicators": [
                "for i in range(1000000)", "nested for", "O(n²)", "O(n³)",
                "inefficient", "slow", "timeout", "large dataset"
            ],
            "description": "Potential performance bottlenecks",
            "mitigations": ["Optimize algorithms", "Use caching", "Profile code", "Use generators"]
        }
    }
    
    def __init__(self, history_file: Path = Path(".kodo/failure_predictions.jsonl")):
        self.history_file = history_file
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
    
    def analyze_code(self, code: str) -> Dict[str, float]:
        """
        Analyze code and return risk scores for each failure pattern.
        Returns: {pattern_name: risk_score (0.0-1.0)}
        """
        risks = {}
        code_lower = code.lower()
        
        for pattern_name, pattern_info in self.FAILURE_PATTERNS.items():
            indicators_found = sum(
                1 for indicator in pattern_info["indicators"]
                if indicator.lower() in code_lower
            )
            
            # Risk score: percentage of indicators found * pattern weight
            pattern_weight = pattern_info["weight"]
            num_indicators = len(pattern_info["indicators"])
            
            if num_indicators > 0:
                indicator_ratio = min(1.0, indicators_found / max(1, num_indicators / 3))
                risk_score = indicator_ratio * pattern_weight
                risks[pattern_name] = risk_score
        
        return risks
    
    def predict_failure(self, code: str, agent_name: str = "unknown") -> Tuple[float, List[str], Dict]:
        """
        Predict overall failure likelihood (0.0-1.0).
        Returns: (failure_probability, concerns, details)
        """
        risks = self.analyze_code(code)
        
        # Remove zero scores
        risks = {k: v for k, v in risks.items() if v > 0.1}
        
        if not risks:
            return 0.0, [], {}
        
        # Overall probability: average of top risks
        top_risks = sorted(risks.items(), key=lambda x: x[1], reverse=True)[:3]
        failure_prob = sum(r for _, r in top_risks) / max(1, len(top_risks))
        
        concerns = [
            f"{self.FAILURE_PATTERNS[name]['description']} (risk: {score:.1%})"
            for name, score in top_risks
        ]
        
        details = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "all_risks": risks,
            "top_risks": dict(top_risks),
            "failure_probability": failure_prob,
            "concerns": concerns,
        }
        
        # Log to history
        with open(self.history_file, "a") as f:
            f.write(json.dumps(details) + "\n")
        
        return failure_prob, concerns, details
    
    def get_mitigations(self, failure_prob: float, details: Dict) -> List[str]:
        """Get suggested mitigations based on predicted risks."""
        if failure_prob < 0.3:
            return ["Code looks relatively safe. Standard verification should suffice."]
        
        mitigations = []
        for pattern_name, score in details.get("top_risks", {}).items():
            if pattern_name in self.FAILURE_PATTERNS:
                pattern_info = self.FAILURE_PATTERNS[pattern_name]
                mitigations.extend(pattern_info["mitigations"])
        
        return list(set(mitigations))[:5]  # Remove duplicates, return top 5
    
    def generate_report(self, code: str, agent_name: str = "unknown") -> str:
        """Generate a failure risk report."""
        failure_prob, concerns, details = self.predict_failure(code, agent_name)
        
        risk_level = "🟢 LOW" if failure_prob < 0.3 else "🟡 MEDIUM" if failure_prob < 0.6 else "🔴 HIGH"
        
        lines = [
            "# Failure Risk Analysis",
            f"Risk Level: {risk_level} ({failure_prob:.1%} failure probability)",
            "",
            "## Key Concerns",
            ""
        ]
        
        if concerns:
            for concern in concerns:
                lines.append(f"- {concern}")
        else:
            lines.append("- No major risks detected")
        
        lines.append("")
        lines.append("## Recommended Mitigations")
        lines.append("")
        
        mitigations = self.get_mitigations(failure_prob, details)
        for i, miti in enumerate(mitigations, 1):
            lines.append(f"{i}. {miti}")
        
        if failure_prob >= 0.6:
            lines.extend([
                "",
                "## ⚠️ Recommendation",
                "HIGH RISK: Consider code review before running in production.",
                "Suggest rewriting to address identified concerns."
            ])
        
        return "\n".join(lines)
