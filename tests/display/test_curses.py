"""Tests for the curses display module."""

from __future__ import annotations

import errno
import unittest
from unittest import mock

import urwid
from urwid.display import escape

try:
    import termios
except ImportError:  # Windows has no termios
    termios = None

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

    def test_zero_wait_retries_cbreak_once(self) -> None:
        """Retry a failed ``cbreak`` once and raise its second failure.

        Once the terminal is gone, ``cbreak`` fails on every call.
        """
        self.screen.s.getch.return_value = -1
        self.cbreak.side_effect = [curses_display.curses.error, None]
        self.assertEqual(-1, self.screen._getch(0))
        self.assertEqual(2, self.cbreak.call_count)

        self.cbreak.reset_mock()
        # an iterator, not a list, so a regression to an unbounded retry ends with StopIteration instead of hanging
        self.cbreak.side_effect = iter([curses_display.curses.error] * 3)
        with self.assertRaises(curses_display.curses.error):
            self.screen._getch(0)
        self.assertEqual(2, self.cbreak.call_count)

    def test_none_wait_is_blocking(self) -> None:
        self.screen.s.getch.return_value = ord("q")
        self.assertEqual(ord("q"), self.screen._getch(None))
        self.screen.s.nodelay.assert_called_once_with(False)
        self.cbreak.assert_called_once_with()
        self.halfdelay.assert_not_called()


@unittest.skipIf(curses_display is None or curses_display.IS_WINDOWS, "termios modes are POSIX only")
class CursesStartTerminalModeTest(unittest.TestCase):
    """Tests for the line discipline flags that ``start()`` clears on the terminal input and ``stop()`` sets again."""

    def setUp(self) -> None:
        """Replace curses, the terminal check and termios, recording the calls that change the mode in order."""
        self.calls = mock.Mock()
        curses_error = curses_display.curses.error
        curses_mock = self.enterContext(mock.patch.object(curses_display, "curses"))
        curses_mock.error = curses_error
        curses_mock.has_colors.return_value = False
        self.def_prog_mode = curses_mock.def_prog_mode
        self.calls.attach_mock(curses_mock.def_prog_mode, "def_prog_mode")
        self.calls.attach_mock(curses_mock.endwin, "endwin")
        self.enterContext(mock.patch.object(curses_display.sys, "stdin", **{"fileno.return_value": 7}))
        self.isatty = self.enterContext(mock.patch("os.isatty", return_value=True))
        self.tcgetattr = self.enterContext(mock.patch("termios.tcgetattr"))
        self.calls.attach_mock(self.enterContext(mock.patch("termios.tcsetattr")), "tcsetattr")

    def mode(self, lflag: int) -> list[object]:
        """Return a fresh [iflag, oflag, cflag, lflag, ispeed, ospeed, cc] list, as termios does on every call."""
        return [0, 0, 0, lflag, 0, 0, [b"\0"] * 32]

    def test_start_clears_iexten_and_flusho_and_stop_sets_them_again(self) -> None:
        """Clear IEXTEN and FLUSHO and keep ISIG; stop() sets back only the bits start() cleared."""
        for name, lflag, cleared in (
            ("IEXTEN | FLUSHO | ISIG", termios.IEXTEN | termios.FLUSHO | termios.ISIG, True),
            ("IEXTEN | ISIG", termios.IEXTEN | termios.ISIG, True),
            ("ISIG", termios.ISIG, False),
        ):
            with self.subTest(lflag=name):
                self.calls.reset_mock()
                # endwin() is mocked, so the terminal keeps the mode start() set until stop() changes it.
                self.tcgetattr.side_effect = [self.mode(lflag), self.mode(termios.ISIG)] + [self.mode(termios.ISIG)] * 4
                screen = curses_display.Screen()

                screen.start()
                screen.stop()

                expected = [
                    mock.call.tcsetattr(7, termios.TCSANOW, self.mode(termios.ISIG)),
                    mock.call.def_prog_mode(),
                    mock.call.endwin(),
                ]
                if cleared:
                    expected.append(mock.call.tcsetattr(7, termios.TCSANOW, self.mode(lflag)))
                # stop() also gives the signal keys back with TCSADRAIN, which is not under test here.
                mode_calls = [c for c in self.calls.mock_calls if c.args[1:2] != (termios.TCSADRAIN,)]
                self.assertEqual(expected, mode_calls)

    def test_start_without_a_curses_terminal_still_clears_and_restores_stdin(self) -> None:
        """Start when curses has no terminal to save a mode for, and still set the flags back on stop()."""
        lflag = termios.IEXTEN | termios.ISIG
        self.tcgetattr.side_effect = [self.mode(lflag), self.mode(termios.ISIG)] + [self.mode(termios.ISIG)] * 4
        self.def_prog_mode.side_effect = curses_display.curses.error("def_prog_mode() returned ERR")
        screen = curses_display.Screen()

        screen.start()
        screen.stop()

        self.assertIn(mock.call.tcsetattr(7, termios.TCSANOW, self.mode(lflag)), self.calls.mock_calls)

    def test_failed_start_restores_the_terminal(self) -> None:
        """Leave curses mode and set the cleared flags back when start() fails after changing them."""
        lflag = termios.IEXTEN | termios.ISIG
        self.tcgetattr.side_effect = [self.mode(lflag), self.mode(termios.ISIG)]
        error = termios.error(errno.EINVAL, "signal keys")
        self.enterContext(mock.patch.object(curses_display.Screen, "tty_signal_keys", side_effect=error))
        screen = curses_display.Screen()

        with self.assertRaises(termios.error):
            screen.start()

        self.assertEqual(
            [mock.call.endwin(), mock.call.tcsetattr(7, termios.TCSANOW, self.mode(lflag))],
            self.calls.mock_calls[-2:],
        )

    def test_stop_gives_the_signal_keys_back_when_the_mode_restore_fails(self) -> None:
        """Restore the signal keys even when setting the cleared flags back raises."""
        self.tcgetattr.side_effect = [self.mode(termios.IEXTEN), self.mode(0)]
        keys = self.enterContext(mock.patch.object(curses_display.Screen, "tty_signal_keys", return_value=(1, 2)))
        screen = curses_display.Screen()
        screen.start()
        self.calls.tcsetattr.side_effect = termios.error(errno.EIO, "restore")

        with self.assertRaises(termios.error):
            screen.stop()

        self.assertEqual(mock.call(1, 2), keys.call_args)

    def test_start_leaves_a_non_terminal_input_alone(self) -> None:
        """Change no termios setting and save no program mode when the input is not a terminal."""
        self.isatty.return_value = False
        screen = curses_display.Screen()

        screen.start()
        screen.stop()

        self.assertEqual([mock.call.endwin()], self.calls.mock_calls)


