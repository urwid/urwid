#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tornado>=6.5.8",
#     "urwid>=5.1.0",
# ]
# ///
"""Serve an urwid application to web browsers over a WebSocket, with Tornado.

Every browser page that connects gets its own session: one :class:`urwid.display.websocket.Screen`
and one :class:`urwid.MainLoop`, all on the one Tornado event loop.
The session ends when the page closes, when the user selects :guilabel:`Quit`,
or when no input arrived for the idle timeout.

.. warning::
    This is an example of how to connect the screen to a server library, not a production server.
    Its TLS support only loads the certificate and key it is given, and it was not tested against real clients.
    Whoever builds a production service on it is responsible for its TLS:
    the certificates and their renewal, the protocol versions and ciphers,
    and usually a reverse proxy or load balancer that terminates TLS.
    The same holds for authentication beyond the single shared token shown here.

The example is as strict as Tornado allows:

- It listens on ``127.0.0.1`` unless told otherwise,
  and refuses another address unless it has TLS.
- It answers only requests whose ``Host`` header names an allowed origin,
  and accepts a WebSocket only from a page whose ``Origin`` is an allowed origin.
  The default origins are the address it listens on, and ``localhost`` for a loopback address.
- Every request needs HTTP Basic authentication with the token from ``--token-file`` as the password,
  also on the loopback address, where every user of the host can connect.
  When the file does not exist, the example creates it, readable by its owner only, with a new random token.
  An existing token file is refused unless it is a regular file of this user that no other user can read or write.
  The token is compared in constant time, and any user name is accepted.
  The token never appears in a URL or a log line.
- After repeated failed logins from one client, or from all clients together, logins are refused for a while
  without checking the token.
- The page has no inline script or style,
  and every response forbids inline script, framing, content sniffing and the ``Referer`` header.
- A WebSocket message is limited in size, the number of sessions is limited,
  and a session whose page stops reading its screen updates is closed.
- An exception in one session's application closes that session; the server and the other sessions go on.

Behind a reverse proxy that terminates TLS and authenticates users, listen on ``127.0.0.1``,
pass the public origin with ``--allowed-origin https://tui.example.org``,
and have the proxy forward the ``Host`` header unchanged and pass the WebSocket upgrade through.

To make a token file by hand::

    (umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(32))" > token)

The script reads only the files named by its options, writes nothing but a new token file,
and logs to standard error.
It exits with status 0 after ``SIGINT`` or ``SIGTERM``, and with status 2 when an option is invalid.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import dataclasses
import hmac
import ipaddress
import logging
import math
import os
import pathlib
import re
import secrets
import signal
import ssl
import stat
import sys
import time
import typing
import urllib.parse
from contextlib import suppress

import tornado.httputil
import tornado.ioloop
import tornado.web
import tornado.websocket

import urwid
import urwid.display.websocket as urwid_websocket

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

LOG: typing.Final = logging.getLogger("websocket_tornado")

TITLE: typing.Final = "Urwid WebSocket demo"
# the WebSocket URL, relative to the page
WEBSOCKET_PATH: typing.Final = "ws"
# UTF-8 takes at most 4 bytes per character
MAX_MESSAGE_BYTES: typing.Final = urwid_websocket.MAX_MESSAGE_LENGTH * 4
# screen updates handed to Tornado and not yet written to the socket; a page that stops reading is closed
MAX_UNWRITTEN_UPDATES: typing.Final = 32
# random bytes in a token the example creates
NEW_TOKEN_BYTES: typing.Final = 32
# a token file larger than this is refused rather than read
MAX_TOKEN_FILE_BYTES: typing.Final = 4096
# a token shorter than this is refused, since it is the only secret
MIN_TOKEN_BYTES: typing.Final = 16
PING_INTERVAL: typing.Final = 30.0
# failed logins, in seconds, that count towards the limits below
FAILURE_WINDOW: typing.Final = 60.0
# failed logins from one client network within the window before its logins are refused
MAX_FAILURES_PER_CLIENT: typing.Final = 5
# failed logins from all clients within the window before every login is refused; it bounds guessing from many addresses
MAX_FAILURES_TOTAL: typing.Final = 100
# Tornado caps the timeout at the interval
PING_TIMEOUT: typing.Final = 20.0

PALETTE: typing.Final = [
    ("header", "white", "dark blue"),
    ("button", "black", "light gray"),
    ("button focus", "white", "dark red"),
]


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class Config:
    """Validated server settings."""

    host: str
    port: int
    # Origin header values accepted on the WebSocket handshake
    allowed_origins: frozenset[str]
    # Host header values accepted on any request
    allowed_hosts: frozenset[str]
    token: bytes = dataclasses.field(repr=False)
    tls: ssl.SSLContext | None = dataclasses.field(repr=False)
    max_sessions: int
    idle_timeout: float


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line and return the raw parsed arguments."""
    parser = argparse.ArgumentParser(description=__doc__.partition("\n")[0])
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8080, help="port to listen on (default: %(default)s)")
    parser.add_argument(
        "--allowed-origin",
        action="append",
        metavar="ORIGIN",
        help="origin such as https://tui.example.org the page is served from; repeat for several; "
        "replaces the default of the listening address",
    )
    parser.add_argument(
        "--certfile",
        type=pathlib.Path,
        help="TLS certificate chain in PEM format; production TLS is the deployer's responsibility",
    )
    parser.add_argument("--keyfile", type=pathlib.Path, help="TLS private key in PEM format")
    parser.add_argument(
        "--token-file",
        type=pathlib.Path,
        required=True,
        help=f"file holding the token users enter as the password, at least {MIN_TOKEN_BYTES} bytes; "
        "created with a new random token when it does not exist",
    )
    parser.add_argument("--max-sessions", type=int, default=8, help="sessions at a time (default: %(default)s)")
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=900.0,
        help="seconds without input before a session is closed (default: %(default)s)",
    )
    parser.add_argument("--debug", action="store_true", help="log debug messages")
    return parser.parse_args(argv)


