"""Context window budgeting for proactive token management.

Prevents surprise context resets by forecasting token usage and resetting
the session *before* hitting the limit, rather than *after*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ContextBudget:
    """Manages token budget for a session.
    
    Prevents context overflow by checking if queries will fit before
    submitting them. Uses conservative estimates to provide headroom.
    
    Attributes:
        total_tokens: Total context window size (e.g., 128000 for GPT-4)
        reserved_for_output: Fraction of budget reserved for output (default: 0.2 = 20%)
    """
    
    total_tokens: int
    reserved_for_output: float = 0.2  # Reserve 20% for output tokens
    
    def __post_init__(self):
        """Validate parameters."""
        if self.total_tokens <= 0:
            raise ValueError("total_tokens must be positive")
        if not 0 <= self.reserved_for_output <= 1:
            raise ValueError("reserved_for_output must be between 0 and 1")
    
    @property
    def available_for_input(self) -> int:
        """Tokens available for input (after reserving space for output)."""
        reserved = int(self.total_tokens * self.reserved_for_output)
        return self.total_tokens - reserved
    
    def can_fit_query(self, query_tokens: int, safety_margin: float = 0.1) -> bool:
        """Check if a query fits in the remaining budget.
        
        Args:
            query_tokens: Estimated tokens the query will use
            safety_margin: Additional margin to keep free (default: 10%)
        
        Returns:
            True if query fits with safety margin, False otherwise
        """
        safety_tokens = int(self.total_tokens * safety_margin)
        available = self.available_for_input - safety_tokens
        return query_tokens < available
    
    def get_reset_urgency(self, used_tokens: int) -> ResetUrgency:
        """Determine how urgent a reset is.
        
        Args:
            used_tokens: Number of tokens already used in session
        
        Returns:
            ResetUrgency level indicating how soon to reset
        """
        available = self.available_for_input
        remaining = available - used_tokens
        utilization = used_tokens / available
        
        if utilization >= 0.95:
            return ResetUrgency.CRITICAL
        elif utilization >= 0.80:
            return ResetUrgency.HIGH
        elif utilization >= 0.60:
            return ResetUrgency.MEDIUM
        else:
            return ResetUrgency.LOW
    
    def forecast_after_query(
        self,
        current_used_tokens: int,
        query_tokens: int,
        estimated_output_ratio: float = 1.5,
    ) -> int:
        """Forecast total tokens after query execution.
        
        Args:
            current_used_tokens: Tokens already used in session
            query_tokens: Estimated input tokens for query
            estimated_output_ratio: Ratio of output to input tokens (default: 1.5x)
        
        Returns:
            Estimated total tokens after query completes
        """
        output_tokens = int(query_tokens * estimated_output_ratio)
        return current_used_tokens + query_tokens + output_tokens
    
    def should_reset_proactively(
        self,
        current_used_tokens: int,
        query_tokens: int,
        estimated_output_ratio: float = 1.5,
    ) -> bool:
        """Decide if session should reset before next query.
        
        Proactively resets if forecast shows we'd exceed 80% utilization
        after the query, preventing surprise resets mid-execution.
        
        Args:
            current_used_tokens: Tokens already used
            query_tokens: Estimated input tokens for next query
            estimated_output_ratio: Ratio of output to input tokens
        
        Returns:
            True if reset is recommended, False otherwise
        """
        forecast = self.forecast_after_query(
            current_used_tokens,
            query_tokens,
            estimated_output_ratio,
        )
        utilization = forecast / self.available_for_input
        return utilization >= 0.80


class ResetUrgency:
    """Urgency levels for context resets."""
    
    LOW = "low"        # < 60% utilization
    MEDIUM = "medium"  # 60-80% utilization
    HIGH = "high"      # 80-95% utilization
    CRITICAL = "critical"  # > 95% utilization


def estimate_token_count(text: str, model: Optional[str] = None) -> int:
    """Estimate token count for text.
    
    Uses conservative approximations:
    - English text: ~4 characters per token
    - Code/JSON: ~3 characters per token (more tokens due to symbols)
    - Includes 10% overhead for tokenization artifacts
    
    Args:
        text: Text to estimate tokens for
        model: Model name (affects estimation, currently unused)
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Simple character-based estimation
    # Most English: ~4 chars/token
    # Code/JSON: ~3 chars/token
    # Average: use 3.5 to be slightly conservative
    
    char_count = len(text)
    estimated = int(char_count / 3.5)
    
    # Add 10% overhead for tokenization artifacts
    overhead = int(estimated * 0.1)
    
    return estimated + overhead


def estimate_output_tokens(task_description: str) -> int:
    """Estimate output tokens for a task.
    
    Different tasks produce different amounts of output:
    - "Generate code": ~1.5-2x input tokens
    - "Analyze code": ~0.5-1x input tokens
    - "Write documentation": ~1.5x input tokens
    - "Debug": ~1x input tokens
    
    Args:
        task_description: Description of the task
    
    Returns:
        Multiplier to apply to input tokens for output estimate
    """
    description_lower = task_description.lower()
    
    # Tasks that typically produce more output
    if any(word in description_lower for word in ["implement", "write", "generate", "build"]):
        return 2.0
    
    # Tasks that produce moderate output
    if any(word in description_lower for word in ["analyze", "review", "debug", "explain"]):
        return 1.0
    
    # Default: assume output is similar to input
    return 1.0
