# jupyterlab_commands_extension

[![GitHub Actions](https://github.com/stellarshenson/jupyterlab_commands_extension/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/jupyterlab_commands_extension/actions/workflows/build.yml)
[![npm version](https://img.shields.io/npm/v/jupyterlab_commands_extension.svg)](https://www.npmjs.com/package/jupyterlab_commands_extension)
[![PyPI version](https://img.shields.io/pypi/v/jupyterlab-commands-extension.svg)](https://pypi.org/project/jupyterlab-commands-extension/)
[![Total PyPI downloads](https://static.pepy.tech/badge/jupyterlab-commands-extension)](https://pepy.tech/project/jupyterlab-commands-extension)
[![JupyterLab 4](https://img.shields.io/badge/JupyterLab-4-orange.svg)](https://jupyterlab.readthedocs.io/en/stable/)
[![Brought To You By KOLOMOLO](https://img.shields.io/badge/Brought%20To%20You%20By-KOLOMOLO-00ffff?style=flat)](https://kolomolo.com)
[![Donate PayPal](https://img.shields.io/badge/Donate-PayPal-blue?style=flat)](https://www.paypal.com/donate/?hosted_button_id=B4KPBJDLLXTSA)

> [!TIP]
> This extension is part of the [stellars_jupyterlab_extensions](https://github.com/stellarshenson/stellars_jupyterlab_extensions) metapackage. Install all Stellars extensions at once: `pip install stellars_jupyterlab_extensions`

Display all available JupyterLab commands with their full reference IDs and arguments in a dedicated tab. The same tab exposes an allowlist of commands that the `jupyterlab-commands` CLI can run in the browser from a terminal.

![Command Palette](.resources/screenshot-command.png)

![Commands Reference Panel](.resources/screenshot-commands-reference.png)

## Features

- **Command reference tab** - Opens a new tab listing every registered JupyterLab command
- **Full command IDs** - Shows complete command identifiers, for example `iframe:open` and `filebrowser:copy`
- **Argument inspection** - Displays command arguments extracted from the running application
- **Searchable list** - Filters commands by command ID, label or description
- **Command executor** - Runs an allowed command from a terminal through the `jupyterlab-commands` CLI
- **Allowlist** - Restricts the CLI to the command IDs in the `allowedCommands` setting

## Requirements

- JupyterLab >= 4.0.0
- Python >= 3.10

## Installation

```bash
pip install jupyterlab_commands_extension
```

For a development install from a clone, run `make install`.

## Command line

`jupyterlab-commands` runs in a terminal of the lab. It finds the running Jupyter server, selects the most recently registered browser tab with the extension active, and asks that tab to run one command. Discovery uses the loopback address by default, and loopback requests bypass any proxy. An explicit `--url` with `JUPYTERLAB_COMMANDS_TOKEN` set reaches a remote server. The token is sent in the Authorization header and is never printed.

```bash
JUPYTERLAB_COMMANDS_TOKEN=... jupyterlab-commands --url https://remote-host:8888 --list
```

`jupyterlab-commands --help` and `jupyterlab-commands <command> --help` hold the full reference. The three subcommands are `list`, which prints the allowed command IDs, `execute`, which runs one allowed command, and `activity`. `--json` prints machine-readable output.

`activity` posts the current time to the JupyterHub activity route, the same write the single-user notifier makes. One call marks the server active once; the hub culls it as idle after its idle timeout counted from the last mark, so while work runs, repeat the call at an interval shorter than that timeout. It needs no browser tab, but it runs only in a lab started by JupyterHub: it posts `{"last_activity": TS, "servers": {JUPYTERHUB_SERVER_NAME: {"last_activity": TS}}}` to `JUPYTERHUB_ACTIVITY_URL` with the hub token from `JUPYTERHUB_API_TOKEN` or `JPY_API_TOKEN`, through no proxy and no redirect. The hub answers 200 even when the time does not move, because the route never moves time backwards. A hub refusal prints the hub message and exits 5. `--url` and `--token` do not apply to it.

```bash
jupyterlab-commands activity
```

`file:download` starts a browser download of a file the contents API serves. The `path` argument names the file relative to the server root; the file must exist, and folders are refused. The download starts in the browser tab that runs the relay, so the file lands on the user computer.

```bash
jupyterlab-commands execute file:download --args '{"path": "data/report.csv"}'
```

Exit codes: 0 success, 2 discovery or usage error, 3 no browser client, 4 command not allowed, 5 execution error.

The browser tab is the executor: the command runs in the lab, not in the terminal.

## Allowlist

The `allowedCommands` setting holds the command IDs the CLI may run. The defaults are `docmanager:open`, `help:open`, `apputils:notify`, `notebook:create-new`, `console:create`, `terminal:create-new`, `launcher:create`, `jupyterlab-commands-reference:open` and `file:download`.

The **Add to command executor** button in the Command Executor column of the reference tab appends that command ID to the setting, and the button then shows **Added**. The setting can also be edited directly in **Settings > Settings Editor > Commands Executor**, whose plugin ID is `jupyterlab_commands_extension:plugin`.

A user with a saved `allowedCommands` list keeps it; the extension does not rewrite the list, so add `file:download` with the **Add to command executor** button.

The reference tab opens from the command palette as **Show Commands Reference** under Help, and carries the text editor icon.

## Agent skill

The agent skill at [`.agents/skills/jupyterlab-commands-extension/SKILL.md`](.agents/skills/jupyterlab-commands-extension/SKILL.md) tells an AI assistant to read `jupyterlab-commands --help` first and adds only the rules the help cannot enforce. The wheel installs a copy at `<sys.prefix>/share/jupyter/agents/skills/jupyterlab-commands-extension/SKILL.md`. No agent reads that directory, so link the copy where agents look.

After `pip install`, with the Python that runs the lab, link the copy where Claude Code reads skills:

```bash
mkdir -p ~/.claude/skills && ln -s "$(python -c 'import sys; print(sys.prefix)')/share/jupyter/agents/skills/jupyterlab-commands-extension" ~/.claude/skills/jupyterlab-commands-extension
```

From a clone:

```bash
mkdir -p ~/.claude/skills && ln -s "$PWD/.agents/skills/jupyterlab-commands-extension" ~/.claude/skills/jupyterlab-commands-extension
```

## Uninstall

```bash
pip uninstall jupyterlab_commands_extension
```

## Contributing

If you would like to contribute to this extension, please refer to the [Contributing Guide](CONTRIBUTING.md).
