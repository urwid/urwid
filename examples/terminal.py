#!/usr/bin/env python3
#
# Urwid terminal emulation widget example app
#    Copyright (C) 2010  aszlig
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
#     "urwid>=5.2.0",
# ]
# ///
"""Run the current user's shell in a Terminal widget, inside an Urwid application.

The shell is ``$SHELL``, or :file:`/bin/sh` without it, started on a new pseudo-terminal as the user running the
script.
The window shows the terminal, its size, and an edit field to move the focus to.
The title the shell sets is shown on the frame, and on the terminal window with the ``raw`` display.
:kbd:`Q` outside the terminal, or the end of the shell, ends the application.

The terminal type the shell's programs see is chosen with ``--term``: ``linux``, the default, or ``xterm-256color``.
It is the ``TERM`` the shell gets, and it decides which keys the terminal sends and how it reads what the programs
write, such as the palette sequences and the cursor colour, so a program's output can look different in each.

The display is chosen with ``--display``:

- ``raw``, the default, and ``curses`` run in the terminal.
  The ``raw`` display passes pasted text on to the shell's programs that ask for it,
  and the focus changes of the terminal window while the terminal widget has the focus.
- ``websocket`` serves the application to a browser on this host, with a shell of its own for each page.
  It is offered when Tornado is installed; the other displays run without it.
  Each page is a shell on this host, so it is a local demonstration, not a server:

  - It listens on ``127.0.0.1`` only, without TLS, and answers only requests for that address.
  - It accepts a WebSocket only from its own page.
  - Every request needs HTTP Basic authentication with a token made for the run.
    The token is kept in a temporary directory, readable by its owner only and removed on exit.
  - It prints the address to open and the login to standard output.
  - Closing a page ends its shell, and Ctrl+C stops the server and ends every shell.

The script writes the token file of the ``websocket`` display, and nothing else itself.
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

LOG: typing.Final = logging.getLogger("terminal")

TITLE: typing.Final = "Terminal"
# the label of the edit field the focus can move to
EDIT_CAPTION: typing.Final = "focus test edit: "

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
# the terminal types the Terminal widget emulates
TermType: typing.TypeAlias = typing.Literal["linux", "xterm-256color"]
TERM_TYPES: typing.Final = typing.get_args(TermType)


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
        help="display to use (default: %(default)s); websocket serves a shell to a browser on this host",
    )
    parser.add_argument(
        "--term",
        choices=TERM_TYPES,
        default="linux",
        help="terminal type the shell's programs see, which decides how their output is read (default: %(default)s)",
    )
    return parser.parse_args(argv)


def build_loop(
    screen: urwid.display.BaseScreen,
    *,
    term_type: TermType,
    event_loop: urwid.EventLoop | None = None,
) -> tuple[urwid.MainLoop, urwid.Terminal]:
    """Return the main loop of the application and the terminal running the shell in it.

    :param screen: the display the main loop draws on.
    :param term_type: the terminal type the shell's programs see.
    :param event_loop: the event loop the main loop runs on, the main loop's own when not given.
    """
    # in a browser, the terminal the script runs in is the server's, where Ctrl+C has to keep stopping it
    term = urwid.Terminal(
        None,
        encoding="utf-8",
        pass_signal_keys=not isinstance(screen, websocket_display.Screen),
        term=term_type,
    )
    size_text = urwid.Text("")
    frame = urwid.LineBox(
        urwid.Pile(
            [
                (urwid.WEIGHT, 70, term),
                (1, urwid.Filler(size_text)),
                (1, urwid.Filler(urwid.Edit(EDIT_CAPTION))),
            ]
        ),
        title=TITLE,
    )

    def show_title(_widget: urwid.Terminal, title: str) -> None:
        """Show the title the shell set on the frame, and on the terminal window where the display has one."""
        frame.set_title(title)
        if isinstance(screen, urwid.display.raw.Screen):
            # the program in the terminal chooses the title, and set_title() removes the control characters from it
            screen.set_title(title)

    def show_size(_widget: urwid.Terminal, size: tuple[int, int]) -> None:
        """Show the size of the terminal."""
        size_text.set_text(f"Terminal size: [{size[0]}, {size[1]}]")

    def end(*_args: typing.Any) -> typing.NoReturn:
        """End the application."""
        raise urwid.ExitMainLoop

    def handle_key(key: str | tuple[str, int, int, int]) -> None:
        """End the application on :kbd:`Q` that no widget took."""
        if key in {"q", "Q"}:
            end()

    urwid.connect_signal(term, "title", show_title)
    urwid.connect_signal(term, "resize", show_size)
    urwid.connect_signal(term, "closed", end)
    return urwid.MainLoop(frame, screen=screen, unhandled_input=handle_key, event_loop=event_loop), term


def run_in_terminal(display: str, term_type: TermType) -> None:
    """Run the application in the terminal on the ``raw`` or ``curses`` *display*, with a terminal of *term_type*."""
    if display == "curses":
        from urwid.display import curses  # needs the curses extension module, which is optional

        screen: urwid.display.raw.Screen | curses.Screen = curses.Screen()
    else:
        screen = urwid.display.raw.Screen(bracketed_paste_mode=True, focus_reporting=True)
    loop, term = build_loop(screen, term_type=term_type)
    try:
        loop.run()
    finally:
        term.terminate()


def make_websocket_app(token: str, term_type: TermType) -> tornado.web.Application:
    """Return the application that serves the page, its files and one shell per WebSocket.

    :param token: the password every request has to carry, with the user name ``WEBSOCKET_USER``.
    :param term_type: the terminal type each page's shell sees.
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

    # the sessions open now, ended by serve_websocket() when the server stops
    sessions: set[tornado.websocket.WebSocketHandler] = set()

    def report_failure(ended: asyncio.Future[None]) -> None:
        """Log a failure to end a session's shell."""
        if not ended.cancelled() and (exc := ended.exception()) is not None:
            LOG.error("Ending a session's shell failed", exc_info=exc)

    class SessionHandler(tornado.websocket.WebSocketHandler):  # pylint: disable=abstract-method  # no streamed body
        """One browser page: a screen, a main loop and a shell, for as long as the WebSocket is open."""

        def __init__(
            self,
            application: tornado.web.Application,
            request: tornado.httputil.HTTPServerRequest,
        ) -> None:
            """Handle one WebSocket."""
            self.screen: websocket_display.Screen | None = None
            self.main_loop: urwid.MainLoop | None = None
            self.term: urwid.Terminal | None = None
            super().__init__(application, request)

        def set_default_headers(self) -> None:
            """Set the security headers."""
            set_headers(self)

        def prepare(self) -> None:
            """Refuse a handshake for another host or without the login."""
            refuse(self)

        def check_origin(self, origin: str) -> bool:
            """Accept only the application's own page."""
            return origin in origins

        def open(self, *path_args: str, **path_kwargs: str) -> None:
            """Start a session with a shell of its own for this page."""
            self.screen = websocket_display.Screen(Transport(self))
            # every page shares the IOLoop, so an error ends this page's session only
            event_loop = urwid.GuardedEventLoop(urwid.TornadoEventLoop(), self._on_application_error)
            self.main_loop, self.term = build_loop(self.screen, term_type=term_type, event_loop=event_loop)
            self.main_loop.start()
            sessions.add(self)

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
            """Stop the session's main loop and end its shell, also when called again.

            The shell is ended on a worker thread, since waiting for it to exit would stall every other page,
            and asyncio.run() waits for that thread before the process exits.
            """
            sessions.discard(self)
            if self.main_loop is not None:
                self.main_loop.stop()
                self.main_loop = None
            if self.term is not None:
                term, self.term = self.term, None
                # the pty is watched on the shared loop, so only its own thread stops watching it
                term.remove_watch()
                asyncio.get_running_loop().run_in_executor(None, term.terminate).add_done_callback(report_failure)

        def _on_application_error(self, exc: Exception) -> None:
            """End this session after the application ends, or after an error in it."""
            if not isinstance(exc, urwid.ExitMainLoop):
                LOG.error("Closing a session after an error in the application", exc_info=exc)
            if self.screen is not None and not self.screen.closed:
                self.screen.close()

    file_pattern = "|".join(re.escape(name) for name in files)
    return tornado.web.Application(
        [(f"/({file_pattern})", PageHandler), (f"/{re.escape(WEBSOCKET_PATH)}", SessionHandler)],
        websocket_max_message_size=websocket_display.MAX_MESSAGE_LENGTH * 4,  # UTF-8 takes at most 4 bytes
        sessions=sessions,
    )


