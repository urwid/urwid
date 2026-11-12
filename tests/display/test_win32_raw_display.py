"""Tests for the Windows console input of the raw display."""

from __future__ import annotations

import socket
import sys
import time
import typing
import unittest
from unittest import mock

from urwid import signals
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED, InputClosedError

if typing.TYPE_CHECKING:
    import ctypes

IS_WINDOWS = sys.platform == "win32"

try:
    from urwid.display import _win32, _win32_raw_display
except ImportError:  # the console API is bound through ctypes.windll, which exists only on Windows
    _win32 = _win32_raw_display = None


def _key_record(char: str) -> typing.Any:
    """Build a key-down console input record for one UTF-16 code unit."""
    record = _win32.INPUT_RECORD()
    record.EventType = _win32.EventType.KEY_EVENT
    record.Event.KeyEvent.bKeyDown = 1
    record.Event.KeyEvent.uChar.UnicodeChar = char
    return record


def _resize_record() -> typing.Any:
    """Build a console screen buffer size change record."""
    record = _win32.INPUT_RECORD()
    record.EventType = _win32.EventType.WINDOW_BUFFER_SIZE_EVENT
    return record


@unittest.skipUnless(IS_WINDOWS, "_win32_raw_display needs the Windows console API")
class TestReadInputThread(unittest.TestCase):
    """The background thread that turns console key events into input bytes."""

    def _run_reads(
        self,
        *batches: list[typing.Any] | None,
        read_succeeds: bool = True,
        resize: mock.Mock | None = None,
        window_sizes: tuple[tuple[int, int] | None, ...] = (None,),
        start_window_size: tuple[int, int] | None = None,
        sent: list[typing.Any] | None = None,
    ) -> list[typing.Any]:
        """Run the reader over console reads returning *batches*, and return what it sent.

        A batch holds key characters and console input records; a batch of None is a wait that times out.
        The window size reported to the reader goes through *window_sizes*, then stays at the last one.
        What is sent is appended to *sent*, a new list by default.
        """
        sent = [] if sent is None else sent
        sizes = iter(window_sizes)
        thread = _win32_raw_display.ReadInputThread(
            mock.Mock(sendall=sent.append),
            resize or mock.Mock(),
            window_size=lambda: next(sizes, window_sizes[-1]),
            start_window_size=start_window_size,
        )
        pending = list(batches)

        def wait(_handle: int, _timeout: int) -> int:
            if not pending:
                thread.should_exit = True
                return _win32.WAIT_TIMEOUT
            if pending[0] is None:
                pending.pop(0)
                return _win32.WAIT_TIMEOUT
            return _win32.WAIT_OBJECT_0

        def read_console(_handle: int, records: typing.Any, _size: int, read_count: typing.Any) -> bool:
            batch = pending.pop(0)
            assert batch is not None  # a None batch is a wait that times out, which reads nothing
            for index, item in enumerate(batch):
                records[index] = _key_record(item) if isinstance(item, str) else item
            read_count.value = len(batch)
            return read_succeeds

        with (
            mock.patch.object(_win32_raw_display, "byref", side_effect=lambda value: value),
            mock.patch.object(_win32, "GetStdHandle", return_value=1),
            mock.patch.object(_win32, "WaitForSingleObject", side_effect=wait),
            mock.patch.object(_win32, "ReadConsoleInputW", side_effect=read_console),
        ):
            thread.run()
        return sent

    def test_character_split_across_reads_is_joined(self):
        """A character outside the BMP whose two UTF-16 halves arrive in separate reads is sent whole."""
        self.assertEqual([b"a", "\U0001f600b".encode()], self._run_reads(["a", "\ud83d"], ["\ude00", "b"]))

    def test_lone_surrogate_and_phantom_nul_do_not_stop_the_reader(self):
        """A half of a pair with no other half is replaced, and modifier-key NUL input is dropped."""
        self.assertEqual(["�x".encode(), b"y"], self._run_reads(["\ude00", "\x00", "x"], ["y"]))

    def test_failed_read_ends_the_reader(self):
        """A failing console read ends the thread instead of looping over stale records."""
        self.assertEqual([], self._run_reads(["a"], ["b"], read_succeeds=False))

    def test_keys_and_a_resize_of_one_read_keep_their_order(self) -> None:
        """Send the keys typed before a resize record, report the resize, then send the keys typed after it."""
        report = _win32_raw_display.escape.window_size_report(100, 30).encode()
        for label, batch, window_sizes, expected in (
            ("keys around the resize", ["a", _resize_record(), "b"], ((100, 30),), [b"a", report, b"b"]),
            ("size unread: reported out of band", ["a", _resize_record(), "b"], (None,), [b"a", "resize", b"b"]),
            (
                "a character split by the resize",
                ["\ud83d", _resize_record(), "\ude00"],
                ((100, 30),),
                [report, "\U0001f600".encode()],
            ),
        ):
            with self.subTest(label):
                events: list[typing.Any] = []
                resize = mock.Mock(side_effect=lambda events=events: events.append("resize"))

                self._run_reads(batch, resize=resize, window_sizes=window_sizes, sent=events)

                self.assertEqual(expected, events)

    def test_resize_is_reported_for_a_buffer_or_a_window_change(self) -> None:
        """A buffer size event or a new window size reports one resize; an unchanged or unread size reports none.

        A resize is counted whether it is written into the input as a window size report or reported out of band.
        """
        for label, batches, window_sizes, start_size, resizes in (
            ("buffer size event", ([_resize_record(), "a"],), ((80, 24),), None, 1),
            ("window change while idle", (None, None), ((80, 24), (80, 24), (80, 30)), None, 1),
            ("window change with a buffer size event", ([_resize_record()],), ((80, 24), (100, 30)), None, 1),
            (
                "window change after a buffer size event",
                ([_resize_record()],),
                ((80, 24), (100, 30), (120, 40)),
                None,
                2,
            ),
            ("unchanged window", (None, ["a"]), ((80, 24),), None, 0),
            ("no console window", (None,), (None,), None, 0),
            ("failed size query", (None, None), ((80, 24), None, (80, 24)), None, 0),
            ("window differs from the start size", (None,), ((100, 30),), (80, 24), 1),
        ):
            with self.subTest(label):
                resize = mock.Mock()
                sent = self._run_reads(*batches, resize=resize, window_sizes=window_sizes, start_window_size=start_size)
                reports = [data for data in sent if data.startswith(b"\x1b[48;")]
                self.assertEqual(resizes, resize.call_count + len(reports))


