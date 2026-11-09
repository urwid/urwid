#!/usr/bin/env python3
#
# Urwid keyboard input test app
#    Copyright (C) 2004-2009  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/
#
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tornado>=6.5.8",
#     "urwid>=5.1",
# ]
# ///
"""Show the input urwid receives for each key press and mouse event, to debug terminals and displays.

Each input is one row: the key names and mouse events the main loop receives,
and the raw codes the display read them from.
:kbd:`Q` asks whether to end the test: :kbd:`Y` ends it, and any other input goes on with it.

The display is chosen with ``--display``:

- ``raw``, the default, and ``curses`` run in the terminal.
  While the test runs, the terminal's signal keys such as Ctrl+C reach it as keys;
  the terminal settings are restored when it ends.
- ``websocket`` serves the test to a browser on this host.
  It is offered when Tornado is installed; the other displays run without it.
  It is a debugging aid, not a server:

  - It listens on ``127.0.0.1`` only, without TLS, and answers only requests for that address.
  - It accepts a WebSocket only from its own page.
  - Every request needs HTTP Basic authentication with a token made for the run.
    The token is kept in a temporary directory, readable by its owner only and removed on exit.
  - It prints the address to open and the login to standard output.
  - Ending the test ends one browser session, and Ctrl+C stops the server.

Run as a CGI script, the test uses the ``web`` display and takes no options.

The script writes ``debug.log`` in the current directory with ``--debug-log``,
and the token file of the ``websocket`` display.
It exits with status 0, with status 1 when the ``websocket`` display cannot start
because the port is in use or the token file cannot be written,
and with status 2 when an option is invalid.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hmac
import importlib.util
import logging
import os
import pathlib
import re
import secrets
import signal
import sys
import tempfile
import typing

import urwid
import urwid.display.websocket as websocket_display

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    import tornado.httputil
    import tornado.web

LOG: typing.Final = logging.getLogger("input_test")

TITLE: typing.Final = "Input Test"
# the header of the test, and the question it shows after Q
HEADER: typing.Final = "Values from get_input(). Q asks to exit."
EXIT_QUESTION: typing.Final = "Exit the input test? Y exits, any other input goes on."

# Dark Monokai: (name, 16-color fg, 16-color bg, monochrome settings, high-color fg, high-color bg).
# "key" and "mouse" set a foreground only and inherit the background of the list box around them.
PALETTE: typing.Final = (
    ("header", "black", "dark green", "standout", "#272822", "#a6e22e"),
    ("listbox", "light gray", "black", None, "#f8f8f2", "#272822"),
    ("key", "yellow,bold", "inherit", "bold", "#e6db74,bold", "inherit"),
    ("mouse", "light cyan,bold", "inherit", "bold,underline", "#66d9ef,bold", "inherit"),
)

# the event loops offered besides "select" and "asyncio", when this installation has them
OPTIONAL_EVENT_LOOPS: typing.Final = {
    "tornado": "TornadoEventLoop",
    "twisted": "TwistedEventLoop",
    "trio": "TrioEventLoop",
    "zmq": "ZMQEventLoop",
}

# the websocket display listens here; only this host can reach it
WEBSOCKET_ADDRESS: typing.Final = "127.0.0.1"
WEBSOCKET_PORT: typing.Final = 8080
# Host header values the websocket display answers
WEBSOCKET_HOSTS: typing.Final = (f"{WEBSOCKET_ADDRESS}:{WEBSOCKET_PORT}", f"localhost:{WEBSOCKET_PORT}")
WEBSOCKET_USER: typing.Final = "urwid"
# the WebSocket URL, relative to the page
WEBSOCKET_PATH: typing.Final = "ws"
# random bytes in the token of the websocket display
TOKEN_BYTES: typing.Final = 32


def event_loops() -> dict[str, type[urwid.EventLoop] | None]:
    """Return the event loops this installation offers, by option value; ``none`` is the main loop's default."""
    loops: dict[str, type[urwid.EventLoop] | None] = {
        "none": None,
        "select": urwid.SelectEventLoop,
        "asyncio": urwid.AsyncioEventLoop,
    }
    for name, class_name in OPTIONAL_EVENT_LOOPS.items():
        if hasattr(urwid, class_name):
            loops[name] = getattr(urwid, class_name)
    return loops


