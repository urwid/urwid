# Urwid html fragment output wrapper for "screen shots"
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


"""
HTML PRE-based UI implementation
"""

from __future__ import annotations

import html
import typing

from urwid import str_util
from urwid.event_loop import ExitMainLoop
from urwid.util import get_encoding

from .common import AttrSpec, BaseScreen

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from urwid import Canvas

# replace control characters with ?'s
_trans_table = "?" * 32 + "".join(chr(x) for x in range(32, 256))

_default_foreground = "black"
_default_background = "light gray"


class HtmlGeneratorSimulationError(Exception):
    pass


class HtmlGenerator(BaseScreen):
    # class variables
    fragments: typing.ClassVar[list[str]] = []
    sizes: typing.ClassVar[list[tuple[int, int]]] = []
    keys: typing.ClassVar[list[list[str]]] = []
    started = True

    def __init__(self) -> None:
        super().__init__()
        self.colors = 16
        self.bright_is_bold = False  # ignored
        self.has_underline = True  # ignored
        self.register_palette_entry(None, _default_foreground, _default_background)

    def set_terminal_properties(
        self,
        colors: int | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
    ) -> None:
        if colors is None:
            colors = self.colors
        if bright_is_bold is None:
            bright_is_bold = self.bright_is_bold
        if has_underline is None:
            has_underline = self.has_underline

        self.colors = colors
        self.bright_is_bold = bright_is_bold
        self.has_underline = has_underline

    def set_input_timeouts(self, *args: typing.Any) -> None:
        pass

    def reset_default_terminal_palette(self, *args: typing.Any) -> None:
        pass

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Create an html fragment from the render object.
        Append it to HtmlGenerator.fragments list.
        """
        # collect output in l
        lines = []

        _cols, rows = size

        if canvas.rows() != rows:
            raise ValueError(rows)

        if canvas.cursor is not None:
            cx, cy = canvas.cursor
        else:
            cx = cy = None

        for y, row in enumerate(canvas.content()):
            col = 0

            for a, _cs, run in row:
                t_run = run.decode(get_encoding()).translate(_trans_table)
                if isinstance(a, AttrSpec):
                    aspec = a
                else:
                    aspec = self._palette[a][{1: 1, 16: 0, 88: 2, 256: 3}[self.colors]]

                if y == cy and col <= cx:
                    run_width = str_util.calc_width(t_run, 0, len(t_run))
                    if col + run_width > cx:
                        lines.append(html_span(t_run, aspec, cx - col))
                    else:
                        lines.append(html_span(t_run, aspec))
                    col += run_width
                else:
                    lines.append(html_span(t_run, aspec))

            lines.append("\n")

        # add the fragment to the list
        self.fragments.append(f"<pre>{''.join(lines)}</pre>")

    def get_cols_rows(self):
        """Return the next screen size in HtmlGenerator.sizes."""
        if not self.sizes:
            raise HtmlGeneratorSimulationError("Ran out of screen sizes to return!")
        return self.sizes.pop(0)

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> list[str]: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[list[str], list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> list[str] | tuple[list[str], list[int]]:
        """Return the next list of keypresses in HtmlGenerator.keys."""
        if not self.keys:
            raise ExitMainLoop()
        if raw_keys:
            return (self.keys.pop(0), [])
        return self.keys.pop(0)


_default_aspec = AttrSpec(_default_foreground, _default_background)
(_d_fg_r, _d_fg_g, _d_fg_b, _d_bg_r, _d_bg_g, _d_bg_b) = _default_aspec.get_rgb_values()


def html_span(s: str, aspec: AttrSpec, cursor: int = -1) -> str:
    fg_r, fg_g, fg_b, bg_r, bg_g, bg_b = aspec.get_rgb_values()
    # use real colours instead of default fg/bg
    if fg_r is None:
        fg_r, fg_g, fg_b = _d_fg_r, _d_fg_g, _d_fg_b
    if bg_r is None:
        bg_r, bg_g, bg_b = _d_bg_r, _d_bg_g, _d_bg_b
    html_fg = f"#{fg_r:02x}{fg_g:02x}{fg_b:02x}"
    html_bg = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
    if aspec.standout:
        html_fg, html_bg = html_bg, html_fg
    extra = ";text-decoration:underline" * aspec.underline + ";font-weight:bold" * aspec.bold

    def _span(fg: str, bg: str, string: str) -> str:
        if not s:
            return ""
        return f'<span style="color:{fg};background:{bg}{extra}">{html.escape(string)}</span>'

    if cursor >= 0:
        c_off, _ign = str_util.calc_text_pos(s, 0, len(s), cursor)
        c2_off = str_util.move_next_char(s, c_off, len(s))
        return (
            _span(html_fg, html_bg, s[:c_off])
            + _span(html_bg, html_fg, s[c_off:c2_off])
            + _span(html_fg, html_bg, s[c2_off:])
        )

    return _span(html_fg, html_bg, s)


def screenshot_init(sizes: list[tuple[int, int]], keys: list[list[str]]) -> None:
    """
    Replace curses_display.Screen and raw_display.Screen class with
    HtmlGenerator.

    Call this function before executing an application that uses
    curses_display.Screen to have that code use HtmlGenerator instead.

    sizes -- list of ( columns, rows ) tuples to be returned by each call
             to HtmlGenerator.get_cols_rows()
    keys -- list of lists of keys to be returned by each call to
            HtmlGenerator.get_input()

    Lists of keys may include "window resize" to force the application to
    call get_cols_rows and read a new screen size.

    For example, the following call will prepare an application to:
     1. start in 80x25 with its first call to get_cols_rows()
     2. take a screenshot when it calls draw_screen(..)
     3. simulate 5 "down" keys from get_input()
     4. take a screenshot when it calls draw_screen(..)
     5. simulate keys "a", "b", "c" and a "window resize"
     6. resize to 20x10 on its second call to get_cols_rows()
     7. take a screenshot when it calls draw_screen(..)
     8. simulate a "Q" keypress to quit the application

    screenshot_init( [ (80,25), (20,10) ],
        [ ["down"]*5, ["a","b","c","window resize"], ["Q"] ] )
    """
    for row, col in sizes:
        if not isinstance(row, int):
            raise TypeError(f"sizes must be list[tuple[int, int]], with values >0 : {row!r}")
        if row <= 0:
            raise ValueError(f"sizes must be list[tuple[int, int]], with values >0 : {row!r}")
        if not isinstance(col, int):
            raise TypeError(f"sizes must be list[tuple[int, int]], with values >0 : {col!r}")
        if col <= 0:
            raise ValueError(f"sizes must be list[tuple[int, int]], with values >0 : {col!r}")

    for line in keys:
        if not isinstance(line, list):
            raise TypeError(f"keys must be list[list[str]]: {line!r}")
        for k in line:
            if not isinstance(k, str):
                raise TypeError(f"keys must be list[list[str]]: {k!r}")

    from . import curses, raw

    curses.Screen = HtmlGenerator
    raw.Screen = HtmlGenerator

    HtmlGenerator.sizes = sizes
    HtmlGenerator.keys = keys


def screenshot_collect() -> list[str]:
    """Return screenshots as a list of HTML fragments."""
    fragments, HtmlGenerator.fragments = HtmlGenerator.fragments, []
    return fragments
