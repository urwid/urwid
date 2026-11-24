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
except ImportError:  # no stdlib curses on this platform, e.g. Windows
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

    def test_colors_are_drawn_with_the_initialised_pairs(self) -> None:
        # pair number is bg * 8 + 7 - fg; only basic colors 0-7 have pairs
        for label, attr, pair in (
            ("bright background folded", urwid.AttrSpec("dark red", "light blue", 16), 4 * 8 + 6),
            ("bright foreground folded", urwid.AttrSpec("light red", "default", 16), 6),
            ("palette entry by its nearest", urwid.AttrSpec("h196", "h21"), 4 * 8 + 6),
            # the nearest of all 16 is dark gray, which would fold to black
            ("RGB by its nearest of 8", urwid.AttrSpec("default", "#a0a0a0", 2**24), 7 * 8),
        ):
            with self.subTest(label):
                self.assertEqual(pair << 8, self.attr_of(attr))

    def test_palette_changes_are_drawn(self) -> None:
        self.screen.register_palette([("entry", "dark red", "inherit"), ("alias", "entry")])
        self.assertEqual(6 << 8, self.attr_of("alias"))

        self.screen.register_palette_entry("entry", "dark green", "inherit")
        self.assertEqual(5 << 8, self.attr_of("entry"))
        self.screen.register_palette_entry(None, "default", "dark blue")
        self.assertEqual((4 * 8 + 5) << 8, self.attr_of("entry"))
        self.screen.register_palette([("alias", "default", "inherit")])
        self.assertEqual(4 * 8 << 8, self.attr_of("alias"))

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
        self.written: list[str] = []
        self.enterContext(
            mock.patch.object(curses_display.Screen, "_write_terminal", side_effect=self.written.append),
        )
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

    def test_failed_initscr_is_the_error_raised(self) -> None:
        """Raise the error of a failed initscr(), not one from undoing a start that changed nothing.

        The screen is left stopped, and the terminal mode is not touched.
        """
        curses_mock = curses_display.curses
        curses_mock.initscr.side_effect = curses_mock.error("setupterm: could not find terminal")
        curses_mock.echo.side_effect = curses_mock.error("must call initscr() first")
        screen = curses_display.Screen()

        with self.assertRaisesRegex(curses_mock.error, "could not find terminal"):
            screen.start()

        self.assertFalse(screen.started)
        self.calls.tcsetattr.assert_not_called()

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

    def test_in_band_resize_is_turned_on_at_start_and_off_at_stop_only_when_asked_for(self) -> None:
        """Turn the mode on at start and off at stop for in_band_resize=True; by default the terminal is not asked."""
        mode = urwid.display.escape.PrivateMode.IN_BAND_RESIZE
        for in_band_resize, at_start, at_stop in (
            (True, [mode.enable_seq], [mode.disable_seq]),
            (False, [], []),
        ):
            with self.subTest(in_band_resize=in_band_resize):
                self.tcgetattr.side_effect = None
                self.tcgetattr.return_value = self.mode(termios.ISIG)
                self.written.clear()
                screen = curses_display.Screen(in_band_resize=in_band_resize)

                screen.start()
                self.assertEqual(at_start, self.written)
                self.written.clear()
                screen.stop()

                self.assertEqual(at_stop, self.written)
                self.assertFalse(screen._in_band_resize)

    def test_stop_leaves_curses_mode_when_turning_the_mode_off_fails(self) -> None:
        """Leave curses mode after a failed write of the disable, raising only what is not a hung-up terminal."""
        self.tcgetattr.side_effect = None
        self.tcgetattr.return_value = self.mode(termios.ISIG)
        for error, raised in ((errno.EIO, False), (errno.EAGAIN, True)):
            with self.subTest(errno=errno.errorcode[error]):
                screen = curses_display.Screen(in_band_resize=True)
                screen.start()
                self.calls.reset_mock()

                with mock.patch.object(
                    curses_display.Screen,
                    "_write_terminal",
                    side_effect=OSError(error, "write"),
                ):
                    if raised:
                        with self.assertRaises(OSError):
                            screen.stop()
                    else:
                        screen.stop()

                self.assertIn(mock.call.endwin(), self.calls.mock_calls)
                self.assertFalse(screen._in_band_resize)

    def test_start_leaves_a_non_terminal_input_alone(self) -> None:
        """Change no termios setting and save no program mode when the input is not a terminal."""
        self.isatty.return_value = False
        screen = curses_display.Screen()

        screen.start()
        screen.stop()

        self.assertEqual([mock.call.endwin()], self.calls.mock_calls)
        self.assertEqual([], self.written)  # the terminal's reply would arrive where nothing reads it