@unittest.skipUnless(IS_WINDOWS, "_win32_raw_display needs the Windows console API")
class TestScreenInput(unittest.TestCase):
    """The Windows screen's handling of its input thread and input socket."""

    def test_stop_ends_the_console_reader_and_unhook_keeps_it(self):
        """The reader ends with the screen, not with each re-hook of the event loop."""
        s = _win32_raw_display.Screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        reader = mock.Mock()

        with mock.patch.object(s, "_input_thread", reader), mock.patch.object(s, "_started", True):
            s.unhook_event_loop(mock.Mock())
            reader.join.assert_not_called()

            s.stop()

        self.assertTrue(reader.should_exit)
        reader.join.assert_called_once()

    def test_stop_restores_both_console_modes_when_a_step_fails(self):
        """Set both console modes back and stop the reader when a write or the output mode fails.

        The failure is still raised.
        """
        for failure, write_error, mode_results in (
            ("write", OSError(9, "bad file descriptor"), [1, 1]),
            ("output mode", None, [0, 1]),
        ):
            with self.subTest(failure=failure):
                s = _win32_raw_display.Screen()
                s.write = mock.Mock(side_effect=write_error)
                s.flush = lambda: None
                s.modes.bracketed_paste = True
                s._dwOriginalOutMode, s._dwOriginalInMode = 1, 2
                reader = mock.Mock()

                with (
                    mock.patch.object(s, "_input_thread", reader),
                    mock.patch.object(s, "_started", True),
                    mock.patch.object(_win32, "GetStdHandle", side_effect=["out", "in"]),
                    mock.patch.object(_win32, "SetConsoleMode", side_effect=mode_results) as set_mode,
                    self.assertRaises(OSError if write_error else RuntimeError),
                ):
                    s.stop()

                self.assertEqual([mock.call("out", 1), mock.call("in", 2)], set_mode.call_args_list)
                self.assertTrue(reader.should_exit)

    def test_no_reader_outlives_a_stop_that_re_hooks_the_screen(self):
        """A main loop re-hooking the screen while it stops does not leave a reader running."""
        readers: list[mock.Mock] = []
        s = _win32_raw_display.Screen()
        s.write = lambda *_a: None
        s.flush = lambda: None
        event_loop = mock.Mock()
        signals.connect_signal(
            s,
            INPUT_DESCRIPTORS_CHANGED,
            lambda: (s.unhook_event_loop(event_loop), s.hook_event_loop(event_loop, mock.Mock())),
        )

        with (
            mock.patch.object(
                _win32_raw_display,
                "ReadInputThread",
                side_effect=lambda *_a, **_kw: readers.append(mock.Mock(should_exit=False)) or readers[-1],
            ),
            mock.patch.object(s, "_started", True),
        ):
            s.hook_event_loop(event_loop, mock.Mock())
            s.stop()
            signals.emit_signal(s, INPUT_DESCRIPTORS_CHANGED)  # a re-notification after stop() starts no reader

        self.assertTrue(readers)
        self.assertTrue(all(reader.should_exit for reader in readers))

    def test_start_reports_a_window_resized_while_stopped(self) -> None:
        """Starting the reader reports a window whose size differs from the last drawn size, before the next draw."""
        for label, last_size, window, resized in (
            ("resized while stopped", (80, 24), (100, 30), True),
            ("unchanged", (100, 30), (100, 30), False),
            ("never drawn", None, (100, 30), False),
            ("no console window", (80, 24), None, False),
        ):
            with self.subTest(label):
                s = _win32_raw_display.Screen()
                with (
                    mock.patch.object(_win32_raw_display, "ReadInputThread") as reader_class,
                    mock.patch.object(s, "_console_window_size", return_value=window) as window_size,
                    mock.patch.object(s, "_last_cols_rows", last_size),
                    mock.patch.object(s, "_wake_input_loop"),
                ):
                    s._start_input_thread()

                self.assertEqual(resized, s._resized)
                self.assertEqual(window_size, reader_class.call_args.kwargs["window_size"])
                self.assertEqual(window, reader_class.call_args.kwargs["start_window_size"])

    @mock.patch("urwid.display._raw_display_base._INPUT_READ_LIMIT", 4)
    def test_input_beyond_the_read_limit_is_left_for_the_next_pass(self):
        """One call stops reading once the limit is in, so a producer that keeps writing cannot keep it reading."""
        input_socket, peer = socket.socketpair()
        self.addCleanup(input_socket.close)
        self.addCleanup(peer.close)
        s = _win32_raw_display.Screen(input=input_socket)
        data = bytes(range(256)) * 6  # more than one 1024-byte chunk past the limit
        peer.sendall(data)
        # a socket pair on Windows is a TCP loopback connection, which can deliver the data in parts
        for _ in range(100):
            if len(input_socket.recv(len(data), socket.MSG_PEEK)) == len(data):
                break
            time.sleep(0.01)

        with mock.patch.object(s, "_started", True):
            first = s.get_available_raw_input()
            rest = s.get_available_raw_input()

        self.assertLess(len(first), 4 + 1024)
        self.assertEqual(list(data), first + rest)

    @mock.patch("urwid.display._raw_display_base._INPUT_READ_LIMIT", 4)
    def test_resize_is_reported_after_the_input_read_before_it(self):
        """Report a resize only once the input that was waiting when it came is read, so keys keep their layout."""
        input_socket, peer = socket.socketpair()
        self.addCleanup(input_socket.close)
        self.addCleanup(peer.close)
        s = _win32_raw_display.Screen(input=input_socket)
        data = b"a" * 1500  # more than one 1024-byte chunk past the limit
        peer.sendall(data)
        # a socket pair on Windows is a TCP loopback connection, which can deliver the data in parts
        for _ in range(100):
            if len(input_socket.recv(len(data), socket.MSG_PEEK)) == len(data):
                break
            time.sleep(0.01)
        s._sigwinch_handler()

        with mock.patch.object(s, "_started", True):
            first = s.get_input()
            rest = s.get_input()

        self.assertEqual(0, first.count("window resize"))
        self.assertEqual([*"a" * len(data), "window resize"], first + rest)

    def test_resize_from_the_console_reader_keeps_its_place_among_the_keys(self):
        """Report a resize the console reader wrote into the input at its place among the keys."""
        s = _win32_raw_display.Screen()
        report = _win32_raw_display.escape.window_size_report(100, 30).encode()
        s._send_input.sendall(b"a" + report + b"b")

        with mock.patch.object(s, "_started", True):
            self.assertEqual(["a", "window resize", "b"], s.get_input())

    def test_every_console_reader_report_is_a_resize(self):
        """Report a resize for each report, also of the size already read: the reader writes one per change.

        The console has the new size before the report is read, and the application may have read it already.
        """
        for in_band_resize in (None, False):
            with self.subTest(in_band_resize=in_band_resize):
                s = _win32_raw_display.Screen(in_band_resize=in_band_resize)
                self.assertIs(False, s.modes.in_band_resize)  # the console is not queried for mode 2048
                s._last_cols_rows = (100, 30)
                s._send_input.sendall(b"a" + _win32_raw_display.escape.window_size_report(100, 30).encode() + b"b")

                with mock.patch.object(s, "_started", True):
                    self.assertEqual(["a", "window resize", "b"], s.get_input())

    def test_closed_input_socket_raises(self):
        """Input from a caller's socket whose other end closed raises instead of spinning."""
        input_socket, peer = socket.socketpair()
        self.addCleanup(input_socket.close)
        s = _win32_raw_display.Screen(input=input_socket)
        peer.close()

        with mock.patch.object(s, "_started", True), self.assertRaises(InputClosedError):
            s.get_available_raw_input()