async def serve_websocket(
    token: str,
    token_file: pathlib.Path,
    term_type: TermType,
) -> None:
    """Serve the application to browsers on this host until ``SIGTERM`` or ``SIGHUP``, or until cancelled by Ctrl+C.

    The addresses and the login are printed once the server listens.
    On the way out, the server stops listening and closes every session, which ends its shell.

    :param token: the password every request has to carry.
    :param token_file: the file that also holds it, named in the printed login.
    :param term_type: the terminal type each page's shell sees.
    :raises OSError: the port is in use.
    """
    app = make_websocket_app(token, term_type)
    server = app.listen(WEBSOCKET_PORT, WEBSOCKET_ADDRESS)
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
        # close_all_connections() leaves a WebSocket open, and Tornado runs on_close() only once the page answers the
        # close, after the server has stopped: each session is closed and ended here
        for session in tuple(app.settings["sessions"]):
            session.close(1001, "server stopping")
            session.on_close()
        await server.close_all_connections()


def run_websocket(term_type: TermType) -> None:
    """Serve the application to browsers on this host until Ctrl+C, ``SIGTERM`` or ``SIGHUP``.

    Every request needs a login made for the run.

    :param term_type: the terminal type each page's shell sees.
    :raises OSError: the port is in use, or the token file cannot be written.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    with tempfile.TemporaryDirectory(prefix="urwid-terminal-") as directory:
        token_file = pathlib.Path(directory, "token")
        with os.fdopen(os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(f"{token}\n")
        # Ctrl+C cancels the server and ends the run
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve_websocket(token, token_file, term_type))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application and return the process exit status."""
    args = parse_args(argv)
    if args.display == "websocket":
        try:
            run_websocket(args.term)
        except OSError as exc:
            print(f"Cannot serve the application: {exc}", file=sys.stderr)
            return 1
        return 0
    run_in_terminal(args.display, args.term)
    return 0


if __name__ == "__main__":
    sys.exit(main())
