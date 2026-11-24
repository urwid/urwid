# Urwid terminal emulation canvas
#    Copyright (C) 2010  aszlig
#    Copyright (C) 2011  Ian Ward
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

"""Screen buffer of :class:`~urwid.canvas.term.TermCanvas`: its cells, scrollback, cursor, tab stops and drawing."""

from __future__ import annotations

import copy
import typing
from collections import deque
from dataclasses import dataclass, field

from urwid import _deprecation
from urwid.ansi_parser import (
    ParseState,
    attrspec_with_hyperlink,
)
from urwid.canvas import Canvas
from urwid.canvas.term._cells import (
    _BLANK,
    _BLANK_CELL,
    _drawn_width,
    _fit_line,
    _mend_wide,
    _Protected,
    _with_flag,
)
from urwid.canvas.term._palette import (
    _BACKGROUND_KEY,
    _DEFAULT_BACKGROUND_ENTRY,
    _DEFAULT_FOREGROUND_ENTRY,
    _DYNAMIC_BACKGROUND,
    _DYNAMIC_CURSOR,
    _DYNAMIC_FOREGROUND,
    _FOREGROUND_KEY,
    _palette_entry,
    _underline_palette_entry,
    _x11_rgb,
)
from urwid.canvas.term._state import TermCharset, TermModes
from urwid.display import _sgr
from urwid.display._sgr import sgi_params_to_attrspec, split_sgr_parameters
from urwid.display.common import AttrSpec, _depth
from urwid.display.escape import PrivateMode

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
    from typing import Literal

    # Imported by name for type checkers, see urwid._deprecation.
    from typing_extensions import deprecated

    from urwid.canvas.term._state import TermType

    class _TermCanvasOwner(typing.Protocol):
        """Widget a :class:`TermCanvas` belongs to: it holds the modes and takes what the terminal reports."""

        term_modes: TermModes

        def respond(self, string: str) -> None:
            """Answer a query in the data, as a terminal writes the reply to its child's input."""

        def set_title(self, title: str) -> None:
            """Take the window title the data set."""

        def beep(self) -> None:
            """Take a bell in the data."""

        def leds(self, which: Literal["clear", "scroll_lock", "num_lock", "caps_lock"]) -> None:
            """Take a keyboard LED change in the data."""

else:
    from urwid._deprecation import deprecated

#: the cursor styles drawn underlined; the others, a block or a bar, are drawn in reverse video
_UNDERLINE_CURSOR_STYLES: typing.Final = frozenset((3, 4))


#: the conformance levels DECSCL selects: VT100 (61), VT200 (62), VT300 (63) and VT400 (64), the highest and the startup
#: one
_CONFORMANCE_LEVELS: typing.Final = range(61, 65)

#: the conformance level from which DECLRMM sets the left and right margins: VT400, as in xterm
_LEFT_RIGHT_MARGIN_LEVEL: typing.Final = 64


def _colored_cursor(attr: AttrSpec | None, *, underline: bool, color: tuple[int, int, int]) -> AttrSpec:
    """Return the attribute of the cell *attr* under a cursor of the RGB color *color*, as xterm draws it.

    An underline cursor is an underline in *color*.
    A block cursor fills the cell with *color* and draws the text in the color the cell's background is shown in.
    The cell's other colors, kept with their kind, and its other settings, such as bold, are kept.
    """
    cursor = _depth.rgb(*color)
    if underline:
        return _depth.replace_channels(_with_flag(attr, "underline"), underline=cursor)
    if attr is not None and attr.standout:
        # the cell shows its foreground color as the background
        return _depth.replace_channels(_with_flag(attr, "standout", remove=True), background=cursor)
    # standout shows the cell's background color, the default one included, as the text color
    return _depth.replace_channels(_with_flag(attr, "standout"), foreground=cursor)


@dataclass(slots=True, weakref_slot=True)
class _Screen:
    """The state a :class:`TermCanvas` keeps for the screen it does not show, the main or the alternate one."""

    term: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
    scrollback_buffer: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
    saved_cursor: tuple[int, int] | None = None
    saved_attrs: tuple[AttrSpec | None, TermCharset] | None = None
    keyboard_flags: list[int] = field(default_factory=list)
    #: the row the cursor was on when the screen was hidden, moved with the rows a resize keeps
    cursor_row: int = 0
    saved_flags: tuple[bool, bool, bool] | None = None


