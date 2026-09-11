# scrn-mgr

A GNU `screen` session manager: CLI first, with a Rich/Textual TUI and an
MCP server, so sessions can be driven the same way from a terminal, a
human-friendly UI, or an AI assistant. Sessions can live on the local
machine or on remote nodes reachable over SSH -- `scrn-mgr` keeps a small
registry at `~/.scrn-mgr/registry.json` recording which host each session
is on.

## Install (dev)

This project is developed inside a [`henv`](https://github.com/) environment:

```bash
henv -x pip install -e ".[dev]"
henv -x pytest -q
```

`python`, `pytest`, and the installed `scrn-mgr` executable are all run the
same way: `henv -x <command> ...`.

## Quick start (Python API)

```python
from scrn_mgr import ScreenSessionManager

manager = ScreenSessionManager()
manager.new_session("work")                       # local
manager.new_session("train", host="user@gpu01")    # remote, over SSH
manager.send_command("work", "python script.py")
output = manager.capture("work")
```

## CLI usage

```bash
scrn-mgr new work                       # alias: create
scrn-mgr new train --host user@gpu01    # started on a remote node over SSH
scrn-mgr send work "echo hello"
scrn-mgr send-commands work -c "echo 1" -c "echo 2"
scrn-mgr send-file work script.sh
scrn-mgr capture work
scrn-mgr list --all
scrn-mgr attach work                    # interactive; ssh -t under the hood if remote
scrn-mgr new-or-attach work             # alias: create-or-attach
scrn-mgr kill work
scrn-mgr cleanup work                   # or: scrn-mgr cleanup --all
scrn-mgr tui                            # Textual UI
scrn-mgr serve                          # MCP server (stdio)
```

## MCP server

`scrn-mgr serve` runs an MCP server over stdio exposing every non-interactive
operation: `list_sessions`, `new_session`, `send_command`, `send_commands`,
`send_file`, `capture`, `cleanup_session`, `kill_session`. Interactive
`attach` is intentionally **not** exposed over MCP -- it needs to take over a
real terminal/PTY for the life of the session, which doesn't fit a single
tool call/response. Use the CLI (`scrn-mgr attach NAME`) or the TUI for that.

Because the MCP server always runs locally next to its client and reaches
remote sessions the same way the CLI does (one `ssh` round trip per call,
using the host recorded in the registry), no special transport is needed for
SSH-remote sessions -- plain stdio is sufficient.

Example client config:

```json
{
  "mcpServers": {
    "scrn-mgr": {
      "command": "scrn-mgr",
      "args": ["serve"]
    }
  }
}
```

## Requirements

- Python 3.10+
- The `screen` binary (`brew install screen` / `apt install screen`)
- For remote sessions: SSH access to the target host (via your normal
  `~/.ssh/config`) with `screen` installed there too