def load_token(path: pathlib.Path) -> bytes:
    """Return the token in *path*.

    When the file does not exist, it is created, readable by its owner only, with a new random token.
    Creating it never writes through an existing file or symbolic link, and its path is logged, never the token.

    An existing file is read only when it is a regular file reached without a symbolic link,
    no larger than ``MAX_TOKEN_FILE_BYTES``, owned by this user, and neither readable nor writable by others.
    So a file another user planted at the path, a FIFO or a device is refused instead of trusted or waited on.

    :raises ValueError: the file is not such a file, or holds a token shorter than ``MIN_TOKEN_BYTES``.
    :raises OSError: the file cannot be created or opened, or the path is a symbolic link.
    """
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="ascii") as new_file:
            new_file.write(secrets.token_urlsafe(NEW_TOKEN_BYTES) + "\n")
        LOG.info("Created %s with a new token; users enter its content as the password", path)

    # Windows has neither flag; there the type and size checks below still apply
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as token_file:
        status = os.fstat(token_file.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_TOKEN_FILE_BYTES:
            raise ValueError(f"{path} is not a regular file of at most {MAX_TOKEN_FILE_BYTES} bytes")
        # Windows file owners and modes do not describe who can read the file
        if os.name == "posix":
            if status.st_uid != os.geteuid():
                raise ValueError(f"{path} belongs to another user")
            if status.st_mode & 0o077:
                raise ValueError(f"other users can read or write {path}; make it private with: chmod 600 {path}")
        token = token_file.read(MAX_TOKEN_FILE_BYTES).rstrip(b"\r\n")
    if len(token) < MIN_TOKEN_BYTES:
        raise ValueError(f"the token must be at least {MIN_TOKEN_BYTES} bytes long")
    return token


def build_config(args: argparse.Namespace) -> Config:
    """Check the parsed arguments and turn them into a :class:`Config`.

    :raises ValueError: an argument is invalid, or the combination of arguments is unsafe.
    :raises OSError: the token file cannot be read or created, or the certificate or key cannot be read.
    :raises ssl.SSLError: the certificate or key is invalid.
    """
    if not 0 < args.port < 65536:
        raise ValueError(f"--port must be between 1 and 65535: {args.port}")
    if args.max_sessions < 1:
        raise ValueError("--max-sessions must be at least 1")
    if not args.idle_timeout > 0:
        raise ValueError("--idle-timeout must be positive")
    if (args.certfile is None) != (args.keyfile is None):
        raise ValueError("--certfile and --keyfile go together")

    tls = None
    if args.certfile is not None:
        tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(args.certfile, args.keyfile)

    try:
        address = ipaddress.ip_address(args.host)
    except ValueError:
        loopback = args.host == "localhost"
        unspecified = False
    else:
        loopback = address.is_loopback
        unspecified = address.is_unspecified
    if not loopback and tls is None:
        raise ValueError("listening on a non-loopback address needs --certfile and --keyfile")

    scheme = "https" if tls is not None else "http"
    if args.allowed_origin:
        given = args.allowed_origin
    elif unspecified:
        raise ValueError(f"listening on all addresses ({args.host}) needs --allowed-origin")
    else:
        host = f"[{args.host}]" if ":" in args.host else args.host
        given = [f"{scheme}://{host}:{args.port}", *([f"{scheme}://localhost:{args.port}"] if loopback else [])]
    origins = set()
    hosts = set()
    for origin in given:
        parts = urllib.parse.urlsplit(origin)
        if parts.scheme not in {"http", "https"} or not parts.hostname or origin != f"{parts.scheme}://{parts.netloc}":
            raise ValueError(f"an origin is a scheme and a host with an optional port, nothing else: {origin!r}")
        # browsers send the host in lowercase and leave out the default port of the scheme
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        if parts.port is not None and parts.port != {"http": 80, "https": 443}[parts.scheme]:
            host = f"{host}:{parts.port}"
        origins.add(f"{parts.scheme}://{host}")
        hosts.add(host)

    # read or created last, so a run refused for another argument changes nothing
    token = load_token(args.token_file)
    return Config(
        host=args.host,
        port=args.port,
        allowed_origins=frozenset(origins),
        allowed_hosts=frozenset(hosts),
        token=token,
        tls=tls,
        max_sessions=args.max_sessions,
        idle_timeout=args.idle_timeout,
    )


def content_security_policy(config: Config) -> str:
    """Return the policy that allows only the page's own files and its WebSocket."""
    sockets = " ".join(sorted(re.sub("^http", "ws", origin) for origin in config.allowed_origins))
    return (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        f"connect-src 'self' {sockets}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


def set_security_headers(handler: tornado.web.RequestHandler, config: Config) -> None:
    """Set the headers every response carries."""
    handler.clear_header("Server")
    handler.set_header("Content-Security-Policy", content_security_policy(config))
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.set_header("Referrer-Policy", "no-referrer")
    handler.set_header("X-Frame-Options", "DENY")
    handler.set_header("Cross-Origin-Opener-Policy", "same-origin")
    handler.set_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.set_header("Cache-Control", "no-store")
    if config.tls is not None:
        handler.set_header("Strict-Transport-Security", "max-age=31536000")


def client_network(address: str) -> str:
    """Return the network a login limit applies to: the IPv4 address, or the /64 prefix of an IPv6 address.

    One host commonly holds a whole IPv6 /64, so a limit per IPv6 address could be avoided by changing address.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


class LoginLimiter:
    """Refuse logins for a while after too many recent failures from one client network, or from all clients.

    A refused login is not checked against the token and does not count as a failure.
    So no more than ``MAX_FAILURES_TOTAL`` failures are ever kept.
    Behind a reverse proxy every request comes from the proxy, so the limit per client applies to all clients.
    """

    __slots__ = ("__weakref__", "_failures")

    def __init__(self) -> None:
        """Start with no failures."""
        # the time and the client network of each failed login within the window, oldest first
        self._failures: collections.deque[tuple[float, str]] = collections.deque()

    def retry_after(self, address: str) -> float:
        """Return the seconds until a login from *address* is checked again, or 0 when it is checked now."""
        now = time.monotonic()
        while self._failures and self._failures[0][0] <= now - FAILURE_WINDOW:
            self._failures.popleft()
        if len(self._failures) >= MAX_FAILURES_TOTAL:
            return self._failures[0][0] + FAILURE_WINDOW - now
        network = client_network(address)
        times = [failed_at for failed_at, failed_network in self._failures if failed_network == network]
        if len(times) >= MAX_FAILURES_PER_CLIENT:
            return times[len(times) - MAX_FAILURES_PER_CLIENT] + FAILURE_WINDOW - now
        return 0.0

    def record_failure(self, address: str) -> None:
        """Count a failed login from *address*."""
        self._failures.append((time.monotonic(), client_network(address)))


def reject_request(handler: tornado.web.RequestHandler, config: Config, limiter: LoginLimiter) -> bool:
    """Answer a request with an unknown ``Host`` or without the token, and return whether it was answered."""
    request = handler.request
    if request.host not in config.allowed_hosts:
        LOG.error("Refused a request for an unknown host from %s", request.remote_ip)
        handler.send_error(400)
        return True
    # requests without a known address share one limit
    address = request.remote_ip or ""
    if (wait := limiter.retry_after(address)) > 0:
        LOG.debug("Refused a login from %s during its login limit", request.remote_ip)
        handler.set_status(429)
        handler.set_header("Retry-After", str(math.ceil(wait)))
        handler.finish()
        return True

    authorization = request.headers.get("Authorization")
    scheme, _, encoded = (authorization or "").partition(" ")
    password = b""
    if scheme.lower() == "basic":
        # binascii.Error, and ValueError for a header that is not ASCII
        with suppress(ValueError):
            _user, _, password = base64.b64decode(encoded, validate=True).partition(b":")
    if password and hmac.compare_digest(password, config.token):
        return False

    # a request without credentials, such as the first one a browser sends, is not a guess
    if authorization is None:
        LOG.debug("Asked %s for credentials", request.remote_ip)
    else:
        LOG.error("Refused a login with a wrong token from %s", request.remote_ip)
        limiter.record_failure(address)
        if limiter.retry_after(address) > 0:
            LOG.warning("Refusing logins from %s for %.0f seconds", request.remote_ip, FAILURE_WINDOW)
    handler.set_status(401)
    handler.set_header("WWW-Authenticate", 'Basic realm="urwid", charset="UTF-8"')
    handler.finish()
    return True


class PageHandler(tornado.web.RequestHandler):  # pylint: disable=abstract-method  # no streamed request body
    """Serve the page and the files it loads."""

    def __init__(
        self,
        application: tornado.web.Application,
        request: tornado.httputil.HTTPServerRequest,
        *,
        config: Config,
        limiter: LoginLimiter,
        files: dict[str, tuple[str, bytes]],
    ) -> None:
        """Serve *files*, by request path, under the settings in *config*."""
        self.config = config
        self.limiter = limiter
        self.files = files
        super().__init__(application, request)

    def set_default_headers(self) -> None:
        """Set the security headers."""
        set_security_headers(self, self.config)

    def prepare(self) -> None:
        """Refuse a request for an unknown host or without the token."""
        reject_request(self, self.config, self.limiter)

    def get(self, name: str) -> None:
        """Send the page or one of its files."""
        content_type, body = self.files[name]
        self.set_header("Content-Type", content_type)
        self.finish(body)


class Connection:
    """Transport of a :class:`~urwid.display.websocket.Screen` over a Tornado WebSocket."""

    __slots__ = ("__weakref__", "_closing", "_handler", "_unwritten")

    def __init__(self, handler: tornado.websocket.WebSocketHandler) -> None:
        """Send through *handler*."""
        self._handler = handler
        self._unwritten = 0
        # set once a page that does not read its updates is being disconnected
        self._closing = False

    def send(self, text: str) -> None:
        """Hand *text* to Tornado, or close the session when the page does not read its updates."""
        if self._closing:
            return
        if self._unwritten >= MAX_UNWRITTEN_UPDATES:
            self._closing = True
            LOG.warning("Closing a session whose page does not read its screen updates")
            self._handler.close(1008, "updates not read")
            return
        try:
            written = self._handler.write_message(text)
        except tornado.websocket.WebSocketClosedError:
            return
        self._unwritten += 1
        written.add_done_callback(self._written)

    def close(self) -> None:
        """Close the WebSocket."""
        self._handler.close()

    def _written(self, written: asyncio.Future[None]) -> None:
        """Count one update as written, also when the connection closed before it was."""
        self._unwritten -= 1
        if not written.cancelled():
            written.exception()  # a closed connection is reported by on_close


class SessionHandler(tornado.websocket.WebSocketHandler):  # pylint: disable=abstract-method  # no streamed body
    """One browser page: a screen and a main loop for as long as the WebSocket is open."""

    def __init__(
        self,
        application: tornado.web.Application,
        request: tornado.httputil.HTTPServerRequest,
        *,
        config: Config,
        limiter: LoginLimiter,
        sessions: set[SessionHandler],
    ) -> None:
        """Handle one WebSocket under the settings in *config*, joining the open *sessions* once it opens."""
        self.config = config
        self.limiter = limiter
        self.sessions = sessions
        self.screen: urwid_websocket.Screen | None = None
        self.main_loop: urwid.MainLoop | None = None
        self.idle_timer: object | None = None
        super().__init__(application, request)

    def set_default_headers(self) -> None:
        """Set the security headers."""
        set_security_headers(self, self.config)

    def prepare(self) -> None:
        """Refuse a handshake for an unknown host or without the token."""
        reject_request(self, self.config, self.limiter)

    def check_origin(self, origin: str) -> bool:
        """Accept only a page served from an allowed origin."""
        if origin in self.config.allowed_origins:
            return True
        LOG.error("Refused a WebSocket from a page of another origin, from %s", self.request.remote_ip)
        return False

    def open(self, *args: str, **kwargs: str) -> None:
        """Start a session, or close the WebSocket when the session limit is reached."""
        if len(self.sessions) >= self.config.max_sessions:
            LOG.warning("Refused a session: %d sessions are open", len(self.sessions))
            self.close(1013, "too many sessions")
            return
        self.set_nodelay(True)
        self.sessions.add(self)
        self.screen = urwid_websocket.Screen(Connection(self))
        self.main_loop = urwid.MainLoop(
            build_widget(),
            PALETTE,
            screen=self.screen,
            # the IOLoop is shared by every session, so an error here ends this session only
            event_loop=urwid.GuardedEventLoop(urwid.TornadoEventLoop(), self._on_application_error),
        )
        self.main_loop.start()
        self._reset_idle_timer()
        LOG.info("Session opened, %d open", len(self.sessions))

    def on_message(self, message: str | bytes) -> None:
        """Pass a message to the screen, and close the session when it is invalid."""
        if self.screen is None:
            return
        try:
            self.screen.feed(message)
        except urwid_websocket.InvalidMessageError as exc:
            LOG.error("Closing a session after an invalid message: %s", exc)  # noqa: TRY400  # the reason is the report
            self.close(1008, "invalid message")
            return
        self._reset_idle_timer()

    def on_close(self) -> None:
        """Stop the session's main loop."""
        io_loop = tornado.ioloop.IOLoop.current()
        if self.idle_timer is not None:
            io_loop.remove_timeout(self.idle_timer)
            self.idle_timer = None
        if self.main_loop is not None:
            self.main_loop.stop()
            self.main_loop = None
        if self in self.sessions:
            self.sessions.discard(self)
            LOG.info("Session closed, %d open", len(self.sessions))

    def _on_application_error(self, exc: Exception) -> None:
        """Close this session after its application raised *exc*."""
        if self.screen is None or self.screen.closed:
            return
        if isinstance(exc, urwid.ExitMainLoop):
            LOG.info("Session ended by its application")
        else:
            LOG.error("Closing a session after an error in its application", exc_info=exc)
        self.screen.close()

    def _reset_idle_timer(self) -> None:
        """Close the session when no input arrives for the idle timeout from now."""
        io_loop = tornado.ioloop.IOLoop.current()
        if self.idle_timer is not None:
            io_loop.remove_timeout(self.idle_timer)
        self.idle_timer = io_loop.call_later(self.config.idle_timeout, self.close, 1000, "idle timeout")


def build_widget() -> urwid.Widget:
    """Return the widget of one session.

    Selecting :guilabel:`Quit` raises :exc:`urwid.ExitMainLoop`, which ends this session only.
    """
    reply = urwid.Text("")
    name = urwid.Edit("What is your name? ")

    def on_name_change(edit: urwid.Edit, _old_text: str) -> None:
        reply.set_text(f"Nice to meet you, {edit.edit_text}." if edit.edit_text else "")

    def on_quit(_button: urwid.Button) -> typing.NoReturn:
        raise urwid.ExitMainLoop

    urwid.connect_signal(name, "postchange", on_name_change)
    quit_button = urwid.AttrMap(urwid.Button("Quit", on_quit), "button", "button focus")
    body = urwid.ListBox(urwid.SimpleFocusListWalker([name, reply, urwid.Divider(), quit_button]))
    header = urwid.AttrMap(urwid.Text(f"{TITLE}: each browser tab is a session of its own"), "header")
    return urwid.Frame(body, header=header)


def make_app(config: Config, sessions: set[SessionHandler]) -> tornado.web.Application:
    """Return the application that serves the page, its files and the WebSocket."""
    limiter = LoginLimiter()
    files = {name: (static.content_type, static.read()) for name, static in urwid_websocket.STATIC_FILES.items()}
    files[""] = ("text/html; charset=utf-8", urwid_websocket.html_page(TITLE, WEBSOCKET_PATH).encode("utf-8"))
    file_pattern = "|".join(re.escape(name) for name in files)
    return tornado.web.Application(
        [
            (f"/({file_pattern})", PageHandler, {"config": config, "limiter": limiter, "files": files}),
            (
                f"/{re.escape(WEBSOCKET_PATH)}",
                SessionHandler,
                {"config": config, "limiter": limiter, "sessions": sessions},
            ),
        ],
        websocket_max_message_size=MAX_MESSAGE_BYTES,
        websocket_ping_interval=PING_INTERVAL,
        websocket_ping_timeout=PING_TIMEOUT,
    )


async def serve(config: Config) -> None:
    """Serve until ``SIGINT`` or ``SIGTERM``, then close every session."""
    sessions: set[SessionHandler] = set()
    server = make_app(config, sessions).listen(config.port, config.host, ssl_options=config.tls)
    stop = asyncio.Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        # Windows has no signal handlers in asyncio; Ctrl+C ends the run there instead
        with suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(signal_number, stop.set)

    LOG.info("Serving %s", ", ".join(sorted(config.allowed_origins)))
    await stop.wait()

    LOG.info("Stopping: closing %d sessions", len(sessions))
    server.stop()
    for session in list(sessions):
        session.close(1001, "server stopping")
    await server.close_all_connections()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server and return the process exit status."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    try:
        config = build_config(args)
    except (ValueError, OSError, ssl.SSLError) as exc:
        LOG.error("%s", exc)  # noqa: TRY400  # the message is the whole report; a traceback adds nothing
        return 2
    asyncio.run(serve(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
