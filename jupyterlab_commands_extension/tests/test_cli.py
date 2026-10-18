"""Tests for the jupyterlab-commands CLI.

No live Jupyter server is used. Server discovery is exercised with a fake
``jupyter`` executable, and the HTTP calls go to a local stub server.
"""

import argparse
import json
import os
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jupyterlab_commands_extension import cli

ENVIRONMENT_VARIABLES = (
    "JUPYTERLAB_COMMANDS_TOKEN",
    "JUPYTERHUB_API_TOKEN",
    "JPY_API_TOKEN",
    "JUPYTER_TOKEN",
    "JUPYTER_PORT",
    "JUPYTERHUB_SERVICE_PREFIX",
    "JUPYTERHUB_SERVICE_URL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Keep the developer's own lab out of every test."""
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_discovery(tmp_path, monkeypatch):
    """Put a fake ``jupyter`` that lists no records first on PATH.

    Every test that does not need records runs with an empty list, so the
    developer's own running servers never reach the assertions.
    """
    directory = _write_fake_jupyter(tmp_path, [])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])


class _StubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # A redirect target records the GET it receives. A refused redirect
        # must leave this list empty, so no Authorization header is sent on.
        self.server.requests.append(
            {
                "method": "GET",
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
            }
        )
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        status, payload = self.server.responder(self.path, body)
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if self.server.location:
            self.send_header("Location", self.server.location)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host="127.0.0.1"):
        super().__init__((host, 0), _StubHandler)
        self.requests = []
        self.location = None
        self.responder = lambda path, body: (200, {"ok": True})


@pytest.fixture
def stub():
    server = _StubServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _base_url(stub):
    return f"http://127.0.0.1:{stub.server_address[1]}"


def _write_fake_jupyter(tmp_path, records):
    """Put a fake ``jupyter`` first on PATH, printing the given records."""
    lines = "\n".join(json.dumps(record) for record in records)
    script = tmp_path / "jupyter"
    script.write_text(
        "#!/bin/sh\ncat <<'JSON'\n" + lines + "\nJSON\n", encoding="utf-8"
    )
    script.chmod(0o755)
    return str(tmp_path)


def _record(port, base_url="/", token="record-token", hostname="127.0.0.1"):
    return {
        "port": port,
        "base_url": base_url,
        "token": token,
        "hostname": hostname,
    }


def test_server_selection_uses_the_service_prefix_and_record_token(
    stub, tmp_path, monkeypatch
):
    dead = _record(9, "/", "decoy-token")
    real = _record(stub.server_address[1], "/user/alice/", "record-token")
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/alice/")
    stub.responder = lambda path, body: (200, {"ok": True, "data": {"opened": True}})

    code = cli.main(
        ["execute", "docmanager:open", "--args", '{"path": "notebook.ipynb"}']
    )

    assert code == cli.EXIT_OK
    request = stub.requests[0]
    assert request["path"] == "/user/alice/jupyterlab-commands/api/execute"
    assert request["authorization"] == "token record-token"
    assert request["body"] == {
        "command": "docmanager:open",
        "args": {"path": "notebook.ipynb"},
    }


def test_several_servers_without_a_matching_prefix_are_refused(
    tmp_path, monkeypatch, capsys
):
    directory = _write_fake_jupyter(
        tmp_path, [_record(9, "/one/"), _record(10, "/two/")]
    )
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/nobody/")

    code = cli.main(["list"])

    assert code == cli.EXIT_USAGE
    error = capsys.readouterr().err
    assert "http://127.0.0.1:9/one" in error
    assert "http://127.0.0.1:10/two" in error


