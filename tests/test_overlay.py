from __future__ import annotations

import unittest

import urwid


class OverlayTest(unittest.TestCase):
    def test_old_params(self):
        o1 = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            ("fixed left", 5),
            ("fixed right", 4),
            ("fixed top", 3),
            ("fixed bottom", 2),
        )
        self.assertEqual(
            o1.contents[1][1],
            ("left", None, "relative", 100, None, 5, 4, "top", None, "relative", 100, None, 3, 2),
        )
        o2 = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            ("fixed right", 5),
            ("fixed left", 4),
            ("fixed bottom", 3),
            ("fixed top", 2),
        )
        self.assertEqual(
            o2.contents[1][1],
            ("right", None, "relative", 100, None, 4, 5, "bottom", None, "relative", 100, None, 2, 3),
        )

    def test_get_cursor_coords(self):
        self.assertEqual(
            urwid.Overlay(
                urwid.Filler(urwid.Edit()),
                urwid.SolidFill("B"),
                "right",
                1,
                "bottom",
                1,
            ).get_cursor_coords((2, 2)),
            (1, 1),
        )

    def test_length(self):
        ovl = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            "center",
            ("relative", 20),
            "middle",
            ("relative", 20),
        )
        self.assertEqual(2, len(ovl))
        self.assertEqual(2, len(ovl.contents))

    def test_common(self):
        s1 = urwid.SolidFill("1")
        s2 = urwid.SolidFill("2")
        o = urwid.Overlay(s1, s2, "center", ("relative", 50), "middle", ("relative", 50))
        self.assertEqual(o.focus, s1)
        self.assertEqual(o.focus_position, 1)
        self.assertRaises(IndexError, lambda: setattr(o, "focus_position", None))
        self.assertRaises(IndexError, lambda: setattr(o, "focus_position", 2))

        self.assertEqual(o.contents[0], (s2, urwid.Overlay._DEFAULT_BOTTOM_OPTIONS))
        self.assertEqual(
            o.contents[1],
            (s1, ("center", None, "relative", 50, None, 0, 0, "middle", None, "relative", 50, None, 0, 0)),
        )
