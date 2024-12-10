# Urwid raw display module
#    Copyright (C) 2004-2009  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/


"""
Direct terminal UI implementation
"""

from __future__ import annotations

import contextlib
import functools
import logging
import selectors
import socket
import sys
import threading
import typing
from ctypes import byref
from ctypes.wintypes import DWORD

from urwid import signals

from . import _raw_display_base, _win32, escape
from .common import INPUT_DESCRIPTORS_CHANGED

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from urwid.event_loop import EventLoop


class Screen(_raw_display_base.Screen):
    _term_input_file: socket.socket

    def __init__(
        self,
        input: socket.socket | None = None,  # noqa: A002  # pylint: disable=redefined-builtin
        output: typing.TextIO = sys.stdout,
    ) -> None:
        """Initialize a screen that directly prints escape codes to an output
        terminal.
        """
        if input is None:
            input, self._send_input = socket.socketpair()  # noqa: A001

        super().__init__(input, output)

    _dwOriginalOutMode = None
    _dwOriginalInMode = None

    def _start(self, alternate_buffer: bool = True) -> None:
        """
        Initialize the screen and input mode.

        alternate_buffer -- use alternate screen buffer
        """
        if alternate_buffer:
            self.write(escape.SWITCH_TO_ALTERNATE_BUFFER)
            self._rows_used = None
        else:
            self._rows_used = 0

        handle_out = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
        handle_in = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)
        self._dwOriginalOutMode = DWORD()
        self._dwOriginalInMode = DWORD()
        _win32.GetConsoleMode(handle_out, byref(self._dwOriginalOutMode))
        _win32.GetConsoleMode(handle_in, byref(self._dwOriginalInMode))
        # TODO: Restore on exit

        dword_out_mode = DWORD(
            self._dwOriginalOutMode.value
            | _win32.ENABLE_VIRTUAL_TERMINAL_PROCESSING
            | _win32.DISABLE_NEWLINE_AUTO_RETURN
        )
        dword_in_mode = DWORD(
            self._dwOriginalInMode.value | _win32.ENABLE_WINDOW_INPUT | _win32.ENABLE_VIRTUAL_TERMINAL_INPUT
        )

        if not (ok := _win32.SetConsoleMode(handle_out, dword_out_mode)):
            raise RuntimeError(f"ConsoleMode set failed for output. Err: {ok!r}")

        if not (ok := _win32.SetConsoleMode(handle_in, dword_in_mode)):
            raise RuntimeError(f"ConsoleMode set failed for input. Err: {ok!r}")
        self._alternate_buffer = alternate_buffer
        self._next_timeout = self.max_wait

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
        # restore mouse tracking to previous state
        self._mouse_tracking(self._mouse_tracking_enabled)

        return super()._start()

    def _stop(self) -> None:
        """
        Restore the screen.
        """
        self.clear()

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

        self._stop_mouse_restore_buffer()

        handle_out = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
        handle_in = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)

        if not (ok := _win32.SetConsoleMode(handle_out, self._dwOriginalOutMode)):
            raise RuntimeError(f"ConsoleMode set failed for output. Err: {ok!r}")

        if not (ok := _win32.SetConsoleMode(handle_in, self._dwOriginalInMode)):
            raise RuntimeError(f"ConsoleMode set failed for input. Err: {ok!r}")

        super()._stop()

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """
        Remove any hooks added by hook_event_loop.
        """
        if self._input_thread is not None:
            self._input_thread.should_exit = True

            with contextlib.suppress(RuntimeError):
                self._input_thread.join(5)

            self._input_thread = None

        for handle in self._current_event_loop_handles:
            event_loop.remove_watch_file(handle)

        if self._input_timeout:
            event_loop.remove_alarm(self._input_timeout)
            self._input_timeout = None

    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[list[str], list[int]], typing.Any],
    ) -> None:
        """
        Register the given callback with the event loop, to be called with new
        input whenever it's available.  The callback should be passed a list of
        processed keys and a list of unprocessed keycodes.

        Subclasses may wish to use parse_input to wrap the callback.
        """
        self._input_thread = ReadInputThread(self._send_input, lambda: self._sigwinch_handler(28))
        self._input_thread.start()
        if hasattr(self, "get_input_nonblocking"):
            wrapper = self._make_legacy_input_wrapper(event_loop, callback)
        else:

            @functools.wraps(callback)
            def wrapper() -> tuple[list[str], typing.Any] | None:
                return self.parse_input(event_loop, callback, self.get_available_raw_input())

        fds = self.get_input_descriptors()
        handles = [event_loop.watch_file(fd if isinstance(fd, int) else fd.fileno(), wrapper) for fd in fds]
        self._current_event_loop_handles = handles

    _input_thread: ReadInputThread | None = None

    def _read_raw_input(self, timeout: int) -> bytearray:
        ready = self._wait_for_input_ready(timeout)

        fd = self._input_fileno()
        chars = bytearray()

        if fd is None or fd not in ready:
            return chars

        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)

            while selector.select(0):
                chars.extend(self._term_input_file.recv(1024))

            return chars

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows)."""
        y, x = super().get_cols_rows()
        with contextlib.suppress(OSError):  # Term size could not be determined
            if hasattr(self._term_output_file, "fileno"):
                if self._term_output_file != sys.stdout:
                    raise RuntimeError("Unexpected terminal output file")
                handle = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
                info = _win32.CONSOLE_SCREEN_BUFFER_INFO()

                if _win32.GetConsoleScreenBufferInfo(handle, byref(info)):
                    # Fallback will be used in case of term size could not be determined
                    y, x = info.dwSize.Y, info.dwSize.X

        self.maxrow = y
        return x, y


class ReadInputThread(threading.Thread):
    name = "urwid Windows input reader"
    daemon = True
    should_exit: bool = False

    def __init__(
        self,
        input_socket: socket.socket,
        resize: Callable[[], typing.Any],
    ) -> None:
        self._input = input_socket
        self._resize = resize
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        super().__init__()

    def run(self) -> None:
        hIn = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)
        MAX = 2048

        read = DWORD(0)
        arrtype = _win32.INPUT_RECORD * MAX
        input_records = arrtype()

        while True:
            _win32.ReadConsoleInputW(hIn, byref(input_records), MAX, byref(read))
            if self.should_exit:
                return
            for i in range(read.value):
                inp = input_records[i]
                if inp.EventType == _win32.EventType.KEY_EVENT:
                    if not inp.Event.KeyEvent.bKeyDown:
                        continue

                    input_data = inp.Event.KeyEvent.uChar.UnicodeChar
                    # On Windows atomic press/release of modifier keys produce phantom input with code NULL.
                    # This input cannot be decoded and should be handled as garbage.
                    input_bytes = input_data.encode("utf-8")
                    if input_bytes != b"\x00":
                        self._input.send(input_bytes)

                elif inp.EventType == _win32.EventType.WINDOW_BUFFER_SIZE_EVENT:
                    self._resize()
                else:
                    pass  # TODO: handle mouse events


def _test():
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
