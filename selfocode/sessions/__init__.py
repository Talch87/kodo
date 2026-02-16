"""Session adapters for selfocode."""

from selfocode.sessions.base import QueryResult, Session, SessionStats
from selfocode.sessions.claude import ClaudeSession
from selfocode.sessions.cursor import CursorSession

__all__ = ["QueryResult", "Session", "SessionStats", "ClaudeSession", "CursorSession"]