@pytest.mark.parametrize(
    "environment,expected",
    [
        ({}, None),
        ({"JUPYTER_TOKEN": "jupyter"}, "jupyter"),
        ({"JPY_API_TOKEN": "jpy", "JUPYTER_TOKEN": "jupyter"}, "jpy"),
        (
            {
                "JUPYTERHUB_API_TOKEN": "hub",
                "JPY_API_TOKEN": "jpy",
                "JUPYTER_TOKEN": "jupyter",
            },
            "hub",
        ),
    ],
)
def test_detect_token_order(monkeypatch, environment, expected):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert cli.detect_token() == expected


def test_the_environment_token_reaches_the_request(stub, monkeypatch):
    monkeypatch.setenv("JUPYTER_TOKEN", "ambient-token")
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(["--url", _base_url(stub), "--list"])

    assert code == cli.EXIT_OK
    assert stub.requests[0]["authorization"] == "token ambient-token"


def test_an_explicit_token_overrides_the_environment(stub, monkeypatch):
    monkeypatch.setenv("JUPYTER_TOKEN", "ambient-token")
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(
        ["--url", _base_url(stub), "--token", "explicit-token", "--list"]
    )

    assert code == cli.EXIT_OK
    assert stub.requests[0]["authorization"] == "token explicit-token"


@pytest.mark.parametrize(
    "token",
    [
        "carriage-return-token\r",
        "line-feed-token\nsecond-part",
        "non-latin-1-token-ж",
    ],
)
def test_a_token_an_http_header_cannot_carry_exits_2(stub, capsys, token):
    # http.client rejects a CR, an LF or a non-latin-1 character in a header
    # value, and its exception text quotes that value. The CLI must report the
    # refusal without printing the token.
    code = cli.main(
        ["--url", _base_url(stub), "--token", token, "execute", "docmanager:open"]
    )

    captured = capsys.readouterr()
    assert code == cli.EXIT_USAGE
    assert token not in captured.err
    for part in token.split():
        assert part not in captured.err
    assert "header" in captured.err
    assert stub.requests == []


def test_list_prints_the_allowed_commands(stub, capsys):
    stub.responder = lambda path, body: (
        200,
        {
            "ok": True,
            "client_id": "browser",
            "allowed": ["docmanager:open", "help:open"],
            "commands": [],
        },
    )

    code = cli.main(["--url", _base_url(stub), "--list"])

    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "docmanager:open\nhelp:open\n"


def test_list_subcommand_is_an_alias_for_the_flag(stub, capsys):
    stub.responder = lambda path, body: (
        200,
        {
            "ok": True,
            "client_id": "browser",
            "allowed": ["help:open"],
            "commands": [],
        },
    )

    code = cli.main(["--url", _base_url(stub), "list"])

    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "help:open\n"


def test_no_registered_client_exits_3(stub, capsys):
    stub.responder = lambda path, body: (
        503,
        {
            "error": {
                "code": "no-client",
                "message": "no browser tab has registered with the relay",
            }
        },
    )

    code = cli.main(["--url", _base_url(stub), "execute", "docmanager:open"])

    assert code == cli.EXIT_NO_CLIENT
    assert "no browser tab has registered" in capsys.readouterr().err


def test_a_command_outside_the_allowlist_exits_4(stub, capsys):
    stub.responder = lambda path, body: (
        403,
        {
            "error": {
                "code": "command-not-allowed",
                "message": "command 'help:open' is not in the browser allowlist",
            }
        },
    )

    code = cli.main(
        [
            "--url",
            _base_url(stub),
            "--token",
            "secret-token",
            "execute",
            "help:open",
        ]
    )

    captured = capsys.readouterr()
    assert code == cli.EXIT_NOT_ALLOWED
    assert "not in the browser allowlist" in captured.err
    assert "secret-token" not in captured.err
    assert "secret-token" not in captured.out


