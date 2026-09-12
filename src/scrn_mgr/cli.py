"""scrn-mgr command-line interface (Typer + Rich). The primary interface."""

from __future__ import annotations

import contextlib
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from scrn_mgr.exceptions import ScrnMgrError
from scrn_mgr.manager import ScreenSessionManager

app = typer.Typer(
    name="scrn-mgr",
    help="Manage GNU screen sessions -- locally and over SSH -- from a CLI, TUI, or MCP.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


@contextlib.contextmanager
def _reporting_errors():
    try:
        yield
    except ScrnMgrError as exc:
        err_console.print(f"[bold red]error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


def _manager() -> ScreenSessionManager:
    return ScreenSessionManager()


# -- creation ----------------------------------------------------------------


def _new(
    name: str = typer.Argument(..., help="Session name"),
    host: Optional[str] = typer.Option(
        None, "--host", "-H", help="[user@]hostname[:port] to create the session on over SSH"
    ),
    cwd: Optional[str] = typer.Option(None, "--cwd", help="Working directory for the session"),
) -> None:
    """Start a new detached session (locally, or on --host over SSH)."""
    with _reporting_errors():
        record = _manager().new_session(name, host=host, cwd=cwd)
        console.print(f"[green]created[/green] {record.name!r} on {record.host}")


app.command("new")(_new)
app.command("create", hidden=True)(_new)  # alias


# -- driving -------------------------------------------------------------


@app.command("send")
def send(name: str, cmd: str) -> None:
    """Send one command line to a session (as if typed + Enter)."""
    with _reporting_errors():
        _manager().send_command(name, cmd)


@app.command("send-commands")
def send_commands(
    name: str,
    command: list[str] = typer.Option(
        [], "-c", "--command", help="Repeatable: -c 'cmd1' -c 'cmd2' ..."
    ),
) -> None:
    """Send multiple command lines to a session, in order."""
    with _reporting_errors():
        _manager().send_commands(name, command)


@app.command("send-file")
def send_file(name: str, path: str) -> None:
    """Send each line of a local file to a session, in order."""
    with _reporting_errors():
        _manager().send_command_from_file(name, path)


@app.command("capture")
def capture(
    name: str,
    lines: int = typer.Option(-1, "--lines", help="Only show the last N lines (-1 = all)"),
) -> None:
    """Print a session's current screen contents (+ scrollback)."""
    with _reporting_errors():
        console.print(_manager().capture(name, lines=lines))


# -- listing -------------------------------------------------------------


@app.command("list")
def list_(
    all_: bool = typer.Option(
        False, "--all", "-a", help="Also show stale (dead) and untracked sessions"
    ),
) -> None:
    """List known sessions."""
    with _reporting_errors():
        records = _manager().list_sessions(all_sessions=all_)
    table = Table()
    table.add_column("name")
    table.add_column("host")
    table.add_column("status")
    table.add_column("tracked")
    table.add_column("created")
    for r in records:
        status_style = {"attached": "green", "detached": "yellow", "dead": "red"}.get(
            r.status, ""
        )
        table.add_row(
            r.name,
            str(r.host),
            f"[{status_style}]{r.status}[/{status_style}]" if status_style else r.status,
            "yes" if r.tracked else "no",
            r.created_at,
        )
    console.print(table)


# -- attach (interactive; never reached over MCP) -----------------------


@app.command("attach")
def attach(name: str) -> None:
    """Attach interactively to a session (takes over this terminal)."""
    with _reporting_errors():
        _manager().attach_session(name)


def _new_or_attach(
    name: str = typer.Argument(..., help="Session name"),
    host: Optional[str] = typer.Option(
        None, "--host", "-H", help="[user@]hostname[:port], used only if the session is new"
    ),
) -> None:
    """Attach to a session, creating it first if it doesn't exist yet."""
    with _reporting_errors():
        _manager().create_or_attach_session(name, host=host)


app.command("new-or-attach")(_new_or_attach)
app.command("create-or-attach", hidden=True)(_new_or_attach)  # alias


# -- teardown -----------------------------------------------------------


@app.command("kill")
def kill(name: str) -> None:
    """Terminate a live session (registry entry stays until `cleanup`)."""
    with _reporting_errors():
        _manager().kill_session(name)
        console.print(f"[yellow]killed[/yellow] {name!r}")


@app.command("cleanup")
def cleanup(
    name: Optional[str] = typer.Argument(None, help="Session name (omit with --all)"),
    all_: bool = typer.Option(False, "--all", help="Prune every dead registry entry"),
) -> None:
    """Remove dead sessions from the registry."""
    with _reporting_errors():
        if all_:
            removed = _manager().cleanup_all()
            console.print(f"removed {len(removed)} dead entr{'y' if len(removed)==1 else 'ies'}: {removed}")
        elif name:
            removed = _manager().cleanup_session(name)
            console.print(f"{name!r} {'removed' if removed else 'still alive, left in place'}")
        else:
            err_console.print("[bold red]error:[/bold red] pass a NAME or --all")
            raise typer.Exit(code=1)


# -- MCP + TUI -------------------------------------------------------------


@app.command("serve")
def serve() -> None:
    """Run the MCP server (stdio transport) for AI assistants to drive sessions."""
    from scrn_mgr.mcp_server import run_server

    run_server()


@app.command("tui")
def tui() -> None:
    """Launch the Textual TUI."""
    tui_main()


def main() -> None:
    app()


def tui_main() -> None:
    """Entry point for the `scrn-mgr-tui` console script (alias for `scrn-mgr tui`)."""
    from scrn_mgr.tui.app import ScrnMgrApp

    ScrnMgrApp().run()


if __name__ == "__main__":
    main()
