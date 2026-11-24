# Urwid terminal emulation widget
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


"""Terminal emulator widget that runs a child process on a pty."""

from __future__ import annotations

import atexit
import errno
import fcntl
import os
import pty
import selectors
import signal
import struct
import sys
import termios
import time
import traceback
import types
import typing
from contextlib import suppress

from urwid import event_loop
from urwid.ansi_parser import MAX_OSC_LENGTH
from urwid.canvas.term import (
    CHARSET_DEFAULT,
    CHARSET_UTF8,
    CSI_COMMANDS,
    ESC,
    ESC_B,
    CSIAlias,
    CSICommand,
    TermCanvas,
    TermCharset,
    TermModes,
)
from urwid.canvas.term import _state as _term_state
from urwid.display import RealTerminal
from urwid.display.escape import (
    _C1_CONTROLS,
    _CSI_LETTER_KEYS,
    _CSI_TILDE_KEYS,
    _CSI_U_KEYS,
    _KEY_MODIFIER_PREFIXES,
    _MOUSE_BYTE_OFFSET,
    _MOUSE_COORD_OFFSET,
    _MOUSE_MODIFIER_PREFIXES,
    _TILDE_KEY_NUMBERS,
    CSI,
    MOUSE_X10_PAST_END,
    KeyModifier,
    KittyKeyboardFlag,
    MouseBit,
    PrivateMode,
    _mouse_button,
    window_size_report,
)
from urwid.widget import MouseButton, Sizing, Widget

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from typing import Literal

    from urwid.canvas.term._state import TermType

    class _WatchLoop(typing.Protocol):
        """Loop the pty is watched on: an event loop or a :class:`urwid.MainLoop`."""

        def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> typing.Any:
            """Call *callback* when *fd* is readable and return a handle for :meth:`remove_watch_file`."""

        def remove_watch_file(self, handle: typing.Any) -> object:
            """Stop the watch :meth:`watch_file` returned *handle* for."""


# Re-exports of the urwid.canvas.term names, and of MAX_OSC_LENGTH, for callers that import them from urwid.vterm.
__all__ = (
    "CHARSET_DEFAULT",
    "CHARSET_UTF8",
    "CSI_COMMANDS",
    "EOF",
    "ESC",
    "ESC_B",
    "KEY_TRANSLATIONS",
    "KEY_TRANSLATIONS_DECCKM",
    "MAX_OSC_LENGTH",
    "CSIAlias",
    "CSICommand",
    "TermCanvas",
    "TermCharset",
    "TermModes",
    "Terminal",
)

EOF = b""


KEY_TRANSLATIONS = {
    "enter": "\r",
    "backspace": chr(127),
    "tab": "\t",
    "esc": ESC,
    **{key: f"{CSI}{final:c}" for final, key in _CSI_LETTER_KEYS.items() if key in {"up", "down", "right", "left"}},
    **{
        key: f"{CSI}{_TILDE_KEY_NUMBERS[key]:d}~" for key in ("home", "insert", "delete", "end", "page up", "page down")
    },
    "begin paste": f"{CSI}200~",
    "end paste": f"{CSI}201~",
    # F1 to F5 as the linux terminal type the child is given sends them
    **{f"f{number:d}": f"{CSI}[{letter}" for number, letter in enumerate("ABCDE", start=1)},
    **{f"f{number:d}": f"{CSI}{_TILDE_KEY_NUMBERS[f'f{number:d}']:d}~" for number in range(6, 21)},
    "shift tab": f"{ESC}\t",  # kcbt of the linux terminal type the child is given
}

#: the legacy key that a key name only the keyboard protocols report (see ``extended_keys`` of the raw display)
#: collapses to in a legacy terminal, as the kitty keyboard protocol's legacy encoding sends it: Enter and Esc lose
#: shift and ctrl, Tab and Backspace lose shift, ctrl Backspace is ctrl H, and ctrl maps Space, "/", "?" and "~" to
#: NUL, US, DEL and RS. The digits are left out, because urwid names the keypad keys with them, and ctrl with the
#: keypad's middle key is "ctrl 5" too.
_LEGACY_KEYS: typing.Final = {
    "shift enter": "enter",
    "ctrl enter": "enter",
    "shift ctrl enter": "enter",
    "ctrl tab": "tab",
    "shift ctrl tab": "shift tab",
    "shift backspace": "backspace",
    "ctrl backspace": "ctrl h",
    "shift ctrl backspace": "ctrl h",
    "shift esc": "esc",
    "ctrl esc": "esc",
    "shift ctrl esc": "esc",
    "ctrl  ": "ctrl @",
    "ctrl /": "ctrl _",
    # without the shifted key in the report, as from a terminal that does not report alternate keys
    "shift ctrl /": "ctrl _",
    "ctrl ?": "backspace",
    "ctrl ~": "ctrl ^",
}

KEY_TRANSLATIONS_DECCKM = {
    "up": f"{ESC}OA",
    "down": f"{ESC}OB",
    "right": f"{ESC}OC",
    "left": f"{ESC}OD",
    "f1": f"{ESC}OP",
    "f2": f"{ESC}OQ",
    "f3": f"{ESC}OR",
    "f4": f"{ESC}OS",
    "f5": f"{CSI}{_TILDE_KEY_NUMBERS['f5']:d}~",
}

#: the most bytes of the child's input kept while the pty does not take them; more is dropped, so a child that sends
#: queries and never reads its input cannot make the widget keep the replies without bound
_UNSENT_INPUT_LIMIT: typing.Final = 1 << 20
#: seconds between tries to write the rest of the child's input while the pty does not take it
_UNSENT_RETRY_DELAY: typing.Final = 0.05

