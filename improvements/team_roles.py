"""
Kodo Team Roles - Defines capabilities and responsibilities
"""

TEAM_STRUCTURE = {
    "roles": {
        "Lead Analyzer": {
            "capabilities": [
                "Code analysis",
                "Improvement identification",
                "Pattern recognition",
                "Opportunity assessment"
            ],
            "responsibilities": [
                "Find 5+ improvements per cycle",
                "Prioritize by impact",
                "Document findings"
            ]
        },
        "Lead Executor": {
            "capabilities": [
                "Code generation",
                "File creation",
                "Commit management",
                "Branch handling",
                "Error recovery"
            ],
            "responsibilities": [
                "Implement improvements safely",
                "Handle failures gracefully",
                "Maintain repo integrity"
            ]
        },
        "Lead Monitor": {
            "capabilities": [
                "Health checking",
                "Metrics collection",
                "Performance tracking",
                "Alert generation",
                "Trend analysis"
            ],
            "responsibilities": [
                "Monitor system health",
                "Detect anomalies",
                "Report status changes",
                "Trigger optimizations"
            ]
        },
        "Lead Optimizer": {
            "capabilities": [
                "Performance tuning",
                "Resource optimization",
                "Batch processing",
                "Parallel execution",
                "Cache management"
            ],
            "responsibilities": [
                "Optimize cycle time",
                "Reduce resource usage",
                "Improve throughput",
                "Scale to handle load"
            ]
        },
        "Lead Reporter": {
            "capabilities": [
                "Progress tracking",
                "Logging",
                "Notifications",
                "Documentation",
                "Status dashboards"
            ],
            "responsibilities": [
                "Log all activities",
                "Report to coordinator",
                "Track metrics",
                "Document improvements"
            ]
        }
    }
}

CAPABILITIES = {
    "parallel_execution": "Run multiple improvements simultaneously",
    "error_recovery": "Automatically recover from failures",
    "batch_processing": "Process improvements in batches",
    "metrics_tracking": "Track and analyze performance metrics",
    "auto_optimization": "Self-optimize based on performance data",
    "distributed_team": "Coordinate across multiple agents",
    "intelligent_prioritization": "Prioritize high-impact improvements",
    "adaptive_learning": "Learn from past results"
}
