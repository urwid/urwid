"""TerminalOutput: a box widget that shows terminal output the application writes to it."""

from __future__ import annotations

import re
import typing

from urwid import util
from urwid.canvas import CompositeCanvas, SolidCanvas
from urwid.canvas.term import TermCanvas, TermModes
from urwid.canvas.term import _state as _term_state

from .constants import MouseButton, Sizing
from .widget import Widget

if typing.TYPE_CHECKING:
    from typing import Literal

    from urwid.canvas.term._state import TermType

# Runs of ASCII and of non-ASCII characters, which write() encodes one at a time.
_ASCII_RUNS: typing.Final = re.compile(r"[\x00-\x7f]+|[^\x00-\x7f]+")


class TerminalOutput(Widget):
    r"""Box widget that emulates a terminal for output the application writes to it, with no process behind it.

    It shows what a program would draw in a terminal: colours, cursor movement, clearing, scrollback.
    The data comes from :meth:`write`, for example captured output, a recording, or text built by the application.
    Unlike :class:`Terminal`, it runs no child process, so it also works on Windows.

    Replies the data asks for, such as a cursor position report, are discarded.
    A bell, a keyboard LED change and a window title in the data emit the ``"beep"``, ``"leds"`` and ``"title"``
    signals, as :class:`Terminal` does.

    The emulated terminal takes the size the widget is rendered at, unless a dimension of it is zero.
    The ``"resize"`` signal is emitted with the new ``(columns, rows)`` each time it changes, including at the first
    render when it differs from the size given to the constructor.
    A resize does not lay the text out again:

    - Narrowing cuts every line on the screen at the new width; widening again adds blank cells, not the cut ones.
      Lines in the scrollback keep their cells.
    - Reducing the height of the screen in use first drops its blank rows at the bottom, below the cursor; then it
      moves the top rows into the scrollback, or drops them on the alternate screen, which has none.
      Increasing it takes rows back from the scrollback while there are any, then adds blank rows at the bottom.

    Content laid out for one size is therefore drawn again from the ``"resize"`` signal: clear the screen and move to
    the top-left corner (``"\x1b[2J\x1b[H"``), then write the content for the new size.

    :kbd:`Page Up` and :kbd:`Page Down`, and the mouse wheel, scroll through the lines that scrolled off the top.

    >>> output = TerminalOutput(size=(12, 2))
    >>> output.write("\x1b[1mbold\x1b[0m line\nsecond line")
    >>> [line.rstrip() for line in output.render((12, 2)).text]
    [b'bold line', b'second line']
    """

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    signals: typing.ClassVar[list[str]] = ["beep", "leds", "title", "resize"]

    def __init__(
        self,
        *,
        size: tuple[int, int] = (80, 24),
        lf_to_crlf: bool = True,
        scroll_on_output: bool = True,
        term: TermType = "linux",
    ) -> None:
        """Create the widget with an empty screen.

        :param size: the ``(columns, rows)`` of the screen until the first render, so data can be written before it.
        :param lf_to_crlf: write each line feed as carriage return and line feed, as a pty does for a program's output.
            Leave it on for text and captured output, where a line feed starts a new line.
            Turn it off for a recording of a pty's raw output, where a line feed only moves the cursor down.
        :param scroll_on_output: move a view scrolled back to the bottom when :meth:`write` is given data.
            When off, the view stays on the lines it shows while new lines scroll into the scrollback below them.
        :param term: the terminal type the data is written for: ``"linux"`` follows the Linux console where it differs
            from xterm, and ``"xterm-256color"`` follows xterm, as for :class:`Terminal`.
        :raises ValueError: a dimension of *size* is not positive, or *term* is not one of those terminal types.
        """
        columns, rows = size
        if columns <= 0 or rows <= 0:
            msg = f"size must be positive, got {size!r}"
            raise ValueError(msg)
        if term not in _term_state.TERM_TYPES:
            msg = f"term must be one of {sorted(_term_state.TERM_TYPES)}, not {term!r}"
            raise ValueError(msg)
        super().__init__()
        #: Whether :meth:`write` writes each line feed as carriage return and line feed.
        self.lf_to_crlf = lf_to_crlf
        #: The modes the data set; the screen resets them, so they are this widget's own.
        self.term_modes = TermModes()
        self._term = TermCanvas(columns, rows, self, scroll_on_output=scroll_on_output, term_type=term)
        # the "resize" signal is being emitted, so a render from its handlers does not resize the terminal again
        self._emitting_resize = False

    def write(self, data: bytes | bytearray | memoryview | str) -> None:
        """Feed *data* to the terminal, as a program writes its output.

        Call it on the thread that runs the main loop; data from another thread goes through
        :meth:`MainLoop.call_from_thread`.

        - ``bytes`` and bytes-like objects are what a program writes to a terminal, in the encoding the terminal reads:
          UTF-8 when urwid's encoding is UTF-8 or the data selected UTF-8 (``ESC % G``), urwid's encoding otherwise.
          Data in any other encoding is decoded by the caller and written as ``str``.
          That includes an encoding that switches character sets with escape sequences, such as ISO-2022-JP,
          even when it is urwid's encoding: the parser takes those sequences as its own, as a terminal does.
          A character split between two writes is completed by the second one.
        - ``str`` is text, shown as the characters given in either case.

        :param data: the output to show.
        """
        term = self._term
        if isinstance(data, str):
            for match in _ASCII_RUNS.finditer(data):
                # Escape sequences that switch to and from UTF-8 are ASCII, so the mode cannot change inside a
                # non-ASCII run: each run is encoded for the mode the earlier runs left the terminal in.
                run = match.group()
                if run.isascii():
                    chunk = run.encode("ascii")
                elif term.reads_utf8:
                    chunk = run.encode("utf-8")
                elif term.within_escape:
                    chunk = run.encode(util.get_encoding(), "urwid_fallback_ascii")
                else:
                    # In urwid's encoding a character can include a C1 control byte such as CSI (0x9B), so the run is
                    # decoded as UTF-8 instead, which makes each character a cell, as it does in UTF-8 mode.
                    chunk = b"\x1b%G" + run.encode("utf-8") + b"\x1b%@"
                if self.lf_to_crlf:
                    chunk = chunk.replace(b"\n", b"\r\n")
                term.addstr(chunk)
        else:
            data = bytes(data)
            term.addstr(data.replace(b"\n", b"\r\n") if self.lf_to_crlf else data)
        self._invalidate()

    def render(
        self,
        size: tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> TermCanvas | CompositeCanvas | SolidCanvas:
        """Resize the terminal to *size* when it differs, and return the terminal canvas.

        The cursor is drawn only when the widget has *focus*.
        The palette colors the data redefined are drawn as 24-bit colors, which the screen converts to the colors it
        draws.
        A size with a zero dimension shows nothing and leaves the terminal at its size, so no output is lost.
        A ``"resize"`` handler that renders the widget at another size gets the terminal cut or padded to that size,
        and the terminal keeps the size the signal reports.
        """
        columns, rows = size
        if columns <= 0 or rows <= 0:
            return SolidCanvas(" ", columns, rows)
        term = self._term
        if size != (term.width, term.height):
            if self._emitting_resize:
                canvas = CompositeCanvas(term)
                # not cached: a later render at this size has to resize the terminal
                canvas.cacheable = False
                canvas.pad_trim_left_right(0, columns - term.width)
                canvas.pad_trim_top_bottom(0, rows - term.height)
                return canvas
            term.resize(*size)
            self._emitting_resize = True
            try:
                self._emit("resize", size)
            finally:
                self._emitting_resize = False
        if focus != term.has_focus:
            term.has_focus = focus
            term.set_term_cursor()
        return term

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return where the cursor is drawn at *size* when the widget has focus.

        At a size other than the one last rendered, the cursor is only kept within *size*; the resize at the next
        render can move it to another row.

        :returns: the ``(column, row)`` of the cursor, or ``None`` when it is not drawn:
            the data hid it, or the view is scrolled back so far that its row is not shown.
        """
        columns, rows = size
        term = self._term
        if not term.modes.visible_cursor:
            return None
        x = max(0, min(term.term_cursor[0], columns - 1))
        y = max(0, min(term.term_cursor[1], rows - 1))
        if term.scrolling_up >= rows - y:
            return None
        return x, y + term.scrolling_up

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Scroll back on :kbd:`Page Up` and forward on :kbd:`Page Down`, and return any other key."""
        if key not in {"page up", "page down"}:
            return key
        self._term.scroll_buffer(up=key == "page up")
        self._invalidate()
        return None

    def mouse_event(  # pyrefly: ignore[bad-override]  # a box widget, sized by two dimensions
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        """Scroll back one line on the wheel up, and forward one line on the wheel down.

        :returns: ``True`` for a wheel press, ``False`` for any other event.
        """
        if not util.is_mouse_press(event) or button not in {MouseButton.WHEEL_UP, MouseButton.WHEEL_DOWN}:
            return False
        self._term.scroll_buffer(up=button == MouseButton.WHEEL_UP, lines=1)
        self._invalidate()
        return True

    def respond(self, string: str) -> None:
        """Discard a reply the data asked for, since no program reads it."""

    def beep(self) -> None:
        """Emit the ``"beep"`` signal for a bell in the data."""
        self._emit("beep")

    def leds(self, which: Literal["clear", "scroll_lock", "num_lock", "caps_lock"]) -> None:
        """Emit the ``"leds"`` signal for a keyboard LED change in the data."""
        self._emit("leds", which)

    def set_title(self, title: str) -> None:
        """Emit the ``"title"`` signal for a window title in the data."""
        self._emit("title", title)
