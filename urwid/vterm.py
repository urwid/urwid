#!/usr/bin/python
#
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


from __future__ import annotations

import atexit
import copy
import errno
import os
import select
import signal
import struct
import sys
import time
import traceback
import typing
from collections.abc import Iterable, Mapping, Sequence, Callable

try:
    import fcntl
    import pty
    import termios
except ImportError:
    pass # windows

from urwid import util
from urwid.canvas import Canvas
from urwid.display_common import _BASIC_COLORS, AttrSpec, RealTerminal,
                                  _color_desc_256, _color_desc_true)
from urwid.escape import ALT_DEC_SPECIAL_CHARS, DEC_SPECIAL_CHARS
from urwid.widget import BOX, Widget
from urwid import event_loop

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

EOF = b''
ESC = chr(27)

KEY_TRANSLATIONS = {
    'enter':     chr(13),
    'backspace': chr(127),
    'tab':       chr(9),
    'esc':       ESC,
    'up':        f"{ESC}[A",
    'down':      f"{ESC}[B",
    'right':     f"{ESC}[C",
    'left':      f"{ESC}[D",
    'home':      f"{ESC}[1~",
    'insert':    f"{ESC}[2~",
    'delete':    f"{ESC}[3~",
    'end':       f"{ESC}[4~",
    'page up':   f"{ESC}[5~",
    'page down': f"{ESC}[6~",

    'f1':        f"{ESC}[[A",
    'f2':        f"{ESC}[[B",
    'f3':        f"{ESC}[[C",
    'f4':        f"{ESC}[[D",
    'f5':        f"{ESC}[[E",
    'f6':        f"{ESC}[17~",
    'f7':        f"{ESC}[18~",
    'f8':        f"{ESC}[19~",
    'f9':        f"{ESC}[20~",
    'f10':       f"{ESC}[21~",
    'f11':       f"{ESC}[23~",
    'f12':       f"{ESC}[24~",
}

KEY_TRANSLATIONS_DECCKM = {
    'up':        f"{ESC}OA",
    'down':      f"{ESC}OB",
    'right':     f"{ESC}OC",
    'left':      f"{ESC}OD",
    'f1':        f"{ESC}OP",
    'f2':        f"{ESC}OQ",
    'f3':        f"{ESC}OR",
    'f4':        f"{ESC}OS",
    'f5':        f"{ESC}[15~",
}

CSI_COMMANDS = {
    # possible values:
    #     None -> ignore sequence
    #     (<minimum number of args>, <fallback if no argument>, callback)
    #     ('alias', <symbol>)
    #
    # while callback is executed as:
    #     callback(<instance of TermCanvas>, arguments, has_question_mark)

    b'@': (1, 1, lambda s, number, q: s.insert_chars(chars=number[0])),
    b'A': (1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative=True)),
    b'B': (1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative=True)),
    b'C': (1, 1, lambda s, cols, q: s.move_cursor(cols[0], 0, relative=True)),
    b'D': (1, 1, lambda s, cols, q: s.move_cursor(-cols[0], 0, relative=True)),
    b'E': (1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative_y=True)),
    b'F': (1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative_y=True)),
    b'G': (1, 1, lambda s, col, q: s.move_cursor(col[0] - 1, 0, relative_y=True)),
    b'H': (2, 1, lambda s, x_y, q: s.move_cursor(x_y[1] - 1, x_y[0] - 1)),
    b'J': (1, 0, lambda s, mode, q: s.csi_erase_display(mode[0])),
    b'K': (1, 0, lambda s, mode, q: s.csi_erase_line(mode[0])),
    b'L': (1, 1, lambda s, number, q: s.insert_lines(lines=number[0])),
    b'M': (1, 1, lambda s, number, q: s.remove_lines(lines=number[0])),
    b'P': (1, 1, lambda s, number, q: s.remove_chars(chars=number[0])),
    b'X': (1, 1, lambda s, number, q: s.erase(s.term_cursor,
                                                (s.term_cursor[0]+number[0] - 1,
                                                 s.term_cursor[1]))),
    b'a': ('alias', b'C'),
    b'c': (0, 0, lambda s, none, q: s.csi_get_device_attributes(q)),
    b'd': (1, 1, lambda s, row, q: s.move_cursor(0, row[0] - 1, relative_x=True)),
    b'e': ('alias', b'B'),
    b'f': ('alias', b'H'),
    b'g': (1, 0, lambda s, mode, q: s.csi_clear_tabstop(mode[0])),
    b'h': (1, 0, lambda s, modes, q: s.csi_set_modes(modes, q)),
    b'l': (1, 0, lambda s, modes, q: s.csi_set_modes(modes, q, reset=True)),
    b'm': (1, 0, lambda s, attrs, q: s.csi_set_attr(attrs)),
    b'n': (1, 0, lambda s, mode, q: s.csi_status_report(mode[0])),
    b'q': (1, 0, lambda s, mode, q: s.csi_set_keyboard_leds(mode[0])),
    b'r': (2, 0, lambda s, t_b, q: s.csi_set_scroll(t_b[0], t_b[1])),
    b's': (0, 0, lambda s, none, q: s.save_cursor()),
    b'u': (0, 0, lambda s, none, q: s.restore_cursor()),
    b'`': ('alias', b'G'),
}

CHARSET_DEFAULT = 1
CHARSET_UTF8 = 2


class TermModes:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        # ECMA-48
        self.display_ctrl = False
        self.insert = False
        self.lfnl = False

        # DEC private modes
        self.keys_decckm = False
        self.reverse_video = False
        self.constrain_scrolling = False
        self.autowrap = True
        self.visible_cursor = True

        # charset stuff
        self.main_charset = CHARSET_DEFAULT


