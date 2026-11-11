"""Type checker fixture for the widgets ScrollBar accepts.

mypy and Pyrefly check this module; nothing in it runs.
The line carrying an ignore pins a checker-visible behaviour: once the behaviour changes, the ignore is unused and
mypy's warn_unused_ignores fails the check.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def decorated(listbox: urwid.ListBox[int]) -> None:
        """Accept a decoration of a box widget, and type the result with it."""
        assert_type(
            urwid.ScrollBar(urwid.AttrMap(listbox, "body")),
            urwid.ScrollBar[urwid.AttrMap[urwid.ListBox[int]]],
        )
        assert_type(
            urwid.ScrollBar(urwid.Padding(listbox, left=1)),
            urwid.ScrollBar[urwid.Padding[urwid.ListBox[int]]],
        )

    def not_a_box_widget(text: urwid.Text) -> None:
        """Reject a widget that is not a box widget."""
        urwid.ScrollBar(text)  # type: ignore[type-var]
