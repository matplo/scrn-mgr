"""Thin wrapper around the `screen` binary, local or over SSH.

Every non-interactive operation (start/send/hardcopy/quit/list) is executed
as a *single* subprocess call -- for a remote `Host` that means one `ssh`
round trip per call, with the remote command line built as one pre-quoted
shell string (ssh does not preserve argv boundaries on the remote end, so we
must quote it ourselves).

Interactive `attach` is handled separately (see `attach_argv`): it needs a
real PTY and to take over the caller's terminal, so it is never run through
`run()` -- callers `os.execvp` into it instead.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess

from scrn_mgr.exceptions import RemoteCommandError, ScreenNotInstalledError
from scrn_mgr.models import Host

SCREEN_BIN = "screen"


def ensure_local_screen_available() -> None:
    if shutil.which(SCREEN_BIN) is None:
        raise ScreenNotInstalledError(
            f"the `{SCREEN_BIN}` binary was not found on PATH "
            "(install it, e.g. `brew install screen` or `apt install screen`)"
        )


def _ssh_argv(host: Host) -> list[str]:
    argv = ["ssh"]
    if host.port:
        argv += ["-p", str(host.port)]
    target = f"{host.user}@{host.hostname}" if host.user else host.hostname
    argv.append(target)
    return argv


def run(
    host: Host, argv: list[str], *, check: bool = True, timeout: float | None = 30
) -> subprocess.CompletedProcess:
    """Run `argv` locally, or as one quoted command string over SSH."""
    if host.is_local:
        full_argv = argv
    else:
        remote_cmd = shlex.join(argv)
        full_argv = [*_ssh_argv(host), "--", remote_cmd]
    try:
        proc = subprocess.run(full_argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ScreenNotInstalledError(str(exc)) from exc
    if check and proc.returncode != 0:
        raise RemoteCommandError(full_argv, proc.returncode, proc.stderr)
    return proc


def start_argv(name: str, cwd: str | None) -> list[str]:
    if cwd:
        inner = f"cd {shlex.quote(cwd)} && exec {SCREEN_BIN} -dmS {shlex.quote(name)}"
        return ["sh", "-c", inner]
    return [SCREEN_BIN, "-dmS", name]


def send_keys_argv(name: str, text: str) -> list[str]:
    if not text.endswith("\n"):
        text += "\n"
    # -p 0 explicitly selects window 0: without it, some screen builds
    # (e.g. the old 4.00.03 macOS-bundled one) silently no-op -X on a
    # session that's never been attached to interactively yet.
    return [SCREEN_BIN, "-S", name, "-p", "0", "-X", "stuff", text]


def hardcopy_argv(name: str) -> list[str]:
    """Snapshot the session's visible screen buffer as text, in one shot.

    Deliberately does not pass hardcopy's `-h` (include scrollback history)
    flag: it's a relatively recent screen addition and is silently ignored
    (producing an empty capture) on older builds such as the macOS-bundled
    4.00.03.
    """
    remote_cmd = (
        f"t=$(mktemp); {SCREEN_BIN} -S {shlex.quote(name)} -p 0 -X hardcopy \"$t\" "
        f'&& cat "$t" 2>/dev/null; rm -f "$t"'
    )
    return ["sh", "-c", remote_cmd]


def quit_argv(name: str) -> list[str]:
    return [SCREEN_BIN, "-S", name, "-X", "quit"]


def list_argv() -> list[str]:
    return [SCREEN_BIN, "-ls"]


def attach_argv(host: Host, name: str) -> list[str]:
    """Argv to `os.execvp` into for an interactive attach (takes over the tty)."""
    if host.is_local:
        return [SCREEN_BIN, "-r", name]
    remote_cmd = f"{SCREEN_BIN} -r {shlex.quote(name)}"
    return ["ssh", "-t", *_ssh_argv(host)[1:], "--", remote_cmd]


_LS_LINE_RE = re.compile(r"^\s*(\d+)\.(\S+)\s+\(([^)]*)\)\s*$", re.MULTILINE)


def parse_screen_ls(output: str) -> list[dict]:
    """Parse `screen -ls` output into [{"pid": int, "name": str, "attached": bool}, ...]."""
    sessions = []
    for m in _LS_LINE_RE.finditer(output):
        pid, name, state = m.group(1), m.group(2), m.group(3)
        sessions.append(
            {
                "pid": int(pid),
                "name": name,
                "attached": "attach" in state.lower(),
            }
        )
    return sessions


def list_sessions_raw(host: Host) -> list[dict]:
    """Run `screen -ls` on `host` and parse it. Never raises on the "no sockets" case."""
    proc = run(host, list_argv(), check=False)
    return parse_screen_ls(proc.stdout + proc.stderr)


def capture(host: Host, name: str, lines: int = -1) -> str:
    proc = run(host, hardcopy_argv(name))
    text = proc.stdout
    if lines is not None and lines > 0:
        text_lines = text.splitlines()
        text = "\n".join(text_lines[-lines:])
    return text