def test_a_redirect_is_refused_and_never_reaches_the_redirect_host(stub, capsys):
    # A 3xx must not be followed: urllib would copy the Authorization header
    # to the redirect target and turn the POST into a GET there, so the token
    # would reach a host the user did not name.
    target = _StubServer()
    target_thread = threading.Thread(target=target.serve_forever, daemon=True)
    target_thread.start()
    try:
        stub.location = f"http://127.0.0.1:{target.server_address[1]}/elsewhere"
        stub.responder = lambda path, body: (302, {"ok": True})

        code = cli.main(
            [
                "--url",
                _base_url(stub),
                "--token",
                "SECRET-TOKEN-xyz",
                "execute",
                "docmanager:open",
            ]
        )

        captured = capsys.readouterr()
        assert code == cli.EXIT_EXECUTION
        assert target.requests == []
        assert "SECRET-TOKEN-xyz" not in captured.err
        assert "SECRET-TOKEN-xyz" not in captured.out
    finally:
        target.shutdown()
        target.server_close()
        target_thread.join(timeout=5)


def test_a_forbidden_answer_without_the_relay_code_exits_2(stub, capsys):
    # Jupyter answers 403 to a missing or wrong token; that is not an allowlist
    # refusal, so it must not be reported as exit 4.
    stub.responder = lambda path, body: (403, {"message": "Forbidden"})

    code = cli.main(
        ["--url", _base_url(stub), "--token", "wrong-token", "execute", "help:open"]
    )

    assert code == cli.EXIT_USAGE
    assert "Forbidden" in capsys.readouterr().err


def test_a_successful_execute_prints_the_data(stub, capsys):
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "data": {"path": "notebook.ipynb"}},
    )

    code = cli.main(
        [
            "--url",
            _base_url(stub),
            "execute",
            "docmanager:open",
            "--args",
            '{"path": "notebook.ipynb"}',
        ]
    )

    assert code == cli.EXIT_OK
    output = capsys.readouterr().out
    assert '"path": "notebook.ipynb"' in output
    assert stub.requests[0]["body"] == {
        "command": "docmanager:open",
        "args": {"path": "notebook.ipynb"},
    }


def test_args_can_come_from_a_file(stub, tmp_path, capsys):
    arguments = tmp_path / "arguments.json"
    arguments.write_text('{"path": "README.md"}', encoding="utf-8")
    stub.responder = lambda path, body: (200, {"ok": True, "data": "opened"})

    code = cli.main(
        [
            "--url",
            _base_url(stub),
            "execute",
            "docmanager:open",
            "--args-file",
            str(arguments),
        ]
    )

    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "opened\n"
    assert stub.requests[0]["body"]["args"] == {"path": "README.md"}


def test_json_prints_the_machine_envelope(stub, capsys):
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "data": {"opened": True}},
    )

    code = cli.main(
        ["--url", _base_url(stub), "--json", "execute", "docmanager:open"]
    )

    assert code == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "data": {"opened": True},
    }


def test_arguments_that_are_not_a_json_object_exit_2(stub):
    code = cli.main(
        ["--url", _base_url(stub), "execute", "docmanager:open", "--args", "[1]"]
    )

    assert code == cli.EXIT_USAGE
    assert stub.requests == []


def test_an_unknown_command_exits_2(stub):
    stub.responder = lambda path, body: (
        404,
        {
            "error": {
                "code": "unknown-command",
                "message": "the browser does not register command 'no:such'",
            }
        },
    )

    code = cli.main(["--url", _base_url(stub), "execute", "no:such"])

    assert code == cli.EXIT_USAGE


def test_an_execution_failure_exits_5(stub, capsys):
    stub.responder = lambda path, body: (
        500,
        {
            "error": {
                "code": "execution-failed",
                "message": "the file does not exist",
            }
        },
    )

    code = cli.main(["--url", _base_url(stub), "execute", "docmanager:open"])

    assert code == cli.EXIT_EXECUTION
    assert "the file does not exist" in capsys.readouterr().err


