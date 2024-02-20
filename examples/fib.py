#!/usr/bin/env python
#
# Urwid example fibonacci sequence viewer / unbounded data demo
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
Urwid example fibonacci sequence viewer / unbounded data demo

Features:
- custom list walker class for browsing infinite set
- custom wrap mode "numeric" for wrapping numbers to right and bottom
"""

from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


class FibonacciWalker(urwid.ListWalker):
    """ListWalker-compatible class for browsing fibonacci set.

    positions returned are (value at position-1, value at position) tuples.
    """

    def __init__(self) -> None:
        self.focus = (0, 1)
        self.numeric_layout = NumericLayout()

    def _get_at_pos(self, pos: tuple[int, int]) -> tuple[urwid.Text, tuple[int, int]]:
        """Return a widget and the position passed."""
        return urwid.Text(f"{pos[1]:d}", layout=self.numeric_layout), pos

    def get_focus(self) -> tuple[urwid.Text, tuple[int, int]]:
        return self._get_at_pos(self.focus)

    def set_focus(self, focus) -> None:
        self.focus = focus
        self._modified()

    def get_next(self, position) -> tuple[urwid.Text, tuple[int, int]]:
        a, b = position
        focus = b, a + b
        return self._get_at_pos(focus)

    def get_prev(self, position) -> tuple[urwid.Text, tuple[int, int]]:
        a, b = position
        focus = b - a, a
        return self._get_at_pos(focus)


def main() -> None:
    palette = [
        ("body", "black", "dark cyan", "standout"),
        ("foot", "light gray", "black"),
        ("key", "light cyan", "black", "underline"),
        (
            "title",
            "white",
            "black",
        ),
    ]

    footer_text = [
        ("title", "Fibonacci Set Viewer"),
        "    ",
        ("key", "UP"),
        ", ",
        ("key", "DOWN"),
        ", ",
        ("key", "PAGE UP"),
        " and ",
        ("key", "PAGE DOWN"),
        " move view  ",
        ("key", "Q"),
        " exits",
    ]

    def exit_on_q(key: str | tuple[str, int, int, int]) -> None:
        if key in {"q", "Q"}:
            raise urwid.ExitMainLoop()

    listbox = urwid.ListBox(FibonacciWalker())
    footer = urwid.AttrMap(urwid.Text(footer_text), "foot")
    view = urwid.Frame(urwid.AttrMap(listbox, "body"), footer=footer)
    loop = urwid.MainLoop(view, palette, unhandled_input=exit_on_q)
    loop.run()


class NumericLayout(urwid.TextLayout):
    """
    TextLayout class for bottom-right aligned numbers
    """

    def layout(
        self,
        text: str | bytes,
        width: int,
        align: Literal["left", "center", "right"] | urwid.Align,
        wrap: Literal["any", "space", "clip", "ellipsis"] | urwid.WrapMode,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
        """
        Return layout structure for right justified numbers.
        """
        lt = len(text)
        r = lt % width  # remaining segment not full width wide
        if r:
            return [
                [(width - r, None), (r, 0, r)],  # right-align the remaining segment on 1st line
                *([(width, x, x + width)] for x in range(r, lt, width)),  # fill the rest of the lines
            ]

        return [[(width, x, x + width)] for x in range(0, lt, width)]


if __name__ == "__main__":
    main()
