"""Display that draws into a browser page over a WebSocket, whatever server library carries the connection.

The screen knows nothing about HTTP or WebSocket libraries.
An adapter written for the server library connects it to one WebSocket connection:

- It serves the page from :func:`html_page` and the files in :data:`STATIC_FILES`.
- It creates one :class:`Screen` and one :class:`~urwid.MainLoop` per connection,
  on the event loop the server library runs on, and calls :meth:`~urwid.MainLoop.start`.
  It wraps that event loop in a :class:`~urwid.GuardedEventLoop` per connection,
  so an exception in one session closes that session instead of stopping the event loop.
- It passes every message from the browser to :meth:`Screen.feed`,
  and closes the connection when that raises :exc:`InvalidMessageError`.
- It calls :meth:`~urwid.MainLoop.stop` when the connection closes.

The screen sends through a :class:`Transport`, which the adapter implements over its connection.
Several sessions run on one event loop, each with its own screen and main loop.

The ``examples/websocket_tornado.py`` script is such an adapter for Tornado.
"""

from __future__ import annotations

import dataclasses
import html
import json
import pathlib
import string
import types
import typing
import unicodedata

from urwid.event_loop.abstract_loop import ExitMainLoop

from ._web_common import MAX_COLS, MAX_ROWS, BrowserScreen

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from urwid.canvas import Canvas
    from urwid.event_loop import EventLoop

__all__ = (
    "MAX_MESSAGE_LENGTH",
    "MAX_PENDING_INPUT",
    "STATIC_FILES",
    "InvalidMessageError",
    "Screen",
    "StaticFile",
    "Transport",
    "html_page",
)

#: the longest message from the browser, in characters; a valid message is far shorter
MAX_MESSAGE_LENGTH: typing.Final = 256
#: the most keys received and not yet handed to the main loop
MAX_PENDING_INPUT: typing.Final = 64

_ASSET_DIR: typing.Final = pathlib.Path(__file__).parent

# the names urwid uses for the keys the page script sends by name, without modifiers
_KEY_NAMES: typing.Final = frozenset(
    {
        "backspace",
        "tab",
        "enter",
        "esc",
        "page up",
        "page down",
        "end",
        "home",
        "left",
        "up",
        "right",
        "down",
        "insert",
        "delete",
        *(f"f{number}" for number in range(1, 13)),
    }
)
# the modifier prefixes of a key name, in the order the page script writes them
_MODIFIERS: typing.Final = ("shift ", "meta ", "ctrl ")


class InvalidMessageError(ValueError):
    """A message from the browser does not follow the protocol of the page script."""


class Transport(typing.Protocol):
    """The connection to one browser page, implemented by the adapter for its server library."""

    def send(self, text: str) -> None:
        """Send *text* to the page as one text message, without blocking.

        It may drop the text when the connection is already closing.
        """

    def close(self) -> None:
        """Close the connection.

        It does nothing when the connection is already closed or closing.
        """


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class StaticFile:
    """A file the page loads from the directory it was served from."""

    content_type: str
    source: str  # the file name in the urwid.display package

    def read(self) -> bytes:
        """Return the content of the file."""
        return (_ASSET_DIR / self.source).read_bytes()


#: the files the page loads, by the name the page uses relative to its own URL
STATIC_FILES: typing.Final[Mapping[str, StaticFile]] = types.MappingProxyType(
    {
        "web.css": StaticFile("text/css; charset=utf-8", "_web.css"),
        "websocket.css": StaticFile("text/css; charset=utf-8", "_websocket.css"),
        "web_common.js": StaticFile("text/javascript; charset=utf-8", "_web_common.js"),
        "websocket.js": StaticFile("text/javascript; charset=utf-8", "_websocket.js"),
    }
)


def html_page(title: str, websocket_path: str) -> str:
    """Return the HTML page that connects to a :class:`Screen`.

    The page has no inline script or style,
    so it works under a ``Content-Security-Policy`` that allows scripts and styles from ``'self'`` only.
    It loads the :data:`STATIC_FILES` by names relative to its own URL.

    >>> page = html_page("Demo & test", "ws")
    >>> "<title>Demo &amp; test</title>" in page
    True
    >>> 'data-websocket-path="ws"' in page
    True

    :param title: the application name shown in the title and above the screen; it is escaped.
    :param websocket_path: the URL of the WebSocket, relative to the page's URL; it is escaped.
    """
    return string.Template((_ASSET_DIR / "_websocket.html").read_text("utf-8")).substitute(
        title=html.escape(title),
        websocket_path=html.escape(websocket_path),
    )


def _reject_constant(name: str) -> typing.NoReturn:
    """Reject the ``NaN`` and ``Infinity`` constants that :func:`json.loads` accepts by default.

    :raises ValueError: always.
    """
    raise ValueError(name)