#: the tracking modes a Terminal recognises and sends no reports for
_MOUSE_UNREPORTED_TRACKING_MODES: typing.Final = frozenset((None, PrivateMode.MOUSE_HIGHLIGHT_TRACKING))
#: the buttons X10 compatibility mode reports, those of the mice it was made for
_MOUSE_X10_BUTTONS: typing.Final = frozenset((MouseButton.LEFT, MouseButton.MIDDLE, MouseButton.RIGHT))
#: the 0-based coordinate past what the X10 and the UTF-8 encoding can carry, which xterm sends as a NUL byte
_MOUSE_COORDINATE_LIMITS: typing.Final = {
    None: MOUSE_X10_PAST_END,
    PrivateMode.MOUSE_UTF8_MODE: 2047 - _MOUSE_BYTE_OFFSET,
}
#: the button bits of a mouse report for each urwid button number, the inverse of the decoding in urwid.display.escape
_MOUSE_BUTTON_CODES: typing.Final = {
    _mouse_button(bits): bits
    for bits in (
        *range(3),
        *(MouseBit.HIGH_BUTTON + n for n in range(4)),
        *(MouseBit.EXTRA_BUTTON + n for n in range(4)),
    )
}
#: the wheel buttons, whose release xterm does not report
_MOUSE_WHEEL_BUTTONS: typing.Final = frozenset(range(MouseButton.WHEEL_UP, MouseButton.BACK))

#: the flags whose key reports differ from the legacy keys; event types and alternate keys alone change no key press
_KITTY_KEYBOARD_REPORTING_FLAGS: typing.Final = KittyKeyboardFlag.DISAMBIGUATE | KittyKeyboardFlag.ALL_KEYS
#: the keypad keys' codes in a CSI u report, from 0 to the middle key; urwid names these keys as the main keys
_KITTY_KEYPAD_CODES: typing.Final = range(57399, 57428)
#: the CSI u codes of Caps Lock, Scroll Lock, Num Lock and the modifier keys, which are reported only with all keys as
#: escape codes
_KITTY_MODIFIER_KEY_CODES: typing.Final = frozenset((*range(57358, 57361), *range(57441, 57455)))
#: the C1 control character of each key name the input decoder gives it, which the child receives
_C1_KEYS: typing.Final = {f"<{code:d}>": chr(code) for code in _C1_CONTROLS}
#: the key of each CSI 1 ; modifiers letter report, by urwid name; "5" is left out, since it is also the digit key
_KITTY_LETTER_KEYS: typing.Final = {name: chr(final) for final, name in _CSI_LETTER_KEYS.items() if name != "5"}
#: the key of each CSI number ~ report, by urwid name: the editing keys, F3 and F5 to F12; F13 and above are CSI u keys
_KITTY_TILDE_KEYS: typing.Final = {
    name: number for number, name in _CSI_TILDE_KEYS.items() if number <= 24 and name not in _KITTY_LETTER_KEYS
}
#: the final byte of each key xterm sends as CSI or SS3 and a letter: the cursor keys, Home, End and F1 to F4; F3 is
#: one too, where a report to urwid leaves it out
_XTERM_LETTER_KEYS: typing.Final = types.MappingProxyType({**_KITTY_LETTER_KEYS, "f3": "R"})
#: the keys xterm sends as SS3 and a letter without modifiers whatever cursor key mode (DECCKM) is: F1 to F4
_XTERM_SS3_KEYS: typing.Final = frozenset(("f1", "f2", "f3", "f4"))
#: the number of each key xterm sends as CSI number ~: the editing keys and F5 to F12
_XTERM_TILDE_KEYS: typing.Final = types.MappingProxyType(
    {
        key: _TILDE_KEY_NUMBERS[key]
        for key in ("insert", "delete", "page up", "page down", *(f"f{number:d}" for number in range(5, 13)))
    }
)
#: F13 to F24, which xterm-256color describes as F1 to F12 with shift, by the key xterm sends them as
_XTERM_SHIFTED_F_KEYS: typing.Final = types.MappingProxyType(
    {f"f{number + 12:d}": f"f{number:d}" for number in range(1, 13)}
)
#: the modifiers xterm reports in a cursor, editing or function key
_XTERM_KEY_MODIFIERS: typing.Final = KeyModifier.SHIFT | KeyModifier.ALT | KeyModifier.CTRL

#: the code of each key a CSI u report names by a code that is not its text, by urwid name; Backspace is 127
_KITTY_CSI_U_KEYS: typing.Final = {
    name: code for code, name in _CSI_U_KEYS.items() if code != 8 and code not in _KITTY_KEYPAD_CODES
}
#: the keys the kitty keyboard protocol sends as legacy keys without modifiers, unless all keys are escape codes
_KITTY_LEGACY_KEYS: typing.Final = frozenset(("enter", "tab", "backspace"))
#: the keys that frame pasted text, which is sent as typed in a legacy terminal whatever the keyboard flags
_PASTE_KEYS: typing.Final = frozenset(("begin paste", "end paste"))

#: the cursor keys xterm sends for the mouse wheel in alternate scroll mode (1007), by wheel button, and how many it
#: sends for one step of the wheel, as its default translations scroll-back(5,line) and scroll-forw(5,line) give
_ALTERNATE_SCROLL_KEYS: typing.Final[types.MappingProxyType[int, str]] = types.MappingProxyType(
    {MouseButton.WHEEL_UP: "up", MouseButton.WHEEL_DOWN: "down"}
)
_ALTERNATE_SCROLL_LINES: typing.Final = 5

