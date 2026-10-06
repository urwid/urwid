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
import gc
import itertools
import os
import selectors
import signal
import sys
import typing
import unittest
import weakref
from itertools import dropwhile
from unittest import mock

import urwid
import urwid.ansi_parser
import urwid.vterm
from urwid.util import set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Callable

IS_WINDOWS = sys.platform == "win32"
IS_GRAALPY = sys.implementation.name == "graalpy"
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


class _FakePTY:
    """In-memory replacement for the spawned subprocess + PTY pair, standing in for the ``os`` calls on both.

    ``to_widget`` is the byte stream the widget will read via ``os.read``
    - i.e. what a real subprocess would have written to its stdout.
    ``from_widget`` captures everything the widget writes to the PTY master.
    The child exits on ``exit_signal`` or ``SIGKILL`` and stays a zombie until ``os.waitpid`` reaps it.
    Closing the master hangs the child up, which counts as ``SIGHUP`` even when ``signals_allowed`` is off,
    as for a setuid child.
    With ``reaped_on_exit`` the child is reaped as soon as it exits, as when ``SIGCHLD`` is ignored.
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

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def register(self, fd: int, events: int) -> None:
        """Accept the fake master fd only."""
        if fd != _FAKE_MASTER_FD:
            msg = f"selector registration of fd {fd} outside the fake PTY"
            raise AssertionError(msg)

    def select(self, timeout: float | None = None) -> list[tuple[None, int]]:
        """Report the master readable when a read would not block, without waiting."""
        return [(None, selectors.EVENT_READ)] if self.pty_state.is_readable() else []


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
@unittest.skipIf(IS_GRAALPY, "Terminal is not supported under GraalPy")
class TermTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pty = _FakePTY()
        self.tty = _FakeTTY()
        self.atexit = _FakeAtexit()
        self._install_patches()

        # The command is never actually executed:
        # pty.fork is mocked to take the parent branch and os.execvpe is a no-op for safety.
        self.term = urwid.Terminal(["/bin/false"])
        self.resize(80, 24)

    def restart(self, width: int = 80, height: int = 24) -> None:
        """Replace the terminal under test with a fresh one on a fresh fake PTY, for one case of a table test."""
        self.term.terminate()
        self.pty.reset()
        self.term = urwid.Terminal(["/bin/false"])
        self.resize(width, height)

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
        for y in range(23, 1, -1):
            self.resize(80, y, soft=True)
            self.write(r"\e[%df\e[J3-\e[%d;%df-4" % (y, y, 79))
            desc = "try to rescale to 80x%d." % y
            self.expect("\n" * (y - 2) + "3-" + " " * 76 + "-4", desc)
        self.resize(80, 24, soft=True)
        self.flush()
        self.expect("1-" + " " * 76 + "-2" + "\n" * 22 + "3-" + " " * 76 + "-4")

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

    def test_cursor_visibility(self):
        self.write(r"\e[?25linvisible")
        self.expect("invisible", focus=True)
        self.assertEqual(self.term.term.cursor, None)
        self.write("\rvisible\\e[?25h\\e[K")
        self.expect("visible", focus=True)
        self.assertNotEqual(self.term.term.cursor, None)

    def test_get_utf8_len(self):
        length = self.term.term.get_utf8_len(int("11110000", 2))
        self.assertEqual(length, 3)
        length = self.term.term.get_utf8_len(int("11000000", 2))
        self.assertEqual(length, 1)
        length = self.term.term.get_utf8_len(int("11111101", 2))
        self.assertEqual(length, 5)

    def test_encoding_unicode(self):
        with set_temporary_encoding("utf-8"):
            self.write("\\e%G\xe2\x80\x94")
            self.expect("\xe2\x80\x94")

    def test_encoding_unicode_ascii(self):
        with set_temporary_encoding("ascii"):
            self.write("\\e%G\xe2\x80\x94")
            self.expect("?")

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
        self.write("\\e]0;bad \xff\007\\e[0G\\e[2Ktest3")
        self.expect("test3")
        self.expect_signal("bad \ufffd")
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
        """Apply an ICH, DCH, IL or DL count larger than the screen at once instead of once per unit."""

        def timeout(_signum: int, _frame: object) -> typing.NoReturn:
            msg = "control sequence count was applied one unit at a time"
            raise TimeoutError(msg)

        self.addCleanup(signal.signal, signal.SIGALRM, signal.signal(signal.SIGALRM, timeout))
        self.addCleanup(signal.setitimer, signal.ITIMER_REAL, 0)
        count = 10**15
        for label, size, output, screen in (
            ("ICH", (80, 24), rf"abcdef\e[3G\e[{count}@x", "abx"),
            ("DCH", (80, 24), rf"abcdef\e[3G\e[{count}Px", "abx"),
            ("IL", (3, 3), f"a\nb\nc\\e[2;1H\\e[{count}Lx", "a\nx"),
            ("DL", (3, 3), f"a\nb\nc\\e[2;1H\\e[{count}Mx", "a\nx"),
        ):
            with self.subTest(label):
                self.restart(*size)
                signal.setitimer(signal.ITIMER_REAL, 5)
                self.write(output)
                self.expect(screen)
                signal.setitimer(signal.ITIMER_REAL, 0)

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
            ("DSR reports the terminal OK", r"\e[5n", b"\x1b[0n"),
            ("DA reports a VT102", r"\e[c", b"\x1b[?6c"),
            ("DA with a private marker is not answered", r"\e[?c", b""),
            ("DECID reports a VT102", r"\eZ", b"\x1b[?6c"),
        ):
            with self.subTest(label):
                self.restart()
                self.write(query)
                self.read()
                self.assertEqual(bytes(self.pty.from_widget), answer)

    def test_save_restore_cursor_esc_keeps_attributes(self) -> None:
        """Restore the attributes saved by DECSC together with the cursor position."""
        self.write(r"\e[31mab\e7\e[0m\e[2;1Hcd\e8e")
        red = urwid.AttrSpec("dark red", "default")
        self.expect(
            [
                [(red, None, b"a"), (red, None, b"b"), (red, None, b"e")],
                [(None, None, b"c"), (None, None, b"d")],
            ],
            raw=True,
        )

    def test_charset_designation(self) -> None:
        """Draw with the DEC special graphics set while it is designated as G0."""
        self.write(r"\e(0q\e(Bq")
        self.expect([[(None, "0", b"q"), (None, None, b"q")]], raw=True)

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
        """Set the attributes of 16-colour, 256-colour and true-colour SGR sequences, brightening bold colours."""
        self.write(r"\e[1;4;7;31;42ma\e[0mb\e[38;5;100mc\e[0;38;2;1;2;3;48;2;4;5;6md")
        self.expect(
            [
                [
                    (urwid.AttrSpec("light red,bold,underline,standout", "dark green"), None, b"a"),
                    (None, None, b"b"),
                    (urwid.AttrSpec("h100", "default", 256), None, b"c"),
                    (urwid.AttrSpec("#010203", "#040506", 2**24), None, b"d"),
                ]
            ],
            raw=True,
        )

    def test_cursor_coords_follow_resize(self) -> None:
        """Report the cursor position constrained to the size being rendered."""
        self.write("abc")
        self.read()
        self.assertEqual(self.term.get_cursor_coords((80, 24)), (3, 0))
        self.assertEqual(self.term.get_cursor_coords((2, 24)), (1, 0))

    def test_resize_keeps_the_cursor_on_its_line(self) -> None:
        """Keep the cursor on its line when the width changes or lines move to and from the scrollback."""
        self.write("a\nb\nc\\e[2;2H")
        for size, char in (((70, 24), "X"), ((70, 23), "Y"), ((80, 24), "Z")):
            self.read()
            self.resize(*size)
            self.write(char)
        self.expect("a\nbXYZ\nc")

    def test_resize_adds_cells_without_attributes(self) -> None:
        """Fill the columns and rows a resize adds with cells that do not take the attributes in effect."""
        self.write(r"\e[41m")
        self.read()
        self.resize(90, 26)
        added = {cell for line in self.term.term.term[:24] for cell in line[80:]}
        added |= {cell for line in self.term.term.term[24:] for cell in line}
        self.assertEqual(added, {(None, None, b" ")})

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

    def test_ctrl_keys_without_control_character_are_not_handled(self) -> None:
        """Return a ctrl key that has no C0 control character unhandled, writing nothing to the child."""
        for key in ("ctrl f5", "ctrl up", "ctrl 5"):
            with self.subTest(key=key):
                self.term.keygrab = True
                self.assertEqual(self.term.keypress(self.termsize, key), key)
                self.assertEqual(bytes(self.pty.from_widget), b"")

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


if __name__ == "__main__":
    unittest.main()