class Screen(BrowserScreen):
    """Screen that draws into one browser page through a :class:`Transport`.

    It takes input only from :meth:`feed`, so it needs no file descriptor, and it runs on any event loop.
    Input reaches the main loop through an alarm of the event loop, which is what makes the main loop redraw.

    :exc:`~urwid.ExitMainLoop` raised by an input handler ends this session only: the screen closes its transport.
    Any other exception from an input handler or a redraw, and :exc:`~urwid.ExitMainLoop` from an alarm,
    stops the event loop,
    and with it every session it runs, unless the main loop runs on a :class:`~urwid.GuardedEventLoop`
    whose handler calls :meth:`close`.

    Call every method from the thread that runs the event loop.

    .. important::
        Do not use :meth:`~urwid.MainLoop.paused` with this screen: there is no terminal to hand over.
    """

    def __init__(self, transport: Transport, *, cols: int = 80, rows: int = 24) -> None:
        """Initialize an unstarted screen that sends through *transport*.

        :param transport: the connection to the page.
        :param cols: the width until the page reports its own; at most ``MAX_COLS`` is used.
        :param rows: the height until the page reports its own; at most ``MAX_ROWS`` is used.
        :raises ValueError: *cols* or *rows* is less than 1.
        """
        super().__init__()
        if cols < 1 or rows < 1:
            raise ValueError(f"screen size must be positive: {cols}x{rows}")
        self._transport = transport
        self._size = (min(cols, MAX_COLS), min(rows, MAX_ROWS))
        self._event_loop: EventLoop | None = None
        self._callback: Callable[[list[str], list[int]], typing.Any] | None = None
        # input checked by feed() and not yet handed to the main loop
        self._pending: list[str] = []
        # the alarm that hands the pending input to the main loop, while one is scheduled
        self._delivery: typing.Any = None
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return whether :meth:`close` has ended the session."""
        return self._closed

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the size the page reported last, or the size given to the constructor."""
        return self._size

    def _start(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        """Send every row on the next draw, since the page may show rows the screen no longer knows."""
        self.clear()

    def clear(self) -> None:
        """Force the screen to be completely repainted on the next call to draw_screen()."""
        self.last_screen = {}
        self.last_screen_width = 0

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Send the rows of *canvas* that the page does not show yet.

        Nothing is sent once the session is closed.

        :raises ValueError: *canvas* does not have the number of rows given by *size*.
        """
        if self._closed:
            return
        self._transport.send("".join(self._render_rows(size, canvas)))

    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[list[str], list[int]], typing.Any],
    ) -> None:
        """Hand the input from :meth:`feed` to *callback* through alarms of *event_loop*.

        :param event_loop: the event loop the main loop runs on.
        :param callback: called with the key names and an empty list of raw key codes.
        """
        if self._event_loop is not None and self._delivery is not None:
            self._event_loop.remove_alarm(self._delivery)
        self._delivery = None
        self._event_loop = event_loop
        self._callback = callback
        if self._pending:
            self._delivery = event_loop.alarm(0, self._deliver)

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """Stop handing input to the callback given to :meth:`hook_event_loop`.

        Input that has not been handed over yet waits for the next :meth:`hook_event_loop`.
        """
        if self._delivery is not None:
            event_loop.remove_alarm(self._delivery)
            self._delivery = None
        self._event_loop = None
        self._callback = None

    def feed(self, message: str | bytes) -> None:
        """Check one message from the page and queue the input it carries.

        A message is a JSON object of one of these forms, with no other keys:

        - ``{"type": "key", "key": <name>}``, where the name is an urwid key name the page script can send:
          a named key such as ``"page up"`` or ``"f5"``, or one character that is not a control character,
          after the modifiers ``"shift "``, ``"meta "`` and ``"ctrl "`` in that order.
        - ``{"type": "resize", "cols": <int>, "rows": <int>}`` with both sizes at least 1.
          A size above ``MAX_COLS`` or ``MAX_ROWS`` is reduced to that limit.

        Messages that arrive after :meth:`close` are ignored.

        :param message: the content of one WebSocket message.
        :raises InvalidMessageError: the message is binary, longer than ``MAX_MESSAGE_LENGTH``,
            not of one of the forms above, or more than ``MAX_PENDING_INPUT`` keys wait for the main loop.
        """
        if self._closed:
            return
        if not isinstance(message, str):
            raise InvalidMessageError("binary message")
        if len(message) > MAX_MESSAGE_LENGTH:
            raise InvalidMessageError(f"message longer than {MAX_MESSAGE_LENGTH} characters")
        try:
            data = json.loads(message, parse_constant=_reject_constant)
        except ValueError as exc:
            raise InvalidMessageError("message is not JSON") from exc

        match data:
            case {"type": "key", "key": str() as key} if len(data) == 2:
                name = key
                for modifier in _MODIFIERS:
                    name = name.removeprefix(modifier)
                # the page sends any single character; Cc and Cs do not change between Unicode versions
                if name not in _KEY_NAMES and not (len(name) == 1 and unicodedata.category(name) not in {"Cc", "Cs"}):
                    raise InvalidMessageError("unknown key name")
                self._queue(key)
            case {"type": "resize", "cols": int() as cols, "rows": int() as rows} if len(data) == 3:
                # bool is a subclass of int, and JSON true is no size
                if isinstance(cols, bool) or isinstance(rows, bool) or cols < 1 or rows < 1:
                    raise InvalidMessageError("screen size must be positive integers")
                self._size = (min(cols, MAX_COLS), min(rows, MAX_ROWS))
                self._queue("window resize")
            case _:
                raise InvalidMessageError("unknown message")

    def close(self) -> None:
        """End the session: drop the queued input, ignore further messages and close the transport."""
        if self._closed:
            return
        self._closed = True
        self._pending = []
        self._transport.close()

    def _queue(self, key: str) -> None:
        """Queue *key* for the main loop.

        :raises InvalidMessageError: ``MAX_PENDING_INPUT`` keys already wait for the main loop.
        """
        if len(self._pending) >= MAX_PENDING_INPUT:
            raise InvalidMessageError(f"more than {MAX_PENDING_INPUT} keys wait for the main loop")
        self._pending.append(key)
        if self._event_loop is not None and self._delivery is None:
            self._delivery = self._event_loop.alarm(0, self._deliver)

    def _deliver(self) -> None:
        """Hand the queued input to the main loop, and close the session when a handler raises ExitMainLoop."""
        self._delivery = None
        keys = self._pending
        self._pending = []
        if self._callback is None or not keys:
            return
        try:
            self._callback(keys, [])
        except ExitMainLoop:
            self.logger.debug("ExitMainLoop raised by an input handler: closing the session")
            self.close()
