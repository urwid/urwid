"""Tests for the console coverage tables in the docstrings of the symbol sets."""

from __future__ import annotations

import re
import unittest

import urwid

# One row of a console coverage table: the member name, then its symbol or, for a look-alike glyph, its code point.
_ROW = re.compile(r"^\s*``(?P<name>[A-Z0-9_]+)``\s+(?P<symbol>\S+)\s")


class SymbolTablesTest(unittest.TestCase):
    """Coverage tables of the symbol sets."""

    def test_tables_list_every_non_ascii_member(self) -> None:
        """Every non-ASCII member of a symbol set has a row with its own symbol in the set's coverage table.

        Applications built on urwid read the table to pick symbols for the Linux and Windows consoles,
        so a member added without a row has to be checked against the console fonts again by each of them.
        """
        sets: tuple[tuple[type, dict[str, str]], ...] = (
            (type(urwid.widget.constants.SHADE_SYMBOLS), urwid.widget.constants.SHADE_SYMBOLS._asdict()),
            *(
                (cls, {member.name: member.value for member in cls})
                for cls in (
                    urwid.Divider.Symbols,
                    urwid.Tabs.Symbols,
                    urwid.ScrollBar.Symbols,
                    urwid.TreeWidget.Symbols,
                    urwid.CheckBox.Symbols,
                )
            ),
        )
        for cls, members in sets:
            with self.subTest(cls.__qualname__):
                matches = [match for match in map(_ROW.match, (cls.__doc__ or "").splitlines()) if match]
                rows = {match["name"]: match["symbol"] for match in matches}
                non_ascii = {name: value for name, value in members.items() if not value.isascii()}
                self.assertCountEqual(non_ascii, [match["name"] for match in matches])
                for name, value in non_ascii.items():
                    self.assertIn(rows[name], {value, f"U+{ord(value):04X}"}, name)
