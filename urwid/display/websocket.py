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
import itertools
import json
import pathlib
import string
import types
import typing
import unicodedata

from urwid.event_loop.abstract_loop import ExitMainLoop

from ._web_common import BrowserScreen

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from urwid.canvas import Canvas
    from urwid.event_loop import EventLoop

__all__ = (
    "MAX_COLS",
    "MAX_MESSAGE_LENGTH",
    "MAX_PENDING_INPUT",
    "MAX_ROWS",
    "STATIC_FILES",
    "InvalidMessageError",
    "Screen",
    "StaticFile",
    "Transport",
    "html_page",
)

#: the default largest width, in columns: the largest an X10 mouse report can address in a terminal
MAX_COLS: typing.Final = 223
#: the default largest height, in rows, for the same reason
MAX_ROWS: typing.Final = 223
#: the longest message from the browser, in characters; a valid message is far shorter
MAX_MESSAGE_LENGTH: typing.Final = 256
#: the most keys and mouse events received and not yet handed to the main loop
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
# the modifier prefixes of a key name or a mouse event, in the order the page script writes them
_MODIFIERS: typing.Final = ("shift ", "meta ", "ctrl ")
# the mouse events the page script sends, without modifiers
_MOUSE_EVENTS: typing.Final = frozenset({"mouse press", "mouse release", "mouse drag"})
# the button numbers the page script sends: left, middle, right, the four wheel directions and the two side buttons
_MOUSE_BUTTONS: typing.Final = range(1, 10)
# the wheel directions, which a browser reports many times a second while the wheel turns
_WHEEL_BUTTONS: typing.Final = range(4, 8)


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


