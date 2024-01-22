from __future__ import annotations

import unittest

import urwid


class TestRawDisplay(unittest.TestCase):
    def test_attrspec_to_escape(self):
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        a2e = s._attrspec_to_escape
        self.assertEqual("\x1b[0;33;42m", a2e(s.AttrSpec("brown", "dark green")))
        self.assertEqual("\x1b[0;38;5;229;4;48;5;164m", a2e(s.AttrSpec("#fea,underline", "#d0d")))
