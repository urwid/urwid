"""Type checker fixture for the placeholder options of Edit.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def edit_options() -> None:
        """Accept the new options in their documented forms, and type what the properties return."""
        edit = urwid.Edit("Port: ", placeholder=("hint", "8080"), placeholder_grow=True)
        edit.placeholder = None
        edit.placeholder_grow = None
        assert_type(urwid.Edit().placeholder_grow, bool | None)
