"""Type checker fixture for the Tabs widget.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid
    from urwid.command_map import Command

    def tabs(edit: urwid.Edit) -> None:
        """Accept markup and widgets as labels, and type the contents as (body, label) pairs."""
        widget = urwid.Tabs([("Log", urwid.Text("log")), (urwid.Text("Edit"), edit)], bar_position="bottom")
        assert_type(widget.focus, urwid.widget.AbstractWidget | None)
        assert_type(widget.contents[0], tuple[urwid.widget.AbstractWidget, urwid.widget.AbstractWidget])
        assert_type(widget.focus_position, int)
        assert_type(urwid.Tabs.options("Log"), urwid.Text)
        assert_type(urwid.Tabs.options(edit), urwid.Edit)
        widget.contents.append((edit, urwid.Tabs.options(("bold", "New"))))
        assert_type(Command.NEXT_TAB, typing.Literal[Command.NEXT_TAB])
        assert_type(widget.overflow_markers, tuple[str, str] | None)
        widget.overflow_markers = (urwid.Tabs.Symbols.GUILLEMET_LEFT, urwid.Tabs.Symbols.GUILLEMET_RIGHT)
        assert_type(widget.underline, tuple[str, str] | None)
        widget.underline = (urwid.Tabs.Symbols.LINE_ASCII, urwid.Tabs.Symbols.LINE_ASCII_DOUBLE)
