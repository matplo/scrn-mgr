"""scrn-mgr: GNU screen session manager (CLI, Textual TUI, MCP server)."""

from scrn_mgr.manager import ScreenSessionManager
from scrn_mgr.models import SessionRecord

__all__ = ["ScreenSessionManager", "SessionRecord"]

__version__ = "0.1.0"
