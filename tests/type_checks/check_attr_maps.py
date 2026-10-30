"""Type checker fixture for attribute maps given in any form AttrMap takes.

mypy and Pyrefly check this module; nothing in it runs.
The line carrying an ignore pins the rejection of a value that is neither an attribute nor a mapping:
once it is accepted, the ignore is unused and mypy's warn_unused_ignores fails the check.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import types
    from collections.abc import Hashable
    from typing import assert_type

    import urwid

    def attr_map_forms(text: urwid.Text, plain: dict[str, str], frozen: types.MappingProxyType[str, str]) -> None:
        """Accept an attribute map as a dict, a Mapping, a single attribute or None."""
        urwid.AttrMap(text, {"a": "b"}, focus_map={"a": "c"})
        urwid.AttrMap(text, plain, plain)
        urwid.AttrMap(text, "attr", "focus attr")
        attr_map = urwid.AttrMap(text, None)
        attr_map.set_attr_map(plain)
        attr_map.set_attr_map(frozen)
        attr_map.set_focus_map({"a": "c"})
        attr_map.set_focus_map(None)
        attr_map.attr_map = plain
        urwid.DropDown(["x", "y"], attr_map=plain, focus_map={"a": "b"})
        urwid.AttrMap(text, ["not", "hashable"])  # type: ignore[arg-type]

    def unfocused_focus_attr_forms(cells: list[urwid.Text], plain: dict[str, str]) -> None:
        """Accept the containers' unfocused focus map in the same forms, and type what it returns."""
        pile = urwid.Pile(cells, unfocused_focus_attr=plain)
        pile.unfocused_focus_attr = {"a": "b"}
        pile.unfocused_focus_attr = "attr"
        pile.unfocused_focus_attr = None
        assert_type(urwid.Pile(cells).unfocused_focus_attr, dict[Hashable, Hashable] | None)
        urwid.Columns(cells, unfocused_focus_attr="attr")
        urwid.ListBox(cells, unfocused_focus_attr=plain)
        urwid.GridFlow(cells, 1, 0, 0, "left", unfocused_focus_attr={"a": "b"})
