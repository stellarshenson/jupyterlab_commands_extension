# Acceptance Criteria - Commands Executor

What the command executor guarantees when a terminal runs a JupyterLab command: the browser tab owns the command registry and runs only allowlisted commands, the server relay forwards a request to the most recently registered tab, and the `jupyterlab-commands` CLI reports each failure with its own exit code.

## Authors

- `@kj` Konrad Jelen

## Package identity `RENAME`

Package, import and command names after the rename, and the installed extension registration.

- [x] `ACC-RENAME-1` **Identity files use the new package name** - CRITICAL; `package.json`, `pyproject.toml`, `install.json` and the server-config file all name `jupyterlab_commands_extension`; tracked build, source, workflow and documentation files contain no occurrence of the pre-rename package name, and the journal keeps its historical entries.
  - evidence: package.json:2, pyproject.toml:6 and install.json:3 name jupyterlab_commands_extension; git grep over tracked build, source, workflow and documentation files excluding logs and .claude/JOURNAL.md exits 1 with no output
  - test: grep the identity files for both names and assert the new name is present and the old name is absent
  - test-tags: MANUAL
  - log: 2026-10-18T00:51:49Z @kj added
  - log: 2026-10-18T00:53:10Z @kj edited text "`package.json`, `pyproject.toml`, `install.json` and the server-config file all name `jupyterlab_commands_extension`; no tracked file mentions `jupyterlab_show_commands_reference_extension`." -> "`package.json`, `pyproject.toml`, `install.json` and the server-config file all name `jupyterlab_commands_extension`; tracked build, source, workflow and documentation files contain no `jupyterlab_show_commands_reference_extension`, and the journal keeps its historical entries."; test-tags "UNIT" -> "MANUAL"
  - log: 2026-10-18T00:53:20Z @kj closed
  - log: 2026-10-18T00:55:09Z @kj edited text "`package.json`, `pyproject.toml`, `install.json` and the server-config file all name `jupyterlab_commands_extension`; tracked build, source, workflow and documentation files contain no `jupyterlab_show_commands_reference_extension`, and the journal keeps its historical entries." -> "`package.json`, `pyproject.toml`, `install.json` and the server-config file all name `jupyterlab_commands_extension`; tracked build, source, workflow and documentation files contain no occurrence of the pre-rename package name, and the journal keeps its historical entries."
- [x] `ACC-RENAME-2` **Extension registers under the new name** - CRITICAL; `jupyter labextension list` reports `jupyterlab_commands_extension` enabled OK, and `jupyter server extension list` validates the same package name.
  - evidence: logs/verify-pm-labextension.log:66 reports jupyterlab_commands_extension v1.0.11 enabled OK; logs/verify-pm-server-extension.log:53-55 reports the server extension enabled and 1.0.11 OK
  - test: run `jupyter labextension list` and `jupyter server extension list` and assert both name the extension and report OK
  - test-tags: MANUAL
  - log: 2026-10-18T00:51:49Z @kj added
  - log: 2026-10-18T00:53:10Z @kj edited test-tags "INTEGRATION" -> "MANUAL"
  - log: 2026-10-18T00:53:20Z @kj closed
- [x] `ACC-RENAME-3` **Console script points at the CLI** - HIGH; The wheel declares `jupyterlab-commands = "jupyterlab_commands_extension.cli:main"` and the installed `jupyterlab-commands --help` exits 0.
  - evidence: pyproject.toml:30-31 declares jupyterlab-commands = jupyterlab_commands_extension.cli:main; logs/test-galata.log:183 passed the --help test that asserts exit codes and token variables
  - test: run `jupyterlab-commands --help` and assert exit 0 and the exit-code epilog
  - test-tags: E2E
  - log: 2026-10-18T00:51:49Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed

## Allowed commands `ALLOW`

The `allowedCommands` setting: where it is edited, what it defaults to, and that an added command persists.

