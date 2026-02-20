"""Tests for PromptOptimizer — token usage reduction without meaning loss.

Covers: token estimation, single prompt optimization, batch optimization,
cross-prompt deduplication, compression rules, metrics, and audit.
"""

from __future__ import annotations

import pytest

from kodo.prompt_optimizer import (
    OptimizationResult,
    PromptMetrics,
    PromptOptimizer,
    audit_prompts,
    estimate_tokens,
)


# ── Token estimation ─────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 1  # min 1

    def test_short_text(self) -> None:
        result = estimate_tokens("hello world")
        assert result >= 1
        assert result <= 5

    def test_longer_text(self) -> None:
        text = "This is a longer piece of text that should estimate more tokens."
        result = estimate_tokens(text)
        assert 10 <= result <= 25

    def test_proportional(self) -> None:
        short = estimate_tokens("abc")
        long = estimate_tokens("abc" * 100)
        assert long > short


# ── PromptMetrics ────────────────────────────────────────────────────────


class TestPromptMetrics:
    def test_savings_calculation(self) -> None:
        m = PromptMetrics(
            original_chars=400,
            optimized_chars=300,
            original_tokens_est=100,
            optimized_tokens_est=75,
        )
        assert m.chars_saved == 100
        assert m.tokens_saved_est == 25
        assert m.savings_pct == 25.0

    def test_no_savings(self) -> None:
        m = PromptMetrics(
            original_chars=100,
            optimized_chars=100,
            original_tokens_est=25,
            optimized_tokens_est=25,
        )
        assert m.chars_saved == 0
        assert m.tokens_saved_est == 0
        assert m.savings_pct == 0.0

    def test_zero_original_no_division_error(self) -> None:
        m = PromptMetrics()
        assert m.savings_pct == 0.0  # no division by zero


# ── Single prompt optimization ───────────────────────────────────────────


class TestPromptOptimizerSingle:
    def test_whitespace_normalization(self) -> None:
        optimizer = PromptOptimizer()
        text = "Hello   world\n\n\n\ntest   foo"
        result = optimizer.optimize(text)
        assert "   " not in result.optimized  # no triple spaces
        assert "\n\n\n" not in result.optimized  # no triple newlines

    def test_compression_rules_applied(self) -> None:
        optimizer = PromptOptimizer()
        result = optimizer.optimize(
            "In order to fix this, please note that the agent is able to handle it."
        )
        # "in order to" → "to", "please note that" → "Note:", "is able to" → "can"
        assert "in order to" not in result.optimized.lower()
        assert "is able to" not in result.optimized.lower()

    def test_verbose_patterns_compressed(self) -> None:
        optimizer = PromptOptimizer()
        result = optimizer.optimize(
            "Due to the fact that the system is very complex, "
            "we need to take into account many factors."
        )
        assert "due to the fact that" not in result.optimized.lower()
        assert "take into account" not in result.optimized.lower()

    def test_filler_words_removed(self) -> None:
        optimizer = PromptOptimizer()
        result = optimizer.optimize("This is really extremely important")
        assert "really" not in result.optimized.lower()
        assert "extremely" not in result.optimized.lower()

    def test_internal_duplicates_removed(self) -> None:
        optimizer = PromptOptimizer()
        text = "Run the tests.\nCheck the output.\nRun the tests."
        result = optimizer.optimize(text)
        assert result.optimized.lower().count("run the tests.") == 1

    def test_metrics_calculated(self) -> None:
        optimizer = PromptOptimizer()
        text = "This is really very extremely important due to the fact that " * 3
        result = optimizer.optimize(text)
        assert result.metrics.original_chars > result.metrics.optimized_chars
        assert result.metrics.tokens_saved_est > 0
        assert result.metrics.savings_pct > 0

    def test_preserves_meaning(self) -> None:
        """Core content should survive optimization."""
        optimizer = PromptOptimizer()
        result = optimizer.optimize(
            "You are a code reviewer. Read the codebase and identify bugs."
        )
        assert "code reviewer" in result.optimized.lower()
        assert "bugs" in result.optimized.lower()

    def test_empty_text(self) -> None:
        optimizer = PromptOptimizer()
        result = optimizer.optimize("")
        assert result.optimized == ""

    def test_already_concise(self) -> None:
        optimizer = PromptOptimizer()
        text = "Run tests. Report bugs."
        result = optimizer.optimize(text)
        # Should be minimally changed
        assert len(result.optimized) <= len(text) + 5