#: the focus event reports xterm sends in focus reporting mode (1004), by the urwid key the display reports them as
_FOCUS_REPORTS: typing.Final = types.MappingProxyType({"focus in": b"\x1b[I", "focus out": b"\x1b[O"})


def _mouse_report(code: int, col: int, row: int, release: bool, encoding: PrivateMode | None) -> bytes:
    """Return the bytes xterm sends for a mouse event with button byte *code* at 0-based *col* and *row*.

    :param release: the event is a release, which only the SGR encoding marks apart from the button byte.
    :param encoding: the mode of the encoding, or None for the X10 encoding.
    """
    if encoding == PrivateMode.MOUSE_SGR_MODE:
        return f"{CSI}<{code};{col + 1};{row + 1}{'m' if release else 'M'}".encode("ascii")

    limit = _MOUSE_COORDINATE_LIMITS[encoding]
    # a coordinate past the limit is sent as the limit, and the limit as a NUL byte
    coordinates = (min(value, limit) for value in (col, row))
    values = [
        code + _MOUSE_BYTE_OFFSET,
        *(0 if value == limit else value + _MOUSE_COORD_OFFSET for value in coordinates),
    ]
    if encoding == PrivateMode.MOUSE_UTF8_MODE:
        # UTF-8 encoding: each value is a character, so one above 127 takes two bytes
        return f"{CSI}M".encode("ascii") + "".join(map(chr, values)).encode("utf-8")
    return f"{CSI}M".encode("ascii") + bytes(values)