- [x] `ACC-ALLOW-4` **Editable in the Settings Editor** - HIGH; The plugin `jupyterlab_commands_extension:plugin` shows `Allowed commands` as an editable array whose defaults include `docmanager:open` and `apputils:notify`.
  - evidence: logs/test-galata.log:223 passed should show the allowedCommands array in the settings editor; schema/plugin.json declares the allowedCommands array with 8 defaults
  - test: open the Settings Editor, select the plugin and assert the array field lists both default ids
  - test-tags: E2E
  - log: 2026-10-18T00:51:53Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed
- [x] `ACC-ALLOW-5` **Added command persists across a reload** - CRITICAL; Adding a command writes through `settings.set`; after a full page reload the same row still shows `Added` and its button is disabled.
  - evidence: logs/test-galata.log:211 passed should show the document icon and keep an added command after reload; the test asserts settings.set persistence and a disabled Added button after reload
  - test: add a command, reload the page, reopen the reference tab and assert the button says Added and is disabled
  - test-tags: E2E
  - log: 2026-10-18T00:51:53Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed

## Reference tab `PANEL`

The Commands Reference tab: its icon, its add button and the added state after a click.

- [x] `ACC-PANEL-6` **Add button on a row outside the allowlist** - HIGH; A row whose command id is not in `allowedCommands` renders an enabled button labelled `Add to command executor`.
  - evidence: logs/test-galata.log:211 passed the reload test; it asserts the Add button and data-command-id on a row outside the allowlist
  - test: open the reference tab and assert the first add button is visible and carries a data-command-id
  - test-tags: E2E
  - log: 2026-10-18T00:51:53Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed
- [x] `ACC-PANEL-7` **Added state after the click** - HIGH; Clicking the button changes its text to `Added`, disables it and appends the command id to `allowedCommands`.
  - evidence: logs/test-galata.log:211 passed the reload test; it clicks Add and asserts the Added text, the disabled state and the id in allowedCommands
  - test: click Add and assert the text, the disabled state and the id present in the setting
  - test-tags: E2E
  - log: 2026-10-18T00:51:53Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed
- [x] `ACC-PANEL-8` **Tab carries the document icon** - LOW; The reference tab title renders the `ui-components:text-editor` icon.
  - evidence: logs/test-galata.log:211 passed the reload test; the test asserts the tab svg with data-icon ui-components:text-editor
  - test: open the reference tab and assert the tab icon svg has data-icon ui-components:text-editor
  - test-tags: E2E
  - log: 2026-10-18T00:51:53Z @kj added
  - log: 2026-10-18T00:53:20Z @kj closed

## Command line `CLI`

The `jupyterlab-commands` CLI: listing, executing, refusing, error codes and relay selection.