@unittest.skipIf(curses_display is None, "the curses module is not available")
class CursesGetInputTest(unittest.TestCase):
    """Tests for ``_get_input``, which decodes the keys curses has queued."""

    def test_sequence_cut_short_waits_for_the_next_keys(self) -> None:
        """Read the keys after a sequence cut short, and decode the sequence alone when none come."""
        for label, later, expected in (
            ("completed by the keys that follow", ord("B"), ["a", "down"]),
            ("decoded as it is when none follow", -1, ["a", "meta ["]),
        ):
            with self.subTest(label):
                screen = curses_display.Screen()
                with (
                    mock.patch("curses.doupdate"),
                    mock.patch.object(screen, "_getch", side_effect=[ord("a"), later]),
                    mock.patch.object(screen, "_getch_nodelay", side_effect=[27, ord("["), -1, -1]),
                ):
                    processed, raw = screen._get_input(None)

                self.assertEqual(expected, processed)
                self.assertEqual([ord("a"), 27, ord("["), *([later] if later >= 0 else [])], raw)


@unittest.skipIf(curses_display is None, "the curses module is not available")
class CursesMouseTest(unittest.TestCase):
    """Tests for the mouse events of curses, which the screen encodes as X10 reports for the input parser."""

    def test_events_past_a_byte_keep_their_position(self) -> None:
        """Report a press, a double click and a release at a column or row past what an X10 byte can carry."""
        curses = curses_display.curses
        screen = curses_display.Screen()
        for bstate, expected in (
            (curses.BUTTON1_PRESSED, ("mouse press", 1, 300, 1000)),
            (curses.BUTTON1_DOUBLE_CLICKED, ("double mouse click", 1, 300, 1000)),
            (curses.BUTTON1_RELEASED, ("mouse release", 1, 300, 1000)),
        ):
            with (
                self.subTest(expected=expected[0]),
                mock.patch.object(curses, "getmouse", return_value=(0, 300, 1000, 0, bstate)),
            ):
                keys, _rest = escape.process_keyqueue(screen._encode_mouse_event(), more_available=False)
                self.assertEqual([expected], keys)

    def test_key_mouse_without_a_queued_event_is_dropped(self) -> None:
        """Report nothing when ncurses delivers KEY_MOUSE but getmouse() finds no event in its queue."""
        curses = curses_display.curses
        screen = curses_display.Screen()
        with mock.patch.object(curses, "getmouse", side_effect=curses.error("getmouse() returned ERR")):
            self.assertEqual([], screen._encode_mouse_event())
