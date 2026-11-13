"""Tests for the server relay: queueing, timeout and allowlist enforcement."""

import asyncio

import pytest

from jupyterlab_commands_extension.relay import (
    CommandNotAllowedError,
    ExecutionFailedError,
    ExecutionTimeoutError,
    CLIENT_EXPIRY_S,
    NoClientError,
    Relay,
    UnknownClientError,
    UnknownCommandError,
    UnknownRequestError,
)

COMMANDS = [
    {"id": "docmanager:open", "label": "Open"},
    {"id": "help:open", "label": "Open help"},
]
ALLOWED = ["docmanager:open"]


def _register(relay, client_id="browser-1", allowed=ALLOWED):
    return relay.register(client_id, COMMANDS, allowed)


@pytest.mark.asyncio
async def test_execute_queues_a_request_and_returns_the_result():
    relay = Relay()
    _register(relay)

    execution = asyncio.create_task(
        relay.execute("docmanager:open", {"path": "notebook.ipynb"})
    )
    await asyncio.sleep(0)

    request = await relay.next_request("browser-1", timeout=1)
    assert request is not None
    assert request.command == "docmanager:open"
    assert request.args == {"path": "notebook.ipynb"}
    assert request.allowed == ALLOWED

    relay.submit_result(request.request_id, True, {"opened": True}, None)
    assert await execution == {"opened": True}


@pytest.mark.asyncio
async def test_pending_poll_returns_none_on_timeout():
    relay = Relay()
    _register(relay)

    assert await relay.next_request("browser-1", timeout=0.01) is None


@pytest.mark.asyncio
async def test_execute_times_out_when_the_browser_does_not_answer():
    relay = Relay()
    _register(relay)

    with pytest.raises(ExecutionTimeoutError):
        await relay.execute("docmanager:open", {}, timeout=0.01)


@pytest.mark.asyncio
async def test_a_registered_command_outside_the_allowlist_is_refused():
    relay = Relay()
    _register(relay)

    with pytest.raises(CommandNotAllowedError):
        await relay.execute("help:open")


@pytest.mark.asyncio
async def test_an_unknown_command_is_refused():
    relay = Relay()
    _register(relay)

    with pytest.raises(UnknownCommandError):
        await relay.execute("not:a-command")


@pytest.mark.asyncio
async def test_execute_without_a_registered_client_is_refused():
    relay = Relay()

    with pytest.raises(NoClientError):
        await relay.execute("docmanager:open")


@pytest.mark.asyncio
async def test_a_failed_execution_carries_the_browser_error():
    relay = Relay()
    _register(relay)

    execution = asyncio.create_task(relay.execute("docmanager:open", {}))
    await asyncio.sleep(0)
    request = await relay.next_request("browser-1", timeout=1)
    relay.submit_result(request.request_id, False, None, "the file does not exist")

    with pytest.raises(ExecutionFailedError) as raised:
        await execution
    assert "the file does not exist" in str(raised.value)


@pytest.mark.asyncio
async def test_a_result_for_an_unknown_request_is_refused():
    relay = Relay()

    with pytest.raises(UnknownRequestError):
        relay.submit_result("missing", True, None, None)


@pytest.mark.asyncio
async def test_the_most_recently_registered_client_receives_requests():
    relay = Relay()
    _register(relay, "first")
    _register(relay, "second")

    execution = asyncio.create_task(relay.execute("docmanager:open", {}))
    await asyncio.sleep(0)

    assert await relay.next_request("first", timeout=0.05) is None
    request = await relay.next_request("second", timeout=1)
    assert request is not None
    relay.submit_result(request.request_id, True, None, None)
    await execution


@pytest.mark.asyncio
async def test_polling_does_not_change_which_client_is_selected():
    relay = Relay()
    _register(relay, "first")
    _register(relay, "second")

    second_poll = asyncio.create_task(relay.next_request("second", timeout=1))
    first_poll = asyncio.create_task(relay.next_request("first", timeout=0.05))
    execution = asyncio.create_task(relay.execute("docmanager:open", {}))
    await asyncio.sleep(0)

    assert await first_poll is None
    request = await second_poll
    assert request is not None
    relay.submit_result(request.request_id, True, None, None)
    await execution


@pytest.mark.asyncio
async def test_registering_again_updates_the_allowlist():
    relay = Relay()
    _register(relay, allowed=[])
    with pytest.raises(CommandNotAllowedError):
        await relay.execute("docmanager:open")

    _register(relay, allowed=["docmanager:open"])
    execution = asyncio.create_task(relay.execute("docmanager:open", {}))
    await asyncio.sleep(0)
    request = await relay.next_request("browser-1", timeout=1)
    relay.submit_result(request.request_id, True, None, None)
    await execution


@pytest.mark.asyncio
async def test_client_status_reports_the_allowlist_and_commands():
    relay = Relay()
    _register(relay)

    status = relay.client_status()
    assert status["client_id"] == "browser-1"
    assert status["allowed"] == ["docmanager:open"]
    assert [entry["id"] for entry in status["commands"]] == [
        "docmanager:open",
        "help:open",
    ]


@pytest.mark.asyncio
async def test_client_status_describes_each_command_by_caption_else_label():
    relay = Relay()
    relay.register(
        "browser-1",
        [
            {"id": "a:caption", "label": "Label", "caption": "Two\n  lines"},
            {"id": "b:label", "label": "Label", "caption": ""},
            {"id": "c:none"},
            "d:id-only",
        ],
        [],
    )

    descriptions = {
        entry["id"]: entry["description"]
        for entry in relay.client_status()["commands"]
    }
    assert descriptions == {
        "a:caption": "Two lines",
        "b:label": "Label",
        "c:none": "",
        "d:id-only": "",
    }


@pytest.mark.asyncio
async def test_a_tab_that_stopped_polling_is_forgotten():
    relay = Relay()
    _register(relay, "open")
    _register(relay, "closed")
    relay._clients["closed"].seen -= CLIENT_EXPIRY_S + 1

    # The closed tab registered last, yet the open tab receives requests.
    assert relay.client.client_id == "open"
    with pytest.raises(UnknownClientError):
        await relay.next_request("closed", timeout=0.05)

    relay._clients["open"].seen -= CLIENT_EXPIRY_S + 1
    _register(relay, "reloaded")
    assert list(relay._clients) == ["reloaded"]


@pytest.mark.asyncio
async def test_polling_keeps_a_tab_registered():
    relay = Relay()
    _register(relay)
    relay._clients["browser-1"].seen -= CLIENT_EXPIRY_S - 1

    assert await relay.next_request("browser-1", timeout=0.05) is None
    relay._clients["browser-1"].seen -= CLIENT_EXPIRY_S - 1

    assert relay.client is not None
