#!/usr/bin/env python
#
# Urwid example lazy text editor suitable for tabbed and format=flowed text
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

"""
Urwid example lazy text editor suitable for tabbed and flowing text

Features:
- custom list walker for lazily loading text file

Usage:
edit.py <filename>

"""

from __future__ import annotations

import sys
import typing

import urwid


class LineWalker(urwid.ListWalker):
    """ListWalker-compatible class for lazily reading file contents."""

    def __init__(self, name: str) -> None:
        # do not overcomplicate example
        self.file = open(name, encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
        self.lines = []
        self.focus = 0

    def __del__(self) -> None:
        self.file.close()

    def get_focus(self):
        return self._get_at_pos(self.focus)

    def set_focus(self, focus) -> None:
        self.focus = focus
        self._modified()

    def get_next(self, position: int) -> tuple[urwid.Edit, int] | tuple[None, None]:
        return self._get_at_pos(position + 1)

    def get_prev(self, position: int) -> tuple[urwid.Edit, int] | tuple[None, None]:
        return self._get_at_pos(position - 1)

    def read_next_line(self) -> str:
        """Read another line from the file."""

        next_line = self.file.readline()

        if not next_line or next_line[-1:] != "\n":
            # no newline on last line of file
            self.file = None
        else:
            # trim newline characters
            next_line = next_line[:-1]

        expanded = next_line.expandtabs()

        edit = urwid.Edit("", expanded, allow_tab=True)
        edit.edit_pos = 0
        edit.original_text = next_line
        self.lines.append(edit)

        return next_line

    def _get_at_pos(self, pos: int) -> tuple[urwid.Edit, int] | tuple[None, None]:
        """Return a widget for the line number passed."""

        if pos < 0:
            # line 0 is the start of the file, no more above
            return None, None

        if len(self.lines) > pos:
            # we have that line so return it
            return self.lines[pos], pos

        if self.file is None:
            # file is closed, so there are no more lines
            return None, None

        assert pos == len(self.lines), "out of order request?"  # noqa: S101  # "assert" is OK in examples

        self.read_next_line()

        return self.lines[-1], pos

    def split_focus(self) -> None:
        """Divide the focus edit widget at the cursor location."""

        focus = self.lines[self.focus]
        pos = focus.edit_pos
        edit = urwid.Edit("", focus.edit_text[pos:], allow_tab=True)
        edit.original_text = ""
        focus.set_edit_text(focus.edit_text[:pos])
        edit.edit_pos = 0
        self.lines.insert(self.focus + 1, edit)

    def combine_focus_with_prev(self) -> None:
        """Combine the focus edit widget with the one above."""

        above, _ = self.get_prev(self.focus)
        if above is None:
            # already at the top
            return

        focus = self.lines[self.focus]
        above.set_edit_pos(len(above.edit_text))
        above.set_edit_text(above.edit_text + focus.edit_text)
        del self.lines[self.focus]
        self.focus -= 1

    def combine_focus_with_next(self) -> None:
        """Combine the focus edit widget with the one below."""

        below, _ = self.get_next(self.focus)
        if below is None:
            # already at bottom
            return

        focus = self.lines[self.focus]
        focus.set_edit_text(focus.edit_text + below.edit_text)
        del self.lines[self.focus + 1]


class EditDisplay:
    palette: typing.ClassVar[list[tuple[str, str, str, ...]]] = [
        ("body", "default", "default"),
        ("foot", "dark cyan", "dark blue", "bold"),
        ("key", "light cyan", "dark blue", "underline"),
    ]

    footer_text = (
        "foot",
        [
            "Text Editor    ",
            ("key", "F5"),
            " save  ",
            ("key", "F8"),
            " quit",
        ],
    )

    def __init__(self, name: str) -> None:
        self.save_name = name
        self.walker = LineWalker(name)
        self.listbox = urwid.ListBox(self.walker)
        self.footer = urwid.AttrMap(urwid.Text(self.footer_text), "foot")
        self.view = urwid.Frame(urwid.AttrMap(self.listbox, "body"), footer=self.footer)

    def main(self) -> None:
        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_keypress)
        self.loop.run()

    def unhandled_keypress(self, k: str | tuple[str, int, int, int]) -> bool | None:
        """Last resort for keypresses."""

        if k == "f5":
            self.save_file()
        elif k == "f8":
            raise urwid.ExitMainLoop()
        elif k == "delete":
            # delete at end of line
            self.walker.combine_focus_with_next()
        elif k == "backspace":
            # backspace at beginning of line
            self.walker.combine_focus_with_prev()
        elif k == "enter":
            # start new line
            self.walker.split_focus()
            # move the cursor to the new line and reset pref_col
            self.loop.process_input(["down", "home"])
        elif k == "right":
            w, pos = self.walker.get_focus()
            w, pos = self.walker.get_next(pos)
            if w:
                self.listbox.set_focus(pos, "above")
                self.loop.process_input(["home"])
        elif k == "left":
            w, pos = self.walker.get_focus()
            w, pos = self.walker.get_prev(pos)
            if w:
                self.listbox.set_focus(pos, "below")
                self.loop.process_input(["end"])
        else:
            return None
        return True

    def save_file(self) -> None:
        """Write the file out to disk."""

        lines = []
        walk = self.walker
        for edit in walk.lines:
            # collect the text already stored in edit widgets
            if edit.original_text.expandtabs() == edit.edit_text:
                lines.append(edit.original_text)
            else:
                lines.append(re_tab(edit.edit_text))

        # then the rest
        while walk.file is not None:
            lines.append(walk.read_next_line())

        # write back to disk
        with open(self.save_name, "w", encoding="utf-8") as outfile:
            prefix = ""
            for line in lines:
                outfile.write(prefix + line)
                prefix = "\n"


def re_tab(s) -> str:
    """Return a tabbed string from an expanded one."""
    line = []
    p = 0
    for i in range(8, len(s), 8):
        if s[i - 2 : i] == "  ":
            # collapse two or more spaces into a tab
            line.append(f"{s[p:i].rstrip()}\t")
            p = i

    if p == 0:
        return s

    line.append(s[p:])
    return "".join(line)


def main() -> None:
    try:
        name = sys.argv[1]
        # do not overcomplicate example
        assert open(name, "ab")  # noqa: SIM115,S101  # pylint: disable=consider-using-with
    except OSError:
        sys.stderr.write(__doc__)
        return
    EditDisplay(name).main()


if __name__ == "__main__":
    main()