@unittest.skipUnless(IS_WINDOWS, "_win32_raw_display needs the Windows console API")
class TestGetColsRows(unittest.TestCase):
    """The Windows screen's terminal size."""

    def test_falls_back_to_80x24_for_output_other_than_stdout(self):
        """An output stream without a console buffer keeps the 80 columns by 24 rows fallback."""
        s = _win32_raw_display.Screen()

        with mock.patch.object(s, "_term_output_file", mock.Mock()):
            cols, rows = s.get_cols_rows()

        self.assertEqual((80, 24), (cols, rows))
        self.assertEqual(24, s.maxrow)
        self.assertEqual((80, 24), s._last_cols_rows)  # a restart compares the console with the size drawn

    def test_uses_the_visible_window_of_the_console_buffer(self):
        """The size is the visible window, not the whole buffer with its scrollback."""
        info = _win32.CONSOLE_SCREEN_BUFFER_INFO()
        info.dwSize.X, info.dwSize.Y = 120, 9001
        info.srWindow.Left, info.srWindow.Top, info.srWindow.Right, info.srWindow.Bottom = 10, 8950, 109, 8979
        s = _win32_raw_display.Screen()

        with (
            mock.patch.object(s, "_term_output_file", sys.stdout),
            mock.patch.object(_win32, "GetStdHandle"),
            mock.patch.object(_win32, "CONSOLE_SCREEN_BUFFER_INFO", return_value=info),
            mock.patch.object(_win32, "GetConsoleScreenBufferInfo", return_value=1),
        ):
            cols, rows = s.get_cols_rows()

        self.assertEqual((100, 30), (cols, rows))
        self.assertEqual(30, s.maxrow)
        self.assertEqual((100, 30), s._last_cols_rows)