class Terminal(Widget):
    """Widget that runs a child process (or callable) and renders its terminal output."""

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    signals: typing.ClassVar[list[str]] = ["closed", "beep", "leds", "title", "resize"]

    # Upper bound on the bytes drained in one feed() call while term_modes.synchronized_output is set,
    # so a child that opens a synchronized-output block (CSI ?2026h) and never closes it --
    # deliberately or by being slow -- cannot stall feed() from ever returning.
    _SYNCHRONIZED_OUTPUT_DRAIN_LIMIT: typing.ClassVar[int] = 1 << 16

    def __init__(
        self,
        command: tuple[str | bytes | os.PathLike[str] | os.PathLike[bytes], ...]
        | list[str | bytes | os.PathLike[str] | os.PathLike[bytes]]
        | Callable[[], typing.Any]
        | None,
        env: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
        main_loop: _WatchLoop | None = None,
        escape_sequence: str | None = None,
        encoding: str = "utf-8",
        *,
        scroll_on_output: bool = True,
        pass_signal_keys: bool = True,
        term: TermType = "linux",
    ) -> None:
        """Initialize a terminal emulator widget.

        ``command`` is the command to execute inside the terminal,
        provided as a list of the command followed by its arguments.
        If 'command' is None, the command is the current user's shell.
        You can also provide a callable instead of a command, which will be executed in the subprocess.

        ``env`` can be used to pass custom environment variables. If omitted,
        os.environ is used.

        ``main_loop`` is the loop to watch the pty on: an event loop or a :class:`MainLoop`,
        whose remove_watch_file must accept the handle its watch_file returned.
        Left out, the terminal watches the pty on the started :class:`MainLoop` it is rendered under,
        and while none runs it reads the pty on every render.
        The watch moves at the first render under another loop, or under no loop, and is removed by :meth:`terminate`.

        ``escape_sequence`` is the urwid key symbol which should be used to break
        out of the terminal widget. If it's not specified, ``ctrl a`` is used.

        ``encoding`` specifies the encoding that is being used when local
        keypresses in Unicode are encoded into raw bytes. UTF-8 is used by default.
        Set this to the encoding of your terminal if you need to transmit
        characters to the spawned process in non-UTF8 encoding.
        Applies to Python 3.x only.

        ``scroll_on_output`` moves a view scrolled back with :kbd:`Page Up` back to the bottom when the child writes,
        as xterm does by default. Set it to ``False`` to keep the view on the lines it shows while new output scrolls
        into the scrollback below them.

        ``pass_signal_keys`` turns off the signal keys of the terminal the application runs in, such as :kbd:`Ctrl+C`,
        while the widget has the focus, so they reach the child as keys.
        Set it to ``False`` when that terminal is not the one the user types into, as for a widget shown in a browser,
        to keep the application's own terminal as it is.

        ``term`` is the terminal type the child is given as ``TERM``: ``"linux"`` follows the Linux console where it
        differs from xterm, and ``"xterm-256color"`` follows xterm, in the keys sent and in the control functions read,
        as :ref:`the manual <basic-grafic-widgets>` describes.

        :raises ValueError: *term* is not one of those terminal types.

        .. note::

            If your Terminal instance does not show Unicode glyphs correctly, urwid's encoding is not UTF-8.
            It is taken from the locale at start-up, and ``urwid.set_encoding("utf-8")`` sets it.
            See :ref:`text-encodings` for more details.
        """
        if term not in _term_state.TERM_TYPES:
            raise ValueError(f"term must be one of {sorted(_term_state.TERM_TYPES)}, not {term!r}")
        super().__init__()

        #: The terminal type the child is given, see :meth:`__init__`.
        self.term_type: TermType = term
        self.escape_sequence: str = escape_sequence or "ctrl a"
        self._scroll_on_output = scroll_on_output
        self._pass_signal_keys = pass_signal_keys

        self.env = dict(env or os.environ)

        self.command = command or [self.env.get("SHELL", "/bin/sh")]

        self.encoding = encoding

        self.keygrab = False
        self.last_key: str | None = None
        # the keys between "begin paste" and "end paste" are being handled
        self._pasting = False
        # the button of the last press reported to the child, for a release or a drag that does not name its button
        self._pressed_button = 0

        self.response_buffer: list[str] = []
        # the child's input the pty did not take yet, sent before anything later, see _send()
        self._unsent = bytearray()
        # the event loop and handle of the alarm that tries to write _unsent again, None without one
        self._unsent_retry: tuple[event_loop.EventLoop, typing.Any] | None = None

        self.term_modes = TermModes()

        self.main_loop = main_loop

        self.master: int | None = None
        # the loop add_watch() watches the pty on, None while no watch is set
        self._watch_loop: _WatchLoop | None = None
        # what _watch_loop.watch_file() returned for the pty; not always the descriptor, as tornado and trio show
        self._watch_handle: typing.Any = None
        # for a MainLoop found running, the start it was found in: the watch lasts for that one start
        self._watch_activation: object = None
        self.pid: int | None = None

        self.width: int | None = None
        self.height: int | None = None
        self.term: TermCanvas | None = None
        self.has_focus = False
        self.old_tios: tuple[bytes, bytes, bytes, bytes, bytes] | None = None
        self.terminated = False

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return where the cursor is drawn at *size* when the widget has focus.

        :returns: the ``(column, row)`` of the cursor, or ``None`` when it is not drawn:
            the child hid it, or the view is scrolled back so far that its row is not shown.
        """
        if self.term is None or not self.term.modes.visible_cursor:
            return None

        # temporarily set width/height to figure out the new cursor position
        # given the provided width/height
        orig_width, orig_height = self.term.width, self.term.height

        self.term.width = size[0]
        self.term.height = size[1]

        x, y = self.term.constrain_coords(
            self.term.term_cursor[0],
            self.term.term_cursor[1],
        )

        self.term.width, self.term.height = orig_width, orig_height

        if self.term.scrolling_up >= size[1] - y:
            return None
        return (x, y + self.term.scrolling_up)

    def spawn(self) -> None:
        """Fork the child process running :attr:`command` and connect it to a new pty."""
        env = self.env
        env["TERM"] = self.term_type

        self.pid, self.master = pty.fork()

        if self.pid == 0:
            if callable(self.command):
                try:
                    # noinspection PyBroadException
                    try:
                        self.command()
                    except BaseException:  # noqa: BLE001  # special case
                        sys.stderr.write(traceback.format_exc())
                    for stream in (sys.stderr, sys.stdout):
                        with suppress(OSError, ValueError):
                            stream.flush()
                finally:
                    os._exit(0)
            try:
                os.execvpe(self.command[0], self.command, env)  # noqa: S606
            except (OSError, TypeError, ValueError) as exc:
                reason = getattr(exc, "strerror", None) or exc
                with suppress(OSError):
                    os.write(2, f"{os.fsdecode(self.command[0])}: {reason}\r\n".encode(errors="replace"))
            finally:
                # 127 is the shell's "command not found" status
                os._exit(127)

        atexit.register(self.terminate)

    def terminate(self) -> None:
        """Stop watching the pty, end the child process and close the pty master.

        Signals escalate from SIGHUP to SIGKILL until the child exits.
        A child that may not be signalled, such as a setuid program, only gets the hangup from closing the master.
        It is then waited for at most one second, and left unreaped if it keeps running.
        """
        if self.terminated:
            return

        self.terminated = True
        atexit.unregister(self.terminate)
        self._cancel_unsent_retry()
        self._unsent.clear()

        if self.pid is not None and self.pid > 0:
            self.remove_watch()
            self.set_termsize(0, 0)
            reaped = killed = False
            try:
                for sig in (signal.SIGHUP, signal.SIGCONT, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.kill(self.pid, sig)
                    except ProcessLookupError:
                        # reaped by someone else: a further signal could hit a process that reuses the pid
                        reaped = True
                        break
                    except PermissionError:
                        # e.g. a setuid child: only the hangup from closing the master below reaches it
                        break
                    killed = sig == signal.SIGKILL
                    if reaped := self._reap_child(0.1):
                        break
            finally:
                os.close(typing.cast("int", self.master))
            if killed and not reaped:
                with suppress(ChildProcessError):
                    os.waitpid(self.pid, 0)
            elif not reaped:
                self._reap_child(1.0)

        # last, so a tty that is already gone cannot stop the cleanup above
        if self.has_focus and self.old_tios:
            RealTerminal().tty_signal_keys(*self.old_tios)

    def _reap_child(self, timeout: float) -> bool:
        """Poll for the child's exit for up to *timeout* seconds, and return whether it is reaped."""
        deadline = time.monotonic() + timeout
        with suppress(ChildProcessError):  # reaped by someone else
            while os.waitpid(typing.cast("int", self.pid), os.WNOHANG)[0] == 0:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.01)
        return True

    def beep(self) -> None:
        """Emit a "beep" signal for anything listening on this widget."""
        self._emit("beep")

    def leds(self, which: Literal["clear", "scroll_lock", "num_lock", "caps_lock"]) -> None:
        """Emit a "leds" signal asking the display to set keyboard LED state *which*."""
        self._emit("leds", which)

    def respond(self, string: str) -> None:
        """Respond to the underlying application with 'string'."""
        self.response_buffer.append(string)

    def flush_responses(self) -> None:
        """Send every buffered response to the child, see :meth:`_send`, and clear the buffer."""
        if self.response_buffer:
            self._send("".join(self.response_buffer).encode("ascii"))
        self.response_buffer = []

    def _write_report(self, data: bytes) -> None:
        """Send *data* to the child when the pty can take input now and nothing is still unsent, and drop it otherwise.

        It is for what the terminal sends without a key typed, such as a size or focus report, which a child that
        stopped reading its input does not need later.
        """
        self._write_unsent()
        if self._unsent:
            return
        with selectors.DefaultSelector() as selector:
            selector.register(typing.cast("int", self.master), selectors.EVENT_WRITE)
            if selector.select(0):
                self._send(data)

    def _send(self, data: bytes) -> None:
        """Write *data* to the child's input, after what the pty has not taken yet, without blocking the event loop.

        What the pty does not take now is kept and written, in order, as the child reads its input: at the next render,
        key, mouse report or reply, and every ``_UNSENT_RETRY_DELAY`` seconds on the event loop the pty is watched on,
        when it is an urwid one. *data* that would make more than ``_UNSENT_INPUT_LIMIT`` bytes kept, after the pty
        took what it can, is dropped.
        """
        if len(self._unsent) + len(data) > _UNSENT_INPUT_LIMIT:
            self._write_unsent()
        if len(self._unsent) + len(data) > _UNSENT_INPUT_LIMIT:
            return
        self._unsent += data
        self._write_unsent()

    def _write_unsent(self) -> None:
        """Write as much of the input :meth:`_send` kept as the pty takes now, and try the rest again later."""
        self._cancel_unsent_retry()
        if not self._unsent or self.terminated:
            return
        master = typing.cast("int", self.master)
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        # non-blocking for this write only: the reads stay blocking, guarded by select()
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            with suppress(BlockingIOError):
                while self._unsent:
                    del self._unsent[: os.write(master, self._unsent)]
        finally:
            fcntl.fcntl(master, fcntl.F_SETFL, flags)
        if not self._unsent:
            return
        loop = self._watch_loop.event_loop if isinstance(self._watch_loop, event_loop.MainLoop) else self._watch_loop
        if isinstance(loop, event_loop.EventLoop):
            self._unsent_retry = (loop, loop.alarm(_UNSENT_RETRY_DELAY, self._write_unsent))

    def _cancel_unsent_retry(self) -> None:
        """Remove the alarm that tries to write the unsent input again, when one is set."""
        if self._unsent_retry is not None:
            loop, handle = self._unsent_retry
            self._unsent_retry = None
            loop.remove_alarm(handle)

    def set_termsize(self, width: int, height: int) -> None:
        """Tell the pty the terminal window is now *width* by *height* characters."""
        winsize = struct.pack("HHHH", height, width, 0, 0)
        fcntl.ioctl(typing.cast("int", self.master), termios.TIOCSWINSZ, winsize)

    def touch_term(self, width: int, height: int) -> None:
        """Spawn the child process if needed, then resize the pty and terminal canvas to *width* by *height*."""
        process_opened = False

        if self.pid is None:
            self.spawn()
            process_opened = True

        if self.width == width and self.height == height:
            return

        self.set_termsize(width, height)

        if not self.term:
            self.term = TermCanvas(
                width,
                height,
                self,
                scroll_on_output=self._scroll_on_output,
                term_type=self.term_type,
            )
        else:
            self.term.resize(width, height)
            if self.term.modes.in_band_resize:
                # Sent after the size the child reads on SIGWINCH is set, as a terminal sends it.
                # A dropped report loses nothing the child cannot read with TIOCGWINSZ.
                self._write_report(window_size_report(width, height).encode("ascii"))

        self.width = width
        self.height = height

        if process_opened:
            self.add_watch()

        self._emit("resize", (width, height))

    def set_title(self, title: str) -> None:
        """Emit a "title" signal with the terminal's new *title*."""
        self._emit("title", title)

    def change_focus(self, has_focus: bool) -> None:
        """Ignore SIGINT if this widget has focus, unless the widget was made to leave the signal keys alone."""
        if self.terminated:
            return

        focus_changed = has_focus != self.has_focus
        self.has_focus = has_focus

        if self.term is not None:
            self.term.has_focus = has_focus
            self.term.set_term_cursor()

        if not focus_changed or not self._pass_signal_keys:
            return

        if has_focus:
            self.old_tios = RealTerminal().tty_signal_keys()
            RealTerminal().tty_signal_keys(*(["undefined"] * 5))  # type: ignore[arg-type]
        elif self.old_tios:
            RealTerminal().tty_signal_keys(*self.old_tios)

    def render(self, size: tuple[int, int], focus: bool = False) -> TermCanvas:  # type: ignore[override]
        """Resize the terminal to *size*, read any pending child output, and return the terminal canvas."""
        if not self.terminated:
            self.change_focus(focus)

            width, height = size
            self.touch_term(width, height)
            self._read_display()

            if self.main_loop is None:
                running = event_loop.get_running_loop_or_none()
                if self._watch_loop is not None and (
                    running is None
                    or running is not self._watch_loop
                    or running._activation is not self._watch_activation  # pylint: disable=protected-access
                ):
                    self.remove_watch()
                self.add_watch()
                if self._watch_loop is None:
                    self.wait_and_feed(0)
            self._write_unsent()

        return self.term  # type: ignore[return-value]

    def add_watch(self) -> None:
        """Register the pty with a loop, so :meth:`feed` runs on new child output.

        The loop is :attr:`main_loop`, or without one the started :class:`MainLoop` running in the caller's context.
        Nothing is registered while a watch is set, or when there is no such loop.
        """
        if self._watch_loop is not None:
            return
        loop = self.main_loop
        if loop is None:
            running = event_loop.get_running_loop_or_none()
            # A loop that is not started, found through a render by hand, runs no event loop to call the watch.
            if running is None or running._activation is None:  # pylint: disable=protected-access
                return
            self._watch_activation = running._activation  # pylint: disable=protected-access
            loop = running
        self._watch_handle = loop.watch_file(typing.cast("int", self.master), self.feed)
        self._watch_loop = loop

    def remove_watch(self) -> None:
        """Unregister the pty from the loop :meth:`add_watch` registered it on, when it did.

        The alarm that tries to write the unsent input again is removed from that loop too.
        """
        self._cancel_unsent_retry()
        if self._watch_loop is None:
            return
        self._watch_loop.remove_watch_file(self._watch_handle)
        self._watch_loop = self._watch_handle = self._watch_activation = None

    def wait_and_feed(self, timeout: float = 1.0) -> None:
        """Block up to *timeout* seconds for pty output, then read and process whatever has arrived."""
        with selectors.DefaultSelector() as selector:
            selector.register(typing.cast("int", self.master), selectors.EVENT_READ)

            if not selector.select(timeout):
                return

        self.feed()

    def _read_display(self) -> None:
        """Give the canvas the default colors of the display the widget is drawn on, which its replies describe.

        They are the outer terminal's default colors of the screen of :attr:`main_loop`, or of the running
        :class:`MainLoop`; a screen without them, such as curses, leaves them unknown.
        They are read again before each output of the child, since the screen learns them from the outer terminal's
        replies after the first render.
        """
        screen_loop = (
            self.main_loop if isinstance(self.main_loop, event_loop.MainLoop) else event_loop.get_running_loop_or_none()
        )
        if screen_loop is not None and self.term is not None:
            self.term.display_default_colors = getattr(screen_loop.screen, "terminal_default_colors", (None, None))

    def feed(self) -> None:
        """Read pending output from the pty and feed it to the terminal, terminating the child on EOF."""
        data = EOF

        try:
            data = os.read(typing.cast("int", self.master), 4096)
        except OSError as e:
            if e.errno == errno.EIO:  # EIO, child terminated
                data = EOF
            elif e.errno == errno.EWOULDBLOCK:  # empty buffer
                return
            else:
                raise

        if data == EOF:
            self.terminate()
            self._emit("closed")
            return

        self._read_display()
        self.term.addstr(data)  # type: ignore[union-attr]

        # The child just opened a synchronized-output block (CSI ?2026h) and is still writing to it:
        # draining whatever it has already queued on the pty before returning keeps the next
        # render() from ever handing out a half-painted mid-block canvas.
        # A child that never closes the block (CSI ?2026l) still gets control back
        # once _SYNCHRONIZED_OUTPUT_DRAIN_LIMIT is hit
        # or the pty simply has nothing more buffered right now.
        if self.term_modes.synchronized_output:
            # The master fd is blocking, so read only what select() reports as ready.
            with selectors.DefaultSelector() as selector:
                selector.register(typing.cast("int", self.master), selectors.EVENT_READ)
                drained = 0
                while (
                    self.term_modes.synchronized_output
                    and drained < self._SYNCHRONIZED_OUTPUT_DRAIN_LIMIT
                    and selector.select(0)
                ):
                    try:
                        more = os.read(typing.cast("int", self.master), 4096)
                    except OSError as e:
                        if e.errno == errno.EWOULDBLOCK:
                            break
                        if e.errno != errno.EIO:
                            raise
                        more = EOF

                    if more == EOF:
                        self.terminate()
                        self._emit("closed")
                        return

                    self.term.addstr(more)  # type: ignore[union-attr]
                    drained += len(more)

        self.flush_responses()

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Translate *key* into the byte sequence the child process expects and write it to the pty.

        :returns: ``None`` when the widget used *key*, or *key* when it did not: the child has exited, the key is
            handed down to the parent outside a key grab, or the terminal type the child is given has no byte form for
            it, as the ``linux`` one has none for a cursor or function key with shift, meta or ctrl.
        """
        if self.terminated:
            return key

        grabbed = self.keygrab

        if key in _FOCUS_REPORTS and self.term_modes.focus_reporting:
            # a focus change is no key: it starts no key grab and does not scroll a view scrolled back
            self._write_report(_FOCUS_REPORTS[key])
            return None

        if key in _PASTE_KEYS:
            self._pasting = key == "begin paste"
            if self.term_modes.bracketed_paste:
                pass  # passthrough bracketed paste sequences
            else:  # swallow bracketed paste sequences
                self.last_key = key
                return None

        if key == "window resize":
            width, height = size
            self.touch_term(width, height)
            return None

        if self.last_key == key == self.escape_sequence:
            # escape sequence pressed twice...
            self.last_key = key
            self.keygrab = True
            # ... so pass it to the terminal
        elif self.keygrab:
            if self.escape_sequence == key:
                # stop grabbing the terminal
                self.keygrab = False
                self.last_key = key
                return None
        else:
            if key == "page up":
                if self.term is not None:  # there is no scrollback before the first render
                    self.term.scroll_buffer()
                self.last_key = key
                self._invalidate()
                return None

            if key == "page down":
                if self.term is not None:  # there is no scrollback before the first render
                    self.term.scroll_buffer(up=False)
                self.last_key = key
                self._invalidate()
                return None

            if self.last_key == self.escape_sequence and key != self.escape_sequence:
                # hand down keypress directly after ungrab.
                self.last_key = key
                return key

            if self.escape_sequence == key:
                # start grabbing the terminal
                self.keygrab = True
                self.last_key = key
                return None

            if self._command_map[key] is None or key == "enter":
                # printable character or escape sequence means:
                # lock in terminal...
                self.keygrab = True
                # ... and do key processing
            else:
                # hand down keypress
                self.last_key = key
                return key

        self.last_key = key

        sent = self._key_sequence(key)
        if sent is None:
            # the key is returned to the parent, so a key grab it started is not kept
            self.keygrab = grabbed
            return key

        if self.term is None:
            # Only touch_term() starts the child and creates the canvas, and render() normally calls it first.
            width, height = size
            self.touch_term(width, height)

        self.term.scroll_buffer(reset=True)  # type: ignore[union-attr]

        self._send(sent.encode(self.encoding, "ignore"))

        return None

    def mouse_event(  # pyrefly: ignore[bad-override]  # a box widget, sized by two dimensions
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Report a mouse event to the child in the tracking mode and the encoding the child turned on.

        The report bytes are the ones xterm sends for the same event.

        In alternate scroll mode (1007), while the child is on the alternate screen and does not track the mouse,
        a wheel press without modifiers is sent as cursor up or down keys instead, as xterm sends them.

        :returns: ``True`` when the child tracks the mouse, also for an event its tracking mode does not report,
            and for a wheel press sent as cursor keys.
            Such events are a drag under mode 1000, the release of a wheel button, and under X10 compatibility mode (9)
            anything but a press of buttons 1 to 3.
            ``False`` when the event is left to the parent, in these cases:

            - the child has exited;
            - the child does not track the mouse, or tracks it in highlight mode (1001), which is not implemented;
            - the view is scrolled back from the screen the child sees;
            - the event is not a press, a release or a drag.
        """
        if self.terminated or self.term is None or self.term.scrolling_up:
            return False

        modes = self.term_modes
        if (
            modes.mouse_tracking is None
            and modes.alternate_scroll
            and modes.alternate_screen
            and event == "mouse press"
            and button in _ALTERNATE_SCROLL_KEYS
        ):
            sent = self._key_sequence(_ALTERNATE_SCROLL_KEYS[button])
            if sent is not None:
                self._write_report((sent * _ALTERNATE_SCROLL_LINES).encode(self.encoding))
            return True

        if modes.mouse_tracking in _MOUSE_UNREPORTED_TRACKING_MODES:
            return False

        code = 0
        action = event
        for prefix, flag in _MOUSE_MODIFIER_PREFIXES:
            if action.startswith(prefix):
                code |= flag
                action = action.removeprefix(prefix)

        release = action == "mouse release"
        x10 = modes.mouse_tracking == PrivateMode.MOUSE_X10
        if action == "mouse press":
            if x10:
                # X10 compatibility reports no modifiers
                if button not in _MOUSE_X10_BUTTONS:
                    return True
                code = 0
            elif button not in _MOUSE_WHEEL_BUTTONS:
                self._pressed_button = button
        elif action == "mouse drag":
            if x10 or modes.mouse_tracking == PrivateMode.MOUSE_REPORTING:
                return True
            button = button or self._pressed_button
            code |= MouseBit.DRAG
        elif release:
            # an X10 report from the parent's terminal does not say which button was released
            button = button or self._pressed_button
            self._pressed_button = 0
            if x10 or button in _MOUSE_WHEEL_BUTTONS:
                return True
        else:
            return False

        if release and modes.mouse_encoding != PrivateMode.MOUSE_SGR_MODE:
            # without SGR, a release names no button, so it is sent also when its button is unknown
            code |= MouseBit.BUTTON
        elif button in _MOUSE_BUTTON_CODES:
            code |= _MOUSE_BUTTON_CODES[button]
        else:
            return True

        self._send(_mouse_report(code, col, row, release, modes.mouse_encoding))
        return True

    def _key_sequence(self, key: str) -> str | None:
        """Return the characters the child receives for *key*, or ``None`` when its terminal type has none.

        While the flags the child set with the kitty keyboard protocol change key reports, the keys are sent in that
        protocol, except for pasted text, which is sent as a legacy terminal sends it.
        """
        name = key.removeprefix("meta ")
        if name in _C1_KEYS:
            key = key[: len(key) - len(name)] + _C1_KEYS[name]

        flags = self.term_modes.keyboard_flags[-1] if self.term_modes.keyboard_flags else 0
        if flags & _KITTY_KEYBOARD_REPORTING_FLAGS and not self._pasting and key not in _PASTE_KEYS:
            sent = _kitty_key_report(key, flags)
        else:
            sent = self._legacy_key_sequence(key)

        # ENTER transmits both a carriage return and linefeed in LF/NL mode.
        if self.term_modes.lfnl and sent is not None and sent.endswith("\r"):
            sent += "\n"

        return sent

    def _legacy_key_sequence(self, key: str) -> str | None:
        """Return the characters the child's terminal type sends for *key*, or ``None`` when it has none.

        ``xterm-256color`` sends the cursor, editing and function keys as xterm does, and any other key as ``linux``.
        """
        if self.term_type != "linux" and (
            sent := _xterm_key_sequence(_LEGACY_KEYS.get(key, key), cursor_keys_application=self.term_modes.keys_decckm)
        ):
            return sent
        meta = key.startswith("meta ")
        sent = key.removeprefix("meta ")
        sent = _LEGACY_KEYS.get(sent, sent)

        if sent.startswith("ctrl "):
            # C0 control characters only exist for "@", "A"-"Z" and "[\]^_"
            char = sent.removeprefix("ctrl ")
            # upper() of a non-ASCII letter can be an ASCII one: U+017F LATIN SMALL LETTER LONG S gives "S"
            char = char.upper() if char.isascii() else char
            if len(char) != 1 or not "@" <= char <= "_":
                return None
            sent = chr(ord(char) - ord("@"))
        elif self.term_modes.keys_decckm and sent in KEY_TRANSLATIONS_DECCKM:
            sent = KEY_TRANSLATIONS_DECCKM[sent]
        elif sent == "backspace" and self.term_modes.backarrow_sends_backspace:
            sent = "\b"
        elif sent in KEY_TRANSLATIONS:
            sent = KEY_TRANSLATIONS[sent]
        elif len(sent) > 1 and (sent.isascii() or " " in sent):
            # a key name such as "shift up", "focus in" or "super \u0436" has no form under TERM=linux, and is not
            # written as text
            return None

        # Meta (Alt) sends ESC before the key's single character, as xterm does with metaSendsEscape.
        # A key that is sent as an escape sequence has no such form.
        if meta and len(sent) != 1:
            return None

        if meta:
            sent = ESC + sent

        return sent


