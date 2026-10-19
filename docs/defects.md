# Defects - Commands Executor

`[ ]` open, `[x]` fixed. Dated notes under each track how it evolved.

## Authors

- `@kj` Konrad Jelen

## Galata test environment `GALATA`

The browser test server used by the Galata suite: fixture directories, teardown and the trash path.

- [x] `DEF-GALATA-1-TRASH` **Galata teardown DELETE fails on the container trash path** - MINOR; every Galata teardown DELETE answered 400 send2trash failed: [Errno 13] Permission denied on /.Trash-1000 while the six tests passed; cause: the container has no writable trash directory and the image config enables trash for the concrete contents manager; fix: ui-tests/jupyter_server_test_config.py sets delete_to_trash False on ContentsManager and AsyncLargeFileManager.
  - evidence: JUPYTER_TEST_PORT=8899 jlpm playwright test from ui-tests exited 0 with 6 passed; logs/verify-final-galata.log has 0 send2trash failures and 0 400 DELETE responses after ui-tests/jupyter_server_test_config.py set c.AsyncLargeFileManager.delete_to_trash = False
  - repro: run the Galata suite and read the web server log: every DELETE /api/contents answers 400 with send2trash failed on /.Trash-1000; the tests still pass
  - test-tags: E2E
  - root-cause: 2026-10-18T01:49:41Z @kj the image jupyter_lab_config.py sets FileContentsManager, AsyncFileContentsManager and AsyncLargeFileManager delete_to_trash True; traitlets applies the concrete class section after ContentsManager and the server uses AsyncLargeFileManager, so the test config must disable it on that concrete class
  - root-cause: 2026-10-18T00:52:09Z @kj send2trash moves the fixture directory to `/.Trash-1000`, which the container refuses; the Jupyter Server contents handler turns the failed move into 400
  - log: 2026-10-18T00:52:09Z @kj added
  - log: 2026-10-18T01:49:37Z @kj amended text "every Galata teardown DELETE answers 400 `send2trash failed: [Errno 13] Permission denied: b'/.Trash-1000'` while the six tests still pass; cause: the container has no writable trash directory; fix: pending, set `ContentsManager.use_trash = False` in the Galata test server config; `ui-tests/jupyter_server_test_config.py`." -> "every Galata teardown DELETE answered 400 send2trash failed: [Errno 13] Permission denied on /.Trash-1000 while the six tests passed; cause: the container has no writable trash directory and the image config enables trash for the concrete contents manager; fix: ui-tests/jupyter_server_test_config.py sets delete_to_trash False on ContentsManager and AsyncLargeFileManager."
  - log: 2026-10-18T01:49:41Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded TRASH

## Authentication and token handling `GUARD`

Token handling defects in the CLI and the relay.

- [x] `DEF-GUARD-2-HEADER-LEAK` **Rejected header token is printed in the error** - CRITICAL; cli.py passed the token to http.client.putheader; a token carrying a CR, an LF or a non-latin-1 character made putheader raise ValueError, whose text quotes the token, and the CLI printed it. The fix translates ValueError into CliError naming the header constraint with no token.
  - evidence: logs/verify-final-test.log:112-114 PASSED test_a_token_an_http_header_cannot_carry_exits_2 for CR, LF and non-latin-1 tokens; exit 2, no token part on stderr, no HTTP request sent
  - related: ACC-GUARD-18-TOKEN-HIDDEN
  - repro: run jupyterlab-commands with --token set to a value ending in a carriage return against any target; before the fix stderr carried that token text, after the fix it exits 2 and names the HTTP header constraint
  - test-tags: UNIT
  - root-cause: 2026-10-18T01:49:13Z @kj the ValueError text from http.client quotes the offending header value; the CLI let the exception message reach stderr instead of translating it
  - log: 2026-10-18T01:49:13Z @kj added
  - log: 2026-10-18T01:49:33Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded HEADER-LEAK