def displays() -> list[str]:
    """Return the displays this installation offers, by option value."""
    offered = ["raw"]
    if importlib.util.find_spec("_curses") is not None:
        offered.append("curses")
    if importlib.util.find_spec("tornado") is not None:
        offered.append("websocket")
    return offered


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and check the command line, exiting with status 2 when it is invalid."""
    parser = argparse.ArgumentParser(description=__doc__.partition("\n")[0])
    parser.add_argument(
        "--display",
        choices=displays(),
        default="raw",
        help="display to use (default: %(default)s); websocket serves the test to a browser on this host",
    )
    parser.add_argument(
        "--extended-keys",
        action="store_true",
        help="ask the terminal to report keys the legacy encodings cannot tell apart, such as ctrl enter (raw only)",
    )
    advanced = parser.add_argument_group("advanced options")
    advanced.add_argument(
        "--event-loop",
        choices=event_loops(),
        default="none",
        help="event loop to use (default: %(default)s, the main loop's own)",
    )
    advanced.add_argument("--debug-log", action="store_true", help="write debug messages to debug.log")
    args = parser.parse_args(argv)
    if args.extended_keys and args.display != "raw":
        parser.error("--extended-keys needs the raw display")
    if args.display == "websocket" and args.event_loop != "none":
        parser.error("--display websocket runs on Tornado's event loop and takes no --event-loop")
    return args


def build_loop(screen: urwid.display.BaseScreen, event_loop: urwid.EventLoop | None) -> urwid.MainLoop:
    """Return the main loop of the test, drawing on *screen* and running on *event_loop*."""
    rows: urwid.SimpleListWalker[urwid.Columns] = urwid.SimpleListWalker([])
    listbox = urwid.ListBox(rows)
    header_text = urwid.Text(HEADER)
    header = urwid.AttrMap(header_text, "header")
    # set after Q, until the next input answers the exit question
    asking = False

    def show_input(
        keys: list[str | tuple[str, int, int, int]],
        raw: list[int],
    ) -> list[str | tuple[str, int, int, int]]:
        """Add a row for *keys* and the *raw* codes they were read from, and return *keys* unchanged.

        :kbd:`q` or :kbd:`Q` among *keys* asks whether to exit.
        The next input answers: :kbd:`y` or :kbd:`Y` exits, anything else is shown as usual.
        A window resize is not an answer.

        :raises urwid.ExitMainLoop: *keys* answer the exit question with :kbd:`y` or :kbd:`Y`.
        """
        nonlocal asking
        if not keys:
            return keys
        answers = [key for key in keys if key != "window resize"]
        if asking and answers:
            if answers[0] in {"y", "Y"}:
                raise urwid.ExitMainLoop
            asking = False
            header_text.set_text(HEADER)

        markup: list[str | tuple[str, str]] = []
        for key in keys:
            if isinstance(key, str):
                markup += ["'", ("key", key), "' "]
                continue
            markup.append("(")
            for index, value in enumerate(key):
                if index:
                    markup.append(", ")
                markup.append(("mouse", repr(value)))
            markup.append(")")
        raw_text = urwid.Text(", ".join(f"{code:d}" for code in raw))
        rows.append(urwid.Columns([(urwid.WEIGHT, 2, urwid.Text(markup)), raw_text]))
        # keep the newest row at the bottom of the list box
        listbox.set_focus(len(rows) - 1, "above")
        if "q" in keys or "Q" in keys:
            asking = True
            header_text.set_text(EXIT_QUESTION)
        return keys

    return urwid.MainLoop(
        urwid.Frame(urwid.AttrMap(listbox, "listbox"), header),
        PALETTE,
        screen,
        input_filter=show_input,
        event_loop=event_loop,
    )


def run_in_terminal(display: str, event_loop: urwid.EventLoop | None, *, extended_keys: bool) -> None:
    """Run the test in the terminal on the ``raw`` or ``curses`` *display*."""
    if display == "curses":
        from urwid.display import curses  # needs the curses extension module, which is optional

        screen: urwid.display.raw.Screen | curses.Screen = curses.Screen()
    else:
        screen = urwid.display.raw.Screen(extended_keys=extended_keys)
    loop = build_loop(screen, event_loop)
    # signal keys such as ctrl c reach the test as keys while it runs
    old_signal_keys = screen.tty_signal_keys("undefined", "undefined", "undefined", "undefined", "undefined")
    try:
        loop.run()
    finally:
        if old_signal_keys:
            screen.tty_signal_keys(*old_signal_keys)


def run_as_cgi() -> None:
    """Run the test for the browser that sent this CGI request, on the ``web`` display."""
    urwid.display.web.set_preferences(TITLE)
    if urwid.display.web.handle_short_request():
        return
    build_loop(urwid.display.web.Screen(), urwid.SelectEventLoop()).run()


def make_websocket_app(token: str) -> tornado.web.Application:
    """Return the application that serves the page, its files and one test session per WebSocket.

    :param token: the password every request has to carry, with the user name ``WEBSOCKET_USER``.
    """
    # Tornado is optional, so it is imported only for this display
    import tornado.web
    import tornado.websocket

    files = {name: (static.content_type, static.read()) for name, static in websocket_display.STATIC_FILES.items()}
    files[""] = ("text/html; charset=utf-8", websocket_display.html_page(TITLE, WEBSOCKET_PATH).encode("utf-8"))
    origins = frozenset(f"http://{host}" for host in WEBSOCKET_HOSTS)
    sockets = " ".join(f"ws://{host}" for host in WEBSOCKET_HOSTS)
    policy = (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        f"connect-src 'self' {sockets}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    expected_user = WEBSOCKET_USER.encode("ascii")
    expected_token = token.encode("ascii")

    def set_headers(handler: tornado.web.RequestHandler) -> None:
        """Forbid inline script, framing, content sniffing, the ``Referer`` header and caching."""
        handler.clear_header("Server")
        handler.set_header("Content-Security-Policy", policy)
        handler.set_header("X-Content-Type-Options", "nosniff")
        handler.set_header("Referrer-Policy", "no-referrer")
        handler.set_header("Cache-Control", "no-store")

    def refuse(handler: tornado.web.RequestHandler) -> None:
        """Answer a request for another host, or one without the login."""
        request = handler.request
        if request.host not in WEBSOCKET_HOSTS:
            handler.send_error(400)
            return
        scheme, _, encoded = request.headers.get("Authorization", "").partition(" ")
        user = password = b""
        if scheme.lower() == "basic":
            # binascii.Error, and ValueError for a header that is not ASCII
            with contextlib.suppress(ValueError):
                user, _, password = base64.b64decode(encoded, validate=True).partition(b":")
        # both compared, so the time taken does not tell which one was wrong
        user_matches = hmac.compare_digest(user, expected_user)
        if hmac.compare_digest(password, expected_token) and user_matches:
            return
        handler.set_status(401)
        handler.set_header("WWW-Authenticate", f'Basic realm="urwid {TITLE}", charset="UTF-8"')
        handler.finish()

    class PageHandler(tornado.web.RequestHandler):  # pylint: disable=abstract-method  # no streamed request body
        """Serve the page and the files it loads."""

        def set_default_headers(self) -> None:
            """Set the security headers."""
            set_headers(self)

        def prepare(self) -> None:
            """Refuse a request for another host or without the login."""
            refuse(self)

        def get(self, name: str) -> None:
            """Send the page or one of its files."""
            content_type, body = files[name]
            self.set_header("Content-Type", content_type)
            self.finish(body)

    class Transport:
        """Send screen updates through one WebSocket."""

        __slots__ = ("__weakref__", "handler")

        def __init__(self, handler: tornado.websocket.WebSocketHandler) -> None:
            """Send through *handler*."""
            self.handler = handler

        def send(self, text: str) -> None:
            """Hand *text* to Tornado; a closed connection is reported to the handler's ``on_close``."""
            with contextlib.suppress(tornado.websocket.WebSocketClosedError):
                written = self.handler.write_message(text)
                # read the result, so a write that failed on a closed connection is not reported as unhandled
                written.add_done_callback(lambda done: done.cancelled() or done.exception())

        def close(self) -> None:
            """Close the WebSocket."""
            self.handler.close()

    class SessionHandler(tornado.websocket.WebSocketHandler):  # pylint: disable=abstract-method  # no streamed body
        """One browser page: a screen and a main loop for as long as the WebSocket is open."""

        def __init__(
            self,
            application: tornado.web.Application,
            request: tornado.httputil.HTTPServerRequest,
        ) -> None:
            """Handle one WebSocket."""
            self.screen: websocket_display.Screen | None = None
            self.main_loop: urwid.MainLoop | None = None
            super().__init__(application, request)

        def set_default_headers(self) -> None:
            """Set the security headers."""
            set_headers(self)

        def prepare(self) -> None:
            """Refuse a handshake for another host or without the login."""
            refuse(self)

        def check_origin(self, origin: str) -> bool:
            """Accept only the test's own page."""
            return origin in origins

        def open(self, *path_args: str, **path_kwargs: str) -> None:
            """Start a test session for this page."""
            self.screen = websocket_display.Screen(Transport(self))
            # every page shares the IOLoop, so an error ends this page's session only
            event_loop = urwid.GuardedEventLoop(urwid.TornadoEventLoop(), self._on_application_error)
            self.main_loop = build_loop(self.screen, event_loop)
            self.main_loop.start()

        def on_message(self, message: str | bytes) -> None:
            """Pass a message to the screen, and close the session when it is invalid."""
            if self.screen is None:
                return
            try:
                self.screen.feed(message)
            except websocket_display.InvalidMessageError as exc:
                LOG.error("Closing a session after an invalid message: %s", exc)  # noqa: TRY400  # no traceback needed
                self.close(1008, "invalid message")

        def on_close(self) -> None:
            """Stop the session's main loop."""
            if self.main_loop is not None:
                self.main_loop.stop()
                self.main_loop = None

        def _on_application_error(self, exc: Exception) -> None:
            """End this session after the test ends, or after an error in it."""
            if not isinstance(exc, urwid.ExitMainLoop):
                LOG.error("Closing a session after an error in the test", exc_info=exc)
            if self.screen is not None and not self.screen.closed:
                self.screen.close()

    file_pattern = "|".join(re.escape(name) for name in files)
    return tornado.web.Application(
        [(f"/({file_pattern})", PageHandler), (f"/{re.escape(WEBSOCKET_PATH)}", SessionHandler)],
        websocket_max_message_size=websocket_display.MAX_MESSAGE_LENGTH * 4,  # UTF-8 takes at most 4 bytes
    )


