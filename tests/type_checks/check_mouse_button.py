"""Type checker fixture for MouseButton.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def mouse_button(widget: urwid.Widget) -> None:
        """Pass a member where a mouse event takes an int button, and type a conversion."""
        widget.mouse_event((5,), "mouse press", urwid.MouseButton.LEFT, 0, 0, True)
        urwid.testing.click(widget, (5,), 0, 0, button=urwid.MouseButton.RIGHT)
        assert_type(urwid.MouseButton(10), urwid.MouseButton)