- [x] `ACC-CLI-9` **List prints the allowed command ids** - HIGH; `jupyterlab-commands --list` prints one allowed command id per line, and `list` is an alias for the flag.
  - evidence: logs/verify-pm-test.log:40-41 PASSED test_list_prints_the_allowed_commands and test_list_subcommand_is_an_alias_for_the_flag; logs/test-galata.log:170 passed the --list test
  - test: run `--list` and `list` against a registered tab and assert stdout is the allowed ids
  - test-tags: UNIT, E2E
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-10` **JSON list carries command arguments** - HIGH; `--list --json` returns `allowed` and one entry per command whose `args` describe the registry arguments, for example `path: string`.
  - evidence: logs/test-galata.log:170 passed --list names the default allowed commands and their arguments; logs/verify-pm-test.log:10-19 Jest 3 suites and 13 tests passed with allowlist.ts at 100 percent lines
  - test: run `--list --json` and assert allowed ids and the args of docmanager:open and apputils:notify
  - test-tags: UNIT, E2E
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-11` **Execute runs an allowed command** - CRITICAL; `jupyterlab-commands execute <id> --args <json>` runs the command in the registered tab, prints its result and exits 0.
  - evidence: logs/test-galata.log:182 passed execute runs an allowed command and refuses one outside the allowlist; logs/verify-pm-test.log:45 PASSED test_a_successful_execute_prints_the_data
  - test: register a tab, execute apputils:notify with a message and assert the notification appears and the exit code is 0
  - test-tags: UNIT, E2E
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-12` **Execute refuses a command outside the allowlist** - HIGH; An id outside `allowedCommands` makes the CLI exit 4, print that the command is not in the browser allowlist, and never reach the browser.
  - evidence: logs/verify-pm-test.log:43 PASSED test_a_command_outside_the_allowlist_exits_4; logs/test-galata.log:182 passed the refusal with exit 4
  - test: execute settingeditor:open and assert exit 4 and the refusal text on stderr
  - test-tags: UNIT, E2E
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-13` **No registered client** - MEDIUM; With no browser tab registered, the CLI exits 3 and reports that no browser tab has registered with the relay.
  - evidence: logs/verify-pm-test.log:42 PASSED test_no_registered_client_exits_3
  - test: execute a command with no registered tab and assert exit 3 and the stderr message
  - test-tags: UNIT
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-14` **Most recently registered tab receives the request** - HIGH; With two tabs registered, the relay queues the request for the most recently registered tab only.
  - evidence: logs/verify-pm-test.log:120 PASSED test_the_most_recently_registered_client_receives_requests
  - test: register two clients, execute a command and assert only the second client receives the pending request
  - test-tags: UNIT
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-15` **Execution timeout** - MEDIUM; When the browser does not answer, the relay raises `ExecutionTimeoutError` after the 30 second execution timeout and the CLI exits 5.
  - evidence: logs/verify-pm-test.log:114 PASSED test_execute_times_out_when_the_browser_does_not_answer
  - test: register a client that never posts a result and assert the timeout error after EXECUTION_TIMEOUT_S
  - test-tags: UNIT
  - log: 2026-10-18T00:51:57Z @kj added
  - log: 2026-10-18T00:53:23Z @kj closed
- [x] `ACC-CLI-27` **Explicit --url matches a listed record** - HIGH; A loopback --url that matches a listed server record on loopback literals, port, scheme and base path uses the address and token from the record; a non-loopback --url keeps the typed URL and receives no ambient token.
  - evidence: logs/verify-final-test.log:127-129,145 PASSED test_an_explicit_url_matches_a_listed_record_and_uses_its_token, test_an_explicit_url_is_replaced_by_the_matched_records_address, test_a_remote_url_keeps_its_address_and_gets_no_ambient_token, test_the_matcher_requires_the_port_scheme_and_base_path
  - test: run pytest jupyterlab_commands_extension/tests/test_cli.py -q with a decoy record listed first and assert the matched record address and token reach the stub, and a remote URL keeps its address with no token
  - test-tags: UNIT
  - log: 2026-10-18T01:14:19Z @kj added
  - log: 2026-10-18T01:49:46Z @kj closed
- [x] `ACC-CLI-28` **Trailing-slash matching and multi-record refusal** - HIGH; JUPYTERHUB_SERVICE_PREFIX matches a record base_url with the trailing slash normalised on both sides; when several records are listed and none matches, the CLI exits 2 and prints every listed URL.
  - evidence: logs/verify-final-test.log:105,132-133 PASSED test_several_servers_without_a_matching_prefix_are_refused and test_the_service_prefix_matches_a_record_with_either_trailing_slash for both slash permutations
  - test: run pytest jupyterlab_commands_extension/tests/test_cli.py -q with both prefix and record slash permutations and with two unmatched records; assert the selected record, exit code 2 and both listed URLs
  - test-tags: UNIT
  - log: 2026-10-18T01:14:19Z @kj added
  - log: 2026-10-18T01:49:46Z @kj closed