- [x] `DEF-GUARD-5-REDIRECT` **CLI follows a redirect and sends the token to the redirect host** - MAJOR; cli.py _post used urllib's default redirect handler: a 3xx copied the Authorization header to the Location host, turned the POST into a GET, and returned that host's JSON as success. The fix installs a _NoRedirect handler on both openers, so a 3xx raises HTTPError and exits 5.
  - evidence: pytest jupyterlab_commands_extension/tests/test_cli.py::test_a_redirect_is_refused_and_never_reaches_the_redirect_host passed; make test 78 passed; the redirect target recorded 0 requests and the CLI exited 5
  - related: ACC-GUARD-17-HEADER
  - repro: point --url at a stub that answers 302 with a Location to a second stub; before the fix the second stub received GET with Authorization: token <secret> and the CLI reported success; after the fix it exits 5 and the second stub receives nothing
  - test-tags: UNIT
  - root-cause: 2026-10-18T02:09:02Z @kj urllib.request.HTTPRedirectHandler copies every non-content header and converts a redirected POST to a GET; the CLI used the default opener chain
  - log: 2026-10-18T02:09:02Z @kj added
  - log: 2026-10-18T02:09:10Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded REDIRECT
- [x] `DEF-GUARD-11-PROXY` **Proxy receives the record token for 127.0.0.2 and non-loopback local records** - MAJOR; _is_loopback accepted only 127.0.0.1, localhost and ::1, so _post proxied 127.0.0.2 URLs and listed records bound to 127.0.0.2 or a non-loopback local address, with the record token in Authorization; the proxy could answer for the lab. The fix accepts every loopback address, marks listed records local and uses no ProxyHandler.
  - evidence: pytest jupyterlab_commands_extension/tests/test_cli.py -q 64 passed; make test 91 passed; test_a_record_bound_to_127_0_0_2_bypasses_the_proxy asserts the 127.0.0.2 stub got token record-token and the recording proxy got 0 requests; test_a_non_loopback_record_is_requested_locally_with_its_token asserts local=True; test_a_local_post_uses_an_empty_proxy_handler_for_a_non_loopback_url asserts ProxyHandler({})
  - related: ACC-GUARD-17-HEADER
  - repro: with http_proxy set and no_proxy unset, run --list --url http://127.0.0.2:<port>, or with a listed record bound to 127.0.0.2 or 192.0.2.10; before the fix the recording proxy received Authorization: token <record token> and the CLI printed its answer; after the fix the stub receives the request and the proxy 0 requests
  - test-tags: UNIT
  - root-cause: 2026-10-18T02:59:44Z @kj the predicate inspected only the literal hosts in _LOOPBACK_URL_HOSTS, and _post had no input saying a listed record names this host; that fact cannot be read from URL text alone
  - log: 2026-10-18T02:59:44Z @kj added
  - log: 2026-10-18T02:59:48Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded PROXY
- [x] `DEF-GUARD-12-LOOPBACK` **\_is_loopback missed legacy local spellings and wildcard clients** - MAJOR; ipaddress.ip_address rejects legacy numeric spellings the resolver accepts (127.1, 2130706433, 0x7f000001, 0177.0.0.1) and the wildcards 0.0.0.0 and ::, so _post sent the token to the proxy. The fix resolves non-literal hosts with getaddrinfo and requires every address to be loopback or unspecified.
  - evidence: pytest jupyterlab_commands_extension/tests/test_cli.py -q 79 passed; make test 106 passed (Jest 16, pytest 106) with exit 0; test_is_loopback_accepts_every_loopback_address covers 127.1, 2130706433, 0x7f000001, 0177.0.0.1, 0.0.0.0 and ::; test_is_loopback_resolves_a_name_and_accepts_only_all_local covers resolver semantics; test_is_loopback_treats_a_resolver_failure_as_remote; test_a_legacy_local_spelling_bypasses_the_proxy asserts the stub got token dedicated-token and the proxy received 0 requests
  - related: ACC-GUARD-17-HEADER
  - repro: with http_proxy set and no_proxy unset, run --list --url http://127.1:<stub port> (also 2130706433, 0x7f000001, 0177.0.0.1, 0.0.0.0); before the fix the recording proxy received Authorization: token <token> and its answer was printed while the stub received 0 requests; after the fix the stub receives the token and the proxy 0 requests
  - test-tags: UNIT
  - root-cause: 2026-10-18T03:19:38Z @kj the predicate inspected URL text with ipaddress.ip_address only, a narrower grammar than the resolver used by the connection, so the locality check and the connect disagreed about what the host means
  - log: 2026-10-18T03:19:38Z @kj added
  - log: 2026-10-18T03:19:40Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded LOOPBACK

