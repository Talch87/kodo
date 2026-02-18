"""Tests for CycleResult and RunResult data classes."""

from __future__ import annotations

from kodo.orchestrators.base import CycleResult, RunResult


class TestRunResult:
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