class TermCharset:
    MAPPING = {
        'default': None,
        'vt100':   '0',
        'ibmpc':   'U',
        'user':    None,
    }

    def __init__(self) -> None:
        self._g = [
            'default',
            'vt100',
        ]

        self._sgr_mapping = False

        # prepare defaults
        self.active = 0
        self.current: str | None = None

        self.activate(0)

    def define(self, g: int, charset: str) -> None:
        """
        Redefine G'g' with new mapping.
        """
        self._g[g] = charset
        self.activate(g=self.active)

    def activate(self, g: int) -> None:
        """
        Activate the given charset slot.
        """
        self.active = g
        self.current = self.MAPPING.get(self._g[g], None)

    def set_sgr_ibmpc(self) -> None:
        """
        Set graphics rendition mapping to IBM PC CP437.
        """
        self._sgr_mapping = True

    def reset_sgr_ibmpc(self) -> None:
        """
        Reset graphics rendition mapping to IBM PC CP437.
        """
        self._sgr_mapping = False
        self.activate(g=self.active)

    def apply_mapping(self, char: bytes) -> bytes:
        if self._sgr_mapping or self._g[self.active] == 'ibmpc':
            dec_pos = DEC_SPECIAL_CHARS.find(char.decode('cp437'))
            if dec_pos >= 0:
                self.current = '0'
                return ALT_DEC_SPECIAL_CHARS[dec_pos].encode("cp437")
            else:
                self.current = 'U'
                return char
        else:
            return char


class TermScroller(list):
    """
    List subclass that handles the terminal scrollback buffer,
    truncating it as necessary.
    """
    SCROLLBACK_LINES = 10000

    def trunc(self):
        if len(self) >= self.SCROLLBACK_LINES:
            self.pop(0)

    def append(self, obj):
        self.trunc()
        super().append(obj)

    def insert(self, idx, obj):
        self.trunc()
        super().insert(idx, obj)

    def extend(self, seq):
        self.trunc()
        super().extend(seq)


