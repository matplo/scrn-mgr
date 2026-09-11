"""MCP server exposing scrn_mgr sessions to AI assistants (stdio transport).

Every tool here is non-interactive by construction, which is what makes it
safe to expose over MCP: a session's host is already recorded in the
registry at creation time (`new_session`), so later calls (send/capture/
kill/cleanup) don't need a host argument -- they look it up themselves and
reach it over SSH transparently if it's remote. The one operation that is
*not* exposed is interactive `attach`: it needs to take over a real
terminal/PTY for the life of the session, which doesn't fit a single MCP
tool call/response -- that stays a CLI (`scrn-mgr attach NAME`) or TUI-only
action.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from scrn_mgr.manager import ScreenSessionManager
from scrn_mgr.models import SessionRecord

mcp = FastMCP("scrn-mgr")


def _manager() -> ScreenSessionManager:
    return ScreenSessionManager()


def _record_to_dict(r: SessionRecord) -> dict:
    return {
        "name": r.name,
        "host": str(r.host),
        "status": r.status,
        "tracked": r.tracked,
        "pid": r.pid,
        "created_at": r.created_at,
        "notes": r.notes,
    }


@mcp.tool()
def list_sessions(all_sessions: bool = False) -> list[dict]:
    """List known screen sessions, local and remote. Set all_sessions=True to
    also include dead/stale and untracked (live but unregistered) sessions."""
    return [_record_to_dict(r) for r in _manager().list_sessions(all_sessions=all_sessions)]


@mcp.tool()
def new_session(name: str, host: str | None = None, cwd: str | None = None) -> dict:
    """Create a new detached session. host is `[user@]hostname[:port]` for a
    remote node over SSH, or omitted/None for the local machine."""
    return _record_to_dict(_manager().new_session(name, host=host, cwd=cwd))


@mcp.tool()
def send_command(name: str, cmd: str) -> str:
    """Send one command line to an existing session, as if typed + Enter."""
    _manager().send_command(name, cmd)
    return f"sent to {name!r}"


@mcp.tool()
def send_commands(name: str, cmds: list[str]) -> str:
    """Send multiple command lines to an existing session, in order."""
    _manager().send_commands(name, cmds)
    return f"sent {len(cmds)} command(s) to {name!r}"


@mcp.tool()
def send_file(name: str, path: str) -> str:
    """Send each line of a local file to an existing session, in order."""
    _manager().send_command_from_file(name, path)
    return f"sent contents of {path!r} to {name!r}"


@mcp.tool()
def capture(name: str, lines: int = -1) -> str:
    """Return a session's current screen contents plus scrollback. lines=-1
    returns everything captured; a positive number limits to the last N lines."""
    return _manager().capture(name, lines=lines)


@mcp.tool()
def cleanup_session(name: str) -> str:
    """Remove `name` from the registry if it is no longer alive."""
    removed = _manager().cleanup_session(name)
    return f"{name!r} {'removed' if removed else 'still alive, left in place'}"


@mcp.tool()
def kill_session(name: str) -> str:
    """Terminate a live session. Its registry entry stays (now dead) until
    cleanup_session removes it."""
    _manager().kill_session(name)
    return f"killed {name!r}"


def run_server() -> None:
    mcp.run()


if __name__ == "__main__":
    run_server()
