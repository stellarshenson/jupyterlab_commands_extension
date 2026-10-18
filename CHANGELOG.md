# Changelog

<!-- <START NEW CHANGELOG ENTRY> -->

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
