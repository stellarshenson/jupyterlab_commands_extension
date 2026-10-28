"""HTTP endpoints of the relay: ``<base_url>jupyterlab-commands/api/...``.

The browser uses register, pending and result. The CLI uses list and execute.
Every handler is authenticated and answers JSON.
"""

from __future__ import annotations

import functools
import json
import time
from typing import Any, Callable, Coroutine

import tornado.web
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join

from .relay import (
    PENDING_TIMEOUT_S,
    BadRequestError,
    ExecutionFailedError,
    ExecutionTimeoutError,
    Relay,
    RelayError,
)

API_NAMESPACE = "jupyterlab-commands"
RELAY_KEY = "jupyterlab_commands_relay"
ARGS_LOG_LIMIT = 500
PURPOSE_WORD_LIMIT = 25


def _checked_context(purpose: Any, owner: Any) -> tuple[Any, Any]:
    """Check the optional purpose and owner audit fields.

    Each may be absent or null; when present it must be a string that strips
    to non-empty, and the purpose carries at most PURPOSE_WORD_LIMIT words.
    """
    checked = []
    for name, value in (("purpose", purpose), ("owner", owner)):
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise BadRequestError(
                    f"'{name}' must be a non-empty string when given"
                )
            value = value.strip()
        checked.append(value)
    purpose_text, owner_text = checked
    if (
        purpose_text is not None
        and len(purpose_text.split()) > PURPOSE_WORD_LIMIT
    ):
        raise BadRequestError(
            f"'purpose' must be at most {PURPOSE_WORD_LIMIT} words"
        )
    return purpose_text, owner_text


def _relay_errors(
    method: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Report a RelayError as its status and JSON body."""

    @functools.wraps(method)
    async def wrapper(self: "RelayHandler", *args: Any, **kwargs: Any) -> None:
        try:
            await method(self, *args, **kwargs)
        except RelayError as error:
            self.set_status(error.status)
            self.finish(
                json.dumps(
                    {"error": {"code": error.code, "message": error.message}}
                )
            )

    return wrapper


class RelayHandler(APIHandler):
    """Base of the relay handlers."""

    @property
    def relay(self) -> Relay:
        return self.settings[RELAY_KEY]

    def body(self) -> dict[str, Any]:
        """The request body as one JSON object."""
        try:
            body = json.loads(self.request.body or b"{}")
        except ValueError:
            raise BadRequestError(
                "the request body must be one JSON object"
            ) from None
        if not isinstance(body, dict):
            raise BadRequestError("the request body must be one JSON object")
        return body


class RegisterHandler(RelayHandler):
    """``POST register``: the browser registers its commands and allowlist."""

    @tornado.web.authenticated
    @_relay_errors
    async def post(self) -> None:
        body = self.body()
        client = self.relay.register(
            body.get("client_id"),
            body.get("commands"),
            body.get("allowed"),
        )
        self.finish(json.dumps({"ok": True, "client_id": client.client_id}))


class PendingHandler(RelayHandler):
    """``GET pending``: the browser long-polls for the next request."""

    @tornado.web.authenticated
    @_relay_errors
    async def get(self) -> None:
        client_id = self.get_query_argument("client_id", "")
        request = await self.relay.next_request(client_id, PENDING_TIMEOUT_S)
        self.finish(
            json.dumps({"request": None if request is None else request.as_dict()})
        )


class ResultHandler(RelayHandler):
    """``POST result``: the browser posts the result of one request."""

    @tornado.web.authenticated
    @_relay_errors
    async def post(self) -> None:
        body = self.body()
        self.relay.submit_result(
            body.get("request_id"),
            body.get("ok"),
            body.get("data"),
            body.get("error"),
        )
        self.finish(json.dumps({"ok": True}))


class ListHandler(RelayHandler):
    """``POST list``: the CLI reads the selected client's allowlist."""

    @tornado.web.authenticated
    @_relay_errors
    async def post(self) -> None:
        self.finish(json.dumps(self.relay.client_status()))


class ExecuteHandler(RelayHandler):
    """``POST execute``: the CLI queues one command and waits for its data."""

    @tornado.web.authenticated
    @_relay_errors
    async def post(self) -> None:
        started = time.monotonic()
        command: Any = None
        args: Any = None
        purpose: Any = None
        owner: Any = None
        try:
            body = self.body()
            command = body.get("command")
            args = body.get("args")
            purpose = body.get("purpose")
            owner = body.get("owner")
            purpose, owner = _checked_context(purpose, owner)
            data = await self.relay.execute(command, args)
        except RelayError as error:
            self._log_execution(started, command, args, purpose, owner, error)
            raise
        self._log_execution(started, command, args, purpose, owner, None)
        self.finish(json.dumps({"ok": True, "data": data}))

    def _log_execution(
        self,
        started: float,
        command: Any,
        args: Any,
        purpose: Any,
        owner: Any,
        error: RelayError | None,
    ) -> None:
        """Write one audit line for this execute request.

        Only the command, the arguments, the optional purpose and owner, the
        elapsed time and the remote IP are read, so the request's
        Authorization token cannot reach the log.
        """
        args_text = json.dumps(args, separators=(",", ":"))
        if len(args_text) > ARGS_LOG_LIMIT:
            args_text = args_text[:ARGS_LOG_LIMIT]
        elapsed_ms = int((time.monotonic() - started) * 1000)
        context = (
            "" if purpose is None else purpose,
            "" if owner is None else owner,
        )
        line = (
            "execute %s command=%r args=%s elapsed_ms=%d remote_ip=%s"
            " purpose=%r owner=%r"
        )
        if error is None:
            self.log.info(
                line,
                "succeeded",
                command,
                args_text,
                elapsed_ms,
                self.request.remote_ip,
                *context,
            )
            return
        outcome = (
            "failed"
            if isinstance(error, (ExecutionTimeoutError, ExecutionFailedError))
            else "refused"
        )
        self.log.warning(
            line + " error=%s",
            outcome,
            command,
            args_text,
            elapsed_ms,
            self.request.remote_ip,
            *context,
            error.code,
        )


def setup_route_handlers(web_app: Any) -> None:
    """Register the relay handlers under the server's base URL."""
    base = url_path_join(web_app.settings["base_url"], API_NAMESPACE, "api")
    handlers = [
        (url_path_join(base, "register"), RegisterHandler),
        (url_path_join(base, "pending"), PendingHandler),
        (url_path_join(base, "result"), ResultHandler),
        (url_path_join(base, "list"), ListHandler),
        (url_path_join(base, "execute"), ExecuteHandler),
    ]
    web_app.add_handlers(".*$", handlers)
