import socket

from scrn_mgr import hostinfo
from scrn_mgr.models import Host


def test_detect_hostname_prefers_host_over_hostname(monkeypatch) -> None:
    monkeypatch.setenv("HOST", "from-host-var")
    monkeypatch.setenv("HOSTNAME", "from-hostname-var")
    assert hostinfo.detect_hostname() == "from-host-var"


def test_detect_hostname_falls_back_to_hostname_var(monkeypatch) -> None:
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setenv("HOSTNAME", "from-hostname-var")
    assert hostinfo.detect_hostname() == "from-hostname-var"


def test_detect_hostname_falls_back_to_socket(monkeypatch) -> None:
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("HOSTNAME", raising=False)
    assert hostinfo.detect_hostname() == socket.gethostname()


def test_detect_ip_returns_none_for_unresolvable_name() -> None:
    assert hostinfo.detect_ip("definitely-not-a-real-host.invalid") is None


def test_resolves_to_local_true_for_bare_host() -> None:
    assert hostinfo.resolves_to_local(Host()) is True


def test_resolves_to_local_true_for_current_hostname() -> None:
    host = Host(hostname=hostinfo.detect_hostname())
    assert hostinfo.resolves_to_local(host) is True


def test_resolves_to_local_true_for_current_ip() -> None:
    ip = hostinfo.detect_ip()
    if ip is None:
        return  # this sandbox's hostname doesn't resolve; nothing to assert
    host = Host(hostname="some-other-name.invalid", ip=ip)
    assert hostinfo.resolves_to_local(host) is True


def test_resolves_to_local_false_for_unrelated_host() -> None:
    host = Host(hostname="definitely-not-a-real-host.invalid", ip="203.0.113.5")
    assert hostinfo.resolves_to_local(host) is False
