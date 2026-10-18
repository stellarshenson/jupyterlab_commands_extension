"""Tests for route registration and for each handler's HTTP contract.

The handler tests drive the real handler methods with a mocked Tornado
request: authentication, request body, query arguments, status and finish are
replaced, while the relay and the error mapping stay real. A live server is
not needed to prove the status code and the JSON body of each answer.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
import tornado.web

from jupyterlab_commands_extension import handlers
from jupyterlab_commands_extension.relay import Relay

COMMANDS = [
    {"id": "docmanager:open", "label": "Open", "args": {"path": "string"}},
    {"id": "help:open", "label": "Open help"},
]
ALLOWED = ["docmanager:open"]


class _FakeWebApp:
    def __init__(self, base_url="/"):
        self.settings = {"base_url": base_url}
        self.host_pattern = None
        self.routes = None

    def add_handlers(self, host_pattern, routes):
        self.host_pattern = host_pattern
        self.routes = routes


def test_routes_land_under_a_hub_base_url():
    app = _FakeWebApp("/user/alice/")

    handlers.setup_route_handlers(app)

    assert app.host_pattern == ".*$"
    routes = dict(app.routes)
    prefix = "/user/alice/jupyterlab-commands/api"
    assert routes == {
        f"{prefix}/register": handlers.RegisterHandler,
        f"{prefix}/pending": handlers.PendingHandler,
        f"{prefix}/result": handlers.ResultHandler,
        f"{prefix}/list": handlers.ListHandler,
        f"{prefix}/execute": handlers.ExecuteHandler,
    }


def test_routes_land_under_a_root_base_url():
    app = _FakeWebApp("/")

    handlers.setup_route_handlers(app)

    assert sorted(dict(app.routes)) == [
        "/jupyterlab-commands/api/execute",
        "/jupyterlab-commands/api/list",
        "/jupyterlab-commands/api/pending",
        "/jupyterlab-commands/api/register",
        "/jupyterlab-commands/api/result",
    ]


class _HandlerHarness:
    """One handler instance with the Tornado request and response mocked.

    The handler methods are the real ones, so the decorators, the relay calls
    and the error mapping all run. Only the transport is fake: the request
    body and query arguments go in, the status and the finished body come out.
    """

    def __init__(self, handler_class, relay, body=None, query=None, user="alice"):
        handler = object.__new__(handler_class)
        handler.application = SimpleNamespace(
            settings={handlers.RELAY_KEY: relay}
        )
        handler.current_user = user
        handler.request = SimpleNamespace(
            method="POST",
            body=b"" if body is None else json.dumps(body).encode("utf-8"),
            uri="/jupyterlab-commands/api/test",
            full_url=lambda: "http://localhost/jupyterlab-commands/api/test",
        )
        self.handler = handler
        self.status = None
        self.finished = []
        handler.set_status = self._set_status
        handler.finish = self._finish
        handler.get_query_argument = lambda name, default=None, strip=True: (
            query or {}
        ).get(name, default)

    def _set_status(self, status, reason=None):
        self.status = status

    def _finish(self, chunk=None):
        self.finished.append(chunk)

    @property
    def answer(self):
        assert len(self.finished) == 1
        return json.loads(self.finished[0])


def _relay_with_client(client_id="browser-1", allowed=ALLOWED):
    relay = Relay()
    relay.register(client_id, COMMANDS, allowed)
    return relay


@pytest.mark.asyncio
async def test_an_unauthenticated_request_is_rejected():
    """Fails if @tornado.web.authenticated is removed from RegisterHandler."""
    harness = _HandlerHarness(
        handlers.RegisterHandler,
        Relay(),
        body={"client_id": "browser-1", "commands": COMMANDS, "allowed": ALLOWED},
        user=None,
    )

    with pytest.raises(tornado.web.HTTPError) as raised:
        await harness.handler.post()

    assert raised.value.status_code == 403
    assert harness.finished == []


@pytest.mark.asyncio
async def test_register_then_list_returns_only_the_allowlist():
    """Fails if ListHandler reports every registered command as allowed."""
    relay = Relay()
    register = _HandlerHarness(
        handlers.RegisterHandler,
        relay,
        body={"client_id": "browser-1", "commands": COMMANDS, "allowed": ALLOWED},
    )
    await register.handler.post()
    assert register.answer == {"ok": True, "client_id": "browser-1"}

    listing = _HandlerHarness(handlers.ListHandler, relay)
    await listing.handler.post()

    answer = listing.answer
    assert answer["allowed"] == ALLOWED
    assert all(command in {entry["id"] for entry in COMMANDS} for command in answer["allowed"])
    assert [entry["id"] for entry in answer["commands"]] == [
        "docmanager:open",
        "help:open",
    ]


@pytest.mark.asyncio
async def test_execute_of_an_allowed_command_queues_it_and_returns_the_result():
    """Fails if ExecuteHandler answers before the browser posts its result."""
    relay = _relay_with_client()
    harness = _HandlerHarness(
        handlers.ExecuteHandler,
        relay,
        body={"command": "docmanager:open", "args": {"path": "README.md"}},
    )

    execution = asyncio.create_task(harness.handler.post())
    request = await relay.next_request("browser-1", timeout=1)
    assert request is not None
    assert request.command == "docmanager:open"
    assert request.args == {"path": "README.md"}

    relay.submit_result(request.request_id, True, {"opened": "README.md"})
    await execution

    assert harness.status is None
    assert harness.answer == {"ok": True, "data": {"opened": "README.md"}}


@pytest.mark.asyncio
async def test_execute_outside_the_allowlist_returns_403():
    """Fails if CommandNotAllowedError stops carrying status 403."""
    harness = _HandlerHarness(
        handlers.ExecuteHandler,
        _relay_with_client(),
        body={"command": "help:open"},
    )

    await harness.handler.post()

    assert harness.status == 403
    assert harness.answer["error"]["code"] == "command-not-allowed"


@pytest.mark.asyncio
async def test_execute_of_an_unknown_command_returns_404():
    """Fails if UnknownCommandError stops carrying status 404."""
    harness = _HandlerHarness(
        handlers.ExecuteHandler,
        _relay_with_client(),
        body={"command": "not:a-command"},
    )

    await harness.handler.post()

    assert harness.status == 404
    assert harness.answer["error"]["code"] == "unknown-command"


@pytest.mark.asyncio
async def test_execute_without_a_registered_client_returns_503():
    """Fails if the handler invents a client instead of reporting no-client."""
    harness = _HandlerHarness(
        handlers.ExecuteHandler,
        Relay(),
        body={"command": "docmanager:open"},
    )

    await harness.handler.post()

    assert harness.status == 503
    assert harness.answer["error"]["code"] == "no-client"


@pytest.mark.asyncio
async def test_a_pending_poll_that_times_out_returns_an_empty_answer(monkeypatch):
    """Fails if PendingHandler raises instead of answering with request null."""
    monkeypatch.setattr(handlers, "PENDING_TIMEOUT_S", 0.01)
    harness = _HandlerHarness(
        handlers.PendingHandler,
        _relay_with_client(),
        query={"client_id": "browser-1"},
    )

    await harness.handler.get()

    assert harness.status is None
    assert harness.answer == {"request": None}


@pytest.mark.asyncio
async def test_a_result_for_an_unknown_request_id_does_not_crash():
    """Fails if submit_result silently accepts an unknown request id."""
    harness = _HandlerHarness(
        handlers.ResultHandler,
        _relay_with_client(),
        body={"request_id": "missing", "ok": True, "data": None},
    )

    await harness.handler.post()

    assert harness.status == 404
    assert harness.answer["error"]["code"] == "unknown-request"