async def serve_websocket(token: str, token_file: pathlib.Path) -> None:
    """Serve the test to browsers on this host until ``SIGTERM`` or ``SIGHUP``, or until cancelled by Ctrl+C.

    The addresses and the login are printed once the server listens.
    On the way out, the server stops listening and closes every session.

    :param token: the password every request has to carry.
    :param token_file: the file that also holds it, named in the printed login.
    :raises OSError: the port is in use.
    """
    server = make_websocket_app(token).listen(WEBSOCKET_PORT, WEBSOCKET_ADDRESS)
    try:
        stop = asyncio.Event()
        # they would end the process without removing the token; Windows has no SIGHUP and no asyncio signal handlers
        for name in ("SIGTERM", "SIGHUP"):
            if (signal_number := getattr(signal, name, None)) is not None:
                with contextlib.suppress(NotImplementedError):
                    asyncio.get_running_loop().add_signal_handler(signal_number, stop.set)
        print(
            *(f"Open http://{host}/" for host in WEBSOCKET_HOSTS),
            f"User name: {WEBSOCKET_USER}",
            f"Password: {token}",
            f"The password is also in {token_file}, which is removed on exit.",
            sep="\n",
            flush=True,
        )
        await stop.wait()
    finally:
        server.stop()
        # closing the connections closes their sessions, whose handlers stop the sessions' main loops
        await server.close_all_connections()