@unittest.skipIf(curses_display is None, "the curses module is not available")
class CursesGetInputTest(unittest.TestCase):
    """Tests for ``_get_input``, which decodes the keys curses has queued."""

    def test_sequence_cut_short_waits_for_the_next_keys(self) -> None:
        """Keep a sequence cut short for the next call, and decode it alone once none of it came by complete_wait.

        The next call waits only for the time left until then, so a caller waiting for input forever still gets it.
        The raw codes of the sequence come with the call that decodes it.
        """
        # clock: time.monotonic() at the start of each call and when the first call keeps the sequence;
        # one more read in the second call checks whether its deadline passed
        for label, later, clock, expected, expected_raw, waits in (
            (
                "completed by the keys that follow",
                ord("B"),
                [100.0, 100.0, 100.0],
                ["down"],
                [27, ord("["), ord("B")],
                [None, 1],
            ),
            (
                "decoded as it is when none follow",
                -1,
                [100.0, 100.0, 100.0, 100.2],
                ["meta ["],
                [27, ord("[")],
                [None, 1],
            ),
            ("decoded as the next call starts", -1, [100.0, 100.0, 100.2], ["meta ["], [27, ord("[")], [None, 0]),
        ):
            with self.subTest(label):
                screen = curses_display.Screen()
                screen._started = True
                with (
                    mock.patch("curses.doupdate"),
                    mock.patch.object(screen, "_getch", side_effect=[ord("a"), later]) as getch,
                    mock.patch.object(screen, "_getch_nodelay", side_effect=[27, ord("["), -1, -1]),
                    mock.patch.object(curses_display.time, "monotonic", side_effect=clock),
                ):
                    self.assertEqual((["a"], [ord("a")]), screen.get_input(raw_keys=True))
                    self.assertEqual((expected, expected_raw), screen.get_input(raw_keys=True))

                # no max_wait: the first call waits forever; the second until complete_wait, one tenth, is over,
                # or not at all once it is
                self.assertEqual(waits, [call.args[0] for call in getch.call_args_list])
                self.assertEqual([], screen._partial_keys)

    def test_raw_codes_that_are_no_key_come_with_the_call_that_read_them(self) -> None:
        """Report a resize and an empty mouse report at once, while the Esc read with them waits for its rest."""
        screen = curses_display.Screen()
        screen._started = True
        resize, mouse = curses_display.KEY_RESIZE, curses_display.KEY_MOUSE
        # clock: the first call's start and its keeping of the Esc; the second call's start
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[27, ord("x")]),
            mock.patch.object(screen, "_getch_nodelay", side_effect=[resize, mouse, -1, -1]),
            mock.patch.object(screen, "_encode_mouse_event", return_value=[]),
            mock.patch.object(curses_display.time, "monotonic", side_effect=[100.0, 100.0, 100.05]),
        ):
            self.assertEqual(([], [resize, mouse]), screen.get_input(raw_keys=True))
            self.assertEqual((["meta x", "window resize"], [27, ord("x")]), screen.get_input(raw_keys=True))

    def test_mouse_report_raw_code_comes_with_its_keys(self) -> None:
        """Report the KEY_MOUSE code once with the keys of the report it was encoded as."""
        screen = curses_display.Screen()
        screen._started = True
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", return_value=curses_display.KEY_MOUSE),
            mock.patch.object(screen, "_getch_nodelay", return_value=-1),
            mock.patch.object(screen, "_encode_mouse_event", return_value=[27, ord("["), ord("M"), 32, 33, 33]),
        ):
            keys, raw = screen.get_input(raw_keys=True)

        self.assertEqual([("mouse press", 1, 0, 0)], keys)
        self.assertEqual([curses_display.KEY_MOUSE], raw)

    def test_kept_sequence_waits_by_the_complete_wait_set_after_it_was_read(self) -> None:
        """A complete_wait set while a sequence is kept counts from the read that kept it."""
        screen = curses_display.Screen()
        screen._started = True
        # clock: the first call's start and its keeping of the sequence; the second call's start and its deadline check
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[ord("a"), -1]) as getch,
            mock.patch.object(screen, "_getch_nodelay", side_effect=[27, ord("["), -1, -1]),
            mock.patch.object(curses_display.time, "monotonic", side_effect=[100.0, 100.0, 100.2, 100.2]),
        ):
            self.assertEqual(["a"], screen.get_input())
            screen.set_input_timeouts(complete_wait=0.5)
            self.assertEqual([], screen.get_input())

        # the second call waits the three tenths left of the half second
        self.assertEqual([None, 3], [call.args[0] for call in getch.call_args_list])
        self.assertEqual([27, ord("[")], screen._partial_keys)

    def test_sequence_cut_short_after_new_input_gets_its_own_complete_wait(self) -> None:
        """Give an Esc read after a decoded key the whole complete_wait, also when an Esc was kept before.

        The time left is rounded up, so a call does not return before the deadline and leave its caller polling.
        """
        screen = curses_display.Screen()
        screen._started = True
        # clock: each call's start, and the reset of the deadline after the first two;
        # the third call checks the deadline once more
        clock = [100.0, 100.0, 100.08, 100.08, 100.15, 100.15]
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[27, ord("a"), -1]) as getch,
            mock.patch.object(screen, "_getch_nodelay", side_effect=[-1, 27, -1]),
            mock.patch.object(curses_display.time, "monotonic", side_effect=clock),
        ):
            self.assertEqual([], screen.get_input())
            self.assertEqual(["meta a"], screen.get_input())
            self.assertEqual([], screen.get_input())
        self.assertEqual([27], screen._partial_keys)
        # 0.02 s and 0.03 s were left: one tenth each, not none
        self.assertEqual([None, 1, 1], [call.args[0] for call in getch.call_args_list])

    def test_sequence_cut_short_waits_for_its_rest_forever_without_complete_wait(self) -> None:
        """With complete_wait None, keep a sequence cut short until more input comes, as max_wait allows."""
        screen = curses_display.Screen()
        screen._started = True
        screen.set_input_timeouts(max_wait=0.2, complete_wait=None)
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[27, -1, ord("[")]) as getch,
            mock.patch.object(screen, "_getch_nodelay", side_effect=[-1, ord("A"), -1]),
        ):
            self.assertEqual([], screen.get_input())
            self.assertEqual([], screen.get_input())
            self.assertEqual(["up"], screen.get_input())
        self.assertEqual([2, 2, 2], [call.args[0] for call in getch.call_args_list])

    def test_sequence_kept_past_its_deadline_comes_before_later_keys(self) -> None:
        """Decode a sequence whose deadline passed before the call alone, ahead of what was read after it.

        A resize read while the sequence was kept is reported after it as well.
        """
        # clock: each call's start, and the deadline set by the first call
        for label, getch, nodelay, first, second in (
            ("keys typed later", [ord("x"), ord("a")], [27, -1, -1], ["x"], ["esc", "a"]),
            (
                "a resize read with the sequence",
                [27, -1],
                [curses_display.KEY_RESIZE, -1],
                [],
                ["esc", "window resize"],
            ),
        ):
            with self.subTest(label):
                screen = curses_display.Screen()
                screen._started = True
                with (
                    mock.patch("curses.doupdate"),
                    mock.patch.object(screen, "_getch", side_effect=getch) as getch_mock,
                    mock.patch.object(screen, "_getch_nodelay", side_effect=nodelay),
                    mock.patch.object(curses_display.time, "monotonic", side_effect=[100.0, 100.0, 100.5]),
                ):
                    self.assertEqual(first, screen.get_input())
                    self.assertEqual(second, screen.get_input())
                self.assertEqual([None, 0], [call.args[0] for call in getch_mock.call_args_list])

    def test_resize_read_with_kept_keys_is_reported_after_them(self) -> None:
        """Hold a resize read while keys are kept, across calls, and report it after them once they are decoded."""
        screen = curses_display.Screen()
        screen._started = True
        # clock: the first call's start and its deadline; the second call's start and its deadline check;
        # the third call's start
        clock = [100.0, 100.0, 100.02, 100.05, 100.06]
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[27, -1, ord("[")]),
            mock.patch.object(screen, "_getch_nodelay", side_effect=[curses_display.KEY_RESIZE, -1, ord("A"), -1]),
            mock.patch.object(curses_display.time, "monotonic", side_effect=clock),
        ):
            self.assertEqual([], screen.get_input())
            self.assertEqual([], screen.get_input())
            self.assertEqual(["up", "window resize"], screen.get_input())

    def test_resize_ends_the_wait_for_a_sequence_without_complete_wait(self) -> None:
        """With complete_wait None, decode the kept keys when a resize comes, so the resize is reported at once."""
        screen = curses_display.Screen()
        screen._started = True
        screen.set_input_timeouts(complete_wait=None)
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[27]),
            mock.patch.object(screen, "_getch_nodelay", side_effect=[curses_display.KEY_RESIZE, -1]),
        ):
            self.assertEqual(["esc", "window resize"], screen.get_input())

    def test_resize_throttle_waits_no_longer_than_the_caller_allows(self) -> None:
        """Wait for more input after repeated resizes only within max_wait, so an alarm due sooner is not held up.

        The time left is rounded to the nearest tenth, as max_wait is.
        """
        # clock: time.monotonic() at the start and before each of the two waits for more input
        for label, max_wait, clock, expected in (
            ("waiting forever", None, [100.0], [1, 1]),
            ("no wait", 0, [100.0, 100.0, 100.0], [0, 0]),
            ("part of max_wait left", 0.3, [100.0, 100.15, 100.22], [1, 1]),
            ("max_wait used up", 0.3, [100.0, 100.28, 100.3], [0, 0]),
        ):
            with self.subTest(label):
                screen = curses_display.Screen()
                screen._started = True
                screen.prev_input_resize = 2
                screen.set_input_timeouts(max_wait)
                with (
                    mock.patch.object(screen, "_get_input", return_value=(["window resize"], [])) as get_input,
                    mock.patch.object(curses_display.time, "monotonic", side_effect=clock),
                ):
                    self.assertEqual(["window resize"], screen.get_input())
                self.assertEqual(
                    [screen.max_tenths, *expected],
                    [call.args[0] for call in get_input.call_args_list],
                )

    def test_report_this_screen_did_not_ask_for_is_dropped(self) -> None:
        """Drop a report or a query reply that answers another program.

        No tuple then reaches the main loop.
        A window size report counts only while this screen has mode 2048 on.
        This screen sends no query, so every query reply answers another program's query.
        """
        for label, report in (
            ("window size report", escape.window_size_report(80, 24)),
            ("private mode report", "\x1b[?2004;1$y"),
            ("keyboard protocol report", "\x1b[?1u"),
            ("modify keys report", "\x1b[>4;2m"),
            ("device attributes", "\x1b[?62;22c"),
            ("terminal version", "\x1bP>|XTerm(390)\x1b\\"),
            ("terminal capabilities", "\x1bP1+r524742\x1b\\"),
        ):
            with self.subTest(label):
                screen = curses_display.Screen()
                with (
                    mock.patch("curses.doupdate"),
                    mock.patch.object(screen, "_getch", side_effect=[ord("a"), -1]),
                    mock.patch.object(screen, "_getch_nodelay", side_effect=[*report.encode(), ord("b"), -1]),
                ):
                    processed, _raw = screen._get_input(None)

                self.assertEqual(["a", "b"], processed)

    def _get_input_with(self, screen: curses_display.Screen, codes: bytes | list[int]) -> list[object]:
        """Return what ``_get_input`` makes of *codes*, with curses reporting a size of 80 by 24."""
        screen.s = mock.Mock(**{"getmaxyx.return_value": (24, 80)})
        with (
            mock.patch("curses.doupdate"),
            mock.patch.object(screen, "_getch", side_effect=[codes[0], -1]),
            mock.patch.object(screen, "_getch_nodelay", side_effect=[*codes[1:], -1]),
        ):
            processed, _raw = screen._get_input(None)
        return processed

    def test_window_size_report_resizes_curses_where_the_mode_is_on(self) -> None:
        """Give curses a new reported size and report a resize at its place.

        A report of the same size, or of a size curses cannot apply, is dropped.
        """
        for size, failure, expected, resized in (
            ((100, 30), None, ["a", "window resize", "b"], True),
            ((80, 24), None, ["a", "b"], False),
            ((100, 30), curses_display.curses.error("resize_term() returned ERR"), ["a", "b"], True),
        ):
            with self.subTest(size=size, failure=failure):
                screen = curses_display.Screen()
                screen._in_band_resize = True

                with mock.patch("curses.resize_term", side_effect=failure) as resize_term:
                    processed = self._get_input_with(
                        screen,
                        b"a" + escape.window_size_report(*size).encode() + b"b",
                    )

                self.assertEqual(expected, processed)
                self.assertEqual([mock.call(size[1], size[0])] if resized else [], resize_term.mock_calls)

    def test_window_size_report_takes_the_place_of_a_resize_curses_read(self) -> None:
        """Report a resize curses read with a report once, at the report's place.

        The terminal sets the size before it sends the report, so curses can have the reported size already.
        """
        for size, resized in (((80, 24), False), ((100, 30), True)):
            with self.subTest(size=size):
                screen = curses_display.Screen()
                screen._in_band_resize = True
                codes = [ord("a"), curses_display.KEY_RESIZE, *escape.window_size_report(*size).encode(), ord("b")]

                with mock.patch("curses.resize_term") as resize_term:
                    processed = self._get_input_with(screen, codes)

                self.assertEqual(["a", "window resize", "b"], processed)
                self.assertEqual([mock.call(size[1], size[0])] if resized else [], resize_term.mock_calls)


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
