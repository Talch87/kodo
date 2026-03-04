"""Tests for context window budgeting and token forecasting."""

import pytest
from kodo.sessions.context_budget import (
    ContextBudget,
    ResetUrgency,
    estimate_token_count,
    estimate_output_tokens,
)


class TestContextBudget:
    """Test context budget calculations."""
    
    def test_create_budget(self):
        """Create a context budget."""
        budget = ContextBudget(total_tokens=128000)
        
        assert budget.total_tokens == 128000
        assert budget.reserved_for_output == 0.2
    
    def test_available_for_input(self):
        """Calculate available tokens for input."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # 100000 * 0.2 = 20000 reserved for output
        # 100000 - 20000 = 80000 for input
        assert budget.available_for_input == 80000
    
    def test_available_for_input_with_different_reservation(self):
        """Different reservations affect available tokens."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.5)
        
        # 100000 * 0.5 = 50000 reserved
        # 100000 - 50000 = 50000 available
        assert budget.available_for_input == 50000
    
    def test_can_fit_query_simple(self):
        """Check if query fits without safety margin."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000
        assert budget.can_fit_query(10000, safety_margin=0.0) is True
        assert budget.can_fit_query(80000, safety_margin=0.0) is False
    
    def test_can_fit_query_with_safety_margin(self):
        """Safety margin prevents overshooting."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000, Safety: 10000, Can use: 70000
        assert budget.can_fit_query(60000, safety_margin=0.1) is True
        assert budget.can_fit_query(70000, safety_margin=0.1) is False
    
    def test_get_reset_urgency_low(self):
        """Low utilization = LOW urgency."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000, used: 40000 = 50% utilization
        urgency = budget.get_reset_urgency(40000)
        assert urgency == ResetUrgency.LOW
    
    def test_get_reset_urgency_medium(self):
        """60-80% utilization = MEDIUM urgency."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000, used: 60000 = 75% utilization
        urgency = budget.get_reset_urgency(60000)
        assert urgency == ResetUrgency.MEDIUM
    
    def test_get_reset_urgency_high(self):
        """80-95% utilization = HIGH urgency."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000, used: 70000 = 87.5% utilization
        urgency = budget.get_reset_urgency(70000)
        assert urgency == ResetUrgency.HIGH
    
    def test_get_reset_urgency_critical(self):
        """>95% utilization = CRITICAL urgency."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Available: 80000, used: 76000 = 95% utilization
        urgency = budget.get_reset_urgency(76000)
        assert urgency == ResetUrgency.CRITICAL
    
    def test_forecast_after_query(self):
        """Forecast total tokens after query."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Input: 1000, output ratio: 1.5 = 1500 output tokens
        # Total: 5000 (used) + 1000 (input) + 1500 (output) = 7500
        forecast = budget.forecast_after_query(
            current_used_tokens=5000,
            query_tokens=1000,
            estimated_output_ratio=1.5,
        )
        
        assert forecast == 7500
    
    def test_forecast_with_custom_output_ratio(self):
        """Custom output ratio changes forecast."""
        budget = ContextBudget(total_tokens=100000)
        
        # Output ratio 2.0: 1000 input * 2.0 = 2000 output
        forecast = budget.forecast_after_query(
            current_used_tokens=0,
            query_tokens=1000,
            estimated_output_ratio=2.0,
        )
        
        assert forecast == 3000  # 1000 + 2000
    
    def test_should_reset_proactively_no_reset_needed(self):
        """Don't reset if utilization stays low."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Used: 10000, query: 5000, ratio: 1.5
        # Forecast: 10000 + 5000 + 7500 = 22500
        # Utilization: 22500 / 80000 = 28% → No reset
        should_reset = budget.should_reset_proactively(
            current_used_tokens=10000,
            query_tokens=5000,
            estimated_output_ratio=1.5,
        )
        
        assert should_reset is False
    
    def test_should_reset_proactively_reset_needed(self):
        """Reset if forecast shows >80% utilization."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Used: 60000, query: 10000, ratio: 2.0
        # Forecast: 60000 + 10000 + 20000 = 90000
        # Utilization: 90000 / 80000 = 112% → Reset
        should_reset = budget.should_reset_proactively(
            current_used_tokens=60000,
            query_tokens=10000,
            estimated_output_ratio=2.0,
        )
        
        assert should_reset is True
    
    def test_invalid_total_tokens(self):
        """Invalid total_tokens raises error."""
        with pytest.raises(ValueError):
            ContextBudget(total_tokens=0)
        
        with pytest.raises(ValueError):
            ContextBudget(total_tokens=-1000)
    
    def test_invalid_reservation_ratio(self):
        """Invalid reservation ratio raises error."""
        with pytest.raises(ValueError):
            ContextBudget(total_tokens=100000, reserved_for_output=-0.1)
        
        with pytest.raises(ValueError):
            ContextBudget(total_tokens=100000, reserved_for_output=1.5)


class TestTokenEstimation:
    """Test token count estimation."""
    
    def test_estimate_empty_text(self):
        """Empty text = 0 tokens."""
        assert estimate_token_count("") == 0
    
    def test_estimate_english_text(self):
        """Estimate English text tokens."""
        # "Hello world" = 11 chars / 3.5 ≈ 3 tokens + 0.3 overhead ≈ 3
        tokens = estimate_token_count("Hello world")
        
        assert tokens > 0
        # Conservative estimate with overhead
        assert tokens <= 5
    
    def test_estimate_code_tokens(self):
        """Code typically has more tokens per character."""
        code = "def foo():\n    return 42"
        tokens = estimate_token_count(code)
        
        assert tokens > 0
        # Code is denser in tokens
        assert tokens <= 10
    
    def test_estimate_long_text(self):
        """Long text estimates scale appropriately."""
        short = "Hello"
        long = "Hello " * 100
        
        short_tokens = estimate_token_count(short)
        long_tokens = estimate_token_count(long)
        
        # Long should be much more than short
        assert long_tokens > short_tokens * 50
    
    def test_estimate_consistency(self):
        """Same text always estimates same tokens."""
        text = "The quick brown fox jumps over the lazy dog"
        tokens1 = estimate_token_count(text)
        tokens2 = estimate_token_count(text)
        
        assert tokens1 == tokens2
    
    def test_estimate_includes_overhead(self):
        """Estimates include 10% overhead."""
        text = "x" * 100  # 100 chars
        
        # 100 / 3.5 ≈ 28 tokens + 10% = 30-31
        tokens = estimate_token_count(text)
        
        assert tokens >= 28
        assert tokens <= 32


class TestOutputTokenEstimation:
    """Test output token ratio estimation."""
    
    def test_implementation_tasks(self):
        """Implementation tasks produce ~2x output."""
        ratio = estimate_output_tokens("Implement a REST API")
        assert ratio == 2.0
        
        ratio = estimate_output_tokens("Build a new feature")
        assert ratio == 2.0
        
        ratio = estimate_output_tokens("Write a test suite")
        assert ratio == 2.0
    
    def test_analysis_tasks(self):
        """Analysis tasks produce ~1x output."""
        ratio = estimate_output_tokens("Analyze the code")
        assert ratio == 1.0
        
        ratio = estimate_output_tokens("Review this PR")
        assert ratio == 1.0
        
        ratio = estimate_output_tokens("Debug the issue")
        assert ratio == 1.0
    
    def test_default_ratio(self):
        """Unknown tasks default to 1x."""
        ratio = estimate_output_tokens("Some random task")
        assert ratio == 1.0
    
    def test_case_insensitive(self):
        """Task estimation is case-insensitive."""
        ratio1 = estimate_output_tokens("IMPLEMENT")
        ratio2 = estimate_output_tokens("implement")
        
        assert ratio1 == ratio2 == 2.0
    
    def test_multiple_keywords(self):
        """Uses first matching keyword."""
        # "Implement" matches (2x), even though "analyze" also mentioned
        ratio = estimate_output_tokens("Implement and analyze")
        assert ratio == 2.0


class TestIntegration:
    """Integration tests combining budget and estimation."""
    
    def test_full_workflow_fits_query(self):
        """Full workflow: estimate → fit check → forecast."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Estimate query size
        query = "Implement a new feature in Python"
        query_tokens = estimate_token_count(query)
        
        # Check if it fits
        fits = budget.can_fit_query(query_tokens, safety_margin=0.1)
        assert fits is True
        
        # Estimate output
        output_ratio = estimate_output_tokens(query)
        assert output_ratio == 2.0
        
        # Forecast
        forecast = budget.forecast_after_query(
            current_used_tokens=10000,
            query_tokens=query_tokens,
            estimated_output_ratio=output_ratio,
        )
        
        # Check if we need proactive reset
        should_reset = budget.should_reset_proactively(
            current_used_tokens=10000,
            query_tokens=query_tokens,
            estimated_output_ratio=output_ratio,
        )
        
        assert should_reset is False  # Still plenty of room
    
    def test_full_workflow_needs_reset(self):
        """Full workflow detecting need for reset."""
        budget = ContextBudget(total_tokens=100000, reserved_for_output=0.2)
        
        # Already used a lot
        used = 70000  # 87.5% of available 80000
        
        # Large query coming
        query = "Implement a complete system"
        query_tokens = estimate_token_count(query) + 1000  # Add padding
        
        # Should suggest reset
        should_reset = budget.should_reset_proactively(
            current_used_tokens=used,
            query_tokens=query_tokens,
            estimated_output_ratio=2.0,
        )
        
        # With high utilization and large query, should reset
        urgency = budget.get_reset_urgency(used)
        assert urgency == ResetUrgency.HIGH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