def _split_key_modifiers(key: str) -> tuple[str, int]:
    """Return the key name *key* without its modifier prefixes, and the modifier bits a terminal reports for them.

    urwid's "meta" is the modifier a terminal sends Alt as, so it gives the ALT bit alone.
    """
    name = key
    modifiers = 0
    for prefix, bits in _KEY_MODIFIER_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name.removeprefix(prefix)
            modifiers |= bits & ~KeyModifier.META
    return name, modifiers


def _xterm_key_sequence(key: str, *, cursor_keys_application: bool) -> str | None:
    """Return what xterm sends for the cursor, editing or function key *key*, or ``None`` for any other key.

    Without modifiers, F1 to F4 are sent as SS3 and a letter, and so are the cursor keys, Home and End while
    *cursor_keys_application* (DECCKM) is set; the other keys are sent as CSI and a letter or as CSI number ~.
    With shift, meta or ctrl, the key is sent as ``CSI 1 ; m letter`` or ``CSI number ; m ~``, m being 1 plus the
    modifier bits; Shift+Tab is sent as ``CSI Z``, and F13 to F24 as F1 to F12 with shift.
    A key with any other modifier has no form.
    """
    name, modifiers = _split_key_modifiers(key)
    if name == "tab" and modifiers == KeyModifier.SHIFT:
        return f"{CSI}Z"
    if name in _XTERM_SHIFTED_F_KEYS and not modifiers & KeyModifier.SHIFT:
        name = _XTERM_SHIFTED_F_KEYS[name]
        modifiers |= KeyModifier.SHIFT
    if modifiers & ~_XTERM_KEY_MODIFIERS:
        return None

    if name in _XTERM_LETTER_KEYS:
        final = _XTERM_LETTER_KEYS[name]
        if modifiers:
            return f"{CSI}1;{modifiers + 1:d}{final}"
        if cursor_keys_application or name in _XTERM_SS3_KEYS:
            return f"{ESC}O{final}"
        return f"{CSI}{final}"
    if name in _XTERM_TILDE_KEYS:
        number = _XTERM_TILDE_KEYS[name]
        return f"{CSI}{number:d};{modifiers + 1:d}~" if modifiers else f"{CSI}{number:d}~"
    return None


