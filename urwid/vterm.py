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
import typing
from contextlib import suppress

from urwid import event_loop
from urwid.ansi_parser import MAX_OSC_LENGTH
from urwid.display import RealTerminal
from urwid.display.escape import (
    _CSI_LETTER_KEYS,
    _CSI_TILDE_KEYS,
    _CSI_U_KEYS,
    _KEY_MODIFIER_PREFIXES,
    _MOUSE_BYTE_OFFSET,
    _MOUSE_COORD_OFFSET,
    MOUSE_X10_PAST_END,
    KeyModifier,
    KittyKeyboardFlag,
    MouseBit,
    PrivateMode,
    window_size_report,
)
from urwid.term_canvas import (
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
from urwid.widget import MouseButton, Sizing, Widget

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from typing import Literal

    class _WatchLoop(typing.Protocol):
        """Loop the pty is watched on: an event loop or a :class:`urwid.MainLoop`."""

        def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> typing.Any:
            """Call *callback* when *fd* is readable and return a handle for :meth:`remove_watch_file`."""

        def remove_watch_file(self, handle: typing.Any) -> object:
            """Stop the watch :meth:`watch_file` returned *handle* for."""


# Re-exports of the urwid.term_canvas names, and of MAX_OSC_LENGTH, for callers that import them from urwid.vterm.
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
    "up": f"{ESC}[A",
    "down": f"{ESC}[B",
    "right": f"{ESC}[C",
    "left": f"{ESC}[D",
    "home": f"{ESC}[1~",
    "insert": f"{ESC}[2~",
    "delete": f"{ESC}[3~",
    "end": f"{ESC}[4~",
    "page up": f"{ESC}[5~",
    "page down": f"{ESC}[6~",
    "begin paste": f"{ESC}[200~",
    "end paste": f"{ESC}[201~",
    "f1": f"{ESC}[[A",
    "f2": f"{ESC}[[B",
    "f3": f"{ESC}[[C",
    "f4": f"{ESC}[[D",
    "f5": f"{ESC}[[E",
    "f6": f"{ESC}[17~",
    "f7": f"{ESC}[18~",
    "f8": f"{ESC}[19~",
    "f9": f"{ESC}[20~",
    "f10": f"{ESC}[21~",
    "f11": f"{ESC}[23~",
    "f12": f"{ESC}[24~",
    "f13": f"{ESC}[25~",
    "f14": f"{ESC}[26~",
    "f15": f"{ESC}[28~",
    "f16": f"{ESC}[29~",
    "f17": f"{ESC}[31~",
    "f18": f"{ESC}[32~",
    "f19": f"{ESC}[33~",
    "f20": f"{ESC}[34~",
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
    "f5": f"{ESC}[15~",
}

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
    **{button: button - MouseButton.LEFT for button in range(MouseButton.LEFT, MouseButton.WHEEL_UP)},
    **{
        button: MouseBit.HIGH_BUTTON + button - MouseButton.WHEEL_UP
        for button in range(MouseButton.WHEEL_UP, MouseButton.BACK)
    },
    **{
        button: MouseBit.EXTRA_BUTTON + button - MouseButton.BACK
        for button in range(MouseButton.BACK, MouseButton.BACK + 4)
    },
}
#: the wheel buttons, whose release xterm does not report
_MOUSE_WHEEL_BUTTONS: typing.Final = frozenset(range(MouseButton.WHEEL_UP, MouseButton.BACK))
#: the modifier prefixes of an urwid mouse event, in the order urwid writes them, and their bits in a mouse report
_MOUSE_MODIFIERS: typing.Final = (("shift ", MouseBit.SHIFT), ("meta ", MouseBit.META), ("ctrl ", MouseBit.CTRL))