class TermCanvas(Canvas):
    cacheable = False

    def __init__(self, width: int, height: int, widget: Terminal) -> None:
        super().__init__()

        self.width, self.height = width, height
        self.widget = widget
        self.modes = widget.term_modes
        self.has_focus = False

        self.scrollback_buffer = TermScroller()
        self.scrolling_up = 0

        self.utf8_eat_bytes = None
        self.utf8_buffer = b''
        self.escbuf = b''

        self.coords["cursor"] = (0, 0, None)

        self.term_cursor = (0, 0)  # do not allow to shoot in the leg at `set_term_cursor`
        self.cursor: tuple[int, int] | None = None

        self.reset()

    def set_term_cursor(self, x: int | None = None, y: int | None = None) -> None:
        """
        Set terminal cursor to x/y and update canvas cursor. If one or both axes
        are omitted, use the values of the current position.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        self.term_cursor = self.constrain_coords(x, y)

        if self.has_focus and self.modes.visible_cursor and self.scrolling_up < self.height - y:
            self.cursor = (x, y + self.scrolling_up)
        else:
            self.cursor = None

    def reset_scroll(self) -> None:
        """
        Reset scrolling region to full terminal size.
        """
        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1

    def scroll_buffer(self, up: bool = True, reset: bool = False, lines: int | None = None) -> None:
        """
        Scroll the scrolling buffer up (up=True) or down (up=False) the given
        amount of lines or half the screen height.

        If just 'reset' is True, set the scrollbuffer view to the current
        terminal content.
        """
        if reset:
            self.scrolling_up = 0
            self.set_term_cursor()
            return

        if lines is None:
            lines = self.height // 2

        if not up:
            lines = -lines

        maxscroll = len(self.scrollback_buffer)
        self.scrolling_up += lines

        if self.scrolling_up > maxscroll:
            self.scrolling_up = maxscroll
        elif self.scrolling_up < 0:
            self.scrolling_up = 0

        self.set_term_cursor()

    def reset(self) -> None:
        """
        Reset the terminal.
        """
        self.escbuf = b''
        self.within_escape = False
        self.parsestate = 0

        self.attrspec = None
        self.charset = TermCharset()

        self.saved_cursor = None
        self.saved_attrs = None

        self.is_rotten_cursor = False

        self.reset_scroll()

        self.init_tabstops()

        # terminal modes
        self.modes.reset()

        # initialize self.term
        self.clear()

    def init_tabstops(self, extend: bool = False) -> None:
        tablen, mod = divmod(self.width, 8)
        if mod > 0:
            tablen += 1

        if extend:
            while len(self.tabstops) < tablen:
                self.tabstops.append(1 << 0)
        else:
            self.tabstops = [1 << 0] * tablen

    def set_tabstop(self, x: int | None = None, remove: bool = False, clear: bool = False) -> None:
        if clear:
            for tab in range(len(self.tabstops)):
                self.tabstops[tab] = 0
            return

        if x is None:
            x = self.term_cursor[0]

        div, mod = divmod(x, 8)
        if remove:
            self.tabstops[div] &= ~(1 << mod)
        else:
            self.tabstops[div] |= (1 << mod)

    def is_tabstop(self, x: int | None = None) -> bool:
        if x is None:
            x = self.term_cursor[0]

        div, mod = divmod(x, 8)
        return (self.tabstops[div] & (1 << mod)) > 0

    def empty_line(self, char: bytes = b' '):
        return [self.empty_char(char)] * self.width

    def empty_char(self, char: bytes = b' '):
        return (self.attrspec, self.charset.current, char)

    def addstr(self, data):
        if self.width <= 0 or self.height <= 0:
            # not displayable, do nothing!
            return

        for byte in data:
            self.addbyte(byte)

    def resize(self, width: int, height: int) -> None:
        """
        Resize the terminal to the given width and height.
        """
        x, y = self.term_cursor

        if width > self.width:
            # grow
            for y in range(self.height):
                self.term[y] += [self.empty_char()] * (width - self.width)
        elif width < self.width:
            # shrink
            for y in range(self.height):
                self.term[y] = self.term[y][:width]

        self.width = width

        if height > self.height:
            # grow
            for y in range(self.height, height):
                try:
                    last_line = self.scrollback_buffer.pop()
                except IndexError:
                    # nothing in scrollback buffer, append an empty line
                    self.term.append(self.empty_line())
                    self.scrollregion_end += 1
                    continue

                # adjust x axis of scrollback buffer to the current width
                if len(last_line) < self.width:
                    last_line += [self.empty_char()] * \
                                 (self.width - len(last_line))
                else:
                    last_line = last_line[:self.width]

                y += 1

                self.term.insert(0, last_line)
        elif height < self.height:
            # shrink
            for y in range(height, self.height):
                self.scrollback_buffer.append(self.term.pop(0))

        self.height = height

        self.reset_scroll()

        x, y = self.constrain_coords(x, y)
        self.set_term_cursor(x, y)

        # extend tabs
        self.init_tabstops(extend=True)

    def set_g01(self, char: bytes, mod: str) -> None:
        """
        Set G0 or G1 according to 'char' and modifier 'mod'.
        """
        if self.modes.main_charset != CHARSET_DEFAULT:
            return

        if mod == b'(':
            g = 0
        else:
            g = 1

        if char == b'0':
            cset = 'vt100'
        elif char == b'U':
            cset = 'ibmpc'
        elif char == b'K':
            cset = 'user'
        else:
            cset = 'default'

        self.charset.define(g, cset)

    def parse_csi(self, char: bytes) -> None:
        """
        Parse ECMA-48 CSI (Control Sequence Introducer) sequences.
        """
        qmark = self.escbuf.startswith(b'?')

        escbuf = []
        for arg in self.escbuf[qmark and 1 or 0:].split(b';'):
            try:
                num = int(arg)
            except ValueError:
                num = None

            escbuf.append(num)

        if CSI_COMMANDS[char] is not None:
            if CSI_COMMANDS[char][0] == 'alias':
                csi_cmd = CSI_COMMANDS[(CSI_COMMANDS[char][1])]
            else:
                csi_cmd = CSI_COMMANDS[char]

            number_of_args, default_value, cmd = csi_cmd
            while len(escbuf) < number_of_args:
                escbuf.append(default_value)
            for i in range(len(escbuf)):
                if escbuf[i] is None or escbuf[i] == 0:
                    escbuf[i] = default_value

            try:
                cmd(self, escbuf, qmark)
            except ValueError:
                # ignore commands that don't match the
                # unpacked tuples in CSI_COMMANDS.
                pass

    def parse_noncsi(self, char: bytes, mod: str | None = None) -> None:
        """
        Parse escape sequences which are not CSI.
        """
        if mod == b'#' and char == b'8':
            self.decaln()
        elif mod == b'%':  # select main character set
            if char == b'@':
                self.modes.main_charset = CHARSET_DEFAULT
            elif char in b'G8':
                # 8 is obsolete and only for backwards compatibility
                self.modes.main_charset = CHARSET_UTF8
        elif mod == b'(' or mod == b')':  # define G0/G1
            self.set_g01(char, mod)
        elif char == b'M':  # reverse line feed
            self.linefeed(reverse=True)
        elif char == b'D':  # line feed
            self.linefeed()
        elif char == b'c':  # reset terminal
            self.reset()
        elif char == b'E':  # newline
            self.newline()
        elif char == b'H':  # set tabstop
            self.set_tabstop()
        elif char == b'Z':  # DECID
            self.widget.respond(f"{ESC}[?6c")
        elif char == b'7':  # save current state
            self.save_cursor(with_attrs=True)
        elif char == b'8':  # restore current state
            self.restore_cursor(with_attrs=True)

    def parse_osc(self, buf: bytes) -> None:
        """
        Parse operating system command.
        """
        if buf.startswith(b';'):  # set window title and icon
            self.widget.set_title(buf[1:])
        elif buf.startswith(b'3;'):  # set window title
            self.widget.set_title(buf[2:])

    def parse_escape(self, char: bytes) -> None:
        if self.parsestate == 1:
            # within CSI
            if char in CSI_COMMANDS:
                self.parse_csi(char)
                self.parsestate = 0
            elif char in b'0123456789;' or (not self.escbuf and char == b'?'):
                self.escbuf += char
                return
        elif self.parsestate == 0 and char == b']':
            # start of OSC
            self.escbuf = b''
            self.parsestate = 2
            return
        elif self.parsestate == 2 and char == b"\x07":
            # end of OSC
            self.parse_osc(self.escbuf.lstrip(b'0'))
        elif self.parsestate == 2 and self.escbuf[-1:] + char == f"{ESC}\\".encode('iso8859-1'):
            # end of OSC
            self.parse_osc(self.escbuf[:-1].lstrip(b'0'))
        elif self.parsestate == 2 and self.escbuf.startswith(b'P') and len(self.escbuf) == 8:
            # set palette (ESC]Pnrrggbb)
            pass
        elif self.parsestate == 2 and not self.escbuf and char == b'R':
            # reset palette
            pass
        elif self.parsestate == 2:
            self.escbuf += char
            return
        elif self.parsestate == 0 and char == b'[':
            # start of CSI
            self.escbuf = b''
            self.parsestate = 1
            return
        elif self.parsestate == 0 and char in (b'%', b'#', b'(', b')'):
            # non-CSI sequence
            self.escbuf = char
            self.parsestate = 3
            return
        elif self.parsestate == 3:
            self.parse_noncsi(char, self.escbuf)
        elif char in (b'c', b'D', b'E', b'H', b'M', b'Z', b'7', b'8', b'>', b'='):
            self.parse_noncsi(char)

        self.leave_escape()

    def leave_escape(self) -> None:
        self.within_escape = False
        self.parsestate = 0
        self.escbuf = b''

    def get_utf8_len(self, bytenum: int) -> int:
        """
        Process startbyte and return the number of bytes following it to get a
        valid UTF-8 multibyte sequence.

        bytenum -- an integer ordinal
        """
        length = 0

        while bytenum & 0x40:
            bytenum <<= 1
            length += 1

        return length

    def addbyte(self, byte: int) -> None:
        """
        Parse main charset and add the processed byte(s) to the terminal state
        machine.

        byte -- an integer ordinal
        """
        if self.modes.main_charset == CHARSET_UTF8 or util._target_encoding == 'utf8':
            if byte >= 0xc0:
                # start multibyte sequence
                self.utf8_eat_bytes = self.get_utf8_len(byte)
                self.utf8_buffer = bytes([byte])
                return
            elif 0x80 <= byte < 0xc0 and self.utf8_eat_bytes is not None:
                if self.utf8_eat_bytes > 1:
                    # continue multibyte sequence
                    self.utf8_eat_bytes -= 1
                    self.utf8_buffer += bytes([byte])
                    return
                else:
                    # end multibyte sequence
                    self.utf8_eat_bytes = None
                    sequence = (self.utf8_buffer + bytes([byte])).decode('utf-8', 'ignore')
                    if len(sequence) == 0:
                        # invalid multibyte sequence, stop processing
                        return
                    char = sequence.encode(util._target_encoding, 'replace')
            else:
                self.utf8_eat_bytes = None
                char = bytes([byte])
        else:
            char = bytes([byte])

        self.process_char(char)

    def process_char(self, char: int | bytes) -> None:
        """
        Process a single character (single- and multi-byte).

        char -- a byte string
        """
        x, y = self.term_cursor

        if isinstance(char, int):
            char = chr(char)

        dc = self.modes.display_ctrl

        if char == b"\x1b" and self.parsestate != 2:  # escape
            self.within_escape = True
        elif not dc and char == b"\x0d":  # carriage return
            self.carriage_return()
        elif not dc and char == b"\x0f":  # activate G0
            self.charset.activate(0)
        elif not dc and char == b"\x0e":  # activate G1
            self.charset.activate(1)
        elif not dc and char in b"\x0a\x0b\x0c":  # line feed
            self.linefeed()
            if self.modes.lfnl:
                self.carriage_return()
        elif not dc and char == b"\x09":  # char tab
            self.tab()
        elif not dc and char == b"\x08":  # backspace
            if x > 0:
                self.set_term_cursor(x - 1, y)
        elif not dc and char == b"\x07" and self.parsestate != 2:  # beep
            # we need to check if we're in parsestate 2, as an OSC can be
            # terminated by the BEL character!
            self.widget.beep()
        elif not dc and char in b"\x18\x1a":  # CAN/SUB
            self.leave_escape()
        elif not dc and char in b"\x00\x7f":  # NUL/DEL
            pass  # this is ignored
        elif self.within_escape:
            self.parse_escape(char)
        elif not dc and char == b"\x9b":  # CSI (equivalent to "ESC [")
            self.within_escape = True
            self.escbuf = b''
            self.parsestate = 1
        else:
            self.push_cursor(char)

    def set_char(self, char: bytes, x: int | None = None, y: int | None = None) -> None:
        """
        Set character of either the current cursor position
        or a position given by 'x' and/or 'y' to 'char'.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        x, y = self.constrain_coords(x, y)
        self.term[y][x] = (self.attrspec, self.charset.current, char)

    def constrain_coords(self, x: int, y: int, ignore_scrolling: bool = False) -> tuple[int, int]:
        """
        Checks if x/y are within the terminal and returns the corrected version.
        If 'ignore_scrolling' is set, constrain within the full size of the
        screen and not within scrolling region.
        """
        if x >= self.width:
            x = self.width - 1
        elif x < 0:
            x = 0

        if self.modes.constrain_scrolling and not ignore_scrolling:
            if y > self.scrollregion_end:
                y = self.scrollregion_end
            elif y < self.scrollregion_start:
                y = self.scrollregion_start
        else:
            if y >= self.height:
                y = self.height - 1
            elif y < 0:
                y = 0

        return x, y

    def linefeed(self, reverse: bool = False) -> None:
        """
        Move the cursor down (or up if reverse is True) one line but don't reset
        horizontal position.
        """
        x, y = self.term_cursor

        if reverse:
            if y <= 0 < self.scrollregion_start:
                pass
            elif y == self.scrollregion_start:
                self.scroll(reverse=True)
            else:
                y -= 1
        else:
            if y >= self.height - 1 > self.scrollregion_end:
                pass
            elif y == self.scrollregion_end:
                self.scroll()
            else:
                y += 1

        self.set_term_cursor(x, y)

    def carriage_return(self) -> None:
        self.set_term_cursor(0, self.term_cursor[1])

    def newline(self) -> None:
        """
        Do a carriage return followed by a line feed.
        """
        self.carriage_return()
        self.linefeed()

    def move_cursor(
        self,
        x: int,
        y: int,
        relative_x: bool = False,
        relative_y: bool = False,
        relative: bool = False,
    ) -> None:
        """
        Move cursor to position x/y while constraining terminal sizes.
        If 'relative' is True, x/y is relative to the current cursor
        position. 'relative_x' and 'relative_y' is the same but just with
        the corresponding axis.
        """
        if relative:
            relative_y = relative_x = True

        if relative_x:
            x += self.term_cursor[0]

        if relative_y:
            y += self.term_cursor[1]
        elif self.modes.constrain_scrolling:
            y += self.scrollregion_start

        self.set_term_cursor(x, y)

    def push_char(self, char: bytes | None, x: int, y: int) -> None:
        """
        Push one character to current position and advance cursor to x/y.
        """
        if char is not None:
            char = self.charset.apply_mapping(char)
            if self.modes.insert:
                self.insert_chars(char=char)
            else:
                self.set_char(char)

        self.set_term_cursor(x, y)

    def push_cursor(self, char: bytes | None = None) -> None:
        """
        Move cursor one character forward wrapping lines as needed.
        If 'char' is given, put the character into the former position.
        """
        x, y = self.term_cursor

        if self.modes.autowrap:
            if x + 1 >= self.width and not self.is_rotten_cursor:
                # "rotten cursor" - this is when the cursor gets to the rightmost
                # position of the screen, the cursor position remains the same but
                # one last set_char() is allowed for that piece of sh^H^H"border".
                self.is_rotten_cursor = True
                self.push_char(char, x, y)
            else:
                x += 1

                if x >= self.width and self.is_rotten_cursor:
                    if y >= self.scrollregion_end:
                        self.scroll()
                    else:
                        y += 1

                    x = 1

                    self.set_term_cursor(0, y)

                self.push_char(char, x, y)

                self.is_rotten_cursor = False
        else:
            if x + 1 < self.width:
                x += 1

            self.is_rotten_cursor = False
            self.push_char(char, x, y)

    def save_cursor(self, with_attrs: bool = False) -> None:
        self.saved_cursor = tuple(self.term_cursor)
        if with_attrs:
            self.saved_attrs = (copy.copy(self.attrspec), copy.copy(self.charset))

    def restore_cursor(self, with_attrs: bool = False) -> None:
        if self.saved_cursor is None:
            return

        x, y = self.saved_cursor
        self.set_term_cursor(x, y)

        if with_attrs and self.saved_attrs is not None:
            self.attrspec, self.charset = (copy.copy(self.saved_attrs[0]), copy.copy(self.saved_attrs[1]))

    def tab(self, tabstop: int = 8) -> None:
        """
        Moves cursor to the next 'tabstop' filling everything in between
        with spaces.
        """
        x, y = self.term_cursor

        while x < self.width - 1:
            self.set_char(b" ")
            x += 1

            if self.is_tabstop(x):
                break

        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def scroll(self, reverse: bool = False) -> None:
        """
        Append a new line at the bottom and put the topmost line into the
        scrollback buffer.

        If reverse is True, do exactly the opposite, but don't save into
        scrollback buffer.
        """
        if reverse:
            self.term.pop(self.scrollregion_end)
            self.term.insert(self.scrollregion_start, self.empty_line())
        else:
            killed = self.term.pop(self.scrollregion_start)
            self.scrollback_buffer.append(killed)
            self.term.insert(self.scrollregion_end, self.empty_line())

    def decaln(self) -> None:
        """
        DEC screen alignment test: Fill screen with E's.
        """
        for row in range(self.height):
            self.term[row] = self.empty_line('E')

    def blank_line(self, row: int) -> None:
        """
        Blank a single line at the specified row, without modifying other lines.
        """
        self.term[row] = self.empty_line()

    def insert_chars(
        self,
        position: tuple[int, int] | None = None,
        chars: int = 1,
        char: bytes | None = None,
    ) -> None:
        """
        Insert 'chars' number of either empty characters - or those specified by
        'char' - before 'position' (or the current position if not specified)
        pushing subsequent characters of the line to the right without wrapping.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        if char is None:
            char = self.empty_char()
        else:
            char = (self.attrspec, self.charset.current, char)

        x, y = position

        while chars > 0:
            self.term[y].insert(x, char)
            self.term[y].pop()
            chars -= 1

    def remove_chars(self, position: tuple[int, int] | None = None, chars: int = 1) -> None:
        """
        Remove 'chars' number of empty characters from 'position' (or the current
        position if not specified) pulling subsequent characters of the line to
        the left without joining any subsequent lines.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        x, y = position

        while chars > 0:
            self.term[y].pop(x)
            self.term[y].append(self.empty_char())
            chars -= 1

    def insert_lines(self, row: int | None = None, lines: int = 1) -> None:
        """
        Insert 'lines' of empty lines after the specified row, pushing all
        subsequent lines to the bottom. If no 'row' is specified, the current
        row is used.
        """
        if row is None:
            row = self.term_cursor[1]
        else:
            row = self.scrollregion_start

        if lines == 0:
            lines = 1

        while lines > 0:
            self.term.insert(row, self.empty_line())
            self.term.pop(self.scrollregion_end)
            lines -= 1

    def remove_lines(self, row: int | None = None, lines: int = 1) -> None:
        """
        Remove 'lines' number of lines at the specified row, pulling all
        subsequent lines to the top. If no 'row' is specified, the current row
        is used.
        """
        if row is None:
            row = self.term_cursor[1]
        else:
            row = self.scrollregion_start

        if lines == 0:
            lines = 1

        while lines > 0:
            self.term.pop(row)
            self.term.insert(self.scrollregion_end, self.empty_line())
            lines -= 1

    def erase(
        self,
        start: tuple[int, int] | tuple[int, int, bool],
        end: tuple[int, int] | tuple[int, int, bool],
    ) -> None:
        """
        Erase a region of the terminal. The 'start' tuple (x, y) defines the
        starting position of the erase, while end (x, y) the last position.

        For example if the terminal size is 4x3, start=(1, 1) and end=(1, 2)
        would erase the following region:

        ....
        .XXX
        XX..
        """
        sx, sy = self.constrain_coords(*start)
        ex, ey = self.constrain_coords(*end)

        # within a single row
        if sy == ey:
            for x in range(sx, ex + 1):
                self.term[sy][x] = self.empty_char()
            return

        # spans multiple rows
        y = sy
        while y <= ey:
            if y == sy:
                for x in range(sx, self.width):
                    self.term[y][x] = self.empty_char()
            elif y == ey:
                for x in range(ex + 1):
                    self.term[y][x] = self.empty_char()
            else:
                self.blank_line(y)

            y += 1

    def sgi_to_attrspec(self, attrs: Iterable[int], fg: int, bg: int, attributes: set[str], prev_colors: int) -> AttrSpec | None:
        """
        Parse SGI sequence and return an AttrSpec representing the sequence
        including all earlier sequences specified as 'fg', 'bg' and
        'attributes'.
        """

        idx = 0
        colors = prev_colors

        while idx < len(attrs):
            attr = attrs[idx]
            if 30 <= attr <= 37:
                fg = attr - 30
                colors = max(16, colors)
            elif 40 <= attr <= 47:
                bg = attr - 40
                colors = max(16, colors)
            elif attr == 38 or attr == 48:
                if idx + 2 < len(attrs) and attrs[idx + 1] == 5:
                    # 8 bit color specification
                    color = attrs[idx + 2]
                    colors = max(256, colors)
                    if attr == 38:
                        fg = color
                    else:
                        bg = color
                    idx += 2
                elif idx + 4 < len(attrs) and attrs[idx + 1] == 2:
                    # 24 bit color specification
                    color = (attrs[idx + 2] << 16) + \
                        (attrs[idx + 3] << 8) + attrs[idx + 4]
                    colors = 2**24
                    if attr == 38:
                        fg = color
                    else:
                        bg = color
                    idx += 4
            elif attr == 39:
                # set default foreground color, remove underline
                attributes.discard('underline')
                fg = None
            elif attr == 49:
                # set default background color
                bg = None
            elif attr == 10:
                self.charset.reset_sgr_ibmpc()
                self.modes.display_ctrl = False
            elif attr in (11, 12):
                self.charset.set_sgr_ibmpc()
                self.modes.display_ctrl = True

            # set attributes
            elif attr == 1:
                attributes.add('bold')
            elif attr == 4:
                attributes.add('underline')
            elif attr == 5:
                attributes.add('blink')
            elif attr == 7:
                attributes.add('standout')

            # unset attributes
            elif attr == 24:
                attributes.discard('underline')
            elif attr == 25:
                attributes.discard('blink')
            elif attr == 27:
                attributes.discard('standout')
            elif attr == 0:
                # clear all attributes
                fg = bg = None
                attributes.clear()

            idx += 1

        if 'bold' in attributes and colors == 16 and fg is not None and fg < 8:
            fg += 8

        def _defaulter(color: int | None, colors: int) -> str:
            if color is None:
                return 'default'
            # Note: we can't detect 88 color mode
            if color > 255 or colors == 2**24:
                return _color_desc_true(color)
            if color > 15 or colors == 256:
                return _color_desc_256(color)
            return _BASIC_COLORS[color]

        fg = _defaulter(fg, colors)
        bg = _defaulter(bg, colors)

        if len(attributes) > 0:
            fg = ','.join([fg] + list(attributes))

        if fg == 'default' and bg == 'default':
            return None
        else:
            if colors:
                return AttrSpec(fg, bg, colors=colors)
            else:
                return AttrSpec(fg, bg)

    def csi_set_attr(self, attrs):
        """
        Set graphics rendition.
        """
        if attrs[-1] == 0:
            self.attrspec = None

        attributes = set()
        if self.attrspec is None:
            fg = bg = None
        else:
            # set default values from previous attrspec
            if 'default' in self.attrspec.foreground:
                fg = None
            else:
                fg = self.attrspec.foreground_number
                if fg >= 8 and self.attrspec._colors() == 16:
                    fg -= 8

            if 'default' in self.attrspec.background:
                bg = None
            else:
                bg = self.attrspec.background_number
                if bg >= 8 and self.attrspec._colors() == 16:
                    bg -= 8

            for attr in ('bold', 'underline', 'blink', 'standout'):
                if not getattr(self.attrspec, attr):
                    continue

                attributes.add(attr)

        attrspec = self.sgi_to_attrspec(attrs, fg, bg, attributes,
                                        self.attrspec._colors()
                                        if self.attrspec else 1)

        if self.modes.reverse_video:
            self.attrspec = self.reverse_attrspec(attrspec)
        else:
            self.attrspec = attrspec

    def reverse_attrspec(self, attrspec: AttrSpec | None, undo: bool = False) -> AttrSpec:
        """
        Put standout mode to the 'attrspec' given and remove it if 'undo' is
        True.
        """
        if attrspec is None:
            attrspec = AttrSpec('default', 'default')
        attrs = [fg.strip() for fg in attrspec.foreground.split(',')]
        if 'standout' in attrs and undo:
            attrs.remove('standout')
            attrspec = attrspec.copy_modified(fg=','.join(attrs))
        elif 'standout' not in attrs and not undo:
            attrs.append('standout')
            attrspec = attrspec.copy_modified(fg=','.join(attrs))
        return attrspec

    def reverse_video(self, undo: bool = False) -> None:
        """
        Reverse video/scanmode (DECSCNM) by swapping fg and bg colors.
        """
        for y in range(self.height):
            for x in range(self.width):
                char = self.term[y][x]
                attrs = self.reverse_attrspec(char[0], undo=undo)
                self.term[y][x] = (attrs,) + char[1:]

    def set_mode(
        self,
        mode: Literal[1, 3, 4, 5, 6, 7, 20, 25] | int,
        flag: bool,
        qmark: bool,
        reset: bool,
    ) -> None:
        """
        Helper method for csi_set_modes: set single mode.
        """
        if qmark:
            # DEC private mode
            if mode == 1:
                # cursor keys send an ESC O prefix, rather than ESC [
                self.modes.keys_decckm = flag
            elif mode == 3:
                # deccolm just clears the screen
                self.clear()
            elif mode == 5:
                if self.modes.reverse_video != flag:
                    self.reverse_video(undo=not flag)
                self.modes.reverse_video = flag
            elif mode == 6:
                self.modes.constrain_scrolling = flag
                self.set_term_cursor(0, 0)
            elif mode == 7:
                self.modes.autowrap = flag
            elif mode == 25:
                self.modes.visible_cursor = flag
                self.set_term_cursor()
        else:
            # ECMA-48
            if mode == 3:
                self.modes.display_ctrl = flag
            elif mode == 4:
                self.modes.insert = flag
            elif mode == 20:
                self.modes.lfnl = flag

    def csi_set_modes(self, modes: Iterable[int], qmark: bool, reset: bool = False) -> None:
        """
        Set (DECSET/ECMA-48) or reset modes (DECRST/ECMA-48) if reset is True.
        """
        flag = not reset

        for mode in modes:
            self.set_mode(mode, flag, qmark, reset)

    def csi_set_scroll(self, top: int = 0, bottom: int = 0) -> None:
        """
        Set scrolling region, 'top' is the line number of first line in the
        scrolling region. 'bottom' is the line number of bottom line. If both
        are set to 0, the whole screen will be used (default).
        """
        if not top:
            top = 1
        if not bottom:
            bottom = self.height

        if top < bottom <= self.height:
            self.scrollregion_start = self.constrain_coords(0, top - 1, ignore_scrolling=True)[1]
            self.scrollregion_end = self.constrain_coords(0, bottom - 1, ignore_scrolling=True)[1]

            self.set_term_cursor(0, 0)

    def csi_clear_tabstop(self, mode: Literal[0, 3] | int = 0):
        """
        Clear tabstop at current position or if 'mode' is 3, delete all
        tabstops.
        """
        if mode == 0:
            self.set_tabstop(remove=True)
        elif mode == 3:
            self.set_tabstop(clear=True)

    def csi_get_device_attributes(self, qmark: bool) -> None:
        """
        Report device attributes (what are you?). In our case, we'll report
        ourself as a VT102 terminal.
        """
        if not qmark:
            self.widget.respond(f"{ESC}[?6c")

    def csi_status_report(self, mode: Literal[5, 6] | int) -> None:
        """
        Report various information about the terminal status.
        Information is queried by 'mode', where possible values are:
            5 -> device status report
            6 -> cursor position report
        """
        if mode == 5:
            # terminal OK
            self.widget.respond(f"{ESC}[0n")
        elif mode == 6:
            x, y = self.term_cursor
            self.widget.respond(ESC + '[%d;%dR' % (y + 1, x + 1))

    def csi_erase_line(self, mode: Literal[0, 1, 2] | int) -> None:
        """
        Erase current line, modes are:
            0 -> erase from cursor to end of line.
            1 -> erase from start of line to cursor.
            2 -> erase whole line.
        """
        x, y = self.term_cursor

        if mode == 0:
            self.erase(self.term_cursor, (self.width - 1, y))
        elif mode == 1:
            self.erase((0, y), (x, y))
        elif mode == 2:
            self.blank_line(y)

    def csi_erase_display(self, mode: Literal[0, 1, 2] | int) -> None:
        """
        Erase display, modes are:
            0 -> erase from cursor to end of display.
            1 -> erase from start to cursor.
            2 -> erase the whole display.
        """
        if mode == 0:
            self.erase(self.term_cursor, (self.width - 1, self.height - 1))
        if mode == 1:
            self.erase((0, 0), (self.term_cursor[0] - 1, self.term_cursor[1]))
        elif mode == 2:
            self.clear(cursor=self.term_cursor)

    def csi_set_keyboard_leds(self, mode: Literal[0, 1, 2, 3] | int = 0) -> None:
        """
        Set keyboard LEDs, modes are:
            0 -> clear all LEDs
            1 -> set scroll lock LED
            2 -> set num lock LED
            3 -> set caps lock LED

        This currently just emits a signal, so it can be processed by another
        widget or the main application.
        """
        states = {
            0: 'clear',
            1: 'scroll_lock',
            2: 'num_lock',
            3: 'caps_lock',
        }

        if mode in states:
            self.widget.leds(states[mode])

    def clear(self, cursor: tuple[int, int] | None = None) -> None:
        """
        Clears the whole terminal screen and resets the cursor position
        to (0, 0) or to the coordinates given by 'cursor'.
        """
        self.term = [self.empty_line() for _ in range(self.height)]

        if cursor is None:
            self.set_term_cursor(0, 0)
        else:
            self.set_term_cursor(*cursor)

    def cols(self) -> int:
        return self.width

    def rows(self) -> int:
        return self.height

    def content(
        self,
        trim_left: int = 0,
        trim_right: int = 0,
        cols: int | None = None,
        rows: int | None = None,
        attr=None,
    ):
        if self.scrolling_up == 0:
            yield from self.term
        else:
            buf = self.scrollback_buffer + self.term
            yield from buf[-(self.height+self.scrolling_up):-self.scrolling_up]

    def content_delta(self, other):
        if other is self:
            return [self.cols()]*self.rows()
        return self.content()


