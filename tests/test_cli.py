import time

from typer.testing import CliRunner

from scrn_mgr.cli import app

from .conftest import requires_screen

runner = CliRunner()


def test_list_empty(state_dir) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_send_to_unknown_session_exits_nonzero(state_dir) -> None:
    result = runner.invoke(app, ["send", "nope", "echo hi"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_cleanup_without_name_or_all_exits_nonzero(state_dir) -> None:
    result = runner.invoke(app, ["cleanup"])
    assert result.exit_code == 1


@requires_screen
def test_new_send_capture_list_kill_cleanup(state_dir, session_name: str) -> None:
    try:
        result = runner.invoke(app, ["new", session_name])
        assert result.exit_code == 0, result.output

        result = runner.invoke(app, ["send", session_name, "echo cli_marker"])
        assert result.exit_code == 0, result.output
        time.sleep(0.3)

        result = runner.invoke(app, ["capture", session_name])
        assert result.exit_code == 0
        assert "cli_marker" in result.output

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert session_name in result.output

        result = runner.invoke(app, ["kill", session_name])
        assert result.exit_code == 0
        time.sleep(0.2)

        result = runner.invoke(app, ["cleanup", "--all"])
        assert result.exit_code == 0
        assert session_name in result.output
    finally:
        runner.invoke(app, ["kill", session_name])
        runner.invoke(app, ["cleanup", "--all"])


@requires_screen
def test_new_duplicate_name_exits_nonzero(state_dir, session_name: str) -> None:
    try:
        assert runner.invoke(app, ["new", session_name]).exit_code == 0
        result = runner.invoke(app, ["new", session_name])
        assert result.exit_code == 1
        assert "already exists" in result.output
    finally:
        runner.invoke(app, ["kill", session_name])
        runner.invoke(app, ["cleanup", "--all"])


def test_create_alias_matches_new(state_dir) -> None:
    # `create` is a hidden alias of `new` -- both should be recognized commands.
    assert "create" in {c.name for c in app.registered_commands}
    assert "create-or-attach" in {c.name for c in app.registered_commands}
