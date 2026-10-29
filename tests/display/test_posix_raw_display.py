from __future__ import annotations

import os
import signal
import struct
import subprocess
import sys
import unittest
from unittest import mock

import urwid
from urwid import signals
from urwid.display import escape
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED

# `_posix_raw_display` (and `fcntl`/`termios`) is not importable on Windows at all, so importing
# it unconditionally at module level would crash collection there under both pytest and plain
# `python -m unittest` -- the latter has no `allow_module_level` skip mechanism and lets a
# module-level `unittest.SkipTest` propagate as an import error instead of a skip. Every test
# class below is decorated with `@unittest.skipIf(IS_WINDOWS, ...)`, which both runners honour
# without needing the module to import successfully first.
IS_WINDOWS = sys.platform == "win32"

if not IS_WINDOWS:
    import termios

    from urwid.display._posix_raw_display import _GPM_B_LEFT, _GPM_MOD_SHIFT, Screen


class _StrictBytes(bytes):
    """A termios key that fails on comparison with a str, as `python -bb` makes every bytes object do."""

    __hash__ = bytes.__hash__

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            raise BytesWarning(f"comparison of {self!r} with {other!r}")
        return super().__eq__(other)


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
        self.assertIsNone(s._old_termios_settings)

        written.clear()
        s.stop()
        output = "".join(written)
        self.assertIn(escape.PrivateMode.BRACKETED_PASTE.disable_seq, output)
        self.assertIn(escape.PrivateMode.FOCUS_REPORTING.disable_seq, output)

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

    @mock.patch("termios.tcsetattr")
    @mock.patch("termios.tcgetattr")
    @mock.patch("tty.setcbreak")
    @mock.patch("os.isatty", return_value=True)
    def test_start_stop_restores_bytes_signal_keys_without_comparing_them_to_str(
        self,
        mock_isatty,
        mock_setcbreak,
        mock_tcgetattr,
        mock_tcsetattr,
    ):
        """termios reports the signal keys as bytes, and `stop()` passes them back to `tty_signal_keys()`.

        Comparing them with the str "undefined" raises BytesWarning under `python -bb` (#512), so the keys
        here fail on any comparison with a str, which needs no interpreter flag.
        """
        cc = [_StrictBytes(b"\0")] * 32
        keys = {
            termios.VINTR: _StrictBytes(b"\x03"),
            termios.VQUIT: _StrictBytes(b"\x1c"),
            termios.VSTART: _StrictBytes(b"\x11"),
            termios.VSTOP: _StrictBytes(b"\x13"),
            termios.VSUSP: _StrictBytes(b"\x1a"),
        }
        for index, key in keys.items():
            cc[index] = key
        mock_tcgetattr.side_effect = lambda fd: [0, 0, 0, 0, 0, 0, cc.copy()]
        s = _make_screen()
        s.write = lambda data: None
        s.flush = lambda: None

        s.start()
        self.addCleanup(s.stop)
        self.assertEqual(tuple(keys.values()), s._old_signal_keys)

        s.stop()
        restored = mock_tcsetattr.call_args_list[-1].args
        self.assertEqual((s._input_fileno(), termios.TCSADRAIN), restored[:2])
        self.assertEqual(cc, restored[2][6])

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

    def test_stop_moves_below_the_frame_before_leaving_the_alternate_screen(self):
        """Stop works whether or not the terminal switched screens, and before any DECRQM reply."""
        for reply in (b"", b"\x1b[?1049;0$y", b"\x1b[?1049;1$y"):
            with self.subTest(reply=reply):
                s = _make_screen()
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                s.start()
                s.parse_input(None, None, list(reply))
                s.maxrow = 5
                written.clear()
                s.stop()
                self.assertIn(
                    escape.set_cursor_position(0, 5) + "\n" + escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.disable_seq,
                    "".join(written),
                )

    def test_restart_after_no_alternate_screen_reported_skips_only_the_switch(self):
        """The frames are still drawn on the whole screen, as on the first start."""
        s = _make_screen()
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        s.start()
        s.parse_input(None, None, list(b"\x1b[?1049;0$y"))
        s.stop()

        written.clear()
        s.start()
        self.addCleanup(s.stop)
        self.assertNotIn(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.enable_seq, "".join(written))
        self.assertTrue(s._alternate_buffer)
        self.assertIsNone(s._rows_used)

    def test_start_installs_signal_handlers_and_stop_restores_them(self):
        s = _make_screen()
        s.write = lambda *_a: None
        s.flush = lambda: None

        previous_winch = signal.getsignal(signal.SIGWINCH)
        previous_tstp = signal.getsignal(signal.SIGTSTP)
        previous_cont = signal.signal(signal.SIGCONT, signal.SIG_IGN)
        self.addCleanup(signal.signal, signal.SIGCONT, previous_cont)

        s.start()
        self.assertEqual(s._sigwinch_handler, signal.getsignal(signal.SIGWINCH))
        self.assertEqual(s._sigtstp_handler, signal.getsignal(signal.SIGTSTP))

        s.stop()
        self.assertEqual(previous_winch, signal.getsignal(signal.SIGWINCH))
        self.assertEqual(previous_tstp, signal.getsignal(signal.SIGTSTP))
        # SIGCONT belongs to the application: neither start() nor stop() replaces it.
        self.assertEqual(signal.SIG_IGN, signal.getsignal(signal.SIGCONT))


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

    def _started_screen(self) -> Screen:
        """Start a screen over a pipe whose write end stays open, so reading input finds nothing rather than EOF."""
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = _make_screen(read_fd)
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(s.stop)
        return s

    @mock.patch("os.kill")
    def test_sigtstp_handler_only_requests_a_suspend(self, mock_kill):
        """The handler leaves the terminal alone and wakes the input loop instead."""
        s = self._started_screen()

        signal.getsignal(signal.SIGTSTP)(signal.SIGTSTP, None)

        self.assertTrue(s.started)
        mock_kill.assert_not_called()
        self.assertEqual(b"R", s.get_input_descriptors()[0].recv(16))

    def test_requested_suspend_runs_in_the_input_path(self):
        """The screen is stopped, with the previous SIGTSTP disposition back, before the process suspends."""
        previous_tstp = signal.getsignal(signal.SIGTSTP)
        s = self._started_screen()
        handler = signal.getsignal(signal.SIGTSTP)
        state_at_kill = []

        def fake_kill(pid: int, signum: int) -> None:
            state_at_kill.append((pid, signum, s.started, signal.getsignal(signal.SIGTSTP)))

        handler(signal.SIGTSTP, None)
        with mock.patch("os.kill", side_effect=fake_kill):
            keys, _raw = s.parse_input(None, None, s.get_available_raw_input())

        self.assertEqual([(os.getpid(), signal.SIGTSTP, False, previous_tstp)], state_at_kill)
        self.assertTrue(s.started)
        self.assertEqual(handler, signal.getsignal(signal.SIGTSTP))
        self.assertEqual(["window resize"], keys)

    @mock.patch("os.kill")
    def test_suspend_requested_while_reading_input_is_not_lost(self, mock_kill):
        """A request whose wake-up byte is drained by the same pass is still carried out in that pass."""
        s = self._started_screen()
        handler = signal.getsignal(signal.SIGTSTP)

        def read_while_signalled() -> list[int]:
            handler(signal.SIGTSTP, None)
            return []

        with mock.patch.object(s, "_get_input_codes", side_effect=read_while_signalled):
            s.get_available_raw_input()

        mock_kill.assert_called_once_with(os.getpid(), signal.SIGTSTP)

    def test_suspend_from_a_main_loop_watch_re_hooks_the_event_loop(self):
        """A suspend carried out from the main loop's input watch leaves the loop watching the restarted screen.

        While the process is suspended, the screen is stopped and the loop watches nothing.
        """
        # pylint: disable=protected-access  # the event loop's watches and the screen's pipe have no public view
        s = self._started_screen()
        event_loop = urwid.SelectEventLoop()
        loop = urwid.MainLoop(urwid.SolidFill(), screen=s, event_loop=event_loop, handle_mouse=False)
        loop.start()
        self.addCleanup(loop.stop)
        watched = set(event_loop._watch_files)
        state_at_kill = []

        def fake_kill(pid: int, signum: int) -> None:
            state_at_kill.append((signum, s.started, dict(event_loop._watch_files)))

        signal.getsignal(signal.SIGTSTP)(signal.SIGTSTP, None)
        with mock.patch("os.kill", side_effect=fake_kill):
            # what the event loop calls when the wake-up byte makes the descriptor readable
            event_loop._watch_files[s._resize_pipe_rd.fileno()]()

        self.assertEqual([(signal.SIGTSTP, False, {})], state_at_kill)
        self.assertTrue(s.started)
        self.assertEqual(watched, set(event_loop._watch_files))
        self.assertIn(s._resize_pipe_rd.fileno(), watched)

    @mock.patch("os.kill")
    def test_stop_discards_a_pending_suspend(self, mock_kill):
        """A suspend requested before stop() does not stop the process after the next start()."""
        s = self._started_screen()
        signal.getsignal(signal.SIGTSTP)(signal.SIGTSTP, None)

        s.stop()
        s.start()
        s.get_available_raw_input()

        mock_kill.assert_not_called()


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

    @mock.patch.dict(os.environ, {"TERM": "linux"})
    @mock.patch("os.set_blocking")
    @mock.patch("urwid.display._posix_raw_display.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_start_gpm_tracking_success_sets_nonblocking(self, mock_isfile, mock_popen_cls, mock_set_blocking):
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
        mock_set_blocking.assert_called_once_with(99, False)
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
        mock_proc.__exit__.assert_called_once()

    @mock.patch("os.kill")  # guard: the helper must be stopped through its Popen object only
    def test_stop_gpm_tracking(self, mock_kill):
        """The helper is interrupted, its pipes closed and reaped, and the event loop told to stop watching it."""
        s = _make_screen()
        fake_proc = mock.MagicMock()
        s.gpm_mev = fake_proc
        seen = []
        signals.connect_signal(s, INPUT_DESCRIPTORS_CHANGED, lambda: seen.append(s.gpm_mev))

        s._stop_gpm_tracking()

        fake_proc.send_signal.assert_called_once_with(signal.SIGINT)
        fake_proc.wait.assert_called_once_with(1.0)
        fake_proc.kill.assert_not_called()
        fake_proc.__exit__.assert_called_once()
        mock_kill.assert_not_called()
        self.assertIsNone(s.gpm_mev)
        self.assertEqual([None], seen)

    @mock.patch.dict(os.environ, {"TERM": "linux"})
    @mock.patch("os.kill")  # guard: the helper must be stopped through its Popen object only
    @mock.patch("os.set_blocking")
    @mock.patch("urwid.display._posix_raw_display.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_toggling_mouse_tracking_updates_watched_descriptors(
        self, mock_isfile, mock_popen_cls, mock_set_blocking, mock_kill
    ):
        """Turning mouse tracking on and off at run time adds and removes the helper's output from the watch."""
        fake_proc = mock_popen_cls.return_value = mock.MagicMock()
        s = _make_screen()
        seen = []
        signals.connect_signal(s, INPUT_DESCRIPTORS_CHANGED, lambda: seen.append(s.gpm_mev))

        s.set_mouse_tracking(True)
        s.set_mouse_tracking(False)

        self.assertEqual([fake_proc, None], seen)
        fake_proc.__exit__.assert_called_once()
        mock_kill.assert_not_called()

    @mock.patch.dict(os.environ, {"TERM": "linux"})
    @mock.patch("os.kill")  # guard: the helper must be stopped through its Popen object only
    @mock.patch("os.set_blocking")
    @mock.patch("urwid.display._posix_raw_display.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_helper_that_does_not_exit_is_killed(self, mock_isfile, mock_popen_cls, mock_set_blocking, mock_kill):
        """A helper still running after the timeout is killed rather than waited for without limit."""
        fake_proc = mock_popen_cls.return_value = mock.MagicMock()
        fake_proc.wait.side_effect = subprocess.TimeoutExpired("mev", 1.0)
        s = _make_screen()

        s.set_mouse_tracking(True)
        s.set_mouse_tracking(False)

        fake_proc.kill.assert_called_once_with()
        fake_proc.__exit__.assert_called_once()

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

        expected_button = 1 + escape.MouseBit.DRAG + 32
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

    @mock.patch("os.kill")  # guard: the helper must be stopped through its Popen object only
    def test_malformed_line_stops_tracking(self, mock_kill):
        s = self._screen_with_gpm_line("not,enough,fields\n")
        gpm_mev = s.gpm_mev
        seen = []
        signals.connect_signal(s, INPUT_DESCRIPTORS_CHANGED, lambda: seen.append(True))

        result = s._encode_gpm_event()

        self.assertEqual([], result)
        self.assertIsNone(s.gpm_mev)
        self.assertEqual([True], seen)
        gpm_mev.send_signal.assert_called_once_with(signal.SIGINT)
        mock_kill.assert_not_called()


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestReadRawInput(unittest.TestCase):
    def test_reads_bytes_of_several_writes_in_one_call(self):
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

    @mock.patch("urwid.display._posix_raw_display._INPUT_READ_LIMIT", 4)
    def test_input_beyond_the_read_limit_is_left_for_the_next_pass(self):
        """One call reads at most the limit, so a producer that keeps writing cannot keep it reading."""
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = _make_screen(read_fd)
        s.write = lambda *_a: None
        s.flush = lambda: None
        s.start()
        self.addCleanup(s.stop)

        os.write(write_fd, b"abcdef")

        self.assertEqual(list(b"abcd"), s.get_available_raw_input())
        self.assertEqual(list(b"ef"), s.get_available_raw_input())

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

    def _screen_over_pipe(self, *, bracketed_paste_mode=None, focus_reporting=None, extended_keys=False):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(
            input=os.fdopen(read_fd, "rb", buffering=0),
            output=open(os.devnull, "w"),  # noqa: SIM115
            bracketed_paste_mode=bracketed_paste_mode,
            focus_reporting=focus_reporting,
            extended_keys=extended_keys,
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

    @mock.patch("os.isatty", return_value=True)
    def test_extended_keys_query_both_protocols_before_primary_da(self, mock_isatty):
        s, written = self._screen_over_pipe(extended_keys=True)

        s._detect_terminal_modes()

        self.assertTrue(
            "".join(written).endswith(
                escape.KITTY_KEYBOARD_QUERY + escape.MODIFY_OTHER_KEYS_QUERY + escape.REPORT_DEVICE_ATTRIBUTES
            )
        )

    @mock.patch("os.isatty", return_value=True)
    def test_keyboard_protocols_are_queried_once_while_the_answer_is_pending(self, mock_isatty):
        s, written = self._screen_over_pipe(extended_keys=True)

        s._detect_terminal_modes()
        s._detect_terminal_modes()

        self.assertEqual(1, "".join(written).count(escape.REPORT_DEVICE_ATTRIBUTES))

    @mock.patch("os.isatty", return_value=True)
    def test_keyboard_protocols_are_not_queried_without_extended_keys(self, mock_isatty):
        s, written = self._screen_over_pipe()

        s._detect_terminal_modes()

        output = "".join(written)
        self.assertNotIn(escape.KITTY_KEYBOARD_QUERY, output)
        self.assertNotIn(escape.MODIFY_OTHER_KEYS_QUERY, output)
        self.assertNotIn(escape.REPORT_DEVICE_ATTRIBUTES, output)


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
        self.assertIn(escape.PrivateMode.BRACKETED_PASTE.enable_seq, "".join(written))

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

    def test_past_end_mouse_events_dropped_without_sgr_reports(self):
        """An X10 report at the past-end NUL byte is dropped once the terminal answered 1006 as unsupported."""
        past_end = [*b"\x1b[M", 32, 0, 33]
        inside = [*b"\x1b[M", 32, 255, 33]
        release = [*b"\x1b[M", 35, 0, 33]
        for sgr, expected in (
            (None, [("mouse press", 1, 223, 0), ("mouse press", 1, 222, 0), ("mouse release", 0, 223, 0)]),
            (False, [("mouse press", 1, 222, 0), ("mouse release", 0, 223, 0)]),
        ):
            with self.subTest(sgr=sgr):
                s, _written = self._screen()
                s.modes.mouse_sgr_mode = sgr
                keys, _raw = s.parse_input(None, None, [*past_end, *inside, *release])
                self.assertEqual(expected, keys)

    def test_sgr_reply_applies_to_the_mouse_events_after_it(self):
        s, _written = self._screen()

        for value in (0, 4):
            with self.subTest(value=value):
                reply = f"\x1b[?1006;{value}$y\x1b[M".encode()
                keys, _raw = s.parse_input(None, None, [*reply, 32, 0, 33, ord("a")])
                self.assertEqual(["a"], keys)


@unittest.skipIf(IS_WINDOWS, "_posix_raw_display is not importable on Windows (no fcntl/termios/tty)")
class TestKeyboardProtocol(unittest.TestCase):
    """With extended_keys, the replies up to the Primary DA reply decide which keyboard protocol is turned on."""

    KITTY_REPLY = b"\x1b[?0u"
    DEVICE_ATTRIBUTES_REPLY = b"\x1b[?62;22c"

    def _queried_screen(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(
            input=os.fdopen(read_fd, "rb", buffering=0),
            output=open(os.devnull, "w"),  # noqa: SIM115
            extended_keys=True,
        )
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None
        with mock.patch("os.isatty", return_value=True):
            s._detect_terminal_modes()
        written.clear()
        # as start() leaves it: the replies are read while the screen runs
        s._started = True
        return s, written

    def test_kitty_keyboard_protocol_is_pushed_and_decoded(self):
        s, written = self._queried_screen()

        keys, _raw = s.parse_input(None, None, [*self.KITTY_REPLY, *self.DEVICE_ATTRIBUTES_REPLY])

        self.assertEqual([], keys)
        self.assertTrue(s.modes.kitty_keyboard)
        self.assertEqual([escape.KITTY_KEYBOARD_PUSH], written)
        keys, _raw = s.parse_input(None, None, [*b"\x1b[P", *b"\x1b[13;5u"])
        self.assertEqual(["f1", "ctrl enter"], keys)

        written.clear()
        s._disable_keyboard_protocol()
        self.assertEqual([escape.KITTY_KEYBOARD_POP], written)
        keys, _raw = s.parse_input(None, None, list(b"\x1b[P"))
        self.assertEqual(["delete"], keys)

    def test_modify_other_keys_is_turned_on_and_its_reported_value_restored(self):
        for reply, restore in ((b"\x1b[>4;1m", "\x1b[>4;1m"), (b"\x1b[>4m", "\x1b[>4m")):
            with self.subTest(reply=reply):
                s, written = self._queried_screen()

                keys, _raw = s.parse_input(None, None, [*reply, *self.DEVICE_ATTRIBUTES_REPLY])

                self.assertEqual([], keys)
                self.assertFalse(s.modes.kitty_keyboard)
                self.assertTrue(s.modes.modify_other_keys)
                self.assertEqual([escape.MODIFY_OTHER_KEYS_ON], written)
                written.clear()
                s._disable_keyboard_protocol()
                self.assertEqual([restore], written)

    def test_kitty_keyboard_protocol_is_preferred_to_modify_other_keys(self):
        s, written = self._queried_screen()

        s.parse_input(None, None, [*self.KITTY_REPLY, *b"\x1b[>4;0m", *self.DEVICE_ATTRIBUTES_REPLY])

        self.assertEqual([escape.KITTY_KEYBOARD_PUSH], written)

    def test_no_reply_before_primary_da_turns_nothing_on(self):
        s, written = self._queried_screen()

        s.parse_input(None, None, list(self.DEVICE_ATTRIBUTES_REPLY))

        self.assertIs(False, s.modes.kitty_keyboard)
        self.assertIs(False, s.modes.modify_other_keys)
        self.assertEqual([], written)

    def test_replies_split_across_reads_are_collected_until_primary_da(self):
        s, written = self._queried_screen()

        keys, _raw = s.parse_input(None, None, [ord("a"), *self.KITTY_REPLY])
        self.assertEqual(["a"], keys)
        self.assertEqual([], written)
        keys, _raw = s.parse_input(None, None, [*self.DEVICE_ATTRIBUTES_REPLY, ord("b")])

        self.assertEqual(["b"], keys)
        self.assertEqual([escape.KITTY_KEYBOARD_PUSH], written)

    def test_reply_out_of_sync_with_the_queries_is_dropped(self):
        """A reply after the Primary DA reply, or with no query sent, did not answer urwid's query."""
        s, written = self._queried_screen()

        keys, _raw = s.parse_input(None, None, [*self.DEVICE_ATTRIBUTES_REPLY, *self.KITTY_REPLY, ord("a")])
        self.assertEqual(["a"], keys)
        keys, _raw = s.parse_input(None, None, [*self.DEVICE_ATTRIBUTES_REPLY, *b"\x1b[>4;1m"])

        self.assertEqual([], keys)
        self.assertIs(False, s.modes.kitty_keyboard)
        self.assertIs(False, s.modes.modify_other_keys)
        self.assertEqual([], written)

    def test_reply_read_while_stopped_turns_nothing_on(self):
        """Nothing would pop the flags pushed while the screen is stopped."""
        s, written = self._queried_screen()
        s._started = False

        s.parse_input(None, None, [*self.KITTY_REPLY, *self.DEVICE_ATTRIBUTES_REPLY])

        self.assertTrue(s.modes.kitty_keyboard)
        self.assertEqual([], written)

    @mock.patch("os.isatty", return_value=True)
    def test_queries_are_sent_again_after_a_stop_discarded_their_replies(self, mock_isatty):
        s, written = self._queried_screen()

        s._disable_keyboard_protocol()
        s._detect_terminal_modes()

        self.assertIn(escape.KITTY_KEYBOARD_QUERY + escape.MODIFY_OTHER_KEYS_QUERY, "".join(written))
        self.assertTrue(s._keyboard_query_pending)

    def test_reply_for_another_key_modifier_resource_is_ignored(self):
        s, written = self._queried_screen()

        s.parse_input(None, None, [*b"\x1b[>1;2m", *self.DEVICE_ATTRIBUTES_REPLY])

        self.assertIs(False, s.modes.modify_other_keys)
        self.assertEqual([], written)

    def test_start_turns_a_resolved_protocol_on_and_stop_restores_it_on_the_alternate_screen(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        s = Screen(
            input=os.fdopen(read_fd, "rb", buffering=0),
            output=open(os.devnull, "w"),  # noqa: SIM115
            extended_keys=True,
        )
        s.modes.kitty_keyboard = True
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None

        for _ in range(2):
            written.clear()
            s.start()
            output = "".join(written)
            self.assertEqual(1, output.count(escape.KITTY_KEYBOARD_PUSH))
            self.assertLess(
                output.index(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.enable_seq),
                output.index(escape.KITTY_KEYBOARD_PUSH),
            )

            written.clear()
            s.stop()
            output = "".join(written)
            self.assertEqual(1, output.count(escape.KITTY_KEYBOARD_POP))
            self.assertLess(
                output.index(escape.KITTY_KEYBOARD_POP),
                output.index(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.disable_seq),
            )

    def test_resolved_protocol_stays_off_without_extended_keys(self):
        s = _make_screen()
        s.modes.kitty_keyboard = True
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None

        s.start()
        s.stop()

        self.assertNotIn(escape.KITTY_KEYBOARD_PUSH, "".join(written))


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

    @mock.patch("urwid.display._posix_raw_display.Screen._start_gpm_tracking")
    def test_stop_and_restart_keeps_mouse_tracking(self, _mock_start_gpm_tracking: mock.Mock) -> None:
        """A restarted screen turns on the mouse tracking the application enabled before the stop."""
        s = _make_screen()
        written: list[str] = []
        self.addCleanup(s.stop)
        with mock.patch.object(s, "write", written.append):
            s.start()
            s.set_mouse_tracking(True)

            s.stop()
            self.assertIn(escape.MOUSE_TRACKING_OFF, "".join(written))
            written.clear()
            s.start()

        self.assertIn(escape.MOUSE_TRACKING_ON, "".join(written))


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

    @mock.patch("fcntl.ioctl", side_effect=OSError)
    def test_falls_back_to_80x24_when_ioctl_fails(self, mock_ioctl):
        """An output that is not a terminal reports 80 columns by 24 rows."""
        s = _make_screen()

        cols, rows = s.get_cols_rows()

        self.assertEqual((80, 24), (cols, rows))
        self.assertEqual(24, s.maxrow)


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
