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


@unittest.skipUnless(IS_WINDOWS, "_win32_raw_display needs the Windows console API")
class TestReadInputThread(unittest.TestCase):
    """The background thread that turns console key events into input bytes."""

    def _run_reads(self, *batches: list[str], read_succeeds: bool = True) -> list[bytes]:
        """Run the reader over console reads returning *batches* of key characters, and return what it sent."""
        sent: list[bytes] = []
        thread = _win32_raw_display.ReadInputThread(mock.Mock(sendall=sent.append), mock.Mock())
        pending = list(batches)

        def wait(_handle: int, _timeout: int) -> int:
            if not pending:
                thread.should_exit = True
                return _win32.WAIT_TIMEOUT
            return _win32.WAIT_OBJECT_0

        def read_console(_handle: int, records: typing.Any, _size: int, read_count: typing.Any) -> bool:
            batch = pending.pop(0)
            for index, char in enumerate(batch):
                records[index] = _key_record(char)
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
                side_effect=lambda *_a: readers.append(mock.Mock(should_exit=False)) or readers[-1],
            ),
            mock.patch.object(s, "_started", True),
        ):
            s.hook_event_loop(event_loop, mock.Mock())
            s.stop()

        self.assertTrue(readers)
        self.assertTrue(all(reader.should_exit for reader in readers))

    def test_closed_input_socket_raises(self):
        """Input from a caller's socket whose other end closed raises instead of spinning."""
        input_socket, peer = socket.socketpair()
        self.addCleanup(input_socket.close)
        s = _win32_raw_display.Screen(input=input_socket)
        peer.close()

        with mock.patch.object(s, "_started", True), self.assertRaises(RuntimeError):
            s.get_available_raw_input()
