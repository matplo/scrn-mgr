"""Persistent registry of known sessions, stored at ~/.scrn-mgr/registry.json.

The registry records *intent*: which session names exist and which host they
live on. It does not track liveness by itself -- `ScreenSessionManager`
reconciles it against real `screen -ls` output. A file lock keeps concurrent
CLI / TUI / MCP-server processes from corrupting it.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path
from typing import Iterator

from scrn_mgr.exceptions import SessionExistsError, SessionNotFoundError
from scrn_mgr.models import Host, SessionRecord

REGISTRY_VERSION = 1


def default_state_dir() -> Path:
    """~/.scrn-mgr, honoring $SCRN_MGR_HOME for tests/overrides."""
    override = os.environ.get("SCRN_MGR_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".scrn-mgr"


class Registry:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or default_state_dir()
        self.path = self.state_dir / "registry.json"
        self.lock_path = self.state_dir / ".lock"

    # -- locking -----------------------------------------------------------

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # -- raw load/save -------------------------------------------------------

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": REGISTRY_VERSION, "sessions": {}}
        with self.path.open("r") as f:
            data = json.load(f)
        data.setdefault("version", REGISTRY_VERSION)
        data.setdefault("sessions", {})
        return data

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp.replace(self.path)

    # -- public API ------------------------------------------------------

    def list(self) -> list[SessionRecord]:
        with self._locked():
            data = self._read()
        return [
            SessionRecord.from_registry(name, entry)
            for name, entry in sorted(data["sessions"].items())
        ]

    def get(self, name: str) -> SessionRecord:
        with self._locked():
            data = self._read()
            entry = data["sessions"].get(name)
        if entry is None:
            raise SessionNotFoundError(name)
        return SessionRecord.from_registry(name, entry)

    def contains(self, name: str) -> bool:
        with self._locked():
            data = self._read()
        return name in data["sessions"]

    def add(self, name: str, host: Host, notes: str = "") -> SessionRecord:
        with self._locked():
            data = self._read()
            if name in data["sessions"]:
                raise SessionExistsError(name, host.to_registry())
            record = SessionRecord(name=name, host=host, notes=notes)
            data["sessions"][name] = record.to_dict()
            self._write(data)
        return record

    def remove(self, name: str) -> None:
        with self._locked():
            data = self._read()
            if name not in data["sessions"]:
                raise SessionNotFoundError(name)
            del data["sessions"][name]
            self._write(data)

    def remove_if_present(self, name: str) -> bool:
        with self._locked():
            data = self._read()
            if name not in data["sessions"]:
                return False
            del data["sessions"][name]
            self._write(data)
        return True
