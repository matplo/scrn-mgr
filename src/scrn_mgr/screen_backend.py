"""Thin wrapper around the `screen` binary, local or over SSH.

Every non-interactive operation (start/send/hardcopy/quit/list) is executed
as a *single* subprocess call. `run()` decides local vs. SSH not from
`host.is_local` alone but from `hostinfo.resolves_to_local(host)` -- a
session recorded under some other node's hostname is still run locally
when we happen to already be on that node (e.g. a cluster's shared $HOME
registry, or a job landing back on the node that created the session).

For a genuinely remote host, the command line is built as one pre-quoted
shell string (ssh does not preserve argv boundaries on the remote end, so
we must quote it ourselves), and is tried against the host's hostname
first, falling back to its recorded IP if the hostname alone doesn't
connect (unresolvable/stale DNS is common for cluster compute nodes).

Interactive `attach` is handled separately (see `attach_argv`): it needs a
real PTY and to take over the caller's terminal, so it is never run through
`run()` -- callers run it as an inherited-stdio subprocess instead.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess

from scrn_mgr.exceptions import RemoteCommandError, ScreenNotInstalledError
from scrn_mgr.hostinfo import resolves_to_local
from scrn_mgr.models import Host

SCREEN_BIN = "screen"

# ssh's own exit code when it never got as far as running a remote command
# (name doesn't resolve, connection refused/timed out, auth failure, ...) --
# distinct from whatever the remote command itself exits with.
SSH_CONNECT_FAILED = 255


def ensure_local_screen_available() -> None:
    if shutil.which(SCREEN_BIN) is None:
        raise ScreenNotInstalledError(
            f"the `{SCREEN_BIN}` binary was not found on PATH "
            "(install it, e.g. `brew install screen` or `apt install screen`)"
        )


def _ssh_target(host: Host, target: str) -> str:
    return f"{host.user}@{target}" if host.user else target


def _run_once(argv: list[str], timeout: float | None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ScreenNotInstalledError(str(exc)) from exc
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv, SSH_CONNECT_FAILED, "", f"timed out after {timeout}s"
        )


def run(
    host: Host, argv: list[str], *, check: bool = True, timeout: float | None = 30
) -> subprocess.CompletedProcess:
    """Run `argv` locally, or as one quoted command string over SSH."""
    if resolves_to_local(host):
        full_argv = argv
        proc = _run_once(full_argv, timeout)
    else:
        remote_cmd = shlex.join(argv)
        # Try the hostname first, then the recorded IP if that didn't even
        # connect -- a stale/unresolvable hostname shouldn't strand a session
        # whose IP is still reachable.
        targets = [t for t in (host.hostname, host.ip) if t]
        if not targets:
            raise RemoteCommandError(argv, -1, "host has neither a hostname nor an ip recorded")
        proc = None
        full_argv = None
        for target in targets:
            ssh_argv = ["ssh"]
            if host.port:
                ssh_argv += ["-p", str(host.port)]
            ssh_argv.append(_ssh_target(host, target))
            full_argv = [*ssh_argv, "--", remote_cmd]
            proc = _run_once(full_argv, timeout)
            if proc.returncode != SSH_CONNECT_FAILED:
                break
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
    """Argv for an interactive attach (takes over the tty). Callers decide
    whether `host` should be treated as local (see hostinfo.resolves_to_local)
    before calling this -- it only looks at host.is_local itself."""
    if host.is_local:
        return [SCREEN_BIN, "-r", name]
    remote_cmd = f"{SCREEN_BIN} -r {shlex.quote(name)}"
    ssh_argv = ["ssh", "-t"]
    if host.port:
        ssh_argv += ["-p", str(host.port)]
    target = host.hostname or host.ip
    ssh_argv.append(_ssh_target(host, target))
    return [*ssh_argv, "--", remote_cmd]


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


def list_sessions_raw(host: Host) -> list[dict] | None:
    """Run `screen -ls` on `host` and parse it. Returns None if the host
    couldn't be reached at all (SSH connection failure) -- distinct from an
    empty list, which means we confirmed there's nothing there."""
    proc = run(host, list_argv(), check=False, timeout=8)
    if proc.returncode == SSH_CONNECT_FAILED:
        return None
    return parse_screen_ls(proc.stdout + proc.stderr)


def capture(host: Host, name: str, lines: int = -1) -> str:
    proc = run(host, hardcopy_argv(name))
    text = proc.stdout
    if lines is not None and lines > 0:
        text_lines = text.splitlines()
        text = "\n".join(text_lines[-lines:])
    return text