- [x] `ACC-CLI-29` **Loopback address families** - HIGH; The record table maps localhost to 127.0.0.1 and [::1], 0.0.0.0 to 127.0.0.1 and :: to [::1]; _server_url uses the first literal and _match_listed_server accepts every literal the typed host can reach.
  - evidence: logs/verify-final-test.log:134-138,139-144 PASSED test_a_localhost_url_matches_every_loopback_family_record for 127.0.0.1, ::1, 0.0.0.0, :: and localhost; test_the_server_url_uses_the_first_reachable_literal; test_the_record_table_reaches_both_families_for_localhost
  - test: run pytest jupyterlab_commands_extension/tests/test_cli.py -q and assert a localhost URL matches records bound to 127.0.0.1, ::1, 0.0.0.0, :: and localhost, and the built URL uses 127.0.0.1 for localhost
  - test-tags: UNIT
  - log: 2026-10-18T01:14:19Z @kj added
  - log: 2026-10-18T01:49:46Z @kj closed
- [x] `ACC-CLI-30` **Help content and colour-independent test** - MEDIUM; Top-level help names every environment variable and exit code; each subcommand prints one to three examples and every flag has help; the help test sets PYTHON_COLORS=0 so colour never changes the text; list help names --json for argument schemas.
  - evidence: logs/verify-final-test.log:146-147 PASSED test_list_json_carries_each_allowed_commands_argument_schema and test_help_names_variables_exit_codes_examples_and_flags, which sets PYTHON_COLORS=0
  - test: run pytest jupyterlab_commands_extension/tests/test_cli.py -q and assert the top-level help names the variables and exit codes, each subcommand prints examples, every flag has help, and list help names --json
  - test-tags: UNIT
  - log: 2026-10-18T01:14:19Z @kj added
  - log: 2026-10-18T01:49:46Z @kj closed

## Authentication and token handling `GUARD`

Server authentication on every relay route and token handling by the CLI.

- [x] `ACC-GUARD-16` **Every relay route requires authentication** - CRITICAL; A request with no authenticated user and a request with a wrong token both answer 403 on the register route.
  - evidence: logs/verify-pm-test.log:54 PASSED test_an_unauthenticated_request_is_rejected, :63 PASSED test_a_wrong_token_is_rejected_over_http, :126 every request handler requires authentication
  - test: call register with user=None and with a wrong token and assert 403 in both cases
  - test-tags: UNIT, INTEGRATION
  - log: 2026-10-18T00:52:00Z @kj added
  - log: 2026-10-18T00:53:27Z @kj closed
- [x] `ACC-GUARD-17` **Token travels in the Authorization header** - CRITICAL; The CLI reads `JUPYTERHUB_API_TOKEN`, `JPY_API_TOKEN` or `JUPYTER_TOKEN` and sends `Authorization: token <value>`; `_clean_url` removes credentials and the token query before the request.
  - evidence: logs/verify-pm-test.log:38-39 PASSED test_the_environment_token_reaches_the_request and test_an_explicit_token_overrides_the_environment; cli.py _clean_url strips credentials and the query before the request
  - test: record requests to the stub and assert the Authorization header carries the token and the path carries none
  - test-tags: UNIT
  - log: 2026-10-18T00:52:00Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
- [x] `ACC-GUARD-18` **Token never printed** - CRITICAL; No CLI output, error or help text contains the token.
  - evidence: logs/test-galata.log:170,182,183 passed with expectNoToken on --list, --list --json, execute, refused execute and --help, asserting stdout and stderr contain no token
  - test: run --list, execute and --help against a recording stub and assert stdout and stderr contain no token
  - test-tags: E2E
  - log: 2026-10-18T00:52:00Z @kj added
  - log: 2026-10-18T00:53:10Z @kj edited test-tags "UNIT, E2E" -> "E2E"
  - log: 2026-10-18T00:53:28Z @kj closed
