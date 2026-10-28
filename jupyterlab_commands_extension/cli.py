"""Command line client of the JupyterLab commands relay.

The CLI finds the Jupyter server this process belongs to, reads the allowlist
of the most recently registered browser tab, and asks that tab to run one
command. The token travels in the Authorization header and is never printed.
The activity subcommand instead sends one activity timestamp to JupyterHub.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

API_NAMESPACE = "jupyterlab-commands"
DEFAULT_PORT = "8888"

# Bound on the `jupyter server list` subprocess.
SERVER_LIST_TIMEOUT_S = 5

# Bound on list, register, pending and result calls.
REQUEST_TIMEOUT_S = 10

# The server waits 30 s for the browser, so the client must wait longer.
EXECUTE_TIMEOUT_S = 35

# Audit context an execute request can carry.
PURPOSE_WORD_LIMIT = 25

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_CLIENT = 3
EXIT_NOT_ALLOWED = 4
EXIT_EXECUTION = 5

# Bind addresses a server record can carry, mapped to every loopback literal
# that reaches that bind, most preferred first. Tornado binds IPv6 sockets
# with IPV6_V6ONLY set, so 127.0.0.1 does not reach ::1 and the reverse.
# localhost reaches both families: _server_url uses the first literal and
# _match_listed_server accepts either.
_LOOPBACK_HOST_FOR = {
    "0.0.0.0": ("127.0.0.1",),
    "localhost": ("127.0.0.1", "[::1]"),
    "127.0.0.1": ("127.0.0.1",),
    "::": ("[::1]",),
    "::1": ("[::1]",),
}

# URL hosts that name a loopback destination, mapped to the literals a request
# to that host can land on. This table is the record-matching surface only:
# _is_loopback decides locality for proxy bypass and ambient token selection,
# so a wildcard client address needs no key here.
_LOOPBACK_URL_HOSTS = {
    "127.0.0.1": ("127.0.0.1",),
    "localhost": ("127.0.0.1", "[::1]"),
    "::1": ("[::1]",),
}

EPILOG = """\
Authentication:
  JUPYTERLAB_COMMANDS_TOKEN is this tool's own variable and is checked first
  for any target, so a remote target never needs the token in argv.
  JUPYTERHUB_API_TOKEN, JPY_API_TOKEN and JUPYTER_TOKEN are used only for a
  loopback target, in that order. A matched server record's own token is used
  before those ambient variables.
  activity sends the hub token, JUPYTERHUB_API_TOKEN then JPY_API_TOKEN, to
  JUPYTERHUB_ACTIVITY_URL only. It never sends JUPYTERLAB_COMMANDS_TOKEN,
  JUPYTER_TOKEN or --token, and refuses --url and --token.
  --token is kept for compatibility, but it puts the secret in argv where
  every local account can read /proc/<pid>/cmdline. Prefer
  JUPYTERLAB_COMMANDS_TOKEN. The token travels in the Authorization header
  and is never printed. A remote target must use TLS, because cleartext http
  exposes that header to anyone on the path.

Environment variables:
  JUPYTERLAB_COMMANDS_TOKEN  token for any target, checked first
  JUPYTERHUB_API_TOKEN, JPY_API_TOKEN, JUPYTER_TOKEN
                             lab targets on loopback only, in that order
  JUPYTERHUB_SERVICE_PREFIX  names this process's own server, so it selects
                             among several listed records, and supplies the
                             base path when no record is listed
  JUPYTER_PORT               port used when no record is listed (default 8888)
  JUPYTERHUB_ACTIVITY_URL    hub activity route that activity posts to
  JUPYTERHUB_SERVER_NAME     server name activity reports (empty for the
                             default server)

Exit codes:
  0  success
  2  discovery or usage error
  3  no browser client
  4  command not allowed
  5  execution error
"""

LIST_EPILOG = """\
Examples:
  jupyterlab-commands --list
  jupyterlab-commands list --json
  JUPYTERLAB_COMMANDS_TOKEN=... jupyterlab-commands list \\
      --url https://remote-host:8888 --json
"""

EXECUTE_EPILOG = """\
Examples:
  jupyterlab-commands execute docmanager:open --args '{"path": "notebook.ipynb"}'
  jupyterlab-commands execute apputils:notify --args-file notify.json --json
  jupyterlab-commands execute docmanager:open --purpose 'show the report' \\
      --owner data-team
  JUPYTERLAB_COMMANDS_TOKEN=... jupyterlab-commands execute docmanager:open \\
      --url https://remote-host:8888 --args '{"path": "README.md"}'
