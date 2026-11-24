# Urwid curses output wrapper.. the horror..
#    Copyright (C) 2004-2011  Ian Ward
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


"""Curses-based UI implementation."""

from __future__ import annotations

import curses
import errno
import math
import os
import sys
import time
import typing
from contextlib import suppress

from urwid import util

from . import escape
from .common import UNPRINTABLE_TRANS_TABLE, AttrSpec, BaseScreen, RealTerminal

if typing.TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import Literal

    from urwid import Canvas

    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _PrivateModeReport = tuple[typing.Literal["private mode report"], str, int]
    _KeyboardProtocolReport = tuple[typing.Literal["keyboard protocol report"], int]
    _ModifyKeysReport = tuple[typing.Literal["modify keys report"], int, int | None]
    _DeviceAttributesReport = tuple[typing.Literal["device attributes"], tuple[int, ...]]
    _WindowSizeReport = tuple[typing.Literal["window size report"], int, int]
    _TerminalVersionReport = tuple[typing.Literal["terminal version"], str]
    _TerminalCapabilitiesReport = tuple[typing.Literal["terminal capabilities"], tuple[tuple[str, str | None], ...]]
    _DefaultColorReport = tuple[typing.Literal["default color"], int, str]
    _SettingReport = tuple[typing.Literal["setting report"], bool, str]
    _TerminalReport = (
        _PrivateModeReport
        | _KeyboardProtocolReport
        | _ModifyKeysReport
        | _DeviceAttributesReport
        | _WindowSizeReport
        | _TerminalVersionReport
        | _TerminalCapabilitiesReport
        | _DefaultColorReport
        | _SettingReport
    )
    _DecodedInput = list[str | _MouseInput | _CursorPosition]

IS_WINDOWS = sys.platform == "win32"
# the C standard output, which initscr() draws on whatever sys.stdout is
_CURSES_OUTPUT_FD: typing.Final = 1

# PyPy's curses has no constants for button 5 (wheel down): there its events are neither asked for nor reported
_BUTTON5_PRESSED: typing.Final[int] = getattr(curses, "BUTTON5_PRESSED", 0)
_BUTTON5_RELEASED: typing.Final[int] = getattr(curses, "BUTTON5_RELEASED", 0)
_BUTTON5_DOUBLE_CLICKED: typing.Final[int] = getattr(curses, "BUTTON5_DOUBLE_CLICKED", 0)
_BUTTON5_TRIPLE_CLICKED: typing.Final[int] = getattr(curses, "BUTTON5_TRIPLE_CLICKED", 0)

# curses.KEY_RESIZE (sometimes not defined)
if IS_WINDOWS:
    KEY_MOUSE = 539  # under Windows key mouse is different
    KEY_RESIZE = 546

    COLOR_CORRECTION: dict[int, int] = dict(
        enumerate(
            (
                curses.COLOR_BLACK,
                curses.COLOR_RED,
                curses.COLOR_GREEN,
                curses.COLOR_YELLOW,
                curses.COLOR_BLUE,
                curses.COLOR_MAGENTA,
                curses.COLOR_CYAN,
                curses.COLOR_WHITE,
            )
        )
    )

    def initscr() -> curses.window:
        """Initialize curses on Windows, copying the ``ACS_*``/``LINES``/``COLS`` attributes ``_curses`` misses."""
        import curses  # noqa: I001  # pylint: disable=redefined-outer-name,reimported  # special case for monkeypatch

        import _curses

        stdscr = _curses.initscr()
        for key, value in _curses.__dict__.items():
            if key.startswith("ACS_") or key in {"LINES", "COLS"}:
                setattr(curses, key, value)

        return stdscr

    curses.initscr = initscr

else:
    KEY_MOUSE = 409  # curses.KEY_MOUSE
    KEY_RESIZE = 410

    COLOR_CORRECTION = {}

