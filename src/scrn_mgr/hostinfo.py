"""Machine self-identification: hostname/IP detection, and whether a given
Host record refers to the machine this code is running on right now.

This matters because the registry can be shared across a cluster (e.g. a
networked $HOME): a session created without --host used to be stored as
"local" (host=None) regardless of *which* node created it, so listing it
from a different node would wrongly probe that node's own `screen -ls` and
report the session dead. Sessions now always record the creating machine's
real hostname (+ best-effort IP); `resolves_to_local()` is what lets every
other operation cheaply tell "is this actually me?" and skip SSH when it is.

Kept dependency-free of scrn_mgr.models (the Host argument below is duck-
typed) so scrn_mgr.models can import from here for Host.detect_local()
without a circular import.
"""

from __future__ import annotations

import os
import socket


def detect_hostname() -> str:
    """This machine's hostname: $HOST, then $HOSTNAME, then socket.gethostname()."""
    return os.environ.get("HOST") or os.environ.get("HOSTNAME") or socket.gethostname()


def detect_ip(hostname: str | None = None) -> str | None:
    """Best-effort DNS lookup of `hostname` (default: this machine's own).
    None if it doesn't resolve (offline, an mDNS-only ".local" name, etc.) --
    never raises."""
    try:
        return socket.gethostbyname(hostname or detect_hostname())
    except OSError:
        return None


def local_hostnames() -> set[str]:
    """Names this machine might be known by, short and fully-qualified."""
    names = {detect_hostname()}
    for var in ("HOST", "HOSTNAME"):
        value = os.environ.get(var)
        if value:
            names.add(value)
    try:
        names.add(socket.gethostname())
    except OSError:
        pass
    return names | {n.split(".")[0] for n in names}


def local_addresses() -> set[str]:
    """This machine's own IP addresses, loopback included."""
    addrs = {"127.0.0.1", "::1"}
    ip = detect_ip()
    if ip:
        addrs.add(ip)
    try:
        _, _, extra = socket.gethostbyname_ex(socket.gethostname())
        addrs.update(extra)
    except OSError:
        pass
    return addrs


def resolves_to_local(host) -> bool:
    """True if `host` (an scrn_mgr.models.Host) refers to the machine this
    code is running on right now -- by hostname string, or by resolved/stored
    IP -- so callers can run `screen` directly instead of going over SSH."""
    if host.is_local:
        return True
    names = local_hostnames()
    if host.hostname and (host.hostname in names or host.hostname.split(".")[0] in names):
        return True
    addrs = local_addresses()
    if host.ip and host.ip in addrs:
        return True
    if host.hostname:
        resolved = detect_ip(host.hostname)
        if resolved and resolved in addrs:
            return True
    return False