def run_websocket() -> None:
    """Serve the test to browsers on this host until Ctrl+C, ``SIGTERM`` or ``SIGHUP``, with a login made for the run.

    :raises OSError: the port is in use, or the token file cannot be written.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    with tempfile.TemporaryDirectory(prefix="urwid-input-test-") as directory:
        token_file = pathlib.Path(directory, "token")
        with os.fdopen(os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(f"{token}\n")
        # Ctrl+C cancels the server and ends the run
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve_websocket(token, token_file))


def enable_debug_log() -> None:
    """Write debug messages and warnings to ``debug.log`` in the current directory."""
    logging.basicConfig(
        level=logging.DEBUG,
        filename="debug.log",
        format=(
            "%(levelname)1.1s %(asctime)s | %(threadName)s | %(name)s \n"
            "\t%(message)s\n"
            "-------------------------------------------------------------------------------"
        ),
        datefmt="%d-%b-%Y %H:%M:%S",
        force=True,
    )
    logging.captureWarnings(True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the test and return the process exit status."""
    if urwid.display.web.is_web_request():
        run_as_cgi()
        return 0

    args = parse_args(argv)
    if args.debug_log:
        enable_debug_log()
    if args.display == "websocket":
        try:
            run_websocket()
        except OSError as exc:
            print(f"Cannot serve the test: {exc}", file=sys.stderr)
            return 1
        return 0

    event_loop_class = event_loops()[args.event_loop]
    run_in_terminal(
        args.display,
        None if event_loop_class is None else event_loop_class(),
        extended_keys=args.extended_keys,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