class Terminal(Widget):
    _selectable = True
    _sizing = frozenset([BOX])

    signals = ['closed', 'beep', 'leds', 'title']

    def __init__(
        self,
        command: Sequence[str] | Callable[[], ...] | None,
        env: Mapping[str, str] | Iterable[Sequence[str]] | None = None,
        main_loop: event_loop.EventLoop | None = None,
        escape_sequence: str | None = None,
        encoding: str = 'utf-8',
    ):
        """
        A terminal emulator within a widget.

        ``command`` is the command to execute inside the terminal,
        provided as a list of the command followed by its arguments.
        If 'command' is None, the command is the current user's shell.
        You can also provide a callable instead of a command, which will be executed in the subprocess.

        ``env`` can be used to pass custom environment variables. If omitted,
        os.environ is used.

        ``main_loop`` should be provided, because the canvas state machine needs
        to act on input from the PTY master device. This object must have
        watch_file and remove_watch_file methods.

        ``escape_sequence`` is the urwid key symbol which should be used to break
        out of the terminal widget. If it's not specified, ``ctrl a`` is used.

        ``encoding`` specifies the encoding that is being used when local
        keypresses in Unicode are encoded into raw bytes. UTF-8 is used by default.
        Set this to the encoding of your terminal if you need to transmit
        characters to the spawned process in non-UTF8 encoding.
        Applies to Python 3.x only.

        .. note::

            If you notice your Terminal instance is not printing unicode glyphs
            correctly, make sure the global encoding for urwid is set to
            ``utf8`` with ``urwid.set_encoding("utf8")``. See
            :ref:`text-encodings` for more details.
        """
        super().__init__()

        self.escape_sequence = escape_sequence or "ctrl a"

        self.env = dict(env or os.environ)

        self.command = command or [self.env.get('SHELL', '/bin/sh')]

        self.encoding = encoding

        self.keygrab = False
        self.last_key = None

        self.response_buffer: list[str] = []

        self.term_modes = TermModes()

        if main_loop is not None:
            self.main_loop = main_loop
        else:
            self.main_loop = event_loop.SelectEventLoop()

        self.master = None
        self.pid = None

        self.width = None
        self.height = None
        self.term: TermCanvas | None = None
        self.has_focus = False
        self.terminated = False

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates for this terminal
        """
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
        env = self.env
        env['TERM'] = 'linux'

        self.pid, self.master = pty.fork()

        if self.pid == 0:
            if callable(self.command):
                try:
                    try:
                        self.command()
                    except:
                        sys.stderr.write(traceback.format_exc())
                        sys.stderr.flush()
                finally:
                    os._exit(0)
            else:
                os.execvpe(self.command[0], self.command, env)

        if self.main_loop is None:
            fcntl.fcntl(self.master, fcntl.F_SETFL, os.O_NONBLOCK)

        atexit.register(self.terminate)

    def terminate(self) -> None:
        if self.terminated:
            return

        self.terminated = True
        self.remove_watch()
        self.change_focus(False)

        if self.pid > 0:
            self.set_termsize(0, 0)
            for sig in (signal.SIGHUP, signal.SIGCONT, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(self.pid, sig)
                    pid, status = os.waitpid(self.pid, os.WNOHANG)
                except OSError:
                    break

                if pid == 0:
                    break
                time.sleep(0.1)
            try:
                os.waitpid(self.pid, 0)
            except OSError:
                pass

            os.close(self.master)

    def beep(self) -> None:
        self._emit('beep')

    def leds(self, which) -> None:
        self._emit('leds', which)

    def respond(self, string: str) -> None:
        """
        Respond to the underlying application with 'string'.
        """
        self.response_buffer.append(string)

    def flush_responses(self) -> None:
        for string in self.response_buffer:
            os.write(self.master, string.encode('ascii'))
        self.response_buffer = []

    def set_termsize(self, width: int, height: int) -> None:
        winsize = struct.pack("HHHH", height, width, 0, 0)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, winsize)

    def touch_term(self, width: int, height: int) -> None:
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

        self.width = width
        self.height = height

        if process_opened:
            self.add_watch()

    def set_title(self, title) -> None:
        self._emit('title', title)

    def change_focus(self, has_focus) -> None:
        """
        Ignore SIGINT if this widget has focus.
        """
        if self.terminated:
            return

        self.has_focus = has_focus

        if self.term is not None:
            self.term.has_focus = has_focus
            self.term.set_term_cursor()

        if has_focus:
            self.old_tios = RealTerminal().tty_signal_keys()
            RealTerminal().tty_signal_keys(*(['undefined'] * 5))
        else:
            if hasattr(self, "old_tios"):
                RealTerminal().tty_signal_keys(*self.old_tios)

    def render(self, size: tuple[int, int], focus: bool = False):
        if not self.terminated:
            self.change_focus(focus)

            width, height = size
            self.touch_term(width, height)

            if self.main_loop is None:
                self.feed()

        return self.term

    def add_watch(self) -> None:
        if self.main_loop is None:
            return
        self.main_loop.watch_file(self.master, self.feed)

    def remove_watch(self) -> None:
        if self.main_loop is None:
            return
        self.main_loop.remove_watch_file(self.master)

    def wait_and_feed(self, timeout: float = 1.0) -> None:
        while True:
            try:
                select.select([self.master], [], [], timeout)
                break
            except OSError as e:
                if e.args[0] != 4:
                    raise
        self.feed()

    def feed(self) -> None:
        data = EOF

        try:
            data = os.read(self.master, 4096)
        except OSError as e:
            if e.errno == 5:  # EIO, child terminated
                data = EOF
            elif e.errno == errno.EWOULDBLOCK: # empty buffer
                return
            else:
                raise

        if data == EOF:
            self.terminate()
            self._emit('closed')
            return

        self.term.addstr(data)

        self.flush_responses()

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        if self.terminated:
            return key

        if key == "window resize":
            width, height = size
            self.touch_term(width, height)
            return None

        if (self.last_key == self.escape_sequence
            and key == self.escape_sequence):
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
            if key == 'page up':
                self.term.scroll_buffer()
                self.last_key = key
                self._invalidate()
                return None
            elif key == 'page down':
                self.term.scroll_buffer(up=False)
                self.last_key = key
                self._invalidate()
                return None
            elif self.last_key == self.escape_sequence and key != self.escape_sequence:
                # hand down keypress directly after ungrab.
                self.last_key = key
                return key
            elif self.escape_sequence == key:
                # start grabbing the terminal
                self.keygrab = True
                self.last_key = key
                return None
            elif self._command_map[key] is None or key == 'enter':
                # printable character or escape sequence means:
                # lock in terminal...
                self.keygrab = True
                # ... and do key processing
            else:
                # hand down keypress
                self.last_key = key
                return key

        self.last_key = key

        self.term.scroll_buffer(reset=True)

        if key.startswith("ctrl "):
            if key[-1].islower():
                key = chr(ord(key[-1]) - ord('a') + 1)
            else:
                key = chr(ord(key[-1]) - ord('A') + 1)
        else:
            if self.term_modes.keys_decckm and key in KEY_TRANSLATIONS_DECCKM:
                key = KEY_TRANSLATIONS_DECCKM.get(key)
            else:
                key = KEY_TRANSLATIONS.get(key, key)

        # ENTER transmits both a carriage return and linefeed in LF/NL mode.
        if self.term_modes.lfnl and key == "\x0d":
            key += "\x0a"

        key = key.encode(self.encoding, 'ignore')

        os.write(self.master, key)

        return None
