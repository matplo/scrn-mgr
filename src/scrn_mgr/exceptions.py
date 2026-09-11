"""Exceptions raised by scrn_mgr."""

from __future__ import annotations


class ScrnMgrError(Exception):
    """Base class for all scrn_mgr errors."""


class ScreenNotInstalledError(ScrnMgrError):
    """The `screen` binary could not be found (locally or on the remote host)."""


class SessionExistsError(ScrnMgrError):
    """A session with this name is already registered (on the requested host)."""

    def __init__(self, name: str, host: str | None = None) -> None:
        self.name = name
        self.host = host
        where = f" on {host}" if host else ""
        super().__init__(f"session {name!r} already exists{where}")


class SessionNotFoundError(ScrnMgrError):
    """No registry entry (or no live screen session) matches this name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"session {name!r} not found")


class RemoteCommandError(ScrnMgrError):
    """A local or SSH-wrapped `screen`/shell invocation failed."""

    def __init__(self, command: list[str], returncode: int, stderr: str = "") -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"command {command!r} exited with {returncode}"
            + (f": {stderr.strip()}" if stderr.strip() else "")
        )