## Command line `CLI`

Defects in relay selection and the CLI request flow.

- [x] `DEF-CLI-3-SELECTION` **Polling a second tab moves the relay selection** - MAJOR; RelayState.next_request assigned the selected client to whichever tab polled, so a second tab long poll took selection from the most recently registered tab. The fix leaves selection to register only; next_request waits without writing it.
  - evidence: logs/verify-final-test.log:170 PASSED test_polling_does_not_change_which_client_is_selected; the first client poll returns None and the second client receives the request
  - related: ACC-CLI-14-NEWEST-TAB
  - repro: register client first then client second, start next_request(second), start next_request(first, timeout=0.05), then execute; before the fix first received the request, after the fix second does
  - test-tags: UNIT
  - root-cause: 2026-10-18T01:49:17Z @kj the long-poll path wrote _selected as a side effect of waiting instead of leaving selection to register
  - log: 2026-10-18T01:49:17Z @kj added
  - log: 2026-10-18T01:49:33Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded SELECTION
- [x] `DEF-CLI-6-STRIP-PATH` **\_strip_lab_path misparses a bare app URL whose base path ends in lab** - MAJOR; _strip_lab_path used rfind('/lab/'), so http://host/user/lab/lab reduced to /user instead of /user/lab, and a tree path with a lab segment reduced to /user/alice/lab/tree; _match_listed_server then returned None. The fix strips at the first /lab/tree marker, otherwise a trailing /lab.
  - evidence: pytest test_clean_url_removes_the_lab_application_path passed for 7 URL shapes including /user/lab/lab and /lab/tree/lab/notebook.ipynb; make test 78 passed
  - related: ACC-CLI-27-URL-MATCH
  - repro: call cli._clean_url('http://host/user/lab/lab'); before the fix it returned http://host/user, after the fix http://host/user/lab; the same rule cleans /user/alice/lab/tree/lab/notebook.ipynb to /user/alice
  - test-tags: UNIT
  - root-cause: 2026-10-18T02:09:13Z @kj rfind('/lab/') matched the earlier lab segment in '/user/lab/lab' because the trailing lab carries no slash, and matched a lab directory inside a tree path instead of the application marker
  - log: 2026-10-18T02:09:13Z @kj added
  - log: 2026-10-18T02:09:15Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded STRIP-PATH
- [x] `DEF-CLI-9-BASE-PATH` **A typed server base path ending in lab is stripped before the record match** - MAJOR; _clean_url stripped a trailing /lab before the record match, so --url http://host/user/lab became /user, missed the record with base /user/lab/, sent the ambient token to the wrong path and exited 2. The fix matches the sanitized typed path against the records first and falls back to the stripped form.
  - evidence: pytest test_a_typed_base_path_ending_in_lab_matches_the_record_before_stripping passed for /user/lab and /user/lab/lab: exit 0, request /user/lab/jupyterlab-commands/api/list with token record-token; make test 80 passed
  - related: ACC-CLI-27-URL-MATCH
  - repro: cli._resolve_target(argparse.Namespace(url='http://127.0.0.1:8888/user/lab', token=None)) with a record {port 8888, base_url '/user/lab/', token 'record-token'} resolved to http://127.0.0.1:8888/user with the ambient token; after the fix it resolves to the record address with record-token
  - test-tags: UNIT
  - root-cause: 2026-10-18T02:23:19Z @kj _clean_url removed the application path before _resolve_target consulted the record list, so a record whose base_url equals the typed path could never match; the strip heuristic cannot distinguish a bare base ending in lab from the application segment
  - log: 2026-10-18T02:23:19Z @kj added
  - log: 2026-10-18T02:23:24Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded BASE-PATH

