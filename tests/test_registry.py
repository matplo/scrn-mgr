import pytest

from scrn_mgr.exceptions import SessionExistsError, SessionNotFoundError
from scrn_mgr.models import Host
from scrn_mgr.registry import Registry


def test_add_and_get(registry: Registry) -> None:
    record = registry.add("work", Host())
    assert record.name == "work"
    assert record.host.is_local

    fetched = registry.get("work")
    assert fetched.name == "work"
    assert fetched.host.is_local


def test_add_remote_host_roundtrip(registry: Registry) -> None:
    host = Host.parse("user@gpu01.cluster:2222")
    registry.add("train", host)
    fetched = registry.get("train")
    assert fetched.host.user == "user"
    assert fetched.host.hostname == "gpu01.cluster"
    assert fetched.host.port == 2222
    assert str(fetched.host) == "user@gpu01.cluster:2222"


def test_duplicate_name_raises(registry: Registry) -> None:
    registry.add("work", Host())
    with pytest.raises(SessionExistsError):
        registry.add("work", Host())


def test_missing_name_raises(registry: Registry) -> None:
    with pytest.raises(SessionNotFoundError):
        registry.get("nope")


def test_list_is_sorted_by_name(registry: Registry) -> None:
    registry.add("zeta", Host())
    registry.add("alpha", Host())
    names = [r.name for r in registry.list()]
    assert names == ["alpha", "zeta"]


def test_remove(registry: Registry) -> None:
    registry.add("work", Host())
    registry.remove("work")
    assert not registry.contains("work")
    with pytest.raises(SessionNotFoundError):
        registry.remove("work")


def test_remove_if_present(registry: Registry) -> None:
    assert registry.remove_if_present("nope") is False
    registry.add("work", Host())
    assert registry.remove_if_present("work") is True


def test_persists_across_instances(state_dir) -> None:
    Registry(state_dir=state_dir).add("work", Host())
    reloaded = Registry(state_dir=state_dir)
    assert reloaded.contains("work")
