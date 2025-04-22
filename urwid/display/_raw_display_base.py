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

import abc
import contextlib
import functools
import os
import platform
import selectors
import signal
import socket
import sys
import typing

from urwid import signals, str_util, util

from . import escape
from .common import UNPRINTABLE_TRANS_TABLE, UPDATE_PALETTE_ENTRY, AttrSpec, BaseScreen, RealTerminal

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import FrameType

    from typing_extensions import Literal

    from urwid import Canvas, EventLoop

IS_WINDOWS = sys.platform == "win32"
IS_WSL = (sys.platform == "linux") and ("wsl" in platform.platform().lower())


class Screen(BaseScreen, RealTerminal):
    def __init__(self, input: typing.IO, output: typing.IO) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """Initialize a screen that directly prints escape codes to an output
        terminal.
        """
        super().__init__()

        self._partial_codes: list[int] = []
        self._pal_escape: dict[str | None, str] = {}
        self._pal_attrspec: dict[str | None, AttrSpec] = {}
        self._alternate_buffer: bool = False
        signals.connect_signal(self, UPDATE_PALETTE_ENTRY, self._on_update_palette_entry)
        self.colors: Literal[1, 16, 88, 256, 16777216] = 16  # FIXME: detect this
        self.has_underline = True  # FIXME: detect this
        self.prev_input_resize = 0
        self.set_input_timeouts()
        self.screen_buf = None
        self._screen_buf_canvas = None
        self._resized = False
        self.maxrow = None
        self._mouse_tracking_enabled = False
        self.last_bstate = 0
        self._setup_G1_done = False
        self._rows_used = None
        self._cy = 0
        self.term = os.environ.get("TERM", "")
        self.fg_bright_is_bold = not self.term.startswith("xterm")
        self.bg_bright_is_blink = self.term == "linux"
        self.back_color_erase = not self.term.startswith("screen")
        self.register_palette_entry(None, "default", "default")
        self._next_timeout = None
        self.signal_handler_setter = signal.signal

        # Our connections to the world
        self._term_output_file = output
        self._term_input_file = input

        # pipe for signalling external event loops about resize events
        self._resize_pipe_rd, self._resize_pipe_wr = socket.socketpair()
        self._resize_pipe_rd.setblocking(False)

    def __del__(self) -> None:
        self._resize_pipe_rd.close()
        self._resize_pipe_wr.close()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(input={self._term_input_file}, output={self._term_output_file})>"

    def _sigwinch_handler(self, signum: int = 28, frame: FrameType | None = None) -> None:
        """
        frame -- will always be None when the GLib event loop is being used.
        """
        logger = self.logger.getChild("signal_handlers")

        logger.debug(f"SIGWINCH handler called with signum={signum!r}, frame={frame!r}")

        if IS_WINDOWS or not self._resized:
            self._resize_pipe_wr.send(b"R")
            logger.debug("Sent fake resize input to the pipe")
        self._resized = True
        self.screen_buf = None

    @property
    def _term_input_io(self) -> typing.IO | None:
        if hasattr(self._term_input_file, "fileno"):
            return self._term_input_file
        return None

    def _input_fileno(self) -> int | None:
        """Returns the fileno of the input stream, or None if it doesn't have one.

        A stream without a fileno can't participate in whatever.
        """
        if hasattr(self._term_input_file, "fileno"):
            return self._term_input_file.fileno()

        return None

    def _on_update_palette_entry(self, name: str | None, *attrspecs: AttrSpec):
        # copy the attribute to a dictionary containing the escape seqences
        a: AttrSpec = attrspecs[{16: 0, 1: 1, 88: 2, 256: 3, 2**24: 4}[self.colors]]
        self._pal_attrspec[name] = a
        self._pal_escape[name] = self._attrspec_to_escape(a)

    def set_input_timeouts(
        self,
        max_wait: float | None = None,
        complete_wait: float = 0.125,
        resize_wait: float = 0.125,
    ) -> None:
        """
        Set the get_input timeout values.  All values are in floating
        point numbers of seconds.

        max_wait -- amount of time in seconds to wait for input when
            there is no input pending, wait forever if None
        complete_wait -- amount of time in seconds to wait when
            get_input detects an incomplete escape sequence at the
            end of the available input
        resize_wait -- amount of time in seconds to wait for more input
            after receiving two screen resize requests in a row to
            stop Urwid from consuming 100% cpu during a gradual
            window resize operation
        """
        self.max_wait = max_wait
        if max_wait is not None:
            if self._next_timeout is None:
                self._next_timeout = max_wait
            else:
                self._next_timeout = min(self._next_timeout, self.max_wait)
        self.complete_wait = complete_wait
        self.resize_wait = resize_wait

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """
        Enable (or disable) mouse tracking.

        After calling this function get_input will include mouse
        click events along with keystrokes.
        """
        enable = bool(enable)
        if enable == self._mouse_tracking_enabled:
            return

        self._mouse_tracking(enable)
        self._mouse_tracking_enabled = enable

    def _mouse_tracking(self, enable: bool) -> None:
        if enable:
            self.write(escape.MOUSE_TRACKING_ON)
        else:
            self.write(escape.MOUSE_TRACKING_OFF)

    @abc.abstractmethod
    def _start(self, alternate_buffer: bool = True) -> None:
        """
        Initialize the screen and input mode.

        alternate_buffer -- use alternate screen buffer
        """

    def _stop_mouse_restore_buffer(self) -> None:
        """Stop mouse tracking and restore the screen."""
        self._mouse_tracking(False)

        move_cursor = ""
        if self._alternate_buffer:
            move_cursor = escape.RESTORE_NORMAL_BUFFER
        elif self.maxrow is not None:
            move_cursor = escape.set_cursor_position(0, self.maxrow)
        self.write(self._attrspec_to_escape(AttrSpec("", "")) + escape.SI + move_cursor + escape.SHOW_CURSOR)
        self.flush()

    @abc.abstractmethod
    def _stop(self) -> None:
        """
        Restore the screen.
        """

    def write(self, data):
        """Write some data to the terminal.

        You may wish to override this if you're using something other than
        regular files for input and output.
        """
        self._term_output_file.write(data)

    def flush(self):
        """Flush the output buffer.

        You may wish to override this if you're using something other than
        regular files for input and output.
        """
        self._term_output_file.flush()

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> list[str]: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[list[str], list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> list[str] | tuple[list[str], list[int]]:
        """Return pending input as a list.

        raw_keys -- return raw keycodes as well as translated versions

        This function will immediately return all the input since the
        last time it was called.  If there is no input pending it will
        wait before returning an empty list.  The wait time may be
        configured with the set_input_timeouts function.

        If raw_keys is False (default) this function will return a list
        of keys pressed.  If raw_keys is True this function will return
        a ( keys pressed, raw keycodes ) tuple instead.

        Examples of keys returned:

        * ASCII printable characters:  " ", "a", "0", "A", "-", "/"
        * ASCII control characters:  "tab", "enter"
        * Escape sequences:  "up", "page up", "home", "insert", "f1"
        * Key combinations:  "shift f1", "meta a", "ctrl b"
        * Window events:  "window resize"

        When a narrow encoding is not enabled:

        * "Extended ASCII" characters:  "\\xa1", "\\xb2", "\\xfe"

        When a wide encoding is enabled:

        * Double-byte characters:  "\\xa1\\xea", "\\xb2\\xd4"

        When utf8 encoding is enabled:

        * Unicode characters: u"\\u00a5", u'\\u253c"

        Examples of mouse events returned:

        * Mouse button press: ('mouse press', 1, 15, 13),
                              ('meta mouse press', 2, 17, 23)
        * Mouse drag: ('mouse drag', 1, 16, 13),
                      ('mouse drag', 1, 17, 13),
                      ('ctrl mouse drag', 1, 18, 13)
        * Mouse button release: ('mouse release', 0, 18, 13),
                                ('ctrl mouse release', 0, 17, 23)
        """
        logger = self.logger.getChild("get_input")
        if not self._started:
            raise RuntimeError

        self._wait_for_input_ready(self._next_timeout)
        keys, raw = self.parse_input(None, None, self.get_available_raw_input())

        # Avoid pegging CPU at 100% when slowly resizing
        if keys == ["window resize"] and self.prev_input_resize:
            logger.debug('get_input: got "window resize" > 1 times. Enable throttling for resize.')
            for _ in range(2):
                self._wait_for_input_ready(self.resize_wait)
                new_keys, new_raw = self.parse_input(None, None, self.get_available_raw_input())
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

        fd_list: list[socket.socket | typing.IO | int] = [self._resize_pipe_rd]

        if (input_io := self._term_input_io) is not None:
            fd_list.append(input_io)
        return fd_list

    _current_event_loop_handles = ()

    @abc.abstractmethod
    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """
        Remove any hooks added by hook_event_loop.
        """

    @abc.abstractmethod
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

    _input_timeout = None

    def _make_legacy_input_wrapper(self, event_loop, callback):
        """
        Support old Screen classes that still have a get_input_nonblocking and expect it to work.
        """

        @functools.wraps(callback)
        def wrapper():
            if self._input_timeout:
                event_loop.remove_alarm(self._input_timeout)
                self._input_timeout = None
            timeout, keys, raw = self.get_input_nonblocking()  # pylint: disable=no-member  # should we deprecate?
            if timeout is not None:
                self._input_timeout = event_loop.alarm(timeout, wrapper)

            callback(keys, raw)

        return wrapper

    def _get_input_codes(self) -> list[int]:
        return list(self._get_keyboard_codes())

    def get_available_raw_input(self) -> list[int]:
        """
        Return any currently available input. Does not block.

        This method is only used by the default `hook_event_loop`
        implementation; you can safely ignore it if you implement your own.
        """
        logger = self.logger.getChild("get_available_raw_input")
        codes = [*self._partial_codes, *self._get_input_codes()]
        self._partial_codes = []

        # clean out the pipe used to signal external event loops
        # that a resize has occurred
        with selectors.DefaultSelector() as selector:
            selector.register(self._resize_pipe_rd, selectors.EVENT_READ)
            present_resize_flag = selector.select(0)  # nonblocking
            while present_resize_flag:
                logger.debug("Resize signal received. Cleaning socket.")
                # Argument "size" is maximum buffer size to read. Since we're emptying, set it reasonably big.
                self._resize_pipe_rd.recv(128)
                present_resize_flag = selector.select(0)

        return codes

    @typing.overload
    def parse_input(
        self,
        event_loop: None,
        callback: None,
        codes: list[int],
        wait_for_more: bool = ...,
    ) -> tuple[list[str], list[int]]: ...

    @typing.overload
    def parse_input(
        self,
        event_loop: EventLoop,
        callback: None,
        codes: list[int],
        wait_for_more: bool = ...,
    ) -> tuple[list[str], list[int]]: ...

    @typing.overload
    def parse_input(
        self,
        event_loop: EventLoop,
        callback: Callable[[list[str], list[int]], typing.Any],
        codes: list[int],
        wait_for_more: bool = ...,
    ) -> None: ...

    def parse_input(
        self,
        event_loop: EventLoop | None,
        callback: Callable[[list[str], list[int]], typing.Any] | None,
        codes: list[int],
        wait_for_more: bool = True,
    ) -> tuple[list[str], list[int]] | None:
        """
        Read any available input from get_available_raw_input, parses it into
        keys, and calls the given callback.

        The current implementation tries to avoid any assumptions about what
        the screen or event loop look like; it only deals with parsing keycodes
        and setting a timeout when an incomplete one is detected.

        `codes` should be a sequence of keycodes, i.e. bytes.  A bytearray is
        appropriate, but beware of using bytes, which only iterates as integers
        on Python 3.
        """

        logger = self.logger.getChild("parse_input")

        # Note: event_loop may be None for 100% synchronous support, only used
        # by get_input.  Not documented because you shouldn't be doing it.
        if self._input_timeout and event_loop:
            event_loop.remove_alarm(self._input_timeout)
            self._input_timeout = None

        original_codes = codes
        decoded_codes = []
        try:
            while codes:
                run, codes = escape.process_keyqueue(codes, wait_for_more)
                decoded_codes.extend(run)
        except escape.MoreInputRequired:
            # Set a timer to wait for the rest of the input; if it goes off
            # without any new input having come in, use the partial input
            k = len(original_codes) - len(codes)
            raw_codes = original_codes[:k]
            self._partial_codes = codes

            def _parse_incomplete_input():
                self._input_timeout = None
                self._partial_codes = []
                self.parse_input(event_loop, callback, codes, wait_for_more=False)

            if event_loop:
                self._input_timeout = event_loop.alarm(self.complete_wait, _parse_incomplete_input)

        else:
            raw_codes = original_codes
            self._partial_codes = []

        logger.debug(f"Decoded codes: {decoded_codes!r}, raw codes: {raw_codes!r}")

        if self._resized:
            decoded_codes.append("window resize")
            logger.debug('Added "window resize" to the codes')
            self._resized = False

        if callback:
            callback(decoded_codes, raw_codes)
            return None

        # For get_input
        return decoded_codes, raw_codes

    def _wait_for_input_ready(self, timeout: float | None) -> list[int]:
        logger = self.logger.getChild("wait_for_input_ready")
        fd_list = self.get_input_descriptors()

        logger.debug(f"Waiting for input: descriptors={fd_list!r}, timeout={timeout!r}")
        with selectors.DefaultSelector() as selector:
            for fd in fd_list:
                selector.register(fd, selectors.EVENT_READ)

            ready = selector.select(timeout)

        logger.debug(f"Input ready: {ready}")

        return [event.fd for event, _ in ready]

    @abc.abstractmethod
    def _read_raw_input(self, timeout: int) -> Iterable[int]: ...

    def _get_keyboard_codes(self) -> Iterable[int]:
        return self._read_raw_input(0)

    def _setup_G1(self) -> None:
        """
        Initialize the G1 character set to graphics mode if required.
        """
        if self._setup_G1_done:
            return

        while True:
            with contextlib.suppress(OSError):
                self.write(escape.DESIGNATE_G1_SPECIAL)
                self.flush()
                break
        self._setup_G1_done = True

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Paint screen with rendered canvas."""

        def set_cursor_home() -> str:
            if not partial_display():
                return escape.set_cursor_position(0, 0)
            return escape.CURSOR_HOME_COL + escape.move_cursor_up(cy)

        def set_cursor_position(x: int, y: int) -> str:
            if not partial_display():
                return escape.set_cursor_position(x, y)
            if cy > y:
                return "\b" + escape.CURSOR_HOME_COL + escape.move_cursor_up(cy - y) + escape.move_cursor_right(x)
            return "\b" + escape.CURSOR_HOME_COL + escape.move_cursor_down(y - cy) + escape.move_cursor_right(x)

        def is_blank_row(row: list[tuple[object, Literal["0", "U"] | None], bytes]) -> bool:
            if len(row) > 1:
                return False
            return not row[0][2].strip()

        def attr_to_escape(a: AttrSpec | str | None) -> str:
            if a in self._pal_escape:
                return self._pal_escape[a]
            if isinstance(a, AttrSpec):
                return self._attrspec_to_escape(a)
            if a is None:
                return self._attrspec_to_escape(AttrSpec("default", "default"))
            # undefined attributes use default/default
            self.logger.debug(f"Undefined attribute: {a!r}")
            return self._attrspec_to_escape(AttrSpec("default", "default"))

        def using_standout_or_underline(a: AttrSpec | str) -> bool:
            a = self._pal_attrspec.get(a, a)
            return isinstance(a, AttrSpec) and (a.standout or a.underline)

        encoding = util.get_encoding()

        logger = self.logger.getChild("draw_screen")

        (maxcol, maxrow) = size

        if not self._started:
            raise RuntimeError

        if maxrow != canvas.rows():
            raise ValueError(maxrow)

        # quick return if nothing has changed
        if self.screen_buf and canvas is self._screen_buf_canvas:
            return

        self._setup_G1()

        if self._resized:
            # handle resize before trying to draw screen
            logger.debug("Not drawing screen: screen resized and resize was not handled")
            return

        logger.debug(f"Drawing screen with size {size!r}")

        last_attributes = None  # Default = empty

        output: list[str] = [escape.HIDE_CURSOR, attr_to_escape(last_attributes)]

        def partial_display() -> bool:
            # returns True if the screen is in partial display mode ie. only some rows belong to the display
            return self._rows_used is not None

        if not partial_display():
            output.append(escape.CURSOR_HOME)

        if self.screen_buf:
            osb = self.screen_buf
        else:
            osb = []
        sb: list[list[tuple[object, Literal["0", "U"] | None, bytes]]] = []
        cy = self._cy
        y = -1

        ins = None
        output.append(set_cursor_home())
        cy = 0

        first = True
        last_charset_flag = None

        for row in canvas.content():
            y += 1
            if osb and y < len(osb) and osb[y] == row:
                # this row of the screen buffer matches what is
                # currently displayed, so we can skip this line
                sb.append(osb[y])
                continue

            sb.append(row)

            # leave blank lines off display when we are using
            # the default screen buffer (allows partial screen)
            if partial_display() and y > self._rows_used:
                if is_blank_row(row):
                    continue
                self._rows_used = y

            if y or partial_display():
                output.append(set_cursor_position(0, y))
            # after updating the line we will be just over the
            # edge, but terminals still treat this as being
            # on the same line
            cy = y

            whitespace_at_end = False
            if row:
                a, cs, run = row[-1]
                if run[-1:] == b" " and self.back_color_erase and not using_standout_or_underline(a):
                    whitespace_at_end = True
                    row = [*row[:-1], (a, cs, run.rstrip(b" "))]  # noqa: PLW2901
                elif y == maxrow - 1 and maxcol > 1:
                    row, back, ins = self._last_row(row)  # noqa: PLW2901

            for a, cs, run in row:
                if not isinstance(run, bytes):  # canvases render with bytes
                    raise TypeError(run)

                if cs != "U":
                    run = run.translate(UNPRINTABLE_TRANS_TABLE)  # noqa: PLW2901

                if last_attributes != a:
                    output.append(attr_to_escape(a))
                    last_attributes = a

                if encoding != "utf-8" and (first or last_charset_flag != cs):
                    if cs not in {None, "0", "U"}:
                        raise ValueError(cs)
                    if last_charset_flag == "U":
                        output.append(escape.IBMPC_OFF)

                    if cs is None:
                        output.append(escape.SI)
                    elif cs == "U":
                        output.append(escape.IBMPC_ON)
                    else:
                        output.append(escape.SO)
                    last_charset_flag = cs

                output.append(run.decode(encoding, "replace"))
                first = False

            if ins:
                (inserta, insertcs, inserttext) = ins
                ias = attr_to_escape(inserta)
                if insertcs not in {None, "0", "U"}:
                    raise ValueError(insertcs)

                if isinstance(inserttext, bytes):
                    inserttext = inserttext.decode(encoding)

                output.extend(("\x08" * back, ias))  # pylint: disable=used-before-assignment  # defined in `if row`

                if encoding != "utf-8":
                    if cs is None:
                        icss = escape.SI
                    elif cs == "U":
                        icss = escape.IBMPC_ON
                    else:
                        icss = escape.SO

                    output.append(icss)

                if not IS_WINDOWS:
                    output += [escape.INSERT_ON, inserttext, escape.INSERT_OFF]
                else:
                    output += [f"{escape.ESC}[{str_util.calc_width(inserttext, 0, len(inserttext))}@", inserttext]

                if encoding != "utf-8" and cs == "U":
                    output.append(escape.IBMPC_OFF)

            if whitespace_at_end:
                output.append(escape.ERASE_IN_LINE_RIGHT)

        if canvas.cursor is not None:
            x, y = canvas.cursor
            output += [set_cursor_position(x, y), escape.SHOW_CURSOR]
            self._cy = y

        if self._resized:
            # handle resize before trying to draw screen
            return
        try:
            for line in output:
                if isinstance(line, bytes):
                    line = line.decode(encoding, "replace")  # noqa: PLW2901
                self.write(line)
            self.flush()
        except OSError as e:
            # ignore interrupted syscall
            if e.args[0] != 4:
                raise

        self.screen_buf = sb
        self._screen_buf_canvas = canvas

    def _last_row(
        self,
        row: list[tuple[object, Literal["0", "U"] | None, bytes]],
    ) -> tuple[
        list[tuple[object, Literal["0", "U"] | None, bytes]],
        int,
        tuple[object, Literal["0", "U"] | None, bytes],
    ]:
        """On the last row we need to slide the bottom right character
        into place. Calculate the new line, attr and an insert sequence
        to do that.

        eg. last row:
        XXXXXXXXXXXXXXXXXXXXYZ

        Y will be drawn after Z, shifting Z into position.
        """

        new_row = row[:-1]
        z_attr, z_cs, last_text = row[-1]
        last_cols = str_util.calc_width(last_text, 0, len(last_text))
        last_offs, z_col = str_util.calc_text_pos(last_text, 0, len(last_text), last_cols - 1)
        if last_offs == 0:
            z_text = last_text
            del new_row[-1]
            # we need another segment
            y_attr, y_cs, nlast_text = row[-2]
            nlast_cols = str_util.calc_width(nlast_text, 0, len(nlast_text))
            z_col += nlast_cols
            nlast_offs, y_col = str_util.calc_text_pos(nlast_text, 0, len(nlast_text), nlast_cols - 1)
            y_text = nlast_text[nlast_offs:]
            if nlast_offs:
                new_row.append((y_attr, y_cs, nlast_text[:nlast_offs]))
        else:
            z_text = last_text[last_offs:]
            y_attr, y_cs = z_attr, z_cs
            nlast_cols = str_util.calc_width(last_text, 0, last_offs)
            nlast_offs, y_col = str_util.calc_text_pos(last_text, 0, last_offs, nlast_cols - 1)
            y_text = last_text[nlast_offs:last_offs]
            if nlast_offs:
                new_row.append((y_attr, y_cs, last_text[:nlast_offs]))

        new_row.append((z_attr, z_cs, z_text))
        return new_row, z_col - y_col, (y_attr, y_cs, y_text)

    def clear(self) -> None:
        """
        Force the screen to be completely repainted on the next
        call to draw_screen().
        """
        self.screen_buf = None

    def _attrspec_to_escape(self, a: AttrSpec) -> str:
        """
        Convert AttrSpec instance a to an escape sequence for the terminal

        >>> s = Screen()
        >>> s.set_terminal_properties(colors=256)
        >>> a2e = s._attrspec_to_escape
        >>> a2e(s.AttrSpec('brown', 'dark green'))
        '\\x1b[0;33;42m'
        >>> a2e(s.AttrSpec('#fea,underline', '#d0d'))
        '\\x1b[0;38;5;229;4;48;5;164m'
        """
        if self.term == "fbterm":
            fg = escape.ESC + f"[1;{a.foreground_number:d}}}"
            bg = escape.ESC + f"[2;{a.background_number:d}}}"
            return fg + bg

        if a.foreground_true:
            fg = f"38;2;{';'.join(str(part) for part in a.get_rgb_values()[0:3])}"
        elif a.foreground_high:
            fg = f"38;5;{a.foreground_number:d}"
        elif a.foreground_basic:
            if a.foreground_number > 7:
                if self.fg_bright_is_bold:
                    fg = f"1;{a.foreground_number - 8 + 30:d}"
                else:
                    fg = f"{a.foreground_number - 8 + 90:d}"
            else:
                fg = f"{a.foreground_number + 30:d}"
        else:
            fg = "39"
        st = (
            "1;" * a.bold
            + "3;" * a.italics
            + "4;" * a.underline
            + "5;" * a.blink
            + "7;" * a.standout
            + "9;" * a.strikethrough
        )
        if a.background_true:
            bg = f"48;2;{';'.join(str(part) for part in a.get_rgb_values()[3:6])}"
        elif a.background_high:
            bg = f"48;5;{a.background_number:d}"
        elif a.background_basic:
            if a.background_number > 7:
                if self.bg_bright_is_blink:
                    bg = f"5;{a.background_number - 8 + 40:d}"
                else:
                    # this doesn't work on most terminals
                    bg = f"{a.background_number - 8 + 100:d}"
            else:
                bg = f"{a.background_number + 40:d}"
        else:
            bg = "49"
        return f"{escape.ESC}[0;{fg};{st}{bg}m"

    def set_terminal_properties(
        self,
        colors: Literal[1, 16, 88, 256, 16777216] | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
    ) -> None:
        """
        colors -- number of colors terminal supports (1, 16, 88, 256, or 2**24)
            or None to leave unchanged
        bright_is_bold -- set to True if this terminal uses the bold
            setting to create bright colors (numbers 8-15), set to False
            if this Terminal can create bright colors without bold or
            None to leave unchanged
        has_underline -- set to True if this terminal can use the
            underline setting, False if it cannot or None to leave
            unchanged
        """
        if colors is None:
            colors = self.colors
        if bright_is_bold is None:
            bright_is_bold = self.fg_bright_is_bold
        if has_underline is None:
            has_underline = self.has_underline

        if colors == self.colors and bright_is_bold == self.fg_bright_is_bold and has_underline == self.has_underline:
            return

        self.colors = colors
        self.fg_bright_is_bold = bright_is_bold
        self.has_underline = has_underline

        self.clear()
        self._pal_escape = {}
        for p, v in self._palette.items():
            self._on_update_palette_entry(p, *v)

    def reset_default_terminal_palette(self) -> None:
        """
        Attempt to set the terminal palette to default values as taken
        from xterm.  Uses number of colors from current
        set_terminal_properties() screen setting.
        """
        if self.colors == 1:
            return
        if self.colors == 2**24:
            colors = 256
        else:
            colors = self.colors

        def rgb_values(n) -> tuple[int | None, int | None, int | None]:
            if colors == 16:
                aspec = AttrSpec(f"h{n:d}", "", 256)
            else:
                aspec = AttrSpec(f"h{n:d}", "", colors)
            return aspec.get_rgb_values()[:3]

        entries = [(n, *rgb_values(n)) for n in range(min(colors, 256))]
        self.modify_terminal_palette(entries)

    def modify_terminal_palette(self, entries: list[tuple[int, int | None, int | None, int | None]]):
        """
        entries - list of (index, red, green, blue) tuples.

        Attempt to set part of the terminal palette (this does not work
        on all terminals.)  The changes are sent as a single escape
        sequence so they should all take effect at the same time.

        0 <= index < 256 (some terminals will only have 16 or 88 colors)
        0 <= red, green, blue < 256
        """

        if self.term == "fbterm":
            modify = [f"{index:d};{red:d};{green:d};{blue:d}" for index, red, green, blue in entries]
            self.write(f"\x1b[3;{';'.join(modify)}}}")
        else:
            modify = [f"{index:d};rgb:{red:02x}/{green:02x}/{blue:02x}" for index, red, green, blue in entries]
            self.write(f"\x1b]4;{';'.join(modify)}\x1b\\")
        self.flush()

    # shortcut for creating an AttrSpec with this screen object's
    # number of colors
    def AttrSpec(self, fg, bg) -> AttrSpec:
        return AttrSpec(fg, bg, self.colors)