def test_an_unreachable_server_exits_2(capsys):
    # Port 9 on loopback is closed, so the connection is refused.
    code = cli.main(
        ["--url", "http://127.0.0.1:9", "--token", "t", "execute", "docmanager:open"]
    )

    assert code == cli.EXIT_USAGE
    assert "cannot reach http://127.0.0.1:9" in capsys.readouterr().err


def test_an_explicit_url_matches_a_listed_record_and_uses_its_token(
    stub, tmp_path, monkeypatch
):
    dead = _record(9, "/", "decoy-token")
    real = _record(
        stub.server_address[1], "/", "record-token", hostname="0.0.0.0"
    )
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTER_TOKEN", "ambient-token")
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(
        ["--url", f"http://localhost:{stub.server_address[1]}", "--list"]
    )

    assert code == cli.EXIT_OK
    request = stub.requests[0]
    assert request["path"] == "/jupyterlab-commands/api/list"
    # The record's token beats the ambient variable for its own address.
    assert request["authorization"] == "token record-token"


def test_an_explicit_url_is_replaced_by_the_matched_records_address(
    stub, tmp_path, monkeypatch
):
    dead = _record(9, "/", "decoy-token")
    real = _record(
        stub.server_address[1], "/", "record-token", hostname="0.0.0.0"
    )
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])

    url, token, local = cli._resolve_target(
        argparse.Namespace(
            url=f"http://localhost:{stub.server_address[1]}", token=None
        )
    )

    assert url == f"http://127.0.0.1:{stub.server_address[1]}"
    assert token == "record-token"
    assert local is True


@pytest.mark.parametrize("typed_path", ["/user/lab", "/user/lab/lab"])
def test_a_typed_base_path_ending_in_lab_matches_the_record_before_stripping(
    stub, tmp_path, monkeypatch, typed_path
):
    dead = _record(9, "/", "decoy-token")
    real = _record(stub.server_address[1], "/user/lab/", "record-token")
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTER_TOKEN", "ambient-token")
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(["--url", _base_url(stub) + typed_path, "--list"])

    assert code == cli.EXIT_OK
    request = stub.requests[0]
    assert request["path"] == "/user/lab/jupyterlab-commands/api/list"
    assert request["authorization"] == "token record-token"


def test_a_remote_url_keeps_its_address_and_gets_no_ambient_token(monkeypatch):
    monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "ambient-token")
    captured = {}

    def fake_post(
        base_url, endpoint, payload, token, timeout, timeout_exit, *, local=False
    ):
        captured.update(base_url=base_url, token=token, local=local)
        return {"ok": True, "allowed": [], "commands": []}

    monkeypatch.setattr(cli, "_post", fake_post)

    code = cli.main(["--url", "http://192.0.2.10:8888", "--list"])

    assert code == cli.EXIT_OK
    assert captured == {
        "base_url": "http://192.0.2.10:8888",
        "token": None,
        "local": False,
    }


def test_the_dedicated_token_reaches_a_remote_target(monkeypatch):
    monkeypatch.setenv("JUPYTERLAB_COMMANDS_TOKEN", "remote-token")
    monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "ambient-token")
    captured = {}

    def fake_post(
        base_url, endpoint, payload, token, timeout, timeout_exit, *, local=False
    ):
        captured.update(base_url=base_url, token=token, local=local)
        return {"ok": True, "allowed": [], "commands": []}

    monkeypatch.setattr(cli, "_post", fake_post)

    code = cli.main(["--url", "http://192.0.2.10:8888", "--list"])

    assert code == cli.EXIT_OK
    assert captured["token"] == "remote-token"
    assert captured["local"] is False


def test_the_dedicated_token_beats_a_listed_record(stub, tmp_path, monkeypatch):
    dead = _record(9, "/", "decoy-token")
    real = _record(stub.server_address[1], "/", "record-token")
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTERLAB_COMMANDS_TOKEN", "dedicated-token")
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(["--url", _base_url(stub), "--list"])

    assert code == cli.EXIT_OK
    assert stub.requests[0]["authorization"] == "token dedicated-token"


