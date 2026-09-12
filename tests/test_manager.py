import time

import pytest

from scrn_mgr import hostinfo
from scrn_mgr.exceptions import SessionExistsError, SessionNotFoundError
from scrn_mgr.manager import ScreenSessionManager
from scrn_mgr.models import Host

from .conftest import requires_screen


def test_send_command_to_unknown_session_raises(manager: ScreenSessionManager) -> None:
    with pytest.raises(SessionNotFoundError):
        manager.send_command("nope", "echo hi")


def test_capture_unknown_session_raises(manager: ScreenSessionManager) -> None:
    with pytest.raises(SessionNotFoundError):
        manager.capture("nope")


@requires_screen
def test_new_session_records_real_hostname(manager: ScreenSessionManager, session_name: str) -> None:
    try:
        record = manager.new_session(session_name)
        assert record.host.hostname == hostinfo.detect_hostname()
        assert str(record.host) == hostinfo.detect_hostname()
    finally:
        manager.kill_session(session_name)


def test_list_sessions_marks_unreachable_host_as_unknown(
    manager: ScreenSessionManager, monkeypatch
) -> None:
    unreachable = Host(hostname="stale-dns-name.invalid", ip="203.0.113.7")
    manager.registry.add("remote-thing", unreachable)

    def fake_list_raw(host):
        if host.hostname == "stale-dns-name.invalid":
            return None
        return []

    monkeypatch.setattr("scrn_mgr.manager.screen_backend.list_sessions_raw", fake_list_raw)

    all_sessions = manager.list_sessions(all_sessions=True)
    record = next(r for r in all_sessions if r.name == "remote-thing")
    assert record.alive is None
    assert record.status == "unknown"

    # not confirmed dead -> still shows up in the default (non-all) view
    default_sessions = manager.list_sessions(all_sessions=False)
    assert any(r.name == "remote-thing" for r in default_sessions)


def test_cleanup_session_leaves_unreachable_host_alone(
    manager: ScreenSessionManager, monkeypatch
) -> None:
    unreachable = Host(hostname="stale-dns-name.invalid", ip="203.0.113.7")
    manager.registry.add("remote-thing", unreachable)
    monkeypatch.setattr(
        "scrn_mgr.manager.screen_backend.list_sessions_raw", lambda host: None
    )
    assert manager.cleanup_session("remote-thing") is False
    assert manager.registry.contains("remote-thing")


def test_create_session_alias(manager: ScreenSessionManager) -> None:
    assert ScreenSessionManager.create_session is ScreenSessionManager.new_session


def test_new_or_attach_alias(manager: ScreenSessionManager) -> None:
    assert (
        ScreenSessionManager.new_or_attach_session
        is ScreenSessionManager.create_or_attach_session
    )


@requires_screen
def test_new_session_duplicate_raises(manager: ScreenSessionManager, session_name: str) -> None:
    manager.new_session(session_name)
    try:
        with pytest.raises(SessionExistsError):
            manager.new_session(session_name)
    finally:
        manager.kill_session(session_name)


@requires_screen
def test_full_lifecycle(manager: ScreenSessionManager, real_session: str) -> None:
    name = real_session

    manager.send_command(name, "echo scrnmgr_lifecycle_marker")
    time.sleep(0.3)
    assert "scrnmgr_lifecycle_marker" in manager.capture(name)

    sessions = manager.list_sessions()
    assert any(r.name == name and r.alive for r in sessions)
    record = next(r for r in sessions if r.name == name)
    assert record.status in ("attached", "detached")
    assert record.tracked is True

    # still alive -> cleanup is a no-op
    assert manager.cleanup_session(name) is False

    manager.kill_session(name)
    time.sleep(0.2)

    # dead but still registered until cleanup
    assert manager.registry.contains(name)
    all_sessions = manager.list_sessions(all_sessions=True)
    dead_record = next(r for r in all_sessions if r.name == name)
    assert dead_record.alive is False
    assert dead_record.status == "dead"

    assert manager.cleanup_session(name) is True
    assert not manager.registry.contains(name)


@requires_screen
def test_send_commands_and_from_file(
    manager: ScreenSessionManager, real_session: str, tmp_path
) -> None:
    name = real_session
    manager.send_commands(name, ["echo one_marker", "echo two_marker"])
    time.sleep(0.3)
    output = manager.capture(name)
    assert "one_marker" in output
    assert "two_marker" in output

    script = tmp_path / "cmds.sh"
    script.write_text("echo three_marker\n")
    manager.send_command_from_file(name, script)
    time.sleep(0.3)
    assert "three_marker" in manager.capture(name)


@requires_screen
def test_cleanup_all(manager: ScreenSessionManager, session_name: str) -> None:
    manager.new_session(session_name)
    manager.kill_session(session_name)
    time.sleep(0.2)
    removed = manager.cleanup_all()
    assert session_name in removed
    assert not manager.registry.contains(session_name)
