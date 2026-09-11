"""Shared test fixtures. Every test runs against an isolated ~/.scrn-mgr so
the real state dir on the developer's machine is never touched, and against
the real `screen` binary (confirmed installed) for integration coverage."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from scrn_mgr.manager import ScreenSessionManager
from scrn_mgr.registry import Registry

requires_screen = pytest.mark.skipif(
    shutil.which("screen") is None, reason="`screen` binary not installed"
)


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "scrn-mgr-state"
    monkeypatch.setenv("SCRN_MGR_HOME", str(d))
    return d


@pytest.fixture
def registry(state_dir: Path) -> Registry:
    return Registry(state_dir=state_dir)


@pytest.fixture
def manager(registry: Registry) -> ScreenSessionManager:
    return ScreenSessionManager(registry=registry)


@pytest.fixture
def session_name() -> str:
    """A short, collision-free session name for tests that start real screens."""
    return f"scrnmgr-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def real_session(manager: ScreenSessionManager, session_name: str):
    """Starts a real local screen session and guarantees it's killed afterward,
    even if the test fails partway through."""
    manager.new_session(session_name)
    try:
        yield session_name
    finally:
        try:
            manager.kill_session(session_name)
        except Exception:
            pass
