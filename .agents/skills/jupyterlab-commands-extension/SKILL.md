---
name: jupyterlab-commands-extension
description: Run an allowed JupyterLab command in a browser tab, through the `jupyterlab-commands` CLI of jupyterlab_commands_extension. Use when a task needs the running JupyterLab to open a file, create a notebook, console, terminal or launcher, show a notification, or run any command id the user has allowed, or "run a JupyterLab command".
---

# jupyterlab-commands

Runs in a terminal of the lab. Discovery uses the loopback address by default; an explicit `--url` with `JUPYTERLAB_COMMANDS_TOKEN` set reaches a remote server. The browser tab that is polling runs one allowed command and returns its result. The token travels in the Authorization header and is never printed.

Commands, flags, output, exit codes: `jupyterlab-commands --help`, `jupyterlab-commands <command> --help`. Read first.

## Rules

- Never print the token. Do not put it in a command you show or log. The CLI reads it from the environment or the server record
- Run `jupyterlab-commands --list` before `execute`. The allowlist belongs to the browser tab; a command outside it fails with exit code 4
- Ask the user before an action that cannot be undone, or that opens or edits their files. `execute` runs in their lab
- Long output: pass `--json` and read the fields you need
