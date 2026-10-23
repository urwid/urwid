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


"""Direct terminal UI implementation."""

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

# milliseconds the console reader waits for input before checking whether it has to stop
_INPUT_POLL_MS = 100

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from urwid.event_loop import EventLoop

    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _DecodedInput = list[str | _MouseInput | _CursorPosition]


class Screen(_raw_display_base.Screen):
    """Raw screen backend that drives a real Windows console."""

    _term_input_file: socket.socket
    # Only set for the socket pair created here: an input given by the caller is fed by the caller.
    _send_input: socket.socket | None = None

    def __init__(
        self,
        input: socket.socket | None = None,  # noqa: A002
        output: _raw_display_base.TextWriter = sys.stdout,
        bracketed_paste_mode: bool | None = None,
        focus_reporting: bool | None = None,
        extended_keys: bool = False,
    ) -> None:
        """Initialize a screen that directly prints escape codes to an output terminal.

        :param input: the socket the console input is read from.
            None (default) creates a socket pair and forwards the console input into it.
        :param output: the terminal output, which the escape codes are written to.
        :param bracketed_paste_mode: enable bracketed paste (`begin`/`end paste` keystrokes).
            None (default) auto-detects via DECRQM and enables it once confirmed supported;
            pass True/False to force it without probing.
        :param focus_reporting: enable focus reporting (`focus in`/`focus out` keystrokes).
            None (default) auto-detects via DECRQM and enables it once confirmed supported;
            pass True/False to force it without probing.
        :param extended_keys: report the keys the legacy encodings cannot tell apart, such as ``'ctrl enter'``
            and ``'ctrl i'`` apart from ``'tab'``, through the keyboard protocol the terminal supports.
            Ctrl+C and Ctrl+Z then arrive as keys instead of signals; see :ref:`extended-keys`.
        """
        if input is None:
            input, self._send_input = socket.socketpair()  # noqa: A001

        super().__init__(
            input,
            output,
            bracketed_paste_mode=bracketed_paste_mode,
            focus_reporting=focus_reporting,
            extended_keys=extended_keys,
        )

    _dwOriginalOutMode: DWORD | None = None
    _dwOriginalInMode: DWORD | None = None
    _console_mode_active: bool = False

    def _is_real_terminal(self) -> bool:
        """Whether stdin/stdout are a real console with VT mode negotiated in `_start()`.

        The base implementation checks `os.isatty` on the input file descriptor, which is wrong
        here: `_input_fileno()` is a socket from `socket.socketpair()`, fed by `ReadInputThread`
        reading the real console, not the console handle itself.
        """
        return self._console_mode_active

    def _start(  # pylint: disable=keyword-arg-before-vararg
        self,
        alternate_buffer: bool = True,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Initialize the screen and input mode.

        :param alternate_buffer: use alternate screen buffer.
            The switch is not sent to a terminal that reported it has no alternate screen.
        :param args: not supported; any value raises :exc:`TypeError`.
        :param kwargs: not supported; any value raises :exc:`TypeError`.
        :raises TypeError: unexpected positional or keyword arguments were given.
        :raises RuntimeError: the console mode could not be set.
        """
        if args or kwargs:
            raise TypeError(f"start() got unexpected arguments: {args=!r}, {kwargs=!r}")

        if alternate_buffer:
            # A terminal that reported no alternate screen on an earlier start ignores the switch, and the frames are
            # drawn the same either way.
            if self.modes.alternate_buffer is not False:
                self.write(escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.enable_seq)
            self._rows_used = None
        else:
            self._rows_used = 0
        # Set as soon as the buffer is actually switched, not after: _stop() (e.g. from cleanup
        # after a later exception in this method) has to know to restore the normal buffer.
        self._alternate_buffer = alternate_buffer

        handle_out = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
        handle_in = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)
        original_out_mode = DWORD(0)
        original_in_mode = DWORD(0)

        # The standard handles are not consoles when the process runs detached or with redirected streams.
        # In that case there is no console mode to negotiate, same as a POSIX terminal which is not a tty.
        if _win32.GetConsoleMode(handle_out, byref(original_out_mode)) and _win32.GetConsoleMode(
            handle_in, byref(original_in_mode)
        ):
            dword_out_mode = DWORD(
                original_out_mode.value | _win32.ENABLE_VIRTUAL_TERMINAL_PROCESSING | _win32.DISABLE_NEWLINE_AUTO_RETURN
            )
            dword_in_mode = DWORD(
                original_in_mode.value | _win32.ENABLE_WINDOW_INPUT | _win32.ENABLE_VIRTUAL_TERMINAL_INPUT
            )

            if not (ok := _win32.SetConsoleMode(handle_out, dword_out_mode)):
                raise RuntimeError(f"ConsoleMode set failed for output. Err: {ok!r}")

            if not (ok := _win32.SetConsoleMode(handle_in, dword_in_mode)):
                _win32.SetConsoleMode(handle_out, original_out_mode)
                raise RuntimeError(f"ConsoleMode set failed for input. Err: {ok!r}")

            self._dwOriginalOutMode = original_out_mode
            self._dwOriginalInMode = original_in_mode
            self._console_mode_active = True

        self._start_input_thread()
        self._detect_terminal_modes()

        if self.modes.bracketed_paste:
            self.write(escape.PrivateMode.BRACKETED_PASTE.enable_seq)

        if self.modes.focus_reporting:
            self.write(escape.PrivateMode.FOCUS_REPORTING.enable_seq)

        self._enable_keyboard_protocol()

        self._next_timeout = self.max_wait

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
        # restore mouse tracking to previous state
        self._mouse_tracking(self._mouse_tracking_enabled)

        super()._start()  # type: ignore[safe-super]

    def __del__(self) -> None:
        if self._send_input is not None:  # the socket pair was created here, so it is closed here
            self._send_input.close()
            self._term_input_file.close()
        super().__del__()

    def _stop(self) -> None:
        """
        Restore the screen.

        :raises RuntimeError: the original console mode could not be restored.
        """
        self.clear()

        if self.modes.bracketed_paste:
            self.write(escape.PrivateMode.BRACKETED_PASTE.disable_seq)

        if self.modes.focus_reporting:
            self.write(escape.PrivateMode.FOCUS_REPORTING.disable_seq)

        # before the alternate screen is left: the kitty keyboard flags are kept per screen
        self._disable_keyboard_protocol()

        self._stop_input_thread()

        self._stop_restore_palette()
        self._stop_mouse_restore_buffer()

        if self._dwOriginalOutMode is not None and self._dwOriginalInMode is not None:
            handle_out = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
            handle_in = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)

            if not (ok := _win32.SetConsoleMode(handle_out, self._dwOriginalOutMode)):
                raise RuntimeError(f"ConsoleMode set failed for output. Err: {ok!r}")

            if not (ok := _win32.SetConsoleMode(handle_in, self._dwOriginalInMode)):
                raise RuntimeError(f"ConsoleMode set failed for input. Err: {ok!r}")

            self._dwOriginalOutMode = None
            self._dwOriginalInMode = None
            self._console_mode_active = False

        super()._stop()  # type: ignore[safe-super]

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """Remove any hooks added by hook_event_loop."""
        for handle in self._current_event_loop_handles:
            event_loop.remove_watch_file(handle)

        if self._input_timeout:
            event_loop.remove_alarm(self._input_timeout)
            self._input_timeout = None

    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[_DecodedInput, list[int]], typing.Any],
    ) -> None:
        """Register the given callback with the event loop, to be called with new input whenever it's available.

        The callback should be passed a list of processed keys and a list of unprocessed keycodes.

        Subclasses may wish to use parse_input to wrap the callback.

        .. deprecated:: 5.0
            A subclass that defines ``get_input_nonblocking()`` is still polled through it.
            Override :meth:`get_available_raw_input` instead. This API will be removed in version 7.0.
        """
        if self._started:  # a stopped screen has no input to read, and the next console user must get it
            self._start_input_thread()

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
    _last_cols_rows: tuple[int, int] | None = None  # the size get_cols_rows() last returned

    def _start_input_thread(self) -> None:
        """Start the background console reader, if it isn't already running."""
        if self._input_thread is not None or self._send_input is None:
            return
        # A window resized while the screen was stopped sent no event: report it before the next draw.
        window = self._console_window_size()
        if window is not None and self._last_cols_rows not in {None, window}:
            self._sigwinch_handler()
        # Console events are only translated for the input socket owned by this screen. signum is
        # left at its default (_raw_display_base._SIGWINCH): this class runs on Windows only,
        # which has no real SIGWINCH to report here anyway.
        self._input_thread = ReadInputThread(
            self._send_input,
            self._sigwinch_handler,
            window_size=self._console_window_size,
            start_window_size=window,
        )
        self._input_thread.start()

    def _stop_input_thread(self) -> None:
        """Stop the background console reader, so it reads no input meant for whatever uses the console next."""
        if self._input_thread is None:
            return
        self._input_thread.should_exit = True
        with contextlib.suppress(RuntimeError):
            self._input_thread.join(5)
        self._input_thread = None

    def _read_raw_input(self, timeout: float) -> bytearray:
        ready = self._wait_for_input_ready(timeout)

        fd = self._input_fileno()
        chars = bytearray()

        if fd is None or fd not in ready:
            return chars

        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)

            while selector.select(0):
                chunk = self._term_input_file.recv(1024)
                if not chunk:
                    raise RuntimeError("stdin has been closed")
                chars.extend(chunk)

            return chars

    def _console_window_size(self) -> tuple[int, int] | None:
        """Return the visible console window size (num columns, num rows), or None when it cannot be read.

        The console buffer describes the standard output only: any other stream has no size here.
        """
        if self._term_output_file is not sys.stdout:
            return None

        handle = _win32.GetStdHandle(_win32.STD_OUTPUT_HANDLE)
        info = _win32.CONSOLE_SCREEN_BUFFER_INFO()
        if not _win32.GetConsoleScreenBufferInfo(handle, byref(info)):
            return None

        # The visible window, not the buffer, which on the classic console also holds the scrollback.
        window = info.srWindow
        return window.Right - window.Left + 1, window.Bottom - window.Top + 1

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows)."""
        x, y = self._last_cols_rows = self._console_window_size() or super().get_cols_rows()
        self.maxrow = y
        return x, y


class ReadInputThread(threading.Thread):
    """Background thread that reads console input events and forwards them over a socket."""

    name = "urwid Windows input reader"
    daemon = True
    should_exit: bool = False

    def __init__(
        self,
        input_socket: socket.socket,
        resize: Callable[[], typing.Any],
        *,
        window_size: Callable[[], tuple[int, int] | None] = lambda: None,
        start_window_size: tuple[int, int] | None = None,
    ) -> None:
        """Forward console input to *input_socket* and call *resize* when the console window changes size.

        :param input_socket: the socket the console input is written to.
        :param resize: called when the console window changes size.
        :param window_size: returns the visible window size, checked on every wake-up of the thread:
            the console reports a change of its buffer size, which a change of the window alone does not cause.
        :param start_window_size: the window size read before the thread started, to compare later sizes with;
            when it is None, the thread reads it when it starts.
        """
        self._input = input_socket
        self._resize = resize
        self._window_size = window_size
        self._start_window_size = start_window_size
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        super().__init__()

    def run(self) -> None:
        hIn = _win32.GetStdHandle(_win32.STD_INPUT_HANDLE)
        MAX = 2048

        read = DWORD(0)
        arrtype = _win32.INPUT_RECORD * MAX
        input_records = arrtype()
        send_input = self._input.sendall
        resize = self._resize
        window_size = self._window_size
        key_event = _win32.EventType.KEY_EVENT
        resize_event = _win32.EventType.WINDOW_BUFFER_SIZE_EVENT

        # A character outside the Basic Multilingual Plane arrives as two UTF-16 halves in two key events,
        # possibly in two reads: the first half waits here for the second one.
        high_surrogate = ""
        window = self._start_window_size or window_size()

        while not self.should_exit:
            # The timeout keeps should_exit and the window size checked while no input arrives.
            wait_result = _win32.WaitForSingleObject(hIn, _INPUT_POLL_MS)
            resized = False
            text = ""

            if wait_result != _win32.WAIT_TIMEOUT:
                if wait_result != _win32.WAIT_OBJECT_0 or not _win32.ReadConsoleInputW(
                    hIn, input_records, MAX, byref(read)
                ):
                    self.logger.warning("Reading console input failed, no further input is received")
                    return

                chars = [high_surrogate]
                for inp in input_records[: read.value]:
                    if inp.EventType == key_event:
                        if inp.Event.KeyEvent.bKeyDown:
                            chars.append(inp.Event.KeyEvent.uChar.UnicodeChar)
                    elif inp.EventType == resize_event:
                        resized = True
                    else:
                        pass  # TODO: handle mouse events

                # On Windows atomic press/release of modifier keys produce phantom input with code NULL.
                text = "".join(chars).replace("\x00", "")
                high_surrogate = text[-1:] if "\ud800" <= text[-1:] <= "\udbff" else ""
                if high_surrogate:
                    text = text[:-1]

            # A size that cannot be read is no change: only a size read from the console replaces the last one.
            if (current_window := window_size()) is not None:
                resized |= window is not None and current_window != window
                window = current_window
            if resized:
                resize()

            if text:
                send_input(text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace").encode("utf-8"))


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
