"""Terminal UI primitives — spinners, ANSI formatting, selection menus."""

import sys
import threading
import time

import questionary


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RESET = "\033[0m"

_BACKEND_LABELS = {
    "ClaudeSession": "claude code",
    "CursorSession": "cursor",
    "CodexSession": "codex",
    "GeminiCliSession": "gemini cli",
}


def backend_label(agent) -> str:
    return _BACKEND_LABELS.get(type(agent.session).__name__, "?")


def print_agent(text: str, turns: int = 0) -> None:
    """Print an agent response with a visible left-border."""
    if not text.strip():
        if turns:
            print(
                f"\n  {DIM}(agent completed {turns} turn(s) — check output files){RESET}\n"
            )
        else:
            print(f"\n  {DIM}(no text response){RESET}\n")
        return
    lines = text.rstrip().splitlines()
    print()
    for line in lines:
        print(f"  {DIM}{CYAN}│{RESET} {line}")
    print()


def print_separator() -> None:
    print(f"  {DIM}{'─' * 60}{RESET}")


class Spinner:
    """Simple elapsed-time spinner for long-running operations."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking"):
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
        # Clear the spinner line
        print(f"\r{' ' * 60}\r", end="", flush=True)

    def _run(self):
        start = time.monotonic()
        i = 0
        while not self._stop.wait(0.1):
            elapsed = int(time.monotonic() - start)
            frame = self.FRAMES[i % len(self.FRAMES)]
            print(f"\r  {frame} {self._message}... {elapsed}s", end="", flush=True)
            i += 1


def labeled_choices(options: list[str], default_index: int) -> list[questionary.Choice]:
    """Build Choice objects, appending '(default)' to the default item's label."""
    choices = []
    for i, opt in enumerate(options):
        label = f"{opt} (default)" if i == default_index else opt
        choices.append(questionary.Choice(title=label, value=opt))
    return choices


def select_one(title: str, options: list[str], default_index: int = 0) -> str:
    """Arrow-key single selection. Returns the chosen string."""
    choices = labeled_choices(options, default_index)
    result = questionary.select(title, choices=choices).ask()
    if result is None:
        print("Cancelled.")
        sys.exit(1)
    return result


def select_numeric(
    title: str, presets: list[str], default_index: int = 0, type_fn: type = int
) -> str:
    """Arrow-key selection with a 'Custom...' option for numeric values."""
    all_options = presets + ["Custom..."]
    choices = labeled_choices(all_options, default_index)
    result = questionary.select(title, choices=choices).ask()
    if result is None:
        print("Cancelled.")
        sys.exit(1)
    if result != "Custom...":
        return result
    while True:
        raw = questionary.text("  Enter value:").ask()
        if raw is None:
            print("Cancelled.")
            sys.exit(1)
        raw = raw.strip()
        try:
            type_fn(raw)
            return raw
        except (ValueError, TypeError):
            print(f"  Invalid input. Expected {type_fn.__name__}.")
