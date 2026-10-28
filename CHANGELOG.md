# Changelog

<!-- <START NEW CHANGELOG ENTRY> -->

## [1.1.7] - 2026-10-29

### Added

- `jupyterlab-commands execute` accepts `--purpose` (at most 25 words) and `--owner`; both are optional in the CLI and required by the agent skill, and both are written to the execute audit line
- `workspace-ui:open` joins the default `allowedCommands` list

### Changed

- Each execute audit line now carries the optional purpose and the owner after the remote IP

## [1.1.5] - 2026-10-28

### Changed

- Every user-facing string passes through the JupyterLab translation bundle: command labels and captions, the palette category, the tab title, the table headers, the filter placeholder and the executor buttons; `@jupyterlab/translation` joins the runtime dependencies
- The Commands Reference widget loads when the tab is first opened instead of at application start, and the relay builds its URLs from the server connection settings

### Fixed

- `jlpm run lint:check` reports no warnings; the 17 eslint warnings the sources carried are cleared

## [1.1.4] - 2026-10-28

### Changed

- No functional change; the patch release re-publishes the 1.1.3 content with refreshed package metadata

## [1.1.3] - 2026-10-28

### Added

- Every `jupyterlab-commands execute` request writes one line to the JupyterLab server log: INFO on success, WARNING on refusal, timeout or failure, naming the command ID, the arguments cut at 500 characters, the elapsed milliseconds and the caller's remote IP; no token is ever logged
- The agent skill states the `file:download` path, destination and exit codes, names the Add to command executor remedy for an older saved allowlist, and carries its improvement certificate

### Changed

- The Commands Reference table uses a fixed layout with single-line cells, 10 px uppercase headers, a compact in-table Add button and the design system's filter field
- The table adapts to its own panel width: Description hides below 1100 px and Arguments below 900 px, while Command ID, Label and the action stay visible from 760 px up

### Fixed

- The Commands Reference table no longer scrolls sideways or stretches its rows when the panel narrows
- The lint and link CI gates no longer trip on the pm-tools tracker line ending or the placeholder hosts recorded in the defect tracker

## [1.1.1] - 2026-10-28

### Added

- `jupyterlab-commands execute file:download --args '{"path": "data/report.csv"}'` downloads a lab file in the browser tab that runs the relay, so the file lands on the user's computer; the path must exist and a folder is refused
- `file:download` joins the default `allowedCommands` list; a saved list keeps its own entries and gains the id through the Add to command executor button
- The agent skill triggers on downloading a lab file to the user's computer

## [1.0.18] - 2026-10-20

### Added

- `jupyterlab-commands activity` marks the server active in JupyterHub: it posts the hub notifier body to `$JUPYTERHUB_ACTIVITY_URL` with the hub API token, so an agent in a terminal with no browser tab keeps the session from being culled as idle while work runs
- Hub refusals (400, 403, 404) print the hub's own message; `--json` returns `{"ok": false, "status", "message"}`
- The agent skill triggers on keeping the JupyterHub session from being culled as idle

### Changed

- Tracker ids carry a subject code, for example `ACC-CLI-32-ACTIVITY`

## [1.0.17] - 2026-10-19

### Fixed

- The source distribution no longer includes the internal `tmp/` workflow files that 1.0.16 shipped; the wheel was not affected

## [1.0.16] - 2026-10-18

### Added

- `jupyterlab-commands` CLI with `list` and `execute`, running one allowed command in the selected browser tab
- Editable `allowedCommands` setting with vetted defaults, plus an **Add to command executor** button and document icon in the reference tab
- Agent skill for the CLI, shipped in the wheel
- Acceptance criteria and defect trackers under `docs/`

### Changed

- Package renamed to `jupyterlab_commands_extension` across PyPI, npm, the GitHub repository and plugin IDs
- Template upgraded to copier v4.6.5 and Makefile v1.46

### Fixed

- Token stays in the Authorization header: redirects are refused and loopback addresses bypass proxies
- Concurrent allowlist writes no longer drop a command added in another tab
- Relay selection stays with the most recently registered browser tab
- CLI matches typed base paths against listed server records and strips only the last Lab segment

<!-- <END NEW CHANGELOG ENTRY> -->