def _kitty_key_report(key: str, flags: int) -> str | None:
    """Return what a terminal sends for *key* in the kitty keyboard protocol, or ``None`` when it sends nothing.

    - Unless all keys are escape codes, a text key whose name has no modifiers is sent as its text.
    - Unless all keys are escape codes, Enter, Tab and Backspace without modifiers are sent as the legacy keys.
    - An upper case letter is reported as the lower case key with shift. With alternate keys, the report adds the
      upper case letter as the shifted key.
    - Another shifted symbol is reported as the symbol, since the key that types it depends on the keyboard layout.
    - The keypad keys are sent as the main keys, since urwid names them alike.

    :param key: the urwid key name.
    :param flags: the keyboard flags in effect, with disambiguate or all keys set.
    """
    name, modifiers = _split_key_modifiers(key)
    all_keys = flags & KittyKeyboardFlag.ALL_KEYS

    if name in _KITTY_LETTER_KEYS:
        final = _KITTY_LETTER_KEYS[name]
        return f"{CSI}1;{modifiers + 1:d}{final}" if modifiers else f"{CSI}{final}"
    if name in _KITTY_TILDE_KEYS:
        number = _KITTY_TILDE_KEYS[name]
        return f"{CSI}{number:d};{modifiers + 1:d}~" if modifiers else f"{CSI}{number:d}~"

    text = ""
    if name in _KITTY_CSI_U_KEYS:
        code = _KITTY_CSI_U_KEYS[name]
        if not (modifiers or all_keys) and name in _KITTY_LEGACY_KEYS:
            return KEY_TRANSLATIONS[name]
        if code in _KITTY_MODIFIER_KEY_CODES and not all_keys:
            return None
        key_field = f"{code:d}"
    elif len(name) == 1 and name.isprintable():
        if not (modifiers or all_keys):
            return name
        if not modifiers:
            # the text the key types, which a name with a modifier does not give
            text = name
        if len(lower := name.lower()) == 1 and lower != name and lower.upper() == name:
            # an upper case letter, typed with shift
            modifiers |= KeyModifier.SHIFT
            key_field = f"{ord(lower):d}"
            if flags & KittyKeyboardFlag.ALTERNATE_KEYS:
                key_field += f":{ord(name):d}"
        else:
            key_field = f"{ord(name):d}"
    else:
        return None

    modifiers_field = f"{modifiers + 1:d}" if modifiers else ""
    if text and flags & KittyKeyboardFlag.ASSOCIATED_TEXT:
        return f"{CSI}{key_field};{modifiers_field};{ord(text):d}u"
    if modifiers:
        return f"{CSI}{key_field};{modifiers_field}u"
    return f"{CSI}{key_field}u"
