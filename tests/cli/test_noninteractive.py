"""Tests for non-interactive CLI mode."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import make_scripted_session
from kodo.cli import (
    _build_params_from_flags,
    run_intake_noninteractive,
    _main_inner,
)
from kodo.log import RunDir


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Temporary project directory."""
    return tmp_path


def _make_args(**overrides) -> Namespace:
    """Create an argparse Namespace with defaults for non-interactive mode."""
    defaults = dict(
        goal="Build something",
        goal_file=None,
        mode=None,
        exchanges=None,
        cycles=None,
        orchestrator=None,
        orchestrator_model=None,
        budget=None,
        skip_intake=False,
        resume=None,
        project_dir=".",
    )
    defaults.update(overrides)
    return Namespace(**defaults)


# ---------------------------------------------------------------------------
# TestBuildParamsFromFlags
# ---------------------------------------------------------------------------


class TestBuildParamsFromFlags:
    @pytest.fixture(autouse=True)
    def _fake_backends(self):
        with (
            patch("kodo.cli.has_claude", return_value=True),
            patch("kodo.cli.check_api_key", return_value=None),
        ):
            yield

    def test_defaults_to_saga_mode(self, project):
        args = _make_args()
        params = _build_params_from_flags(args, project)
        assert params["mode"] == "saga"

    def test_explicit_mode(self, project):
        args = _make_args(mode="mission")
        params = _build_params_from_flags(args, project)
        assert params["mode"] == "mission"

    def test_exchanges_falls_back_to_mode_default(self, project):
        args = _make_args()
        params = _build_params_from_flags(args, project)
        assert params["max_exchanges"] == 30  # saga default

    def test_exchanges_override(self, project):
        args = _make_args(exchanges=50)
        params = _build_params_from_flags(args, project)
        assert params["max_exchanges"] == 50

    def test_cycles_falls_back_to_mode_default(self, project):
        args = _make_args()
        params = _build_params_from_flags(args, project)
        assert params["max_cycles"] == 5  # saga default

    def test_mission_mode_defaults(self, project):
        args = _make_args(mode="mission")
        params = _build_params_from_flags(args, project)
        assert params["max_exchanges"] == 20
        assert params["max_cycles"] == 1

    def test_orchestrator_auto_detects_api_for_gemini(self, project):
        args = _make_args(orchestrator_model="gemini-flash")
        params = _build_params_from_flags(args, project)
        assert params["orchestrator"] == "api"

    def test_orchestrator_explicit(self, project):
        args = _make_args(orchestrator="api", orchestrator_model="opus")
        params = _build_params_from_flags(args, project)
        assert params["orchestrator"] == "api"

    def test_budget_none_by_default(self, project):
        args = _make_args()
        params = _build_params_from_flags(args, project)
        assert params["budget_per_step"] is None

    def test_budget_explicit(self, project):
        args = _make_args(budget=5.0)
        params = _build_params_from_flags(args, project)
        assert params["budget_per_step"] == 5.0

    def test_saves_config_to_disk(self, project):
        args = _make_args()
        _build_params_from_flags(args, project)
        config_path = project / ".kodo" / "config.json"
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["mode"] == "saga"

    def test_api_key_validation_exits(self, project):
        args = _make_args(orchestrator="api", orchestrator_model="opus")
        with patch("kodo.cli.check_api_key", return_value="ANTHROPIC_API_KEY not set"):
            with pytest.raises(SystemExit):
                _build_params_from_flags(args, project)


# ---------------------------------------------------------------------------
# TestNonInteractiveGoalInput
# ---------------------------------------------------------------------------


