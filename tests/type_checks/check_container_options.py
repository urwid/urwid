"""Type checker fixture for Pile.options() and Columns.options() feeding the containers' contents.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import Literal, assert_type

    import urwid

    def pile_options(pile: urwid.Pile, kind: urwid.WHSettings) -> None:
        assert_type(pile.options(urwid.PACK), tuple[Literal[urwid.WHSettings.PACK], None])
        assert_type(pile.options("given", 3), tuple[Literal[urwid.WHSettings.GIVEN], int])
        assert_type(pile.options(), tuple[Literal[urwid.WHSettings.WEIGHT], int | float])
        assert_type(
            pile.options(kind),
            tuple[Literal[urwid.WHSettings.PACK], None]
            | tuple[Literal[urwid.WHSettings.GIVEN], int]
            | tuple[Literal[urwid.WHSettings.WEIGHT], int | float],
        )
        pile.contents.insert(0, (urwid.Edit(), pile.options(urwid.PACK)))
        pile.contents.append((urwid.SolidFill(), pile.options()))
        pile.contents[0] = (urwid.AttrMap(urwid.Text(""), None), pile.options("pack"))

    def columns_options(columns: urwid.Columns) -> None:
        assert_type(columns.options(urwid.PACK), tuple[Literal[urwid.WHSettings.PACK], None, bool])
        assert_type(columns.options("given", 3, True), tuple[Literal[urwid.WHSettings.GIVEN], int, bool])
        assert_type(columns.options(), tuple[Literal[urwid.WHSettings.WEIGHT], int | float, bool])
        columns.contents.insert(0, (urwid.Edit(), columns.options(urwid.PACK)))
        columns.contents.append((urwid.Text(""), columns.options()))
