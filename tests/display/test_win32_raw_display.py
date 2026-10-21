"""Tests for the Windows console input of the raw display."""

from __future__ import annotations

import socket
import sys
import typing
import unittest
from unittest import mock

from urwid import signals
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED

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
    ) -> list[bytes]:
        """Run the reader over console reads returning *batches*, and return what it sent.

        A batch holds key characters and console input records; a batch of None is a wait that times out.
        The window size reported to the reader goes through *window_sizes*, then stays at the last one.
        """
        sent: list[bytes] = []
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

    def test_resize_is_reported_for_a_buffer_or_a_window_change(self) -> None:
        """A buffer size event or a new window size reports one resize; an unchanged or unread size reports none."""
        for label, batches, window_sizes, start_size, resizes in (
            ("buffer size event", ([_resize_record(), "a"],), ((80, 24),), None, 1),
            ("window change while idle", (None, None), ((80, 24), (80, 24), (80, 30)), None, 1),
            ("window change with a buffer size event", ([_resize_record()],), ((80, 24), (100, 30)), None, 1),
            ("unchanged window", (None, ["a"]), ((80, 24),), None, 0),
            ("no console window", (None,), (None,), None, 0),
            ("failed size query", (None, None), ((80, 24), None, (80, 24)), None, 0),
            ("window differs from the start size", (None,), ((100, 30),), (80, 24), 1),
        ):
            with self.subTest(label):
                resize = mock.Mock()
                self._run_reads(*batches, resize=resize, window_sizes=window_sizes, start_window_size=start_size)
                self.assertEqual(resizes, resize.call_count)


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

    def test_closed_input_socket_raises(self):
        """Input from a caller's socket whose other end closed raises instead of spinning."""
        input_socket, peer = socket.socketpair()
        self.addCleanup(input_socket.close)
        s = _win32_raw_display.Screen(input=input_socket)
        peer.close()

        with mock.patch.object(s, "_started", True), self.assertRaises(RuntimeError):
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
