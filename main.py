"""Legacy entry point — delegates to kodo.cli.main().

Use the ``kodo`` CLI instead::

    kodo ./project --goal-file goal.md --mode saga --max-cycles 3 --yes
"""

import sys
import warnings


def main() -> None:
    warnings.warn(
        "main.py is deprecated. Use the `kodo` CLI with --goal-file and --yes flags.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Map old positional args to new CLI flags:
    #   old: python main.py goal.md ./project [--mode ...] [--max-cycles ...]
    #   new: kodo ./project --goal-file goal.md [--mode ...] --yes
    old_argv = sys.argv[:]
    if len(old_argv) >= 3 and not old_argv[1].startswith("-"):
        goal_file = old_argv[1]
        project_dir = old_argv[2]
        rest = old_argv[3:]
        sys.argv = [old_argv[0], project_dir, "--goal-file", goal_file, "--yes"] + rest

    from kodo.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
