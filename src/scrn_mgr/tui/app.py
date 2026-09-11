"""Textual TUI for scrn-mgr."""

from __future__ import annotations

import subprocess

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Static

from scrn_mgr.exceptions import ScrnMgrError
from scrn_mgr.manager import ScreenSessionManager


class NameInputScreen(ModalScreen[str | None]):
    """Modal: prompt for a session name."""

    DEFAULT_CSS = """
    NameInputScreen { align: center middle; }
    NameInputScreen > Vertical {
        width: 50; height: auto; border: round $accent; padding: 1 2;
    }
    """

    def __init__(self, prompt: str = "session name") -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._prompt)
            yield Input(placeholder="name")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class MessageScreen(ModalScreen[None]):
    """Modal: show a block of text (capture output, errors)."""

    DEFAULT_CSS = """
    MessageScreen { align: center middle; }
    MessageScreen > Vertical {
        width: 90%; height: 80%; border: round $accent; padding: 1 2;
    }
    """

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body or "(empty)"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self._title}[/b] (press any key to close)")
            yield Static(self._body)

    def on_key(self, event) -> None:
        self.dismiss(None)


class ScrnMgrApp(App[None]):
    """Session table with new/attach/capture/kill/cleanup/refresh."""

    TITLE = "scrn-mgr"
    CSS = "DataTable { height: 1fr; }"
    BINDINGS = [
        Binding("n", "new_session", "New"),
        Binding("a", "attach", "Attach"),
        Binding("c", "capture", "Capture"),
        Binding("k", "kill", "Kill"),
        Binding("x", "cleanup", "Cleanup"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, manager: ScreenSessionManager | None = None) -> None:
        super().__init__()
        self.manager = manager or ScreenSessionManager()

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="sessions")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("name", "host", "status", "tracked", "created")
        self.action_refresh()

    def _selected_name(self) -> str | None:
        table = self.query_one(DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        return str(cell_key.row_key.value)

    def _report_error(self, exc: ScrnMgrError) -> None:
        self.push_screen(MessageScreen("error", str(exc)))

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        try:
            records = self.manager.list_sessions(all_sessions=True)
        except ScrnMgrError as exc:
            self._report_error(exc)
            return
        for r in records:
            table.add_row(
                r.name, str(r.host), r.status, "yes" if r.tracked else "no", r.created_at,
                key=r.name,
            )

    def action_new_session(self) -> None:
        def handle(name: str | None) -> None:
            if not name:
                return
            try:
                self.manager.new_session(name)
            except ScrnMgrError as exc:
                self._report_error(exc)
            self.action_refresh()

        self.push_screen(NameInputScreen("new session name"), handle)

    def action_attach(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            argv = self.manager.attach_command_argv(name)
        except ScrnMgrError as exc:
            self._report_error(exc)
            return
        with self.suspend():
            subprocess.run(argv)
        self.action_refresh()

    def action_capture(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            text = self.manager.capture(name)
        except ScrnMgrError as exc:
            text = str(exc)
        self.push_screen(MessageScreen(f"capture: {name}", text))

    def action_kill(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            self.manager.kill_session(name)
        except ScrnMgrError as exc:
            self._report_error(exc)
        self.action_refresh()

    def action_cleanup(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            self.manager.cleanup_session(name)
        except ScrnMgrError as exc:
            self._report_error(exc)
        self.action_refresh()


def main() -> None:
    ScrnMgrApp().run()


if __name__ == "__main__":
    main()
