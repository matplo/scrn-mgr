"""Headless smoke tests for the Textual TUI via App.run_test()/Pilot.

No pytest-asyncio dependency needed: each test is a plain sync function that
drives the single async check through asyncio.run().
"""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable

from scrn_mgr.manager import ScreenSessionManager
from scrn_mgr.tui.app import ScrnMgrApp

from .conftest import requires_screen


def test_mounts_with_empty_table(manager: ScreenSessionManager) -> None:
    async def run() -> None:
        app = ScrnMgrApp(manager=manager)
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one(DataTable)
            assert table.row_count == 0
            assert [str(c.label) for c in table.columns.values()] == [
                "name",
                "host",
                "status",
                "tracked",
                "created",
            ]

    asyncio.run(run())


@requires_screen
def test_refresh_reflects_new_session(manager: ScreenSessionManager, real_session: str) -> None:
    async def run() -> None:
        app = ScrnMgrApp(manager=manager)
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one(DataTable)
            app.action_refresh()
            await pilot.pause()
            assert table.row_count == 1
            row_key = table.coordinate_to_cell_key((0, 0)).row_key
            assert str(row_key.value) == real_session

    asyncio.run(run())


@requires_screen
def test_refresh_key_binding_triggers_reload(
    manager: ScreenSessionManager, real_session: str
) -> None:
    async def run() -> None:
        app = ScrnMgrApp(manager=manager)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            table = app.query_one(DataTable)
            assert table.row_count == 1

    asyncio.run(run())
