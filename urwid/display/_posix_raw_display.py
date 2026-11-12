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
import errno
import fcntl
import functools
import os
import signal
import stat
import struct
import subprocess
import sys
import termios
import tty
import typing
from subprocess import PIPE, Popen

from urwid import signals
from urwid._selectors import read_selector

from . import _raw_display_base, escape
from .common import INPUT_DESCRIPTORS_CHANGED, InputClosedError

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType

    from urwid.event_loop import EventLoop

    SignalHandler = Callable[[int, FrameType | None], typing.Any] | int | None
    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _DecodedInput = list[str | _MouseInput | _CursorPosition]


# GPM event-type bits, as reported by the `mev` helper on its `Ax<hex>` field.
# See GPM's public gpm.h, Gpm_Event.type.
_GPM_MOVE = 1
_GPM_DRAG = 2
_GPM_DOWN = 4
_GPM_UP = 8
_GPM_SINGLE = 16
_GPM_DOUBLE = 32
_GPM_TRIPLE = 64
_GPM_MFLAG = 128
_GPM_HARD = 256

# Event-type combinations actually emitted by `mev -e 158`, decoded against the bitmask above.
_GPM_EV_DOWN_SINGLE = _GPM_DOWN | _GPM_SINGLE  # 20: first click of a press
_GPM_EV_DOWN_DOUBLE = _GPM_DOWN | _GPM_DOUBLE  # 36: second click of a press
_GPM_EV_DOWN_TRIPLE = _GPM_DOWN | _GPM_SINGLE | _GPM_DOUBLE  # 52: third click of a press
_GPM_EV_DRAG = _GPM_DRAG | _GPM_SINGLE | _GPM_MFLAG  # 146
_GPM_EV_UP_DOUBLE = _GPM_UP | _GPM_DOUBLE  # 40: release ending a double click

# GPM Gpm_Event.buttons bits, from gpm.h.
_GPM_B_LEFT = 4
_GPM_B_MIDDLE = 2
_GPM_B_RIGHT = 1

# GPM Gpm_Event.modifiers bits. GPM documents this field as the Linux console "get shift state"
# byte (TIOCLINUX subcode 6): bit 0 is shift, bit 1 is AltGr, bit 2 is control, bit 3 is (left) alt.
_GPM_MOD_SHIFT = 1
_GPM_MOD_ALTGR = 2
_GPM_MOD_CTRL = 4
_GPM_MOD_ALT = 8

# seconds the gpm helper is given to exit on SIGINT before it is killed
_GPM_STOP_TIMEOUT = 1.0

# Linux virtual consoles /dev/tty1 to /dev/tty63: TTY_MAJOR and MAX_NR_CONSOLES in the kernel's tty headers.
# Minor 0 is /dev/tty0, the console in the foreground, and minors from 64 on are serial ports.
_VT_MAJOR = 4
_VT_MAX_MINOR = 63
# TTYAUX_MAJOR: /dev/tty and /dev/console, which stand for another terminal.
_TTY_ALIAS_MAJOR = 5
# TIOCGDEV, _IOR('T', 0x32, unsigned int): the device behind an alias, in the kernel's 32-bit dev_t encoding.
# These architectures encode the read direction of an ioctl request in bit 30 instead of bit 31.
_TIOCGDEV = 0x40045432 if os.uname().machine.startswith(("alpha", "mips", "parisc", "ppc", "sparc")) else 0x80045432


