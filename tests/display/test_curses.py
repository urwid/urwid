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

    def test_hyperlink_is_ignored(self) -> None:
        linked = urwid.AttrSpec("dark red,bold", "dark blue", hyperlink="https://urwid.org")

        self.assertEqual(self.attr_of(linked.style_only()), self.attr_of(linked))
        self.assertEqual([linked.style_only()], list(self.screen._curses_attr_cache))


@unittest.skipIf(curses_display is None or curses_display.IS_WINDOWS, "halfdelay waits are POSIX curses only")
class CursesInputTimeoutTest(unittest.TestCase):
    """Tests for the halfdelay waits of ``_getch``, which curses limits to 255 tenths each."""

    def setUp(self) -> None:
        """Make an unstarted screen whose ``getch`` timeouts add the current halfdelay to ``elapsed``."""
        self.screen = curses_display.Screen()
        self.screen.s = mock.Mock()
        self.elapsed = 0
        self.delay = 0
        self.halfdelay = self.enterContext(
            mock.patch.object(curses_display.curses, "halfdelay", side_effect=self.set_delay)
        )
        self.cbreak = self.enterContext(mock.patch.object(curses_display.curses, "cbreak"))

    def set_delay(self, tenths: int) -> None:
        """Record the halfdelay value, rejecting the values real curses rejects."""
        if not 1 <= tenths <= 255:
            raise OverflowError("halfdelay is limited to 255 tenths")
        self.delay = tenths

    def timeout(self) -> int:
        """Let the current halfdelay expire with no input."""
        self.elapsed += self.delay
        return -1

    def test_finite_waits_expire_after_the_requested_duration(self) -> None:
        for tenths in (1, 255, 256, 510, 511, 1000):
            with self.subTest(tenths=tenths):
                self.elapsed = 0
                self.screen.s.getch.side_effect = self.timeout
                self.assertEqual(-1, self.screen._getch(tenths))
                self.assertEqual(tenths, self.elapsed)

    def test_input_interrupts_a_long_wait(self) -> None:
        for preceding_timeouts in (0, 1):
            with self.subTest(preceding_timeouts=preceding_timeouts):
                self.elapsed = 0
                calls = 0

                def getch() -> int:
                    nonlocal calls
                    calls += 1
                    return self.timeout() if calls <= preceding_timeouts else ord("q")

                self.screen.s.getch.side_effect = getch
                self.assertEqual(ord("q"), self.screen._getch(1000))
                self.assertLess(self.elapsed, 1000)
                self.assertEqual(preceding_timeouts + 1, calls)

    def test_zero_wait_is_nonblocking(self) -> None:
        self.screen.s.getch.return_value = -1
        self.assertEqual(-1, self.screen._getch(0))
        self.screen.s.nodelay.assert_called_once_with(True)
        self.halfdelay.assert_not_called()

    def test_none_wait_is_blocking(self) -> None:
        self.screen.s.getch.return_value = ord("q")
        self.assertEqual(ord("q"), self.screen._getch(None))
        self.screen.s.nodelay.assert_called_once_with(False)
        self.cbreak.assert_called_once_with()
        self.halfdelay.assert_not_called()
