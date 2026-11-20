# Urwid terminal emulation canvas
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

"""Cursor movement, text output and editing control functions of :class:`~urwid.canvas.term.TermCanvas`."""

from __future__ import annotations

import typing

from urwid import str_util
from urwid.canvas.term._cells import _drawn_width, _mend_wide, _Protected
from urwid.canvas.term._screen import _ScreenCanvas
from urwid.str_util import _MAX_CLUSTER_LENGTH, _continues_cluster

#: the largest count REP takes, xterm's largest parameter value; a larger one counts as this
_MAX_REPEAT: typing.Final = 65535


class _EditingCanvas(_ScreenCanvas):
    """Move the cursor, write characters and edit lines of a :class:`~urwid.canvas.term.TermCanvas` screen."""

    __slots__ = ()

    def linefeed(self, reverse: bool = False) -> None:
        """Move the cursor down (or up if reverse is True) one line but don't reset horizontal position."""
        x, y = self.term_cursor

        if reverse:
            if y <= 0 < self.scrollregion_start:
                pass
            elif y == self.scrollregion_start:
                self.scroll(reverse=True)
            else:
                y -= 1
        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            if y >= self.height - 1 > self.scrollregion_end:
                pass
            elif y == self.scrollregion_end:
                self.scroll()
            else:
                y += 1

        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def carriage_return(self) -> None:
        """Move the cursor to column 0 of the current line.

        A pending wrap ends, as in xterm.
        """
        self.set_term_cursor(0, self.term_cursor[1])
        self.is_rotten_cursor = False

    def newline(self) -> None:
        """Do a carriage return followed by a line feed."""
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
        """Move cursor to position x/y while constraining terminal sizes.

        If 'relative' is True, x/y is relative to the current cursor position.
        'relative_x' and 'relative_y' is the same but just with the corresponding axis.
        """
        if relative:
            relative_y = relative_x = True

        if relative_x:
            x += self.term_cursor[0]

        if relative_y:
            y += self.term_cursor[1]
        elif self.modes.constrain_scrolling:
            y += self.scrollregion_start

        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def push_char(self, char: bytes | None, x: int, y: int, *, dec_special: bool = False) -> None:
        """Push one character to current position and advance cursor to x/y.

        :param char: the character to store, or ``None`` to only move the cursor.
        :param x: the column to move the cursor to.
        :param y: the row to move the cursor to.
        :param dec_special: *char* is already in the DEC special character set: store it there, unmapped.
        """
        if char is not None:
            if not dec_special:
                char = self.charset.apply_mapping(char)
            if self.modes.insert:
                self.insert_chars(char=char, dec_special=dec_special)
            else:
                self.set_char(char, dec_special=dec_special)
            self.charset.end_single_shift()

        self.set_term_cursor(x, y)

    def push_cursor(self, char: bytes | None = None, *, dec_special: bool = False) -> None:
        """Move cursor one character forward wrapping lines as needed.

        If 'char' is given, put the character into the former position.

        :param char: the character to put into the former position, if any.
        :param dec_special: *char* is already in the DEC special character set: store it there, unmapped.
        """
        x, y = self.term_cursor
        if char is not None:
            self._last_graphic = (char, dec_special, False)

        if self.modes.autowrap:
            if x + 1 >= self.width and not self.is_rotten_cursor:
                # "rotten cursor" - this is when the cursor gets to the rightmost
                # position of the screen, the cursor position remains the same but
                # one last set_char() is allowed for that piece of sh^H^H"border".
                self.is_rotten_cursor = True
                self.push_char(char, x, y, dec_special=dec_special)
            else:
                x += 1

                if x >= self.width and self.is_rotten_cursor:
                    # as a line feed: only the bottom row of the scrolling region scrolls it
                    if y == self.scrollregion_end:
                        self.scroll()
                    else:
                        y += 1

                    x = 1

                    self.set_term_cursor(0, y)

                self.push_char(char, x, y, dec_special=dec_special)

                self.is_rotten_cursor = False
        else:
            # as in xterm, a write in the last column leaves a pending wrap, which only autowrap acts on
            self.is_rotten_cursor = x + 1 >= self.width
            if not self.is_rotten_cursor:
                x += 1

            self.push_char(char, x, y, dec_special=dec_special)

    def push_wide_char(self, char: bytes) -> None:
        """Write a character two columns wide at the cursor and move the cursor past it, as xterm does.

        It takes the cursor cell and the one after it, which holds an empty string.
        A character that does not fit before the right edge moves to the next line first with autowrap, and is dropped
        without it.

        :param char: the character, in urwid's encoding.
        """
        self._last_graphic = (char, False, True)
        x, y = self.term_cursor
        if self.width < 2 or (not self.modes.autowrap and x + 1 >= self.width):
            return
        if self.modes.autowrap and x + 1 >= self.width:
            # as a line feed: only the bottom row of the scrolling region scrolls it
            if y == self.scrollregion_end:
                self.scroll()
            else:
                y += 1
            self.set_term_cursor(0, y)
            x, y = self.term_cursor
        if self.modes.insert:
            self.insert_chars(chars=2)
        char = self.charset.apply_mapping(char)
        if self.protected:
            char = _Protected(char)
        tail = _Protected(b"") if self.protected else b""
        line = self.term[y]
        line[x : x + 2] = [(self.attrspec, self.charset.current, char), (self.attrspec, self.charset.current, tail)]
        _mend_wide(line, x)
        _mend_wide(line, x + 2)
        self.charset.end_single_shift()
        # in the last two columns the cursor stays on the second half, with a pending wrap
        self.set_term_cursor(min(x + 2, self.width - 1), y)
        self.is_rotten_cursor = x + 2 >= self.width

    def combine_char(self, char: bytes, text: str, *, width: int | None = None) -> bool:
        """Join *char* to the character before the cursor when it continues its grapheme cluster.

        A cell holds a grapheme cluster, as urwid's width calculation measures one, so a combining accent, a zero
        width joiner and the emoji after it, a variation selector, a skin tone modifier and the second regional
        indicator of a flag join the character before them.
        A character with no width that starts a cluster of its own joins it too, as a cell cannot hold it alone.
        After a character was written in the last column, the character before the cursor is the one under it.
        It is joined also when the cursor was moved there, as a text editor joins a character to the text before it.
        A cluster the display draws one column wider than its character, such as a heart with an emoji variation
        selector, takes the next cell as its second half, and the cursor moves past it; in the last column it moves to
        the next line with autowrap, as in kitty.

        It does not join the cluster:

        - when the cluster would hold more than :data:`urwid.str_util._MAX_CLUSTER_LENGTH` code points;
        - when it would be drawn wider than two columns or narrower than before, as Hangul jamo that do not make a
          syllable can be;
        - when it would be drawn wider in the last column without autowrap, or on a screen one column wide;
        - when the character before the cursor is a DEC special graphics character, which the display draws in a
          character set without it, or there is no character before the cursor.

        Such a character takes a cell of its own, or is dropped when it has no width.

        :param char: the character, in urwid's encoding, which is UTF-8 for any character to join.
        :param text: the character as text.
        :param width: the columns the display draws *char* alone in, when the caller has measured it.
        :returns: whether the character was joined or dropped, and so takes no cell of its own.
        """
        if str_util.get_byte_encoding() != "utf8":
            return False
        if width is None:
            width = _drawn_width(char)
        x, y = self.term_cursor
        if not (self.is_rotten_cursor and x == self.width - 1):
            x -= 1
        if x < 0:
            return width == 0
        line = self.term[y]
        if not line[x][2]:
            # the second half of a wide character: the first half holds it
            x -= 1
        attrspec, charset, cell = line[x]
        held = cell.decode("utf-8", "replace")
        if charset == "0" or not (width == 0 or _continues_cluster(held, text)):
            return width == 0
        joined = bytes(cell) + char
        old_width, new_width = _drawn_width(cell), _drawn_width(joined)
        if len(held) + len(text) > _MAX_CLUSTER_LENGTH or new_width not in {old_width, 2}:
            return width == 0
        protected = isinstance(cell, _Protected)
        if new_width != old_width and x + 1 >= self.width:
            if not self.modes.autowrap or self.width < 2:
                return width == 0
            # as in kitty, the cluster moves to the next line, as a wide character that does not fit does
            line[x] = self.empty_char()
            # the cluster is no character of its own for REP, which repeats its base character
            base = self._last_graphic
            self.push_wide_char(joined)
            self._last_graphic = base
            row = self.term[self.term_cursor[1]]
            row[0] = (attrspec, charset, _Protected(joined) if protected else joined)
            row[1] = (attrspec, charset, _Protected(b"") if protected else b"")
            return True
        if new_width != old_width:
            if self.modes.insert:
                self.insert_chars((x + 1, y))
            line[x + 1] = (attrspec, charset, _Protected(b"") if protected else b"")
            _mend_wide(line, x + 2)
            self.set_term_cursor(min(x + 2, self.width - 1), y)
            self.is_rotten_cursor = x + 2 >= self.width
        line[x] = (attrspec, charset, _Protected(joined) if protected else joined)
        return True

    def tab(self, tabstop: int = 8) -> None:
        """Move cursor to the next 'tabstop', leaving the cells it passes unchanged.

        As in xterm, a pending wrap stays, and the cursor does not move.
        """
        if self.is_rotten_cursor:
            return
        x, y = self.term_cursor

        while x < self.width - 1:
            x += 1

            if self.is_tabstop(x):
                break

        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def csi_forward_tab(self, count: int) -> None:
        """Move the cursor to the *count*-th next tab stop (CHT), or to the last column when there are fewer.

        As in xterm, a pending wrap stays, and the cursor does not move.
        """
        for _ in range(min(count, self.width)):
            self.tab()

    def csi_backward_tab(self, count: int) -> None:
        """Move the cursor to the *count*-th tab stop before it (CBT), or to the first column when there are fewer.

        As in xterm, a pending wrap stays, and the cursor does not move.
        """
        if self.is_rotten_cursor:
            return
        x, y = self.term_cursor
        for _ in range(min(count, self.width)):
            while x > 0:
                x -= 1
                if self.is_tabstop(x):
                    break
        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def csi_repeat(self, count: int) -> None:
        """Write the character written just before this sequence *count* more times (REP), as xterm does.

        As in xterm:

        - the character is the one that took a cell of its own, also when combining characters joined it;
        - nothing is written when anything else came just before the sequence, such as a control character,
          another control function or another REP;
        - the count is at most 65535.

        Once a screen and one more line are written, every full line of copies more leaves the screen as it was, so the
        count is reduced past that by whole lines.
        The screen and the cursor end as with the whole count, and the lines left out are not added to the scrollback.
        """
        if self._repeat_graphic is None:
            return
        char, dec_special, wide = self._repeat_graphic
        self._repeat_graphic = None
        count = min(count, _MAX_REPEAT)
        per_line = max(self.width // 2, 1) if wide else self.width
        limit = per_line * (self.height + 1)
        if count > limit:
            count = limit + (count - limit) % per_line
        for _ in range(count):
            if wide:
                self.push_wide_char(char)
            else:
                self.push_cursor(char, dec_special=dec_special)
        # the copies are no character written just before a REP that follows
        self._last_graphic = None

    def csi_scroll(self, lines: int, *, reverse: bool = False) -> None:
        """Scroll the scrolling region up by *lines*, or down with *reverse*.

        This is SU (``CSI Ps S``), and SD (``CSI Ps T`` and ``CSI Ps ^``).
        The cursor and a pending wrap stay.
        As in xterm, the lines scrolled off the top are not saved in the scrollback.
        """
        for _ in range(min(lines, self.scrollregion_end - self.scrollregion_start + 1)):
            self.scroll(reverse=reverse, scrollback=False)

    def csi_set_scroll(self, top: int = 0, bottom: int = 0) -> None:
        """Set scrolling region, 'top' is the line number of first line in the scrolling region.

        'bottom' is the line number of bottom line. If both are set to 0, the whole screen will be used (default).
        """
        if not top:
            top = 1
        if not bottom:
            bottom = self.height

        if top < bottom <= self.height:
            self.scrollregion_start = self.constrain_coords(0, top - 1, ignore_scrolling=True)[1]
            self.scrollregion_end = self.constrain_coords(0, bottom - 1, ignore_scrolling=True)[1]

            self.set_term_cursor(0, 0)
            self.is_rotten_cursor = False

    def csi_clear_tabstop(self, mode: int = 0) -> None:
        """Clear tabstop at current position or if 'mode' is 3, delete all tabstops."""
        if mode == 0:
            self.set_tabstop(remove=True)
        elif mode == 3:
            self.set_tabstop(clear=True)

    def csi_erase_line(self, mode: int, *, selective: bool = False) -> None:
        """Erase current line.

        Modes are:

            0 -> erase from cursor to end of line.
            1 -> erase from start of line to cursor.
            2 -> erase whole line.

        With *selective*, as DECSEL, the protected characters are kept.
        """
        x, y = self.term_cursor

        if mode == 0:
            self.erase(self.term_cursor, (self.width - 1, y), selective=selective)
        elif mode == 1:
            self.erase((0, y), (x, y), selective=selective)
        elif mode == 2:
            self.erase((0, y), (self.width - 1, y), selective=selective)

    def csi_erase_display(self, mode: int, *, selective: bool = False) -> None:
        """Erase display.

        Modes are:

            0 -> erase from cursor to end of display.
            1 -> erase from start to cursor.
            2 -> erase the whole display.

        The rows outside the scrolling region are erased in origin mode too, as in xterm.
        With *selective*, as DECSED, the protected characters are kept.
        """
        top_left = (0, 0, True)
        bottom_right = (self.width - 1, self.height - 1, True)
        cursor = (*self.term_cursor, True)
        if mode == 0:
            self.erase(cursor, bottom_right, selective=selective)
        elif mode == 1:
            self.erase(top_left, cursor, selective=selective)
        elif mode == 2:
            self.erase(top_left, bottom_right, selective=selective)