class Screen(_raw_display_base.Screen):
    """Raw screen backend that drives a real POSIX terminal."""

    def __init__(
        self,
        input: _raw_display_base.SupportsFileno = sys.stdin,  # noqa: A002
        output: _raw_display_base.TextWriter = sys.stdout,
        bracketed_paste_mode: bool | None = None,
        focus_reporting: bool | None = None,
        extended_keys: bool = False,
        *,
        in_band_resize: bool | None = None,
    ) -> None:
        """Initialize a screen that directly prints escape codes to an output terminal.

        :param input: the terminal input, read through its file descriptor.
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
        :param in_band_resize: take the terminal size from the resize notifications the terminal sends in the input
            (DEC private mode 2048), as well as from ``SIGWINCH``; see :ref:`in-band-resize`.
            None (default) auto-detects via DECRQM and enables it once confirmed supported,
            except on the iTerm2 releases that send the notifications without their final byte;
            pass True/False to force it without probing.

        .. note::
            on terminal-generated signals: putting the terminal into cbreak mode (see `start()`)
            does not clear the tty's ``ISIG`` flag,
            so the line discipline still turns Ctrl+C and Ctrl+Z into ``SIGINT`` and ``SIGTSTP``
            and delivers them to this process (urwid/urwid#1268).
            ``SIGINT`` is left for the application or its event loop to handle as it sees fit.
            ``SIGTSTP`` is handled by this class:
            `signal_init()` installs a handler that wakes the input loop,
            which restores the terminal before actually suspending the process,
            then puts the terminal back into cbreak/alternate-buffer mode and forces a redraw on resume,
            so a stray Ctrl+Z does not leave a stale, unresponsive frame painted on screen.
            The suspend therefore waits until the application next reads input,
            through `get_input()` or the callback `hook_event_loop()` registers.
            Applications that install their own ``SIGTSTP`` handler on top of this one
            should chain to the previous handler (as this class does) rather than replacing it outright,
            and multithreaded applications must call `signal_init()` and `signal_restore()` from the main thread,
            since only the main thread can receive process signals.
            `start()` also clears the ``IEXTEN`` flag, which cbreak mode leaves on,
            so on macOS and the BSDs Ctrl+V, Ctrl+O and Ctrl+Y reach the application
            instead of being handled by the terminal driver.
            It clears ``FLUSHO`` as well: a Ctrl+O typed before the start can leave that output discard on,
            and without ``IEXTEN`` no Ctrl+O can turn it off.
            `stop()` restores both flags.
        """
        if in_band_resize is None and _raw_display_base.sends_incomplete_window_size_reports(os.environ):
            in_band_resize = False
        super().__init__(
            input,
            output,
            bracketed_paste_mode=bracketed_paste_mode,
            focus_reporting=focus_reporting,
            extended_keys=extended_keys,
            in_band_resize=in_band_resize,
        )
        self.gpm_mev: Popen[str] | None = None
        self.gpm_event_pending: bool = False
        self._old_termios_settings: list[typing.Any] | None = None

        # These store the previous signal handlers after setting ours
        self._prev_sigtstp_handler: SignalHandler = None
        self._prev_sigwinch_handler: SignalHandler = None
        # Set by the SIGTSTP handler, carried out by get_available_raw_input().
        self._suspend_requested = False

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}("
            f"input={self._term_input_file}, "
            f"output={self._term_output_file}, "
            f"bracketed_paste_mode={self.modes.bracketed_paste}, "
            f"focus_reporting={self.modes.focus_reporting}, "
            f"in_band_resize={self.modes.in_band_resize})>"
        )

    def _sigwinch_handler(self, signum: int = signal.SIGWINCH, frame: FrameType | None = None) -> None:
        """Record a terminal resize and pass the signal on to the previous handler.

        :param signum: the signal number.
        :param frame: will always be None when the GLib event loop is being used.
        """
        super()._sigwinch_handler(signum, frame)

        if callable(self._prev_sigwinch_handler):
            self._prev_sigwinch_handler(signum, frame)

    def _sigtstp_handler(self, signum: int, frame: FrameType | None = None) -> None:
        """Request a suspend, carried out by :meth:`get_available_raw_input` in the thread reading input.

        Restoring the terminal writes to it, changes the termios settings and re-hooks the event loop.
        None of that is safe at the arbitrary point of the program a signal interrupts,
        so the handler only sets a flag and wakes the input loop.
        """
        self._suspend_requested = True
        self._wake_input_loop()

    def signal_init(self) -> None:
        """Set the SIGWINCH and SIGTSTP signal handlers, called in the startup of run wrapper.

        Override this function to call from main thread in threaded
        applications.
        """
        self._prev_sigwinch_handler = self.signal_handler_setter(signal.SIGWINCH, self._sigwinch_handler)
        self._prev_sigtstp_handler = self.signal_handler_setter(signal.SIGTSTP, self._sigtstp_handler)

    def signal_restore(self) -> None:
        """Restore the SIGTSTP and SIGWINCH signal handlers, called in the finally block of run wrapper.

        Override this function to call from main thread in threaded
        applications.
        """
        self.signal_handler_setter(signal.SIGTSTP, self._prev_sigtstp_handler or signal.SIG_DFL)
        self.signal_handler_setter(signal.SIGWINCH, self._prev_sigwinch_handler or signal.SIG_DFL)

    def _mouse_tracking(self, enable: bool) -> None:
        super()._mouse_tracking(enable)
        if enable:
            self._start_gpm_tracking()
        else:
            self._stop_gpm_tracking()

    def _start_gpm_tracking(self) -> None:
        """
        Start the gpm helper that reports mouse events on the Linux console the screen reads from.

        The helper starts only when :attr:`term` names the Linux console and the input is a virtual console.
        Input opened through :file:`/dev/tty` or :file:`/dev/console` counts as the terminal behind it.
        The helper is attached to that console by number.
        The gpm daemon gives a client that names no console of its own,
        such as one on a pseudo-terminal, the events of every console without a client.

        :raises OSError: the input descriptor cannot be examined, for example because it was closed.
        :raises RuntimeError: the gpm helper process provides no standard output.
        """
        if not os.path.isfile("/usr/bin/mev"):
            return
        if not _raw_display_base._is_linux_console(self.term):  # pylint: disable=protected-access  # same package
            return
        fd = self._input_fileno()
        if fd is None:
            return
        # The device number tells both whether the input is a virtual console and which one,
        # whatever the names under /dev are.
        input_stat = os.fstat(fd)
        if not stat.S_ISCHR(input_stat.st_mode):
            return
        device = input_stat.st_rdev
        if os.major(device) == _TTY_ALIAS_MAJOR:
            try:
                (device,) = struct.unpack("I", fcntl.ioctl(fd, _TIOCGDEV, bytes(4)))
            except OSError:  # a kernel without TIOCGDEV, or an alias with no terminal behind it
                return
        console = os.minor(device)
        if os.major(device) != _VT_MAJOR or not 1 <= console <= _VT_MAX_MINOR:
            return

        m = Popen(  # noqa: S603  # fixed program path; the only variable argument is the kernel's console number
            # mev reads the console number with scanf("%x")
            ["/usr/bin/mev", "-e", "158", "-C", f"{console:x}"],
            stdin=PIPE,
            stdout=PIPE,
            close_fds=True,
            encoding="ascii",
        )
        if m.stdout is None:
            with m:  # closes the pipes and reaps the process on the way out
                m.kill()
            raise RuntimeError("gpm mouse tracking stdout was not created")
        os.set_blocking(m.stdout.fileno(), False)
        self.gpm_mev = m
        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

    def _stop_gpm_tracking(self) -> None:
        """Stop the gpm helper, close its pipes and stop watching its output."""
        gpm_mev, self.gpm_mev = self.gpm_mev, None
        if gpm_mev is None:
            return
        try:
            with gpm_mev:  # closes both pipes and reaps the process on the way out
                gpm_mev.send_signal(signal.SIGINT)
                try:
                    gpm_mev.wait(_GPM_STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    gpm_mev.kill()
        finally:
            signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

    def _start(  # pylint: disable=keyword-arg-before-vararg
        self,
        alternate_buffer: bool = True,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Initialize the screen and input mode.

        :param alternate_buffer: use an alternate screen buffer.
            The switch is not sent to a terminal that reported it has no alternate screen.
        :param args: not supported; any value raises :exc:`TypeError`.
        :param kwargs: not supported; any value raises :exc:`TypeError`.
        :raises TypeError: unexpected positional or keyword arguments were given.
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

        fd = self._input_fileno()
        if fd is not None and os.isatty(fd):
            self._old_termios_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            # setcbreak() leaves IEXTEN on, and with it the macOS and BSD drivers still act on ctrl v (VLNEXT),
            # ctrl o (VDISCARD, which toggles FLUSHO, and the driver drops every write while FLUSHO is set)
            # and ctrl y (VDSUSP).
            # FLUSHO is cleared too, because with IEXTEN off no ctrl o can clear it.
            # ISIG stays as it is for tty_signal_keys().
            mode = termios.tcgetattr(fd)
            mode[tty.LFLAG] &= ~(termios.IEXTEN | termios.FLUSHO)
            termios.tcsetattr(fd, termios.TCSANOW, mode)

        self._detect_terminal_modes()

        if self.modes.bracketed_paste:
            self.write(escape.PrivateMode.BRACKETED_PASTE.enable_seq)

        if self.modes.focus_reporting:
            self.write(escape.PrivateMode.FOCUS_REPORTING.enable_seq)

        if self.modes.in_band_resize:
            self._set_in_band_resize(True)

        self._enable_keyboard_protocol()
        self._show_title()

        self.signal_init()
        self._next_timeout = self.max_wait

        if not self._signal_keys_set:
            self._old_signal_keys = self.tty_signal_keys(fileno=fd)

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
        # restore mouse tracking to previous state
        self._mouse_tracking(self._mouse_tracking_enabled)

        super()._start(*args, **kwargs)  # type: ignore[safe-super]

    def _stop(self) -> None:
        """Restore the screen."""
        self.clear()
        self.signal_restore()
        # the terminal may be resized while stopped, and SIGWINCH is what reports that then
        self._reported_cols_rows = None

        try:
            try:
                if self.modes.bracketed_paste:
                    self.write(escape.PrivateMode.BRACKETED_PASTE.disable_seq)

                if self.modes.focus_reporting:
                    self.write(escape.PrivateMode.FOCUS_REPORTING.disable_seq)

                if self._in_band_resize:
                    self._set_in_band_resize(False)

                # before the alternate screen is left: the kitty keyboard flags are kept per screen
                self._disable_keyboard_protocol()

                self._stop_restore_palette()
                self._restore_title()
                self._stop_mouse_restore_buffer()
            except OSError as exc:
                # A hung-up terminal (EIO, or ENXIO on FreeBSD) or a closed output pipe (EPIPE) has nothing to restore,
                # and raising here would hide the error that ended the run, such as the closed input.
                if exc.errno not in {errno.EIO, errno.ENXIO, errno.EPIPE}:
                    raise
            finally:
                # a failed write skips the step of _mouse_tracking() that stops the helper
                self._stop_gpm_tracking()
        finally:
            # the terminal settings are restored also when an error other than a hang-up ended the writes
            fd = self._input_fileno()
            try:
                if fd is not None and os.isatty(fd) and self._old_termios_settings is not None:
                    termios.tcsetattr(fd, termios.TCSAFLUSH, self._old_termios_settings)

                if self._old_signal_keys:
                    self.tty_signal_keys(*self._old_signal_keys, fd)
            except termios.error:
                # A terminal that hung up after the isatty() check is no tty any more and has no settings to restore.
                # One that still is, such as a terminal an orphaned process group may not change, reports its error.
                if fd is None or os.isatty(fd):
                    raise

        # A suspend requested while the screen ran must not stop the process after a later restart.
        self._suspend_requested = False

        super()._stop()  # type: ignore[safe-super]

    def get_input_descriptors(self) -> list[_raw_display_base.SupportsFileno | int]:
        """Return a list of integer file descriptors that should be polled in external event loops.

        Used to check for user input. Use this method if you are implementing your own event loop.

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
        if hasattr(self, "get_input_nonblocking"):
            wrapper = self._make_legacy_input_wrapper(event_loop, callback)
        else:

            @functools.wraps(callback)
            def wrapper() -> tuple[_DecodedInput, list[int]] | None:
                self.logger.debug('Calling callback for "watch file"')
                return self.parse_input(event_loop, callback, self.get_available_raw_input())

        fds = self.get_input_descriptors()
        handles = [event_loop.watch_file(fd if isinstance(fd, int) else fd.fileno(), wrapper) for fd in fds]
        self._current_event_loop_handles = handles

    def get_available_raw_input(self) -> list[int]:
        """Return any currently available input, then carry out a suspend requested by ``SIGTSTP``.

        The screen is stopped before the process suspends itself, and restarted and fully redrawn on resume.
        The flag is checked after the wake-up socket is drained, so a later request keeps its wake-up pending.
        """
        codes = super().get_available_raw_input()
        if self._suspend_requested and self._started:
            self._suspend_requested = False
            self.stop()  # restores the previous SIGTSTP disposition, which the kill below runs
            os.kill(os.getpid(), signal.SIGTSTP)
            self.start()
            # This resize is the redraw after the resume and is set after this pass's read,
            # so no input typed before it can still be waiting, and it is not held back.
            self._resized = True
            self._hold_resize = False
        return codes

    def _get_input_codes(self) -> list[int]:
        return super()._get_input_codes() + self._get_gpm_codes()

    def _get_gpm_codes(self) -> list[int]:
        codes: list[int] = []
        gpm_mev = self.gpm_mev
        try:
            while gpm_mev is not None and self.gpm_event_pending:
                if gpm_mev.stdout is None:
                    return codes
                codes.extend(self._encode_gpm_event())
        except OSError as e:
            if e.args[0] != 11:
                raise
        return codes

    def _read_raw_input(self, timeout: float) -> bytearray:
        """
        Read at most `_INPUT_READ_LIMIT` bytes of the raw input available, waiting at most *timeout* seconds.

        `_hold_resize` is set when a resize can have input typed before it still waiting:
        the resize was not pending when the read started, or input is still readable after it.

        :raises InputClosedError: the input file has been closed.
        """
        resize_pending = self._resized
        self._hold_resize = not resize_pending
        ready = self._wait_for_input_ready(timeout)
        gpm_stdout = self.gpm_mev.stdout if self.gpm_mev is not None else None
        if gpm_stdout is not None and gpm_stdout.fileno() in ready:
            self.gpm_event_pending = True
        fd = self._input_fileno()
        chars = bytearray()

        if fd is None or fd not in ready:
            return chars

        # `fd` was just reported ready, so this read does not block. Input beyond the limit is read on the next pass.
        chunk = os.read(fd, _raw_display_base._INPUT_READ_LIMIT)  # pylint: disable=protected-access  # same package
        if not chunk:
            raise InputClosedError("stdin has been closed")
        chars.extend(chunk)
        # A terminal returns at most its line discipline buffer per read (about 4 KiB on Linux), below the limit,
        # so whether input is left is asked of the descriptor rather than read off the size of the chunk.
        with read_selector([(fd, None)]) as selector:
            self._hold_resize = not resize_pending or bool(selector.select(0))
        return chars

    def _encode_gpm_event(self) -> list[int]:
        self.gpm_event_pending = False
        if self.gpm_mev is None or self.gpm_mev.stdout is None:
            return []

        event_result = self.gpm_mev.stdout.readline().split(",")
        if len(event_result) != 6:
            # unexpected output, stop tracking
            self._stop_gpm_tracking()
            return []

        ev_, x_, y_, _ign, b_, m_ = event_result
        ev = int(ev_.rsplit("x", 1)[-1], 16)
        x = int(x_.rsplit(" ", 1)[-1])
        y = int(y_.lstrip().split(" ", 1)[0])
        b = int(b_.rsplit(" ", 1)[-1])
        m = int(m_.rsplit("x", 1)[-1].rstrip(), 16)

        # convert to xterm-like escape sequence

        last_state = next_state = self.last_bstate
        result: list[int] = []

        mod = 0
        if m & _GPM_MOD_SHIFT:
            mod |= 4  # shift
        if m & (_GPM_MOD_ALTGR | _GPM_MOD_ALT):
            mod |= 8  # alt
        if m & _GPM_MOD_CTRL:
            mod |= 16  # ctrl

        def append_button(b: int) -> None:
            b |= mod
            result.extend([27, ord("["), ord("M"), b + 32, x + 32, y + 32])

        if ev in {_GPM_EV_DOWN_SINGLE, _GPM_EV_DOWN_DOUBLE, _GPM_EV_DOWN_TRIPLE}:  # press
            if b & _GPM_B_LEFT and last_state & 1 == 0:
                append_button(0)
                next_state |= 1
            if b & _GPM_B_MIDDLE and last_state & 2 == 0:
                append_button(1)
                next_state |= 2
            if b & _GPM_B_RIGHT and last_state & 4 == 0:
                append_button(2)
                next_state |= 4
        elif ev == _GPM_EV_DRAG:  # drag
            if b & _GPM_B_LEFT:
                append_button(0 + escape.MouseBit.DRAG)
            elif b & _GPM_B_MIDDLE:
                append_button(1 + escape.MouseBit.DRAG)
            elif b & _GPM_B_RIGHT:
                append_button(2 + escape.MouseBit.DRAG)
        else:  # release
            if b & _GPM_B_LEFT and last_state & 1:
                append_button(0 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~1
            if b & _GPM_B_MIDDLE and last_state & 2:
                append_button(1 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~2
            if b & _GPM_B_RIGHT and last_state & 4:
                append_button(2 + escape.MOUSE_RELEASE_FLAG)
                next_state &= ~4
        if ev == _GPM_EV_UP_DOUBLE:  # double click (release)
            if b & _GPM_B_LEFT and last_state & 1:
                append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
            if b & _GPM_B_MIDDLE and last_state & 2:
                append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
            if b & _GPM_B_RIGHT and last_state & 4:
                append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        elif ev == _GPM_EV_DOWN_TRIPLE:  # triple click (press)
            if b & _GPM_B_LEFT and last_state & 1:
                append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
            if b & _GPM_B_MIDDLE and last_state & 2:
                append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
            if b & _GPM_B_RIGHT and last_state & 4:
                append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)

        self.last_bstate = next_state
        return result

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows).

        The size the terminal last reported in the input is returned while it is newer than the last ``SIGWINCH``,
        see :ref:`in-band-resize`; otherwise the size is read from the terminal device.
        """
        if self._reported_cols_rows is not None:
            x, y = self._last_cols_rows = self._reported_cols_rows
            self.maxrow = y
            return x, y
        x, y = super().get_cols_rows()
        with contextlib.suppress(OSError):  # Term size could not be determined
            if isinstance(self._term_output_file, _raw_display_base.SupportsFileno):
                buf = fcntl.ioctl(self._term_output_file.fileno(), termios.TIOCGWINSZ, b" " * 8)
                y, x, _, _ = struct.unpack("hhhh", buf)

        # Provide some lightweight fallbacks in case the TIOCWINSZ doesn't
        # give sane answers
        if (x <= 0 or y <= 0) and self.term in {"ansi", "vt100"}:
            y, x = 24, 80
        self.maxrow = y
        self._last_cols_rows = x, y
        return x, y


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