#: the flags whose key reports differ from the legacy keys; event types and alternate keys alone change no key press
_KITTY_KEYBOARD_REPORTING_FLAGS: typing.Final = KittyKeyboardFlag.DISAMBIGUATE | KittyKeyboardFlag.ALL_KEYS
#: the keypad keys' codes in a CSI u report, from 0 to the middle key; urwid names these keys as the main keys
_KITTY_KEYPAD_CODES: typing.Final = range(57399, 57428)
#: the CSI u codes of Caps Lock, Scroll Lock, Num Lock and the modifier keys, which are reported only with all keys as
#: escape codes
_KITTY_MODIFIER_KEY_CODES: typing.Final = frozenset((*range(57358, 57361), *range(57441, 57455)))
#: the key of each CSI 1 ; modifiers letter report, by urwid name; "5" is left out, since it is also the digit key
_KITTY_LETTER_KEYS: typing.Final = {name: chr(final) for final, name in _CSI_LETTER_KEYS.items() if name != "5"}
#: the key of each CSI number ~ report, by urwid name: the editing keys, F3 and F5 to F12; F13 and above are CSI u keys
_KITTY_TILDE_KEYS: typing.Final = {
    name: number for number, name in _CSI_TILDE_KEYS.items() if number <= 24 and name not in _KITTY_LETTER_KEYS
}
#: the code of each key a CSI u report names by a code that is not its text, by urwid name; Backspace is 127
_KITTY_CSI_U_KEYS: typing.Final = {
    name: code for code, name in _CSI_U_KEYS.items() if code != 8 and code not in _KITTY_KEYPAD_CODES
}
#: the keys the kitty keyboard protocol sends as legacy keys without modifiers, unless all keys are escape codes
_KITTY_LEGACY_KEYS: typing.Final = frozenset(("enter", "tab", "backspace"))
#: the keys that frame pasted text, which is sent as typed in a legacy terminal whatever the keyboard flags
_PASTE_KEYS: typing.Final = frozenset(("begin paste", "end paste"))