## Allowed commands `ALLOW`

Defects in the allowedCommands setting handling.

- [x] `DEF-ALLOW-4-STALE-WRITE` **A stale settings composite drops a command added in another tab** - MAJOR; addAllowedCommand read the allowlist composite once and wrote the list plus the new id; a tab whose composite predated another tab save overwrote that tab entry, and concurrent Add clicks could lose one. The fix reloads the setting before the read and serializes writes through a promise queue.
  - evidence: logs/verify-final-test.log:6,18-19 PASS src/**tests**/allowlist.spec.ts; Test Suites 3 passed, Tests 16 passed; the suite keeps an entry another tab added and serializes two concurrent adds
  - related: ACC-ALLOW-5-PERSIST
  - repro: open two tabs, add command X in tab one, add command Y in tab two without reloading tab two; before the fix allowedCommands held only Y, after the fix it holds X and Y
  - test-tags: UNIT
  - root-cause: 2026-10-18T01:49:20Z @kj the write used a per-tab cached composite and an unserialized read-modify-write
  - log: 2026-10-18T01:49:20Z @kj added
  - log: 2026-10-18T01:49:33Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded STALE-WRITE

## Documentation `DOCS`

README and CLI help text that documents installation and operation

- [x] `DEF-DOCS-7-CLEARTEXT` **Documented remote examples send the token over cleartext http** - MAJOR; README.md and the CLI epilog showed --url http://remote-host:8888 with JUPYTERLAB_COMMANDS_TOKEN, so the Authorization header carrying the full-access token crossed the network in cleartext. The three examples now use https and the Authentication block states that a remote target must use TLS.
  - evidence: make test 78 passed including test_help_names_variables_exit_codes_examples_and_flags; README.md:47 and both cli.py epilog examples now use https for remote targets
  - related: ACC-DOCS-24-README
  - related: ACC-GUARD-17-HEADER
  - repro: read README.md:47 and the list and execute epilog examples in cli.py; before the fix all three showed http://remote-host:8888 with the token variable
  - test-tags: MANUAL
  - root-cause: 2026-10-18T02:09:18Z @kj the remote examples were written from the local http default without accounting for the Authorization header that carries the token
  - log: 2026-10-18T02:09:18Z @kj added
  - log: 2026-10-18T02:09:20Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded CLEARTEXT
- [x] `DEF-DOCS-8-SKILL-ROOT` **Skill install commands target different agent roots** - MEDIUM; README.md linked the pip-installed skill into ~/.agents/skills and the clone skill into ~/.claude/skills, so a stock Claude Code install never loaded the pip-installed skill while the command appeared to succeed. Both commands now create and link into ~/.claude/skills, and the introduction names Claude Code.
  - evidence: make test 78 passed; README.md both install commands now create and link into ~/.claude/skills, and the pip-install introduction names Claude Code
  - related: ACC-DOCS-24-README
  - repro: read the two skill install commands in README.md; before the fix they used ~/.agents/skills and ~/.claude/skills respectively
  - test-tags: MANUAL
  - root-cause: 2026-10-18T02:09:23Z @kj the two install paths were written independently and no sentence named the agent that reads each root
  - log: 2026-10-18T02:09:23Z @kj added
  - log: 2026-10-18T02:09:25Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded SKILL-ROOT
