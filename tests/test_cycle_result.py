"""Tests for CycleResult and RunResult data classes."""

from __future__ import annotations

from selfocode.orchestrators.base import CycleResult, RunResult


class TestCycleResult:
    def test_defaults(self) -> None:
        cr = CycleResult()
        assert cr.exchanges == 0
        assert cr.finished is False
        assert cr.success is False
        assert cr.summary == ""
        assert cr.total_cost_usd == 0.0

    def test_finished_without_success(self) -> None:
        """BUG FIX: finished=True + success=False means the orchestrator gave up."""
        cr = CycleResult(finished=True, success=False, summary="Blocked on API key")
        assert cr.finished is True
        assert cr.success is False

    def test_finished_with_success(self) -> None:
        cr = CycleResult(finished=True, success=True, summary="All done")
        assert cr.finished is True
        assert cr.success is True


class TestRunResult:
    def test_empty_run(self) -> None:
        rr = RunResult()
        assert rr.total_exchanges == 0
        assert rr.total_cost_usd == 0.0
        assert rr.finished is False
        assert rr.summary == ""

    def test_finished_when_last_cycle_finished(self) -> None:
        rr = RunResult(
            cycles=[
                CycleResult(finished=False, summary="partial"),
                CycleResult(finished=True, summary="done"),
            ]
        )
        assert rr.finished is True
        assert rr.summary == "done"

    def test_not_finished_when_last_cycle_not_finished(self) -> None:
        rr = RunResult(
            cycles=[
                CycleResult(finished=True, summary="first"),
                CycleResult(finished=False, summary="ran out of turns"),
            ]
        )
        assert rr.finished is False

    def test_totals_sum_across_cycles(self) -> None:
        rr = RunResult(
            cycles=[
                CycleResult(exchanges=10, total_cost_usd=1.0),
                CycleResult(exchanges=5, total_cost_usd=0.5),
            ]
        )
        assert rr.total_exchanges == 15
        assert rr.total_cost_usd == 1.5
