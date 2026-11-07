---
name: jupyterlab-commands-extension
description: Run an allowed JupyterLab command in a browser tab, through the `jupyterlab-commands` CLI of jupyterlab_commands_extension. Use when a task needs the running JupyterLab to open a file, create a notebook, console, terminal or launcher, show a notification, download a lab file to the user computer through their browser (`file:download`), or run any command id the user has allowed, or keep the JupyterHub session from being culled as idle while work runs (`activity`), or "run a JupyterLab command".
---

# jupyterlab-commands

Runs in a terminal of the lab. Discovery uses the loopback address by default; an explicit `--url` with `JUPYTERLAB_COMMANDS_TOKEN` set reaches a remote server. The browser tab that is polling runs one allowed command and returns its result.

Commands, flags, output, exit codes: `jupyterlab-commands --help`, `jupyterlab-commands <command> --help`. Read first.

## Rules

- Never print the token. Do not put it in a command you show or log. The CLI reads it from the environment or the server record
- Run `jupyterlab-commands --list` before `execute`; it prints each allowed command id with its description. The allowlist belongs to the browser tab; a command outside it fails with exit code 4
- Every `execute` passes `--purpose` (at most 25 words) and `--owner` (agent or project name); the CLI treats both as optional, this skill does not
- Ask the user before an action that cannot be undone, or that opens or edits their files. `execute` runs in their lab
- Long output: pass `--json` and read the fields you need
- `file:download` takes `path` relative to the server root, not the shell directory; the file lands in the download folder of the computer that runs the browser tab, not on the server
- `file:download` exits 5 on a missing file or a directory; exit 0 means the browser download started, not that it finished
- When `--list` lacks `file:download`, the saved allowlist predates the command; the user adds it with the Add to command executor button in the Commands Reference tab
- `activity` marks the server active once; the hub culls it after its idle timeout counted from the last mark. While work the user asked for runs, repeat it at an interval the user names, shorter than that timeout; never loop without the user's word

## How-to

Every example also carries `--purpose` and `--owner`, per the rule above.

- New terminal: `jupyterlab-commands execute terminal:create-new`; add `--args '{"cwd": "projects"}'` to start it in a folder
- Notification: `jupyterlab-commands execute apputils:notify --args '{"message": "Training finished", "type": "info"}'`
- Open a file: `jupyterlab-commands execute docmanager:open --args '{"path": "report.ipynb"}'`
- New notebook: `jupyterlab-commands execute notebook:create-new --args '{"kernelName": "python3"}'`
- Download a file: `jupyterlab-commands execute file:download --args '{"path": "data/report.csv"}'`
- Reload the workspace: `jupyterlab-commands execute workspace-ui:open --args '{"workspace": "default"}'`

### Run a local web app in the lab with all permissions

1. Serve the app on loopback only: `python3 -m http.server 8000 --bind 127.0.0.1`
2. Build the URL the lab proxies: `<lab base>/proxy/8000/<path>`, where `<lab base>` is the lab address in the browser, for example `http://127.0.0.1:8888`
3. Open it:

```bash
jupyterlab-commands execute workspace-page:open --args '{"url": "http://127.0.0.1:8888/proxy/8000/index.html", "title": "My app", "icon": "http://127.0.0.1:8888/proxy/8000/favicon.ico", "policy": {"sandbox": null}}' --purpose "show the app" --owner "my-agent"
```

`"policy": {"sandbox": null}` removes the iframe sandbox, so the app keeps the lab origin: its scripts, `localStorage`, cookies and POSTs reach the lab. Without `policy`, the iframe runs under the default sandbox `allow-scripts`: scripts run, but the origin is opaque, so the page has no lab session, no storage or cookies, and its requests do not reach the lab. Use the default for a page that only displays, and `sandbox: null` only for a page served from `/proxy/<port>/` that must keep state or post data.

<!-- improved 2026-10-28 | body 356→345w / 21→21L | quality 28/28 assertions, 1 blinded grader (n=1/cell, uncalibrated) | trigger 4/8 held-out | on claude-opus-5-5 | via improve-skill -->
