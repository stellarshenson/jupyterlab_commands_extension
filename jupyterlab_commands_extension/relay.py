"""Relay between the CLI and the command registry of a browser tab.

The browser registers the commands it has and the subset it allows the CLI to
run, then long-polls for requests. The CLI posts a request and waits for the
browser to post the result. Every method runs on the Tornado IOLoop of the
Jupyter server, so the dictionaries need no lock.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

# How long the browser long poll waits before it is answered with no request.
PENDING_TIMEOUT_S = 25.0

# How long the relay waits for the browser to answer an execute request.
EXECUTION_TIMEOUT_S = 30.0


class RelayError(Exception):
    """A request the relay refuses, with the HTTP status that reports it."""

    status = 500
    code = "relay-error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequestError(RelayError):
    status = 400
    code = "bad-request"


class NoClientError(RelayError):
    status = 503
    code = "no-client"


class UnknownClientError(RelayError):
    status = 404
    code = "unknown-client"


class UnknownCommandError(RelayError):
    status = 404
    code = "unknown-command"


class CommandNotAllowedError(RelayError):
    status = 403
    code = "command-not-allowed"


class UnknownRequestError(RelayError):
    status = 404
    code = "unknown-request"


class ExecutionTimeoutError(RelayError):
    status = 504
    code = "execution-timeout"


class ExecutionFailedError(RelayError):
    status = 500
    code = "execution-failed"


@dataclass
class Request:
    """One command the browser must run."""

    request_id: str
    command: str
    args: dict[str, Any]
    allowed: list[str]
    future: asyncio.Future

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.request_id,
            "command": self.command,
            "args": self.args,
            "allowed": self.allowed,
        }


@dataclass
class Result:
    """The browser's answer to one request."""

    ok: bool
    data: Any
    error: str | None


@dataclass
class Client:
    """A registered browser tab."""

    client_id: str
    commands: dict[str, dict[str, Any]]
    allowed: set[str]
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


def _command_table(commands: Any) -> dict[str, dict[str, Any]]:
    """Normalise the registered command list to id -> descriptor.

    An entry is either a command id or an object with at least an ``id``.
    """
    if not isinstance(commands, list):
        raise BadRequestError("'commands' must be a list")
    table: dict[str, dict[str, Any]] = {}
    for entry in commands:
        if isinstance(entry, str):
            command_id = entry
            descriptor: dict[str, Any] = {"id": entry}
        elif isinstance(entry, dict):
            command_id = entry.get("id")
            descriptor = dict(entry)
        else:
            raise BadRequestError(
                "each command must be an id or an object with an 'id'"
            )
        if not isinstance(command_id, str) or not command_id:
            raise BadRequestError("each command must have a non-empty string 'id'")
        table[command_id] = descriptor
    return table


def _allowed_set(allowed: Any) -> set[str]:
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) for item in allowed
    ):
        raise BadRequestError("'allowed' must be a list of command ids")
    return set(allowed)


class Relay:
    """Holds the registered clients, the pending requests and their results."""

    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}
        self._pending: dict[str, Request] = {}
        self._selected: str | None = None

    def register(self, client_id: Any, commands: Any, allowed: Any) -> Client:
        """Register or refresh one browser tab and select it.

        The most recently registered client receives the next execute request.
        A tab that registers again keeps its queue, so a long poll that was
        waiting before the refresh still receives the next request.
        """
        if not isinstance(client_id, str) or not client_id.strip():
            raise BadRequestError("'client_id' must be a non-empty string")
        table = _command_table(commands)
        allowed_set = _allowed_set(allowed)
        previous = self._clients.get(client_id)
        client = Client(
            client_id=client_id,
            commands=table,
            allowed=allowed_set,
            queue=previous.queue if previous is not None else asyncio.Queue(),
        )
        self._clients[client_id] = client
        self._selected = client_id
        return client

    @property
    def client(self) -> Client | None:
        """The client that receives requests, or None when none registered."""
        if self._selected is None:
            return None
        return self._clients.get(self._selected)

    def _require_client(self) -> Client:
        client = self.client
        if client is None:
            raise NoClientError(
                "no browser tab has registered with the relay; open JupyterLab "
                "with the commands extension enabled"
            )
        return client

    async def next_request(
        self, client_id: Any, timeout: float = PENDING_TIMEOUT_S
    ) -> Request | None:
        """Wait up to ``timeout`` for a request for this client.

        Returns None when the wait ends with no request.
        """
        if not isinstance(client_id, str) or not client_id:
            raise BadRequestError("'client_id' must be a non-empty string")
        client = self._clients.get(client_id)
        if client is None:
            raise UnknownClientError(
                "this client id is not registered; register before polling"
            )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                request = await asyncio.wait_for(client.queue.get(), remaining)
            except asyncio.TimeoutError:
                return None
            # A request stays in the queue after its execute call timed out
            # or was cancelled; it must not run after the CLI reported failure.
            if request.future.done():
                continue
            return request

    async def execute(
        self,
        command: Any,
        args: Any = None,
        timeout: float = EXECUTION_TIMEOUT_S,
    ) -> Any:
        """Queue one allowed command and return the browser's data.

        Raises:
            NoClientError: no browser tab is registered (503).
            UnknownCommandError: the browser does not register the command (404).
            CommandNotAllowedError: the command is registered but not allowed (403).
            ExecutionTimeoutError: the browser did not answer in time (504).
            ExecutionFailedError: the browser reported a failure (500).
        """
        client = self._require_client()
        if not isinstance(command, str) or not command:
            raise BadRequestError("'command' must be a non-empty string")
        if command not in client.commands:
            raise UnknownCommandError(
                f"the browser does not register command {command!r}"
            )
        if command not in client.allowed:
            raise CommandNotAllowedError(
                f"command {command!r} is not in the browser allowlist"
            )
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise BadRequestError("'args' must be a JSON object")

        request = Request(
            request_id=uuid.uuid4().hex,
            command=command,
            args=args,
            allowed=sorted(client.allowed),
            future=asyncio.get_running_loop().create_future(),
        )
        self._pending[request.request_id] = request
        await client.queue.put(request)
        try:
            result: Result = await asyncio.wait_for(request.future, timeout)
        except asyncio.TimeoutError:
            raise ExecutionTimeoutError(
                f"the browser did not answer command {command!r} "
                f"within {timeout:g}s"
            ) from None
        finally:
            self._pending.pop(request.request_id, None)
        if not result.ok:
            raise ExecutionFailedError(
                result.error or "the browser reported a failed execution"
            )
        return result.data

    def submit_result(
        self,
        request_id: Any,
        ok: Any,
        data: Any = None,
        error: Any = None,
    ) -> None:
        """Resolve the pending request with the browser's answer."""
        if not isinstance(request_id, str) or not request_id:
            raise BadRequestError("'request_id' must be a non-empty string")
        if not isinstance(ok, bool):
            raise BadRequestError("'ok' must be a boolean")
        request = self._pending.get(request_id)
        if request is None or request.future.done():
            raise UnknownRequestError(
                f"request {request_id!r} is not waiting for a result"
            )
        request.future.set_result(
            Result(ok=ok, data=data, error=error if isinstance(error, str) else None)
        )

    def client_status(self) -> dict[str, Any]:
        """The selected client's allowlist and command descriptors."""
        client = self._require_client()
        return {
            "ok": True,
            "client_id": client.client_id,
            "allowed": sorted(client.allowed),
            "commands": [client.commands[key] for key in sorted(client.commands)],
        }
