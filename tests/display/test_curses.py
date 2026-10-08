"""Tests for the curses display module."""

from __future__ import annotations

import unittest
from unittest import mock

import urwid

try:
    from urwid.display import curses as curses_display
except ImportError:  # no stdlib curses on this platform, e.g. Windows and GraalPy
    curses_display = None


@unittest.skipIf(curses_display is None, "the curses module is not available")
class CursesSetAttrTest(unittest.TestCase):
    """Tests for the curses attribute of a canvas run, set through BaseScreen.resolve_attr."""

    def setUp(self) -> None:
        """Make an unstarted screen with a mocked window and color pairs numbered from the pair index."""
        self.screen = curses_display.Screen()
        self.screen.s = mock.Mock()
        self.screen.has_color = True
        patcher = mock.patch.object(curses_display.curses, "color_pair", side_effect=lambda number: number << 8)
        patcher.start()
        self.addCleanup(patcher.stop)

    def attr_of(self, attr: object) -> int:
        """Return the value the screen passes to ``attrset`` for *attr*."""
        self.screen._setattr(attr)
        return self.screen.s.attrset.call_args.args[0]

    def test_attributes_resolved_through_the_palette(self) -> None:
        self.screen.register_palette(
            [(None, "default", "dark blue"), ("red_fg", "dark red", "inherit"), ("green_bg", "inherit", "dark green")]
        )
        # pair number is bg * 8 + 7 - fg; a default foreground counts as 7
        for label, attr, pair in (
            ("no attribute uses the None entry", None, 4 * 8),
            ("fg-only name over the None entry", "red_fg", 4 * 8 + 6),
            ("layered attribute", urwid.LayeredAttr("red_fg", "green_bg"), 2 * 8 + 6),
        ):
            with self.subTest(label):
                self.assertEqual(pair << 8, self.attr_of(attr))
