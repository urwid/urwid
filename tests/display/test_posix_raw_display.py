from __future__ import annotations

import os
import signal
import struct
import sys
import unittest
from unittest import mock

from urwid import escape, signals
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED

# `_posix_raw_display` (and `fcntl`/`termios`) is not importable on Windows at all, so importing
# it unconditionally at module level would crash collection there under both pytest and plain
# `python -m unittest` -- the latter has no `allow_module_level` skip mechanism and lets a
# module-level `unittest.SkipTest` propagate as an import error instead of a skip. Every test
# class below is decorated with `@unittest.skipIf(IS_WINDOWS, ...)`, which both runners honour
# without needing the module to import successfully first.
IS_WINDOWS = sys.platform == "win32"
# GraalPy's signal module has no pthread_sigmask at all, which _sigtstp_handler() calls directly,
# so both mock.patch("signal.pthread_sigmask") (which requires the attribute to exist)
# and the real code path fail the same way there.
IS_GRAALPY = sys.implementation.name == "graalpy"

if not IS_WINDOWS:
    import fcntl
    import termios

    from urwid.display._posix_raw_display import _GPM_B_LEFT, _GPM_MOD_SHIFT, Screen


def _make_screen(input_fd: int | None = None) -> Screen:
    """Build a Screen over a pipe (or /dev/null) so tests never touch a real tty."""
    if input_fd is None:
        input_fd, write_fd = os.pipe()
        os.close(write_fd)
    return Screen(input=os.fdopen(input_fd, "rb", buffering=0), output=open(os.devnull, "w"))


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestStartStop(unittest.TestCase):
    def test_start_stop_not_a_tty(self):
        """termios is left untouched when the input fd is not a tty (a pipe here)."""
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(
            input=os.fdopen(read_fd, "rb", buffering=0),
            output=open(os.devnull, "w"),  # noqa: SIM115
            bracketed_paste_mode=True,
            focus_reporting=True,
        )
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None

        s.start()
        self.addCleanup(s.stop)

        output = "".join(written)
        self.assertIn(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.enable_seq, output)
        self.assertIn(escape.PrivateMode.BRACKETED_PASTE.enable_seq, output)
        self.assertIn(escape.PrivateMode.FOCUS_REPORTING.enable_seq, output)
        self.assertNotIn("_old_termios_settings", vars(s))

        written.clear()
        s.stop()
        output = "".join(written)
        self.assertIn(escape.PrivateMode.BRACKETED_PASTE.disable_seq, output)
        self.assertIn(escape.DISABLE_FOCUS_REPORTING, output)

    @mock.patch("termios.tcsetattr")
    @mock.patch("termios.tcgetattr")
    @mock.patch("tty.setcbreak")
    @mock.patch("os.isatty", return_value=True)
    def test_start_stop_saves_and_restores_termios_for_a_tty(
        self,
        mock_isatty,
        mock_setcbreak,
        mock_tcgetattr,
        mock_tcsetattr,
    ):
        # A minimally realistic termios attribute list: [iflag, oflag, cflag, lflag, ispeed,
        # ospeed, cc], with `cc` large enough to index by any of the VINTR/VQUIT/... constants
        # that tty_signal_keys() reads out of it.
        fake_attrs = [0, 0, 0, 0, 0, 0, [0] * 32]
        mock_tcgetattr.return_value = fake_attrs
        s = _make_screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None

        s.start()
        self.addCleanup(s.stop)

        fd = s._input_fileno()
        mock_tcgetattr.assert_any_call(fd)
        mock_setcbreak.assert_called_once_with(fd)
        self.assertEqual(fake_attrs, s._old_termios_settings)

        s.stop()
        mock_tcsetattr.assert_any_call(fd, termios.TCSAFLUSH, fake_attrs)

    def test_alternate_buffer_flag_is_set_before_later_start_steps_can_fail(self):
        """`stop()` still calls `_stop()` after `_start()` raises (`_started` is set first), so
        `_alternate_buffer` has to already be correct by the time the write happens, not after
        later steps -- here `signal_init()` -- that could still fail."""
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.signal_init = mock.Mock(side_effect=RuntimeError("boom"))

        with self.assertRaises(RuntimeError):
            s.start()

        self.assertTrue(s._alternate_buffer)
        s.stop()  # must not raise: signal_restore() only reads what __init__ already set

    def test_start_installs_signal_handlers_and_stop_restores_them(self):
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None

        previous_winch = signal.getsignal(signal.SIGWINCH)
        previous_tstp = signal.getsignal(signal.SIGTSTP)

        s.start()
        self.assertEqual(s._sigwinch_handler, signal.getsignal(signal.SIGWINCH))
        self.assertEqual(s._sigtstp_handler, signal.getsignal(signal.SIGTSTP))

        s.stop()
        self.assertEqual(previous_winch, signal.getsignal(signal.SIGWINCH))
        self.assertEqual(previous_tstp, signal.getsignal(signal.SIGTSTP))


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestSignalHandlers(unittest.TestCase):
    def test_sigwinch_handler_chains_to_previous(self):
        s = _make_screen()
        calls = []
        s._prev_sigwinch_handler = lambda signum, frame: calls.append((signum, frame))
        s._resized = False

        s._sigwinch_handler(signal.SIGWINCH, None)

        self.assertTrue(s._resized)
        self.assertEqual([(signal.SIGWINCH, None)], calls)

    @unittest.skipIf(IS_GRAALPY, "signal.pthread_sigmask is missing on GraalPy")
    @mock.patch("os.kill")
    @mock.patch("signal.pthread_sigmask")
    def test_sigtstp_handler_blocks_sigcont_around_the_kill(self, mock_sigmask, mock_kill):
        mock_sigmask.return_value = set()
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(lambda: s.stop() if s._started else None)

        s._sigtstp_handler(signal.SIGTSTP, None)

        mock_sigmask.assert_any_call(signal.SIG_BLOCK, {signal.SIGCONT})
        mock_sigmask.assert_any_call(signal.SIG_SETMASK, set())
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGTSTP)
        # stop() ran as part of the handler, so the screen is no longer marked started.
        self.assertFalse(s._started)
        # A SIGCONT handler was installed to catch the eventual resume.
        self.assertEqual(s._sigcont_handler, signal.getsignal(signal.SIGCONT))
        signal.signal(signal.SIGCONT, s._prev_sigcont_handler or signal.SIG_DFL)

    @unittest.skipIf(IS_GRAALPY, "signal.pthread_sigmask is missing on GraalPy")
    @mock.patch("os.kill")
    @mock.patch("signal.pthread_sigmask")
    def test_sigcont_handler_restarts_the_screen_and_chains(self, mock_sigmask, mock_kill):
        mock_sigmask.return_value = set()
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        s._sigtstp_handler(signal.SIGTSTP, None)
        self.assertFalse(s._started)

        chained = []
        s._prev_sigcont_handler = lambda signum, frame: chained.append((signum, frame))

        s._sigcont_handler(signal.SIGCONT, None)

        self.assertTrue(s._started)
        self.assertTrue(s._resized)
        self.assertEqual([(signal.SIGCONT, None)], chained)
        s.stop()


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestGpmTracking(unittest.TestCase):
    @mock.patch("os.path.isfile", return_value=False)
    def test_start_gpm_tracking_skips_when_mev_missing(self, mock_isfile):
        s = _make_screen()
        s._start_gpm_tracking()
        self.assertIsNone(s.gpm_mev)
        mock_isfile.assert_called_once_with("/usr/bin/mev")

    @mock.patch.dict(os.environ, {"TERM": "xterm"})
    @mock.patch("os.path.isfile", return_value=True)
    def test_start_gpm_tracking_skips_when_term_not_linux(self, mock_isfile):
        s = _make_screen()
        s._start_gpm_tracking()
        self.assertIsNone(s.gpm_mev)

    @unittest.skipIf(IS_GRAALPY, "fcntl.fcntl is missing on GraalPy")
    @mock.patch.dict(os.environ, {"TERM": "linux"})
    @mock.patch("fcntl.fcntl")
    @mock.patch("urwid.display._posix_raw_display.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_start_gpm_tracking_success_sets_nonblocking(self, mock_isfile, mock_popen_cls, mock_fcntl):
        mock_proc = mock.MagicMock()
        mock_proc.stdout.fileno.return_value = 99
        mock_popen_cls.return_value = mock_proc

        s = _make_screen()
        s._start_gpm_tracking()

        mock_popen_cls.assert_called_once_with(
            ["/usr/bin/mev", "-e", "158"],
            stdin=mock.ANY,
            stdout=mock.ANY,
            close_fds=True,
            encoding="ascii",
        )
        mock_fcntl.assert_called_once_with(99, fcntl.F_SETFL, os.O_NONBLOCK)
        self.assertIs(mock_proc, s.gpm_mev)

    @mock.patch.dict(os.environ, {"TERM": "linux"})
    @mock.patch("urwid.display._posix_raw_display.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_start_gpm_tracking_raises_when_stdout_missing(self, mock_isfile, mock_popen_cls):
        mock_proc = mock.MagicMock()
        mock_proc.stdout = None
        mock_popen_cls.return_value = mock_proc

        s = _make_screen()
        with self.assertRaises(RuntimeError):
            s._start_gpm_tracking()

        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once_with(1)

    @mock.patch("os.waitpid")
    @mock.patch("os.kill")
    def test_stop_gpm_tracking(self, mock_kill, mock_waitpid):
        s = _make_screen()
        fake_proc = mock.MagicMock()
        fake_proc.pid = 4321
        s.gpm_mev = fake_proc

        s._stop_gpm_tracking()

        mock_kill.assert_called_once_with(4321, signal.SIGINT)
        mock_waitpid.assert_called_once_with(4321, 0)
        self.assertIsNone(s.gpm_mev)

    def test_stop_gpm_tracking_noop_when_not_tracking(self):
        s = _make_screen()
        s._stop_gpm_tracking()  # must not raise
        self.assertIsNone(s.gpm_mev)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestEncodeGpmEvent(unittest.TestCase):
    @staticmethod
    def _gpm_line(ev_hex: str, x: int, y: int, buttons: int, modifiers_hex: str) -> str:
        # Field layout mirrors what _encode_gpm_event's parser expects:
        #  - event type: hex digits after the last "x"
        #  - x: last whitespace-separated token
        #  - y: first whitespace-separated token (after stripping leading space)
        #  - a 4th field that is ignored
        #  - buttons: last whitespace-separated token, parsed as decimal
        #  - modifiers: hex digits after the last "x"
        return f"Ax{ev_hex}, Ax  {x}, {y} y, dx 0x0, buttons {buttons}, modifiers 0x{modifiers_hex}\n"

    def _screen_with_gpm_line(self, line: str) -> Screen:
        s = _make_screen()
        gpm_mev = mock.MagicMock()
        gpm_mev.stdout.readline.return_value = line
        s.gpm_mev = gpm_mev
        return s

    def test_press_left_button(self):
        s = self._screen_with_gpm_line(self._gpm_line("14", 7, 10, _GPM_B_LEFT, "0"))  # ev=20
        s.last_bstate = 0

        result = s._encode_gpm_event()

        self.assertEqual([27, ord("["), ord("M"), 32, 7 + 32, 10 + 32], result)
        self.assertEqual(1, s.last_bstate)
        self.assertFalse(s.gpm_event_pending)

    def test_drag_middle_button(self):
        s = self._screen_with_gpm_line(self._gpm_line("92", 3, 4, 2, "0"))  # ev=146, buttons=GPM_B_MIDDLE
        s.last_bstate = 0

        result = s._encode_gpm_event()

        expected_button = 1 + escape.MOUSE_DRAG_FLAG + 32
        self.assertEqual([27, ord("["), ord("M"), expected_button, 3 + 32, 4 + 32], result)
        # drag does not change the tracked button state
        self.assertEqual(0, s.last_bstate)

    def test_release_left_button(self):
        s = self._screen_with_gpm_line(self._gpm_line("8", 1, 2, _GPM_B_LEFT, "0"))  # ev=8 (plain "up")
        s.last_bstate = 1  # left button was down

        result = s._encode_gpm_event()

        expected_button = escape.MOUSE_RELEASE_FLAG + 32
        self.assertEqual([27, ord("["), ord("M"), expected_button, 1 + 32, 2 + 32], result)
        self.assertEqual(0, s.last_bstate)

    def test_double_click_release_emits_release_and_multi_click(self):
        s = self._screen_with_gpm_line(self._gpm_line("28", 5, 6, _GPM_B_LEFT, "0"))  # ev=40
        s.last_bstate = 1  # left button was down

        result = s._encode_gpm_event()

        release_button = escape.MOUSE_RELEASE_FLAG + 32
        double_button = escape.MOUSE_MULTIPLE_CLICK_FLAG + 32
        self.assertEqual(
            [
                27,
                ord("["),
                ord("M"),
                release_button,
                5 + 32,
                6 + 32,
                27,
                ord("["),
                ord("M"),
                double_button,
                5 + 32,
                6 + 32,
            ],
            result,
        )
        self.assertEqual(0, s.last_bstate)

    def test_triple_click_press(self):
        s = self._screen_with_gpm_line(self._gpm_line("34", 8, 9, _GPM_B_LEFT, "0"))  # ev=52
        s.last_bstate = 1  # left button already tracked as down from the preceding double click

        result = s._encode_gpm_event()

        triple_button = escape.MOUSE_MULTIPLE_CLICK_FLAG * 2 + 32
        self.assertEqual([27, ord("["), ord("M"), triple_button, 8 + 32, 9 + 32], result)
        self.assertEqual(1, s.last_bstate)

    def test_shift_modifier_is_applied(self):
        s = self._screen_with_gpm_line(self._gpm_line("14", 0, 0, _GPM_B_LEFT, "1"))  # ev=20, mod=GPM_MOD_SHIFT
        s.last_bstate = 0

        result = s._encode_gpm_event()

        # shift maps to xterm's mod bit 4, ORed into the button byte
        self.assertEqual(4 + 32, result[3])
        self.assertEqual(_GPM_MOD_SHIFT, 1)  # sanity: the constant used to build the fixture

    @mock.patch("os.waitpid")
    @mock.patch("os.kill")
    def test_malformed_line_stops_tracking(self, mock_kill, mock_waitpid):
        s = self._screen_with_gpm_line("not,enough,fields\n")
        s.gpm_mev.pid = 4242
        seen = []
        signals.connect_signal(s, INPUT_DESCRIPTORS_CHANGED, lambda: seen.append(True))

        result = s._encode_gpm_event()

        self.assertEqual([], result)
        self.assertIsNone(s.gpm_mev)
        self.assertEqual([True], seen)
        mock_kill.assert_called_once_with(4242, signal.SIGINT)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestReadRawInput(unittest.TestCase):
    def test_drains_all_available_bytes_across_multiple_writes(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(input=os.fdopen(read_fd, "rb", buffering=0), output=open(os.devnull, "w"))  # noqa: SIM115
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(s.stop)

        os.write(write_fd, b"abc")
        os.write(write_fd, b"def")

        result = s._read_raw_input(1)

        self.assertEqual(bytearray(b"abcdef"), result)

    def test_returns_empty_on_timeout_with_nothing_available(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(input=os.fdopen(read_fd, "rb", buffering=0), output=open(os.devnull, "w"))  # noqa: SIM115
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(s.stop)

        result = s._read_raw_input(0)

        self.assertEqual(bytearray(), result)

    def test_raises_runtime_error_on_eof(self):
        read_fd, write_fd = os.pipe()
        s = Screen(input=os.fdopen(read_fd, "rb", buffering=0), output=open(os.devnull, "w"))  # noqa: SIM115
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(s.stop)

        os.close(write_fd)  # EOF with nothing ever written

        with self.assertRaises(RuntimeError):
            s._read_raw_input(1)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestDetectTerminalModes(unittest.TestCase):
    """_detect_terminal_modes() only writes the DECRQM queries; it does not wait for a reply."""

    def _screen_over_pipe(self, *, bracketed_paste_mode=None, focus_reporting=None):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(
            input=os.fdopen(read_fd, "rb", buffering=0),
            output=open(os.devnull, "w"),  # noqa: SIM115
            bracketed_paste_mode=bracketed_paste_mode,
            focus_reporting=focus_reporting,
        )
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        return s, written

    @mock.patch("os.isatty", return_value=True)
    def test_queries_every_mode_left_at_its_sentinel(self, mock_isatty):
        s, written = self._screen_over_pipe()

        s._detect_terminal_modes()

        output = "".join(written)
        self.assertIn(escape.PrivateMode.SYNCHRONIZED_OUTPUT.query, output)
        self.assertIn(escape.PrivateMode.GRAPHEME_CLUSTERING.query, output)
        self.assertIn(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.query, output)
        self.assertIn(escape.PrivateMode.MOUSE_REPORTING.query, output)
        self.assertIn(escape.PrivateMode.MOUSE_SGR_MODE.query, output)
        self.assertIn(escape.PrivateMode.BRACKETED_PASTE.query, output)
        self.assertIn(escape.PrivateMode.FOCUS_REPORTING.query, output)

    @mock.patch("os.isatty", return_value=True)
    def test_skips_modes_given_an_explicit_preference(self, mock_isatty):
        s, written = self._screen_over_pipe(bracketed_paste_mode=True, focus_reporting=False)

        s._detect_terminal_modes()

        output = "".join(written)
        # synchronized_output/grapheme_clustering have no sentinel to skip: always queried.
        self.assertIn(escape.PrivateMode.SYNCHRONIZED_OUTPUT.query, output)
        self.assertIn(escape.PrivateMode.GRAPHEME_CLUSTERING.query, output)
        self.assertNotIn(escape.PrivateMode.BRACKETED_PASTE.query, output)
        self.assertNotIn(escape.PrivateMode.FOCUS_REPORTING.query, output)

    def test_not_a_tty_writes_nothing(self):
        # os.isatty is left unmocked here: a plain pipe is never a tty.
        s, written = self._screen_over_pipe()

        s._detect_terminal_modes()

        self.assertEqual([], written)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestApplyPrivateModeReports(unittest.TestCase):
    """parse_input() recognizes a DECRPM reply, applies it to self.modes, and strips it out."""

    @staticmethod
    def _screen(*, bracketed_paste: bool | None = None):
        s = _make_screen()
        s.modes.bracketed_paste = bracketed_paste
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        return s, written

    def test_recognized_reply_resolves_the_sentinel_and_is_not_returned(self):
        s, _written = self._screen()

        keys, _raw = s.parse_input(None, None, list(b"\x1b[?2026;1$y"))

        self.assertEqual([], keys)
        self.assertTrue(s.modes.synchronized_output)

    def test_grapheme_clustering_reply_is_recorded_without_acting_on_it(self):
        """Queried (see TestDetectTerminalModes above), but nothing enables or reads it back."""
        s, written = self._screen()

        keys, _raw = s.parse_input(None, None, list(b"\x1b[?2027;1$y"))

        self.assertEqual([], keys)
        self.assertTrue(s.modes.grapheme_clustering)
        self.assertEqual([], written)

    def test_bracketed_paste_confirmed_from_the_sentinel_is_enabled_immediately(self):
        s, written = self._screen(bracketed_paste=None)

        s.parse_input(None, None, list(b"\x1b[?2004;1$y"))

        self.assertTrue(s.modes.bracketed_paste)
        self.assertIn(escape.ENABLE_BRACKETED_PASTE_MODE, "".join(written))

    def test_unrecognized_reply_resolves_the_sentinel_to_false_without_enabling(self):
        s, written = self._screen(bracketed_paste=None)

        s.parse_input(None, None, list(b"\x1b[?2004;0$y"))

        self.assertFalse(s.modes.bracketed_paste)
        self.assertEqual([], written)

    def test_reply_for_an_already_forced_mode_does_not_write_enable_again(self):
        """A mode that was never at its sentinel must not get ENABLE written a second time."""
        s, written = self._screen(bracketed_paste=True)

        s.parse_input(None, None, list(b"\x1b[?2004;1$y"))

        self.assertTrue(s.modes.bracketed_paste)
        self.assertEqual([], written)

    def test_reply_for_a_mode_urwid_does_not_track_is_dropped_without_error(self):
        s, _written = self._screen()

        keys, _raw = s.parse_input(None, None, list(b"\x1b[?9999;1$y"))

        self.assertEqual([], keys)

    def test_ordinary_input_around_a_reply_still_comes_through(self):
        s, _written = self._screen()

        keys, _raw = s.parse_input(None, None, [ord("a"), *b"\x1b[?2026;1$y", ord("b")])

        self.assertEqual(["a", "b"], keys)
        self.assertTrue(s.modes.synchronized_output)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestMouseTracking(unittest.TestCase):
    def test_enable_writes_the_sequence_when_support_is_unresolved(self):
        s = _make_screen()
        written: list[str] = []
        s.write = written.append

        s._mouse_tracking(True)

        self.assertIn(escape.MOUSE_TRACKING_ON, written)
        self.assertTrue(s._mouse_tracking_enabled)

    def test_enable_is_a_noop_once_confirmed_unsupported(self):
        s = _make_screen()
        s.modes.mouse_reporting = False
        written: list[str] = []
        s.write = written.append

        s._mouse_tracking(True)

        self.assertEqual([], written)
        self.assertFalse(s._mouse_tracking_enabled)

    def test_becoming_confirmed_unsupported_resets_a_previously_enabled_state(self):
        s = _make_screen()
        s.write = lambda *_a: None
        s._mouse_tracking(True)
        self.assertTrue(s._mouse_tracking_enabled)

        s.modes.mouse_reporting = False
        s._mouse_tracking(True)

        self.assertFalse(s._mouse_tracking_enabled)

    def test_disable_always_writes_the_sequence(self):
        s = _make_screen()
        s.modes.mouse_reporting = False
        written: list[str] = []
        s.write = written.append

        s._mouse_tracking(False)

        self.assertIn(escape.MOUSE_TRACKING_OFF, written)
        self.assertFalse(s._mouse_tracking_enabled)

    def test_set_mouse_tracking_is_a_noop_when_already_at_the_requested_state(self):
        s = _make_screen()
        written: list[str] = []
        s.write = written.append

        s.set_mouse_tracking(False)  # already disabled by default

        self.assertEqual([], written)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestGetColsRows(unittest.TestCase):
    @mock.patch("fcntl.ioctl")
    def test_uses_ioctl_result(self, mock_ioctl):
        mock_ioctl.return_value = struct.pack("hhhh", 40, 100, 0, 0)
        s = _make_screen()

        cols, rows = s.get_cols_rows()

        self.assertEqual((100, 40), (cols, rows))
        self.assertEqual(40, s.maxrow)

    @mock.patch("fcntl.ioctl")
    def test_falls_back_to_80x24_for_ansi_vt100_when_ioctl_gives_non_positive(self, mock_ioctl):
        mock_ioctl.return_value = struct.pack("hhhh", 0, 0, 0, 0)
        s = _make_screen()
        s.term = "ansi"

        cols, rows = s.get_cols_rows()

        self.assertEqual((80, 24), (cols, rows))


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestGetInputDescriptors(unittest.TestCase):
    def test_empty_when_not_started(self):
        s = _make_screen()
        self.assertEqual([], s.get_input_descriptors())

    @mock.patch("os.waitpid")
    @mock.patch("os.kill")
    def test_includes_gpm_stdout_when_tracking_and_started(self, mock_kill, mock_waitpid):
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()

        gpm_mev = mock.MagicMock()
        gpm_mev.pid = 4343
        s.gpm_mev = gpm_mev

        descriptors = s.get_input_descriptors()

        self.assertIn(gpm_mev.stdout, descriptors)

        # stop() while the os.kill/os.waitpid mocks are still active, since _stop_gpm_tracking()
        # would otherwise try to signal a fake pid for real.
        s.stop()