class TestNonInteractiveGoalInput:
    @pytest.fixture(autouse=True)
    def _fake_backends(self):
        with (
            patch("kodo.cli.has_claude", return_value=True),
            patch("kodo.cli.check_api_key", return_value=None),
        ):
            yield

    def test_inline_goal(self, project):
        """--goal 'text' passes goal_text correctly through to launch."""
        with (
            patch("kodo.cli.launch_run") as mock_launch,
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal", "Build a web app", str(project)]
            _main_inner()
            goal_arg = mock_launch.call_args[0][1]
            assert goal_arg == "Build a web app"

    def test_goal_file(self, project):
        """--goal-file reads from the file."""
        goal_file = project / "my-goal.md"
        goal_file.write_text("Build an API server")

        with (
            patch("kodo.cli.launch_run") as mock_launch,
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = ["kodo", "--goal-file", str(goal_file), str(project)]
            _main_inner()
            goal_arg = mock_launch.call_args[0][1]
            assert goal_arg == "Build an API server"

    def test_goal_file_not_found(self, project):
        with pytest.raises(SystemExit):
            sys.argv = [
                "kodo",
                "--goal-file",
                str(project / "nonexistent.md"),
                str(project),
            ]
            _main_inner()

    def test_goal_file_empty(self, project):
        goal_file = project / "empty.md"
        goal_file.write_text("   ")

        with pytest.raises(SystemExit):
            sys.argv = ["kodo", "--goal-file", str(goal_file), str(project)]
            _main_inner()

    def test_goal_and_goal_file_mutually_exclusive(self):
        """argparse should reject both --goal and --goal-file."""
        with pytest.raises(SystemExit):
            sys.argv = ["kodo", "--goal", "X", "--goal-file", "y.md"]
            _main_inner()


# ---------------------------------------------------------------------------
# TestRunIntakeNoninteractive
# ---------------------------------------------------------------------------


class TestRunIntakeNoninteractive:
    def test_produces_plan_in_one_query(self, project):
        run_dir = RunDir.create(project, "test")
        plan_json = json.dumps(
            {
                "context": "Test",
                "stages": [
                    {
                        "index": 1,
                        "name": "S1",
                        "description": "Do it",
                        "acceptance_criteria": "Done",
                        "browser_testing": False,
                    }
                ],
            }
        )
        session = make_scripted_session(
            ["Plan written."],
            project,
            write_file={
                "on_query": 0,
                "path": str(run_dir.goal_plan_file),
                "content": plan_json,
            },
        )

        with (
            patch("kodo.cli.make_session", return_value=session),
            patch("kodo.cli.has_claude", return_value=True),
        ):
            result = run_intake_noninteractive(run_dir, "Build something")

        assert result is not None
        assert len(result.stages) == 1
        assert session.stats.queries == 1

    def test_finalize_fallback(self, project):
        """If first query doesn't produce file, sends finalize query."""
        run_dir = RunDir.create(project, "test")
        plan_json = json.dumps(
            {
                "context": "Test",
                "stages": [
                    {
                        "index": 1,
                        "name": "S1",
                        "description": "Do it",
                        "acceptance_criteria": "Done",
                        "browser_testing": False,
                    }
                ],
            }
        )
        session = make_scripted_session(
            ["Analyzing...", "Plan written."],
            project,
            write_file={
                "on_query": 1,
                "path": str(run_dir.goal_plan_file),
                "content": plan_json,
            },
        )

        with (
            patch("kodo.cli.make_session", return_value=session),
            patch("kodo.cli.has_claude", return_value=True),
        ):
            result = run_intake_noninteractive(run_dir, "Build something")

        assert result is not None
        assert session.stats.queries == 2

    def test_returns_none_when_no_file_written(self, project):
        run_dir = RunDir.create(project, "test")
        session = make_scripted_session(["Hmm.", "Still nothing."], project)

        with (
            patch("kodo.cli.make_session", return_value=session),
            patch("kodo.cli.has_claude", return_value=True),
        ):
            result = run_intake_noninteractive(run_dir, "Vague goal")

        assert result is None

    def test_returns_none_when_no_backend(self, project):
        run_dir = RunDir.create(project, "test")
        with (
            patch("kodo.cli.has_claude", return_value=False),
            patch("kodo.cli.has_cursor", return_value=False),
        ):
            result = run_intake_noninteractive(run_dir, "Build something")

        assert result is None

    def test_no_input_calls(self, project):
        """Non-interactive intake must never call input()."""
        run_dir = RunDir.create(project, "test")
        session = make_scripted_session(["Done."], project)

        with (
            patch("kodo.cli.make_session", return_value=session),
            patch("kodo.cli.has_claude", return_value=True),
            patch("builtins.input", side_effect=AssertionError("input() called")),
        ):
            run_intake_noninteractive(run_dir, "Build something")


# ---------------------------------------------------------------------------
# TestNonInteractiveEndToEnd
# ---------------------------------------------------------------------------


class TestNonInteractiveEndToEnd:
    @pytest.fixture(autouse=True)
    def _fake_backends(self):
        with (
            patch("kodo.cli.has_claude", return_value=True),
            patch("kodo.cli.check_api_key", return_value=None),
        ):
            yield

    def test_no_interactive_prompts(self, project):
        """The full non-interactive flow must never call input() or questionary."""
        with (
            patch("kodo.cli.launch_run") as mock_launch,
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
            patch(
                "builtins.input",
                side_effect=AssertionError("input() should not be called"),
            ),
            patch(
                "questionary.select",
                side_effect=AssertionError("questionary should not be called"),
            ),
        ):
            sys.argv = ["kodo", "--goal", "Build X", str(project)]
            _main_inner()
            mock_launch.assert_called_once()

    def test_params_passed_through(self, project):
        """CLI flags should be reflected in the params passed to launch_run."""
        with (
            patch("kodo.cli.launch_run") as mock_launch,
            patch("kodo.cli.run_intake_noninteractive", return_value=None),
        ):
            sys.argv = [
                "kodo",
                "--goal",
                "Build X",
                "--mode",
                "mission",
                "--exchanges",
                "42",
                "--cycles",
                "7",
                "--orchestrator",
                "api",
                "--orchestrator-model",
                "gemini-pro",
                "--budget",
                "3.50",
                str(project),
            ]
            _main_inner()

            params = mock_launch.call_args[0][2]
            assert params["mode"] == "mission"
            assert params["max_exchanges"] == 42
            assert params["max_cycles"] == 7
            assert params["orchestrator"] == "api"
            assert params["orchestrator_model"] == "gemini-pro"
            assert params["budget_per_step"] == 3.50

    def test_skip_intake_flag(self, project):
        """--skip-intake should prevent intake from running."""
        with (
            patch("kodo.cli.launch_run"),
            patch("kodo.cli.run_intake_noninteractive") as mock_intake,
        ):
            sys.argv = [
                "kodo",
                "--goal",
                "Simple fix",
                "--skip-intake",
                str(project),
            ]
            _main_inner()
            mock_intake.assert_not_called()

    def test_resume_with_goal_errors(self):
        """--resume + --goal should be rejected."""
        with pytest.raises(SystemExit):
            sys.argv = ["kodo", "--resume", "--goal", "Build X"]
            _main_inner()

    def test_uses_existing_goal_plan(self, project):
        """If goal-plan.json exists in the run dir, non-interactive mode uses it."""
        plan = {
            "context": "Test",
            "stages": [
                {
                    "index": 1,
                    "name": "Stage 1",
                    "description": "Do it",
                    "acceptance_criteria": "Done",
                    "browser_testing": False,
                }
            ],
        }

        # Patch RunDir.create so we can pre-populate the goal plan file
        original_create = RunDir.create

        def create_with_plan(project_dir, run_id=None):
            rd = original_create(project_dir, run_id)
            rd.goal_plan_file.write_text(json.dumps(plan))
            return rd

        with (
            patch("kodo.cli.launch_run") as mock_launch,
            patch("kodo.cli.run_intake_noninteractive") as mock_intake,
            patch("kodo.cli.RunDir.create", side_effect=create_with_plan),
        ):
            sys.argv = ["kodo", "--goal", "Build X", str(project)]
            _main_inner()
            # Should use existing plan, not run intake
            mock_intake.assert_not_called()
            launched_plan = (
                mock_launch.call_args.kwargs.get("plan") or mock_launch.call_args[0][3]
            )
            assert len(launched_plan.stages) == 1