"""

ACTIVITY_EPILOG = """\
Request:
  POST $JUPYTERHUB_ACTIVITY_URL, the JupyterHub activity route
  {JUPYTERHUB_API_URL}/users/{user}/activity, with the body
  {"last_activity": TS, "servers": {JUPYTERHUB_SERVER_NAME: {"last_activity": TS}}}
  where TS is the current UTC time ending in Z. A hub refusal (HTTP 400, 403
  or 404) prints the hub message and exits 5.

Examples:
  jupyterlab-commands activity
  jupyterlab-commands activity --json
"""


class CliError(Exception):
    """A failure with the process exit code that reports it."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _list_running_servers() -> list[dict[str, Any]]:
    """Run ``jupyter server list --json`` and return its records.

    The command walks the runtime directory with ``os.listdir``, so the order
    of the records carries no meaning.
    """
    try:
        result = subprocess.run(
            ["jupyter", "server", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=SERVER_LIST_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    servers: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            servers.append(record)
    return servers


def _select_server(servers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the server this process belongs to, or None when ambiguous.

    JUPYTERHUB_SERVICE_PREFIX names the server of this process. Without a match
    one listed server is unambiguous and several are not.
    """
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    if prefix:
        wanted = prefix.rstrip("/") + "/"
        for server in servers:
            if server.get("base_url", "/").rstrip("/") + "/" == wanted:
                return server
    if len(servers) == 1:
        return servers[0]
    return None


def _loopback_literals_for(server: dict[str, Any]) -> tuple[str, ...]:
    """Return every loopback literal that reaches the address a record binds."""
    return _LOOPBACK_HOST_FOR.get(server.get("hostname", ""), ())


def _server_url(server: dict[str, Any]) -> str:
    """Build the base URL for one server record.

    A bind address such as localhost can be reached by more than one literal;
    the first literal is the one used for the request.
    """
    scheme = "https" if server.get("secure") else "http"
    hostname = server.get("hostname", "")
    literals = _loopback_literals_for(server)
    if literals:
        host = literals[0]
    else:
        host = f"[{hostname}]" if ":" in hostname else hostname
    base_url = server.get("base_url", "/").rstrip("/")
    return f"{scheme}://{host}:{server['port']}{base_url}"


def _match_listed_server(
    url: str, servers: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the listed record an explicit loopback URL reaches.

    A non-loopback URL never matches: its typed host is a remote target and
    must keep its own address. A loopback URL matches a record when a loopback
    literal either names can reach the other, the port and scheme agree, and
    the base path agrees with the trailing slash normalised.
    """
    try:
        if not _is_loopback(url):
            return None
        parsed = urlparse(url)
        explicit_port = parsed.port
    except ValueError:
        return None
    if explicit_port is not None:
        port = explicit_port
    else:
        port = 443 if parsed.scheme == "https" else 80
    path = parsed.path.rstrip("/")
    # A widened loopback check also accepts addresses such as 127.0.0.2 that
    # the literal table does not carry, so a missing key means no match.
    reachable = _LOOPBACK_URL_HOSTS.get(parsed.hostname, ())
    for server in servers:
        if not set(reachable) & set(_loopback_literals_for(server)):
            continue
        if server.get("port") != port:
            continue
        if bool(server.get("secure")) != (parsed.scheme == "https"):
            continue
        if server.get("base_url", "/").rstrip("/") == path:
            return server
    return None


def _fallback_url() -> str:
    """Build the address from the environment when no record is listed."""
    port = os.environ.get("JUPYTER_PORT") or DEFAULT_PORT
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    base = f"http://127.0.0.1:{port}"
    return base + (prefix.rstrip("/") if prefix else "")


def detect_token() -> str | None:
    """Find an ambient token for this host.

    Checks JUPYTERHUB_API_TOKEN, then JPY_API_TOKEN, then JUPYTER_TOKEN.
    """
    return (
        os.environ.get("JUPYTERHUB_API_TOKEN")
        or os.environ.get("JPY_API_TOKEN")
        or os.environ.get("JUPYTER_TOKEN")
        or None
    )


def _dedicated_token() -> str | None:
    """The token this tool reads for any target, remote included."""
    return os.environ.get("JUPYTERLAB_COMMANDS_TOKEN") or None


def _is_loopback(url: str) -> bool:
    """True when the URL host reaches this host.

    Every address in 127.0.0.0/8, the IPv6 loopback, the legacy numeric
    spellings the resolver accepts (127.1, 2130706433, 0x7f000001,
    0177.0.0.1) and the wildcards 0.0.0.0 and :: count as local. A name other
    than localhost counts only when every address it resolves to reaches this
    host, so a mixed-resolution name stays remote.
    """
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    if host is None:
        return False
    host = host.removesuffix(".")
    if host == "localhost":
        return True
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError):
            return False
        if not infos:
            return False
        for info in infos:
            try:
                address = ipaddress.ip_address(info[4][0])
            except ValueError:
                return False
            if not (address.is_loopback or address.is_unspecified):
                return False
        return True
    return parsed.is_loopback or parsed.is_unspecified


def _clean_url(url: str, *, strip_lab: bool = True) -> str:
    """Remove credentials, the query and the application path.

    A URL pasted from a browser can carry ``?token=`` and end in ``/lab`` or
    ``/lab/tree/...``. Removing them here keeps the secret out of the request
    line, the progress messages and stderr, and leaves the server base that
    the relay endpoints live under. With ``strip_lab`` false the path is kept
    as typed, so the caller can test it against the listed records before the
    application path is guessed away.
    """
    text = url.strip().partition("#")[0].partition("?")[0]
    try:
        parsed = urlparse(text)
    except ValueError as error:
        safe = text.rpartition("@")[2]
        raise CliError(f"bad URL {safe!r}: {error}", EXIT_USAGE) from None
    safe = urlunparse(parsed._replace(netloc=parsed.netloc.rpartition("@")[2]))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CliError(
            f"bad URL {safe!r}: needs an http:// or https:// prefix and a host",
            EXIT_USAGE,
        )
    netloc = parsed.netloc.rpartition("@")[2]
    path = _strip_lab_path(parsed.path) if strip_lab else parsed.path
    return urlunparse(parsed._replace(netloc=netloc, path=path))


def _strip_lab_path(path: str) -> str:
    """Reduce a JupyterLab application path to the server base path.

    The first ``/lab/tree`` marker is removed, so the tree path after it goes
    too. Without that marker a trailing ``/lab`` application segment is
    removed. A bare server base path that itself ends in ``lab``, such as a
    JupyterHub user path, is indistinguishable from the application segment at
    this level, so the caller matches the typed path against the listed server
    records before this guess.
    """
    path = path.rstrip("/")
    marker = path.find("/lab/tree")
    if marker != -1:
        path = path[:marker]
    elif path.endswith("/lab"):
        path = path[: -len("/lab")]
    return path.rstrip("/")


def _resolve_target(args: argparse.Namespace) -> tuple[str, str | None, bool]:
    """Resolve the server base URL, the token and the local-target flag.

    The token order matches the reference client: --token, then
    JUPYTERLAB_COMMANDS_TOKEN, then the matched record's own token, then the
    ambient variables for a loopback target only. The flag is true for a
    listed record: a record names this host, so its request must bypass any
    configured proxy even when the record host is a non-loopback address.
    """
    server: dict[str, Any] | None = None
    if args.url:
        servers = _list_running_servers()
        url = _clean_url(args.url)
        # An explicit loopback URL names a server by address. Match the path
        # exactly as typed first: a record whose base_url equals it is the
        # strongest reading, and _strip_lab_path cannot tell a bare base that
        # ends in /lab from the application segment. The stripped form keeps
        # every pasted application path matching as before. Either way, the
        # record's own address is used because urllib resolves localhost
        # itself and may choose the family the server does not listen on.
        server = _match_listed_server(
            _clean_url(args.url, strip_lab=False), servers
        )
        if server is None:
            server = _match_listed_server(url, servers)
        if server is not None:
            url = _server_url(server)
    else:
        servers = _list_running_servers()
        server = _select_server(servers)
        if server is not None:
            url = _server_url(server)
        elif servers:
            listed = "\n".join(f"  {_server_url(record)}" for record in servers)
            raise CliError(
                "several Jupyter servers are running and JUPYTERHUB_SERVICE_PREFIX "
                "matches none of them; choose one with --url:\n" + listed,
                EXIT_USAGE,
            )
        else:
            url = _fallback_url()

    token = args.token or _dedicated_token()
    # A record names this host and this port, so its own token is the right
    # credential whatever the address text looks like.
    if token is None and server is not None:
        token = server.get("token") or None
    # The ambient variables belong to this host, not to the target, so they
    # stay gated on the target being loopback.
    if token is None and _is_loopback(url):
        token = detect_token()
    return url, token, server is not None


def _exit_code_for_status(status: int, code: str | None = None) -> int:
    if status == 503:
        return EXIT_NO_CLIENT
    if status == 403:
        # Jupyter answers 403 when the token is missing or wrong. Only the
        # relay's own code means the browser refused the command.
        if code == "command-not-allowed":
            return EXIT_NOT_ALLOWED
        return EXIT_USAGE
    if 400 <= status < 500:
        return EXIT_USAGE
    return EXIT_EXECUTION


def _error_details(body: bytes) -> tuple[str | None, str]:
    """Extract the error code and reason from an error body, if present."""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None, ""
    if not isinstance(data, dict):
        return None, ""
    code = None
    message = ""
    error = data.get("error")
    if isinstance(error, dict):
        if isinstance(error.get("code"), str):
            code = error["code"]
        if isinstance(error.get("message"), str):
            message = error["message"]
    elif isinstance(error, str):
        message = error
    if not message:
        fallback = data.get("message")
        if isinstance(fallback, str):
            message = fallback
    return code, message


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, so the request cannot reach another host.

    urllib copies every non-content header, including Authorization, to the
    redirect target and turns a redirected POST into a GET. A 3xx therefore
    raises HTTPError and is reported against the URL the user named.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
    token: str | None,
    timeout: int,
    timeout_exit: int,
    *,
    local: bool = False,
) -> dict[str, Any]:
    """Post one JSON request to the relay and return its JSON answer."""
    url = f"{base_url.rstrip('/')}/{API_NAMESPACE}/api/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    # Loopback requests must not go through a proxy: the proxy would receive
    # the token and could answer in place of the lab. A listed record names
    # this host, so its request bypasses the proxy too, whatever its address.
    # A remote server keeps the configured proxy.
    if local or _is_loopback(base_url):
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
    else:
        opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        try:
            raw = error.read()
        except (HTTPException, OSError):
            raw = b""
        code, reason = _error_details(raw)
        message = f"HTTP {error.code} {error.reason} from {base_url}"
        if reason:
            message += f": {reason}"
        raise CliError(
            message, _exit_code_for_status(error.code, code)
        ) from None
    except TimeoutError:
        raise CliError(
            f"no answer from {base_url} within {timeout}s", timeout_exit
        ) from None
    except urllib.error.URLError as error:
        raise CliError(
            f"cannot reach {base_url}: {error.reason}", EXIT_USAGE
        ) from None
    except (HTTPException, OSError) as error:
        raise CliError(
            f"connection to {base_url} failed before a usable answer arrived "
            f"({error!r})",
            timeout_exit,
        ) from None
    except ValueError:
        # http.client refuses a header value that carries a CR, an LF or a
        # character outside latin-1. Its exception text quotes that value, so
        # the token must not reach the message.
        raise CliError(
            "the token or URL contains characters an HTTP header cannot carry",
            EXIT_USAGE,
        ) from None
    try:
        answer = json.loads(body.decode("utf-8"))
    except ValueError:
        raise CliError(
            f"unreadable answer from {base_url}; is the server extension "
            "jupyterlab_commands_extension loaded?",
            EXIT_USAGE,
        ) from None
    if not isinstance(answer, dict):
        raise CliError(
            f"unreadable answer from {base_url}; expected one JSON object",
            EXIT_USAGE,
        )
    return answer


def _run_activity(args: argparse.Namespace) -> int:
    """Send one activity timestamp to JupyterHub, as the hub notifier does."""
    # --url and --token name the lab; a lab token must never reach the hub.
    if args.url or args.token:
        raise CliError(
            "--url and --token name the lab target and do not apply to activity, "
            "which sends the hub token to JUPYTERHUB_ACTIVITY_URL only",
            EXIT_USAGE,
        )
    url = os.environ.get("JUPYTERHUB_ACTIVITY_URL")
    token = os.environ.get("JUPYTERHUB_API_TOKEN") or os.environ.get("JPY_API_TOKEN")
    if not url or not token:
        missing = (
            "JUPYTERHUB_ACTIVITY_URL"
            if not url
            else "JUPYTERHUB_API_TOKEN or JPY_API_TOKEN"
        )
        raise CliError(
            f"{missing} is not set; activity runs only in a lab started by "
            "JupyterHub",
            EXIT_USAGE,
        )
    server = os.environ.get("JUPYTERHUB_SERVER_NAME", "")
    # The form jupyterhub.utils.isoformat produces: naive UTC with a Z suffix.
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    payload = {
        "servers": {server: {"last_activity": timestamp}},
        "last_activity": timestamp,
    }
    # The hub notifier ignores proxy variables, and the token must reach only
    # the hub, so the request takes no proxy and follows no redirect.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"token {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with opener.open(request, timeout=REQUEST_TIMEOUT_S):
            pass
    except urllib.error.HTTPError as error:
        try:
            raw = error.read()
        except (HTTPException, OSError):
            raw = b""
        # Only a JSON message is printed; an HTML error page never is.
        _, reason = _error_details(raw)
        status = error.code
        if status in (400, 403, 404) and reason:
            message = reason
        else:
            message = f"HTTP {status} {error.reason} from {url}"
            if reason:
                message += f": {reason}"
        return _activity_refused(args, status, message)
    except TimeoutError:
        raise CliError(
            f"no answer from {url} within {REQUEST_TIMEOUT_S}s", EXIT_USAGE
        ) from None
    except urllib.error.URLError as error:
        raise CliError(f"cannot reach {url}: {error.reason}", EXIT_USAGE) from None
    except (HTTPException, OSError) as error:
        raise CliError(
            f"connection to {url} failed before a usable answer arrived "
            f"({error!r})",
            EXIT_USAGE,
        ) from None
    except ValueError:
        # The exception text of a refused header quotes the token.
        raise CliError(
            "the token or URL contains characters an HTTP header cannot carry",
            EXIT_USAGE,
        ) from None
    if args.json:
        print(
            json.dumps(
                {"ok": True, "last_activity": timestamp, "server": server},
                sort_keys=True,
            )
        )
    else:
        print(f"sent hub activity last_activity={timestamp}")
    return EXIT_OK


def _activity_refused(args: argparse.Namespace, status: int, message: str) -> int:
    """Report a hub refusal of activity and return the execution exit code."""
    if not args.json:
        raise CliError(message, EXIT_EXECUTION)
    print(
        json.dumps(
            {"ok": False, "status": status, "message": message}, sort_keys=True
        )
    )
    return EXIT_EXECUTION


def _read_arguments(args: argparse.Namespace) -> dict[str, Any]:
    """Read --args or --args-file and parse one JSON object."""
    if args.args_file:
        try:
            text = Path(args.args_file).read_text(encoding="utf-8")
        except OSError as error:
            raise CliError(
                f"cannot read {args.args_file}: {error}", EXIT_USAGE
            ) from None
    elif args.args is not None:
        text = args.args
    else:
        return {}
    try:
        value = json.loads(text)
    except ValueError as error:
        raise CliError(f"arguments are not valid JSON: {error}", EXIT_USAGE) from None
    if not isinstance(value, dict):
        raise CliError("arguments must be one JSON object", EXIT_USAGE)
    return value


def _print_data(data: Any) -> None:
    if data is None:
        return
    if isinstance(data, str):
        print(data)
        return
    print(json.dumps(data, indent=2, sort_keys=True))


def _run_list(args: argparse.Namespace) -> int:
    url, token, local = _resolve_target(args)
    answer = _post(
        url, "list", {}, token, REQUEST_TIMEOUT_S, EXIT_USAGE, local=local
    )
    if args.json:
        print(json.dumps(answer, sort_keys=True))
        return EXIT_OK
    for command in answer.get("allowed", []):
        print(command)
    return EXIT_OK


def _execution_context(args: argparse.Namespace) -> dict[str, str]:
    """The optional purpose and owner, stripped and checked.

    The body carries a value only when its flag is given, so an execute
    without either flag sends the same body as before.
    """
    context: dict[str, str] = {}
    for name in ("purpose", "owner"):
        value = getattr(args, name)
        if value is None:
            continue
        value = value.strip()
        if not value:
            raise CliError(f"--{name} must not be empty", EXIT_USAGE)
        context[name] = value
    if len(context.get("purpose", "").split()) > PURPOSE_WORD_LIMIT:
        raise CliError(
            f"--purpose must be at most {PURPOSE_WORD_LIMIT} words", EXIT_USAGE
        )
    return context


def _run_execute(args: argparse.Namespace) -> int:
    command_args = _read_arguments(args)
    payload = {
        "command": args.command,
        "args": command_args,
        **_execution_context(args),
    }
    url, token, local = _resolve_target(args)
    answer = _post(
        url,
        "execute",
        payload,
        token,
        EXECUTE_TIMEOUT_S,
        EXIT_EXECUTION,
        local=local,
    )
    if args.json:
        print(json.dumps(answer, sort_keys=True))
    else:
        _print_data(answer.get("data"))
    return EXIT_OK


def _add_common_options(parser: argparse.ArgumentParser, suppress: bool) -> None:
    """Add --url, --token and --json to a parser.

    With ``suppress`` the options leave the namespace untouched when they are
    absent, so a value given before a subcommand survives the subparser.
    """
    default_url = argparse.SUPPRESS if suppress else None
    default_json = argparse.SUPPRESS if suppress else False
    parser.add_argument(
        "--url",
        default=default_url,
        help=(
            "base URL of the Jupyter server; overrides discovery. A loopback "
            "URL that matches a listed server uses that record's address and "
            "token"
        ),
    )
    parser.add_argument(
        "--token",
        default=default_url,
        help=(
            "authentication token; it puts the secret in argv where "
            "/proc/<pid>/cmdline exposes it, so prefer JUPYTERLAB_COMMANDS_TOKEN"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=default_json,
        help=(
            "print machine-readable JSON; with list, each command's argument "
            "schema"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, suppress=True)

    parser = argparse.ArgumentParser(
        prog="jupyterlab-commands",
        description=(
            "Run an allowed JupyterLab command in a browser tab that has the "
            "commands extension open."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_options(parser, suppress=False)
    parser.add_argument(
        "--list",
        action="store_true",
        help=(
            "list the command ids the browser allows; --json adds each "
            "command's argument schema"
        ),
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    subparsers.add_parser(
        "list",
        parents=[common],
        help="list the allowed commands and their arguments",
        description=(
            "List the command ids the browser allows the CLI to run. --json "
            "prints each allowed command with its argument schema."
        ),
        epilog=LIST_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    execute = subparsers.add_parser(
        "execute",
        parents=[common],
        help="execute one allowed command",
        description="Run one allowed command in the browser tab and print its result.",
        epilog=EXECUTE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    execute.add_argument("command", help="command id, for example docmanager:open")
    source = execute.add_mutually_exclusive_group()
    source.add_argument("--args", help="command arguments as one JSON object")
    source.add_argument(
        "--args-file", help="file holding the command arguments as one JSON object"
    )
    execute.add_argument(
        "--purpose", help="short purpose of this execution, at most 25 words"
    )
    execute.add_argument(
        "--owner", help="owner of this action, an agent name or a project name"
    )
    subparsers.add_parser(
        "activity",
        parents=[common],
        help="post the current time to the JupyterHub activity route",
        description=(
            "Post the current time to the JupyterHub activity route as this "
            "server's last activity, the same write the single-user notifier "
            "makes. One call marks the server active once; the hub culls it "
            "as idle after its idle timeout counted from the last mark, so "
            "while work runs, repeat the call at an interval shorter than "
            "that timeout. It needs no browser tab. The hub answers 200 even "
            "when the time does not move, because the route never moves time "
            "backwards. The hub token goes to JUPYTERHUB_ACTIVITY_URL only; "
            "--url and --token do not apply."
        ),
        epilog=ACTIVITY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.list and args.subcommand in ("execute", "activity"):
            raise CliError(
                f"--list cannot be combined with the {args.subcommand} subcommand",
                EXIT_USAGE,
            )
        if args.list or args.subcommand == "list":
            return _run_list(args)
        if args.subcommand == "execute":
            return _run_execute(args)
        if args.subcommand == "activity":
            return _run_activity(args)
        parser.print_help()
        return EXIT_USAGE
    except CliError as error:
        print(f"jupyterlab-commands: {error.message}", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        print("jupyterlab-commands: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
