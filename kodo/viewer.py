"""Open a JSONL log file in the chat-style HTML viewer.

Usage: python -m kodo.viewer <logfile.jsonl>
   or: python -m kodo.viewer  (opens drag-and-drop page)
"""

from __future__ import annotations

import json
import sys
import tempfile
import webbrowser
from pathlib import Path

_VIEWER_HTML = Path(__file__).parent / "viewer.html"
_EMBED_MARKER = "/*__EMBED_MARKER__*/"


def open_viewer(log_path: Path | None = None) -> None:
    template = _VIEWER_HTML.read_text(encoding="utf-8")

    if log_path is not None:
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in lines]
        embed = f"EMBEDDED_DATA = {json.dumps(events)};"
        html = template.replace(_EMBED_MARKER, embed)
    else:
        html = template

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name

    url = Path(tmp).as_uri()
    webbrowser.open(url)
    print(f"Log viewer: {url}")


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        open_viewer(path)
    else:
        open_viewer()


if __name__ == "__main__":
    main()