_curses_colours = {  # pylint: disable=consider-using-namedtuple-or-dataclass  # historic test/debug data
    "default": (-1, 0),
    "black": (curses.COLOR_BLACK, 0),
    "dark red": (curses.COLOR_RED, 0),
    "dark green": (curses.COLOR_GREEN, 0),
    "brown": (curses.COLOR_YELLOW, 0),
    "dark blue": (curses.COLOR_BLUE, 0),
    "dark magenta": (curses.COLOR_MAGENTA, 0),
    "dark cyan": (curses.COLOR_CYAN, 0),
    "light gray": (curses.COLOR_WHITE, 0),
    "dark gray": (curses.COLOR_BLACK, 1),
    "light red": (curses.COLOR_RED, 1),
    "light green": (curses.COLOR_GREEN, 1),
    "yellow": (curses.COLOR_YELLOW, 1),
    "light blue": (curses.COLOR_BLUE, 1),
    "light magenta": (curses.COLOR_MAGENTA, 1),
    "light cyan": (curses.COLOR_CYAN, 1),
    "white": (curses.COLOR_WHITE, 1),
}


class Screen(BaseScreen, RealTerminal):
    """Screen backend that drives the real terminal through the ``curses`` module.

    Outside Windows, `start()` clears the ``IEXTEN`` and ``FLUSHO`` flags of a terminal input,
    as :class:`urwid.display.raw.Screen` does, and `stop()` restores them.
    """

    def __init__(self, *, in_band_resize: bool = False) -> None:
        """Initialize an unstarted curses screen with no color pairs allocated yet.

        :param in_band_resize: turn on the resize notifications the terminal sends in the input
            (DEC private mode 2048), and take the terminal size from them as well as from the resize curses reports;
            see :ref:`in-band-resize`.
            Only for a terminal known to support the mode, since it is not asked.
            The mode stays on while ncurses suspends the program,
            so a terminal resized then sends the notifications to the shell.
        """
        super().__init__()
        self._in_band_resize_requested = in_band_resize
        # this screen has mode 2048 on, so the window size reports in the input count
        self._in_band_resize = False
        self.curses_pairs = [(None, None)]  # Can't be sure what pair 0 will default to
        self.has_color = False
        self.has_default_colors = False
        self.s: curses.window | None = None
        self.cursor_state: typing.Literal["fixed"] | int | None = None
        self.prev_input_resize = 0
        # keys of a sequence cut short, kept for the next get_input()
        self._partial_keys: list[int] = []
        # per kept key, the raw codes it was read as, reported with the call that decodes it
        self._partial_raw: list[tuple[int, ...]] = []
        # time.monotonic() of the read that left them: get_input() decodes them as they are once no more of the sequence
        # arrived for complete_wait after it
        self._partial_read_time = 0.0
        # a resize read while keys were kept, reported after them once they are decoded
        self._resize_held = False
        self.set_input_timeouts()
        self.last_bstate = 0
        self._mouse_tracking_enabled = False
        self._curses_attr_cache: dict[AttrSpec, int] = {}
        # Holds the last drawn canvas so the canvas cache keeps its entries alive.
        self.keep_cache_alive_link: Canvas | None = None
        # The IEXTEN and FLUSHO bits that start() cleared on the terminal input, for stop() to set again.
        self._cleared_lflag = 0

        self.register_palette_entry(None, "default", "default")

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """
        Enable mouse tracking.

        After calling this function get_input will include mouse
        click events along with keystrokes.

        :raises NotImplementedError: *enable* is false while tracking is on; tracking cannot be turned off.
        """
        if enable == self._mouse_tracking_enabled:
            return

        if enable:
            curses.mousemask(
                0
                | curses.BUTTON1_PRESSED
                | curses.BUTTON1_RELEASED
                | curses.BUTTON2_PRESSED
                | curses.BUTTON2_RELEASED
                | curses.BUTTON3_PRESSED
                | curses.BUTTON3_RELEASED
                | curses.BUTTON4_PRESSED
                | curses.BUTTON4_RELEASED
                | _BUTTON5_PRESSED
                | _BUTTON5_RELEASED
                | curses.BUTTON1_DOUBLE_CLICKED
                | curses.BUTTON1_TRIPLE_CLICKED
                | curses.BUTTON2_DOUBLE_CLICKED
                | curses.BUTTON2_TRIPLE_CLICKED
                | curses.BUTTON3_DOUBLE_CLICKED
                | curses.BUTTON3_TRIPLE_CLICKED
                | curses.BUTTON4_DOUBLE_CLICKED
                | curses.BUTTON4_TRIPLE_CLICKED
                | _BUTTON5_DOUBLE_CLICKED
                | _BUTTON5_TRIPLE_CLICKED
                | curses.BUTTON_SHIFT
                | curses.BUTTON_ALT
                | curses.BUTTON_CTRL
            )
        else:
            raise NotImplementedError

        self._mouse_tracking_enabled = enable

    def _start(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        """Initialize the screen and input mode."""
        self.s = curses.initscr()
        self.has_color = curses.has_colors()
        if self.has_color:
            curses.start_color()
            if curses.COLORS < 8:
                # not colourful enough
                self.has_color = False
        if self.has_color:
            try:
                curses.use_default_colors()
                self.has_default_colors = True
            except curses.error:
                self.has_default_colors = False
        self._setup_colour_pairs()
        self._curses_attr_cache.clear()
        curses.noecho()
        curses.meta(True)
        curses.halfdelay(10)  # use set_input_timeouts to adjust
        self.s.keypad(False)

        if not IS_WINDOWS and os.isatty(fd := sys.stdin.fileno()):
            import termios
            import tty

            # cbreak mode leaves IEXTEN on, and with it the macOS and BSD drivers still act on ctrl v (VLNEXT),
            # ctrl o (VDISCARD, which toggles FLUSHO, and the driver drops every write while FLUSHO is set)
            # and ctrl y (VDSUSP).
            # FLUSHO is cleared too, because with IEXTEN off no ctrl o can clear it.
            mode = termios.tcgetattr(fd)
            self._cleared_lflag = mode[tty.LFLAG] & (termios.IEXTEN | termios.FLUSHO)
            mode[tty.LFLAG] &= ~self._cleared_lflag
            termios.tcsetattr(fd, termios.TCSANOW, mode)
            # cbreak() and halfdelay() in _getch() apply the mode curses saved last.
            # Curses has no mode to save when its output is no terminal, and then never changes stdin's.
            with suppress(curses.error):
                curses.def_prog_mode()

        # the reports arrive in the input, so both ends have to be the terminal
        if (
            self._in_band_resize_requested
            and not IS_WINDOWS
            and os.isatty(sys.stdin.fileno())
            and os.isatty(_CURSES_OUTPUT_FD)
        ):
            self._set_in_band_resize(True)

        if not self._signal_keys_set:
            self._old_signal_keys = self.tty_signal_keys()

        super()._start()

        if IS_WINDOWS:
            # halfdelay() seems unnecessary and causes everything to slow down a lot.
            curses.nocbreak()  # exits halfdelay mode
            # keypad(1) is needed, or we get no special keys (cursor keys, etc.)
            self.s.keypad(True)

    def _stop(self) -> None:
        """Restore the screen."""
        try:
            if self._in_band_resize:
                self._set_in_band_resize(False)
        except OSError as exc:
            # A hung-up terminal (EIO, or ENXIO on FreeBSD) or a closed output pipe (EPIPE) has nothing to restore,
            # and raising here would hide the error that ended the run.
            if exc.errno not in {errno.EIO, errno.ENXIO, errno.EPIPE}:
                raise
        finally:
            self._stop_curses()

    def _stop_curses(self) -> None:
        """Leave curses mode and restore the terminal settings and signal keys start() changed."""
        # A start that failed in initscr() left nothing to undo here, and these calls then raise "must call initscr()
        # first"; that error must not replace the one that ended the start.
        with suppress(curses.error):
            curses.echo()
            self._curs_set(1)
            curses.endwin()

        try:
            # endwin() restores the terminal curses writes to, which need not be stdin's.
            if self._cleared_lflag and os.isatty(fd := sys.stdin.fileno()):
                import termios
                import tty

                mode = termios.tcgetattr(fd)
                mode[tty.LFLAG] |= self._cleared_lflag
                termios.tcsetattr(fd, termios.TCSANOW, mode)
        finally:
            self._cleared_lflag = 0
            if self._old_signal_keys:
                self.tty_signal_keys(*self._old_signal_keys)
            super()._stop()

    @staticmethod
    def _write_terminal(data: str) -> None:
        """Write a control sequence curses has no call for to the terminal curses draws on."""
        encoded = data.encode("ascii")
        while encoded:
            encoded = encoded[os.write(_CURSES_OUTPUT_FD, encoded) :]

    def _set_in_band_resize(self, enable: bool) -> None:
        """Switch the terminal's in-band resize notifications (DEC private mode 2048) on or off."""
        mode = escape.PrivateMode.IN_BAND_RESIZE
        # before the write, which can fail on a terminal that hung up, so a stop still counts no report after it
        self._in_band_resize = enable
        self._write_terminal(mode.enable_seq if enable else mode.disable_seq)

    def _apply_terminal_reports(
        self,
        processed: list[str | _MouseInput | _CursorPosition | _TerminalReport],
        resize: bool,
    ) -> tuple[_DecodedInput, bool]:
        """Apply the window size reports among *processed* and strip out every terminal report.

        This screen sends no query.
        A query reply in the input therefore answers another program's query and is dropped.
        A window size report counts while this screen has mode 2048 on.
        When its size differs from the one curses has, curses takes it.
        The report becomes a ``"window resize"`` at its place among the keys
        when it changed the size, or when *resize* says curses reported a resize in the same read,
        which the terminal raised when it set the size it then sent.
        Any other report is dropped, so input that only looks like one cannot change the screen.

        :param resize: curses reported a resize in the keys *processed* was decoded from.
        :returns: the input left, and whether the resize curses reported is still to be added.
        """
        logger = self.logger.getChild("get_input")
        result: _DecodedInput = []
        for item in processed:
            match item:
                case ("window size report", int() as cols, int() as rows) if self._in_band_resize:
                    if self.get_cols_rows() != (cols, rows):
                        try:
                            # resize_term(), unlike resizeterm(), queues no KEY_RESIZE of its own
                            curses.resize_term(rows, cols)
                        except curses.error:
                            # a size too large for curses to allocate
                            logger.debug(f"Dropped a window size report curses could not apply: {item!r}")
                            continue
                    elif not resize:
                        continue
                    resize = False
                    if result[-1:] != ["window resize"]:
                        result.append("window resize")
                case ("window size report", *_):
                    logger.debug(f"Dropped a window size report this screen did not ask for: {item!r}")
                case (
                    "private mode report"
                    | "keyboard protocol report"
                    | "modify keys report"
                    | "device attributes"
                    | "terminal version"
                    | "terminal capabilities"
                    | "setting report"
                    | "default color",
                    *_,
                ):
                    logger.debug(f"Dropped a reply to a query this screen did not send: {item!r}")
                case _:
                    result.append(item)
        return result, resize

    def _setup_colour_pairs(self) -> None:
        """Initialize all 63 color pairs based on the term: bg * 8 + 7 - fg.

        So to get a color, we just need to use that term and get the right color pair number.
        """
        if not self.has_color:
            return

        if IS_WINDOWS:
            self.has_default_colors = False

        for fg in range(8):
            for bg in range(8):
                # leave out white on black
                if fg == curses.COLOR_WHITE and bg == curses.COLOR_BLACK:
                    continue

                curses.init_pair(bg * 8 + 7 - fg, COLOR_CORRECTION.get(fg, fg), COLOR_CORRECTION.get(bg, bg))

    def _curs_set(self, x: int) -> None:
        if self.cursor_state in {"fixed", x}:
            return
        try:
            curses.curs_set(x)
            self.cursor_state = x
        except curses.error:
            self.cursor_state = "fixed"

    def _getch(self, wait_tenths: int | None) -> int:
        if wait_tenths == 0:
            return self._getch_nodelay()

        self.s.nodelay(False)
        if not IS_WINDOWS:
            if wait_tenths is None:
                curses.cbreak()
            else:
                # halfdelay accepts at most 255 tenths; keep waiting after each
                # chunk expires, but return immediately when input arrives.
                while wait_tenths > 255:
                    curses.halfdelay(255)
                    key = self.s.getch()
                    if key != -1:
                        return key
                    wait_tenths -= 255
                curses.halfdelay(wait_tenths)

        return self.s.getch()

    def _getch_nodelay(self) -> int:
        self.s.nodelay(True)

        if not IS_WINDOWS:
            try:
                curses.cbreak()
            except curses.error:
                # it can fail once and work when called again, but once the terminal is gone it fails every time
                curses.cbreak()

        return self.s.getch()

    def set_input_timeouts(
        self,
        max_wait: float | None = None,
        complete_wait: float = 0.1,
        resize_wait: float = 0.1,
    ) -> None:
        """Set the get_input timeout values.

        All values have a granularity of 0.1s, ie. any value between 0.15 and 0.05 will be treated as
        0.1 and any value less than 0.05 will be treated as 0.  Waits
        longer than 25.5 seconds are split into multiple curses waits.

        :param max_wait: amount of time in seconds to wait for input when there is no input pending, wait forever if
            None
        :param complete_wait: amount of time in seconds to wait for the rest of an escape sequence cut short at the end
            of the available input, before get_input returns it decoded as it is.
            The wait never lasts past the end of *max_wait*: the sequence is then kept for the next get_input.
        :param resize_wait: amount of time in seconds to wait for more input after receiving two screen resize requests
            in a row to stop urwid from consuming 100% cpu during a gradual window resize operation.
            The wait never lasts past the end of *max_wait*.
        """

        def convert_to_tenths(s: float | None) -> int | None:
            if s is None:
                return None
            return int((s + 0.05) * 10)

        self.max_tenths = convert_to_tenths(max_wait)
        self.complete_tenths = convert_to_tenths(complete_wait)
        self.resize_tenths = convert_to_tenths(resize_wait)

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> _DecodedInput: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[_DecodedInput, list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> _DecodedInput | tuple[_DecodedInput, list[int]]:
        r"""Return pending input as a list.

        :param raw_keys: return raw keycodes as well as translated versions
        :raises RuntimeError: the screen has not been started.

        This function will immediately return all the input since the
        last time it was called.  If there is no input pending it will
        wait before returning an empty list.  The wait time may be
        configured with the set_input_timeouts function.

        A key that can begin a longer sequence, such as Esc, is kept until the rest of the sequence arrives
        or *complete_wait* is over, so the list can be empty before *max_wait* is over.

        If raw_keys is False (default) this function will return a list
        of keys pressed.  If raw_keys is True this function will return
        a ( keys pressed, raw keycodes ) tuple instead.

        Examples of keys returned:

        * ASCII printable characters:  :kbd:`space`, :kbd:`a`, :kbd:`0`, :kbd:`A`, :kbd:`-`, :kbd:`/`
        * ASCII control characters:  :kbd:`tab`, :kbd:`enter`
        * Escape sequences:  :kbd:`up`, :kbd:`page up`, :kbd:`home`, :kbd:`insert`, :kbd:`f1`
        * Key combinations:  :kbd:`shift f1`, :kbd:`meta a`, :kbd:`ctrl b`
        * Window events:  ``"window resize"``

        Other characters, decoded from the terminal encoding (UTF-8, or a single- or double-byte encoding):

        * Unicode characters: "\u00a5", "\u253c", "\u4e2d"

        Examples of mouse events returned:

        * Mouse button press: ('mouse press', 1, 15, 13),
                            ('meta mouse press', 2, 17, 23)
        * Mouse button release: ('mouse release', 1, 18, 13),
                              ('ctrl mouse release', 2, 17, 23)

        The button number is a :class:`~urwid.MouseButton` value.
        """
        if not self._started:
            raise RuntimeError

        now = time.monotonic()
        # counted with the complete_wait in effect now, which set_input_timeouts() may have changed since the read;
        # None waits forever
        complete_wait = math.inf if self.complete_tenths is None else self.complete_tenths / 10
        partial_deadline = self._partial_read_time + complete_wait
        # The waits for more input after a resize end by the time max_wait would have ended.
        deadline = None if self.max_tenths is None else now + self.max_tenths / 10
        partial = self._partial_keys
        expired_keys: _DecodedInput = []
        expired_raw: list[int] = []
        wait_tenths = self.max_tenths
        if partial and now >= partial_deadline:
            # Its deadline passed before this call: it is decoded alone, ahead of the keys that came since.
            self._partial_keys = []
            expired_raw = [code for codes in self._partial_raw for code in codes]
            self._partial_raw = []
            decoded = escape.decode_input(partial, more_available=False)[0]
            expired_keys, held = self._apply_terminal_reports(decoded, self._resize_held)
            self._resize_held = False
            if held:
                expired_keys.append("window resize")
            wait_tenths = 0
        elif partial and math.isfinite(partial_deadline):
            # The rest of a sequence cut short is waited for only until its deadline.
            # Rounded up, as a wait of 0 tenths would return before it and the caller would poll until then.
            left_tenths = max(0, math.ceil((partial_deadline - now) * 10))
            wait_tenths = left_tenths if wait_tenths is None else min(wait_tenths, left_tenths)
        keys, raw = self._get_input(wait_tenths)
        keys = [*expired_keys, *keys]
        raw = [*expired_raw, *raw]

        # Avoid pegging CPU at 100% when slowly resizing, and work
        # around a bug with some braindead curses implementations that
        # return "no key" between "window resize" commands;
        # not while a sequence cut short waits for its rest
        if keys == ["window resize"] and self.prev_input_resize and not self._partial_keys:
            for _ in range(2):
                wait_tenths = self.resize_tenths
                if deadline is not None:
                    # rounded to the nearest tenth, as set_input_timeouts() rounds max_wait
                    left_tenths = max(0, int((deadline - time.monotonic() + 0.05) * 10))
                    wait_tenths = left_tenths if wait_tenths is None else min(wait_tenths, left_tenths)
                new_keys, new_raw = self._get_input(wait_tenths)
                raw += new_raw
                if new_keys and new_keys != ["window resize"]:
                    if "window resize" in new_keys:
                        keys = new_keys
                    else:
                        keys.extend(new_keys)
                    break

        if keys == ["window resize"]:
            self.prev_input_resize = 2
        elif self.prev_input_resize == 2 and not keys:
            self.prev_input_resize = 1
        else:
            self.prev_input_resize = 0

        if raw_keys:
            return keys, raw
        return keys

    def _get_input(self, wait_tenths: int | None) -> tuple[_DecodedInput, list[int]]:
        # this works around a strange curses bug with window resizing
        # not being reported correctly with repeated calls to this
        # function without a doupdate call in between
        curses.doupdate()

        key = self._getch(wait_tenths)
        resize = False
        partial = self._partial_keys
        keys = [*partial]
        # per key, the raw codes it was read as: a mouse report's code goes with its first key
        keys_raw = [*self._partial_raw]
        # raw codes that are no key, such as a resize, are reported with this call
        other_raw: list[int] = []

        while key >= 0:
            if key == KEY_RESIZE:
                resize = True
                other_raw.append(key)
            elif key == KEY_MOUSE:
                if mouse_keys := self._encode_mouse_event():
                    keys += mouse_keys
                    keys_raw += [(key,), *[()] * (len(mouse_keys) - 1)]
                else:
                    other_raw.append(key)
            else:
                keys.append(key)
                keys_raw.append((key,))
            key = self._getch_nodelay()

        read_new = len(keys) > len(partial)
        # a sequence cut short, with no more of it by its deadline, is decoded as it is
        complete_wait = math.inf if self.complete_tenths is None else self.complete_tenths / 10
        expired = bool(partial) and not read_new and time.monotonic() >= self._partial_read_time + complete_wait
        processed, consumed = escape.decode_input(keys, more_available=not expired)
        self._partial_keys = keys[consumed:]
        # each read that leaves a sequence cut short gives it complete_wait to arrive whole
        if self._partial_keys and read_new:
            self._partial_read_time = time.monotonic()

        if self._partial_keys and (resize or self._resize_held) and self.complete_tenths is None:
            # With no deadline for the rest of the sequence, a resize ends the wait, so it is not held for good.
            processed += escape.decode_input(self._partial_keys, more_available=False)[0]
            self._partial_keys = []
            consumed = len(keys)
        self._partial_raw = keys_raw[consumed:]
        raw = [*(code for codes in keys_raw[:consumed] for code in codes), *other_raw]

        if self._partial_keys:
            # a resize read after keys still kept is reported once they are decoded, after them
            self._resize_held = self._resize_held or resize
            resize = False
        elif self._resize_held:
            resize = True
            self._resize_held = False

        result, resize = self._apply_terminal_reports(processed, resize)

        if resize:
            result.append("window resize")

        return result, raw

    def _encode_mouse_event(self) -> list[int]:
        """Encode the pending curses mouse event as X10 mouse reports.

        :returns: the codes of the reports, empty when ncurses has no event in its queue.
        """
        last_state = next_state = self.last_bstate
        try:
            (_id, x, y, _z, bstate) = curses.getmouse()
        except curses.error:
            # ncurses returns KEY_MOUSE also when its queue holds no event matching the mask,
            # e.g. for every pointer move on the FreeBSD syscons console, and getmouse() then fails.
            return []

        mod = 0
        if bstate & curses.BUTTON_SHIFT:
            mod |= 4
        if bstate & curses.BUTTON_ALT:
            mod |= 8
        if bstate & curses.BUTTON_CTRL:
            mod |= 16

        result = []

        def append_button(b: int) -> None:
            b |= mod
            result.extend([27, ord("["), ord("M"), b + 32, x + 33, y + 33])

        if bstate & curses.BUTTON1_PRESSED and last_state & 1 == 0:
            append_button(0)
            next_state |= 1
        if bstate & curses.BUTTON2_PRESSED and last_state & 2 == 0:
            append_button(1)
            next_state |= 2
        if bstate & curses.BUTTON3_PRESSED and last_state & 4 == 0:
            append_button(2)
            next_state |= 4
        if bstate & curses.BUTTON4_PRESSED and last_state & 8 == 0:
            append_button(64)
            next_state |= 8
        if bstate & _BUTTON5_PRESSED and last_state & 16 == 0:
            append_button(65)
            next_state |= 16
        if bstate & curses.BUTTON1_RELEASED and last_state & 1:
            append_button(0 + escape.MOUSE_RELEASE_FLAG)
            next_state &= ~1
        if bstate & curses.BUTTON2_RELEASED and last_state & 2:
            append_button(1 + escape.MOUSE_RELEASE_FLAG)
            next_state &= ~2
        if bstate & curses.BUTTON3_RELEASED and last_state & 4:
            append_button(2 + escape.MOUSE_RELEASE_FLAG)
            next_state &= ~4
        if bstate & curses.BUTTON4_RELEASED and last_state & 8:
            append_button(64 + escape.MOUSE_RELEASE_FLAG)
            next_state &= ~8
        if bstate & _BUTTON5_RELEASED and last_state & 16:
            append_button(65 + escape.MOUSE_RELEASE_FLAG)
            next_state &= ~16

        if bstate & curses.BUTTON1_DOUBLE_CLICKED:
            append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON2_DOUBLE_CLICKED:
            append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON3_DOUBLE_CLICKED:
            append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON4_DOUBLE_CLICKED:
            append_button(64 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & _BUTTON5_DOUBLE_CLICKED:
            append_button(65 + escape.MOUSE_MULTIPLE_CLICK_FLAG)

        if bstate & curses.BUTTON1_TRIPLE_CLICKED:
            append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON2_TRIPLE_CLICKED:
            append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON3_TRIPLE_CLICKED:
            append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON4_TRIPLE_CLICKED:
            append_button(64 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & _BUTTON5_TRIPLE_CLICKED:
            append_button(65 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)

        self.last_bstate = next_state
        return result

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows)."""
        rows, cols = self.s.getmaxyx()
        return cols, rows

    def _setattr(self, a: Hashable) -> None:
        # curses cannot draw hyperlinks, so attributes differing only by one share a cache entry;
        # it draws the 8 colors of the pairs _setup_colour_pairs() initialised
        a = self._drawn_attr(a, 0, 8 if self.has_color else 1).style_only()

        try:
            attr = self._curses_attr_cache[a]
        except KeyError:
            attr = self._curses_attr_cache[a] = self._compute_curses_attr(a)

        self.s.attrset(attr)

    def _compute_curses_attr(self, a: AttrSpec) -> int:
        if self.has_color:
            # a converted attribute holds the basic colors 0-7 only
            fg = a.foreground_number if a.foreground_basic else 7
            bg = a.background_number if a.background_basic else 0

            attr = curses.color_pair(bg * 8 + 7 - fg)
        else:
            attr = 0

        if a.bold:
            attr |= curses.A_BOLD
        if a.standout:
            attr |= curses.A_STANDOUT
        if a.underline:
            attr |= curses.A_UNDERLINE
        if a.blink:
            attr |= curses.A_BLINK
        if a.faint:
            attr |= curses.A_DIM

        return attr

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Paint screen with rendered canvas.

        :raises RuntimeError: the screen has not been started.
        :raises ValueError: *canvas* does not match *size*, or a run carries an unknown character set.
        :raises TypeError: a text run is not a byte string.
        """
        logger = self.logger.getChild("draw_screen")

        if not self._started:
            raise RuntimeError

        _cols, rows = size

        if canvas.rows() != rows:
            raise ValueError("canvas size and passed size don't match")

        logger.debug(f"Drawing screen with size {size!r}")

        for y, row in enumerate(canvas.content()):
            try:
                self.s.move(y, 0)
            except curses.error:
                # terminal shrunk?
                # move failed so stop drawing rows, but still flush what
                # was already drawn instead of leaving a stale screen.
                break

            first = True
            lasta = None

            aborted = False
            for nr, (a, cs, seg) in enumerate(row):
                if not isinstance(seg, bytes):  # canvases render with bytes
                    raise TypeError(seg)
                if cs != "U":
                    seg = seg.translate(UNPRINTABLE_TRANS_TABLE)  # noqa: PLW2901

                if first or lasta != a:
                    self._setattr(a)
                    lasta = a
                try:
                    if cs in {"0", "U"}:
                        for segment in seg:
                            self.s.addch(0x400000 + segment)
                    else:
                        if cs is not None:
                            raise ValueError(f"cs not in ('0', 'U' ,'None'): {cs!r}")
                        self.s.addstr(seg.decode(util.get_encoding(), "replace"))
                except curses.error:
                    # it's OK to get out of the
                    # screen on the lower right
                    if y != rows - 1 or nr != len(row) - 1:
                        # perhaps screen size changed
                        # quietly abort, but still flush what was already drawn.
                        aborted = True
                    break
            if aborted:
                break

        else:
            if canvas.cursor is not None:
                x, y = canvas.cursor
                self._curs_set(1)
                with suppress(curses.error):
                    self.s.move(y, x)
            else:
                self._curs_set(0)
                self.s.move(0, 0)

        self.s.refresh()
        self.keep_cache_alive_link = canvas

    def clear(self) -> None:
        """Force the screen to be completely repainted on the next call to draw_screen()."""
        self.s.clear()


class _test:
    def __init__(self) -> None:
        self.ui = Screen()
        self.l = sorted(_curses_colours)

        for c in self.l:
            self.ui.register_palette(
                [
                    (f"{c} on black", c, "black", "underline"),
                    (f"{c} on dark blue", c, "dark blue", "bold"),
                    (f"{c} on light gray", c, "light gray", "standout"),
                ]
            )

        with self.ui.start():
            self.run()

    def run(self) -> None:
        """Render a palette demo screen showing every registered color combination."""
        from urwid.canvas import TextCanvas

        encoding = util.get_encoding()

        text = [f"  has_color = {self.ui.has_color!r}", ""]
        attr: list[list[tuple[Hashable, int]]] = [[], []]

        for c in self.l:
            t = ""
            a: list[tuple[Hashable, int]] = []
            for p in f"{c} on black", f"{c} on dark blue", f"{c} on light gray":
                a.append((p, 27))
                t += (p + 27 * " ")[:27]
            text.append(t)
            attr.append(a)

        text += ["", "return values from get_input(): (q exits)", ""]
        attr += [[], [], []]
        cols, rows = self.ui.get_cols_rows()
        keys = None
        while keys != ["q"]:
            r = TextCanvas(
                text=([t.encode(encoding, "replace").ljust(cols) for t in text] + [b""] * rows)[:rows],
                attr=(attr + [[] for _ in range(rows)])[:rows],
            )
            self.ui.draw_screen((cols, rows), r)
            keys, raw = self.ui.get_input(raw_keys=True)
            if "window resize" in keys:
                cols, rows = self.ui.get_cols_rows()
            if not keys:
                continue
            t = ""
            a = []
            for k in keys:
                shown = k if isinstance(k, str) else repr(k)
                t += f"'{shown}' "
                # canvas attribute runs are measured in bytes of the encoded text
                a += [(None, 1), ("yellow on dark blue", len(shown.encode(encoding, "replace"))), (None, 2)]

            text.append(f"{t}: {raw!r}")
            attr.append(a)
            text = text[-rows:]
            attr = attr[-rows:]


if __name__ == "__main__":
    _test()