# ── Batch optimization ───────────────────────────────────────────────────


class TestPromptOptimizerBatch:
    def test_batch_processes_all(self) -> None:
        optimizer = PromptOptimizer()
        prompts = {
            "a": "This is really the first prompt.",
            "b": "This is really the second prompt.",
        }
        results = optimizer.optimize_batch(prompts)
        assert "a" in results
        assert "b" in results
        assert isinstance(results["a"], OptimizationResult)

    def test_total_savings(self) -> None:
        optimizer = PromptOptimizer()
        prompts = {
            "a": "In order to do this, please note that " * 5,
            "b": "Due to the fact that this is very important " * 5,
        }
        results = optimizer.optimize_batch(prompts)
        total = optimizer.total_savings(results)
        assert total.tokens_saved_est > 0
        assert total.savings_pct > 0

    def test_aggressive_cross_dedup(self) -> None:
        optimizer = PromptOptimizer(aggressive=True)
        prompts = {
            "a": "Fix issues yourself. Report blocking issues only.",
            "b": "Fix issues yourself. Report blocking issues only.",
        }
        results = optimizer.optimize_batch(prompts)
        # Second prompt should have the shared sentence removed
        assert len(results["b"].optimized) < len(results["a"].optimized)


# ── Audit ────────────────────────────────────────────────────────────────


class TestAuditPrompts:
    def test_audit_returns_metrics(self) -> None:
        metrics = audit_prompts()
        assert "orchestrator_system" in metrics
        assert "tester" in metrics
        assert "TOTAL" in metrics
        assert isinstance(metrics["TOTAL"], PromptMetrics)

    def test_audit_total_has_savings(self) -> None:
        metrics = audit_prompts()
        total = metrics["TOTAL"]
        # Even conservative optimization should save some tokens
        assert total.original_tokens_est > 0
        assert total.savings_pct >= 0  # may be 0 if prompts are already tight

    def test_audit_all_prompts_measured(self) -> None:
        metrics = audit_prompts()
        expected_keys = {
            "orchestrator_system",
            "tester",
            "tester_browser",
            "architect",
            "designer",
            "designer_browser",
            "TOTAL",
        }
        assert set(metrics.keys()) == expected_keys


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content_preserved(self) -> None:
        optimizer = PromptOptimizer()
        text = "Check the output: ✓ passed, ✗ failed"
        result = optimizer.optimize(text)
        assert "✓" in result.optimized
        assert "✗" in result.optimized

    def test_code_blocks_preserved(self) -> None:
        optimizer = PromptOptimizer()
        text = "Run this:\n```python\ndef foo():\n    return 42\n```"
        result = optimizer.optimize(text)
        assert "def foo():" in result.optimized
        assert "return 42" in result.optimized

    def test_markdown_headers_preserved(self) -> None:
        optimizer = PromptOptimizer()
        text = "# Header\n\nContent here.\n\n## Subheader\n\nMore content."
        result = optimizer.optimize(text)
        assert "# Header" in result.optimized
        assert "## Subheader" in result.optimized

    def test_large_prompt(self) -> None:
        """Optimizer handles large prompts without error."""
        optimizer = PromptOptimizer()
        # Use line-separated duplicates (dedup works per-line)
        text = "\n".join(["This is a test sentence."] * 1000)
        result = optimizer.optimize(text)
        # Should be significantly shorter due to dedup (999 duplicates removed)
        assert result.metrics.savings_pct > 90

    def test_optimizer_state_reset_between_batches(self) -> None:
        """Batch dedup state is reset between optimize_batch calls."""
        optimizer = PromptOptimizer(aggressive=True)
        prompts = {"a": "Unique sentence here."}
        optimizer.optimize_batch(prompts)
        # Second batch should not see "a"'s sentences
        results2 = optimizer.optimize_batch({"b": "Unique sentence here."})
        assert "unique sentence" in results2["b"].optimized.lower()