@unittest.skipUnless(IS_WINDOWS, "_win32_raw_display needs the Windows console API")
class TestTitle(unittest.TestCase):
    """The window title of a Windows console, which has no title stack."""

    def test_console_title_is_set_and_given_back_through_the_console_api(self) -> None:
        """A console gets the title through the console API, and its own title back; nothing is written."""
        for label, old_title, restored in (("title read", "shell", ["shell"]), ("read failed", "", [])):
            with self.subTest(label):
                s = _win32_raw_display.Screen()
                written: list[str] = []
                s.write = written.append
                s.flush = lambda: None
                titles: list[str] = []

                def get_title(buffer: ctypes.Array[ctypes.c_wchar], _size: int, title: str = old_title) -> int:
                    buffer.value = title
                    return len(title)

                with (
                    mock.patch.object(_win32, "GetConsoleTitleW", side_effect=get_title),
                    mock.patch.object(_win32, "SetConsoleTitleW", side_effect=titles.append),
                    mock.patch.object(s, "_console_mode_active", True),
                    mock.patch.object(s, "_started", True),
                ):
                    s.set_title("app")
                    s.set_title(None)

                self.assertEqual(["app", *restored], titles)
                self.assertEqual([], written)

    def test_title_outside_a_console_uses_the_title_stack(self) -> None:
        """Without a console, such as in a terminal emulator running over a pipe, the escape sequences are written."""
        s = _win32_raw_display.Screen()
        s.term = "xterm-256color"
        written: list[str] = []
        s.write = written.append
        s.flush = lambda: None

        with (
            mock.patch.object(_win32, "SetConsoleTitleW") as set_title,
            mock.patch.object(s, "_started", True),
        ):
            s.set_title("app")
            s.set_title(None)

        set_title.assert_not_called()
        self.assertEqual("\x1b[22;0t\x1b]2;app\x07\x1b[23;0t", "".join(written))