class _ScreenCanvas(Canvas):
    """Hold the state of a :class:`~urwid.canvas.term.TermCanvas` and edit its screen buffer.

    Every attribute of the canvas, the escape sequence parser's included, is set here.
    The layers above add the control functions, and call only this layer and the ones between.
    """

    __slots__ = (
        "_dynamic_colors",
        "_escbuf",
        "_hidden_screen",
        "_last_graphic",
        "_osc_control",
        "_osc_invalid_utf8",
        "_palette",
        "_parsestate",
        "_repeat_graphic",
        "_within_escape",
        "attribute_extent",
        "attrspec",
        "charset",
        "conformance_level",
        "display_default_colors",
        "has_focus",
        "height",
        "is_rotten_cursor",
        "margin_left",
        "margin_right",
        "modes",
        "protected",
        "saved_attrs",
        "saved_cursor",
        "saved_flags",
        "scroll_on_output",
        "scrollback_buffer",
        "scrolling_up",
        "scrollregion_end",
        "scrollregion_start",
        "tabstops",
        "term",
        "term_cursor",
        "term_type",
        "utf8_buffer",
        "utf8_eat_bytes",
        "widget",
        "width",
    )

    cacheable = False

    def __init__(
        self,
        width: int,
        height: int,
        widget: _TermCanvasOwner,
        *,
        scroll_on_output: bool = True,
        term_type: TermType = "linux",
    ) -> None:
        """Initialize an empty `width` by `height` canvas backing `widget`.

        :param scroll_on_output: move a view scrolled back from the bottom to the bottom when output arrives.
            When off, the view stays on the lines it shows while new lines scroll into the scrollback below them.
        :param term_type: the terminal type the output is written for: ``"linux"`` follows the Linux console where it
            differs from xterm, ``"xterm-256color"`` follows xterm.
        """
        super().__init__()

        self.width, self.height = width, height
        self.widget = widget
        self.modes: TermModes = widget.term_modes
        #: The terminal type the output is written for, see :meth:`__init__`.
        self.term_type: TermType = term_type
        self.has_focus = False
        #: Whether output returns a scrolled-back view to the bottom, see :meth:`__init__`.
        self.scroll_on_output = scroll_on_output

        self.scrollback_buffer: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]] = deque(
            maxlen=10000
        )
        self.scrolling_up = 0

        self.utf8_eat_bytes: int | None = None
        self.utf8_buffer = bytearray()
        self._escbuf = b""
        # the OSC string being read had a sequence that is not valid UTF-8, in UTF-8 mode
        self._osc_invalid_utf8 = False
        # the OSC string being read had a control character, which it goes on without
        self._osc_control = False

        self.coords["cursor"] = (0, 0, None)

        self.term_cursor: tuple[int, int] = (0, 0)  # do not allow to shoot in the leg at `set_term_cursor`

        self._within_escape = False
        self._parsestate: ParseState = ParseState.ESCAPE

        self.attrspec: AttrSpec | None = None
        #: DECSCA or SPA: the characters written are protected
        self.protected = False
        #: DECSACE: 2 makes DECCARA and DECRARA act on a rectangle, and any other value on a stream of cells
        self.attribute_extent = 0

        self.charset = TermCharset(g1_graphics=self.linux_console)

        self.saved_cursor: tuple[int, int] | None = None
        self.saved_attrs: tuple[AttrSpec | None, TermCharset] | None = None
        #: origin mode, a pending autowrap and DECSCA, saved with the attributes by DECSC, or None when nothing is saved
        self.saved_flags: tuple[bool, bool, bool] | None = None

        self.is_rotten_cursor = False
        # the character the last input wrote in a cell of its own, whether it is a DEC special graphics character,
        # and whether it is wide; None when the last input was anything else, such as a control function
        self._last_graphic: tuple[bytes, bool, bool] | None = None
        # the character REP repeats: the one written just before the escape sequence being read
        self._repeat_graphic: tuple[bytes, bool, bool] | None = None
        # the palette colors the child redefined, with the Linux console's palette sequence or xterm's OSC 4, as red,
        # green and blue
        self._palette: dict[int, tuple[int, int, int]] = {}
        # xterm's dynamic colors the child set with OSC 10 to 12, by their number, as red, green and blue
        self._dynamic_colors: dict[int, tuple[int, int, int]] = {}
        #: the default foreground and background colors of the display, as X11 color specs such as
        #: ``rgb:ffff/ffff/ffff``, which the replies to OSC 10 and OSC 11 describe until the child sets them; None while
        #: unknown. The widget sets it.
        self.display_default_colors: tuple[str | None, str | None] = (None, None)

        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1
        #: the left and right margins DECSLRM set, 0-based columns included; the screen's edges while DECLRMM is reset
        self.margin_left = 0
        self.margin_right = self.width - 1

        #: the conformance level DECSCL selected, 61 to 64: at 61 the VT300 reports are not answered, and below 64 the
        #: left and right margins cannot be set
        self.conformance_level = _CONFORMANCE_LEVELS[-1]

        self.tabstops: list[int] = []
        self.term: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]] = []
        # the screen not shown: the alternate one while the main one is shown, and the other way round
        self._hidden_screen = _Screen([], deque(maxlen=0))
        # a new canvas starts on its main screen, also for modes an earlier canvas left on the alternate one
        self.modes.alternate_screen = False

        self.reset()

    def set_term_cursor(self, x: int | None = None, y: int | None = None) -> None:
        """Set terminal cursor to x/y and update canvas cursor.

        If one or both axes are omitted, use the values of the current position.
        In origin mode the cursor stays within the left and right margins too.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        x, y = self.constrain_coords(x, y)
        if self.modes.constrain_scrolling:
            x = min(max(x, self.margin_left), self.margin_right)
        self.term_cursor = x, y

        # with a cursor style set, content() draws the cursor and the display shows none
        self.cursor = self._shown_cursor() if self.modes.cursor_style is None else None

    def _shown_cursor(self) -> tuple[int, int] | None:
        """Return the cursor's column and row in the view, or None while it is hidden, out of focus or scrolled away."""
        x, y = self.term_cursor
        if self.has_focus and self.modes.visible_cursor and self.scrolling_up < self.height - y:
            return x, y + self.scrolling_up
        return None

    def reset_scroll(self) -> None:
        """Reset scrolling region to full terminal size."""
        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1

    def reset_margins(self) -> None:
        """Set the left and right margins to the screen's edges."""
        self.margin_left = 0
        self.margin_right = self.width - 1

    def right_edge(self, x: int) -> int:
        """Return the last column the cursor at column *x* reaches.

        It is the right margin, or the screen's right edge for a cursor right of the margin.
        """
        return self.margin_right if x <= self.margin_right else self.width - 1

    def scroll_buffer(self, up: bool = True, reset: bool = False, lines: int | None = None) -> None:
        """Scroll the scrolling buffer up (up=True) or down (up=False) the given amount of lines.

        Scrolls half the screen height when *lines* is omitted.

        If just 'reset' is True, set the scrollbuffer view to the current terminal content.
        """
        if reset:
            self.scrolling_up = 0
            self.set_term_cursor()
            return

        if lines is None:
            lines = self.height // 2

        if not up:
            lines = -lines

        maxscroll = len(self.scrollback_buffer)
        self.scrolling_up += lines

        if self.scrolling_up > maxscroll:
            self.scrolling_up = maxscroll
        elif self.scrolling_up < 0:
            self.scrolling_up = 0

        self.set_term_cursor()

    @property
    def linux_console(self) -> bool:
        """Return whether the canvas follows the Linux console where it differs from xterm."""
        return self.term_type == "linux"

    @property
    def _vt_linux_palette(self) -> bool:
        """Return whether the Linux console's palette sequence is read: while the canvas follows the Linux console."""
        return self.linux_console

    def reset(self) -> None:
        """Reset the terminal to its startup state on the main screen.

        The main screen is cleared. It keeps its scrollback. The alternate screen is replaced by a blank one.
        The conformance level DECSCL selected stays, as in xterm.
        The palette colors the child redefined stay while the canvas follows the Linux console, which keeps them, and
        are set back while it follows xterm.
        """
        if self.modes.alternate_screen:
            self._swap_screens()

        self._escbuf = b""
        self._within_escape = False
        self._parsestate = ParseState.ESCAPE

        self.attrspec = None
        self.protected = False
        self.attribute_extent = 0
        self.charset = TermCharset(g1_graphics=self.linux_console)
        if not self.linux_console:
            # xterm sets its palette back, the Linux console keeps it
            self._palette.clear()

        self.saved_cursor = None
        self.saved_attrs = None
        self.saved_flags = None

        self.is_rotten_cursor = False
        self._last_graphic = self._repeat_graphic = None

        self.reset_scroll()
        self.reset_margins()

        self.init_tabstops()

        # terminal modes
        self.modes.reset()

        # initialize self.term
        self.clear()
        # the alternate screen keeps no scrollback, as in xterm: the lines scrolled off it are dropped
        self._hidden_screen = _Screen([[_BLANK_CELL] * self.width for _ in range(self.height)], deque(maxlen=0))

    def _swap_screens(self) -> None:
        """Swap the screen shown with the one kept apart.

        The cursor position stays where it is.
        """
        hidden = self._hidden_screen
        self._hidden_screen = _Screen(
            self.term,
            self.scrollback_buffer,
            self.saved_cursor,
            self.saved_attrs,
            self.modes.keyboard_flags,
            self.term_cursor[1],
            self.saved_flags,
        )
        self.term = hidden.term
        self.scrollback_buffer = hidden.scrollback_buffer
        self.saved_cursor = hidden.saved_cursor
        self.saved_attrs = hidden.saved_attrs
        self.saved_flags = hidden.saved_flags
        self.modes.keyboard_flags = hidden.keyboard_flags
        self.modes.alternate_screen = not self.modes.alternate_screen
        self.scroll_buffer(reset=True)

    def set_alternate_screen(self, mode: PrivateMode, flag: bool) -> None:
        """Switch to or from the alternate screen for DEC private *mode*, as xterm does.

        Each screen keeps its own content, scrollback, cursor saved by DECSC and keyboard flags. The cursor position
        is shared.

        - 47 switches to the alternate screen when set, and back to the main one when reset.
        - 1047 also clears the alternate screen before switching back from it.
        - 1049 also saves the cursor as DECSC does before switching to the alternate screen.
        - 1049 also clears the alternate screen after switching to it.
        - 1049 also restores the saved cursor after switching back to the main screen.

        :param mode: one of the modes in :data:`_ALTERNATE_SCREEN_MODES`.
        :param flag: the mode is set rather than reset.
        """
        if flag:
            if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
                self.save_cursor(with_attrs=True)
            if not self.modes.alternate_screen:
                self._swap_screens()
            if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
                self.clear(cursor=self.term_cursor)
            return

        if self.modes.alternate_screen:
            if mode == PrivateMode.ALTERNATE_SCREEN_CLEARED_ON_EXIT:
                self.clear(cursor=self.term_cursor)
            self._swap_screens()
        if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
            self.restore_cursor(with_attrs=True)

    def init_tabstops(self, extend: bool = False) -> None:
        """Set every column to a tabstop, or, when *extend* is set, grow the existing tabstops to the new width."""
        tablen, mod = divmod(self.width, 8)
        if mod > 0:
            tablen += 1

        if extend:
            while len(self.tabstops) < tablen:
                self.tabstops.append(1 << 0)
        else:
            self.tabstops = [1 << 0] * tablen

    def set_tabstop(self, x: int | None = None, remove: bool = False, clear: bool = False) -> None:
        """Set, remove, or (with *clear*) remove every tabstop, at column *x* or the cursor's column by default."""
        if clear:
            for tab in range(len(self.tabstops)):
                self.tabstops[tab] = 0
            return

        if x is None:
            x = self.term_cursor[0]

        div, mod = divmod(x, 8)
        if remove:
            self.tabstops[div] &= ~(1 << mod)
        else:
            self.tabstops[div] |= 1 << mod

    def is_tabstop(self, x: int | None = None) -> bool:
        """Return whether column *x* (the cursor's column by default) is a tabstop."""
        if x is None:
            x = self.term_cursor[0]

        div, mod = divmod(x, 8)
        return (self.tabstops[div] & (1 << mod)) > 0

    def empty_line(self, char: bytes = _BLANK) -> list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]:
        """Return a full row of empty characters, one per column, filled with *char*."""
        return [self.empty_char(char)] * self.width

    def empty_char(self, char: bytes = _BLANK) -> tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]:
        """Return one empty terminal cell holding *char*, with the canvas's current colours and charset.

        As in xterm, an erased or scrolled-in cell takes the colours only: not bold, underline, reverse video or the
        other attribute flags, and not the current hyperlink.
        By default it holds a space never written, which DECRQCRA counts as xterm does.
        """
        attrspec = self.attrspec
        if attrspec is not None and attrspec.hyperlink is not None:
            attrspec = attrspec_with_hyperlink(attrspec, None, unset_color="default")
        if attrspec is None:
            return (None, self.charset.current, char)
        if any(getattr(attrspec, name) for name, _code in _sgr.FLAGS):
            colour = ",".join(
                part
                for part in (part.strip() for part in attrspec.foreground.split(","))
                if part not in _sgr.FLAG_NAMES
            )
            attrspec = attrspec.copy_modified(fg=colour or "default")
        if attrspec.foreground == "default" == attrspec.background:
            return (None, self.charset.current, char)
        return (attrspec, self.charset.current, char)

    def resize(self, width: int, height: int) -> None:
        """Resize both screens to the given width and height.

        A screen that shrinks drops its blank bottom rows below the cursor first, so the cursor stays on its line
        unless a row below it holds content; the cursor and the saved cursors move with the rows that stay.
        For the hidden screen, that row is the one its cursor was on when it was hidden.
        A view scrolled back keeps showing the same top line.
        """
        x, y = self.term_cursor

        shift = self._resize_lines(self.term, self.scrollback_buffer, width, height, cursor_row=y)
        y += shift
        if self.saved_cursor is not None:
            self.saved_cursor = (self.saved_cursor[0], self.saved_cursor[1] + shift)
        hidden = self._hidden_screen
        hidden_shift = self._resize_lines(
            hidden.term,
            hidden.scrollback_buffer,
            width,
            height,
            cursor_row=hidden.cursor_row,
        )
        hidden.cursor_row += hidden_shift
        if hidden.saved_cursor is not None:
            hidden.saved_cursor = (hidden.saved_cursor[0], hidden.saved_cursor[1] + hidden_shift)

        self.width = width
        self.height = height

        self.reset_scroll()
        self.reset_margins()
        if self.scrolling_up:
            # the lines moved into the scrollback, or taken back from it, would otherwise move the view
            self.scrolling_up = max(0, min(self.scrolling_up - shift, len(self.scrollback_buffer)))

        x, y = self.constrain_coords(x, y)
        self.set_term_cursor(x, y)

        # extend tabs
        self.init_tabstops(extend=True)

    def _resize_lines(
        self,
        lines: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]],
        scrollback: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]],
        width: int,
        height: int,
        *,
        cursor_row: int | None = None,
    ) -> int:
        """Fit *lines*, a screen of the current size, to *width* and *height* in place.

        A screen that shrinks moves its top lines to the end of *scrollback*, and one that grows takes them back from
        there, or adds blank lines at the bottom once *scrollback* is empty.
        With *cursor_row*, a shrinking screen first drops the blank lines at its bottom below that row,
        so the lines above stay on the screen.
        A blank line is spaces with no attributes, in any character set.

        :returns: how many rows the lines that stay on the screen moved down, negative when they moved up.
        """
        for row in range(self.height):
            lines[row] = _fit_line(lines[row], width)

        shift = 0
        for _y in range(self.height, height):
            if not scrollback:
                lines.append([_BLANK_CELL] * width)
                continue

            # adjust x axis of the scrollback line to the new width
            last_line = scrollback.pop()
            lines.insert(0, _fit_line(last_line, width))
            shift += 1
        for _y in range(height, self.height):
            if (
                cursor_row is not None
                and len(lines) - 1 > cursor_row + shift
                and all(attr is None and text == b" " for attr, _charset, text in lines[-1])
            ):
                lines.pop()
                continue
            scrollback.append(lines.pop(0))
            shift -= 1

        return shift

    def set_char(
        self,
        char: bytes,
        x: int | None = None,
        y: int | None = None,
        *,
        dec_special: bool = False,
    ) -> None:
        """Set character of either the current cursor position or a position given by 'x' and/or 'y' to 'char'.

        The other half of a wide character the cell was part of becomes a space.

        :param char: the character to store.
        :param x: the column, the cursor's when not given.
        :param y: the row, the cursor's when not given.
        :param dec_special: store *char* in the DEC special character set instead of the active one.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        x, y = self.constrain_coords(x, y)
        if self.protected:
            char = _Protected(char)
        line = self.term[y]
        replaced = line[x][2]
        line[x] = (self.attrspec, "0" if dec_special else self.charset.current, char)
        if not replaced or (len(replaced) > 1 and _drawn_width(replaced) == 2):
            # a wide character written over loses its other half
            _mend_wide(line, x)
            _mend_wide(line, x + 1)

    def constrain_coords(self, x: int, y: int, ignore_scrolling: bool = False) -> tuple[int, int]:
        """Check if x/y are within the terminal and return the corrected version.

        If 'ignore_scrolling' is set, constrain within the full size of the screen and not within scrolling region.
        """
        if x >= self.width:
            x = self.width - 1
        elif x < 0:
            x = 0

        if self.modes.constrain_scrolling and not ignore_scrolling:
            if y > self.scrollregion_end:
                y = self.scrollregion_end
            elif y < self.scrollregion_start:
                y = self.scrollregion_start
        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            if y >= self.height:
                y = self.height - 1
            elif y < 0:
                y = 0

        return x, y

    def save_cursor(self, with_attrs: bool = False) -> None:
        """Save the current cursor position.

        With *with_attrs*, as DECSC, the attributes, DECSCA, the character sets, origin mode and a pending autowrap are
        saved too.
        """
        self.saved_cursor = self.term_cursor
        if with_attrs:
            self.saved_attrs = (copy.copy(self.attrspec), copy.copy(self.charset))
            self.saved_flags = (self.modes.constrain_scrolling, self.is_rotten_cursor, self.protected)

    def restore_cursor(self, with_attrs: bool = False) -> None:
        """Restore the cursor position saved by :meth:`save_cursor`.

        Without *with_attrs* only the position is restored, a pending autowrap ends, and nothing happens when no
        position was saved.

        With *with_attrs*, as DECRC, the attributes, DECSCA, the character sets, origin mode and a pending autowrap are
        restored too.
        Whatever :meth:`save_cursor` did not save with them is reset instead, as in xterm: the cursor moves home when no
        position was saved, and the attributes, DECSCA, the character sets and origin mode take their startup values.
        The IBM PC mapping of SGR 11 and 12 ends, as on the Linux console, which draws from the restored slot's set.
        """
        if self.saved_cursor is None and not with_attrs:
            return
        x, y = (0, 0) if self.saved_cursor is None else self.saved_cursor
        origin, wrap, protected = (False, False, False) if self.saved_flags is None else self.saved_flags

        if with_attrs:
            if self.saved_attrs is None:
                self.csi_set_attr([0])
                self.charset = TermCharset(g1_graphics=self.linux_console)
            else:
                self.attrspec, self.charset = (copy.copy(self.saved_attrs[0]), copy.copy(self.saved_attrs[1]))
                self.charset.reset_sgr_ibmpc()
            self.protected = protected
            # origin mode first, since it decides how the position is constrained
            self.modes.constrain_scrolling = origin

        self.set_term_cursor(x, y)
        self.is_rotten_cursor = with_attrs and wrap

    def scroll(self, reverse: bool = False, *, scrollback: bool = True) -> None:
        """Append a new line at the bottom of the scrolling region and remove its topmost line.

        The removed line goes into the scrollback buffer when the region starts at the top row, as in xterm.
        A region below the top row drops it, and so does a scroll without *scrollback*.
        If reverse is True, do exactly the opposite, but don't save into scrollback buffer.
        With left and right margins inside the screen, only the cells between them scroll, and nothing goes into the
        scrollback buffer, as in xterm.
        """
        if self.margin_left or self.margin_right < self.width - 1:
            self._shift_between_margins(self.scrollregion_start, self.scrollregion_end, -1 if reverse else 1)
            return
        if reverse:
            self.term.pop(self.scrollregion_end)
            self.term.insert(self.scrollregion_start, self.empty_line())
        else:
            killed = self.term.pop(self.scrollregion_start)
            self.term.insert(self.scrollregion_end, self.empty_line())
            if self.scrollregion_start > 0 or not scrollback:
                return
            self.scrollback_buffer.append(killed)
            if self.scrolling_up and not self.scroll_on_output:
                # the view moves up with the lines it shows
                self.scrolling_up = min(self.scrolling_up + 1, len(self.scrollback_buffer))

    def _shift_between_margins(self, top: int, bottom: int, lines: int) -> None:
        """Move the cells between the left and right margins in rows *top* to *bottom* up by *lines* rows.

        A negative *lines* moves them down.
        The cells left behind between the margins become blank.
        """
        left, right = self.margin_left, self.margin_right
        rows = [self.term[y][left : right + 1] for y in range(top, bottom + 1)]
        count = min(abs(lines), len(rows))
        blanks = [[self.empty_char()] * (right - left + 1)] * count
        rows = [*rows[count:], *blanks] if lines > 0 else [*blanks, *rows[: len(rows) - count]]
        for y, cells in enumerate(rows, top):
            line = self.term[y]
            line[left : right + 1] = cells
            _mend_wide(line, left)
            _mend_wide(line, right + 1)

    def decaln(self) -> None:
        """DEC screen alignment test: fill the screen with E's, without attributes and in ASCII, as xterm does.

        As in xterm, the left and right margins are reset and the cursor moves home.
        """
        cell: tuple[AttrSpec | None, Literal["0", "U"] | None, bytes] = (None, None, b"E")
        for row in range(self.height):
            self.term[row] = [cell] * self.width
        self.reset_margins()
        self.set_term_cursor(0, 0)
        self.is_rotten_cursor = False

    def blank_line(self, row: int) -> None:
        """Blank a single line at the specified row, without modifying other lines."""
        self.term[row] = self.empty_line()

    def insert_chars(
        self,
        position: tuple[int, int] | None = None,
        chars: int = 1,
        char: bytes | None = None,
        *,
        dec_special: bool = False,
    ) -> None:
        """Insert 'chars' number of empty characters (or those given by 'char') before 'position'.

        Defaults to the current position if 'position' is not specified,
        pushing subsequent characters of the line to the right without wrapping.
        The characters pushed past :meth:`right_edge` are dropped, as in xterm.
        With *dec_special*, 'char' is stored in the DEC special character set instead of the active one.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        if char is None:
            # inserted blanks are written spaces, as in xterm
            char_spec = self.empty_char(b" ")
        else:
            charset: Literal["0", "U"] | None = "0" if dec_special else self.charset.current
            char_spec = (self.attrspec, charset, _Protected(char) if self.protected else char)

        x, y = position
        line = self.term[y]
        right = self.right_edge(x)
        chars = min(chars, right + 1 - x)
        line[x:x] = [char_spec] * chars
        del line[right + 1 : right + 1 + chars]
        _mend_wide(line, x)
        _mend_wide(line, x + chars)
        _mend_wide(line, right + 1)

    def remove_chars(self, position: tuple[int, int] | None = None, chars: int = 1) -> None:
        """Remove 'chars' number of empty characters from 'position'.

        Defaults to the current position if 'position' is not specified,
        pulling subsequent characters of the line to the left without joining any subsequent lines.
        The characters up to :meth:`right_edge` move, and blanks fill the cells left before it, as in xterm.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        x, y = position
        right = self.right_edge(x)
        chars = min(chars, right + 1 - x)
        line = self.term[y]
        del line[x : x + chars]
        line[right + 1 - chars : right + 1 - chars] = [self.empty_char()] * chars
        _mend_wide(line, x)
        _mend_wide(line, right + 1 - chars)
        _mend_wide(line, right + 1)

    def insert_lines(self, row: int | None = None, lines: int = 1) -> None:
        """Insert 'lines' empty lines at 'row', or the cursor row, pushing the lines below down the scrolling region.

        Lines pushed past the bottom of the scrolling region are dropped.
        Nothing happens when the row is outside the scrolling region.
        At the cursor row, as IL, the cursor moves to the left margin and a pending wrap ends, as in xterm, and
        nothing happens while the cursor is outside the left and right margins.
        With left and right margins inside the screen, only the cells between them move.
        """
        at_cursor = row is None
        if row is None:
            row = self.term_cursor[1]

        if lines == 0:
            lines = 1

        if not self.scrollregion_start <= row <= self.scrollregion_end:
            return

        if at_cursor:
            if not self.margin_left <= self.term_cursor[0] <= self.margin_right:
                return
            self.set_term_cursor(self.margin_left, row)
            self.is_rotten_cursor = False

        if self.margin_left or self.margin_right < self.width - 1:
            self._shift_between_margins(row, self.scrollregion_end, -lines)
            return

        for _ in range(min(lines, self.scrollregion_end - row + 1)):
            self.term.insert(row, self.empty_line())
            self.term.pop(self.scrollregion_end + 1)

    def remove_lines(self, row: int | None = None, lines: int = 1) -> None:
        """Remove 'lines' lines at 'row', or the cursor row, pulling the lines below up the scrolling region.

        Empty lines fill the bottom of the scrolling region.
        Nothing happens when the row is outside the scrolling region.
        At the cursor row, as DL, the cursor moves to the left margin and a pending wrap ends, as in xterm, and
        nothing happens while the cursor is outside the left and right margins.
        With left and right margins inside the screen, only the cells between them move.
        """
        at_cursor = row is None
        if row is None:
            row = self.term_cursor[1]

        if lines == 0:
            lines = 1

        if not self.scrollregion_start <= row <= self.scrollregion_end:
            return

        if at_cursor:
            if not self.margin_left <= self.term_cursor[0] <= self.margin_right:
                return
            self.set_term_cursor(self.margin_left, row)
            self.is_rotten_cursor = False

        if self.margin_left or self.margin_right < self.width - 1:
            self._shift_between_margins(row, self.scrollregion_end, lines)
            return

        for _ in range(min(lines, self.scrollregion_end - row + 1)):
            self.term.pop(row)
            self.term.insert(self.scrollregion_end, self.empty_line())

    def erase(
        self,
        start: tuple[int, int] | tuple[int, int, bool],
        end: tuple[int, int] | tuple[int, int, bool],
        *,
        selective: bool = False,
    ) -> None:
        """Erase a region of the terminal.

        As in xterm, the cells of a row erased up to its last column hold spaces never written, and the cells of a row
        erased short of it hold written spaces, which DECRQCRA counts.
        With *selective*, as DECSED and DECSEL, or as ED, EL and ECH after SPA, the protected characters are kept, and
        each run of cells between them is erased as a row would be.
        A pending wrap ends, as in xterm.

        The 'start' tuple (x, y) defines the starting position of the erase, while end (x, y) the last position.

        For example if the terminal size is 4x3, start=(1, 1) and end=(1, 2)
        would erase the following region:

        ....
        .XXX
        XX..
        """
        # pyrefly: ignore[bad-argument-type]  # the optional third element widens to bool | int
        sx, sy = self.constrain_coords(*start)
        # pyrefly: ignore[bad-argument-type]  # the optional third element widens to bool | int
        ex, ey = self.constrain_coords(*end)

        self.is_rotten_cursor = False
        blank = self.empty_char()
        written = self.empty_char(b" ")
        for y in range(sy, ey + 1):
            line = self.term[y]
            first = sx if y == sy else 0
            last = ex if y == ey else self.width - 1
            runs = [(first, last)]
            if selective:
                kept = [x for x in range(first, last + 1) if isinstance(line[x][2], _Protected)]
                runs = list(zip((first, *(x + 1 for x in kept)), (*(x - 1 for x in kept), last), strict=True))
            for run_first, run_last in runs:
                if run_first <= run_last:
                    cell = blank if run_last == self.width - 1 else written
                    line[run_first : run_last + 1] = [cell] * (run_last - run_first + 1)
                    _mend_wide(line, run_first)
                    _mend_wide(line, run_last + 1)

    def csi_set_attr(self, attrs: Sequence[int | tuple[int, ...]]) -> None:
        """Set graphics rendition.

        The colour/attribute-flag computation itself is delegated to the shared, platform-independent
        :func:`urwid.ansi_parser.sgi_params_to_attrspec`; SGR 10/11/12 toggle vterm's own charset/display-control
        state rather than colour/attributes, so that side effect is applied separately, here, since
        ``sgi_params_to_attrspec`` deliberately ignores it (see its docstring).

        :param attrs: the SGR numeric parameters to apply, in encounter order;
            a tuple is a code already split, as :func:`urwid.ansi_parser.split_sgr_parameters` gives it.
            The arguments of an extended color are never read as SGR 10 to 12.
            They are read only while the canvas follows the Linux console; xterm ignores them.
        """
        if self.linux_console:
            for code in split_sgr_parameters(attrs):
                if code == (10,):
                    self.charset.reset_sgr_ibmpc()
                    self.modes.display_ctrl = False
                elif code in {(11,), (12,)}:
                    self.charset.set_sgr_ibmpc()
                    self.modes.display_ctrl = True

        self.attrspec = sgi_params_to_attrspec(attrs, self.attrspec)

    def reverse_attrspec(self, attrspec: AttrSpec | None, undo: bool = False) -> AttrSpec:
        """Put standout mode to the 'attrspec' given and remove it if 'undo' is True."""
        return _with_flag(attrspec, "standout", remove=undo)

    @deprecated(
        "TermCanvas.reverse_video() is deprecated, set TermCanvas.modes.reverse_video instead. "
        "Deprecated since urwid 5.1.3, will be removed in version 8.0.",
        category=None,
    )
    def reverse_video(self, undo: bool = False) -> None:
        """Turn the reverse video mode (DECSCNM) on, or off if *undo* is True.

        .. deprecated:: 5.1.3
            Set :attr:`TermCanvas.modes.reverse_video <TermModes.reverse_video>` instead.
            This method will be removed in version 8.0.
        """
        _deprecation.warn(
            "TermCanvas.reverse_video() is deprecated, set TermCanvas.modes.reverse_video instead.",
            since="5.1.3",
            removed_in="8.0",
            category=PendingDeprecationWarning,
        )
        self.modes.reverse_video = not undo

    def clear(self, cursor: tuple[int, int] | None = None) -> None:
        """Clear the whole terminal screen and move the cursor to (0, 0) or to 'cursor'.

        A pending wrap ends, as in xterm.
        """
        self.term = [self.empty_line() for _ in range(self.height)]

        if cursor is None:
            self.set_term_cursor(0, 0)
        else:
            self.set_term_cursor(*cursor)
        self.is_rotten_cursor = False

    def cols(self) -> int:
        """Return the canvas's number of columns."""
        return self.width

    def rows(self) -> int:
        """Return the canvas's number of rows."""
        return self.height

    def content(  # type: ignore[override]
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]:
        """Canvas content.

        The cells store the attributes the child set.
        The palette colors the child redefined, with the Linux palette sequence or xterm's OSC 4, and the default colors
        it set with OSC 10 and OSC 11, are drawn with their new values as 24-bit colors, which the screen converts to
        the colors it draws; every other color keeps its kind and number.
        While the reverse video mode (DECSCNM) is on, every line is yielded with its attributes in standout.
        After a DECSCUSR the shown cursor cell is drawn in reverse video for a block or a bar, or underlined for an
        underline, and the blinking styles are drawn steady.
        A cell that is already in reverse video, or already underlined for an underline, is drawn without it.
        A cursor color set with xterm's OSC 12 is drawn as xterm draws it instead:
        the underline in that color, or for a block or a bar the cell in that color with its text in the color the
        cell's background is shown in.
        On a cell that is already underlined, and where the cursor color is the color a block cursor has to stand out
        from, the cursor is drawn as without a color, since a display may not draw the color.

        All parameters are ignored.
        """
        lines = self._screen_lines()
        if self._palette or self._dynamic_colors:
            lines = self._recolored(lines)
        style = self.modes.cursor_style
        if style is None or (shown := self._shown_cursor()) is None:
            yield from lines
            return
        cursor_x, cursor_y = shown
        cursor_color = self._dynamic_colors.get(_DYNAMIC_CURSOR)
        for row, line in enumerate(lines):
            if row != cursor_y or cursor_x >= len(line):
                yield line
                continue
            # a copy, so the screen's own row is not changed
            drawn = line.copy()
            if not drawn[cursor_x][2] and cursor_x > 0:
                # the second half of a wide character: its first half draws both
                cursor_x -= 1
            cell_attr, charset, text = drawn[cursor_x]
            underline = style in _UNDERLINE_CURSOR_STYLES
            if cursor_color is not None and self._shows_colored_cursor(cell_attr, cursor_color, underline=underline):
                cell_attr = _colored_cursor(cell_attr, underline=underline, color=cursor_color)
            else:
                # the flag is turned off on a cell that already has it, so the cursor stays visible there
                flag = "underline" if underline else "standout"
                cell_attr = _with_flag(cell_attr, flag, remove=cell_attr is not None and getattr(cell_attr, flag))
            drawn[cursor_x] = (cell_attr, charset, text)
            yield drawn

    def _shows_colored_cursor(
        self,
        attr: AttrSpec | None,
        color: tuple[int, int, int],
        *,
        underline: bool,
    ) -> bool:
        """Return whether a cursor of the RGB color *color* on the cell *attr* differs from the cell by more than color.

        An underline cursor on a cell that is already underlined differs only by its color.
        A block cursor differs from its cell by its standout state, unless its color is the one the cell's background
        is shown in, as far as that color is known.
        """
        if underline:
            return attr is None or not attr.underline
        foreground, background, _line = (_depth.DEFAULT_CHANNEL,) * 3 if attr is None else _depth.channels(attr)
        standout = attr is not None and attr.standout
        return self._shown_rgb(foreground if standout else background, background=not standout) != color

    def _shown_rgb(self, channel: _depth.Channel, *, background: bool) -> tuple[int, int, int] | None:
        """Return the RGB value a color channel of a cell is shown in, None when it is not known.

        :param background: a default color is the default background, not the default foreground.
        """
        match channel.kind:
            case _depth.Kind.DEFAULT if self.linux_console:
                entry = _DEFAULT_BACKGROUND_ENTRY if background else _DEFAULT_FOREGROUND_ENTRY
                return self._palette.get(entry, _depth.rgb_values(_depth.Channel(_depth.Kind.BASIC, entry)))
            case _depth.Kind.DEFAULT:
                number = _DYNAMIC_BACKGROUND if background else _DYNAMIC_FOREGROUND
                if number in self._dynamic_colors:
                    return self._dynamic_colors[number]
                spec = self.display_default_colors[1 if background else 0]
                return None if spec is None else _x11_rgb(spec)
            case _depth.Kind.INHERIT:
                return None
            case _depth.Kind.BASIC | _depth.Kind.INDEX_88 | _depth.Kind.INDEX_256:
                return self._palette.get(channel.number, _depth.rgb_values(channel))
            case _depth.Kind.RGB:
                return _depth.rgb_components(channel.number)
            case _:
                typing.assert_never(channel.kind)

    def _recolored(
        self,
        lines: Iterable[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]],
    ) -> Iterator[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]:
        """Yield *lines* with each palette color the child redefined drawn as its new value.

        The palette entries are the colors of their number, 0 to 15 on the Linux console and 0 to 255 in xterm.
        The default foreground and background are entries 7 and 0 on the Linux console; in xterm they are the
        dynamic colors OSC 10 and OSC 11 set.
        """
        redefined: dict[int | str | None, tuple[int, int, int]] = dict(self._palette.items())
        for number, key in ((_DYNAMIC_FOREGROUND, _FOREGROUND_KEY), (_DYNAMIC_BACKGROUND, _BACKGROUND_KEY)):
            if number in self._dynamic_colors:
                redefined[key] = self._dynamic_colors[number]
        # a screen holds few distinct attributes, so each one is recolored once per call
        recolored: dict[AttrSpec | None, AttrSpec | None] = {}
        for line in lines:
            new_line = []
            for cell_attr, charset, text in line:
                if cell_attr not in recolored:
                    recolored[cell_attr] = self._recolored_attr(cell_attr, redefined)
                new_line.append((recolored[cell_attr], charset, text))
            yield new_line

    def _recolored_attr(
        self,
        attr: AttrSpec | None,
        redefined: Mapping[int | str | None, tuple[int, int, int]],
    ) -> AttrSpec | None:
        """Return *attr* with its colors, the underline color included, from the *redefined* colors, or *attr* itself.

        Only the colors that were redefined are replaced, by their exact RGB value; the others keep their kind.

        :param redefined: the new values, by palette entry and by the keys of the default colors.
        """
        # the Linux console draws the default colors with palette entries, xterm with colors of their own
        default_fg: int | str = _DEFAULT_FOREGROUND_ENTRY if self.linux_console else _FOREGROUND_KEY
        default_bg: int | str = _DEFAULT_BACKGROUND_ENTRY if self.linux_console else _BACKGROUND_KEY
        fg_entry: int | str | None
        bg_entry: int | str | None
        line_entry: int | None
        if attr is None:
            fg_entry, bg_entry, line_entry = default_fg, default_bg, None
        else:
            foreground, background, _line = _depth.channels(attr)
            fg_entry = _palette_entry(foreground, default_fg)
            bg_entry = _palette_entry(background, default_bg)
            line_entry = _underline_palette_entry(attr)
        if fg_entry not in redefined and bg_entry not in redefined and line_entry not in redefined:
            return attr
        return _depth.replace_channels(
            attr,
            foreground=_depth.rgb(*redefined[fg_entry]) if fg_entry in redefined else None,
            background=_depth.rgb(*redefined[bg_entry]) if bg_entry in redefined else None,
            underline=_depth.rgb(*redefined[line_entry]) if line_entry in redefined else None,
        )

    def _screen_lines(self) -> Iterator[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]:
        """Yield the rows in view, with their attributes in standout while the reverse video mode (DECSCNM) is on."""
        lines: Iterable[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
        if self.scrolling_up == 0:
            lines = self.term
        else:
            viewport_range = slice(-(self.height + self.scrolling_up), -self.scrolling_up)
            lines = (_fit_line(line, self.width) for line in (*self.scrollback_buffer, *self.term)[viewport_range])

        if not self.modes.reverse_video:
            yield from lines
            return

        # a screen holds few distinct attributes, so each one is reversed once per call
        reversed_attrs: dict[AttrSpec | None, AttrSpec] = {}
        for line in lines:
            reversed_line: list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]] = []
            for cell_attr, charset, text in line:
                if cell_attr not in reversed_attrs:
                    reversed_attrs[cell_attr] = self.reverse_attrspec(cell_attr)
                reversed_line.append((reversed_attrs[cell_attr], charset, text))
            yield reversed_line