- [x] `ACC-GUARD-26` **Token sources and the argv warning** - CRITICAL; `JUPYTERLAB_COMMANDS_TOKEN` is checked first for any target, remote included; `JUPYTERHUB_API_TOKEN`, `JPY_API_TOKEN` and `JUPYTER_TOKEN` are used only for a loopback target, in that order; a matched record token comes before the ambient variables; `--token` still works but its help says the secret is visible in `/proc/<pid>/cmdline` and points at `JUPYTERLAB_COMMANDS_TOKEN`.
  - evidence: logs/verify-final-test.log:106-109 PASSED test_detect_token_order; :130-131 PASSED test_the_dedicated_token_reaches_a_remote_target and test_the_dedicated_token_beats_a_listed_record; :127 PASSED test_an_explicit_url_matches_a_listed_record_and_uses_its_token with the record token beating JUPYTER_TOKEN; :145 PASSED test_a_remote_url_keeps_its_address_and_gets_no_ambient_token; :147 PASSED test_help_names_variables_exit_codes_examples_and_flags with the argv warning
  - test: run pytest jupyterlab_commands_extension/tests/test_cli.py -q and assert the dedicated variable reaches a remote stub, the ambient variables do not, the record token is used when the dedicated variable is unset, and the --token help names argv and the variable
  - test-tags: UNIT
  - log: 2026-10-18T01:14:19Z @kj added
  - log: 2026-10-18T01:15:46Z @kj edited text "JUPYTERLAB_COMMANDS_TOKEN is checked first for any target, remote included; JUPYTERHUB_API_TOKEN, JPY_API_TOKEN and JUPYTER_TOKEN are used only for a loopback target, in that order; a matched record token comes before the ambient variables; --token still works but its help says the secret is visible in /proc/<pid>/cmdline and points at JUPYTERLAB_COMMANDS_TOKEN." -> "`JUPYTERLAB_COMMANDS_TOKEN` is checked first for any target, remote included; `JUPYTERHUB_API_TOKEN`, `JPY_API_TOKEN` and `JUPYTER_TOKEN` are used only for a loopback target, in that order; a matched record token comes before the ambient variables; `--token` still works but its help says the secret is visible in `/proc/<pid>/cmdline` and points at `JUPYTERLAB_COMMANDS_TOKEN`."
  - log: 2026-10-18T01:49:47Z @kj closed

## Agent skill `SKILL`

The agent skill shipped inside the wheel and installed with the package.

- [x] `ACC-SKILL-19` **Wheel installs the agent skill** - MEDIUM; The wheel maps `.agents/skills/jupyterlab-commands-extension` to `share/jupyter/agents/skills/jupyterlab-commands-extension`, and the installed `SKILL.md` equals the repository copy.
  - evidence: logs/verify-pm-test.log PASSED test_installed_skill_matches_the_repository_copy in the 45-test run; pyproject.toml shared-data maps .agents/skills to share/jupyter/agents/skills
  - test: run pytest jupyterlab_commands_extension/tests/test_skill.py and assert the installed file equals the repository file
  - test-tags: INTEGRATION
  - log: 2026-10-18T00:52:00Z @kj added
  - log: 2026-10-18T00:53:10Z @kj edited test-tags "UNIT, INTEGRATION" -> "INTEGRATION"
  - log: 2026-10-18T00:53:28Z @kj closed

## Test suites `TESTS`

The four test tiers that prove the executor: pytest handlers, pytest integration, Jest and Galata.

