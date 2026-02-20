"""Tests for TaskRouter — task complexity scoring and agent routing.

Covers: complexity scoring, routing recommendations, routing history
tracking, statistics computation, and edge cases.
"""

from __future__ import annotations

import pytest

from kodo.orchestrators.base import TaskComplexity, TaskRouter


# ── TaskComplexity unit tests ────────────────────────────────────────────


class TestTaskComplexity:
    """TaskComplexity dataclass behavior."""

    def test_low_complexity(self) -> None:
        tc = TaskComplexity(score=0.1, recommended_agent="worker_fast", reasoning="simple")
        assert tc.level == "low"

    def test_medium_complexity(self) -> None:
        tc = TaskComplexity(score=0.5, recommended_agent="worker_smart", reasoning="medium")
        assert tc.level == "medium"

    def test_high_complexity(self) -> None:
        tc = TaskComplexity(score=0.9, recommended_agent="worker_smart", reasoning="complex")
        assert tc.level == "high"

    def test_boundary_low_medium(self) -> None:
        tc = TaskComplexity(score=0.3, recommended_agent="worker_smart", reasoning="boundary")
        assert tc.level == "medium"  # 0.3 is >= 0.3, so medium

    def test_boundary_medium_high(self) -> None:
        tc = TaskComplexity(score=0.7, recommended_agent="worker_smart", reasoning="boundary")
        assert tc.level == "high"  # 0.7 is >= 0.7, so high


# ── TaskRouter scoring tests ────────────────────────────────────────────


class TestTaskRouterScoring:
    """TaskRouter.score_task() returns correct complexity and routing."""

    def test_simple_typo_fix(self) -> None:
        router = TaskRouter()
        result = router.score_task("Fix typo in the README file")
        assert result.score < 0.4
        assert result.recommended_agent == "worker_fast"
        assert result.level == "low"

    def test_simple_rename(self) -> None:
        router = TaskRouter()
        result = router.score_task("Rename the getCwd function to getCurrentDirectory")
        assert result.recommended_agent == "worker_fast"

    def test_simple_add_comment(self) -> None:
        router = TaskRouter()
        result = router.score_task("Add comment to explain what the calculate function does")
        assert result.recommended_agent == "worker_fast"

    def test_complex_refactor(self) -> None:
        router = TaskRouter()
        result = router.score_task(
            "Refactor the authentication system across multiple files "
            "to use JWT tokens instead of session cookies"
        )
        assert result.score > 0.5
        assert result.recommended_agent == "worker_smart"

    def test_complex_debugging(self) -> None:
        router = TaskRouter()
        result = router.score_task(
            "Debug tricky race condition in the concurrent request handler"
        )
        assert result.score > 0.5
        assert result.recommended_agent == "worker_smart"

    def test_complex_performance(self) -> None:
        router = TaskRouter()
        result = router.score_task(
            "Performance optimization of the database query system"
        )
        assert result.score >= 0.5
        assert result.recommended_agent == "worker_smart"

    def test_architectural_review(self) -> None:
        router = TaskRouter()
        result = router.score_task(
            "Review and assess the codebase architecture for scalability issues. "
            "Survey the current design patterns and evaluate their effectiveness."
        )
        assert result.recommended_agent == "architect"

    def test_code_review(self) -> None:
        router = TaskRouter()
        result = router.score_task(
            "Review the recent changes and inspect the codebase for potential bugs"
        )
        assert result.recommended_agent == "architect"

    def test_medium_complexity_default(self) -> None:
        router = TaskRouter()
        result = router.score_task("Update the user profile page")
        # No strong signals in either direction — should be medium
        assert result.level == "medium"

    def test_straightforward_task(self) -> None:
        router = TaskRouter()
        result = router.score_task("Make a simple, straightforward change to the config")
        assert result.score < 0.4

    def test_memory_leak(self) -> None:
        router = TaskRouter()
        result = router.score_task("Fix memory leak in the event handler")
        assert result.score > 0.5
        assert result.recommended_agent == "worker_smart"

    def test_migration_task(self) -> None:
        router = TaskRouter()
        result = router.score_task("Migrate the database schema from v2 to v3")
        assert result.score > 0.5
        assert result.recommended_agent == "worker_smart"

    def test_security_audit(self) -> None:
        router = TaskRouter()
        result = router.score_task("Security audit of the authentication module")
        assert result.score > 0.5

    def test_long_task_more_complex(self) -> None:
        """Longer task descriptions get a small complexity boost."""
        router = TaskRouter()
        short = router.score_task("fix bug")
        long = router.score_task(
            "Fix the complex bug in the authentication system that causes "
            "intermittent failures when multiple users attempt to log in "
            "simultaneously through the OAuth2 flow. The issue manifests "
            "as race conditions between the session store and the token "
            "refresh mechanism, leading to corrupted session state. We need "
            "to implement proper locking around the critical sections "
            "and ensure that the token refresh is atomic across all "
            "concurrent requests. Additionally, add comprehensive logging "
            "to trace the exact sequence of events during failure scenarios."
        )
        assert long.score > short.score

    def test_score_clamped_to_bounds(self) -> None:
        """Score should never exceed [0, 1]."""
        router = TaskRouter()
        # Many high-complexity keywords
        result = router.score_task(
            "Refactor and redesign the complex architecture with migration "
            "while debugging tricky performance optimization and fixing "
            "race condition deadlock memory leak concurrency issues"
        )
        assert 0.0 <= result.score <= 1.0

        # Many low-complexity keywords
        result2 = router.score_task(
            "Simple straightforward trivial one-line quick fix "
            "rename and add comment and change text and update string"
        )
        assert 0.0 <= result2.score <= 1.0


