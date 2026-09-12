"""ScreenSessionManager: the high-level API used by the CLI, TUI and MCP server."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scrn_mgr import hostinfo, screen_backend
from scrn_mgr.exceptions import ScrnMgrError
from scrn_mgr.models import Host, SessionRecord
from scrn_mgr.registry import Registry


class ScreenSessionManager:
    """Create, drive, and track `screen` sessions -- local or over SSH."""

    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or Registry()

    # -- creation ----------------------------------------------------------

    def new_session(
        self, name: str, host: str | Host | None = None, cwd: str | None = None
    ) -> SessionRecord:
        """Register and start a new detached session. Raises SessionExistsError if
        `name` is already registered (on any host).

        With no `host` (or "local"), records *this* machine's real hostname
        (see Host.detect_local) rather than a bare "local" placeholder -- the
        registry can be shared across a cluster (e.g. a networked $HOME), so
        "local" would otherwise be ambiguous about which node actually has
        the session.
        """
        if isinstance(host, Host):
            h = host
        elif not host or host == "local":
            h = Host.detect_local()
        else:
            h = Host.parse(host)
        if h.hostname and not h.ip:
            ip = hostinfo.detect_ip(h.hostname)
            if ip:
                h = Host(user=h.user, hostname=h.hostname, port=h.port, ip=ip)

        if hostinfo.resolves_to_local(h):
            screen_backend.ensure_local_screen_available()
        record = self.registry.add(name, h)
        screen_backend.run(h, screen_backend.start_argv(name, cwd))
        return record

    create_session = new_session  # alias (matches the inspiration API)

    # -- driving a session ---------------------------------------------------

    def send_command(self, name: str, cmd: str) -> None:
        record = self.registry.get(name)
        screen_backend.run(record.host, screen_backend.send_keys_argv(name, cmd))

    def send_commands(self, name: str, cmds: list[str]) -> None:
        record = self.registry.get(name)
        for cmd in cmds:
            screen_backend.run(record.host, screen_backend.send_keys_argv(name, cmd))

    def send_command_from_file(self, name: str, path: str | Path) -> None:
        lines = Path(path).read_text().splitlines()
        self.send_commands(name, lines)

    def capture(self, name: str, lines: int = -1) -> str:
        record = self.registry.get(name)
        return screen_backend.capture(record.host, name, lines=lines)

    # -- listing -------------------------------------------------------------

    def list_sessions(self, all_sessions: bool = False) -> list[SessionRecord]:
        """Reconcile the registry against live `screen -ls` output (run
        locally or over SSH per distinct host, see hostinfo.resolves_to_local).

        Default: everything not *confirmed* dead -- i.e. alive or unknown
        (host currently unreachable). all_sessions=True also includes
        confirmed-dead (stale) and untracked (alive but not in the registry)
        sessions.
        """
        registered = self.registry.list()
        hosts_by_key: dict[str, Host] = {str(r.host): r.host for r in registered}
        live_by_host = {
            key: screen_backend.list_sessions_raw(h) for key, h in hosts_by_key.items()
        }
        unreachable = {key for key, entries in live_by_host.items() if entries is None}
        live_index = {
            (key, e["name"]): e
            for key, entries in live_by_host.items()
            if entries is not None
            for e in entries
        }

        result: list[SessionRecord] = []
        seen: set[tuple[str, str]] = set()
        for record in registered:
            key = str(record.host)
            if key in unreachable:
                record.alive = None  # couldn't check -- not the same as confirmed dead
            else:
                live = live_index.get((key, record.name))
                if live:
                    record.pid = live["pid"]
                    record.attached = live["attached"]
                    record.alive = True
                else:
                    record.alive = False
            seen.add((key, record.name))
            result.append(record)

        if all_sessions:
            for key, entries in live_by_host.items():
                if entries is None:
                    continue
                host = hosts_by_key[key]
                for e in entries:
                    if (key, e["name"]) in seen:
                        continue
                    result.append(
                        SessionRecord(
                            name=e["name"],
                            host=host,
                            pid=e["pid"],
                            attached=e["attached"],
                            alive=True,
                            tracked=False,
                        )
                    )
        else:
            result = [r for r in result if r.alive is not False]

        return result

    # -- interactive attach (CLI/TUI only, never MCP) -------------------------

    def _resolve_attach(self, name: str) -> tuple[list[str], bool]:
        record = self.registry.get(name)
        is_local = hostinfo.resolves_to_local(record.host)
        effective_host = Host() if is_local else record.host
        return screen_backend.attach_argv(effective_host, name), is_local

    def attach_command_argv(self, name: str) -> list[str]:
        """Argv for an interactive `screen -r` (or, over SSH, `ssh -t ... screen
        -r`). Exposed separately from attach_session so the TUI can run it as a
        suspended subprocess instead of taking over the whole process."""
        argv, _ = self._resolve_attach(name)
        return argv

    def attach_session(self, name: str) -> None:
        """Attach interactively (inherits this process's stdio, taking over
        the terminal for the life of the session). Raises ScrnMgrError if a
        remote attach's SSH connection itself fails, with a suggestion to
        connect manually."""
        argv, is_local = self._resolve_attach(name)
        proc = subprocess.run(argv)
        if not is_local and proc.returncode == screen_backend.SSH_CONNECT_FAILED:
            record = self.registry.get(name)
            raise ScrnMgrError(
                f"couldn't ssh to {record.host} to attach to {name!r}. "
                f"Try connecting manually: ssh {record.host}, then run "
                f"`scrn-mgr attach {name}` there."
            )

    def create_or_attach_session(
        self, name: str, host: str | Host | None = None
    ) -> None:
        if not self.registry.contains(name):
            self.new_session(name, host=host)
        self.attach_session(name)

    new_or_attach_session = create_or_attach_session  # alias

    # -- teardown ------------------------------------------------------------

    def kill_session(self, name: str) -> None:
        """Terminate the live screen process. Leaves the registry entry in place
        (now dead) -- run cleanup_session/cleanup_all to prune it."""
        record = self.registry.get(name)
        screen_backend.run(record.host, screen_backend.quit_argv(name), check=False)

    def cleanup_session(self, name: str) -> bool:
        """Remove `name` from the registry if it's confirmed no longer alive.
        Returns whether it was removed -- False both when it's still alive
        and when its host couldn't be reached to check (never guesses)."""
        record = self.registry.get(name)
        live = screen_backend.list_sessions_raw(record.host)
        if live is None or any(e["name"] == name for e in live):
            return False
        return self.registry.remove_if_present(name)

    def cleanup_all(self) -> list[str]:
        return [r.name for r in self.registry.list() if self.cleanup_session(r.name)]