@pytest.mark.parametrize(
    "prefix,record_base",
    [("/user/alice/", "/user/alice"), ("/user/alice", "/user/alice/")],
)
def test_the_service_prefix_matches_a_record_with_either_trailing_slash(
    stub, tmp_path, monkeypatch, prefix, record_base
):
    dead = _record(9, "/", "decoy-token")
    real = _record(stub.server_address[1], record_base, "record-token")
    directory = _write_fake_jupyter(tmp_path, [dead, real])
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", prefix)
    stub.responder = lambda path, body: (
        200,
        {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
    )

    code = cli.main(["list"])

    assert code == cli.EXIT_OK
    assert stub.requests[0]["path"] == (
        "/user/alice/jupyterlab-commands/api/list"
    )
    assert stub.requests[0]["authorization"] == "token record-token"


@pytest.mark.parametrize(
    "record_host", ["127.0.0.1", "::1", "0.0.0.0", "::", "localhost"]
)
def test_a_localhost_url_matches_every_loopback_family_record(record_host):
    record = _record(8899, "/", "record-token", hostname=record_host)

    assert cli._match_listed_server("http://localhost:8899", [record]) is record


@pytest.mark.parametrize(
    "record_host,literal",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("localhost", "127.0.0.1"),
        ("::1", "[::1]"),
        ("0.0.0.0", "127.0.0.1"),
        ("::", "[::1]"),
    ],
)
def test_the_server_url_uses_the_first_reachable_literal(record_host, literal):
    record = _record(8899, "/", "record-token", hostname=record_host)

    assert cli._server_url(record) == f"http://{literal}:8899"


def test_the_record_table_reaches_both_families_for_localhost():
    assert cli._LOOPBACK_HOST_FOR["localhost"] == ("127.0.0.1", "[::1]")
    assert cli._LOOPBACK_URL_HOSTS["localhost"] == ("127.0.0.1", "[::1]")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://127.0.0.2:8899", True),
        ("http://[::ffff:127.0.0.1]:8899", True),
        ("http://localhost.:8899", True),
        ("http://[0:0:0:0:0:0:0:1]:8899", True),
        ("http://127.1:8899", True),
        ("http://2130706433:8899", True),
        ("http://0x7f000001:8899", True),
        ("http://0177.0.0.1:8899", True),
        ("http://0.0.0.0:8899", True),
        ("http://[::]:8899", True),
        ("http://1.2.3:8899", False),
        ("http://192.0.2.10:8899", False),
        ("http://example.com:8899", False),
    ],
)
def test_is_loopback_accepts_every_loopback_address(url, expected):
    assert cli._is_loopback(url) is expected


@pytest.mark.parametrize(
    "addresses,expected",
    [
        (["127.0.0.1"], True),
        (["127.0.0.1", "192.0.2.10"], False),
    ],
)
def test_is_loopback_resolves_a_name_and_accepts_only_all_local(
    monkeypatch, addresses, expected
):
    calls = []

    def fake_getaddrinfo(host, port, *, type):
        calls.append((host, port, type))
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in addresses
        ]

    monkeypatch.setattr(cli.socket, "getaddrinfo", fake_getaddrinfo)

    assert cli._is_loopback("http://lab.internal:8899") is expected
    assert calls == [("lab.internal", None, socket.SOCK_STREAM)]


