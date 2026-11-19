# Urwid terminal emulation widget unit tests
#    Copyright (C) 2010  aszlig
#    Copyright (C) 2011  Ian Ward
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

from __future__ import annotations

import errno
import fcntl
import gc
import itertools
import os
import pty
import selectors
import signal
import struct
import sys
import termios
import typing
import unittest
import weakref
from itertools import dropwhile
from unittest import mock

import wcwidth

import urwid
import urwid.ansi_parser
import urwid.vterm
from tests.util import NonExternalLoopScreen, external_loop, pipe_terminal
from urwid.util import set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Callable

IS_WINDOWS = sys.platform == "win32"
IS_CPYTHON = sys.implementation.name == "cpython"

# Sentinel values for the mocked PTY.
# They never collide with real fds/pids because every os.* call in vterm.py is intercepted while the test is running.
_FAKE_MASTER_FD = 0xC0FFEE
_FAKE_PID = 0xBEEF

# The patches replace these process-wide, so calls for any other fd go to the originals.
_REAL_OS_READ = os.read
_REAL_OS_WRITE = os.write
_REAL_OS_CLOSE = os.close


def _pty_echo(data: bytes) -> bytes:
    """Mimic the Linux PTY cooked-mode echo of bytes written to the master.

    Control characters become caret notation (e.g. ESC -> ``^[``),
    matching what a real PTY driver would push back when ECHO/ECHOCTL is enabled
    - which is how the `keypress` writes to show up on the canvas.
    """
    out = bytearray()
    for byte in data:
        if byte < 0x20:
            out.append(0x5E)  # '^'
            out.append(byte + 0x40)
        elif byte == 0x7F:
            out.extend(b"^?")
        else:
            out.append(byte)
    return bytes(out)


#: the string terminator ST, ESC backslash, in the form TermTest.write() takes
_ST = "\\e\\"


class _FakePTY:
    """In-memory replacement for the spawned subprocess + PTY pair, standing in for the ``os`` calls on both.

    ``to_widget`` is the byte stream the widget will read via ``os.read``
    - i.e. what a real subprocess would have written to its stdout.
    ``from_widget`` captures everything the widget writes to the PTY master.
    The child exits on ``exit_signal`` or ``SIGKILL`` and stays a zombie until ``os.waitpid`` reaps it.
    Closing the master hangs the child up, which counts as ``SIGHUP`` even when ``signals_allowed`` is off,
    as for a setuid child.
    With ``reaped_on_exit`` the child is reaped as soon as it exits, as when ``SIGCHLD`` is ignored.
    Without ``child_reads`` the child reads no input, so the master does not take more.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Return to the state of a freshly spawned child with no output yet."""
        self.to_widget = bytearray()
        self.from_widget = bytearray()
        self.closed = False
        self.exited = False
        self.reaped = False
        self.exit_signal = signal.SIGHUP
        self.signals_allowed = True
        self.reaped_on_exit = False
        self.child_reads = True
        self.signals_sent: list[int] = []

    def is_readable(self) -> bool:
        """Return whether ``os.read`` on the master would return without blocking."""
        return bool(self.to_widget) or self.exited or self.closed

    def read(self, fd: int, n: int) -> bytes:
        """Stand in for ``os.read`` on a blocking master fd."""
        if fd != _FAKE_MASTER_FD:
            return _REAL_OS_READ(fd, n)
        if self.closed or self.exited:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        if not self.to_widget:
            msg = "os.read() on a PTY master with nothing to read would hang a real event loop"
            raise AssertionError(msg)
        chunk = bytes(self.to_widget[:n])
        del self.to_widget[:n]
        return chunk

    def write(self, fd: int, data: bytes) -> int:
        """Stand in for ``os.write``, echoing what the master receives like a PTY in cooked mode."""
        if fd != _FAKE_MASTER_FD:
            return _REAL_OS_WRITE(fd, data)
        self.from_widget.extend(data)
        self.to_widget.extend(_pty_echo(data))
        return len(data)

    def close(self, fd: int) -> None:
        """Stand in for ``os.close``."""
        if fd == _FAKE_MASTER_FD:
            self.closed = True
            if self.exit_signal == signal.SIGHUP:
                self.exited = True
            return
        _REAL_OS_CLOSE(fd)

    def kill(self, pid: int, sig: int) -> None:
        """Stand in for ``os.kill``, refusing any process other than the fake child."""
        if pid != _FAKE_PID:
            msg = f"os.kill({pid}, {sig}) outside the fake child"
            raise AssertionError(msg)
        if self.reaped:
            raise ProcessLookupError(errno.ESRCH, os.strerror(errno.ESRCH))
        if not self.signals_allowed:
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))
        self.signals_sent.append(sig)
        if sig in {self.exit_signal, signal.SIGKILL}:
            self.exited = True
            self.reaped = self.reaped_on_exit

    def waitpid(self, pid: int, options: int) -> tuple[int, int]:
        """Stand in for ``os.waitpid``, refusing a blocking wait that would never return."""
        if pid != _FAKE_PID:
            msg = f"os.waitpid({pid}) outside the fake child"
            raise AssertionError(msg)
        if self.reaped:
            raise ChildProcessError(errno.ECHILD, os.strerror(errno.ECHILD))
        if self.exited:
            self.reaped = True
            return _FAKE_PID, 0
        if options & os.WNOHANG:
            return 0, 0
        msg = "blocking os.waitpid() on a child that is still running"
        raise AssertionError(msg)


class _FakeSelector:
    """Stand-in for ``selectors.DefaultSelector`` that reports the fake master readable from the fake PTY state."""

    def __init__(self, pty_state: _FakePTY) -> None:
        self.pty_state = pty_state
        self.events = 0

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def register(self, fd: int, events: int) -> None:
        """Accept the fake master fd only."""
        if fd != _FAKE_MASTER_FD:
            msg = f"selector registration of fd {fd} outside the fake PTY"
            raise AssertionError(msg)
        self.events |= events

    def select(self, timeout: float | None = None) -> list[tuple[None, int]]:
        """Report the master readable when a read would not block, and writable while the child reads.

        It never waits.
        """
        ready = 0
        if self.events & selectors.EVENT_READ and self.pty_state.is_readable():
            ready |= selectors.EVENT_READ
        if self.events & selectors.EVENT_WRITE and self.pty_state.child_reads:
            ready |= selectors.EVENT_WRITE
        return [(None, ready)] if ready else []


class _FakeTTY:
    """Drop-in for ``urwid.display.RealTerminal`` keeping the tty signal keys in memory instead of on a real tty."""

    def __init__(self) -> None:
        self.signal_keys = (3, 28, 17, 19, 26)  # ^C, ^\, ^Q, ^S, ^Z

    def tty_signal_keys(self, *keys: typing.Literal["undefined"] | int | None) -> tuple[int, ...]:
        """Return the current signal keys and set the given ones, like the real method."""
        old = self.signal_keys
        if keys:
            self.signal_keys = tuple(
                0 if key == "undefined" else current if key is None else key
                for key, current in zip(keys, old, strict=True)
            )
        return old


class _FakeAtexit:
    """Stand-in for :mod:`atexit` holding the registered hooks in a list instead of running them at exit."""

    def __init__(self) -> None:
        self.hooks: list[Callable[[], object]] = []

    def register(self, func: Callable[[], object]) -> None:
        """Record the hook."""
        self.hooks.append(func)

    def unregister(self, func: Callable[[], object]) -> None:
        """Drop every hook equal to *func*."""
        self.hooks = [hook for hook in self.hooks if hook != func]


class _ChildExit(BaseException):
    """Raised by the patched ``os._exit``, so the forked-child branch ends without ending the test process."""


def _forbidden(name: str) -> Callable[..., typing.NoReturn]:
    """Return a stand-in for a process-control call that no code under test may make while the child is mocked."""

    def call(*args: object) -> typing.NoReturn:
        msg = f"{name}{args} called while the child process is mocked"
        raise AssertionError(msg)

    return call


