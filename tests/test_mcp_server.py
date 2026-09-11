import time

import pytest

from scrn_mgr import mcp_server
from scrn_mgr.exceptions import SessionNotFoundError

from .conftest import requires_screen


def test_list_sessions_empty(state_dir) -> None:
    assert mcp_server.list_sessions() == []


def test_send_command_unknown_session_raises(state_dir) -> None:
    with pytest.raises(SessionNotFoundError):
        mcp_server.send_command("nope", "echo hi")


def test_no_attach_tool_registered() -> None:
    tool_names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    assert "attach" not in tool_names
    assert "attach_session" not in tool_names
    for expected in [
        "list_sessions",
        "new_session",
        "send_command",
        "send_commands",
        "send_file",
        "capture",
        "cleanup_session",
        "kill_session",
    ]:
        assert expected in tool_names


@requires_screen
def test_mcp_tools_full_roundtrip(state_dir, session_name: str) -> None:
    try:
        created = mcp_server.new_session(session_name)
        assert created["name"] == session_name
        assert created["host"] == "local"

        assert "sent" in mcp_server.send_command(session_name, "echo mcp_marker")
        time.sleep(0.3)
        assert "mcp_marker" in mcp_server.capture(session_name)

        sessions = mcp_server.list_sessions()
        assert any(s["name"] == session_name for s in sessions)

        assert "killed" in mcp_server.kill_session(session_name)
        time.sleep(0.2)
        assert "removed" in mcp_server.cleanup_session(session_name)
    finally:
        try:
            mcp_server.kill_session(session_name)
        except Exception:
            pass
        try:
            mcp_server.cleanup_session(session_name)
        except Exception:
            pass
