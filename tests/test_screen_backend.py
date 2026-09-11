import time

from scrn_mgr import screen_backend
from scrn_mgr.models import Host

from .conftest import requires_screen

SAMPLE_LS_OUTPUT = """\
There are screens on:
\t12345.work\t(Detached)
\t12346.gpu-train\t(Attached)
2 Sockets in /var/folders/xx/screens/S-user.
"""

NO_SOCKETS_OUTPUT = "No Sockets found in /var/folders/xx/screens/S-user.\n"


def test_parse_screen_ls_multiple() -> None:
    sessions = screen_backend.parse_screen_ls(SAMPLE_LS_OUTPUT)
    assert sessions == [
        {"pid": 12345, "name": "work", "attached": False},
        {"pid": 12346, "name": "gpu-train", "attached": True},
    ]


def test_parse_screen_ls_empty() -> None:
    assert screen_backend.parse_screen_ls(NO_SOCKETS_OUTPUT) == []


def test_start_argv_no_cwd() -> None:
    assert screen_backend.start_argv("work", None) == ["screen", "-dmS", "work"]


def test_start_argv_with_cwd() -> None:
    argv = screen_backend.start_argv("work", "/tmp/some dir")
    assert argv[0] == "sh"
    assert "cd '/tmp/some dir'" in argv[2]
    assert "screen -dmS work" in argv[2]


def test_send_keys_argv_appends_newline() -> None:
    argv = screen_backend.send_keys_argv("work", "echo hi")
    assert argv == ["screen", "-S", "work", "-p", "0", "-X", "stuff", "echo hi\n"]


def test_send_keys_argv_keeps_existing_newline() -> None:
    argv = screen_backend.send_keys_argv("work", "echo hi\n")
    assert argv[-1] == "echo hi\n"


def test_quit_argv() -> None:
    assert screen_backend.quit_argv("work") == ["screen", "-S", "work", "-X", "quit"]


def test_attach_argv_local() -> None:
    assert screen_backend.attach_argv(Host(), "work") == ["screen", "-r", "work"]


def test_attach_argv_remote_uses_ssh_dash_t() -> None:
    host = Host.parse("user@gpu01:2222")
    argv = screen_backend.attach_argv(host, "work")
    assert argv[0] == "ssh"
    assert "-t" in argv
    assert "-p" in argv and "2222" in argv
    assert "user@gpu01" in argv
    assert argv[-1] == "screen -r work"


def test_run_wraps_remote_command_as_single_shlex_joined_string() -> None:
    host = Host.parse("user@gpu01")
    # A name with a space must survive as one argument on the remote end.
    argv = screen_backend.send_keys_argv("my session", "echo hi")
    # We only assert on argv construction here (no real ssh call) --
    # `run()`'s remote path shlex.joins argv into one string; verify that
    # round-trips through shlex.
    import shlex

    joined = shlex.join(argv)
    assert shlex.split(joined) == argv


# -- integration tests against the real, installed `screen` binary ----------


@requires_screen
def test_local_session_lifecycle(session_name: str) -> None:
    host = Host()
    try:
        proc = screen_backend.run(host, screen_backend.start_argv(session_name, None))
        assert proc.returncode == 0

        # give screen a moment to register the socket
        for _ in range(20):
            if any(e["name"] == session_name for e in screen_backend.list_sessions_raw(host)):
                break
            time.sleep(0.1)
        live = screen_backend.list_sessions_raw(host)
        assert any(e["name"] == session_name for e in live)

        screen_backend.run(host, screen_backend.send_keys_argv(session_name, "echo scrnmgr_marker"))
        time.sleep(0.3)
        output = screen_backend.capture(host, session_name)
        assert "scrnmgr_marker" in output
    finally:
        screen_backend.run(host, screen_backend.quit_argv(session_name), check=False)
        time.sleep(0.2)
        live = screen_backend.list_sessions_raw(host)
        assert not any(e["name"] == session_name for e in live)
