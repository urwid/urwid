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
import fcntl
import functools
import os
import selectors
import signal
import struct
import sys
import termios
import tty
import typing
from subprocess import PIPE, Popen

from urwid import signals

from . import _raw_display_base, escape
from .common import INPUT_DESCRIPTORS_CHANGED

if typing.TYPE_CHECKING:
    import socket
    from collections.abc import Callable
    from types import FrameType

    from urwid.event_loop import EventLoop


class Screen(_raw_display_base.Screen):
    def __init__(
        self,
        input: typing.TextIO = sys.stdin,  # noqa: A002  # pylint: disable=redefined-builtin
        output: typing.TextIO = sys.stdout,
        bracketed_paste_mode=False,
        focus_reporting=False,
    ) -> None:
        """Initialize a screen that directly prints escape codes to an output
        terminal.

        bracketed_paste_mode -- enable bracketed paste mode in the host terminal.
            If the host terminal supports it, the application will receive `begin paste`
            and `end paste` keystrokes when the user pastes text.
        focus_reporting -- enable focus reporting in the host terminal.
            If the host terminal supports it, the application will receive `focus in`
            and `focus out` keystrokes when the application gains and loses focus.
        """
        super().__init__(input, output)
        self.gpm_mev: Popen | None = None
        self.gpm_event_pending: bool = False
        self.bracketed_paste_mode = bracketed_paste_mode
        self.focus_reporting = focus_reporting

        # These store the previous signal handlers after setting ours
        self._prev_sigcont_handler = None
        self._prev_sigtstp_handler = None
        self._prev_sigwinch_handler = None

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}("
            f"input={self._term_input_file}, "
            f"output={self._term_output_file}, "
            f"bracketed_paste_mode={self.bracketed_paste_mode}, "
            f"focus_reporting={self.focus_reporting})>"
        )

    def _sigwinch_handler(self, signum: int = 28, frame: FrameType | None = None) -> None:
        """
        frame -- will always be None when the GLib event loop is being used.
        """
        super()._sigwinch_handler(signum, frame)

        if callable(self._prev_sigwinch_handler):
            self._prev_sigwinch_handler(signum, frame)

    def _sigtstp_handler(self, signum: int, frame: FrameType | None = None) -> None:
        self.stop()  # Restores the previous signal handlers
        self._prev_sigcont_handler = self.signal_handler_setter(signal.SIGCONT, self._sigcont_handler)
        # Handled by the previous handler.
        # If non-default, it may set its own SIGCONT handler which should hopefully call our own.
        os.kill(os.getpid(), signal.SIGTSTP)

    def _sigcont_handler(self, signum: int, frame: FrameType | None = None) -> None:
        """
        frame -- will always be None when the GLib event loop is being used.
        """
        self.signal_restore()

        if callable(self._prev_sigcont_handler):
            # May set its own SIGTSTP handler which would be stored and replaced in
            # `signal_init()` (via `start()`).
            self._prev_sigcont_handler(signum, frame)

        self.start()
        self._sigwinch_handler(28, None)

    def signal_init(self) -> None:
        """
        Called in the startup of run wrapper to set the SIGWINCH
        and SIGTSTP signal handlers.

        Override this function to call from main thread in threaded
        applications.
        """
        self._prev_sigwinch_handler = self.signal_handler_setter(signal.SIGWINCH, self._sigwinch_handler)
        self._prev_sigtstp_handler = self.signal_handler_setter(signal.SIGTSTP, self._sigtstp_handler)

    def signal_restore(self) -> None:
        """
        Called in the finally block of run wrapper to restore the
        SIGTSTP, SIGCONT and SIGWINCH signal handlers.

        Override this function to call from main thread in threaded
        applications.
        """
        self.signal_handler_setter(signal.SIGTSTP, self._prev_sigtstp_handler or signal.SIG_DFL)
        self.signal_handler_setter(signal.SIGCONT, self._prev_sigcont_handler or signal.SIG_DFL)
        self.signal_handler_setter(signal.SIGWINCH, self._prev_sigwinch_handler or signal.SIG_DFL)

    def _mouse_tracking(self, enable: bool) -> None:
        super()._mouse_tracking(enable)
        if enable:
            self._start_gpm_tracking()
        else:
            self._stop_gpm_tracking()

    def _start_gpm_tracking(self) -> None:
        if not os.path.isfile("/usr/bin/mev"):
            return
        if not os.environ.get("TERM", "").lower().startswith("linux"):
            return

        m = Popen(  # pylint: disable=consider-using-with
            ["/usr/bin/mev", "-e", "158"],
            stdin=PIPE,
            stdout=PIPE,
            close_fds=True,
            encoding="ascii",
        )
        fcntl.fcntl(m.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
        self.gpm_mev = m

    def _stop_gpm_tracking(self) -> None:
        if not self.gpm_mev:
            return
        os.kill(self.gpm_mev.pid, signal.SIGINT)
        os.waitpid(self.gpm_mev.pid, 0)
        self.gpm_mev = None

    def _start(self, alternate_buffer: bool = True) -> None:
        """
        Initialize the screen and input mode.

        alternate_buffer -- use an alternate screen buffer
        """
        if alternate_buffer:
            self.write(escape.SWITCH_TO_ALTERNATE_BUFFER)
            self._rows_used = None
        else:
            self._rows_used = 0

        if self.bracketed_paste_mode:
            self.write(escape.ENABLE_BRACKETED_PASTE_MODE)

        if self.focus_reporting:
            self.write(escape.ENABLE_FOCUS_REPORTING)

        fd = self._input_fileno()
        if fd is not None and os.isatty(fd):
            self._old_termios_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)

        self.signal_init()
        self._alternate_buffer = alternate_buffer
        self._next_timeout = self.max_wait

        if not self._signal_keys_set:
            self._old_signal_keys = self.tty_signal_keys(fileno=fd)

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
        # restore mouse tracking to previous state
        self._mouse_tracking(self._mouse_tracking_enabled)

        return super()._start()

    def _stop(self) -> None:
        """
        Restore the screen.
        """
        self.clear()

        if self.bracketed_paste_mode:
            self.write(escape.DISABLE_BRACKETED_PASTE_MODE)

        if self.focus_reporting:
            self.write(escape.DISABLE_FOCUS_REPORTING)

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

        self.signal_restore()

        self._stop_mouse_restore_buffer()

        fd = self._input_fileno()
        if fd is not None and os.isatty(fd):
            termios.tcsetattr(fd, termios.TCSAFLUSH, self._old_termios_settings)

        if self._old_signal_keys:
            self.tty_signal_keys(*self._old_signal_keys, fd)

        super()._stop()

    def get_input_descriptors(self) -> list[socket.socket | typing.IO | int]:
        """
        Return a list of integer file descriptors that should be
        polled in external event loops to check for user input.

        Use this method if you are implementing your own event loop.

        This method is only called by `hook_event_loop`, so if you override
        that, you can safely ignore this.
        """
        if not self._started:
            return []

        fd_list = super().get_input_descriptors()
        if self.gpm_mev is not None and self.gpm_mev.stdout is not None:
            fd_list.append(self.gpm_mev.stdout)
        return fd_list

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """
        Remove any hooks added by hook_event_loop.
        """
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
        if hasattr(self, "get_input_nonblocking"):
            wrapper = self._make_legacy_input_wrapper(event_loop, callback)
        else:

            @functools.wraps(callback)
            def wrapper() -> tuple[list[str], typing.Any] | None:
                self.logger.debug('Calling callback for "watch file"')
                return self.parse_input(event_loop, callback, self.get_available_raw_input())

        fds = self.get_input_descriptors()
        handles = [event_loop.watch_file(fd if isinstance(fd, int) else fd.fileno(), wrapper) for fd in fds]
        self._current_event_loop_handles = handles

    def _get_input_codes(self) -> list[int]:
        return super()._get_input_codes() + self._get_gpm_codes()

    def _get_gpm_codes(self) -> list[int]:
        codes = []
        try:
            while self.gpm_mev is not None and self.gpm_event_pending:
                codes.extend(self._encode_gpm_event())
        except OSError as e:
            if e.args[0] != 11:
                raise
        return codes

    def _read_raw_input(self, timeout: int) -> bytearray:
        ready = self._wait_for_input_ready(timeout)
        if self.gpm_mev is not None and self.gpm_mev.stdout.fileno() in ready:
            self.gpm_event_pending = True
        fd = self._input_fileno()
        chars = bytearray()

        if fd is None or fd not in ready:
            return chars

        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            input_ready = selector.select(0)
            while input_ready:
                chars.extend(os.read(fd, 1024))
                input_ready = selector.select(0)

            return chars

    def _encode_gpm_event(self) -> list[int]:
        self.gpm_event_pending = False
        s = self.gpm_mev.stdout.readline()
        result = s.split(", ")
        if len(result) != 6:
            # unexpected output, stop tracking
            self._stop_gpm_tracking()
            signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
            return []
        ev, x, y, _ign, b, m = s.split(",")
        ev = int(ev.split("x")[-1], 16)
        x = int(x.split(" ")[-1])
        y = int(y.lstrip().split(" ")[0])
        b = int(b.split(" ")[-1])
        m = int(m.split("x")[-1].rstrip(), 16)

        # convert to xterm-like escape sequence

        last_state = next_state = self.last_bstate
        result = []

        mod = 0
        if m & 1:
            mod |= 4  # shift
        if m & 10:
            mod |= 8  # alt
        if m & 4:
            mod |= 16  # ctrl

        def append_button(b: int) -> None:
            b |= mod
            result.extend([27, ord("["), ord("M"), b + 32, x + 32, y + 32])

        if ev in {20, 36, 52}:  # press
            if b & 4 and last_state & 1 == 0:
                append_button(0)
                next_state |= 1
            if b & 2 and last_state & 2 == 0:
                append_button(1)
                next_state |= 2
            if b & 1 and last_state & 4 == 0:
                append_button(2)
                next_state |= 4
        elif ev == 146:  # drag
            if b & 4:
                append_button(0 + escape.MOUSE_DRAG_FLAG)
            elif b & 2:
                append_button(1 + escape.MOUSE_DRAG_FLAG)
            elif b & 1:
                append_button(2 + escape.MOUSE_DRAG_FLAG)
        else:  # release
            if b & 4 and last_state & 1:
                append_button(0 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~1
            if b & 2 and last_state & 2:
                append_button(1 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~2
            if b & 1 and last_state & 4:
                append_button(2 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~4
        if ev == 40:  # double click (release)
            if b & 4 and last_state & 1:
                append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
            if b & 2 and last_state & 2:
                append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
            if b & 1 and last_state & 4:
                append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        elif ev == 52:
            if b & 4 and last_state & 1:
                append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
            if b & 2 and last_state & 2:
                append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
            if b & 1 and last_state & 4:
                append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)

        self.last_bstate = next_state
        return result

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows)."""
        y, x = super().get_cols_rows()
        with contextlib.suppress(OSError):  # Term size could not be determined
            if hasattr(self._term_output_file, "fileno"):
                buf = fcntl.ioctl(self._term_output_file.fileno(), termios.TIOCGWINSZ, b" " * 8)
                y, x, _, _ = struct.unpack("hhhh", buf)

        # Provide some lightweight fallbacks in case the TIOCWINSZ doesn't
        # give sane answers
        if (x <= 0 or y <= 0) and self.term in {"ansi", "vt100"}:
            y, x = 24, 80
        self.maxrow = y
        return x, y


def _test():
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
