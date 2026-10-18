"""Integration tests against a live Jupyter Server.

The server is started by the ``jp_serverapp`` fixture with the extension
enabled. Requests travel over real HTTP through ``jp_fetch`` at the server's
own base URL. A simulated browser tab registers, long-polls, posts a result
and receives the CLI's execute answer, so the test exercises the routes,
authentication and the relay together.
"""

import json

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