# ── TaskRouter routing history tests ─────────────────────────────────────


class TestTaskRouterHistory:
    """TaskRouter routing history and statistics."""

    def test_empty_history(self) -> None:
        router = TaskRouter()
        stats = router.routing_stats
        assert stats["total_tasks"] == 0
        assert stats["first_try_success_rate"] == 0.0

    def test_record_single_success(self) -> None:
        router = TaskRouter()
        router.record_routing("fix typo", "worker_fast", "worker_fast", success=True)
        stats = router.routing_stats
        assert stats["total_tasks"] == 1
        assert stats["first_try_success_rate"] == 1.0
        assert stats["recommendation_follow_rate"] == 1.0
        assert stats["followed_and_succeeded_rate"] == 1.0

    def test_record_single_failure(self) -> None:
        router = TaskRouter()
        router.record_routing("fix bug", "worker_fast", "worker_fast", success=False)
        stats = router.routing_stats
        assert stats["total_tasks"] == 1
        assert stats["first_try_success_rate"] == 0.0

    def test_recommendation_not_followed(self) -> None:
        router = TaskRouter()
        router.record_routing("refactor", "worker_smart", "worker_fast", success=False)
        stats = router.routing_stats
        assert stats["recommendation_follow_rate"] == 0.0
        assert stats["followed_and_succeeded_rate"] == 0.0

    def test_mixed_history(self) -> None:
        router = TaskRouter()
        # 4 tasks: 3 followed recommendation, 3 successes
        router.record_routing("fix typo", "worker_fast", "worker_fast", success=True)
        router.record_routing("refactor", "worker_smart", "worker_smart", success=True)
        router.record_routing("review", "architect", "architect", success=True)
        router.record_routing("complex debug", "worker_smart", "worker_fast", success=False)

        stats = router.routing_stats
        assert stats["total_tasks"] == 4
        assert stats["first_try_success_rate"] == 0.75
        assert stats["recommendation_follow_rate"] == 0.75
        assert stats["followed_and_succeeded_rate"] == 1.0  # 3/3 followed succeeded

    def test_high_success_rate_scenario(self) -> None:
        """Simulates the target: 95%+ first-try success rate."""
        router = TaskRouter()
        # 20 tasks, 19 succeed
        for i in range(19):
            router.record_routing(f"task {i}", "worker_smart", "worker_smart", success=True)
        router.record_routing("failed task", "worker_smart", "worker_smart", success=False)

        stats = router.routing_stats
        assert stats["first_try_success_rate"] == 0.95
        assert stats["total_tasks"] == 20

    def test_routing_history_preserved(self) -> None:
        """Verify that individual routing records are stored."""
        router = TaskRouter()
        router.record_routing("task A", "worker_fast", "worker_fast", success=True)
        router.record_routing("task B", "worker_smart", "worker_smart", success=True)

        assert len(router._routing_history) == 2
        assert router._routing_history[0]["task_summary"] == "task A"
        assert router._routing_history[1]["recommended"] == "worker_smart"


# ── Integration: score_task + record_routing workflow ────────────────────


class TestTaskRouterWorkflow:
    """End-to-end routing workflow: score → route → record → stats."""

    def test_full_workflow(self) -> None:
        router = TaskRouter()

        # Score a simple task
        simple = router.score_task("Fix typo in README")
        assert simple.recommended_agent == "worker_fast"

        # Route to recommended agent, succeeds
        router.record_routing(
            "Fix typo in README",
            simple.recommended_agent,
            simple.recommended_agent,  # followed recommendation
            success=True,
        )

        # Score a complex task
        complex_t = router.score_task(
            "Refactor the authentication across multiple files"
        )
        assert complex_t.recommended_agent == "worker_smart"

        # Route to recommended agent, succeeds
        router.record_routing(
            "Refactor auth",
            complex_t.recommended_agent,
            complex_t.recommended_agent,
            success=True,
        )

        # Score an architectural task
        arch = router.score_task(
            "Survey and review the codebase architecture, "
            "evaluate design patterns and assess scalability"
        )
        assert arch.recommended_agent == "architect"

        # Route to recommended agent, succeeds
        router.record_routing(
            "Arch review",
            arch.recommended_agent,
            arch.recommended_agent,
            success=True,
        )

        # All 3 tasks followed recommendation and succeeded
        stats = router.routing_stats
        assert stats["total_tasks"] == 3
        assert stats["first_try_success_rate"] == 1.0
        assert stats["recommendation_follow_rate"] == 1.0
        assert stats["followed_and_succeeded_rate"] == 1.0