def test_is_loopback_treats_a_resolver_failure_as_remote(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(cli.socket, "getaddrinfo", fake_getaddrinfo)

    assert cli._is_loopback("http://lab.internal:8899") is False


def test_a_loopback_url_missing_from_the_literal_table_matches_no_record():
    # 127.0.0.2 is loopback but is not a key of _LOOPBACK_URL_HOSTS.
    assert cli._match_listed_server("http://127.0.0.2:8899", []) is None


def test_a_non_loopback_record_is_requested_locally_with_its_token(
    tmp_path, monkeypatch
):
    # Every listed record names this host, even when it binds a LAN address.
    directory = _write_fake_jupyter(
        tmp_path, [_record(8899, "/", "record-token", hostname="192.0.2.10")]
    )
    monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
    captured = {}

    def fake_post(
        base_url, endpoint, payload, token, timeout, timeout_exit, *, local=False
    ):
        captured.update(base_url=base_url, token=token, local=local)
        return {"ok": True, "allowed": [], "commands": []}

    monkeypatch.setattr(cli, "_post", fake_post)

    code = cli.main(["list"])

    assert code == cli.EXIT_OK
    assert captured == {
        "base_url": "http://192.0.2.10:8899",
        "token": "record-token",
        "local": True,
    }


def test_a_record_bound_to_127_0_0_2_bypasses_the_proxy(tmp_path, monkeypatch):
    stub = _StubServer(host="127.0.0.2")
    proxy = _StubServer()
    stub_thread = threading.Thread(target=stub.serve_forever, daemon=True)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    stub_thread.start()
    proxy_thread.start()
    try:
        stub.responder = lambda path, body: (
            200,
            {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
        )
        directory = _write_fake_jupyter(
            tmp_path,
            [
                _record(
                    stub.server_address[1],
                    "/",
                    "record-token",
                    hostname="127.0.0.2",
                )
            ],
        )
        monkeypatch.setenv("PATH", directory + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv(
            "http_proxy", f"http://127.0.0.1:{proxy.server_address[1]}"
        )
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)

        code = cli.main(["list"])

        assert code == cli.EXIT_OK
        assert stub.requests[0]["path"] == "/jupyterlab-commands/api/list"
        assert stub.requests[0]["authorization"] == "token record-token"
        assert proxy.requests == []
    finally:
        stub.shutdown()
        stub.server_close()
        proxy.shutdown()
        proxy.server_close()
        stub_thread.join(timeout=5)
        proxy_thread.join(timeout=5)


@pytest.mark.parametrize(
    "spelling",
    ["127.1", "2130706433", "0x7f000001", "0177.0.0.1", "0.0.0.0"],
)
def test_a_legacy_local_spelling_bypasses_the_proxy(
    tmp_path, monkeypatch, spelling
):
    stub = _StubServer()
    proxy = _StubServer()
    stub_thread = threading.Thread(target=stub.serve_forever, daemon=True)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    stub_thread.start()
    proxy_thread.start()
    try:
        stub.responder = lambda path, body: (
            200,
            {"ok": True, "client_id": "browser", "allowed": [], "commands": []},
        )
        proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
        monkeypatch.setenv("JUPYTERLAB_COMMANDS_TOKEN", "dedicated-token")
        monkeypatch.setenv("http_proxy", proxy_url)
        monkeypatch.setenv("HTTP_PROXY", proxy_url)
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)

        code = cli.main(
            ["--url", f"http://{spelling}:{stub.server_address[1]}", "--list"]
        )

        assert code == cli.EXIT_OK
        assert stub.requests[0]["path"] == "/jupyterlab-commands/api/list"
        assert stub.requests[0]["authorization"] == "token dedicated-token"
        assert proxy.requests == []
    finally:
        stub.shutdown()
        stub.server_close()
        proxy.shutdown()
        proxy.server_close()
        stub_thread.join(timeout=5)
        proxy_thread.join(timeout=5)


def test_a_local_post_uses_an_empty_proxy_handler_for_a_non_loopback_url(
    monkeypatch,
):
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    class FakeOpener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            return FakeResponse()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(cli.urllib.request, "build_opener", fake_build_opener)

    answer = cli._post(
        "http://192.0.2.10:8888", "list", {}, None, 10, 2, local=True
    )

    assert answer == {"ok": True}
    proxy_handlers = [
        handler
        for handler in captured["handlers"]
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert captured["url"] == (
        "http://192.0.2.10:8888/jupyterlab-commands/api/list"
    )


def test_the_matcher_requires_the_port_scheme_and_base_path():
    record = _record(8899, "/base/", "record-token")

    assert cli._match_listed_server("http://localhost:8899/base", [record]) is record
    assert cli._match_listed_server("http://localhost:8898/base", [record]) is None
    assert cli._match_listed_server("https://localhost:8899/base", [record]) is None
    assert cli._match_listed_server("http://localhost:8899/other", [record]) is None


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://hub.example.com/lab", "http://hub.example.com"),
        ("http://hub.example.com/lab/tree/x", "http://hub.example.com"),
        (
            "http://hub.example.com/user/alice/lab",
            "http://hub.example.com/user/alice",
        ),
        (
            "http://hub.example.com/user/lab/lab/tree/x",
            "http://hub.example.com/user/lab",
        ),
        (
            "http://hub.example.com/user/lab/lab",
            "http://hub.example.com/user/lab",
        ),
        (
            "http://hub.example.com/user/alice/lab/tree/lab/notebook.ipynb",
            "http://hub.example.com/user/alice",
        ),
        (
            "http://hub.example.com/lab/tree/lab/notebook.ipynb",
            "http://hub.example.com",
        ),
    ],
)
def test_clean_url_removes_the_lab_application_path(url, expected):
    # A base path that itself ends in lab, as on a JupyterHub user named lab,
    # must survive the removal of the application path.
    assert cli._clean_url(url) == expected


