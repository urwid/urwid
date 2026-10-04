from __future__ import annotations

import sys
import unittest
from unittest import mock

IS_WINDOWS = sys.platform == "win32"

if not IS_WINDOWS:
    from urwid.display import curses


@unittest.skipIf(IS_WINDOWS, "Tests the POSIX curses halfdelay implementation")
class TestInputTimeouts(unittest.TestCase):
    def setUp(self):
        self.screen = curses.Screen()
        self.screen.s = mock.Mock()
        self.elapsed = 0
        self.delay = None
        self.halfdelay = self.enterContext(mock.patch.object(curses.curses, "halfdelay", side_effect=self.set_delay))
        self.cbreak = self.enterContext(mock.patch.object(curses.curses, "cbreak"))

    def set_delay(self, tenths):
        if not 1 <= tenths <= 255:
            raise OverflowError("halfdelay is limited to 255 tenths")
        self.delay = tenths

    def timeout(self):
        self.elapsed += self.delay
        return -1

    def test_finite_waits_expire_after_the_requested_duration(self):
        for tenths in (1, 255, 256, 510, 511, 1000):
            with self.subTest(tenths=tenths):
                self.elapsed = 0
                self.screen.s.getch.side_effect = self.timeout
                self.assertEqual(self.screen._getch(tenths), -1)
                self.assertEqual(self.elapsed, tenths)

    def test_input_interrupts_a_long_wait(self):
        for preceding_timeouts in (0, 1):
            with self.subTest(preceding_timeouts=preceding_timeouts):
                self.elapsed = 0
                calls = 0

                def getch():
                    nonlocal calls
                    calls += 1
                    return self.timeout() if calls <= preceding_timeouts else ord("q")

                self.screen.s.getch.side_effect = getch
                self.assertEqual(self.screen._getch(1000), ord("q"))
                self.assertLess(self.elapsed, 1000)
                self.assertEqual(calls, preceding_timeouts + 1)

    def test_zero_wait_is_nonblocking(self):
        self.screen.s.getch.return_value = -1
        self.assertEqual(self.screen._getch(0), -1)
        self.screen.s.nodelay.assert_called_once_with(True)
        self.halfdelay.assert_not_called()

    def test_none_wait_is_blocking(self):
        self.screen.s.getch.return_value = ord("q")
        self.assertEqual(self.screen._getch(None), ord("q"))
        self.screen.s.nodelay.assert_called_once_with(False)
        self.cbreak.assert_called_once_with()
        self.halfdelay.assert_not_called()