def html_page(
    title: str,
    websocket_path: str,
    *,
    max_cols: int = MAX_COLS,
    max_rows: int = MAX_ROWS,
) -> str:
    """Return the HTML page that connects to a :class:`Screen`.

    The page has no inline script or style,
    so it works under a ``Content-Security-Policy`` that allows scripts and styles from ``'self'`` only.
    It loads the :data:`STATIC_FILES` by names relative to its own URL.
    It carries the largest screen size, so the page fits its screen area to the size the screen uses
    and does not report the mouse beyond it.

    >>> page = html_page("Demo & test", "ws")
    >>> "<title>Demo &amp; test</title>" in page
    True
    >>> 'data-websocket-path="ws"' in page
    True

    :param title: the application name shown in the title and above the screen; it is escaped.
    :param websocket_path: the URL of the WebSocket, relative to the page's URL; it is escaped.
    :param max_cols: the largest width; the same value as the screen's *max_cols*.
    :param max_rows: the largest height; the same value as the screen's *max_rows*.
    :raises ValueError: *max_cols* or *max_rows* is less than 1.
    """
    if max_cols < 1 or max_rows < 1:
        raise ValueError(f"largest screen size must be positive: {max_cols}x{max_rows}")
    return string.Template((_ASSET_DIR / "_websocket.html").read_text("utf-8")).substitute(
        title=html.escape(title),
        websocket_path=html.escape(websocket_path),
        max_cols=max_cols,
        max_rows=max_rows,
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

    def __init__(
        self,
        transport: Transport,
        *,
        cols: int = 80,
        rows: int = 24,
        max_cols: int = MAX_COLS,
        max_rows: int = MAX_ROWS,
    ) -> None:
        """Initialize an unstarted screen that sends through *transport*.

        :param transport: the connection to the page.
        :param cols: the width until the page reports its own; at most *max_cols* is used.
        :param rows: the height until the page reports its own; at most *max_rows* is used.
        :param max_cols: the largest width the page may report; pass the same value to :func:`html_page`.
        :param max_rows: the largest height the page may report; pass the same value to :func:`html_page`.
        :raises ValueError: *cols*, *rows*, *max_cols* or *max_rows* is less than 1.
        """
        super().__init__()
        if cols < 1 or rows < 1 or max_cols < 1 or max_rows < 1:
            raise ValueError(f"screen sizes must be positive: {cols}x{rows}, at most {max_cols}x{max_rows}")
        self._transport = transport
        self._max_size = (max_cols, max_rows)
        self._size = (min(cols, max_cols), min(rows, max_rows))
        self._event_loop: EventLoop | None = None
        self._callback: Callable[[list[str | tuple[str, int, int, int]], list[int]], typing.Any] | None = None
        # input checked by feed() and not yet handed to the main loop: key names and mouse events
        self._pending: list[str | tuple[str, int, int, int]] = []
        # the size each queued "window resize" brings, in order
        self._resize_sizes: list[tuple[int, int]] = []
        # the size after the last "window resize" handed to the main loop
        self._delivered_size = self._size
        # while a batch is handed to the main loop: the size its input arrived at
        self._batch_size: tuple[int, int] | None = None
        # set by the main loop through set_mouse_tracking(); mouse messages are dropped while it is not
        self._mouse_tracking = False
        # the alarm that hands the pending input to the main loop, while one is scheduled
        self._delivery: typing.Any = None
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return whether :meth:`close` has ended the session."""
        return self._closed

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the size the page reported last, or the size given to the constructor.

        While queued input is handed to the main loop, it is the size that input arrived at instead,
        so the main loop lays out input that arrived before a later resize at the size the page had then.
        """
        if self._batch_size is not None:
            return self._batch_size
        return self._size

    def _start(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        """Send every row on the next draw, since the page may show rows the screen no longer knows."""
        self.clear()

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """Pass the mouse events the page sends to the main loop, or drop them.

        The page sends them in either case, so it takes the mouse buttons for the application all the time.
        """
        self._mouse_tracking = enable

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
        callback: Callable[[list[str | tuple[str, int, int, int]], list[int]], typing.Any],
    ) -> None:
        """Hand the input from :meth:`feed` to *callback* through alarms of *event_loop*.

        :param event_loop: the event loop the main loop runs on.
        :param callback: called with the key names and mouse events, and an empty list of raw key codes.
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
          A size above the screen's *max_cols* or *max_rows* is reduced to that limit.
        - ``{"type": "mouse", "event": <name>, "button": <int>, "col": <int>, "row": <int>}``,
          where the name is ``"mouse press"``, ``"mouse release"`` or ``"mouse drag"``
          after the same modifiers as a key name,
          the button is 1 to 9 as :class:`~urwid.MouseButton` numbers them,
          and the column and row are at least 0.
          A position outside the screen is moved to its nearest edge.
          It reaches the main loop as an ``(event, button, col, row)`` tuple,
          and is dropped while mouse tracking is off.
          A drag replaces a drag of the same button that still waits for the main loop,
          and a wheel press is dropped while ``MAX_PENDING_INPUT`` inputs wait,
          so a fast drag or wheel does not end the session.

        Messages that arrive after :meth:`close` are ignored.

        :param message: the content of one WebSocket message.
        :raises InvalidMessageError: the message is binary, longer than ``MAX_MESSAGE_LENGTH``,
            not of one of the forms above, or more than ``MAX_PENDING_INPUT`` inputs wait for the main loop.
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
                self._queue("window resize")
                max_cols, max_rows = self._max_size
                self._size = (min(cols, max_cols), min(rows, max_rows))
                self._resize_sizes.append(self._size)
            case {
                "type": "mouse",
                "event": str() as event,
                "button": int() as button,
                "col": int() as col,
                "row": int() as row,
            } if len(data) == 5:
                name = event
                for modifier in _MODIFIERS:
                    name = name.removeprefix(modifier)
                if name not in _MOUSE_EVENTS:
                    raise InvalidMessageError("unknown mouse event")
                # bool is a subclass of int, and JSON true is no number
                if any(isinstance(value, bool) for value in (button, col, row)) or button not in _MOUSE_BUTTONS:
                    raise InvalidMessageError("mouse button must be an integer from 1 to 9")
                if col < 0 or row < 0:
                    raise InvalidMessageError("mouse position must be non-negative integers")
                if not self._mouse_tracking:
                    return
                cols, rows = self._size
                mouse = (event, button, min(col, cols - 1), min(row, rows - 1))
                # a queued key name never starts with the (event, button) pair
                if name == "mouse drag" and self._pending and self._pending[-1][:2] == (event, button):
                    self._pending[-1] = mouse
                elif not (button in _WHEEL_BUTTONS and len(self._pending) >= MAX_PENDING_INPUT):
                    self._queue(mouse)
            case _:
                raise InvalidMessageError("unknown message")

    def close(self) -> None:
        """End the session: drop the queued input, ignore further messages and close the transport."""
        if self._closed:
            return
        self._closed = True
        self._pending = []
        self._resize_sizes = []
        self._transport.close()

    def _queue(self, key: str | tuple[str, int, int, int]) -> None:
        """Queue *key*, a key name or a mouse event, for the main loop.

        :raises InvalidMessageError: ``MAX_PENDING_INPUT`` inputs already wait for the main loop.
        """
        if len(self._pending) >= MAX_PENDING_INPUT:
            raise InvalidMessageError(f"more than {MAX_PENDING_INPUT} inputs wait for the main loop")
        self._pending.append(key)
        if self._event_loop is not None and self._delivery is None:
            self._delivery = self._event_loop.alarm(0, self._deliver)

    def _deliver(self) -> None:
        """Hand the queued input to the main loop, and close the session when a handler raises ExitMainLoop.

        The input is handed over in batches that end at each ``"window resize"``,
        since the main loop lays out a whole batch at one screen size,
        and :meth:`get_cols_rows` returns the size each batch arrived at while it is handed over.
        When a handler unhooks or hooks the screen again, the batches not handed over yet wait for the next hook.
        """
        self._delivery = None
        callback = self._callback
        if callback is None or not self._pending:
            return
        keys = self._pending
        sizes = self._resize_sizes
        self._pending = []
        self._resize_sizes = []
        batches: list[list[str | tuple[str, int, int, int]]] = [[]]
        for key in keys:
            batches[-1].append(key)
            if key == "window resize":
                batches.append([])
        try:
            for index, batch in enumerate(batches):
                # a handler of an earlier batch may have closed the session
                if self._closed or not batch:
                    break
                if self._callback is not callback:
                    self._pending[:0] = itertools.chain.from_iterable(batches[index:])
                    self._resize_sizes[:0] = sizes
                    if self._event_loop is not None and self._delivery is None:
                        self._delivery = self._event_loop.alarm(0, self._deliver)
                    break
                self._batch_size = self._delivered_size
                callback(batch, [])
                if batch[-1] == "window resize":
                    self._delivered_size = sizes.pop(0)
        except ExitMainLoop:
            self.logger.debug("ExitMainLoop raised by an input handler: closing the session")
            self.close()
        except BaseException:
            # the batches after the one that raised are lost, so the size moves on to the newest
            self._delivered_size = self._size
            raise
        finally:
            self._batch_size = None
