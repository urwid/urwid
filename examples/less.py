#!/usr/bin/env python3
#
# Urwid example: a pager that reads a text file only as far as it is shown
#    Copyright (C) 2004-2009  Ian Ward
#    Copyright (C) 2026 Urwid developers
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
#     "urwid>=5.3",
# ]
# ///
"""Example: a pager that reads a text file only as far as it is shown.

A custom list walker reads the next line from the file the first time the list box asks for it,
so even a huge file opens at once.

Keys:

- the arrows, :kbd:`page up` and :kbd:`page down` scroll;
- a number followed by :kbd:`g` goes to that line, and :kbd:`g` alone to the first line;
- :kbd:`esc` forgets a number typed so far;
- :kbd:`q` quits.

The file is read as UTF-8, with any bytes that are not UTF-8 shown as replacement characters.
"""

from __future__ import annotations

import argparse
import pathlib
import string
import sys
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

PALETTE: typing.Final = (("status", "white", "dark blue"),)
# Most digits a line number may have; more are ignored.
MAX_DIGITS: typing.Final = 12


class LineWalker(urwid.ListWalker[int, urwid.Text]):
    """List walker over the lines of an open text file.

    Each line is read the first time the list box asks for it.
    Lines are read in order and kept as text, so moving back up never reads the file again.
    A widget is made for a line only when the list box asks for it, so a long file costs little more than its text.
    """

    def __init__(self, file: typing.TextIO) -> None:
        """Walk the lines of *file*.

        The file stays open while the walker is in use, and no line is read yet.
        """
        # None once the end of the file has been read.
        self._file: typing.TextIO | None = file
        # The text of the lines read so far, tabs expanded.
        self.lines: list[str] = []
        self.focus = 0

    def _read_to(self, position: int) -> bool:
        """Read lines until the one at *position* is loaded.

        :returns: whether the file has a line at *position*.
        """
        while self._file is not None and len(self.lines) <= position:
            line = self._file.readline()
            if not line:
                self._file = None
                break
            self.lines.append(line.rstrip("\n").expandtabs())
        return position < len(self.lines)

    def _at(self, position: int) -> tuple[urwid.Text, int] | tuple[None, None]:
        """Return the widget of the line at *position* and the position, or ``None`` twice past either end."""
        if position < 0 or not self._read_to(position):
            return None, None
        return urwid.Text(self.lines[position]), position

    def get_focus(self) -> tuple[urwid.Text, int] | tuple[None, None]:
        """Return the widget and position of the focus line."""
        return self._at(self.focus)

    def set_focus(self, position: int) -> None:
        """Move the focus to the line at *position*."""
        self.focus = position
        self._modified()

    def get_next(self, position: int) -> tuple[urwid.Text, int] | tuple[None, None]:
        """Return the widget and position of the line after *position*."""
        return self._at(position + 1)

    def get_prev(self, position: int) -> tuple[urwid.Text, int] | tuple[None, None]:
        """Return the widget and position of the line before *position*."""
        return self._at(position - 1)

    def position_of(self, number: int) -> int | None:
        """Return the position of line *number*, counted from 1.

        Only the lines up to *number* are read.

        :returns: the position of the last line when the file is shorter, the first line for a number below 1,
            and ``None`` for an empty file.
        """
        self._read_to(max(number, 1) - 1)
        if not self.lines:
            return None
        return max(min(number, len(self.lines)) - 1, 0)


class Pager:
    """The pager screen: the lines of the file and a status line, with the keys the list box leaves unused."""

    __slots__ = ("__weakref__", "frame", "keys", "listbox", "number", "walker")

    def __init__(self, walker: LineWalker, name: str) -> None:
        """Show the lines of *walker*, with *name* on the status line."""
        self.walker = walker
        self.listbox: urwid.ListBox[int] = urwid.ListBox(walker)
        # The digits typed so far for a following "g".
        self.number = ""
        # The number typed so far and the keys, right of the file name, which is cut to fit.
        self.keys = urwid.Text("")
        status = urwid.Columns(
            [
                urwid.Text(name, wrap=urwid.WrapMode.ELLIPSIS),
                (urwid.PACK, self.keys),
            ],
            dividechars=2,
        )
        self.frame: urwid.Frame[urwid.ListBox[int], None, urwid.AttrMap[urwid.Columns]] = urwid.Frame(
            self.listbox,
            footer=urwid.AttrMap(status, "status"),
        )
        self.show_status()

    def show_status(self) -> None:
        """Show the number typed so far and the keys."""
        typed = f"{self.number}g  " if self.number else ""
        self.keys.set_text(f"{typed}<number>g: go to line, q: quit")

    def go_to(self, number: int) -> None:
        """Show line *number*, counted from 1, at the top.

        A file shorter than that shows its last line, and an empty file stays as it is.
        """
        position = self.walker.position_of(number)
        if position is not None:
            self.listbox.set_focus(position)
            self.listbox.set_focus_valign("top")

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Handle a key the list box did not use.

        :returns: ``True`` when the key was handled, ``None`` otherwise.
        :raises urwid.ExitMainLoop: on :kbd:`q`.
        """
        if not isinstance(key, str):
            return None
        if len(key) == 1 and key in string.digits:
            self.number = (self.number + key)[:MAX_DIGITS]
        elif key == "g":
            self.go_to(int(self.number or "1"))
            self.number = ""
        elif key == "esc":
            self.number = ""
        elif key == "q":
            raise urwid.ExitMainLoop
        else:
            return None
        self.show_status()
        return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Page through a text file.")
    parser.add_argument("file", type=pathlib.Path, help="the file to show")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pager and return the exit status."""
    args = parse_args(argv)
    try:
        file = args.file.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1
    with file:
        pager = Pager(LineWalker(file), str(args.file))
        urwid.MainLoop(pager.frame, PALETTE, unhandled_input=pager.unhandled_input).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
