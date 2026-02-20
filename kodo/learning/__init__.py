"""
KODO 2.0 Pillars 8-10: Learning & Improvement

Pillar 8: Production Feedback Loop - Collect metrics, analyze patterns
Pillar 9: Human Trust Score - Calculate 0-100% confidence
Pillar 10: Autonomous Improvement - Post-project analysis, pattern extraction
"""

from .feedback import FeedbackCollector, FeedbackRecord
from .trust import TrustScorer, TrustAssessment
from .improvement import AutomatedImprovement, ImprovementSuggestion

__all__ = [
    "FeedbackCollector",
    "FeedbackRecord",
    "TrustScorer",
    "TrustAssessment",
    "AutomatedImprovement",
    "ImprovementSuggestion",
]