- [x] `DEF-DOCS-10-EXIT-CODES` **README omits the CLI exit codes required by ACC-DOCS-24-README** - MEDIUM; README.md named the subcommands and --json but carried no exit-code text in the worktree, index or HEAD, while checked ACC-DOCS-24-README requires the CLI behaviour and exit codes and its evidence claimed coverage. The Command line section now lists the five codes from cli.py.
  - evidence: pytest jupyterlab_commands_extension/tests/test_docs.py::test_readme_states_the_cli_exit_codes_in_the_command_line_section passed; make test 81 passed (Jest 16 passed, pytest 81 passed); README.md:52 states the five exit codes in the Command line section
  - related: ACC-DOCS-24-README
  - repro: grep -in 'exit' README.md exited 1 in the worktree, index and HEAD before the fix, while ACC-DOCS-24-README was checked on evidence claiming exit-code coverage
  - test-tags: UNIT
  - root-cause: 2026-10-18T02:33:54Z @kj the README documented the subcommand names and --json but no sentence carried the exit-code mapping; the checked evidence asserted coverage the file did not have
  - log: 2026-10-18T02:33:54Z @kj added
  - log: 2026-10-18T02:33:58Z @kj closed
  - log: 2026-10-19T19:37:14Z @kj coded EXIT-CODES
  - log: 2026-10-19T19:37:25Z @kj amended title "README omits the CLI exit codes required by ACC-DOCS-24" -> "README omits the CLI exit codes required by ACC-DOCS-24-README"; text "README.md named the subcommands and --json but carried no exit-code text in the worktree, index or HEAD, while checked ACC-DOCS-24 requires the CLI behaviour and exit codes and its evidence claimed coverage. The Command line section now lists the five codes from cli.py." -> "README.md named the subcommands and --json but carried no exit-code text in the worktree, index or HEAD, while checked ACC-DOCS-24-README requires the CLI behaviour and exit codes and its evidence claimed coverage. The Command line section now lists the five codes from cli.py."; reason: write the full id after code migration
  - log: 2026-10-19T19:37:25Z @kj edited repro "grep -in 'exit' README.md exited 1 in the worktree, index and HEAD before the fix, while ACC-DOCS-24 was checked on evidence claiming exit-code coverage" -> "grep -in 'exit' README.md exited 1 in the worktree, index and HEAD before the fix, while ACC-DOCS-24-README was checked on evidence claiming exit-code coverage"; reason: write the full id after code migration
- [x] `DEF-DOCS-13-SKILL-ACTIVITY` **Skill says activity keeps the hub session alive** - MEDIUM; SKILL.md line 18 said activity keeps the user's hub session alive; one call posts one timestamp and touches no login session, so an agent could call it once and report the server protected from the idle culler
  - evidence: SKILL.md activity bullet now says it marks the server active once and must repeat under the idle timeout; UNIT test_skill_states_that_activity_marks_the_server_active_once fails on the old line and passes; test_installed_skill_matches_the_repository_copy passes after make install; 130 pytest pass (logs/activity-skill-pytest.log)
  - related: ACC-CLI-32-ACTIVITY - the skill misstated what activity does
  - repro: read the activity bullet in .agents/skills/jupyterlab-commands-extension/SKILL.md; it says keeps the user's hub session alive
  - test-tags: UNIT
  - root-cause: 2026-10-19T19:45:56Z @kj the skill rule described the intent (keep alive) and not the action: _run_activity sends one POST and exits, and the hub idle culler counts from that timestamp
  - log: 2026-10-19T19:45:56Z @kj added
  - log: 2026-10-19T19:46:04Z @kj closed: fixed: activity bullet reworded
- [x] `DEF-DOCS-14-HELP-ACTIVITY` **activity help and README say one post keeps the server from the culler while work runs** - MEDIUM; activity --help and README.md line 52 said one post stops the hub culling the server while work runs; one call marks one moment and the idle timeout counts from the last mark, so a user who calls it once believes a long job is protected
  - evidence: UNIT test_help_names_variables_exit_codes_examples_and_flags asserts 'marks the server active once' and 'counted from the last mark'; it fails on the HEAD cli.py and passes on the new text (logs/activity-wording-red-green.log); 130 pytest pass after make install (logs/activity-wording-pytest.log)
  - related: ACC-CLI-32-ACTIVITY
  - repro: jupyterlab-commands activity --help prints 'so the hub does not cull the server as idle while work runs'; README.md line 52 says the same
  - test-tags: UNIT
  - root-cause: 2026-10-19T19:51:55Z @kj the round 1 fix corrected SKILL.md only; the same false sentence stayed in the activity subparser description in cli.py and in README.md line 52
  - log: 2026-10-19T19:51:55Z @kj added
  - log: 2026-10-19T19:52:02Z @kj closed: fixed: activity description and README.md line 52 reworded