- [x] `ACC-TESTS-20` **pytest handler tests cover the HTTP contract** - HIGH; `test_handlers.py` proves route registration under a hub base URL, rejection of an unauthenticated request, list, execute, allowlist refusal, unknown command, no client, pending timeout and unknown result.
  - evidence: logs/verify-pm-test.log PASSED all 10 test_handlers.py tests, including test_routes_land_under_a_hub_base_url, test_an_unauthenticated_request_is_rejected and test_a_result_for_an_unknown_request_id_does_not_crash
  - test: run pytest jupyterlab_commands_extension/tests/test_handlers.py -q and assert every test passes
  - test-tags: UNIT
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
- [x] `ACC-TESTS-21` **pytest integration tests run over HTTP** - HIGH; `test_integration.py` registers, lists, executes and collects a result over the real server, and proves that a wrong token and an outside-allowlist command answer 403.
  - evidence: logs/verify-pm-test.log PASSED test_register_list_execute_and_result_over_http, test_a_wrong_token_is_rejected_over_http and test_execute_outside_the_allowlist_returns_403_over_http
  - test: run pytest jupyterlab_commands_extension/tests/test_integration.py -q and assert three tests pass
  - test-tags: INTEGRATION
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
- [x] `ACC-TESTS-22` **Jest unit tests pass** - MEDIUM; `jlpm test` passes three suites and 13 tests, including 100 percent line coverage of `allowlist.ts`.
  - evidence: logs/verify-pm-test.log:18-19 Test Suites 3 passed, Tests 13 passed; the coverage table shows allowlist.ts at 100 percent lines
  - test: run jlpm test and assert 3 suites and 13 tests passed
  - test-tags: UNIT
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
- [x] `ACC-TESTS-23` **Galata UI and CLI tests pass** - HIGH; The Galata suite passes six tests across the UI and CLI specs, covering the icon, add button, reload persistence, settings editor, list, execute, refusal and help.
  - evidence: logs/test-galata.log:170-225 six tests passed across jupyterlab_commands_cli.spec.ts and jupyterlab_commands_extension.spec.ts
  - test: run `jlpm playwright test` in ui-tests and assert six tests pass
  - test-tags: E2E
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed

## Documentation `DOCS`

The README sections a user and an agent need to install and operate the executor.

- [x] `ACC-DOCS-24` **README documents install and operation** - MEDIUM; README states the package name, the pip install command, the CLI behaviour and exit codes, the allowlist path and defaults, the add button and Added state, the tab icon and the agent skill location.
  - evidence: README.md headings at lines 20, 34, 42, 56 and 64 cover Features, Installation, Command line, Allowlist and Agent skill; line 37 is pip install jupyterlab_commands_extension; the Command line section at line 52 states the five exit codes (0 success, 2 discovery or usage error, 3 no browser client, 4 command not allowed, 5 execution error); the allowlist defaults, Add/Added button, tab icon and agent skill path appear under those headings
  - test: read README.md and assert each named section and fact is present
  - test-tags: MANUAL
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
  - log: 2026-10-18T02:33:48Z @kj edited evidence "README.md headings at lines 20, 34, 42, 50 and 58 cover Features, Installation, Command line, Allowlist and Agent skill; line 37 is pip install jupyterlab_commands_extension; the CLI, exit codes, defaults and skill path appear under those headings" -> "README.md headings at lines 20, 34, 42, 56 and 64 cover Features, Installation, Command line, Allowlist and Agent skill; line 37 is pip install jupyterlab_commands_extension; the Command line section at line 52 states the five exit codes (0 success, 2 discovery or usage error, 3 no browser client, 4 command not allowed, 5 execution error); the allowlist defaults, Add/Added button, tab icon and agent skill path appear under those headings"; reason: evidence cited stale heading lines and asserted exit-code coverage the README did not have; the README now states the five codes and the evidence cites the post-edit lines
- [x] `ACC-DOCS-25` **README badges name the renamed packages** - LOW; The GitHub Actions, npm and PyPI badges point at repository and package names `jupyterlab_commands_extension` and `jupyterlab-commands-extension`.
  - evidence: README.md:3-5 badges point at github.com/stellarshenson/jupyterlab_commands_extension, npm jupyterlab_commands_extension and PyPI jupyterlab-commands-extension
  - test: read the badge URLs in README.md and assert the repository and package names
  - test-tags: MANUAL
  - log: 2026-10-18T00:52:04Z @kj added
  - log: 2026-10-18T00:53:28Z @kj closed
