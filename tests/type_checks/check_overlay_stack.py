"""Type checker fixture for the OverlayStack widget.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def overlay_stack() -> None:
        """Type the open() and close() calls and the properties."""
        stack = urwid.OverlayStack(urwid.Frame(urwid.SolidFill()), close_on_menu=True)
        dialog = urwid.LineBox(urwid.Text("saved"))
        stack.open(dialog, width=20, close_on_click_outside=True, on_close=print)
        stack.open(urwid.Text("text"), align=urwid.RIGHT, valign=("relative", 10), height="pack")
        assert_type(stack.close("result"), bool)
        assert_type(stack.close(widget=dialog), bool)
        assert_type(stack.levels, tuple[urwid.Widget, ...])
        assert_type(stack.depth, int)
        assert_type(stack.base, urwid.Widget)
        assert_type(stack.close_on_menu, bool)
        stack.base = urwid.SolidFill(".")
        urwid.MainLoop(stack)
