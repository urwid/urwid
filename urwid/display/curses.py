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


"""
Curses-based UI implementation
"""

from __future__ import annotations

import curses
import sys
import typing
from contextlib import suppress

from urwid import util

from . import escape
from .common import UNPRINTABLE_TRANS_TABLE, AttrSpec, BaseScreen, RealTerminal

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from urwid import Canvas

IS_WINDOWS = sys.platform == "win32"

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

    def initscr():
        import curses  # noqa: I001  # pylint: disable=redefined-outer-name,reimported  # special case for monkeypatch

        import _curses

        stdscr = _curses.initscr()
        for key, value in _curses.__dict__.items():
            if key[:4] == "ACS_" or key in {"LINES", "COLS"}:
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
    def __init__(self) -> None:
        super().__init__()
        self.curses_pairs = [(None, None)]  # Can't be sure what pair 0 will default to
        self.palette = {}
        self.has_color = False
        self.s = None
        self.cursor_state = None
        self.prev_input_resize = 0
        self.set_input_timeouts()
        self.last_bstate = 0
        self._mouse_tracking_enabled = False

        self.register_palette_entry(None, "default", "default")

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """
        Enable mouse tracking.

        After calling this function get_input will include mouse
        click events along with keystrokes.
        """
        enable = bool(enable)
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
                | curses.BUTTON1_DOUBLE_CLICKED
                | curses.BUTTON1_TRIPLE_CLICKED
                | curses.BUTTON2_DOUBLE_CLICKED
                | curses.BUTTON2_TRIPLE_CLICKED
                | curses.BUTTON3_DOUBLE_CLICKED
                | curses.BUTTON3_TRIPLE_CLICKED
                | curses.BUTTON4_DOUBLE_CLICKED
                | curses.BUTTON4_TRIPLE_CLICKED
                | curses.BUTTON_SHIFT
                | curses.BUTTON_ALT
                | curses.BUTTON_CTRL
            )
        else:
            raise NotImplementedError()

        self._mouse_tracking_enabled = enable

    def _start(self) -> None:
        """
        Initialize the screen and input mode.
        """
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
        curses.noecho()
        curses.meta(True)
        curses.halfdelay(10)  # use set_input_timeouts to adjust
        self.s.keypad(False)

        if not self._signal_keys_set:
            self._old_signal_keys = self.tty_signal_keys()

        super()._start()

        if IS_WINDOWS:
            # halfdelay() seems unnecessary and causes everything to slow down a lot.
            curses.nocbreak()  # exits halfdelay mode
            # keypad(1) is needed, or we get no special keys (cursor keys, etc.)
            self.s.keypad(True)

    def _stop(self) -> None:
        """
        Restore the screen.
        """
        curses.echo()
        self._curs_set(1)
        with suppress(curses.error):
            curses.endwin()
            # don't block original error with curses error

        if self._old_signal_keys:
            self.tty_signal_keys(*self._old_signal_keys)

        super()._stop()

    def _setup_colour_pairs(self) -> None:
        """
        Initialize all 63 color pairs based on the term:
        bg * 8 + 7 - fg
        So to get a color, we just need to use that term and get the right color
        pair number.
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

    def _curs_set(self, x: int):
        if self.cursor_state in {"fixed", x}:
            return
        try:
            curses.curs_set(x)
            self.cursor_state = x
        except curses.error:
            self.cursor_state = "fixed"

    def _clear(self) -> None:
        self.s.clear()
        self.s.refresh()

    def _getch(self, wait_tenths: int | None) -> int:
        if wait_tenths == 0:
            return self._getch_nodelay()

        if not IS_WINDOWS:
            if wait_tenths is None:
                curses.cbreak()
            else:
                curses.halfdelay(wait_tenths)

        self.s.nodelay(False)
        return self.s.getch()

    def _getch_nodelay(self) -> int:
        self.s.nodelay(True)

        if not IS_WINDOWS:
            while True:
                # this call fails sometimes, but seems to work when I try again
                with suppress(curses.error):
                    curses.cbreak()
                    break

        return self.s.getch()

    def set_input_timeouts(
        self,
        max_wait: float | None = None,
        complete_wait: float = 0.1,
        resize_wait: float = 0.1,
    ):
        """
        Set the get_input timeout values.  All values have a granularity
        of 0.1s, ie. any value between 0.15 and 0.05 will be treated as
        0.1 and any value less than 0.05 will be treated as 0.  The
        maximum timeout value for this module is 25.5 seconds.

        max_wait -- amount of time in seconds to wait for input when
            there is no input pending, wait forever if None
        complete_wait -- amount of time in seconds to wait when
            get_input detects an incomplete escape sequence at the
            end of the available input
        resize_wait -- amount of time in seconds to wait for more input
            after receiving two screen resize requests in a row to
            stop urwid from consuming 100% cpu during a gradual
            window resize operation
        """

        def convert_to_tenths(s):
            if s is None:
                return None
            return int((s + 0.05) * 10)

        self.max_tenths = convert_to_tenths(max_wait)
        self.complete_tenths = convert_to_tenths(complete_wait)
        self.resize_tenths = convert_to_tenths(resize_wait)

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
        * Mouse button release: ('mouse release', 0, 18, 13),
                              ('ctrl mouse release', 0, 17, 23)
        """
        if not self._started:
            raise RuntimeError

        keys, raw = self._get_input(self.max_tenths)

        # Avoid pegging CPU at 100% when slowly resizing, and work
        # around a bug with some braindead curses implementations that
        # return "no key" between "window resize" commands
        if keys == ["window resize"] and self.prev_input_resize:
            for _ in range(2):
                new_keys, new_raw = self._get_input(self.resize_tenths)
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

    def _get_input(self, wait_tenths: int | None) -> tuple[list[str], list[int]]:
        # this works around a strange curses bug with window resizing
        # not being reported correctly with repeated calls to this
        # function without a doupdate call in between
        curses.doupdate()

        key = self._getch(wait_tenths)
        resize = False
        raw = []
        keys = []

        while key >= 0:
            raw.append(key)
            if key == KEY_RESIZE:
                resize = True
            elif key == KEY_MOUSE:
                keys += self._encode_mouse_event()
            else:
                keys.append(key)
            key = self._getch_nodelay()

        processed = []

        try:
            while keys:
                run, keys = escape.process_keyqueue(keys, True)
                processed += run
        except escape.MoreInputRequired:
            key = self._getch(self.complete_tenths)
            while key >= 0:
                raw.append(key)
                if key == KEY_RESIZE:
                    resize = True
                elif key == KEY_MOUSE:
                    keys += self._encode_mouse_event()
                else:
                    keys.append(key)
                key = self._getch_nodelay()
            while keys:
                run, keys = escape.process_keyqueue(keys, False)
                processed += run

        if resize:
            processed.append("window resize")

        return processed, raw

    def _encode_mouse_event(self) -> list[int]:
        # convert to escape sequence
        last_state = next_state = self.last_bstate
        (_id, x, y, _z, bstate) = curses.getmouse()

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

        if bstate & curses.BUTTON1_DOUBLE_CLICKED:
            append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON2_DOUBLE_CLICKED:
            append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON3_DOUBLE_CLICKED:
            append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG)
        if bstate & curses.BUTTON4_DOUBLE_CLICKED:
            append_button(64 + escape.MOUSE_MULTIPLE_CLICK_FLAG)

        if bstate & curses.BUTTON1_TRIPLE_CLICKED:
            append_button(0 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON2_TRIPLE_CLICKED:
            append_button(1 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON3_TRIPLE_CLICKED:
            append_button(2 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)
        if bstate & curses.BUTTON4_TRIPLE_CLICKED:
            append_button(64 + escape.MOUSE_MULTIPLE_CLICK_FLAG * 2)

        self.last_bstate = next_state
        return result

    def _dbg_instr(self):  # messy input string (intended for debugging)
        curses.echo()
        self.s.nodelay(0)
        curses.halfdelay(100)
        string = self.s.getstr()
        curses.noecho()
        return string

    def _dbg_out(self, string) -> None:  # messy output function (intended for debugging)
        self.s.clrtoeol()
        self.s.addstr(string)
        self.s.refresh()
        self._curs_set(1)

    def _dbg_query(self, question):  # messy query (intended for debugging)
        self._dbg_out(question)
        return self._dbg_instr()

    def _dbg_refresh(self) -> None:
        self.s.refresh()

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows)."""
        rows, cols = self.s.getmaxyx()
        return cols, rows

    def _setattr(self, a):
        if a is None:
            self.s.attrset(0)
            return
        if not isinstance(a, AttrSpec):
            p = self._palette.get(a, (AttrSpec("default", "default"),))
            a = p[0]

        if self.has_color:
            if a.foreground_basic:
                if a.foreground_number >= 8:
                    fg = a.foreground_number - 8
                else:
                    fg = a.foreground_number
            else:
                fg = 7

            if a.background_basic:
                bg = a.background_number
            else:
                bg = 0

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

        self.s.attrset(attr)

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Paint screen with rendered canvas."""

        logger = self.logger.getChild("draw_screen")

        if not self._started:
            raise RuntimeError

        _cols, rows = size

        if canvas.rows() != rows:
            raise ValueError("canvas size and passed size don't match")

        logger.debug(f"Drawing screen with size {size!r}")

        y = -1
        for row in canvas.content():
            y += 1
            try:
                self.s.move(y, 0)
            except curses.error:
                # terminal shrunk?
                # move failed so stop rendering.
                return

            first = True
            lasta = None

            for nr, (a, cs, seg) in enumerate(row):
                if cs != "U":
                    seg = seg.translate(UNPRINTABLE_TRANS_TABLE)  # noqa: PLW2901
                    if not isinstance(seg, bytes):
                        raise TypeError(seg)

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
                        if not isinstance(seg, bytes):
                            raise TypeError(seg)
                        self.s.addstr(seg.decode(util.get_encoding()))
                except curses.error:
                    # it's OK to get out of the
                    # screen on the lower right
                    if y != rows - 1 or nr != len(row) - 1:
                        # perhaps screen size changed
                        # quietly abort.
                        return

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
        """
        Force the screen to be completely repainted on the next call to draw_screen().
        """
        self.s.clear()


class _test:
    def __init__(self):
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
        class FakeRender:
            pass

        r = FakeRender()
        text = [f"  has_color = {self.ui.has_color!r}", ""]
        attr = [[], []]
        r.coords = {}
        r.cursor = None

        for c in self.l:
            t = ""
            a = []
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
            r.text = ([t.ljust(cols) for t in text] + [""] * rows)[:rows]
            r.attr = (attr + [[] for _ in range(rows)])[:rows]
            self.ui.draw_screen((cols, rows), r)
            keys, raw = self.ui.get_input(raw_keys=True)
            if "window resize" in keys:
                cols, rows = self.ui.get_cols_rows()
            if not keys:
                continue
            t = ""
            a = []
            for k in keys:
                if isinstance(k, str):
                    k = k.encode(util.get_encoding())  # noqa: PLW2901

                t += f"'{k}' "
                a += [(None, 1), ("yellow on dark blue", len(k)), (None, 2)]

            text.append(f"{t}: {raw!r}")
            attr.append(a)
            text = text[-rows:]
            attr = attr[-rows:]


if __name__ == "__main__":
    _test()
