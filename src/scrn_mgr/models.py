"""Data model for scrn_mgr: session records and host addressing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scrn_mgr import hostinfo

_HOST_RE = re.compile(
    r"^(?:(?P<user>[^@\s]+)@)?(?P<hostname>[^:\s]+)(?::(?P<port>\d+))?$"
)


@dataclass(frozen=True)
class Host:
    """An SSH-reachable target, or the local machine when hostname is None."""

    user: str | None = None
    hostname: str | None = None  # None means "local machine"
    port: int | None = None
    ip: str | None = None  # best-effort resolved IP, recorded for display and
    # as an SSH fallback target if the hostname alone isn't reachable/resolvable

    @property
    def is_local(self) -> bool:
        return self.hostname is None

    @classmethod
    def parse(cls, spec: str | None) -> "Host":
        """Parse a `[user@]hostname[:port]` string. None/"" -> local host."""
        if not spec or spec == "local":
            return cls()
        m = _HOST_RE.match(spec.strip())
        if not m:
            raise ValueError(f"invalid host spec: {spec!r}")
        port = int(m.group("port")) if m.group("port") else None
        return cls(user=m.group("user"), hostname=m.group("hostname"), port=port)

    @classmethod
    def detect_local(cls, user: str | None = None, port: int | None = None) -> "Host":
        """The machine this code is running on right now, recorded by its real
        hostname (+ best-effort IP) rather than a bare "local" placeholder --
        so a registry shared across a cluster still says *which* node a
        session is actually on."""
        hostname = hostinfo.detect_hostname()
        return cls(user=user, hostname=hostname, port=port, ip=hostinfo.detect_ip(hostname))

    def __str__(self) -> str:
        if self.is_local:
            return "local"
        s = self.hostname or ""
        if self.user:
            s = f"{self.user}@{s}"
        if self.port:
            s = f"{s}:{self.port}"
        return s

    def to_registry(self) -> dict | None:
        """Value stored in the registry JSON: None for a bare local host,
        else a dict (hostname/user/port/ip)."""
        if self.hostname is None:
            return None
        return {"user": self.user, "hostname": self.hostname, "port": self.port, "ip": self.ip}

    @classmethod
    def from_registry_value(cls, value) -> "Host":
        if value is None:
            return cls()
        if isinstance(value, str):
            # registries written before 0.2 stored a plain "[user@]host[:port]" string
            return cls.parse(value)
        return cls(
            user=value.get("user"),
            hostname=value.get("hostname"),
            port=value.get("port"),
            ip=value.get("ip"),
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SessionRecord:
    """A tracked screen session: registry metadata, optionally enriched with live state."""

    name: str
    host: Host = field(default_factory=Host)
    created_at: str = field(default_factory=now_iso)
    notes: str = ""

    # Populated when reconciled against live `screen -ls` output. alive=None
    # means "couldn't check" (e.g. the host is unreachable over SSH right
    # now) -- distinct from alive=False, which means we *confirmed* it's gone.
    pid: int | None = None
    attached: bool | None = None
    alive: bool | None = None
    tracked: bool = True  # False = discovered live but not in the registry ("untracked")

    @property
    def status(self) -> str:
        if self.alive is None:
            return "unknown"
        if not self.alive:
            return "dead"
        return "attached" if self.attached else "detached"

    def to_dict(self) -> dict:
        return {
            "host": self.host.to_registry(),
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_registry(cls, name: str, data: dict) -> "SessionRecord":
        return cls(
            name=name,
            host=Host.from_registry_value(data.get("host")),
            created_at=data.get("created_at", now_iso()),
            notes=data.get("notes", ""),
        )