@unittest.skipIf(IS_WINDOWS, "Terminal is not supported under windows")
class TermTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pty = _FakePTY()
        self.tty = _FakeTTY()
        self.atexit = _FakeAtexit()
        self._install_patches()

        # An event loop that never runs: the tests feed the pty themselves, so a render reads nothing.
        self.event_loop = mock.Mock(spec=urwid.SelectEventLoop)
        # The command is never actually executed:
        # pty.fork is mocked to take the parent branch and os.execvpe is a no-op for safety.
        self.term = urwid.Terminal(["/bin/false"], main_loop=self.event_loop)
        self.resize(80, 24)

    def restart(self, width: int = 80, height: int = 24, soft: bool = False, *, scroll_on_output: bool = True) -> None:
        """Replace the terminal under test with a fresh one on a fresh fake PTY, for one case of a table test."""
        self.term.terminate()
        self.pty.reset()
        self.term = urwid.Terminal(["/bin/false"], main_loop=self.event_loop, scroll_on_output=scroll_on_output)
        self.resize(width, height, soft)

    def tearDown(self) -> None:
        if not self.term.terminated:
            self.term.terminate()

    # ------------------------------------------------------------------
    # Patching
    # ------------------------------------------------------------------

    def _install_patches(self) -> None:
        patches = [
            mock.patch("urwid.vterm.pty.fork", return_value=(_FAKE_PID, _FAKE_MASTER_FD)),
            mock.patch("urwid.vterm.os.read", side_effect=self.pty.read),
            mock.patch("urwid.vterm.os.write", side_effect=self.pty.write),
            mock.patch("urwid.vterm.os.close", side_effect=self.pty.close),
            mock.patch("urwid.vterm.os.kill", side_effect=self.pty.kill),
            mock.patch("urwid.vterm.os.waitpid", side_effect=self.pty.waitpid),
            mock.patch("urwid.vterm.os.killpg", side_effect=_forbidden("os.killpg")),
            mock.patch("urwid.vterm.signal.pthread_kill", side_effect=_forbidden("signal.pthread_kill")),
            mock.patch("urwid.vterm.os.execvpe"),
            mock.patch("urwid.vterm.fcntl.fcntl", return_value=0),
            mock.patch("urwid.vterm.fcntl.ioctl", return_value=0),
            mock.patch("urwid.vterm.atexit", self.atexit),
            mock.patch("urwid.vterm.RealTerminal", return_value=self.tty),
            mock.patch("urwid.vterm.selectors.DefaultSelector", side_effect=lambda: _FakeSelector(self.pty)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    # ------------------------------------------------------------------
    # Signal helpers
    # ------------------------------------------------------------------

    def connect_signal(self, name: str):
        self._sig_response = None

        def _set_signal_response(widget: urwid.Widget, *args, **kwargs) -> None:
            self._sig_response = (args, kwargs)

        self._set_signal_response = _set_signal_response

        urwid.connect_signal(self.term, name, self._set_signal_response)

    def expect_signal(self, *args, **kwargs):
        self.assertEqual(self._sig_response, (args, kwargs))

    def disconnect_signal(self, name: str) -> None:
        urwid.disconnect_signal(self.term, name, self._set_signal_response)

    def caught_beep(self, obj):
        self.beeped = True

    # ------------------------------------------------------------------
    # Drive the widget
    # ------------------------------------------------------------------

    def resize(self, width: int, height: int, soft: bool = False) -> None:
        self.termsize = (width, height)
        if not soft:
            self.term.render(self.termsize, focus=False)

    def write(self, data: str) -> None:
        """Push bytes into the widget's input stream.

        Equivalent to the spawned subprocess writing to its stdout.
        PTY cooked-mode ONLCR is applied as a bare ``\\n`` becomes ``\\r\\n`` on the master read side
        - matching what the kernel would do for a real child process.
        """
        encoded = data.encode("iso8859-1").replace(rb"\e", b"\x1b")
        encoded = encoded.replace(b"\n", b"\r\n")
        self.pty.to_widget.extend(encoded)

    def drain(self) -> None:
        """Feed the widget until it has read everything written so far, one PTY read at a time."""
        while self.pty.to_widget:
            self.term.wait_and_feed()

    def flush(self) -> None:
        self.write(chr(0x7F))

    @typing.overload
    def read(self, raw: bool = False, focus: bool = ...) -> bytes: ...

    @typing.overload
    def read(self, raw: bool = True, focus: bool = ...) -> list[list[bytes, typing.Any, typing.Any]]: ...

    def read(self, raw: bool = False, focus: bool = False) -> bytes | list[list[bytes, typing.Any, typing.Any]]:
        self.term.wait_and_feed()
        rendered = self.term.render(self.termsize, focus=focus)
        if raw:
            is_empty = lambda c: c == (None, None, b" ")
            content = list(rendered.content())
            lines = (tuple(dropwhile(is_empty, reversed(line))) for line in content)
            return [list(reversed(line)) for line in lines if line]
        else:
            content = rendered.text
            lines = (line.rstrip() for line in content)
            return b"\n".join(lines).rstrip()

    def expect(
        self,
        what: str | list[tuple[typing.Any, str | None, bytes]],
        desc: str | None = None,
        raw: bool = False,
        focus: bool = False,
    ) -> None:
        if not isinstance(what, list):
            what = what.encode("iso8859-1")
        got = self.read(raw=raw, focus=focus)
        if desc is None:
            desc = ""
        else:
            desc += "\n"
        desc += f"Expected:\n{what!r}\nGot:\n{got!r}"
        self.assertEqual(got, what, desc)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_simplestring(self):
        self.write("hello world")
        self.expect("hello world")

    def test_linefeed(self):
        self.write("hello\x0aworld")
        self.expect("hello\nworld")

    def test_linefeed2(self):
        self.write("aa\b\b\\eDbb")
        self.expect("aa\nbb")

    def test_carriage_return(self):
        self.write("hello\x0dworld")
        self.expect("world")

    def test_insertlines(self):
        self.write("\\e[0;0flast\\e[0;0f\\e[10L\\e[0;0ffirst\nsecond\n\\e[11D")
        self.expect("first\nsecond\n\n\n\n\n\n\n\n\nlast")

    def test_deletelines(self):
        self.write("1\n2\n3\n4\\e[2;1f\\e[2M")
        self.expect("1\n4")

    def test_nul(self):
        self.write("a\0b")
        self.expect("ab")

    def test_movement(self):
        self.write(r"\e[10;20H11\e[10;0f\e[20C\e[K")
        self.expect("\n" * 9 + " " * 19 + "1")
        self.write("\\e[A\\e[B\\e[C\\e[D\b\\e[K")
        self.expect("")
        self.write(r"\e[50A2")
        self.expect(" " * 19 + "2")
        self.write("\b\\e[K\\e[50B3")
        self.expect("\n" * 23 + " " * 19 + "3")
        self.write("\b\\e[K" + r"\eM" * 30 + r"\e[100C4")
        self.expect(" " * 79 + "4")
        self.write(r"\e[100D\e[K5")
        self.expect("5")

    def edgewall(self):
        edgewall = "1-\\e[1;%(x)df-2\\e[%(y)d;1f3-\\e[%(y)d;%(x)df-4\x0d"
        self.write(edgewall % {"x": self.termsize[0] - 1, "y": self.termsize[1] - 1})

    def test_horizontal_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.expect("1-" + " " * 76 + "-2" + "\n" * 22 + "3-" + " " * 76 + "-4")
        self.resize(78, 24, soft=True)
        self.flush()
        self.expect("1-" + "\n" * 22 + "3-")
        self.resize(80, 24, soft=True)
        self.flush()
        self.expect("1-" + "\n" * 22 + "3-")

    def test_vertical_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.expect("1-" + " " * 76 + "-2" + "\n" * 22 + "3-" + " " * 76 + "-4")
        # the bottom line is redrawn one row higher each time, and the blank rows below it go first,
        # so the top line stays on the screen
        for y in range(23, 1, -1):
            self.resize(80, y, soft=True)
            self.write(r"\e[%df\e[J3-\e[%d;%df-4" % (y, y, 79))
            desc = "try to rescale to 80x%d." % y
            self.expect("1-" + " " * 76 + "-2" + "\n" * (y - 1) + "3-" + " " * 76 + "-4", desc)
        self.resize(80, 24, soft=True)
        self.flush()
        self.expect("1-" + " " * 76 + "-2" + "\n" + "3-" + " " * 76 + "-4")

    def write_movements(self, arg):
        fmt = "XXX\n\\e[faaa\\e[Bccc\\e[Addd\\e[Bfff\\e[Cbbb\\e[A\\e[Deee"
        self.write(fmt.replace(r"\e[", r"\e[" + arg))

    def test_defargs(self):
        self.write_movements("")
        self.expect("aaa   ddd      eee\n   ccc   fff bbb")

    def test_nullargs(self):
        self.write_movements("0")
        self.expect("aaa   ddd      eee\n   ccc   fff bbb")

    def test_erase_line(self):
        self.write("1234567890\\e[5D\\e[K\n1234567890\\e[5D\\e[1K\naaaaaaaaaaaaaaa\\e[2Ka")
        self.expect("12345\n      7890\n               a")

    def test_erase_display(self):
        self.write(r"1234567890\e[5D\e[Ja")
        self.expect("12345a")
        self.write(r"98765\e[8D\e[1Jx")
        self.expect("   x5a98765")
        # mode 1 erases through the cursor cell, also on a row below the first
        self.write("\\ecabc\ndef\ngh\\e[2;2H\\e[1J")
        self.expect("\n  f\ngh")
        self.write("\\ecabc\ndef\\e[2;1H\\e[1J")
        self.expect("\n ef")
        # in origin mode the rows outside the scrolling region are erased too, as in xterm
        for erase, screen in (
            (r"\e[2J", ""),
            (r"\e[?2J", ""),
            (r"\e[H\e[J", "X"),
            (r"\e[2;1H\e[1J", "\n\n\nX\nX\nX"),
        ):
            with self.subTest(erase):
                self.write("\\ecX\nX\nX\nX\nX\nX\\e[2;4r\\e[?6h" + erase)
                self.expect(screen)

    def test_erased_cells_keep_the_colours_only(self) -> None:
        """Give erased, inserted and scrolled-in cells the colours but not the attribute flags, as xterm does.

        DECERA keeps the flags, and DECALN fills with plain E's, also as in xterm.
        """
        blue = urwid.AttrSpec("default", "dark blue")
        reverse = urwid.AttrSpec("default,standout", "dark blue")
        for label, data, cell in (
            ("EL", r"\e[7;4;1;44m\e[K", (blue, None, b" ")),
            ("ECH", r"\e[7;4;1;44m\e[2X", (blue, None, b" ")),
            ("DECSEL", r"\e[7;4;1;44m\e[?K", (blue, None, b" ")),
            ("ICH", r"X\e[1;1H\e[7;4;1;44m\e[@", (blue, None, b" ")),
            ("IL", r"\e[7;4;1;44m\e[L", (blue, None, b" ")),
            ("ED with default colours", r"\e[7;4m\e[2J", (None, None, b" ")),
            ("ED from the middle row", r"\e[2;2H\e[44m\e[1J", (blue, None, b" ")),
            ("DECERA keeps the flags", r"\e[7;44m\e[1;1;1;2$z", (reverse, None, b" ")),
            ("DECALN ignores the attributes and the charset", r"\e[7;44m\e(0\e#8", (None, None, b"E")),
        ):
            with self.subTest(label):
                self.restart(4, 2)
                self.write(data)
                self.read()
                self.assertEqual(self.term.term.term[0][0], cell)

    def test_selective_erase(self) -> None:
        """Keep the protected characters in the erases xterm keeps them in.

        Those DECSCA protected are kept by DECSED, DECSEL and DECSERA, and those SPA protected by ED, EL, ECH, DECSED
        and DECSEL until DECSCA, DECSTR or RIS.
        """
        for label, data, screen in (
            ("DECSEL", r"\e[1;1H\e[?K", " BC"),
            ("DECSED", "\nEF\\e[?2J", " BC"),
            ("DECSERA", r"\e[1;1;1;4${", " BC"),
            ("DECSERA outside the rectangle", r"\e[1;3;1;4${", "ABC"),
            ("EL", r"\e[1;1H\e[K", ""),
            ("DCH, which shifts the protection", r"\e[1;1H\e[P\e[?K", "BC"),
            ("insert mode, which protects the inserted characters", '\\e[1;1H\\e[4h\\e[1"qE\\e[1;1H\\e[?K', "E BC"),
            (
                "DECRC on the alternate screen, which restores DECSCA",
                '\\e[1"q\\e[?1049h\\e[0"q\\e[?1049lE\\e[1;1H\\e[?K',
                " BC E",
            ),
        ):
            with self.subTest(label):
                self.restart()
                self.write('A\\e[1"qBC\\e[0"qD' + data)
                self.expect(screen)

        for label, data, screen in (
            ("ED", r"\e[1;1H\e[2J", " BC"),
            ("EL", r"\e[1;1H\e[K", " BC"),
            ("ECH", r"\e[1;1H\e[4X", " BC"),
            ("DECSED", r"\e[?2J", " BC"),
            ("DECSERA, which erases them", r"\e[1;1;1;4${", ""),
            ("ED after DECSCA, which ends the ISO protection with any value", r'\e[5"q\e[2J', ""),
            ("DECSED after DECSCA", r'\e[0"q\e[?2J', " BC"),
            ("ED after DECSTR", r"\e[!p\e[2J", ""),
            ("ED after DECRC, which does not restore the ISO protection", r'\e7\e[0"q\e8\e[2J', ""),
            ("ED, as DECRC restores the protection SPA set", r"\e[1;1H\eV\e7\eW\e8E\eW\e[2J", "EBC"),
            ("DECSEL, as EPA ends DECSCA", r'\e[1"qE\eWF\e[?2J', " BC E"),
        ):
            with self.subTest(f"SPA, {label}"):
                self.restart()
                self.write(r"A\eVBC\eWD" + data)
                self.expect(screen)

        self.restart()
        self.write(r"\eV\ec")
        self.read()
        self.assertFalse(self.term.term.modes.iso_protection, "RIS ends the ISO protection")

        red = urwid.AttrSpec("default", "dark red")
        self.restart(4, 2)
        self.write(r"\e[41mX\e[0;7;44m\e[${")
        self.read()
        self.assertEqual(self.term.term.term[0][0][::2], (red, b" "), "DECSERA keeps the cell's own attributes")

    def test_area_attributes_change_as_sgr(self) -> None:
        """Change attributes with DECCARA and DECRARA as SGR does, so bold brightens a basic colour and faint stays."""
        for label, data, sgr in (
            ("DECCARA 1", r"\e[31mA\e[0m\e[1;1;1;1;1$r", r"\e[31;1m"),
            ("DECCARA 22", r"\e[31;1mA\e[0m\e[1;1;1;1;22$r", r"\e[31m"),
            ("DECCARA 22 keeping faint", r"\e[1;2mA\e[0m\e[1;1;1;1;22$r", r"\e[2m"),
            ("DECRARA 1", r"\e[31;1mA\e[0m\e[1;1;1;1;1$t", r"\e[31m"),
            ("DECCARA 0 keeping the colours", r"\e[1;4;31;44mA\e[0m\e[1;1;1;1;0$r", r"\e[31;44m"),
        ):
            with self.subTest(label):
                self.restart(4, 2)
                self.write(sgr + "A")
                self.read()
                expected = self.term.term.term[0][0]
                self.restart(4, 2)
                self.write(data)
                self.read()
                self.assertEqual(self.term.term.term[0][0], expected)

    def test_scrolling_region_simple(self):
        # TODO(Aleksei): Issue #544
        self.write("\\e[10;20r\\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\\e[faa")
        self.expect("aa" + "\n" * 9 + "2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12")

    def test_scrolling_region_reverse(self):
        self.write("\\e[2J\\e[1;2r\\e[5Baaa\r\\eM\\eM\\eMbbb\nXXX")
        self.expect("\n\nbbb\nXXX\n\naaa")

    def test_scrolling_region_move(self):
        self.write("\\e[10;20r\\e[2J\\e[10Bfoo\rbar\rblah\rmooh\r\\e[10Aone\r\\eM\\eMtwo\r\\eM\\eMthree\r\\eM\\eMa")
        self.expect("ahree\n\n\n\n\n\n\n\n\n\nmooh")

    def test_scrolling_twice(self):
        self.write(r"\e[?6h\e[10;20r\e[2;5rtest")
        self.expect("\ntest")

    def test_scrolling_region_scrollback(self) -> None:
        """Save the lines scrolled off a region only when it starts at the top row, as xterm does."""
        for region, row, saved, screen in (
            ("3;5", 5, [], "STATUS\nL1\nN1\nN2\nN3"),
            ("1;4", 4, [b"STATUS", b"L1", b"L2"], "L3\nN1\nN2\nN3\nL4"),
        ):
            with self.subTest(region=region):
                self.restart(10, 5)
                self.write(f"STATUS\nL1\nL2\nL3\nL4\\e[{region}r\\e[{row};1H\nN1\nN2\nN3")
                self.expect(screen)
                self.assertEqual(
                    [
                        b"".join(text for _attr, _charset, text in line).rstrip()
                        for line in self.term.term.scrollback_buffer
                    ],
                    saved,
                )
        # a view frozen with scroll_on_output off keeps the status line above such a region on its row
        self.restart(10, 5, scroll_on_output=False)
        self.write("L0\nL1\nL2\nL3\nL4\nL5\nL6\\e[1;1HSTATUS\\e[3;5r\\e[5;1H")
        self.drain()
        self.term.term.scroll_buffer(up=True, lines=2)
        self.expect("L0\nL1\nSTATUS\nL3\nL4")
        self.write("\nN1\nN2\nN3")
        self.expect("L0\nL1\nSTATUS\nL3\nN1")

    def test_wrap_below_scrolling_region(self) -> None:
        """Wrapping on a row below the scrolling region moves down a row, or stays on the last one, without scrolling."""
        for label, row, screen in (
            ("below the region", 5, "1\n2\n3\n\n" + "a" * 80 + "\nb"),
            ("on the last row", 24, "1\n2\n3" + "\n" * 21 + "b" + "a" * 79),
        ):
            with self.subTest(label):
                self.restart()
                self.write(f"1\n2\n3\\e[1;3r\\e[{row};1H" + "a" * 80 + "b")
                self.expect(screen)

    def test_cursor_scrolling_region(self):
        # TODO(Aleksei): Issue #544
        self.write("\\e[?6h\\e[10;20r\\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\\e[faa")
        self.expect("\n" * 9 + "aa\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12")

    def test_scrolling_region_simple_with_focus(self):
        # TODO(Aleksei): Issue #544
        self.write("\\e[10;20r\\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\\e[faa")
        self.expect("aa" + "\n" * 9 + "2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12", focus=True)

    def test_scrolling_region_reverse_with_focus(self):
        self.write("\\e[2J\\e[1;2r\\e[5Baaa\r\\eM\\eM\\eMbbb\nXXX")
        self.expect("\n\nbbb\nXXX\n\naaa", focus=True)

    def test_scrolling_region_move_with_focus(self):
        self.write("\\e[10;20r\\e[2J\\e[10Bfoo\rbar\rblah\rmooh\r\\e[10Aone\r\\eM\\eMtwo\r\\eM\\eMthree\r\\eM\\eMa")
        self.expect("ahree\n\n\n\n\n\n\n\n\n\nmooh", focus=True)

    def test_scrolling_twice_with_focus(self):
        self.write(r"\e[?6h\e[10;20r\e[2;5rtest")
        self.expect("\ntest", focus=True)

    def test_cursor_scrolling_region_with_focus(self):
        # TODO(Aleksei): Issue #544
        self.write("\\e[?6h\\e[10;20r\\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\\e[faa")
        self.expect("\n" * 9 + "aa\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12", focus=True)

    def test_relative_region_jump(self):
        self.write(r"\e[21H---\e[10;20r\e[?6h\e[18Htest")
        self.expect("\n" * 19 + "test\n---")

    def test_set_multiple_modes(self):
        self.write(r"\e[?6;5htest")
        self.expect("test")
        self.assertTrue(self.term.term_modes.constrain_scrolling)
        self.assertTrue(self.term.term_modes.reverse_video)
        self.write(r"\e[?6;5l")
        self.expect("test")
        self.assertFalse(self.term.term_modes.constrain_scrolling)
        self.assertFalse(self.term.term_modes.reverse_video)

    def test_wrap_simple(self):
        self.write(r"\e[?7h\e[1;%dHtt" % self.term.width)
        self.expect(" " * (self.term.width - 1) + "t\nt")

    def test_wrap_backspace_tab(self):
        self.write("\\e[?7h\\e[1;%dHt\b\b\t\ta" % self.term.width)
        self.expect(" " * (self.term.width - 1) + "a")

    def test_cursor_motion_cancels_pending_wrap(self) -> None:
        """A character written after moving the cursor off a pending wrap stays where the cursor was moved to."""
        for label, move in (
            ("CUP", r"\e[2;80H"),
            ("CUD", r"\e[B"),
            ("VPA", r"\e[2d"),
            ("IND", r"\eD"),
            ("VT", "\v"),
            ("DECRC", r"\e8"),
            ("SCORC", r"\e[u"),
        ):
            with self.subTest(label):
                self.restart()
                self.write(r"\e[2;80H\e7\e[s\e[1;80HA" + move + "B")
                self.expect(" " * 79 + "A\n" + " " * 79 + "B")

    def test_cursor_visibility(self):
        self.write(r"\e[?25linvisible")
        self.expect("invisible", focus=True)
        self.assertEqual(self.term.term.cursor, None)
        self.assertIsNone(self.term.get_cursor_coords(self.termsize))
        self.write("\rvisible\\e[?25h\\e[K")
        self.expect("visible", focus=True)
        self.assertNotEqual(self.term.term.cursor, None)
        self.assertEqual(self.term.get_cursor_coords(self.termsize), self.term.term.cursor)

    def test_get_utf8_len(self):
        length = self.term.term.get_utf8_len(int("11110000", 2))
        self.assertEqual(length, 3)
        length = self.term.term.get_utf8_len(int("11000000", 2))
        self.assertEqual(length, 1)
        length = self.term.term.get_utf8_len(int("11111101", 2))
        self.assertEqual(length, 5)

    def test_encoding_unicode(self):
        """Read UTF-8 output as one cell per character.

        Under a UTF-8 encoding by either name, with or without ESC % G.
        """
        for encoding in ("utf-8", "utf8"):
            for select_utf8 in ("\\e%G", ""):
                with self.subTest(encoding=encoding, select_utf8=select_utf8), set_temporary_encoding(encoding):
                    self.write(f"\\ec{select_utf8}\xe2\x80\x94")
                    self.expect([[(None, None, b"\xe2\x80\x94")]], raw=True)

    def test_encoding_unicode_ascii(self):
        with set_temporary_encoding("ascii"):
            self.write("\\e%G\xe2\x80\x94")
            self.expect("?")

    def test_encoding_unicode_csi_byte(self):
        """Show a UTF-8 character that is the CSI byte in urwid's encoding as a cell, and keep escapes as they were."""
        self.connect_signal("title")
        with set_temporary_encoding("cp1252"):
            # U+203A is 0x9B in cp1252.
            self.write("\\e%Ga\xe2\x80\xba1m")
            self.expect([[(None, None, char) for char in (b"a", b"\x9b", b"1", b"m")]], raw=True)
            # In an OSC string the character is part of the title.
            self.write("\\e]2;a\xe2\x80\xbab\a")
            self.read()
            self.expect_signal("a\u203ab")
            # In CSI parameters it starts a new CSI, so ESC [ U+203A 25 l does not hide the cursor.
            self.write("\\e[\xe2\x80\xba25l")
            self.read()
            self.assertTrue(self.term.term_modes.visible_cursor)
        self.disconnect_signal("title")

    def test_encoding_unicode_ascii_dec_special(self):
        """A DEC drawing character, or a fallback to one, from a UTF-8 child is one cell in the DEC character set."""
        self.addCleanup(urwid.set_ascii_fallbacks, urwid.get_ascii_fallbacks())
        urwid.set_ascii_fallbacks({"\N{EM DASH}": "-", "\N{FULL BLOCK}": "\N{BOX DRAWINGS LIGHT VERTICAL}"})
        dec_q, dec_x = (None, "0", b"q"), (None, "0", b"x")
        with set_temporary_encoding("ascii"):
            # U+2500, U+2014 and U+2588 in UTF-8, then an ASCII "q" in the active character set
            self.write("\\e%G\xe2\x94\x80\xe2\x80\x94\xe2\x96\x88q")
            self.expect([[dec_q, (None, None, b"-"), dec_x, (None, None, b"q")]], raw=True)

            # the IBM PC mapping does not remap a cell that is already in the DEC character set
            self.write("\\ec\\e%G\\e[11m\xe2\x94\x80\\e[10m")
            self.expect([[dec_q]], raw=True)

            # insert mode stores the cell in the DEC character set as well
            self.write("\\ec\\e%Ga\\e[4h\\e[D\xe2\x94\x80")
            self.expect([[dec_q, (None, None, b"a")]], raw=True)

    def test_encoding_wrong_unicode(self):
        with set_temporary_encoding("utf-8"):
            self.write("\\e%G\xc0\x99")
            self.expect("")

    def test_encoding_vt100_graphics(self):
        with set_temporary_encoding("ascii"):
            self.write("\\e)0\\e(0\x0fg\x0eg\\e)Bn\\e)0g\\e)B\\e(B\x0fn")
            self.expect(
                [[(None, "0", b"g"), (None, "0", b"g"), (None, None, b"n"), (None, "0", b"g"), (None, None, b"n")]],
                raw=True,
            )

    def test_ibmpc_mapping(self):
        with set_temporary_encoding("ascii"):
            self.write("\\e[11m\x18\\e[10m\x18")
            self.expect([[(None, "U", b"\x18")]], raw=True)

            self.write("\\ec\\e)U\x0e\x18\x0f\\e[3h\x18\\e[3l\x18")
            self.expect([[(None, None, b"\x18")]], raw=True)

            self.write("\\ec\\e[11m\xdb\x18\\e[10m\xdb")
            self.expect(
                [[(None, "U", b"\xdb"), (None, "U", b"\x18"), (None, None, b"\xdb")]],
                raw=True,
            )

        with set_temporary_encoding("utf-8"):
            # a display writes "U" cells unchanged, so the C0 CAN and the C1 OSC must not reach a UTF-8 host terminal
            self.write("\\ec\\e%G\\e[11m\x18\xc2\x9d\xc3\xa9\\e[10m")
            self.expect([[(None, "U", b"?"), (None, "U", b"?"), (None, "U", b"\xc3\xa9")]], raw=True)

    def test_set_title(self):
        self._the_title = None

        def _change_title(widget, title):
            self._the_title = title

        self.connect_signal("title")
        self.write("\\e]666parsed right?\\e\\te\\e]0;test title\007st1")
        self.expect("test1")
        self.expect_signal("test title")
        self.write("\\e];stupid title\\e\\\\e[0G\\e[2Ktest2")
        self.expect("test2")
        self.expect_signal("stupid title")
        # \xff, a lead byte no UTF-8 sequence uses, cut short by BEL; and the complete but overlong \xc0\x80
        for select_utf8, invalid in itertools.product(("", "\\e%G"), ("\xff", "\xc0\x80")):
            with self.subTest(select_utf8=select_utf8, invalid=invalid), set_temporary_encoding("utf-8"):
                self._sig_response = None
                self.write(f"\\ec{select_utf8}\\e]0;bad {invalid}\007test3")
                self.expect("test3")
                self.assertIsNone(self._sig_response, "a title that is not valid UTF-8 is not set, as in tmux")
        self.disconnect_signal("title")

    def test_hyperlink(self):
        """Link the text after an OSC 8 command through SGR changes, and end the link at an empty or invalid one."""
        link = urwid.Hyperlink("https://urwid.org", id="a")
        for select_utf8 in ("", "\\e%G"):
            with self.subTest(select_utf8=select_utf8), set_temporary_encoding("utf-8"):
                self.write(
                    f"\\ec{select_utf8}\\e]8;id=a;https://urwid.org\\e\\\\e[1mab\\e[0mc\\e]8;;\\e\\d"
                    "\\e]8;;https://b.org\007e\\e]8;;bad\x7fbad\x18f\\e]8;;https://b.org\007g\\e]8;;bad\xff\007h"
                )
                self.expect(
                    [
                        [
                            (urwid.AttrSpec("default,bold", "default", hyperlink=link), None, b"a"),
                            (urwid.AttrSpec("default,bold", "default", hyperlink=link), None, b"b"),
                            (urwid.AttrSpec("default", "default", hyperlink=link), None, b"c"),
                            (None, None, b"d"),
                            (urwid.AttrSpec("default", "default", hyperlink="https://b.org"), None, b"e"),
                            (urwid.AttrSpec("default", "default", hyperlink="https://b.org"), None, b"f"),
                            (urwid.AttrSpec("default", "default", hyperlink="https://b.org"), None, b"g"),
                            (None, None, b"h"),
                        ]
                    ],
                    raw=True,
                )

    def test_hyperlink_not_in_blank_cells(self):
        """Leave erased cells unlinked, and end the link at an over-long OSC 8 command."""
        self.resize(4, 2)
        self.write("\\e[31m\\e]8;;https://urwid.org\\e\\ab\\e[K\n\\e[2K")
        self.write(f"\\e]8;;{'u' * urwid.vterm.MAX_OSC_LENGTH}\\e\\c")
        self.drain()
        blank = (urwid.AttrSpec("dark red", "default"), None, b" ")
        self.expect(
            [
                [
                    (urwid.AttrSpec("dark red", "default", hyperlink="https://urwid.org"), None, b"a"),
                    (urwid.AttrSpec("dark red", "default", hyperlink="https://urwid.org"), None, b"b"),
                    *[blank] * 2,
                ],
                [(urwid.AttrSpec("dark red", "default"), None, b"c"), *[blank] * 3],
            ],
            raw=True,
        )

    def test_control_characters_in_osc_are_ignored(self):
        """Neither execute a control character inside an OSC string nor take it into the body, as a terminal does."""
        self.connect_signal("title")
        self.write("a\\e]8;;https://ur\nwid.org\007L\\e]8;;\007\\e]0;t\r\x01i\b\ttle\007c")
        self.expect(
            [
                [
                    (None, None, b"a"),
                    (urwid.AttrSpec("default", "default", hyperlink="https://urwid.org"), None, b"L"),
                    (None, None, b"c"),
                ]
            ],
            raw=True,
        )
        self.expect_signal("title")
        self.disconnect_signal("title")

    def test_osc_controls_after_escape_and_in_display_ctrl_mode(self):
        """Execute a control after an ESC in an OSC string, keep DEL in it, and abort it at CAN with display_ctrl."""
        self.connect_signal("title")
        self.write("a\\e]0;t\\e\n\\b")
        self.expect("a\nb")
        self.expect_signal("t")
        self.write("\\e]0;u\\e\t\\c")
        self.expect("a\nb       c")
        self.expect_signal("u")
        self.write("\\e]0;v\\e\x01\\")
        self.expect("a\nb       c")
        self.expect_signal("v")
        self.write("\\e]0;ti\x7ftle\007")
        self.expect("a\nb       c")
        self.expect_signal("ti\x7ftle")
        self._sig_response = None
        self.term.term.modes.display_ctrl = True
        self.write("\\e]0;x\x18y\007")
        self.read()
        self.assertIsNone(self._sig_response)
        self.disconnect_signal("title")

    def test_other_controls_are_ignored(self):
        """Ignore C0 control characters a terminal ignores, in text and inside an escape sequence, which continues."""
        self.write("a\x01b\\e[3\x011mR\\e\x01[0mc")
        red = urwid.AttrSpec("dark red", "default")
        self.expect([[(None, None, b"a"), (None, None, b"b"), (red, None, b"R"), (None, None, b"c")]], raw=True)

    def test_title_in_output_encoding(self):
        """Decode a title from the encoding UTF-8 input is converted to, so it survives a non-UTF-8 locale."""
        old_encoding = urwid.util.get_encoding()
        urwid.set_encoding("latin-1")
        self.addCleanup(urwid.set_encoding, old_encoding)
        self.connect_signal("title")
        self.write("\\e%G\\e]0;caf\xc3\xa9\007")
        self.read()
        self.expect_signal("caf\xe9")
        # every byte is valid Latin-1, so only the UTF-8 decoding can tell that \xff is not a character
        self._sig_response = None
        self.write("\\e]0;bad \xff\007")
        self.read()
        self.assertIsNone(self._sig_response, "a title that is not valid UTF-8 is not set, as in tmux")
        self.disconnect_signal("title")

    def test_c1_characters_in_title_are_kept(self):
        """Keep U+0080 to U+009F inside an OSC string as part of the title, as tmux does with UTF-8 input."""
        self.connect_signal("title")
        self.write("\\e]0;t\xc2\x9c\xc2\x9ble\007")
        self.read()
        self.expect_signal("t\x9c\x9ble")
        self.disconnect_signal("title")

    def test_unterminated_osc_ends_at_escape(self):
        """End an OSC string unapplied at an ESC not followed by a backslash, and parse what follows."""
        self.connect_signal("title")
        for chunks in (["a\\e]0;title\\e[31mred"], ["a\\e]0;title\\e", "[31mred"]):
            with self.subTest(chunks=chunks):
                for chunk in chunks:
                    self.write(chunk)
                    self.read()
                self.expect(
                    [
                        [
                            (None, None, b"a"),
                            *[(urwid.AttrSpec("dark red", "default"), None, c) for c in (b"r", b"e", b"d")],
                        ]
                    ],
                    raw=True,
                )
                self.assertIsNone(self._sig_response)
                self.write("\\e[0m\\e[H\\e[2J")
        self.disconnect_signal("title")

    def test_osc_terminated_by_st_across_chunks(self):
        """Apply an OSC title whose ESC backslash terminator is split across two reads."""
        self.connect_signal("title")
        self.write("\\e]0;title\\e")
        self.read()
        self.assertEqual(self.term.term.escbuf, b"0;title\x1b")
        self.assertIsInstance(self.term.term.escbuf, bytes)
        self.write("\\rest")
        self.expect("rest")
        self.expect_signal("title")
        self.disconnect_signal("title")

    def test_title_never_contains_escape(self):
        """Take the title from the OSC string an ESC starts, not from the unterminated one before it."""
        self.connect_signal("title")
        self.write("\\e]0;ti\\e")
        self.read()
        self.write("]0;tle\007x")
        self.expect("x")
        self.expect_signal("tle")
        self.disconnect_signal("title")

    def test_command_strings_are_discarded(self) -> None:
        """Discard a DCS, SOS, PM or APC string up to its ST, ignoring BEL in it, as xterm does."""
        self.beeped = False
        urwid.connect_signal(self.term, "beep", self.caught_beep)
        red = urwid.AttrSpec("dark red", "default")
        for label, chunks, line in (
            ("DCS", [r"a\eP1;1|17/ab\e\b"], [(None, None, b"a"), (None, None, b"b")]),
            ("SOS", [r"a\eXsos\e\b"], [(None, None, b"a"), (None, None, b"b")]),
            ("PM", [r"a\e^pm\e\b"], [(None, None, b"a"), (None, None, b"b")]),
            (
                "APC, as in the kitty graphics protocol",
                [r"a\e_Gf=24;AAAA\e\b"],
                [(None, None, b"a"), (None, None, b"b")],
            ),
            ("ST across reads", [r"a\ePx\e", r"\b"], [(None, None, b"a"), (None, None, b"b")]),
            ("BEL inside", ["a\\ePx\x07y\\e\\b"], [(None, None, b"a"), (None, None, b"b")]),
            ("CAN aborts the string", ["a\\ePx\x18b"], [(None, None, b"a"), (None, None, b"b")]),
            (
                "an ESC ends the string and starts a sequence",
                [r"a\ePx\e[31mb"],
                [(None, None, b"a"), (red, None, b"b")],
            ),
            ("a control after an ESC inside is executed", ["a\\ePx\\e\b\\b"], [(None, None, b"b")]),
        ):
            with self.subTest(label):
                self.restart()
                for chunk in chunks:
                    self.write(chunk)
                    self.read()
                self.expect([line], raw=True)
                self.assertEqual(bytes(self.pty.from_widget), b"")
        self.assertFalse(self.beeped)

    def test_escape_with_intermediate_bytes_is_read_whole(self) -> None:
        """Read an escape sequence with any intermediate bytes up to its final byte, printing none of it."""
        for sequence in (
            r"\e G",
            r"\e F",
            r"\e*0",
            r"\e+B",
            r"\e-A",
            r"\e(%5",
            r"\e%/G",
            r"\e*E",
            r"\e+Z",
            r"\e*7",
            r"\e-M",
            r"\e.H",
            r"\e 7",
        ):
            with self.subTest(sequence=sequence):
                self.restart()
                self.write(rf"a{sequence}b")
                self.expect("ab")
                # a final byte that is a single-character sequence of its own, such as DECID, is not run
                self.assertEqual(bytes(self.pty.from_widget), b"")
                self.assertIsNone(self.term.term.saved_cursor)

    def test_set_leds(self):
        self.connect_signal("leds")
        self.write(r"\e[0qtest1")
        self.expect("test1")
        self.expect_signal("clear")
        self.write(r"\e[3q\e[H\e[Ktest2")
        self.expect("test2")
        self.expect_signal("caps_lock")
        self.disconnect_signal("leds")

    def test_in_listbox(self):
        listbox = urwid.ListBox([urwid.BoxAdapter(self.term, 80)])
        listbox.render((80, 24))

    def test_bracketed_paste_mode_on(self):
        self.write(r"\e[?2004htest")
        self.expect("test")
        self.assertTrue(self.term.term_modes.bracketed_paste)
        self.term.keypress(None, "begin paste")
        self.term.keypress(None, "A")
        self.term.keypress(None, "end paste")
        self.expect(r"test^[[200~A^[[201~")

    def test_bracketed_paste_mode_off(self):
        self.write(r"\e[?2004ltest")
        self.expect("test")
        self.assertFalse(self.term.term_modes.bracketed_paste)
        self.term.keypress(None, "begin paste")
        self.term.keypress(None, "B")
        self.term.keypress(None, "end paste")
        self.expect(r"testB")

    def test_synchronized_output_mode_on(self):
        self.write(r"\e[?2026htest")
        self.expect("test")
        self.assertTrue(self.term.term_modes.synchronized_output)

    def test_synchronized_output_mode_off(self):
        self.write(r"\e[?2026ltest")
        self.expect("test")
        self.assertFalse(self.term.term_modes.synchronized_output)

    def test_synchronized_output_block_spanning_chunks_drains_in_one_feed(self):
        """A synchronized-output block bigger than one os.read() chunk (4096 bytes) is fully
        drained within a single feed() call, so a render() in between never lands mid-block."""
        self.write(r"\e[?2026h" + "a" * 5000 + r"\e[?2026l" + "B")

        got = self.read()

        self.assertFalse(self.term.term_modes.synchronized_output)
        self.assertTrue(got.endswith(b"B"))

    def test_control_sequences(self) -> None:
        """Draw the screen each control sequence is specified to produce."""
        for label, size, output, screen in (
            ("ICH inserts blanks at the cursor", (80, 24), r"abcdef\e[1G\e[2@XY", "XYabcdef"),
            ("DCH pulls the rest of the line left", (80, 24), r"abcdef\e[2G\e[2P", "adef"),
            ("ECH blanks cells without moving the rest", (80, 24), r"abcdef\e[2G\e[3X", "a   ef"),
            ("HTS sets a tabstop", (80, 24), "\\e[3g\\e[1;5H\\eH\\e[1G\ta", "    a"),
            ("TBC 0 clears the tabstop at the cursor", (80, 24), "\\e[1;9H\\e[g\\e[1G\ta", " " * 16 + "a"),
            ("TBC 3 clears every tabstop", (80, 24), "\\e[3g\\e[1G\ta", " " * 79 + "a"),
            ("HT moves over cells without erasing them", (80, 24), "abc\r\tX", "abc     X"),
            ("NEL and RI", (80, 24), r"a\eEb\eMc", "ac\nb"),
            ("IND keeps the column", (80, 24), r"a\eDb", "a\n b"),
            ("IRM inserts instead of replacing", (80, 24), r"abc\e[1G\e[4hX", "Xabc"),
            ("LNM makes VT a newline", (80, 24), "\\e[20hab\x0bcd", "ab\ncd"),
            ("DECALN fills the screen with E", (4, 2), r"\e#8", "EEEE\nEEEE"),
            ("OSC palette set ends with its 7th hex digit", (80, 24), r"\e]Pabcdef0xy", "xy"),
            ("OSC palette reset ends with its R", (80, 24), r"\e]Rxy", "xy"),
            ("OSC palette set cut short by ST", (80, 24), r"\e]Pabcdef\e\xy", "xy"),
            ("OSC palette set cut short by a CSI", (80, 24), r"ab\e]Pabcdef\e[1GX", "Xb"),
            ("ESC inside a CSI sequence starts a new one", (80, 24), r"ab\e[3\e[1GX", "Xb"),
            ("ESC inside a C1 CSI sequence starts a new one", (80, 24), "ab\x9b3\\e[1GX", "Xb"),
            ("C1 CSI inside a CSI sequence starts a new one", (80, 24), "ab\\e[3\x9b1GX", "Xb"),
            ("C1 CSI inside ESC ( starts a new sequence", (80, 24), "ab\\e(\x9b1GX", "Xb"),
            ("C1 CSI after an ESC starts a new sequence", (80, 24), "ab\\e\x9b1GX", "Xb"),
            ("C1 CSI after an over-long CSI starts a new one", (80, 24), "ab\\e[" + "1;" * 300 + "\x9b1GX", "Xb"),
            ("C1 CSI after an ESC inside an OSC string starts a CSI", (80, 24), "ab\\e]0;t\\e\x9b1GX", "Xb"),
            ("C1 CSI is displayed in display control mode", (80, 24), "\\e[3hab\x9bc", "ab\x9bc"),
            ("ESC after an ESC starts a new sequence", (80, 24), r"ab\e\e[1GX", "Xb"),
            ("ESC inside ESC % starts a new sequence", (80, 24), r"ab\e%\e[1GX", "Xb"),
            ("ESC inside ESC ( starts a new sequence", (4, 2), r"\e(\e#8", "EEEE\nEEEE"),
            ("ESC inside ESC # starts a new sequence", (80, 24), r"ab\e#\ecd", "d"),
            ("ESC # c is no terminal reset", (80, 24), r"ab\e#cd", "abd"),
            ("ESC # M is no reverse line feed", (80, 24), "a\nb\\e#Mc", "a\nbc"),
            ("DECSTBM with top below bottom is ignored", (80, 24), r"\e[5;2rtext", "text"),
            ("CUU, CUF, CUD and CUB are relative", (80, 24), r"\e[3;3H\e[2A\e[2C\e[1B\e[3Dx", "\n x"),
            ("CNL and CPL go to the first column", (80, 24), r"\e[2;5H\e[1Ea\e[2Fb", "b\n\na"),
            ("VPA keeps the column", (80, 24), r"\e[3dx", "\n\nx"),
            ("SCOSC and SCORC", (80, 24), r"ab\e[s\e[3;1Hcd\e[uXY", "abXY\n\ncd"),
            ("UTF-8 and default charset selection", (80, 24), r"\e%G\e%@ab", "ab"),
            ("IL pushes the bottom line off the region", (3, 3), "a\nb\nc\\e[H\\e[L", "\na\nb"),
            ("IL below the scrolling region is ignored", (3, 4), "a\nb\nc\nd\\e[1;2r\\e[4;1H\\e[L", "a\nb\nc\nd"),
            ("DL below the scrolling region is ignored", (3, 4), "a\nb\nc\nd\\e[1;2r\\e[4;1H\\e[M", "a\nb\nc\nd"),
        ):
            with self.subTest(label):
                self.restart(*size)
                self.write(output)
                self.expect(screen)

    def test_huge_counts_are_bounded_by_the_screen(self) -> None:
        """Apply an ICH, DCH, IL or DL count larger than the screen at once instead of once per unit.

        A count applied one unit at a time does not finish, and the project-wide pytest timeout fails the test.
        """
        count = 10**15
        for label, size, output, screen in (
            ("ICH", (80, 24), rf"abcdef\e[3G\e[{count}@x", "abx"),
            ("DCH", (80, 24), rf"abcdef\e[3G\e[{count}Px", "abx"),
            ("IL", (3, 3), f"a\nb\nc\\e[2;1H\\e[{count}Lx", "a\nx"),
            ("DL", (3, 3), f"a\nb\nc\\e[2;1H\\e[{count}Mx", "a\nx"),
        ):
            with self.subTest(label):
                self.restart(*size)
                self.write(output)
                self.expect(screen)

    def test_overlong_sequences_are_bounded_and_skipped(self) -> None:
        """Skip a CSI or OSC sequence over the shared length limit, without buffering more than the limit."""
        csi_limit = urwid.ansi_parser.MAX_CSI_LENGTH
        osc_limit = urwid.ansi_parser.MAX_OSC_LENGTH
        for label, output in (
            ("CSI over the limit is not applied", "a\\e[" + "1;" * csi_limit + "31mb"),
            ("OSC over the limit ends at BEL", "a\\e]0;" + "A" * osc_limit + "\ab"),
            ("OSC over the limit ends at ST", "a\\e]0;" + "A" * osc_limit + "\\e\\b"),
        ):
            with self.subTest(label):
                self.restart()
                self.connect_signal("title")
                self.write(output)
                self.drain()
                self.expect([[(None, None, b"a"), (None, None, b"b")]], raw=True)
                self.assertIsNone(self._sig_response)
                self.disconnect_signal("title")
        for label, output, limit in (
            ("unterminated CSI", "\\e[" + "1;" * 10 * csi_limit, csi_limit),
            ("unterminated OSC", "\\e]0;" + "A" * 10 * osc_limit, osc_limit),
        ):
            with self.subTest(label):
                self.restart()
                self.write(output)
                self.drain()
                self.assertLessEqual(len(self.term.term.escbuf), limit)
        # an ESC other than ST ends an over-long OSC and starts the next sequence
        self.restart()
        self.write("\\e]0;" + "A" * osc_limit + "\\e[31mx")
        self.drain()
        self.expect([[(urwid.AttrSpec("dark red", "default"), None, b"x")]], raw=True)

    def test_insert_and_remove_lines_at_a_given_row(self) -> None:
        """Insert or remove lines at the row passed in, not at the cursor or the top of the scrolling region."""
        for label, edit, screen in (
            ("insert", lambda canvas: canvas.insert_lines(row=1), "a\n\nb"),
            ("remove", lambda canvas: canvas.remove_lines(row=1), "a\nc"),
        ):
            with self.subTest(label):
                self.restart(3, 3)
                self.write("a\nb\nc")
                self.read()
                edit(self.term.term)
                self.expect(screen)

    def test_responses(self) -> None:
        """Answer each terminal query on the PTY."""
        for label, query, answer in (
            ("CPR reports the 1-based cursor position", r"\e[3;5H\e[6n", b"\x1b[3;5R"),
            (
                "CPR in origin mode counts the row from the top margin, as CUP does",
                r"\e[3;7r\e[?6h\e[2;4H\e[6n",
                b"\x1b[2;4R",
            ),
            ("DSR reports the terminal OK", r"\e[5n", b"\x1b[0n"),
            ("DECXCPR reports the cursor position on page 1", r"\e[3;5H\e[?6n", b"\x1b[?3;5;1R"),
            (
                "DECXCPR in origin mode counts the row from the top margin",
                r"\e[3;7r\e[?6h\e[2;4H\e[?6n",
                b"\x1b[?2;4;1R",
            ),
            (
                "the DEC DSR forms report the terminal OK, no printer, unlocked keys and the keyboard",
                r"\e[?5n\e[?15n\e[?25n\e[?26n",
                b"\x1b[?0n\x1b[?13n\x1b[?20n\x1b[?27;1;0;0n",
            ),
            ("the DEC DSR forms of the other reports are not answered", r"\e[?53n\e[15n\e[25n\e[26n", b""),
            ("DA reports a VT320 with selective erase and ANSI colour", r"\e[c", b"\x1b[?63;6;22c"),
            ("DA with a private marker is not answered", r"\e[?c", b""),
            ("DECID reports a VT320", r"\eZ", b"\x1b[?63;6;22c"),
            ("DECID after an unfinished ESC # reports a VT320", r"\e#\eZ", b"\x1b[?63;6;22c"),
            ("ESC # Z is no DECID and is not answered", r"\e#Z", b""),
            ("the kitty keyboard flags are answered before DA", r"\e[?u\e[c", b"\x1b[?0u\x1b[?63;6;22c"),
            ("Secondary DA reports a VT320", r"\e[>c\e[>0c", b"\x1b[>24;10;0c" * 2),
            ("Secondary DA with a parameter other than 0 is not answered", r"\e[>1c", b""),
            ("Tertiary DA reports unit ID zero", r"\e[=c\e[=0c", b"\x1bP!|00000000\x1b\\" * 2),
            ("Tertiary DA with a parameter other than 0 is not answered", r"\e[=1c", b""),
            ("Tertiary DA is not answered at the VT100 level", r'\e[61"p\e[=c', b""),
            ("DECRQCRA counts a blank cell 0", r"\e[5;1;1;1;1;1*y", b"\x1bP5!~0000\x1b\\"),
            (
                "DECRQCRA adds bold, blink, reverse and underline to the character, not faint or colours",
                r"A\e[1mA\e[0;5mA\e[0;7mA\e[0;4mA\e[0;2;31mA\e[0m"
                + "".join(rf"\e[1;1;1;{col};1;{col}*y" for col in range(1, 7)),
                b"".join(b"\x1bP1!~%s\x1b\\" % code for code in (b"FFBF", b"FF3F", b"FF7F", b"FF9F", b"FFAF", b"FFBF")),
            ),
            ("DECRQCRA takes the low 7 bits of a character", "\xc3\xa9\\e[1;1;1;1;1;1*y", b"\x1bP1!~FF97\x1b\\"),
            ("DECRQCRA sums a rectangle, the whole page by default", r"AB\e[1;1*y", b"\x1bP1!~FF7D\x1b\\"),
            (
                "DECRQCRA counts rows from the top margin in origin mode",
                r"\e[3;7r\e[?6hA\e[1;1;1;1;1;1*y",
                b"\x1bP1!~FFBF\x1b\\",
            ),
            (
                "DECRQCRA without parameters is not answered, and an empty Pid is 65535, as in xterm",
                r"\e[*y\e[;*y\e[7*y",
                b"\x1bP65535!~0000\x1b\\\x1bP7!~0000\x1b\\",
            ),
            ("DECRQCRA is not answered at the VT100 level", r'\e[61"p\e[1;1;1;1;1;1*y', b""),
            (
                "DECFRA fills in the current attributes, and DECERA erases",
                r"\e[1m\e[88;1;1;2;3$x\e[0m\e[1;1;1;1;2;3*y\e[1;1;1;1$z\e[1;1;1;1;1;1*y\e[1;1;1;2;1;2*y",
                b"\x1bP1!~FAF0\x1b\\\x1bP1!~FFE0\x1b\\\x1bP1!~FF28\x1b\\",
            ),
            *(
                (
                    f"DECRQCRA counts a cell left by {label} as xterm does",
                    "\\ec" + data + "\\e[0m" + rf"\e[1;1;{row};{col};{row};{col}*y",
                    b"\x1bP1!~%s\x1b\\" % value,
                )
                for label, data, row, col, value in (
                    ("EL, never written", "ABCD\\e[1;2H\\e[1m\\e[K", 1, 2, b"0000"),
                    ("ED, never written", "ABCD\\e[1;2H\\e[1m\\e[J", 1, 2, b"0000"),
                    ("EL 1, a space without attributes", "ABCD\\e[1;2H\\e[1m\\e[1K", 1, 1, b"FFE0"),
                    ("ED 1, a space on the cursor row", "ABCD\\e[2;2H\\e[1m\\e[1J", 2, 2, b"FFE0"),
                    ("ED 1, never written above the cursor row", "ABCD\\e[2;2H\\e[1m\\e[1J", 1, 1, b"0000"),
                    ("ECH, a space without attributes", "ABCD\\e[1;2H\\e[1m\\e[2X", 1, 2, b"FFE0"),
                    ("ECH up to the last column, never written", "ABCD\\e[1;1H\\e[1m\\e[80X", 1, 1, b"0000"),
                    ("ICH, a space without attributes", "ABCD\\e[1;2H\\e[1m\\e[2@", 1, 2, b"FFE0"),
                    ("DECIC, a space without attributes", "ABCD\\e[1;2H\\e[1m\\e['}", 1, 2, b"FFE0"),
                    ("DCH, never written", "ABCD\\e[1;1H\\e[1m\\e[2P", 1, 80, b"0000"),
                    ("IL, never written", "ABCD\\e[1;1H\\e[1m\\e[L", 1, 1, b"0000"),
                    ("scrolling, never written", "ABCD\\e[1m\\e[24;1H\n", 24, 1, b"0000"),
                    ("DECERA, a space in the attributes", "ABCD\\e[1m\\e[1;2;1;2$z", 1, 2, b"FF60"),
                    ("a written space", " ", 1, 1, b"FFE0"),
                    ("a written bold space", "\\e[1m ", 1, 1, b"FF60"),
                    ("a tab, never written", "\\e[1m\tX", 1, 2, b"0000"),
                    ("DECALN, a plain E", "\\e[1m\\e#8", 1, 1, b"FFBB"),
                    ("a Latin-1 character, its low 7 bits", "\xc3\xa9", 1, 1, b"FF97"),
                    ("a no-break space", "\xc2\xa0", 1, 1, b"FFE5"),
                    ("U+00FF", "\xc3\xbf", 1, 1, b"0000"),
                    ("a character past Latin-1", "\xe2\x82\xac", 1, 1, b"FFE5"),
                    ("a DEC graphics character", "\\e(0q", 1, 1, b"FFE3"),
                    ("a DEC graphics blank", "\\e(0_", 1, 1, b"0000"),
                    ("a DEC graphics degree sign", "\\e(0f", 1, 1, b"FF50"),
                )
            ),
            (
                "DECRQCRA values a blank and a written space apart in one request",
                r"\e[2;1H \e[1;1;1;1;2;1*y",
                b"\x1bP1!~FFE0\x1b\\",
            ),
            *(
                (
                    f"DECRQCRA counts the cells as xterm does after {label}",
                    '\\ecA\\e[1"qBC\\e[0"qD'
                    + data
                    + "".join(rf"\e[1;1;{row};{col};{row};{col}*y" for col in range(1, 5)),
                    b"".join(b"\x1bP1!~%s\x1b\\" % value for value in values.encode().split()),
                )
                for label, data, row, values in (
                    ("DECSCA, which adds 0x04 to a protected character", "", 1, "FFBF FFBA FFB9 FFBC"),
                    ("DECSEL, which keeps protected characters", r"\e[1;1H\e[?K", 1, "FFE0 FFBA FFB9 0000"),
                    ("DECSEL 1", r"\e[1;3H\e[?1K", 1, "FFE0 FFBA FFB9 FFBC"),
                    ("DECSEL 2", r"\e[?2K", 1, "FFE0 FFBA FFB9 0000"),
                    ("DECSED 0", r"\e[1;1H\e[?J", 1, "FFE0 FFBA FFB9 0000"),
                    ("DECSED 2", r"\e[?2J", 1, "FFE0 FFBA FFB9 0000"),
                    ("EL, which erases protected characters", r"\e[1;1H\e[K", 1, "0000 0000 0000 0000"),
                    ("ECH, which erases protected characters", r"\e[1;1H\e[4X", 1, "FFE0 FFE0 FFE0 FFE0"),
                    ("DECERA, which erases protected characters", r"\e[1;1;1;4$z", 1, "FFE0 FFE0 FFE0 FFE0"),
                    ("DECERA while DECSCA protects", r'\e[1"q\e[1;1;1;4$z\e[0"q\e[?2K', 1, "FFDC FFDC FFDC FFDC"),
                    ("DECFRA while DECSCA protects", r'\e[1"q\e[88;1;1;1;4$x\e[0"q\e[?2K', 1, "FFA4 FFA4 FFA4 FFA4"),
                    ("EL while DECSCA protects", r'\e[1"q\e[1;1H\e[K\e[0"q\e[?2K', 1, "0000 0000 0000 0000"),
                    (
                        "DECCRA, which copies the protection",
                        r"\e[1;1;1;4;1;2;1$v\e[2;1H\e[?2K",
                        2,
                        "FFE0 FFBA FFB9 0000",
                    ),
                    ("overwriting a protected character", r"\e[1;2HX\e[?2K", 1, "FFE0 FFE0 FFB9 0000"),
                    ("DECSERA on a cell never written", r"\e[2;1;2;1${", 2, "FFE0 0000 0000 0000"),
                    ("RIS", r"\ecABCD\e[?2K", 1, "0000 0000 0000 0000"),
                    ("SPA, which adds 0x04 too, and ED", r"\ecX\eVAB\eWC\e[1;1H\e[J", 1, "FFE0 FFBB FFBA 0000"),
                    ("SPA and ECH", r"\ecX\eVAB\eWC\e[1;1H\e[4X", 1, "FFE0 FFBB FFBA FFE0"),
                )
            ),
            *(
                (f"DECRQSS reports DECSCA {label}", rf'\ec{data}\eP$q"q{_ST}', b'\x1bP1$r%s"q\x1b\\' % value)
                for label, data, value in (
                    ("off at startup", "", b"0"),
                    ("set", r'\e[1"q', b"1"),
                    ("reset by 2", r'\e[1"q\e[2"q', b"0"),
                    ("reset by no parameter", r'\e[1"q\e["q', b"0"),
                    ("set, ignoring a value past 2", r'\e[1"q\e[5"q', b"1"),
                    ("set, ignoring SGR 0", r'\e[1"q\e[0m', b"1"),
                    ("set, as DECRC restores it", r'\e[1"q\e7\e[0"q\e8', b"1"),
                    ("set, as SCORC restores it", r'\e[1"q\e[s\e[0"q\e[u', b"1"),
                    ("off while SPA protects", r"\eV", b"0"),
                    ("set by DECSCA after SPA", r'\eV\e[1"q', b"1"),
                    ("off, as EPA ends DECSCA", r'\e[1"q\eW', b"0"),
                    ("off after DECSTR", r'\e[1"q\e[!p', b"0"),
                    ("off after RIS", r'\e[1"q\ec', b"0"),
                )
            ),
            *(
                (
                    f"DECRQCRA counts the cells as xterm does after {label}",
                    "\\ec"
                    + data
                    + "".join(
                        rf"\e[1;1;{row};{col};{row};{col}*y" for row in range(1, rows + 1) for col in range(1, 5)
                    ),
                    b"".join(b"\x1bP1!~%s\x1b\\" % value for value in values.encode().split()),
                )
                for label, data, rows, values in (
                    ("DECCARA setting bold", r"ABCD\e[1;2;1;3;1$r", 1, "FFBF FF3E FF3D FFBC"),
                    (
                        "DECCARA setting underline, blink and reverse video",
                        r"ABCD\e[1;1;1;1;4$r\e[1;2;1;2;5$r\e[1;3;1;3;7$r",
                        1,
                        "FFAF FF7E FF9D FFBC",
                    ),
                    ("DECCARA 0", r"\e[1;4;5;7mABCD\e[0m\e[1;1;1;4;0$r", 1, "FFBF FFBE FFBD FFBC"),
                    ("DECCARA without attributes", r"\e[1;4;5;7mABCD\e[0m\e[1;1;1;4$r", 1, "FECF FECE FECD FECC"),
                    (
                        "DECCARA resetting each attribute",
                        r"\e[1;4;5;7mABCD\e[0m\e[1;1;1;1;22$r\e[1;2;1;2;24$r\e[1;3;1;3;25$r\e[1;4;1;4;27$r",
                        1,
                        "FF4F FEDE FF0D FEEC",
                    ),
                    ("DECCARA in order", r"ABCD\e[1;1;1;1;1;22$r\e[1;2;1;2;22;1$r", 1, "FFBF FF3E FFBD FFBC"),
                    ("DECCARA ignoring another parameter", r"A\e[1;1;1;1;1;99$r", 1, "FF3F 0000 0000 0000"),
                    ("DECCARA keeping the protection", r'\e[1"qA\e[0"q\e[1;1;1;1;1$r', 1, "FF3B 0000 0000 0000"),
                    (
                        "DECCARA in origin mode",
                        "ABCD\nEFGH" + r"\e[2;5r\e[?6h\e[1;1;1;1;1$r\e[?6l\e[r",
                        2,
                        "FFBF FFBE FFBD FFBC FF3B FFBA FFB9 FFB8",
                    ),
                    ("DECRARA", r"ABCD\e[1;1;1;2;7$r\e[1;2;1;3;7$t", 1, "FF9F FFBE FF9D FFBC"),
                    ("DECRARA 0", r"\e[1mA\e[0mB\e[1;1;1;2;0$t", 1, "FF4F FECE 0000 0000"),
                    ("DECRARA without attributes", r"\e[1mA\e[0mB\e[1;1;1;2$t", 1, "FF3F FFBE 0000 0000"),
                    ("DECRARA ignoring 22", r"\e[1mA\e[0m\e[1;1;1;1;22$t", 1, "FF3F 0000 0000 0000"),
                    ("DECRARA reversing twice", r"A\e[1;1;1;1;1;1$t", 1, "FFBF 0000 0000 0000"),
                    (
                        "DECCARA in a stream, the default",
                        "ABCD\nEFGH\nIJKL" + r"\e[1;2;3;3;1$r",
                        3,
                        "FFBF FF3E FF3D FF3C FF3B FF3A FF39 FF38 FF37 FF36 FF35 FFB4",
                    ),
                    (
                        "DECCARA in a rectangle after DECSACE 2",
                        "ABCD\nEFGH\nIJKL" + r"\e[2*x\e[1;2;3;3;1$r",
                        3,
                        "FFBF FF3E FF3D FFBC FFBB FF3A FF39 FFB8 FFB7 FF36 FF35 FFB4",
                    ),
                    (
                        "DECCARA in a stream after DECSACE 3",
                        "ABCD\nEFGH" + r"\e[3*x\e[1;2;2;3;1$r",
                        2,
                        "FFBF FF3E FF3D FF3C FF3B FF3A FF39 FFB8",
                    ),
                    (
                        "DECCARA in a stream, skipping cells never written",
                        r"AB\e[1;1;1;4;1$r",
                        1,
                        "FF3F FF3E 0000 0000",
                    ),
                    ("DECCARA in a rectangle, writing spaces", r"AB\e[2*x\e[1;1;1;4;1$r", 1, "FF3F FF3E FF60 FF60"),
                    ("DECRARA in a rectangle", r"AB\e[2*x\e[1;1;1;4;7$t", 1, "FF9F FF9E FFC0 FFC0"),
                    ("DECCARA 0 in a rectangle", r"\e[2*x\e[1;1;1;1;0$r", 1, "FFE0 0000 0000 0000"),
                    ("DECCARA without attributes in a rectangle", r"\e[2*x\e[1;1;1;1$r", 1, "FFE0 0000 0000 0000"),
                    (
                        "DECERA after DECSACE 1, still on a rectangle",
                        "ABCD\nEFGH" + r"\e[1*x\e[1;2;2;3$z",
                        2,
                        "FFBF FFE0 FFE0 FFBC FFBB FFE0 FFE0 FFB8",
                    ),
                )
            ),
            (
                "DECRQSS reports any DECSACE, and no parameter as 0",
                rf"\eP$q*x{_ST}\e[2*x\eP$q*x{_ST}\e[3*x\eP$q*x{_ST}\e[*x\eP$q*x{_ST}",
                b"".join(b"\x1bP1$r%s*x\x1b\\" % value for value in (b"0", b"2", b"3", b"0")),
            ),
            (
                "DECSTR keeps DECSACE, and RIS resets it",
                rf"\e[2*x\e[!p\eP$q*x{_ST}\ec\eP$q*x{_ST}",
                b"\x1bP1$r2*x\x1b\\\x1bP1$r0*x\x1b\\",
            ),
            (
                "DECCIR reports DECSCA, and DECRSPS restores it",
                rf'\e[1"q\e[1$w\e[0"q\eP1$t1;1;1;@;A;@;0;2;@;BBBB{_ST}\eP$q"q{_ST}',
                b'\x1bP1$u1;1;1;@;A;@;0;2;@;B0BB\x1b\\\x1bP1$r1"q\x1b\\',
            ),
            (
                "DECRSPS keeps the protection SPA started, which DECCIR does not report",
                rf'\eV\eP1$t1;1;1;@;@;@;0;2;@;B0BB{_ST}\e[5"q\eP$q"q{_ST}',
                b'\x1bP1$r1"q\x1b\\',
            ),
            (
                "DECCIR does not report SPA",
                r"\eV\e[1$w",
                b"\x1bP1$u1;1;1;@;@;@;0;2;@;B0BB\x1b\\",
            ),
            *(
                (
                    f"DECCIR reports no pending wrap after {label}, as xterm does",
                    "A" * 80 + data + r"\e[1$w",
                    b"\x1bP1$u1;%d;1;@;@;@;0;2;@;B0BB\x1b\\" % column,
                )
                for label, data, column in (
                    ("CR", "\r", 1),
                    ("BS", "\b", 79),
                    ("DECSTBM", r"\e[1;3r", 1),
                    ("DECOM reset", r"\e[?6l", 1),
                    ("ED", r"\e[2J", 80),
                    ("EL", r"\e[K", 80),
                    ("ECH", r"\e[X", 80),
                    ("the alternate screen is shown", r"\e[?1049h", 80),
                )
            ),
            ("DECRQDE reports the screen", r'\e["v', b'\x1b[24;80;1;1;1"w'),
            (
                "DECRQM reports DECLRMM and DECKBUM permanently reset",
                r"\e[?69h\e[?69$p\e[?68$p",
                b"\x1b[?69;4$y\x1b[?68;4$y",
            ),
            (
                "DECRQSS reports the full-width margins and the lines per screen",
                rf"\eP$qs{_ST}\eP$q*|{_ST}",
                b"\x1bP1$r1;80s\x1b\\\x1bP1$r24*|\x1b\\",
            ),
            ("DECFRA ignores a control character", r"\e[10;1;1;1;1$x\e[1;1;1;1;1;1*y", b"\x1bP1!~0000\x1b\\"),
            (
                "DECCRA copies a rectangle and leaves the source",
                r"AB\e[1;1;1;2;1;3;5;1$v\e[1;1;3;5;3;6*y\e[1;1;1;1;1;2*y",
                b"\x1bP1!~FF7D\x1b\\" * 2,
            ),
            ("DECRQSS reports the lines per page", rf"\eP$qt{_ST}", b"\x1bP1$r24t\x1b\\"),
            (
                "DECRQSS reports the cursor style DECSCUSR set, 0 being 1, a style past 6 ignored",
                rf"\eP$q q{_ST}\e[0 q\eP$q q{_ST}\e[5 q\e[7 q\eP$q q{_ST}",
                b"\x1bP1$r2 q\x1b\\\x1bP1$r1 q\x1b\\\x1bP1$r5 q\x1b\\",
            ),
            (
                "DECSTR and RIS restore the steady block cursor",
                rf"\e[5 q\e[!p\eP$q q{_ST}\e[5 q\ec\eP$q q{_ST}",
                b"\x1bP1$r2 q\x1b\\" * 2,
            ),
            ("DECRQM reports a mode reset", r"\e[?2048$p", b"\x1b[?2048;2$y"),
            ("DECRQM reports a mode set", r"\e[?2004h\e[?2004$p", b"\x1b[?2004;1$y"),
            (
                "DECRQM reports the mouse tracking mode set",
                r"\e[?1002h\e[?1002$p\e[?1000$p",
                b"\x1b[?1002;1$y\x1b[?1000;2$y",
            ),
            ("DECRQM reports a mode with no state as unknown", r"\e[?30$p\e[?9999$p", b"\x1b[?30;0$y\x1b[?9999;0$y"),
            *(
                (
                    f"DECRQM reports ANSI mode {mode} permanently reset, as xterm does",
                    rf"\e[{mode}$p",
                    b"\x1b[%d;4$y" % mode,
                )
                for mode in (1, 5, 7, 10, 11, 13, 14, 15, 16, 17, 18, 19)
            ),
            *(
                (f"DECRQM reports DEC mode {mode} permanently reset", rf"\e[?{mode}$p", b"\x1b[?%d;4$y" % mode)
                for mode in (4, 8, 18, 19, 42)
            ),
            ("DECRQM reports DECCOLM reset, as xterm does without 132 columns", r"\e[?3h\e[?3$p", b"\x1b[?3;2$y"),
            (
                "DECRQM reports ANSI mode (DECANM) permanently set, as VT52 mode is not implemented",
                r"\e[?2l\e[?2$p",
                b"\x1b[?2;3$y",
            ),
            ("DECRQUPSS reports ISO Latin-1", r"\e[&u", b"\x1bP1!uA\x1b\\"),
            ("DECRQUPSS is not answered at the VT100 level", r'\e[61"p\e[&u', b""),
            ("DECRQM is not answered without a mode", r"\e[?$p\e[?1;2$p", b""),
            ("other sequences ending in p are not answered", r'\e[5p\e[!p\e[61;1"p', b""),
            (
                "DECRQM reports the ANSI modes",
                r"\e[4h\e[20h\e[4$p\e[20$p\e[3$p\e[2$p\e[12$p\e[99$p",
                b"\x1b[4;1$y\x1b[20;1$y\x1b[3;2$y\x1b[2;4$y\x1b[12;3$y\x1b[99;0$y",
            ),
            ("DECRQM for an ANSI mode is not answered without a mode", r"\e[$p\e[4;20$p", b""),
            (
                "DECRQM reports the keypad and backarrow modes",
                r"\e[?66$p\e=\e[?66$p\e>\e[?66$p\e[?66h\e[?66$p\e[?67$p\e[?67h\e[?67$p",
                b"\x1b[?66;2$y\x1b[?66;1$y\x1b[?66;2$y\x1b[?66;1$y\x1b[?67;2$y\x1b[?67;1$y",
            ),
            (
                "RIS resets the keypad and backarrow modes",
                r"\e[?66h\e[?67h\ec\e[?66$p\e[?67$p",
                b"\x1b[?66;2$y\x1b[?67;2$y",
            ),
            ("DECRQSS reports the default SGR", rf"\eP$qm{_ST}", b"\x1bP1$r0m\x1b\\"),
            (
                "DECRQSS reports the SGR set, bold making the colour bright",
                rf"\e[1;2;3;4;5;7;9;31;44m\eP$qm{_ST}",
                b"\x1bP1$r0;1;2;3;4;5;7;9;91;44m\x1b\\",
            ),
            (
                "DECRQSS reports a 256-colour SGR",
                rf"\e[38;5;100;48;5;7m\eP$qm{_ST}",
                b"\x1bP1$r0;38;5;100;48;5;7m\x1b\\",
            ),
            ("DECRQSS reports a true-colour SGR", rf"\e[48;2;1;2;3m\eP$qm{_ST}", b"\x1bP1$r0;48;2;1;2;3m\x1b\\"),
            ("DECRQSS leaves the hyperlink out of SGR", rf"\e]8;;http://x{_ST}\eP$qm{_ST}", b"\x1bP1$r0m\x1b\\"),
            ("DECRQSS reports the scrolling region", rf"\e[2;5r\eP$qr{_ST}", b"\x1bP1$r2;5r\x1b\\"),
            ("DECRQSS reports the whole screen as the region", rf"\eP$qr{_ST}", b"\x1bP1$r1;24r\x1b\\"),
            ("DECRQSS reports the conformance level", rf'\eP$q"p{_ST}', b'\x1bP1$r63;1"p\x1b\\'),
            ("DECRQSS reports the columns per page", rf"\eP$q$|{_ST}", b"\x1bP1$r80$|\x1b\\"),
            (
                "DECSCL sets the level DECRQSS reports, and ignores another level",
                rf'\e[62;1"p\eP$q"p{_ST}\e[64"p\e[60"p\eP$q"p{_ST}\e[63"p\eP$q"p{_ST}',
                b'\x1bP1$r62;1"p\x1b\\\x1bP1$r62;1"p\x1b\\\x1bP1$r63;1"p\x1b\\',
            ),
            (
                "at the VT100 level DECRQSS and DECRQPSR are not answered, DECRQM still is",
                rf'\e[61"p\eP$qm{_ST}\e[1$w\e[2$w\e[?66$p',
                b"\x1b[?66;2$y",
            ),
            ("DECSCL performs a soft reset", r'\e[?25l\e[63;1"p\e[?25$p', b"\x1b[?25;1$y"),
            (
                "DECRSPS keeps faint and the colours, which DECCIR does not carry",
                rf"\e[2;31m\eP1$t1;1;1;A;@;@;0;2;@;B0BB{_ST}\eP$qm{_ST}",
                b"\x1bP1$r0;1;2;91m\x1b\\",
            ),
            (
                "DECCIR reports the screen row in origin mode, and DECRSPS restores it",
                rf"\e[3;7r\e[?6h\e[1$w\eP1$t4;1;1;@;@;A;0;2;@;B0BB{_ST}\e[1$w",
                b"\x1bP1$u3;1;1;@;@;A;0;2;@;B0BB\x1b\\\x1bP1$u4;1;1;@;@;A;0;2;@;B0BB\x1b\\",
            ),
            ("RIS restores the VT300 level", rf'\e[61"p\ec\eP$q"p{_ST}', b'\x1bP1$r63;1"p\x1b\\'),
            (
                "DECCIR reports the cursor and the startup state",
                r"\e[3;5H\e[1$w",
                b"\x1bP1$u3;5;1;@;@;@;0;2;@;B0BB\x1b\\",
            ),
            (
                "DECCIR reports bold, underline, blink and reverse, not faint, italics or strikethrough",
                r"\e[1;4;5;7m\e[1$w\e[0;2;3;9m\e[1$w",
                b"\x1bP1$u1;1;1;O;@;@;0;2;@;B0BB\x1b\\\x1bP1$u1;1;1;@;@;@;0;2;@;B0BB\x1b\\",
            ),
            (
                "DECCIR reports origin mode and a pending autowrap",
                r"\e[?6h\e[1$w\e[?6l\e[1;80Hx\e[1$w",
                b"\x1bP1$u1;1;1;@;@;A;0;2;@;B0BB\x1b\\\x1bP1$u1;80;1;@;@;H;0;2;@;B0BB\x1b\\",
            ),
            (
                "DECCIR reports a pending single shift and the shifts into GL and GR",
                "\\eN\\e[1$w\\eO\\e[1$wy\x0e\\e|\\e[1$w",
                (
                    b"\x1bP1$u1;1;1;@;@;B;0;2;@;B0BB\x1b\\"
                    b"\x1bP1$u1;1;1;@;@;D;0;2;@;B0BB\x1b\\"
                    b"\x1bP1$u1;2;1;@;@;@;1;3;@;B0BB\x1b\\"
                ),
            ),
            (
                "DECCIR reports the designations, 96-character sets marked",
                r"\e(0\e)B\e*<\e[1$w\e-A\e.A\e/A\e[1$w",
                b"\x1bP1$u1;1;1;@;@;@;0;2;@;0B<B\x1b\\\x1bP1$u1;1;1;@;@;@;0;2;N;0AAA\x1b\\",
            ),
            (
                "DECTABSR reports the tab stops",
                r"\e[2$w\e[3g\e[1;3H\eH\e[1;10H\eH\e[2$w",
                b"\x1bP2$u1/9/17/25/33/41/49/57/65/73\x1b\\\x1bP2$u3/10\x1b\\",
            ),
            ("DECRQPSR for another report is not answered", r"\e[0$w\e[3$w\e[$w", b""),
            (
                "DECRSPS restores the tab stops, dropping one past the edge, and an empty list clears them",
                rf"\eP2$t5/9/81/33{_ST}\e[2$w\eP2$t{_ST}\e[2$w\eP2$t3{_ST}\eP2$t5/x{_ST}\e[2$w",
                b"\x1bP2$u5/9/33\x1b\\\x1bP2$u\x1b\\\x1bP2$u3\x1b\\",
            ),
            (
                "DECRSPS restores the cursor information DECCIR reported",
                rf"\eP1$t2;7;1;A;@;C;1;3;D;0BAB{_ST}\e[1$w\e[6n",
                b"\x1bP1$u2;7;1;A;@;C;1;3;D;0BAB\x1b\\\x1b[2;7R",
            ),
            (
                "DECRSPS sets origin mode before the cursor, and ends a single shift the report has none of",
                rf"\e[3;5r\e[?6h\eN\eP1$t1;1;1;@;@;@;0;2;@;BBBB{_ST}\e[1$w",
                b"\x1bP1$u1;1;1;@;@;@;0;2;@;BBBB\x1b\\",
            ),
            (
                "DECCIR reports a final byte it cannot carry as the default set",
                "\\e(\xc3\xa9\\e);\\e-\xc3\xa9\\e[1$w",
                b"\x1bP1$u1;1;1;@;@;@;0;2;B;BBBB\x1b\\",
            ),
            (
                "DECRSPS ignores a malformed DECCIR whole",
                rf"\e[2;2H\eP1$t5;5;1;A;@;@;0;2;@;0B{_ST}\eP1$tzz{_ST}\e[6n",
                b"\x1b[2;2R",
            ),
            (
                "DECRQSS answers a setting not reported as invalid",
                rf"\eP$q$}}{_ST}\eP$qmm{_ST}\eP$q{_ST}",
                b"\x1bP0$r\x1b\\" * 3,
            ),
            ("DECRQSS ignores BEL and ends only at ST", f"\\eP$q\x07m{_ST}", b"\x1bP1$r0m\x1b\\"),
            ("a DCS that is no DECRQSS is not answered", rf"\eP1$qm{_ST}\ePzz{_ST}", b""),
            ("an over-long DECRQSS is not answered", r"\eP$q" + "m" * 4096 + rf"{_ST}", b""),
            ("DECRQSS aborted by CAN is not answered", f"\\eP$qm\x18{_ST}", b""),
            ("mode 2048 reports the size on each set", r"\e[?2048h\e[?2048h", b"\x1b[48;24;80;0;0t" * 2),
            ("mode 2048 is reset by RIS", r"\e[?2048h\ec\e[?2048$p", b"\x1b[48;24;80;0;0t\x1b[?2048;2$y"),
        ):
            with self.subTest(label):
                self.restart()
                self.write(query)
                self.read()
                self.assertEqual(bytes(self.pty.from_widget), answer)

    def test_in_band_resize_reports_each_new_size(self) -> None:
        """Send the child a report after its new size is set, while mode 2048 is set and the pty takes input."""
        for mode, child_reads, answer in (
            (r"\e[?2048h", True, b"\x1b[48;30;100;0;0t"),
            (r"\e[?2048h\e[?2048l", True, b""),
            (r"\e[?2048h", False, b""),
        ):
            with self.subTest(mode=mode, child_reads=child_reads):
                self.restart()
                self.write(mode)
                self.read()
                self.pty.from_widget.clear()
                self.pty.child_reads = child_reads
                order: list[str] = []
                ioctl = mock.Mock(side_effect=lambda *_args, order=order: order.append("size") or 0)
                write = urwid.vterm.os.write

                with (
                    mock.patch("urwid.vterm.fcntl.ioctl", ioctl),
                    mock.patch(
                        "urwid.vterm.os.write",
                        side_effect=lambda *args, order=order, write=write: order.append("report") or write(*args),
                    ),
                ):
                    self.resize(100, 30)

                self.assertEqual(bytes(self.pty.from_widget), answer)
                self.assertEqual(["size", "report"] if answer else ["size"], order)

    def test_save_restore_cursor_esc_keeps_attributes(self) -> None:
        """Restore the attributes saved by DECSC, SCOSC or mode 1048 together with the cursor position."""
        red = urwid.AttrSpec("dark red", "default")
        for save, restore in ((r"\e7", r"\e8"), (r"\e[s", r"\e[u"), (r"\e[?1048h", r"\e[?1048l")):
            with self.subTest(save=save):
                self.restart()
                self.write(rf"\e[31mab{save}\e[0m\e[2;1Hcd{restore}e")
                self.expect(
                    [
                        [(red, None, b"a"), (red, None, b"b"), (red, None, b"e")],
                        [(None, None, b"c"), (None, None, b"d")],
                    ],
                    raw=True,
                )

    def test_save_restore_cursor_keeps_origin_mode_and_pending_wrap(self) -> None:
        """Restore origin mode and a pending autowrap with the cursor saved by DECSC or SCOSC, as xterm does."""
        for save, restore in ((r"\e7", r"\e8"), (r"\e[s", r"\e[u")):
            with self.subTest(save=save):
                self.restart(10, 8)
                # saved in origin mode inside the region rows 3 to 7, restored after origin mode was reset
                self.write(rf"\e[3;7r\e[?6h\e[2;2H{save}\e[?6l\e[1;1H{restore}\e[?6$p\e[6n")
                self.read()
                self.assertEqual(bytes(self.pty.from_widget), b"\x1b[?6;1$y\x1b[2;2R")
                self.restart(10, 8)
                # saved with the cursor waiting to wrap at the last column: the next character starts the next row
                self.write(rf"\e[1;10Hx{save}\e[3;3H{restore}y")
                self.expect([[*[(None, None, b" ")] * 9, (None, None, b"x")], [(None, None, b"y")]], raw=True)

    def test_saved_origin_mode_is_kept_per_screen(self) -> None:
        """Keep origin mode saved by DECSC with the screen it was saved on, as the position is kept."""
        self.restart(10, 8)
        self.write(r"\e[3;7r\e[?6h\e[2;2H\e7\e[?6l\e[?47h\e8\e[?6$p\e[?47l\e8\e[?6$p\e[6n")
        self.read()
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b[?6;2$y\x1b[?6;1$y\x1b[2;2R")

    def test_restore_cursor_without_a_saved_one_resets_it(self) -> None:
        """Move home and reset the attributes, the charsets and origin mode at DECRC or SCORC with nothing saved."""
        for restore in (r"\e8", r"\e[u"):
            with self.subTest(restore=restore):
                self.restart(10, 8)
                self.write(f"\\e[3;7r\\e[5;5H\\e[1;31m\x0e\\e[?6h{restore}q\\e[?6$p")
                self.expect([[(None, None, b"q")]], raw=True)
                self.assertEqual(bytes(self.pty.from_widget), b"\x1b[?6;2$y")

    def test_charset_designation(self) -> None:
        """Draw with the DEC special graphics set while it is designated as G0."""
        self.write(r"\e(0q\e(Bq")
        self.expect([[(None, "0", b"q"), (None, None, b"q")]], raw=True)

    def test_g2_and_g3_shifts(self) -> None:
        """Draw from G2 and G3 with the locking shifts LS2 and LS3, and for one character with SS2 and SS3."""
        dec = (None, "0", b"q")
        ascii_q = (None, None, b"q")
        for label, data, line in (
            ("SS2 shifts one character", r"\e*0q\eNqq", [ascii_q, dec, ascii_q]),
            ("SS3 shifts one character", r"\e+0q\eOqq", [ascii_q, dec, ascii_q]),
            ("SS2 returns to the locking shift in effect", "\\e*0\x0e\\eNqq", [dec, dec]),
            ("a designation during SS2 keeps it a single shift", r"\e*0\eN\e(Bqq", [dec, ascii_q]),
            ("SGR 10 during SS2 keeps it a single shift", r"\e*0\eN\e[10mqq", [dec, ascii_q]),
            ("SI during SS2 changes the slot it returns to", "\\e*0\x0e\\eN\x0fqq", [dec, ascii_q]),
            ("LS2 and LS3 stay until SI", "\\e*0\\e+0\\enq\\eoq\x0fq", [dec, dec, ascii_q]),
            ("a 96-character set is drawn as the default set", "\\e)0\\e-A\\e.A\\e/A\x0eq\\enq", [ascii_q, ascii_q]),
            ("RIS resets G2 and G3", r"\e*0\ec\enq", [ascii_q]),
        ):
            with self.subTest(label):
                self.restart()
                self.write(data)
                self.expect([line], raw=True)

    def test_designation_after_decsc_does_not_change_the_saved_charsets(self) -> None:
        """Restore the character sets DECSC saved, also after a designation made between DECSC and DECRC."""
        self.write("\\e7\\e(0\\e8\x0fq")
        self.expect([[(None, None, b"q")]], raw=True)

    def test_cursor_style_is_drawn_after_decscusr(self) -> None:
        """Draw the cursor cell in the style DECSCUSR set instead of the display's cursor, until DECSTR or RIS."""
        reverse = urwid.AttrSpec("default,standout", "default")
        underline = urwid.AttrSpec("default,underline", "default")
        red_reverse = urwid.AttrSpec("dark red,standout", "default")
        for label, data, cell, cursor in (
            ("the display's cursor before a DECSCUSR", r"AB\e[1;1H", (None, None, b"A"), (0, 0)),
            ("a block in reverse video", r"AB\e[1;1H\e[2 q", (reverse, None, b"A"), None),
            ("a blinking underline drawn steady", r"AB\e[1;1H\e[3 q", (underline, None, b"A"), None),
            ("a bar in reverse video", r"AB\e[1;1H\e[6 q", (reverse, None, b"A"), None),
            (
                "a reverse cell drawn back to normal",
                r"\e[7mA\e[0mB\e[1;1H\e[2 q",
                (urwid.AttrSpec("default", "default"), None, b"A"),
                None,
            ),
            (
                "an underlined cell drawn without the underline",
                r"\e[4mA\e[0mB\e[1;1H\e[4 q",
                (urwid.AttrSpec("default", "default"), None, b"A"),
                None,
            ),
            ("the cell keeps its colour", r"\e[31mA\e[0mB\e[1;1H\e[2 q", (red_reverse, None, b"A"), None),
            ("a hidden cursor is not drawn", r"AB\e[1;1H\e[2 q\e[?25l", (None, None, b"A"), None),
            ("DECSTR returns to the display's cursor", r"AB\e[1;1H\e[2 q\e[!p", (None, None, b"A"), (0, 0)),
            ("RIS returns to the display's cursor", r"\e[2 q\ecAB\e[1;1H", (None, None, b"A"), (0, 0)),
        ):
            with self.subTest(label):
                self.restart(10, 3)
                self.write(data)
                self.term.wait_and_feed()
                canvas = self.term.render(self.termsize, focus=True)
                self.assertEqual(next(iter(canvas.content()))[0], cell)
                self.assertEqual(canvas.cursor, cursor)
        # out of focus no cursor is drawn
        self.restart(10, 3)
        self.write(r"AB\e[1;1H\e[2 q")
        self.term.wait_and_feed()
        self.assertEqual(next(iter(self.term.render(self.termsize, focus=False).content()))[0], (None, None, b"A"))

    def test_wide_and_combining_characters(self) -> None:
        """Give a wide character two cells and join a character with no width to the one before, as xterm draws them.

        Which characters are wide is urwid's own width calculation, which differs between Unicode versions and so
        between terminals; the cases take characters whose width has not changed, or ask wcwidth.
        """
        wide = "\u4e2d"
        # a variation selector joins the heart only where urwid then draws it as wide as before
        heart = "\u2764\ufe0f" if wcwidth.width("\u2764\ufe0f") == wcwidth.width("\u2764") else "\u2764"
        for label, data, screen, cursor in (
            ("a wide character", wide, wide, (2, 0)),
            ("a character after a wide one", f"{wide}X", f"{wide}X", (3, 0)),
            ("a wide character in the last two columns", rf"\e[1;11H{wide}", " " * 10 + wide, (11, 0)),
            (
                "autowrap after a wide character in the last two columns",
                rf"\e[1;11H{wide}Y",
                " " * 10 + f"{wide}\nY",
                (1, 1),
            ),
            ("autowrap before a wide character in the last column", rf"\e[1;12H{wide}Y", f"\n{wide}Y", (3, 1)),
            ("no autowrap: dropped in the last column", rf"\e[?7l\e[1;12H{wide}Y", " " * 11 + "Y", (11, 0)),
            ("no autowrap: written in the last two columns", rf"\e[?7l\e[1;11H{wide}", " " * 10 + wide, (11, 0)),
            ("no autowrap: overwritten in the last column", rf"\e[?7l\e[1;11H{wide}Y", " " * 11 + "Y", (11, 0)),
            ("no autowrap: dropped past the last column", rf"\e[?7l\e[1;10H{wide}{wide}", " " * 9 + wide, (11, 0)),
            ("overwriting the first half", rf"{wide}\e[1;1HX", "X", (1, 0)),
            ("overwriting the second half", rf"{wide}\e[1;2HX", " X", (2, 0)),
            ("a wide character over a second half", rf"AB{wide}\e[1;4H{wide}", f"AB {wide}", (5, 0)),
            ("a wide character over two halves", rf"{wide}{wide}\e[1;2H{wide}", f" {wide}", (3, 0)),
            ("ICH in a wide character", rf"{wide}AB\e[1;2H\e[@", "   AB", (1, 0)),
            ("ICH before a wide character", rf"{wide}AB\e[1;1H\e[@", f" {wide}AB", (0, 0)),
            ("ICH pushing a wide character past the edge", rf"{'A' * 10}{wide}\e[1;1H\e[@", " " + "A" * 10, (0, 0)),
            ("DCH of the first half", rf"{wide}AB\e[1;1H\e[P", " AB", (0, 0)),
            ("DCH of the second half", rf"{wide}AB\e[1;2H\e[P", " AB", (1, 0)),
            ("DCH before a wide character", rf"A{wide}B\e[1;1H\e[P", f"{wide}B", (0, 0)),
            ("ECH of the first half", rf"{wide}AB\e[1;1H\e[X", "  AB", (0, 0)),
            ("ECH of the second half", rf"{wide}AB\e[1;2H\e[X", "  AB", (1, 0)),
            ("EL 1 of the first half", rf"{wide}AB\e[1;1H\e[1K", "  AB", (0, 0)),
            ("EL of the second half", rf"{wide}AB\e[1;2H\e[K", "", (1, 0)),
            ("insert mode", rf"ABC\e[1;1H\e[4h{wide}", f"{wide}ABC", (2, 0)),
            ("BS onto the second half", f"{wide}\bX", " X", (2, 0)),
            ("a tab onto the second half", rf"{wide * 3}\e[3g\e[1;4H\eH\e[1;1H" + "\tX", f"{wide} X{wide}", (4, 0)),
            ("DECCRA of a second half", rf"{wide}AB\e[1;2;1;3;1;2;1$v", f"{wide}AB\n A", (4, 0)),
            ("DECERA of a second half", rf"{wide}AB\e[1;2;1;2$z", "  AB", (4, 0)),
            ("DECFRA of a second half", rf"{wide}AB\e[88;1;2;1;2$x", " XAB", (4, 0)),
            ("DECIC in a wide character", rf"{wide}AB\e[1;2H\e['}}", "   AB", (1, 0)),
            ("DECDC in a wide character", rf"{wide}AB\e[1;2H\e['~", " AB", (1, 0)),
            ("DECSED keeps a protected wide character", rf'\e[1"q{wide}\e[0"q\e[?2J', wide, (2, 0)),
            ("an emoji", "\U0001f600X", "\U0001f600X", (3, 0)),
            ("a combining accent", "e\u0301X", "e\u0301X", (2, 0)),
            ("a combining accent at the start of a line, dropped", "\u0301X", "X", (1, 0)),
            ("a combining accent after the last column", "\\e[1;12He\u0301X", " " * 11 + "e\u0301\nX", (1, 1)),
            ("a combining accent on a wide character", f"{wide}\u0301X", f"{wide}\u0301X", (3, 0)),
            ("a combining accent on a blank", "e\\e[C\u0301X", "e \u0301X", (3, 0)),
            ("a zero width joiner", "a\u200dX", "a\u200dX", (2, 0)),
            ("a variation selector", "\u2764\ufe0fX", f"{heart}X", (2, 0)),
            ("a wide character after CR from the last column", f"{'A' * 12}\r{wide}", f"{wide}{'A' * 10}", (2, 0)),
            ("a wide character after BS from the last column", f"{'A' * 12}\b{wide}", f"{'A' * 10}{wide}", (11, 0)),
            (
                "a wide character after DECSTBM homes the cursor",
                rf"{'A' * 12}\e[1;3r{wide}",
                f"{wide}{'A' * 10}",
                (2, 0),
            ),
            ("a combining accent after CR from the last column, dropped", f"{'A' * 12}\r\u0301", "A" * 12, (0, 0)),
            (
                "no autowrap: a combining accent after the last column",
                "\\e[?7l\\e[1;11Hde\u0301",
                " " * 10 + "de\u0301",
                (11, 0),
            ),
            (
                "autowrap set after a write in the last column wraps",
                rf"\e[?7l{'A' * 12}\e[?7hB",
                "A" * 12 + "\nB",
                (1, 1),
            ),
            ("at most two combining accents", "e\u0301\u0302\u0303X", "e\u0301\u0302X", (2, 0)),
            ("a combining accent on a DEC graphics character, dropped", "\\e(0q\u0301\\e(BX", "qX", (2, 0)),
        ):
            with self.subTest(label), set_temporary_encoding("utf-8"):
                self.restart(12, 3)
                self.write(data.encode().decode("iso8859-1"))
                self.assertEqual(self.read(), screen.encode())
                self.assertEqual(self.term.term.term_cursor, cursor)

        with set_temporary_encoding("utf-8"):
            self.restart(12, 3)
            self.write(rf"{wide}\e[1;1;1;1;1;2*y".encode().decode("iso8859-1"))
            self.read()
            self.assertEqual(
                bytes(self.pty.from_widget),
                b"\x1bP1!~FFC5\x1b\\",
                "DECRQCRA counts the first half as 0x1B and the second as a space, as xterm does",
            )

            self.restart(12, 3)
            self.write(rf"\e[11m{wide}".encode().decode("iso8859-1"))
            self.read()
            self.assertEqual(self.term.term.term[0][0][1], "U", "the IBM PC mapping stores a wide character in it")

            self.restart(12, 3)
            self.write(f"{'A' * 10}{wide}".encode().decode("iso8859-1"))
            self.read()
            self.resize(11, 3)
            self.assertEqual(self.read(), b"A" * 10, "a resize cutting a wide character in half leaves no half")

            self.restart(12, 3)
            self.write(rf"{wide}\e[D\e[2 q".encode().decode("iso8859-1"))
            self.term.wait_and_feed()
            first = next(iter(self.term.render(self.termsize, focus=True).content()))[0]
            self.assertEqual(
                first,
                (urwid.AttrSpec("default,standout", "default"), None, wide.encode()),
                "the cursor on the second half is drawn on the first",
            )

    def test_scroll_up_and_down(self) -> None:
        """Scroll the scrolling region with SU and SD, keeping the cursor and the scrollback, as xterm does."""
        for label, data, screen, cursor in (
            ("SU", r"\e[S", "2\n3\n4\n5", (1, 4)),
            ("SU 2", r"\e[2S", "3\n4\n5", (1, 4)),
            ("SU 0 scrolls one line", r"\e[0S", "2\n3\n4\n5", (1, 4)),
            ("SU past the region clears it", r"\e[99S", "", (1, 4)),
            ("SU in the scrolling region", r"\e[2;4r\e[5;2H\e[S", "1\n3\n4\n\n5", (1, 4)),
            ("SD", r"\e[T", "\n1\n2\n3\n4", (1, 4)),
            ("SD 2 in the scrolling region", r"\e[2;4r\e[5;2H\e[2T", "1\n\n\n2\n5", (1, 4)),
            (
                "SD with more parameters is ignored, as xterm's mouse highlight tracking",
                r"\e[2;1T",
                "1\n2\n3\n4\n5",
                (1, 4),
            ),
            ("SU with ? is not SU", r"\e[?1S", "1\n2\n3\n4\n5", (1, 4)),
            ("SD 0 is ignored, as in xterm", r"\e[0T", "1\n2\n3\n4\n5", (1, 4)),
            ("SD with ? is not SD", r"\e[?1T", "1\n2\n3\n4\n5", (1, 4)),
            ("SD as ECMA-48 corrected it", r"\e[2^", "\n\n1\n2\n3", (1, 4)),
            ("SD as ECMA-48 corrected it, 0 scrolling one line, as in xterm", r"\e[0^", "\n1\n2\n3\n4", (1, 4)),
        ):
            with self.subTest(label):
                self.restart(10, 5)
                self.write("1\n2\n3\n4\n5" + data)
                self.expect(screen)
                self.assertEqual(self.term.term.term_cursor, cursor)
                self.assertEqual(len(self.term.term.scrollback_buffer), 0, "the lines scrolled off are not saved")

        self.restart(10, 5)
        self.write(r"\e[5;1H" + "A" * 10 + r"\e[SB")
        # the wrap at the bottom row scrolls once more
        self.expect("\n\n" + "A" * 10 + "\n\nB")
        self.assertEqual(self.term.term.term_cursor, (1, 4), "SU keeps a pending wrap")

    def test_c1_controls_in_utf8_are_dropped(self) -> None:
        """Neither run nor draw a C1 control written in UTF-8, as xterm and kitty do."""
        for label, data in (
            ("NEL", "AB\u0085C"),
            ("IND", "AB\u0084C"),
            ("RI", "AB\u008dC"),
            ("an unassigned one", "AB\u0081C"),
            ("CSI", "AB\u009b2DC"),
            ("OSC", "AB\u009d0;t\u009cC"),
        ):
            with self.subTest(label), set_temporary_encoding("utf-8"):
                self.restart(12, 3)
                self.write(data.encode().decode("iso8859-1"))
                text = data.encode("ascii", "ignore").decode()
                self.assertEqual(self.read(), text.encode())
                self.assertEqual(self.term.term.term_cursor, (len(text), 0))

        with set_temporary_encoding("iso8859-1"):
            # U+009B is byte 0x9B in this encoding, which a display would send to the host terminal as CSI
            self.restart(12, 3)
            self.write("\\e%GAB" + "\u009b2DC".encode().decode("iso8859-1"))
            self.assertEqual(self.read(), b"AB2DC")

        for label, data in (
            ("the IBM PC mapping designated", "\\e(UA\u0085B"),
            ("display control mode", "\\e[3hA\u0085B"),
        ):
            with self.subTest(f"drawn with {label}"), set_temporary_encoding("utf-8"):
                self.restart(12, 3)
                self.write(data.encode().decode("iso8859-1"))
                self.read()
                self.assertEqual(self.term.term.term_cursor, (3, 0))

    def test_column_operations(self) -> None:
        """Insert and delete columns in the scrolling region with DECIC, DECDC, DECBI and DECFI, as xterm does."""
        for label, sequence, rows, cursor in (
            ("DECIC at the cursor column", r"\e[1;3H\e[2'}", ["AB  CDEF"] * 4, (2, 0)),
            ("DECDC at the cursor column", r"\e[2;3H\e[2'~", ["ABEF"] * 4, (2, 1)),
            (
                "DECIC only in the scrolling region",
                r"\e[2;3r\e[2;3H\e['}",
                ["ABCDEF", "AB CDEF", "AB CDEF", "ABCDEF"],
                (2, 1),
            ),
            ("DECIC outside the scrolling region", r"\e[2;3r\e[1;3H\e['}", ["ABCDEF"] * 4, (2, 0)),
            ("DECBI at the left edge", r"\e[2;1H\e6", [" ABCDEF"] * 4, (0, 1)),
            ("DECBI elsewhere moves left", r"\e[2;3H\e6", ["ABCDEF"] * 4, (1, 1)),
            ("DECFI at the right edge", r"\e[2;10H\e9", ["BCDEF"] * 4, (9, 1)),
            ("DECFI elsewhere moves right", r"\e[2;3H\e9", ["ABCDEF"] * 4, (3, 1)),
        ):
            with self.subTest(label):
                self.restart(10, 4)
                self.write("ABCDEF\nABCDEF\nABCDEF\nABCDEF" + sequence)
                self.read()
                self.assertEqual([line.rstrip() for line in self.term.term.text], [row.encode() for row in rows])
                self.assertEqual(self.term.term.term_cursor, cursor)

    def test_soft_reset(self) -> None:
        """Reset the modes, the region, the attributes and the charsets DECSTR resets, keeping the cursor, as xterm."""
        self.write(r"\e[?1h\e[?25l\e[4h\e[?7l\e[2;4r\e[1;31m\e=\e(0\e[3;5H\e7\e[2;2H\e[!p")
        self.read()
        self.assertEqual(self.term.term.term_cursor, (1, 1))
        self.write(rf"\e[?1$p\e[?6$p\e[?7$p\e[?25$p\e[4$p\e[?66$p\eP$qm{_ST}\eP$qr{_ST}")
        self.read()
        self.assertEqual(
            bytes(self.pty.from_widget),
            b"\x1b[?1;2$y\x1b[?6;2$y\x1b[?7;1$y\x1b[?25;1$y\x1b[4;2$y\x1b[?66;2$y\x1bP1$r0m\x1b\\\x1bP1$r1;24r\x1b\\",
        )
        self.pty.from_widget.clear()
        # the cursor DECSC saved before is replaced by the home position with the reset attributes and charsets
        self.write(r"\e[2J\e8q\e[6n")
        self.read()
        self.assertEqual(self.term.term.term[0][0], (None, None, b"q"))
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b[1;2R")

    def test_scrollback(self) -> None:
        """Scroll the view through the scrollback buffer within its bounds."""
        self.resize(10, 3)
        self.write("1\n2\n3\n4\n5")
        self.expect("3\n4\n5")
        self.term.term.scroll_buffer(up=True, lines=2)
        self.expect("1\n2\n3")
        self.term.term.scroll_buffer(up=False, lines=1)
        self.expect("2\n3\n4")
        self.term.term.scroll_buffer(up=True, lines=1000)
        self.assertEqual(self.term.term.scrolling_up, len(self.term.term.scrollback_buffer))
        self.term.term.scroll_buffer(up=False, lines=1000)
        self.assertEqual(self.term.term.scrolling_up, 0)
        self.expect("3\n4\n5")
        self.term.term.scroll_buffer(up=True)
        self.term.term.scroll_buffer(reset=True)
        self.expect("3\n4\n5")
        # lines pushed into the scrollback at the old width are shown at the current one
        for width in (6, 14):
            with self.subTest(width=width):
                self.resize(width, 3)
                self.term.term.scroll_buffer(up=True, lines=2)
                self.assertEqual({len(line) for line in self.term.term.content()}, {width})
                self.term.term.scroll_buffer(reset=True)
        # the padding of those lines does not take the attributes in effect now
        self.write(r"\e[41m")
        self.read()
        self.term.term.scroll_buffer(up=True, lines=2)
        self.assertEqual({cell for line in self.term.term.content() for cell in line[10:]}, {(None, None, b" ")})
        self.term.term.scroll_buffer(reset=True)
        self.resize(14, 5)
        self.assertEqual({cell for line in self.term.term.term[:2] for cell in line[10:]}, {(None, None, b" ")})

    def test_sgr_colors(self) -> None:
        """Set the attributes of 16-colour, 256-colour and true-colour SGR sequences, brightening bold colours.

        A colour value of 0 is not a reset: the other attributes stay.
        """
        self.write(r"\e[1;4;7;31;42ma\e[0mb\e[38;5;100mc\e[0;38;2;1;2;3;48;2;4;5;6md\e[0;1;44m\e[38;5;0me")
        self.expect(
            [
                [
                    (urwid.AttrSpec("light red,bold,underline,standout", "dark green"), None, b"a"),
                    (None, None, b"b"),
                    (urwid.AttrSpec("h100", "default", 256), None, b"c"),
                    (urwid.AttrSpec("#010203", "#040506", 2**24), None, b"d"),
                    (urwid.AttrSpec("h0,bold", "h4", 256), None, b"e"),
                ]
            ],
            raw=True,
        )

    def test_sgr_italics_and_strikethrough(self) -> None:
        self.write(r"\e[3;9ma\e[23mb\e[29mc")
        self.expect(
            [
                [
                    (urwid.AttrSpec("default,italics,strikethrough", "default"), None, b"a"),
                    (urwid.AttrSpec("default,strikethrough", "default"), None, b"b"),
                    (None, None, b"c"),
                ]
            ],
            raw=True,
        )

    def test_csi_with_sub_parameters_or_intermediate_bytes_is_ignored_whole(self) -> None:
        """Ignore a whole CSI sequence with sub-parameters, a private marker or intermediate bytes (ECMA-48 5.4)."""
        self.write(r"\e[38:5:196ma\e[38:2::1:2:3mb\e[4:3mc\e[2 @d\e[>4;1me\e[=5cf\e[1$tg\e[>1ch")
        self.expect("abcdefgh")
        self.assertIsNone(self.term.term.attrspec)
        self.assertEqual(bytes(self.pty.from_widget), b"")

    def test_private_form_of_a_command_without_one_is_ignored(self) -> None:
        """Ignore CSI ? 4 m (XTQMODKEYS), CSI ? s and CSI ? r (XTSAVE, XTRESTORE)."""
        self.write(r"a\e[s\e[2;1Hbc\e[?4md\e[?1se\e[?1r\e[uf")
        self.expect("af\nbcde")
        self.assertIsNone(self.term.term.attrspec)
        self.assertEqual(bytes(self.pty.from_widget), b"")

    def test_cursor_coords_follow_resize(self) -> None:
        """Report the cursor position constrained to the size being rendered."""
        self.write("abc")
        self.read()
        self.assertEqual(self.term.get_cursor_coords((80, 24)), (3, 0))
        self.assertEqual(self.term.get_cursor_coords((2, 24)), (1, 0))
        # a view scrolled back moves the cursor down with its row, and drops it once that row is not shown
        self.restart(10, 3)
        self.write("1\n2\n3\n4\n5\n6\\e[1;2H")
        self.read()
        for lines, coords in ((1, (1, 1)), (2, (1, 2)), (3, None)):
            with self.subTest(lines=lines):
                self.term.term.scroll_buffer(up=True, lines=lines)
                self.assertEqual(self.term.get_cursor_coords(self.termsize), coords)
                self.assertEqual(self.term.render(self.termsize, focus=True).cursor, coords)
                self.term.term.scroll_buffer(reset=True)

    def test_resize_keeps_the_cursor_on_its_line(self) -> None:
        """Keep the cursor and the saved cursor on their line across width changes and scrollback moves both ways."""
        self.write("a\nb\nc\\e[2;2H")
        # two rows: the blank rows below the cursor go first, then "a" moves into the scrollback
        for size, char in (((70, 24), "X"), ((70, 2), "Y"), ((80, 24), "Z")):
            self.read()
            self.resize(*size)
            self.write(char)
        self.expect("a\nbXYZ\nc")
        self.write(r"\e[2;2H\e7")
        self.read()
        self.resize(80, 2)
        self.write(r"\e8W")
        self.expect("bWYZ\nc")
        self.write(r"\e[1;3H\e7")
        self.read()
        self.resize(80, 24)
        self.write(r"\e8V")
        self.expect("a\nbWVZ\nc")
        # shrinking past the cursor's row and growing back leaves the cursor at the end of its line
        self.write("\\echello\nworld")
        for size in ((80, 1), (80, 24)):
            self.read()
            self.resize(*size)
        self.write("!")
        self.expect("hello\nworld!")
        # a view scrolled back past what a resize leaves in the scrollback is moved down, and still renders whole
        self.write("\\ec1\n2\n3\n4\n5")
        self.read()
        self.resize(80, 3)
        self.term.term.scroll_buffer(up=True, lines=2)
        self.resize(80, 5)
        self.assertEqual(self.term.term.scrolling_up, 0)
        self.assertEqual(5, len(list(self.term.render((80, 5)).content())))
        # a view scrolled back keeps its top line while a resize moves lines into the scrollback and back
        self.write("\\ec" + "\n".join(map(str, range(10))))
        self.read()
        self.term.term.scroll_buffer(up=True, lines=3)
        self.expect("2\n3\n4\n5\n6")
        self.resize(80, 3)
        self.expect("2\n3\n4")
        self.resize(80, 5)
        self.expect("2\n3\n4\n5\n6")

    def test_resize_adds_cells_without_attributes(self) -> None:
        """Fill the columns and rows a resize adds with cells that do not take the attributes in effect."""
        self.write(r"\e[41m")
        self.read()
        self.resize(90, 26)
        added = {cell for line in self.term.term.term[:24] for cell in line[80:]}
        added |= {cell for line in self.term.term.term[24:] for cell in line}
        self.assertEqual(added, {(None, None, b" ")})

    def test_resize_sets_the_pty_size_and_emits_resize(self) -> None:
        """Pass each new size to the pty and emit "resize" once per change."""
        on_resize = mock.Mock()
        urwid.connect_signal(self.term, "resize", on_resize)
        with mock.patch("urwid.vterm.fcntl.ioctl", return_value=0) as ioctl:
            for size in ((100, 30), (100, 30), (60, 10)):
                self.resize(*size)
        sizes = [(100, 30), (60, 10)]
        self.assertEqual(on_resize.call_args_list, [mock.call(self.term, size) for size in sizes])
        self.assertEqual(
            ioctl.call_args_list,
            [
                mock.call(_FAKE_MASTER_FD, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
                for width, height in sizes
            ],
        )

    def test_alternate_screen(self) -> None:
        """Show the alternate screen while modes 47, 1047 and 1049 are set, keeping the main screen and its scrollback.

        The alternate screen keeps no scrollback. 1049 saves and restores the cursor, and clears the alternate screen
        on entering it. 1047 clears it on leaving it. 47 keeps it.
        """
        for mode, main, alternate in (
            ("47", "2   Z\n3\n4", "\n Y"),
            ("1047", "2   Z\n3\n4", ""),
            ("1049", "2\n3\n4Z", "\n Y"),
        ):
            with self.subTest(mode=mode):
                self.restart(10, 3)
                self.write("1\n2\n3\n4")
                self.read()
                # the alternate screen is shown from its first line on
                self.term.term.scroll_buffer(up=True)
                self.write(rf"\e[?{mode}hX")
                self.expect("\n\n X")
                self.assertTrue(self.term.term_modes.alternate_screen)
                self.write("\\e[2J\\e[3;2HY\n")
                self.expect("\n Y")
                self.term.term.scroll_buffer(up=True)
                self.expect("\n Y")
                self.write(rf"\e[1;5H\e[?{mode}lZ")
                self.expect(main)
                self.assertFalse(self.term.term_modes.alternate_screen)
                self.assertEqual(len(self.term.term.scrollback_buffer), 1)
                self.term.term.scroll_buffer(up=True)
                self.expect("1\n" + main.rsplit("\n", 1)[0])
                self.term.term.scroll_buffer(reset=True)
                self.write(r"\e[?47h")
                self.expect(alternate)

    def test_new_canvas_starts_on_the_main_screen(self) -> None:
        """Start a canvas on its main screen, with a scrollback, also for modes left on the alternate screen."""
        self.write(r"\e[?1049h")
        self.read()
        canvas = urwid.TermCanvas(10, 3, self.term)
        self.assertFalse(self.term.term_modes.alternate_screen)
        # the alternate screen keeps no scrollback
        self.assertGreater(canvas.scrollback_buffer.maxlen, 0)

    def rendered_standout(self) -> list[list[bool]]:
        """Read the pending output and return, per rendered cell, whether it is shown in standout."""
        self.read()
        rendered = self.term.render(self.termsize)
        return [[attr is not None and attr.standout for attr, _, _ in line] for line in rendered.content()]

    def test_reverse_video_covers_both_screens(self) -> None:
        """Show DECSCNM on whichever screen is switched to."""
        self.write(r"a\e[?47hb\e[?5h\e[?47l")
        self.assertTrue(self.rendered_standout()[0][0])
        self.write(r"\e[?5l\e[?47h")
        self.assertFalse(self.rendered_standout()[0][1])

    def test_reverse_video_is_applied_when_rendered(self) -> None:
        """Show every cell in standout while DECSCNM is on, and keep the stored cells as the child wrote them."""
        self.write(r"a\e[31mb\e[?5h")
        self.assertTrue(all(all(line) for line in self.rendered_standout()))
        self.assertFalse(any(attr is not None and attr.standout for attr, _, _ in self.term.term.term[0]))
        self.write(r"\e[?5l")
        self.read()
        self.assertEqual(list(self.term.render(self.termsize).content()), self.term.term.term)

    def test_reverse_video_shows_the_text_written_after_the_change(self) -> None:
        """Show text written after DECSCNM is set, with no SGR sequence in between, in standout."""
        self.write(r"\e[31ma\e[?5hb")
        self.assertEqual(self.rendered_standout()[0][:2], [True, True])

    def test_reverse_video_off_keeps_the_reverse_attribute(self) -> None:
        """Keep the standout of text written with SGR 7 when DECSCNM is set and reset."""
        self.write(r"\e[7ma\e[mb\e[?5h\e[?5l")
        self.assertEqual(self.rendered_standout()[0][:2], [True, False])

    def test_reverse_video_covers_the_scrollback_view(self) -> None:
        """Show the lines scrolled back into view in standout while DECSCNM is on, and normal once it is off."""
        self.write("\n".join(str(number) for number in range(30)) + r"\e[?5h")
        self.read()
        self.term.term.scroll_buffer(up=True, lines=3)
        self.assertTrue(all(all(line) for line in self.rendered_standout()))
        self.write(r"\e[?5l")
        self.assertFalse(any(any(line) for line in self.rendered_standout()))

    def test_reset_turns_reverse_video_off(self) -> None:
        """Show the screen normally again after ESC c clears DECSCNM."""
        self.write(r"\e[?5h\ectext")
        self.assertFalse(any(any(line) for line in self.rendered_standout()))

    def test_reverse_video_change_touches_no_cell(self) -> None:
        """Change DECSCNM without reversing any attribute, so its cost does not grow with the screen area."""
        self.write("text")
        self.read()
        canvas = self.term.term
        with mock.patch.object(canvas, "reverse_attrspec", wraps=canvas.reverse_attrspec) as reverse_attrspec:
            self.write(r"\e[?5h\e[?5l" * 50)
            self.drain()
        self.assertEqual(reverse_attrspec.call_count, 0)

    def test_alternate_screen_resize(self) -> None:
        """Resize the main screen with the alternate one shown, restoring the cursor saved by 1049 to its line."""
        self.restart(10, 3)
        self.write("1\n2\n3\\e[?1049hA")
        self.read()
        self.resize(12, 2)
        self.expect("\n A")
        self.write(r"\e[?1049lZ")
        self.expect("2\n3Z")
        self.assertEqual({len(line) for line in self.term.term.content()}, {12})
        self.write(r"\e[?1049hB")
        self.read()
        self.resize(10, 3)
        self.write(r"\e[?1049lY")
        self.expect("1\n2\n3ZY")
        # the hidden main screen drops its blank rows below the cursor it was hidden with, as the screen shown does;
        # neither the alternate screen's cursor nor a cursor DECSC saved lower down keeps them
        for enter, leave, screen in ((r"\e[?1049h", r"\e[?1049l", "a\nbX"), (r"\e[?47h", r"\e[?47l", "a\nb\nX")):
            with self.subTest(enter=enter):
                self.restart(4, 5)
                self.write(r"\e[5;1H\e7\e[Ha" + "\nb" + enter + r"\e[5;1H")
                self.read()
                self.resize(4, 3)
                self.write(leave + "X")
                self.expect(screen)

    def test_reset_shows_the_main_screen(self) -> None:
        """Show the main screen on a reset, keeping its scrollback, and clear the alternate screen and the flags."""
        self.restart(10, 3)
        self.write("1\n2\n3\n4\\e[>1u\\e[?1049h\\e[>8ualt\\ec")
        self.expect("")
        self.assertFalse(self.term.term_modes.alternate_screen)
        self.assertEqual(self.term.term_modes.keyboard_flags, [])
        self.assertEqual(len(self.term.term.scrollback_buffer), 1)
        self.write(r"\e[?47h\e[?u")
        self.expect("")
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b[?0u")

    def test_keyboard_flags(self) -> None:
        """Answer the kitty keyboard flags query after pushing, popping and setting the flags, on each screen."""
        # none of these sequences is the restore of the cursor that CSI u is without a private marker
        self.write(r"a\e[s\e[2;1Hb\e[>1u\e[=1u\e[<uc")
        self.expect("a\nbc")
        steps = (
            ("", 0),
            (r"\e[>1u", 1),
            (r"\e[>5u", 5),
            (r"\e[<u", 1),
            (r"\e[=4;2u", 5),
            (r"\e[=1;3u", 4),
            (r"\e[=8u", 8),
            (r"\e[=1;4u", 8),
            (r"\e[>1:2u\e[>1;2:3u", 8),
            (r"\e[<5u", 0),
            (r"\e[=3u", 3),
            (r"\e[<u", 0),
            (r"\e[>255u", 31),
            (r"\e[>u", 0),
            ("".join(rf"\e[>{flags}u" for flags in range(1, 11)) + r"\e[<7u", 3),
            (r"\e[<u", 0),
            (r"\e[>2u\e[?47h", 0),
            (r"\e[>4u", 4),
            (r"\e[?47l", 2),
            (r"\e[?47h", 4),
        )
        for written, flags in steps:
            with self.subTest(written=written):
                self.pty.from_widget.clear()
                self.write(rf"{written}\e[?u")
                self.read()
                self.assertEqual(bytes(self.pty.from_widget), f"\x1b[?{flags}u".encode())

    def test_wait_and_feed_without_output_returns(self) -> None:
        """Return after the timeout without reading when the child wrote nothing."""
        self.term.wait_and_feed(0)
        self.expect("")

    def test_synchronized_output_block_left_open_returns(self) -> None:
        """Return from feed() once the PTY is drained, even inside an unfinished synchronized-output block."""
        self.write(r"\e[?2026hpartial")
        self.expect("partial")
        self.assertTrue(self.term.term_modes.synchronized_output)

    def test_ctrl_keys_send_control_characters(self) -> None:
        r"""Send the C0 control character for ctrl with a letter or one of @[\]^_."""
        for key, sent in (
            ("ctrl b", b"\x02"),
            ("ctrl B", b"\x02"),
            ("ctrl @", b"\x00"),
            ("ctrl [", b"\x1b"),
            ("ctrl _", b"\x1f"),
        ):
            with self.subTest(key=key):
                self.pty.from_widget.clear()
                self.term.keygrab = True
                self.assertIsNone(self.term.keypress(self.termsize, key))
                self.assertEqual(bytes(self.pty.from_widget), sent)

    def test_keypress_before_first_render(self) -> None:
        """Start the child at the keypress size only for a key sent to it before the first render."""
        for key, handled, sent in (
            ("a", None, b"a"),
            ("page up", None, None),
            ("page down", None, None),
            ("up", "up", None),
            ("shift up", "shift up", None),
        ):
            with self.subTest(key=key):
                self.restart(40, 10, soft=True)
                self.assertEqual(self.term.keypress(self.termsize, key), handled)
                if sent is None:
                    self.assertIsNone(self.term.term)
                    self.assertIsNone(self.term.pid)
                else:
                    self.assertEqual((self.term.term.width, self.term.term.height), self.termsize)
                    self.assertEqual(bytes(self.pty.from_widget), sent)

    def test_ctrl_keys_without_control_character_are_not_handled(self) -> None:
        """Return a ctrl key that has no C0 control character unhandled, writing nothing to the child."""
        for key in (
            "ctrl f5",
            "ctrl up",
            "ctrl 5",
            "ctrl \N{LATIN SMALL LETTER LONG S}",
            "ctrl \N{LATIN SMALL LETTER DOTLESS I}",
        ):
            with self.subTest(key=key):
                self.term.keygrab = True
                self.assertEqual(self.term.keypress(self.termsize, key), key)
                self.assertEqual(bytes(self.pty.from_widget), b"")

    def test_backarrow_key_mode(self) -> None:
        """Send BS for Backspace while DECBKM is set, and DEL while it is reset, its default."""
        for mode, key, sent in (
            ("", "backspace", b"\x7f"),
            (r"\e[?67h", "backspace", b"\x08"),
            (r"\e[?67h", "shift backspace", b"\x08"),
            (r"\e[?67h\e[?67l", "backspace", b"\x7f"),
        ):
            with self.subTest(mode=mode, key=key):
                self.restart()
                self.write(mode)
                self.read()
                self.pty.from_widget.clear()
                self.term.keygrab = True
                self.assertIsNone(self.term.keypress(self.termsize, key))
                self.assertEqual(bytes(self.pty.from_widget), sent)

    def test_meta_keys_send_escape_prefix(self) -> None:
        """Send ESC before the key's character for a meta key, which urwid's own input parser reads back as that key."""
        for key, sent in (
            ("meta x", b"\x1bx"),
            ("meta X", b"\x1bX"),
            ("meta ctrl x", b"\x1b\x18"),
            ("meta enter", b"\x1b\r"),
            ("meta backspace", b"\x1b\x7f"),
            ("meta tab", b"\x1b\t"),
        ):
            with self.subTest(key=key):
                self.pty.from_widget.clear()
                self.term.keygrab = True
                self.assertIsNone(self.term.keypress(self.termsize, key))
                self.assertEqual(bytes(self.pty.from_widget), sent)
                self.assertEqual(urwid.display.escape.process_keyqueue(list(sent), more_available=False), ([key], []))

    def test_keyboard_protocol_keys_are_sent_as_a_legacy_terminal_sends_them(self) -> None:
        """Send a key only the keyboard protocols report apart as the legacy key it collapses to."""
        for key, sent in (
            ("ctrl enter", b"\r"),
            ("shift enter", b"\r"),
            ("shift ctrl enter", b"\r"),
            ("meta ctrl enter", b"\x1b\r"),
            ("ctrl tab", b"\t"),
            ("shift ctrl tab", b"\x1b\t"),
            ("shift backspace", b"\x7f"),
            ("ctrl backspace", b"\x08"),
            ("ctrl esc", b"\x1b"),
            ("ctrl  ", b"\x00"),
            ("ctrl /", b"\x1f"),
            ("ctrl ?", b"\x7f"),
            ("ctrl ~", b"\x1e"),
            ("shift ctrl /", b"\x1f"),
        ):
            with self.subTest(key=key):
                self.pty.from_widget.clear()
                self.term.keygrab = True
                self.assertIsNone(self.term.keypress(self.termsize, key))
                self.assertEqual(bytes(self.pty.from_widget), sent)

    def test_meta_enter_in_lf_nl_mode(self) -> None:
        """Send ESC CR LF for meta enter while LF/NL mode is set, as for enter."""
        self.write(r"\e[20h")
        self.drain()
        self.assertTrue(self.term.term_modes.lfnl)
        self.term.keygrab = True
        self.assertIsNone(self.term.keypress(self.termsize, "meta enter"))
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b\r\n")

    def test_meta_keys_without_single_character_are_not_handled(self) -> None:
        """Return a meta key sent as an escape sequence, or without a control character, unhandled."""
        for key in ("meta up", "meta f5", "meta ctrl up", "meta ctrl 5", "meta shift tab"):
            with self.subTest(key=key):
                self.term.keygrab = True
                self.assertEqual(self.term.keypress(self.termsize, key), key)
                self.assertEqual(bytes(self.pty.from_widget), b"")

    def test_shift_tab_sends_linux_back_tab(self) -> None:
        """Send shift tab as ESC TAB, the back-tab key of the linux terminal type the child is given."""
        self.term.keygrab = True
        self.assertIsNone(self.term.keypress(self.termsize, "shift tab"))
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b\t")

    def test_key_names_without_byte_form_are_not_handled(self) -> None:
        """Return a key name the linux terminal type has no byte form for unhandled instead of writing it as text."""
        for key in (
            "shift up",
            "shift f1",
            "shift meta ctrl f12",
            "meta shift up",
            "f21",
            "focus in",
            "<130>",
            "super enter",
            "super a",
            "super \u0436",
            "hyper \u00e9",
        ):
            with self.subTest(key=key):
                self.term.keygrab = True
                self.assertEqual(self.term.keypress(self.termsize, key), key)
                self.assertEqual(bytes(self.pty.from_widget), b"")

    def test_unhandled_key_keeps_the_key_grab_state(self) -> None:
        """A key the child has no byte form for neither starts nor ends a key grab."""
        for grabbed in (False, True):
            for key in ("focus in", "ctrl up", "meta up"):
                with self.subTest(grabbed=grabbed, key=key):
                    self.term.keygrab = grabbed
                    self.assertEqual(self.term.keypress(self.termsize, key), key)
                    self.assertEqual(self.term.keygrab, grabbed)

    def test_unhandled_key_keeps_the_scrollback_view(self) -> None:
        """A key the child has no byte form for leaves the view where it was scrolled to."""
        self.resize(10, 3)
        self.write("1\n2\n3\n4\n5")
        self.drain()
        self.term.term.scroll_buffer(up=True, lines=2)
        self.term.keygrab = True
        self.assertEqual(self.term.keypress(self.termsize, "shift up"), "shift up")
        self.assertEqual(self.term.term.scrolling_up, 2)

    def test_output_while_scrolled_back(self) -> None:
        """Return the view to the bottom on output, or keep it on the lines being read with scroll_on_output off."""
        for scroll_on_output, view in ((True, "6\n7\n8"), (False, "1\n2\n3")):
            with self.subTest(scroll_on_output=scroll_on_output):
                self.restart(10, 3, scroll_on_output=scroll_on_output)
                self.write("1\n2\n3\n4\n5")
                self.drain()
                self.term.term.scroll_buffer(up=True, lines=2)
                self.write("\n6\n7\n8")
                self.expect(view)

    def test_function_keys_above_f12_send_linux_sequences(self) -> None:
        """Send F13-F20 as the linux terminal type defines them, which urwid's own input parser reads back."""
        for sent in (
            b"\x1b[25~",
            b"\x1b[26~",
            b"\x1b[28~",
            b"\x1b[29~",
            b"\x1b[31~",
            b"\x1b[32~",
            b"\x1b[33~",
            b"\x1b[34~",
        ):
            with self.subTest(sent=sent):
                self.pty.from_widget.clear()
                keys, rest = urwid.display.escape.process_keyqueue(list(sent), more_available=False)
                self.assertEqual(rest, [])
                self.term.keygrab = True
                self.assertIsNone(self.term.keypress(self.termsize, keys[0]))
                self.assertEqual(bytes(self.pty.from_widget), sent)

    def test_keys_in_the_kitty_keyboard_protocol(self) -> None:
        """Send keys as the kitty keyboard protocol reports them under the flags the child set.

        urwid's own input parser reads each report back as the same key.
        """
        for flags, key, sent in (
            # disambiguate escape codes
            (1, "a", b"a"),
            (1, "A", b"A"),
            (1, "ctrl b", b"\x1b[98;5u"),
            (1, "ctrl A", b"\x1b[97;6u"),
            (1, "ctrl c", b"\x1b[99;5u"),
            (1, "meta a", b"\x1b[97;3u"),
            (1, "meta ctrl super hyper x", b"\x1b[120;31u"),
            (1, "ctrl  ", b"\x1b[32;5u"),
            (1, "shift 1", b"\x1b[49;2u"),
            (1, "ctrl 5", b"\x1b[53;5u"),
            (1, "ctrl \u0436", b"\x1b[1078;5u"),
            (1, "ctrl \u0416", b"\x1b[1078;6u"),
            (1, "esc", b"\x1b[27u"),
            (1, "enter", b"\r"),
            (1, "tab", b"\t"),
            (1, "backspace", b"\x7f"),
            (1, "shift enter", b"\x1b[13;2u"),
            (1, "shift tab", b"\x1b[9;2u"),
            (1, "ctrl backspace", b"\x1b[127;5u"),
            (1, "up", b"\x1b[A"),
            (1, "ctrl up", b"\x1b[1;5A"),
            (1, "f1", b"\x1b[P"),
            (1, "shift f4", b"\x1b[1;2S"),
            (1, "f3", b"\x1b[13~"),
            (1, "shift f3", b"\x1b[13;2~"),
            (1, "page up", b"\x1b[5~"),
            (1, "f12", b"\x1b[24~"),
            (1, "f13", b"\x1b[57376u"),
            (1, "media play", b"\x1b[57428u"),
            (1, "left shift", None),
            (1, "caps lock", None),
            (1, "focus in", None),
            (1, "<130>", None),
            # event types are accepted, and only presses are reported
            (3, "ctrl b", b"\x1b[98;5u"),
            # report alternate keys
            (5, "ctrl A", b"\x1b[97:65;6u"),
            (5, "meta A", b"\x1b[97:65;4u"),
            (5, "ctrl b", b"\x1b[98;5u"),
            (5, "A", b"A"),
            # report all keys as escape codes
            (8, "a", b"\x1b[97u"),
            (8, "A", b"\x1b[97;2u"),
            (8, "1", b"\x1b[49u"),
            (8, "enter", b"\x1b[13u"),
            (8, "left shift", b"\x1b[57441u"),
            (8, "shift caps lock", b"\x1b[57358;2u"),
            # and associated text
            (28, "a", b"\x1b[97;;97u"),
            (28, "A", b"\x1b[97:65;2;65u"),
            (28, "ctrl b", b"\x1b[98;5u"),
            # event types or alternate keys alone change no key press
            (2, "ctrl b", b"\x02"),
            (4, "f1", b"\x1b[[A"),
            (20, "meta a", b"\x1ba"),
        ):
            with self.subTest(flags=flags, key=key):
                self.restart()
                self.write(rf"\e[={flags}u")
                self.read()
                self.term.keygrab = True
                self.assertEqual(self.term.keypress(self.termsize, key), None if sent else key)
                self.assertEqual(bytes(self.pty.from_widget), sent or b"")
                if sent is not None:
                    keys, rest = urwid.display.escape.process_keyqueue(
                        list(sent), more_available=False, keyboard_protocol="kitty"
                    )
                    self.assertEqual((keys, rest), ([key], []))

    def test_kitty_keyboard_protocol_keeps_cursor_key_and_lf_nl_modes_apart(self) -> None:
        """Send the cursor keys in their CSI form also in cursor key mode, and enter as CR LF in LF/NL mode."""
        self.write(r"\e[?1h\e[20h\e[=1u")
        self.read()
        self.term.keygrab = True
        for key in ("up", "enter"):
            self.term.keypress(self.termsize, key)
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b[A\r\n")

    def test_pasted_text_is_sent_as_text_under_the_kitty_keyboard_protocol(self) -> None:
        """Send the keys between "begin paste" and "end paste" as typed, also when all keys are escape codes."""
        self.write(r"\e[?2004h\e[=8u")
        self.read()
        self.term.keygrab = True
        for key in ("begin paste", "a", "enter", "end paste", "a"):
            self.term.keypress(self.termsize, key)
        self.assertEqual(bytes(self.pty.from_widget), b"\x1b[200~a\r\x1b[201~\x1b[97u")

    def mouse(self, *events: tuple[str, int, int, int]) -> tuple[list[bool | None], bytes]:
        """Send mouse *events* as ``(event, button, col, row)``, and return what each returned and what the child got."""
        self.pty.from_widget.clear()
        handled = [self.term.mouse_event(self.termsize, *event, focus=True) for event in events]
        return handled, bytes(self.pty.from_widget)

    def test_mouse_events_reported_as_xterm_does(self) -> None:
        """Report mouse events to a child that tracks the mouse, in its tracking mode and encoding."""
        for modes, events, sent in (
            ("1000", [("mouse press", 1, 4, 2), ("mouse release", 0, 4, 2)], b"\x1b[M %#\x1b[M#%#"),
            (
                "1000",
                [
                    ("mouse press", 1, 0, 0),
                    ("mouse press", 3, 0, 0),
                    ("mouse release", 0, 0, 0),
                    ("mouse release", 0, 0, 0),
                ],
                b'\x1b[M !!\x1b[M"!!\x1b[M#!!\x1b[M#!!',
            ),
            ("1000", [("mouse press", 1, 0, 0), ("shift mouse release", 0, 0, 0)], b"\x1b[M !!\x1b[M'!!"),
            ("1000", [("shift ctrl mouse press", 3, 0, 0)], b"\x1b[M6!!"),
            ("1002", [("mouse drag", 0, 0, 0)], b""),
            (
                "1002",
                [("mouse press", 1, 0, 0), ("mouse press", 4, 0, 0), ("mouse drag", 0, 1, 0)],
                b'\x1b[M !!\x1b[M`!!\x1b[M@"!',
            ),
            (
                "1000;1006",
                [("mouse press", 1, 0, 0), ("mouse release", 0, 0, 0), ("mouse release", 0, 0, 0)],
                b"\x1b[<0;1;1M\x1b[<0;1;1m",
            ),
            ("1000;1006", [("mouse press", 9, 0, 0), ("mouse release", 9, 0, 0)], b"\x1b[<129;1;1M\x1b[<129;1;1m"),
            ("1000", [("meta mouse press", 8, 0, 0)], b"\x1b[M\xa8!!"),
            ("1000", [("mouse press", 5, 0, 0), ("mouse release", 5, 0, 0)], b"\x1b[Ma!!"),
            ("1000", [("mouse press", 1, 0, 0), ("mouse drag", 1, 1, 0)], b"\x1b[M !!"),
            ("1002", [("mouse press", 1, 0, 0), ("mouse drag", 1, 1, 0)], b'\x1b[M !!\x1b[M@"!'),
            ("1003", [("mouse press", 2, 0, 0), ("mouse drag", 0, 1, 0)], b'\x1b[M!!!\x1b[MA"!'),
            ("1000", [("mouse press", 1, 222, 300)], b"\x1b[M \xff\x00"),
            ("1000;1005", [("mouse press", 1, 94, 300)], b"\x1b[M \x7f\xc5\x8d"),
            ("1000;1005", [("mouse press", 1, 3000, 0)], b"\x1b[M \x00!"),
            ("1000;1006", [("mouse press", 2, 4, 2), ("mouse release", 2, 4, 2)], b"\x1b[<1;5;3M\x1b[<1;5;3m"),
            ("1000;1006", [("mouse press", 3, 4, 2), ("mouse release", 0, 4, 2)], b"\x1b[<2;5;3M\x1b[<2;5;3m"),
            ("1000;1006", [("mouse release", 0, 0, 0)], b""),
            ("1000;1006", [("mouse press", 4, 300, 0)], b"\x1b[<64;301;1M"),
            ("1002;1006", [("ctrl mouse drag", 1, 0, 0)], b"\x1b[<48;1;1M"),
            ("1000;1005;1006", [("mouse press", 1, 0, 0)], b"\x1b[<0;1;1M"),
            ("9", [("shift ctrl mouse press", 1, 4, 2)], b"\x1b[M %#"),
            (
                "9",
                [
                    ("mouse press", 3, 0, 0),
                    ("mouse drag", 3, 1, 0),
                    ("mouse release", 0, 1, 0),
                    ("mouse press", 4, 0, 0),
                ],
                b'\x1b[M"!!',
            ),
            ("9;1006", [("meta mouse press", 2, 4, 2), ("mouse release", 2, 4, 2)], b"\x1b[<1;5;3M"),
        ):
            with self.subTest(modes=modes, events=events):
                self.restart()
                self.write(f"\\e[?{modes}h")
                self.drain()
                self.assertEqual(self.mouse(*events), ([True] * len(events), sent))

    def test_mouse_reports_read_back_as_the_same_event(self) -> None:
        """Encode a mouse event so that urwid's own input parser reads the event back."""
        for modes in ("1002", "1002;1006"):
            for event in (
                ("mouse press", 1, 4, 2),
                ("shift meta ctrl mouse press", 3, 0, 0),
                ("mouse press", 7, 0, 0),
                ("mouse press", 11, 0, 0),
                ("mouse drag", 2, 9, 9),
            ):
                with self.subTest(modes=modes, event=event):
                    self.restart()
                    self.write(f"\\e[?{modes}h")
                    self.drain()
                    _, sent = self.mouse(event)
                    keys, rest = urwid.display.escape.process_keyqueue(list(sent), more_available=False)
                    self.assertEqual((keys, rest), ([event], []))

    def test_mouse_events_not_handled(self) -> None:
        """Leave a mouse event to the parent when the child does not track the mouse or cannot receive it."""
        self.assertEqual(self.mouse(("mouse press", 1, 0, 0)), ([False], b""))

        self.write("\\e[?1000h")
        self.drain()
        for event in ("double mouse click", "mouse click"):
            with self.subTest(event=event):
                self.assertEqual(self.mouse((event, 1, 0, 0)), ([False], b""))

        # highlight tracking is not implemented, so its press would wait for a CSI T answer that never comes
        self.write("\\e[?1001h")
        self.drain()
        self.assertEqual(self.mouse(("mouse press", 1, 0, 0)), ([False], b""))
        self.write("\\e[?1000h")
        self.drain()

        self.resize(10, 3)
        self.write("1\n2\n3\n4\n5")
        self.drain()
        self.term.term.scroll_buffer(up=True, lines=1)
        self.assertEqual(self.mouse(("mouse press", 1, 0, 0)), ([False], b""))

        self.term.term.scroll_buffer(reset=True)
        self.term.terminate()
        self.assertEqual(self.mouse(("mouse press", 1, 0, 0)), ([False], b""))

    def test_mouse_modes_set_and_reset(self) -> None:
        """Track the mouse modes as xterm does: one tracking mode and one encoding at a time."""
        mode = urwid.display.escape.PrivateMode
        for sequence, tracking, encoding in (
            ("\\e[?1000h\\e[?1003h", mode.MOUSE_ANY_EVENT_TRACKING, None),
            ("\\e[?1003h\\e[?1000l", None, None),
            ("\\e[?1006h\\e[?1005h", None, mode.MOUSE_UTF8_MODE),
            ("\\e[?1006h\\e[?1005l", None, mode.MOUSE_SGR_MODE),
            ("\\e[?1006h\\e[?1006l", None, None),
            ("\\e[?1002;1006h\\ec", None, None),
            ("\\e[?1000h\\e[?1001h", mode.MOUSE_HIGHLIGHT_TRACKING, None),
            ("\\e[?1003h\\e[?1001l", None, None),
            ("\\e[?1006h\\e[?1015h", None, mode.MOUSE_SGR_MODE),
            ("\\e[?1015h", None, None),
            ("\\e[?9h", mode.MOUSE_X10, None),
            ("\\e[?9h\\e[?9l", None, None),
            ("\\e[?1000h\\e[?9h", mode.MOUSE_REPORTING, None),
            ("\\e[?1003h\\e[?9h\\e[?9l", mode.MOUSE_ANY_EVENT_TRACKING, None),
            ("\\e[?9h\\e[?1002h", mode.MOUSE_BUTTON_TRACKING, None),
            ("\\e[?9h\\e[?1000l", None, None),
            ("\\e[?1002;1006h\\e[?12;1036;1039h", mode.MOUSE_BUTTON_TRACKING, mode.MOUSE_SGR_MODE),
        ):
            with self.subTest(sequence=sequence):
                self.restart()
                self.write(sequence)
                self.drain()
                modes = self.term.term_modes
                self.assertEqual((modes.mouse_tracking, modes.mouse_encoding), (tracking, encoding))

    def test_focus_restores_tty_signal_keys(self) -> None:
        """Restore the tty signal keys seen before the first focused render, on unfocus and on terminate."""
        original = self.tty.signal_keys
        self.read(focus=True)
        self.read(focus=True)
        self.assertEqual(self.tty.signal_keys, (0, 0, 0, 0, 0))
        self.read(focus=False)
        self.assertEqual(self.tty.signal_keys, original)
        self.read(focus=True)
        self.term.terminate()
        self.assertEqual(self.tty.signal_keys, original)

    def test_terminate_reaps_the_child(self) -> None:
        """Send the next signal only while the child runs, and never wait for it without a timeout.

        A child that may not be signalled gets only the hangup from closing the master.
        """
        for label, child, sent, reaped in (
            (
                "child exiting on SIGTERM",
                {"exit_signal": signal.SIGTERM},
                [signal.SIGHUP, signal.SIGCONT, signal.SIGINT, signal.SIGTERM],
                True,
            ),
            ("child reaped by someone else already", {"reaped": True}, [], True),
            ("child reaped as soon as it exits", {"reaped_on_exit": True}, [signal.SIGHUP], True),
            ("setuid child exiting on the hangup", {"signals_allowed": False}, [], True),
            (
                "setuid child ignoring the hangup",
                {"signals_allowed": False, "exit_signal": signal.SIGTERM},
                [],
                False,
            ),
        ):
            with self.subTest(label):
                self.restart()
                for name, value in child.items():
                    setattr(self.pty, name, value)
                with (
                    mock.patch("urwid.vterm.time.monotonic", side_effect=itertools.count(step=0.05)),
                    mock.patch("urwid.vterm.time.sleep"),
                ):
                    self.term.terminate()
                self.assertEqual(self.pty.signals_sent, sent)
                self.assertEqual(self.pty.reaped, reaped)
                self.assertTrue(self.pty.closed)

    def test_terminate_removes_the_watch_by_its_handle(self) -> None:
        """Remove the pty watch by the handle watch_file() returned, once.

        On tornado and trio that handle is not the descriptor.
        """
        loop = mock.create_autospec(urwid.EventLoop, instance=True)
        loop.watch_file.return_value = handle = object()
        term = urwid.Terminal(["/bin/false"], main_loop=loop)
        term.render(self.termsize)
        loop.watch_file.assert_called_once_with(_FAKE_MASTER_FD, term.feed)
        term.terminate()
        term.remove_watch()
        loop.remove_watch_file.assert_called_once_with(handle)
        self.assertTrue(self.pty.closed)

    def _default_terminal(self) -> urwid.Terminal:
        """Return a terminal built without ``main_loop=``, terminated at the end of the test."""
        term = urwid.Terminal(["/bin/false"])
        self.addCleanup(term.terminate)
        return term

    def _loop_on(self, widget: urwid.Widget | None = None) -> tuple[urwid.MainLoop, mock.Mock]:
        """Return a main loop over a mock screen and a mock event loop, with that event loop.

        The main loop's own watch, for :meth:`~urwid.MainLoop.call_from_thread`, gets a handle of its own,
        so :meth:`_pty_watches` and :meth:`_pty_removals` can leave it out.
        """
        event_loop = mock.create_autospec(urwid.EventLoop, instance=True)
        event_loop.watch_file.side_effect = lambda fd, _callback: mock.DEFAULT if fd == _FAKE_MASTER_FD else object()
        return external_loop(widget, event_loop), event_loop

    @staticmethod
    def _pty_watches(event_loop: mock.Mock) -> list[mock._Call]:
        """Return the calls of :meth:`_loop_on`'s *event_loop* that watched the pty."""
        return [call for call in event_loop.watch_file.call_args_list if call.args[0] == _FAKE_MASTER_FD]

    @staticmethod
    def _pty_removals(event_loop: mock.Mock) -> list[mock._Call]:
        """Return the calls of :meth:`_loop_on`'s *event_loop* that removed a watch of the pty."""
        handle = event_loop.watch_file.return_value
        return [call for call in event_loop.remove_watch_file.call_args_list if call.args[0] is handle]

    def test_default_reads_the_pty_on_render_while_no_loop_runs(self) -> None:
        """Without ``main_loop=`` and with no loop running, each render shows the child's output."""
        term = self._default_terminal()
        lines = []
        for chunk in (b"one", b" two"):
            self.pty.to_widget.extend(chunk)
            lines.append(term.render(self.termsize).text[0].rstrip())

        self.assertEqual([b"one", b"one two"], lines)
        self.assertIsNone(term.main_loop)
        self.assertIsNone(term._watch_loop)
        typing.cast("mock.Mock", urwid.vterm.fcntl.fcntl).assert_not_called()

    def test_default_watches_on_the_running_loop(self) -> None:
        """Without ``main_loop=``, a render under a started loop watches the pty there, until terminate()."""
        term = self._default_terminal()
        loop, event_loop = self._loop_on()
        event_loop.watch_file.return_value = handle = object()
        with loop.start():
            term.render(self.termsize)
            fd, callback = event_loop.watch_file.call_args.args
            self.pty.to_widget.extend(b"x")
            callback()
            term.terminate()

        self.assertEqual(_FAKE_MASTER_FD, fd)
        self.assertEqual(b"x", term.term.text[0].rstrip())
        self.assertEqual([mock.call(handle)], self._pty_removals(event_loop))

    def test_default_follows_the_loop_it_is_rendered_under(self) -> None:
        """Without ``main_loop=``, the watch moves to each loop rendered under, and is dropped outside them."""
        term = self._default_terminal()
        loop_a, event_loop_a = self._loop_on()
        loop_b, event_loop_b = self._loop_on()
        event_loop_a.watch_file.return_value = handle_a = object()

        term.render(self.termsize)
        event_loop_a.watch_file.assert_not_called()
        with loop_a.start():
            term.render(self.termsize)
        self.assertEqual(1, len(self._pty_watches(event_loop_a)))
        self.pty.to_widget.extend(b"read")
        self.assertEqual(b"read", term.render(self.termsize).text[0].rstrip())
        self.assertEqual([mock.call(handle_a)], self._pty_removals(event_loop_a))
        with loop_b.start():
            term.render(self.termsize)
        self.assertEqual(1, len(self._pty_watches(event_loop_b)))
        self.assertEqual(1, len(self._pty_watches(event_loop_a)))

    def test_default_watches_again_on_each_start_of_one_loop(self) -> None:
        """A loop started a second time gets a new watch, and the one of its first start is removed."""
        term = self._default_terminal()
        loop, event_loop = self._loop_on()
        for _ in range(2):
            with loop.start():
                term.render(self.termsize)
                term.render(self.termsize)

        self.assertEqual(2, len(self._pty_watches(event_loop)))
        self.assertEqual(1, len(self._pty_removals(event_loop)))

    def test_explicit_main_loop_never_moves_the_watch(self) -> None:
        """With ``main_loop=``, the watch set at the spawn stays there, whichever loop the terminal is rendered under."""
        explicit = mock.create_autospec(urwid.EventLoop, instance=True)
        term = urwid.Terminal(["/bin/false"], main_loop=explicit)
        self.addCleanup(term.terminate)
        loop_a, event_loop_a = self._loop_on()

        term.render(self.termsize)
        with loop_a.start():
            term.render(self.termsize)
        term.render(self.termsize)

        explicit.watch_file.assert_called_once_with(_FAKE_MASTER_FD, term.feed)
        explicit.remove_watch_file.assert_not_called()
        self.assertEqual([], self._pty_watches(event_loop_a))

    def test_draw_by_hand_before_start_reads_the_pty(self) -> None:
        """Draws of a loop that is not started read the pty on each render; starting it sets the watch once."""
        term = self._default_terminal()
        loop, event_loop = self._loop_on(term)
        for chunk in (b"a", b"b", b"c"):
            self.pty.to_widget.extend(chunk)
            loop.draw_screen()
            self.assertEqual(b"", bytes(self.pty.to_widget))
        event_loop.watch_file.assert_not_called()

        with loop.start():
            loop.draw_screen()
            loop.draw_screen()
        self.assertEqual(1, len(self._pty_watches(event_loop)))

    def test_explicit_main_loop_watches_from_a_key_before_any_render(self) -> None:
        """With ``main_loop=``, a key pressed before the first render spawns the child and sets the watch once."""
        explicit = mock.create_autospec(urwid.EventLoop, instance=True)
        term = urwid.Terminal(["/bin/false"], main_loop=explicit)
        self.addCleanup(term.terminate)

        term.keypress(self.termsize, "x")
        explicit.watch_file.assert_called_once_with(_FAKE_MASTER_FD, term.feed)
        term.render(self.termsize)
        explicit.watch_file.assert_called_once()

    def test_terminate_before_spawn(self) -> None:
        """Mark a terminal that never spawned its child as terminated without touching any process."""
        term = urwid.Terminal(["/bin/false"])
        term.terminate()
        self.assertTrue(term.terminated)
        self.assertEqual(self.pty.signals_sent, [])

    @unittest.skipUnless(IS_CPYTHON, "relies on reference counting to free the terminal at once")
    def test_terminated_terminal_is_freed(self) -> None:
        """Drop the at-exit hook on terminate, so it no longer keeps the terminal alive."""
        term = urwid.Terminal(["/bin/false"])
        term.render(self.termsize)
        self.assertIn(term.terminate, self.atexit.hooks)
        term.terminate()
        ref = weakref.ref(term)
        del term
        gc.collect()
        self.assertIsNone(ref())

    def test_failed_exec_exits_the_child(self) -> None:
        """Exit the forked child with status 127 when the command cannot be run, instead of returning to the caller."""
        term = urwid.Terminal(["/nonexistent"])
        with (
            mock.patch("urwid.vterm.pty.fork", return_value=(0, _FAKE_MASTER_FD)),
            mock.patch("urwid.vterm.os.execvpe", side_effect=FileNotFoundError(errno.ENOENT, "No such file")),
            mock.patch("urwid.vterm.os._exit", side_effect=_ChildExit) as exit_,
            mock.patch("urwid.vterm.os.write") as write,
            self.assertRaises(_ChildExit),
        ):
            term.spawn()
        exit_.assert_called_once_with(127)
        write.assert_called_once_with(2, b"/nonexistent: No such file\r\n")


@unittest.skipIf(IS_WINDOWS, "Terminal is not supported under windows")
class TermWindowSizeTest(unittest.TestCase):
    """Check the size on a real pty pair, with no child process started."""

    def test_child_side_reads_the_rendered_size(self) -> None:
        """Report each rendered size on the child's side of the pty.

        A child process reads the size there after the kernel sends it SIGWINCH.
        """
        master, child_side = pty.openpty()
        self.addCleanup(os.close, child_side)
        self.addCleanup(os.close, master)
        term = urwid.Terminal(["/bin/false"])
        term.master = master
        with (
            mock.patch.object(term, "spawn"),
            mock.patch("urwid.vterm.os.kill", side_effect=_forbidden("os.kill")),
            mock.patch("urwid.vterm.os.killpg", side_effect=_forbidden("os.killpg")),
        ):
            for width, height in ((80, 24), (132, 43)):
                term.render((width, height))
                rows, cols, _xpixel, _ypixel = struct.unpack(
                    "HHHH",
                    fcntl.ioctl(child_side, termios.TIOCGWINSZ, bytes(8)),
                )
                self.assertEqual((cols, rows), (width, height))


@unittest.skipIf(IS_WINDOWS, "Terminal is not supported under windows")
class TermScreenEventLoopTest(unittest.TestCase):
    """A terminal on the loop of a screen without event loop support, reading a real pipe."""

    def test_pty_is_watched_by_the_screen_driven_loop(self) -> None:
        """Child output reaches the canvas through the watch, and render() does not read the pty meanwhile."""
        with pipe_terminal() as (term, child_out):

            def check(loop: urwid.MainLoop, attempt: int) -> None:
                if b"hi" in term.term.text[0] or attempt > 100:
                    raise urwid.ExitMainLoop
                loop.set_alarm_in(0.02, check, attempt + 1)

            loop = urwid.MainLoop(term, screen=NonExternalLoopScreen((20, 3)), handle_mouse=False)
            loop.set_alarm_in(0, lambda *_args: os.write(child_out, b"hi"))
            loop.set_alarm_in(0, check, 0)
            with mock.patch.object(term, "wait_and_feed", wraps=term.wait_and_feed) as wait_and_feed:
                loop.run()

        self.assertEqual(b"hi", term.term.text[0].rstrip())
        wait_and_feed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