def _mouse_report(code: int, col: int, row: int, release: bool, encoding: PrivateMode | None) -> bytes:
    """Return the bytes xterm sends for a mouse event with button byte *code* at 0-based *col* and *row*.

    :param release: the event is a release, which only the SGR encoding marks apart from the button byte.
    :param encoding: the mode of the encoding, or None for the X10 encoding.
    """
    if encoding == PrivateMode.MOUSE_SGR_MODE:
        return f"{ESC}[<{code};{col + 1};{row + 1}{'m' if release else 'M'}".encode("ascii")

    limit = _MOUSE_COORDINATE_LIMITS[encoding]
    # a coordinate past the limit is sent as the limit, and the limit as a NUL byte
    coordinates = (min(value, limit) for value in (col, row))
    values = [
        code + _MOUSE_BYTE_OFFSET,
        *(0 if value == limit else value + _MOUSE_COORD_OFFSET for value in coordinates),
    ]
    if encoding == PrivateMode.MOUSE_UTF8_MODE:
        # UTF-8 encoding: each value is a character, so one above 127 takes two bytes
        return f"{ESC}[M".encode("ascii") + "".join(map(chr, values)).encode("utf-8")
    return f"{ESC}[M".encode("ascii") + bytes(values)


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

        .. note::

            If your Terminal instance does not show Unicode glyphs correctly, urwid's encoding is not UTF-8.
            It is taken from the locale at start-up, and ``urwid.set_encoding("utf-8")`` sets it.
            See :ref:`text-encodings` for more details.
        """
        super().__init__()

        self.escape_sequence: str = escape_sequence or "ctrl a"

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
        """Return the cursor coordinates for this terminal."""
        if self.term is None:
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

        return (x, y)

    def spawn(self) -> None:
        """Fork the child process running :attr:`command` and connect it to a new pty."""
        env = self.env
        env["TERM"] = "linux"

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
        """Write every buffered response to the pty and clear the buffer."""
        for string in self.response_buffer:
            os.write(typing.cast("int", self.master), string.encode("ascii"))
        self.response_buffer = []

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
            self.term = TermCanvas(width, height, self)
        else:
            self.term.resize(width, height)
            if self.term.modes.in_band_resize:
                # Sent after the size the child reads on SIGWINCH is set, as a terminal sends it, and only when the pty
                # can take it now: this runs in render(), which a child that stopped reading must not block.
                # A dropped report loses nothing the child cannot read with TIOCGWINSZ.
                master = typing.cast("int", self.master)
                with selectors.DefaultSelector() as selector:
                    selector.register(master, selectors.EVENT_WRITE)
                    writable = bool(selector.select(0))
                if writable:
                    os.write(master, window_size_report(width, height).encode("ascii"))

        self.width = width
        self.height = height

        if process_opened:
            self.add_watch()

        self._emit("resize", (width, height))

    def set_title(self, title: str) -> None:
        """Emit a "title" signal with the terminal's new *title*."""
        self._emit("title", title)

    def change_focus(self, has_focus: bool) -> None:
        """Ignore SIGINT if this widget has focus."""
        if self.terminated:
            return

        focus_changed = has_focus != self.has_focus
        self.has_focus = has_focus

        if self.term is not None:
            self.term.has_focus = has_focus
            self.term.set_term_cursor()

        if not focus_changed:
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
        """Unregister the pty from the loop :meth:`add_watch` registered it on, when it did."""
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
            handed down to the parent outside a key grab, or the ``linux`` terminal type the child is given has no
            byte form for it, as for a cursor or function key with shift, meta or ctrl.
        """
        if self.terminated:
            return key

        grabbed = self.keygrab

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

        os.write(typing.cast("int", self.master), sent.encode(self.encoding, "ignore"))

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

        :returns: ``True`` when the child tracks the mouse, also for an event its tracking mode does not report.
            Such events are a drag under mode 1000, the release of a wheel button, and under X10 compatibility mode (9)
            anything but a press of buttons 1 to 3.
            ``False`` when the event is left to the parent, in these cases:

            - the child has exited;
            - the child does not track the mouse, or tracks it in highlight mode (1001), which is not implemented;
            - the view is scrolled back from the screen the child sees;
            - the event is not a press, a release or a drag.
        """
        modes = self.term_modes
        if (
            self.terminated
            or modes.mouse_tracking in _MOUSE_UNREPORTED_TRACKING_MODES
            or self.term is None
            or self.term.scrolling_up
        ):
            return False

        code = 0
        action = event
        for prefix, flag in _MOUSE_MODIFIERS:
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

        os.write(typing.cast("int", self.master), _mouse_report(code, col, row, release, modes.mouse_encoding))
        return True

    def _key_sequence(self, key: str) -> str | None:
        """Return the characters the child receives for *key*, or ``None`` when its terminal type has none.

        While the flags the child set with the kitty keyboard protocol change key reports, the keys are sent in that
        protocol, except for pasted text, which is sent as a legacy terminal sends it.
        """
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
        """Return the characters a ``linux`` terminal sends for *key*, or ``None`` when it has none."""
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
    name = key
    modifiers = 0
    for prefix, bits in _KEY_MODIFIER_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name.removeprefix(prefix)
            # urwid's "meta" is the modifier a terminal sends Alt as
            modifiers |= bits & ~KeyModifier.META
    all_keys = flags & KittyKeyboardFlag.ALL_KEYS

    if name in _KITTY_LETTER_KEYS:
        final = _KITTY_LETTER_KEYS[name]
        return f"{ESC}[1;{modifiers + 1:d}{final}" if modifiers else f"{ESC}[{final}"
    if name in _KITTY_TILDE_KEYS:
        number = _KITTY_TILDE_KEYS[name]
        return f"{ESC}[{number:d};{modifiers + 1:d}~" if modifiers else f"{ESC}[{number:d}~"

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
        return f"{ESC}[{key_field};{modifiers_field};{ord(text):d}u"
    if modifiers:
        return f"{ESC}[{key_field};{modifiers_field}u"
    return f"{ESC}[{key_field}u"
