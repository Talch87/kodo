"""Tests for --json and --yes CLI flags (structured output for automation).

These flags allow kodo to be invoked by other programs (CI, agents, scripts)
and get machine-readable output without any interactive prompts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from kodo.cli import _main_inner, launch_run
from kodo.factory import Mode
from kodo.log import RunDir
from kodo.orchestrators.base import RunResult, CycleResult


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _fake_launch(
    run_dir, goal_text, params, plan=None, json_mode=False, auto_refine=False
):
    """Fake launch_run that returns a successful RunResult."""
    return RunResult(
        cycles=[
            CycleResult(
                exchanges=5, total_cost_usd=0.01, finished=True, summary="All done"
            )
        ],
    )


def _fake_launch_partial(
    run_dir, goal_text, params, plan=None, json_mode=False, auto_refine=False
):
    """Fake launch_run that returns a partial RunResult."""
    return RunResult(
        cycles=[
            CycleResult(
                exchanges=5,
                total_cost_usd=0.01,
                finished=False,
                summary="Ran out of time",
            )
        ],
    )


# ---------------------------------------------------------------------------
# --json: structured JSON output on stdout
# ---------------------------------------------------------------------------


class TestJsonOutput:
    @pytest.fixture(autouse=True)
    def _fake_backends(self):
        with (
            patch("kodo.cli.has_claude", return_value=True),
            patch("kodo.cli.check_api_key", return_value=None),
        ):
            yield

    def test_json_flag_accepted(self, project):
        """The --json flag should be recognized by argparse."""
        with (
            patch("kodo.cli.launch_run", side_effect=_fake_launch),
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal", "Build X", "--json", str(project)]
            try:
                _main_inner()
            except SystemExit:
                pass  # exit code is fine, we just need no argparse error

    def test_json_outputs_valid_json(self, project, capsys):
        """--json should print a parseable JSON object to stdout."""
        with (
            patch("kodo.cli.launch_run", side_effect=_fake_launch),
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal", "Build X", "--json", str(project)]
            try:
                _main_inner()
            except SystemExit:
                pass

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "completed"
        assert output["finished"] is True
        assert "summary" in output

    def test_json_partial_status(self, project, capsys):
        """Unfinished run should report status=partial in JSON."""
        with (
            patch("kodo.cli.launch_run", side_effect=_fake_launch_partial),
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal", "Build X", "--json", str(project)]
            try:
                _main_inner()
            except SystemExit:
                pass

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "partial"
        assert output["finished"] is False

    def test_json_no_input_calls(self, project):
        """--json must never call input() or questionary."""
        with (
            patch("kodo.cli.launch_run", side_effect=_fake_launch),
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
            patch(
                "builtins.input",
                side_effect=AssertionError("input() called in --json mode"),
            ),
        ):
            sys.argv = ["kodo", "--goal", "Build X", "--json", str(project)]
            try:
                _main_inner()
            except SystemExit:
                pass

    def test_json_error_output(self, project, capsys):
        """Errors in --json mode should produce JSON with status=error."""
        sys.argv = [
            "kodo",
            "--goal-file",
            str(project / "nonexistent.md"),
            "--json",
            str(project),
        ]
        try:
            _main_inner()
        except SystemExit:
            pass

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "error"
        assert output["error"]

    def test_json_includes_cost_and_exchanges(self, project, capsys):
        """JSON output should include exchanges and cost."""
        with (
            patch("kodo.cli.launch_run", side_effect=_fake_launch),
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal", "Build X", "--json", str(project)]
            try:
                _main_inner()
            except SystemExit:
                pass

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "exchanges" in output
        assert "cost_usd" in output


# ---------------------------------------------------------------------------
# launch_run must return RunResult (prerequisite for --json)
# ---------------------------------------------------------------------------


class TestLaunchRunReturnsResult:
    def test_returns_run_result(self, project):
        """launch_run should return the RunResult, not None."""
        from tests.conftest import FakeSession
        from kodo.agent import Agent

        run_dir = RunDir.create(project, "test")

        fake_result = RunResult(
            cycles=[CycleResult(exchanges=3, total_cost_usd=0.0, finished=True)],
        )

        fake_team = {"worker": Agent(FakeSession(), "test worker")}

        fake_mode = Mode(
            name="saga",
            description="test",
            system_prompt="test",
            build_team=lambda _budget: fake_team,
            default_max_exchanges=30,
            default_max_cycles=5,
        )

        with (
            patch("kodo.cli.build_orchestrator") as mock_orch,
            patch("kodo.cli.load_team_config", return_value=None),
            patch("kodo.cli.get_mode", return_value=fake_mode),
        ):
            mock_orch.return_value.run.return_value = fake_result
            mock_orch.return_value.model = "test"

            result = launch_run(
                run_dir,
                "Build X",
                {
                    "mode": "saga",
                    "orchestrator": "claude-code",
                    "orchestrator_model": "opus",
                    "max_exchanges": 10,
                    "max_cycles": 1,
                    "budget_per_step": None,
                },
            )

        assert result is not None
        assert result.finished is True
