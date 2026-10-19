"""Integration tests against a live Jupyter Server.

The server is started by the ``jp_serverapp`` fixture with the extension
enabled. Requests travel over real HTTP through ``jp_fetch`` at the server's
own base URL. A simulated browser tab registers, long-polls, posts a result
and receives the CLI's execute answer, so the test exercises the routes,
authentication and the relay together.

The activity tests run the CLI as a real subprocess from the source tree
against a stub hub HTTP server and a recording proxy in the test process.
"""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from tornado.httpclient import HTTPClientError
from traitlets.config import Config

pytest_plugins = ["pytest_jupyter.jupyter_server"]

API = ("jupyterlab-commands", "api")
CLIENT_ID = "simulated-browser-1"

COMMANDS = [
    {"id": "docmanager:open", "label": "Open", "args": {"path": "string"}},
    {"id": "help:open", "label": "Open help"},
]
ALLOWED = ["docmanager:open"]


@pytest.fixture
def jp_server_config():
    """Enable the extension under test in the server the fixtures start."""
    return Config(
        {
            "ServerApp": {
                "jpserver_extensions": {"jupyterlab_commands_extension": True},
            }
        }
    )


async def _register(jp_fetch, allowed=ALLOWED):
    response = await jp_fetch(
        *API,
        "register",
        method="POST",
        body=json.dumps(
            {"client_id": CLIENT_ID, "commands": COMMANDS, "allowed": allowed}
        ),
    )
    assert response.code == 200
    return json.loads(response.body)


async def test_register_list_execute_and_result_over_http(jp_fetch):
    """Fails if the browser's result never reaches the waiting execute call."""
    registered = await _register(jp_fetch)
    assert registered == {"ok": True, "client_id": CLIENT_ID}

    listing = json.loads(
        (await jp_fetch(*API, "list", method="POST", body="{}")).body
    )
    assert listing["allowed"] == ALLOWED
    assert [entry["id"] for entry in listing["commands"]] == [
        "docmanager:open",
        "help:open",
    ]

    execution = jp_fetch(
        *API,
        "execute",
        method="POST",
        body=json.dumps(
            {"command": "docmanager:open", "args": {"path": "README.md"}}
        ),
    )
    pending = json.loads(
        (
            await jp_fetch(
                *API, "pending", params={"client_id": CLIENT_ID}
            )
        ).body
    )
    request = pending["request"]
    assert request["command"] == "docmanager:open"
    assert request["args"] == {"path": "README.md"}
    assert request["allowed"] == ALLOWED

    result = await jp_fetch(
        *API,
        "result",
        method="POST",
        body=json.dumps(
            {"request_id": request["id"], "ok": True, "data": {"opened": True}}
        ),
    )
    assert result.code == 200
    assert json.loads(result.body) == {"ok": True}

    executed = await execution
    assert json.loads(executed.body) == {"ok": True, "data": {"opened": True}}


async def test_a_wrong_token_is_rejected_over_http(jp_fetch):
    """Fails if the relay routes stop requiring authentication."""
    with pytest.raises(HTTPClientError) as raised:
        await jp_fetch(
            *API,
            "register",
            method="POST",
            headers={"Authorization": "token not-the-server-token"},
            body=json.dumps(
                {"client_id": CLIENT_ID, "commands": COMMANDS, "allowed": ALLOWED}
            ),
        )

    assert raised.value.code == 403


async def test_execute_outside_the_allowlist_returns_403_over_http(jp_fetch):
    """Fails if the allowlist check moves out of the execute route."""
    await _register(jp_fetch)

    with pytest.raises(HTTPClientError) as raised:
        await jp_fetch(
            *API,
            "execute",
            method="POST",
            body=json.dumps({"command": "help:open"}),
        )

    assert raised.value.code == 403
    error = json.loads(raised.value.response.body)["error"]
    assert error["code"] == "command-not-allowed"


HUB_TOKEN = "HUB-SECRET-token-123"
ACTIVITY_PATH = "/hub/api/users/alice/activity"
NO_SUCH_SERVER = "No such server '' for user alice"
SOURCE_ROOT = Path(__file__).resolve().parents[2]


class _HubHandler(BaseHTTPRequestHandler):
    def _record(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": json.loads(raw) if raw else None,
            }
        )

    def do_GET(self):
        self._record()
        self.send_response(502)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self._record()
        status, payload = self.server.answer
        data = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _HubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _HubHandler)
        self.requests = []
        # The hub answers the activity route with 200 and an empty body.
        self.answer = (200, None)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


@pytest.fixture
def hub_and_proxy():
    servers = (_HubServer(), _HubServer())
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in servers
    ]
    for thread in threads:
        thread.start()
    try:
        yield servers
    finally:
        for server, thread in zip(servers, threads):
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _run_activity_subprocess(hub, proxy):
    """Run ``python -m jupyterlab_commands_extension.cli activity --json``."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("JUPYTER", "JPY_"))
        and name.lower() not in ("http_proxy", "https_proxy", "no_proxy")
    }
    environment.update(
        {
            "JUPYTERHUB_ACTIVITY_URL": hub.url + ACTIVITY_PATH,
            "JUPYTERHUB_API_TOKEN": HUB_TOKEN,
            "http_proxy": proxy.url,
            "HTTP_PROXY": proxy.url,
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "jupyterlab_commands_extension.cli", "activity", "--json"],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert HUB_TOKEN not in completed.stdout
    assert HUB_TOKEN not in completed.stderr
    assert proxy.requests == []
    return completed


def test_activity_subprocess_posts_to_the_hub_activity_route(hub_and_proxy):
    """Fails if the installed-style CLI run does not reach the hub route."""
    hub, proxy = hub_and_proxy

    completed = _run_activity_subprocess(hub, proxy)

    assert completed.returncode == 0, completed.stderr
    assert len(hub.requests) == 1
    request = hub.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == ACTIVITY_PATH
    assert request["authorization"] == f"token {HUB_TOKEN}"
    timestamp = request["body"]["last_activity"]
    assert request["body"] == {
        "last_activity": timestamp,
        "servers": {"": {"last_activity": timestamp}},
    }
    assert timestamp.endswith("Z")
    datetime.fromisoformat(timestamp[:-1])
    assert json.loads(completed.stdout) == {
        "ok": True,
        "last_activity": timestamp,
        "server": "",
    }


def test_activity_subprocess_prints_the_hub_refusal(hub_and_proxy):
    """Fails if a hub 400 is not reported with its message and exit 5."""
    hub, proxy = hub_and_proxy
    hub.answer = (400, {"status": 400, "message": NO_SUCH_SERVER})

    completed = _run_activity_subprocess(hub, proxy)

    assert completed.returncode == 5, completed.stderr
    assert len(hub.requests) == 1
    assert json.loads(completed.stdout) == {
        "ok": False,
        "status": 400,
        "message": NO_SUCH_SERVER,
    }
