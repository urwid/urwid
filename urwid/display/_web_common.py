# Urwid browser display rendering
#    Copyright (C) 2004-2007  Ian Ward
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

"""Rendering shared by the screens that draw into a browser page.

The page script that reads the row format lives in ``_web_common.js`` next to this module.
"""

from __future__ import annotations

import typing
import unicodedata

from urwid.str_util import calc_text_pos, calc_width, move_next_char
from urwid.util import get_encoding

from .common import AttrSpec, BaseScreen, _browser_href, attr_spec_to_css

if typing.TYPE_CHECKING:
    from urwid.canvas import Canvas

MAX_COLS = 200
MAX_ROWS = 100

# replace control characters with ?'s
_trans_table = str.maketrans(dict.fromkeys(range(32), "?"))

# the separator between the fields of a span in the wire format: inline CSS, the optional link URL, and the text;
# safe because control characters in the text have already been replaced by _trans_table,
# and a Hyperlink URI is printable ASCII
_STYLE_SEP = "\x01"

#: index into the (basic, mono, high_88, high_256, high_true) tuple stored per palette entry,
#: selected by the ``colors`` value passed to :meth:`BrowserScreen.set_terminal_properties`
_COLOUR_INDEX = {1: 1, 16: 0, 88: 2, 256: 3, 2**24: 4}

_default_foreground = "black"
_default_background = "light gray"

# a row of a canvas with its attributes resolved, plus the cursor column when the cursor is on that row
_RowSignature: typing.TypeAlias = tuple[tuple[AttrSpec, str] | int | None, ...]

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


def is_key_name(key: str) -> bool:
    """Return whether `key` is a key name the page script sends.

    The name is any single character or one of the named keys, after the modifier prefixes in the script's order.
    A control character and a lone surrogate are not key names.

    >>> is_key_name("shift meta page up")
    True
    >>> is_key_name("ctrl shift a")
    False
    """
    name = key
    for modifier in _MODIFIERS:
        name = name.removeprefix(modifier)
    # Cc and Cs do not change between Unicode versions
    return name in _KEY_NAMES or (len(name) == 1 and unicodedata.category(name) not in {"Cc", "Cs"})


def code_span(s: str, aspec: AttrSpec, cursor: int = -1) -> str:
    """Return `s` wrapped in an HTML ``<code>`` span styled per `aspec`, with the cursor column highlighted.

    A piece is sent as ``css SEP text``, or as ``css SEP url SEP text`` when *aspec* has a hyperlink
    with a scheme a browser may follow (see :ref:`hyperlinks`).
    """
    fg, bg, extra = attr_spec_to_css(aspec)
    href = _browser_href(aspec.hyperlink) if aspec.hyperlink is not None else None
    link = "" if href is None else f"{href}{_STYLE_SEP}"

    def _piece(fg_: str, bg_: str, text: str) -> str:
        return f"color:{fg_};background-color:{bg_}{extra}{_STYLE_SEP}{link}{text}\n"

    if cursor >= 0:
        c_off, _ign = calc_text_pos(s, 0, len(s), cursor)
        c2_off = move_next_char(s, c_off, len(s))

        return _piece(fg, bg, s[:c_off]) + _piece(bg, fg, s[c_off:c2_off]) + _piece(fg, bg, s[c2_off:])

    return _piece(fg, bg, s)


class BrowserScreen(BaseScreen):  # pylint: disable=abstract-method  # the subclasses draw
    """Base of the screens that send their rows to a page script in a browser.

    It holds the palette handling and the row format the page script draws.
    A row that the browser already shows is sent as a reference to that row instead of its text.
    """

    def __init__(self) -> None:
        """Initialize an unstarted screen defaulting to true color."""
        super().__init__()
        self.has_color = True
        self.colors = 2**24  # browsers render arbitrary RGB, so default to true color
        self.bright_is_bold = False  # ignored: the browser renders bold as requested
        self.has_underline = True  # ignored: the browser renders underline as requested
        self._colour_index = _COLOUR_INDEX[self.colors]
        # the rows the browser shows, by signature, so an unchanged row is sent as a reference
        self.last_screen: dict[_RowSignature, list[int]] = {}
        self.last_screen_width = 0
        self.register_palette_entry(None, _default_foreground, _default_background)

    def set_terminal_properties(
        self,
        colors: int | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
    ) -> None:
        """Set the number of colors used to resolve named palette entries.

        :param colors: one of 1, 16, 88, 256 or 2**24 (2**24, true color, is the default,
            since a browser can render any RGB color directly)
        :param bright_is_bold: ignored, kept for API parity with the other display modules
        :param has_underline: ignored, kept for API parity with the other display modules
        :raises KeyError: *colors* is not one of the supported palette sizes.
        """
        if colors is not None:
            self._colour_index = _COLOUR_INDEX[colors]
            self.colors = colors
        if bright_is_bold is not None:
            self.bright_is_bold = bright_is_bold
        if has_underline is not None:
            self.has_underline = has_underline

    def _render_rows(self, size: tuple[int, int], canvas: Canvas) -> list[str]:
        """Return the rows of *canvas* in the page script's row format, and remember them as shown.

        Each row is its spans, one ``code_span`` piece per line, followed by an empty line.
        A row the browser already shows is a single ``<N`` line naming the row to copy.

        :raises ValueError: *canvas* does not have the number of rows given by *size*.
        """
        (cols, rows) = size
        encoding = get_encoding()

        if cols != self.last_screen_width:
            self.last_screen = {}

        if canvas.rows() != rows:
            raise ValueError(rows)

        if canvas.cursor is not None:
            cx, cy = canvas.cursor
        else:
            cx = cy = -1  # no cursor: matches no row

        sendq: list[str] = []
        new_screen: dict[_RowSignature, list[int]] = {}

        y = -1
        for row in canvas.content():
            y += 1
            # resolved, so a row is sent again when a palette change gives it other colors
            l_row = tuple(
                (self.resolve_attr(attr_, self._colour_index), line.decode(encoding, "replace"))
                for attr_, _, line in row
            )

            line = []

            sig: _RowSignature = l_row
            if y == cy:
                sig = (*sig, cx)
            new_screen.setdefault(sig, []).append(y)

            if (old_line_numbers := self.last_screen.get(sig, None)) is not None:
                old_line = y if y in old_line_numbers else old_line_numbers[0]
                sendq.append(f"<{old_line:d}\n")
                continue

            col = 0
            for aspec, run in l_row:
                t_run = run.translate(_trans_table)
                if y == cy and col <= cx:
                    run_width = calc_width(t_run, 0, len(t_run))
                    if col + run_width > cx:
                        line.append(code_span(t_run, aspec, cx - col))
                    else:
                        line.append(code_span(t_run, aspec))
                    col += run_width
                else:
                    line.append(code_span(t_run, aspec))

            sendq.append(f"{''.join(line)}\n")
        self.last_screen = new_screen
        self.last_screen_width = cols
        return sendq
