from __future__ import annotations

import unittest

import urwid
from urwid.util import get_encoding


class DividerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_default_and_div_char(self) -> None:
        blank = urwid.Divider()
        dashed = urwid.Divider("-")

        self.assertEqual(frozenset((urwid.FLOW,)), blank.sizing())
        self.assertEqual(1, blank.rows((10,)))
        self.assertEqual([b"          "], blank.render((10,)).text)
        self.assertEqual([b"-----"], dashed.render((5,)).text)

    def test_symbols_and_vertical_padding(self) -> None:
        divider = urwid.Divider(div_char=urwid.Divider.Symbols.LIGHT_HL, top=1, bottom=1)

        self.assertEqual("─", urwid.Divider.Symbols.LIGHT_HL)
        self.assertEqual(3, divider.rows((4,)))
        self.assertEqual(
            ["    ", "────", "    "],
            [line.decode("utf-8") for line in divider.render((4,)).text],
        )
