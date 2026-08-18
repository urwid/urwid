from __future__ import annotations

import unittest

import urwid
from urwid.util import set_temporary_encoding


class TestRawDisplay(unittest.TestCase):
    def test_attrspec_to_escape(self):
        s = urwid.display.raw.Screen()
        s.set_terminal_properties(colors=256)
        a2e = s._attrspec_to_escape
        self.assertEqual("\x1b[0;33;42m", a2e(s.AttrSpec("brown", "dark green")))
        self.assertEqual("\x1b[0;38;5;229;4;48;5;164m", a2e(s.AttrSpec("#fea,underline", "#d0d")))

    def test_last_row_without_preceding_segment(self):
        """A last row holding a single grapheme has no character to slide back."""
        s = urwid.display.raw.Screen()
        row = [(None, None, "日".encode())]

        self.assertEqual((row, 0, None), s._last_row(row))

    def test_draw_screen_two_columns_wide_characters(self):
        """Drawing double width text on a two column screen used to raise IndexError."""
        s = urwid.display.raw.Screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s._started = True

        with set_temporary_encoding("utf-8"):
            canvas = urwid.Text("日本語").render((2,))
            s.draw_screen((2, canvas.rows()), canvas)

        self.assertEqual(3, canvas.rows())
        self.assertIn("語", "".join(written))