def test_list_json_carries_each_allowed_commands_argument_schema(stub, capsys):
    stub.responder = lambda path, body: (
        200,
        {
            "ok": True,
            "client_id": "browser",
            "allowed": ["docmanager:open", "apputils:notify"],
            "commands": [
                {"id": "apputils:notify", "args": "message: string"},
                {"id": "docmanager:open", "args": "path: string"},
            ],
        },
    )

    code = cli.main(["--url", _base_url(stub), "--list", "--json"])

    assert code == cli.EXIT_OK
    answer = json.loads(capsys.readouterr().out)
    schemas = {entry["id"]: entry["args"] for entry in answer["commands"]}
    assert answer["allowed"] == ["docmanager:open", "apputils:notify"]
    assert set(answer["allowed"]) <= set(schemas)
    assert schemas["docmanager:open"] == "path: string"
    assert schemas["apputils:notify"] == "message: string"


def test_help_names_variables_exit_codes_examples_and_flags(monkeypatch, capsys):
    # Colour must never change the text the test reads.
    monkeypatch.setenv("PYTHON_COLORS", "0")
    monkeypatch.setenv("COLUMNS", "200")

    with pytest.raises(SystemExit) as top_exit:
        cli.main(["--help"])

    assert top_exit.value.code == 0
    top = capsys.readouterr().out
    for name in (
        "JUPYTERLAB_COMMANDS_TOKEN",
        "JUPYTERHUB_API_TOKEN",
        "JPY_API_TOKEN",
        "JUPYTER_TOKEN",
        "JUPYTERHUB_SERVICE_PREFIX",
        "JUPYTER_PORT",
    ):
        assert name in top
    for line in (
        "0  success",
        "2  discovery or usage error",
        "3  no browser client",
        "4  command not allowed",
        "5  execution error",
    ):
        assert line in top
    assert "/proc/<pid>/cmdline" in top
    assert "--json" in top

    parser = cli._build_parser()
    for action in parser._actions:
        if action.option_strings:
            assert action.help
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    for name, subparser in subparsers.choices.items():
        for action in subparser._actions:
            assert action.help
        with pytest.raises(SystemExit) as sub_exit:
            cli.main([name, "--help"])
        assert sub_exit.value.code == 0
        text = capsys.readouterr().out
        assert "Examples:" in text
        assert "jupyterlab-commands" in text.split("Examples:", 1)[1]
