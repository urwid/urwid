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

"""DEC rectangular area and column control functions of :class:`~urwid.canvas.term.TermCanvas`."""

from __future__ import annotations

import types
import typing

from urwid import util
from urwid.ansi_parser import (
    attrspec_with_hyperlink,
)
from urwid.canvas.term._cells import _BLANK, _RENDITION_BITS, _mend_wide, _Protected
from urwid.canvas.term._editing import _EditingCanvas
from urwid.display._sgr import sgi_params_to_attrspec
from urwid.display.escape import DCS, ST

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Literal

    from urwid.display import AttrSpec


#: the DECRQCRA value xterm gives each character of the DEC special graphics set, by the ASCII byte it is designated
#: with, as measured from xterm 407
_DEC_CHECKSUM_VALUES: typing.Final = types.MappingProxyType(
    dict(
        zip(
            (bytes((code,)) for code in range(0x5F, 0x7F)),
            # the values of "_" to "~", in that order
            bytes.fromhex(
                "00 14 78 0a 0d 0e 0b b0 b1 15 0c 16 17 18 19 1a 1b 1c 1d 1e 1f 80 81 82 83 84 85 86 c6 87 a3 b7"
            ),
            strict=True,
        )
    )
)
#: the DECRQCRA value xterm gives a character with no 7-bit value: U+00A0 and anything past Latin-1
_CHECKSUM_UNMAPPED: typing.Final = 0x1B


#: the DECRQCRA checksum bits of the AttrSpec flags, as xterm adds them to each character
_CHECKSUM_BITS: typing.Final = (("bold", 0x80), ("blink", 0x40), ("standout", 0x20), ("underline", 0x10))


#: the DECRQCRA checksum bit of a protected character
_CHECKSUM_PROTECTED: typing.Final = 0x04


#: the AttrSpec flags DECCARA sets and DECRARA reverses, by SGR parameter, as xterm takes them
_AREA_FLAGS: typing.Final = types.MappingProxyType({sgr: name for name, _bit, sgr in _RENDITION_BITS})
#: the AttrSpec flags DECCARA resets, by SGR parameter
_AREA_FLAG_RESETS: typing.Final = types.MappingProxyType(
    {22: "bold", 24: "underline", 25: "blink", 27: "standout"},
)
#: the DECSACE value that makes DECCARA and DECRARA act on a rectangle rather than on a stream of cells
_ATTRIBUTE_EXTENT_RECTANGLE: typing.Final = 2


def _checksum_value(cell: tuple[AttrSpec | None, Literal["0", "U"] | None, bytes], encoding: str) -> int:
    """Return what a written *cell* adds to a DECRQCRA checksum.

    The values are those :meth:`TermCanvas.csi_request_checksum` describes; a never-written blank is left to the caller.
    """
    attrspec, charset, char = cell
    flags = 0 if attrspec is None else sum(bit for name, bit in _CHECKSUM_BITS if getattr(attrspec, name))
    if charset == "0" and char in _DEC_CHECKSUM_VALUES:
        return _DEC_CHECKSUM_VALUES[char] + flags
    text = char.decode(encoding, "replace")
    # the second half of a wide character counts as a space
    code = ord(text[0]) if text else 0x20
    if code < 0x7F:
        return code + flags
    if 0xA0 < code < 0xFF:
        return (code & 0x7F) + flags
    # DEL, the C1 controls and U+00FF count 0 in xterm
    return (_CHECKSUM_UNMAPPED if code == 0xA0 or code > 0xFF else 0) + flags


def _apply_area_sgr(sgrs: Sequence[int], attrspec: AttrSpec | None) -> AttrSpec | None:
    """Return *attrspec* with the SGR parameters *sgrs* of DECCARA or DECRARA applied, keeping faint.

    SGR 22 also ends faint, which neither control changes, so faint is set again, as xterm keeps it.
    """
    faint = [2] if attrspec is not None and attrspec.faint and 22 in sgrs else []
    return sgi_params_to_attrspec([*sgrs, *faint], attrspec)


class _RectanglesCanvas(_EditingCanvas):
    """Edit rectangular areas and columns of a :class:`~urwid.canvas.term.TermCanvas` screen."""

    __slots__ = ()

    def _rectangle(self, params: Sequence[int | None]) -> tuple[int, int, int, int] | None:
        """Return the rectangle the parameters Pt ; Pl ; Pb ; Pr of a VT420 rectangular area sequence select.

        A missing or zero parameter selects the edge of the page, and a parameter past the edge selects the edge.
        In origin mode the rows count from the top margin and stop at the bottom margin, and the columns count from the
        left margin and stop at the right margin, as in xterm.

        :returns: the 0-based top row, left column, bottom row and right column, all included, or None for a rectangle
            whose top is below its bottom or whose left is right of its right.
        """
        top, left, bottom, right = (*params, None, None, None, None)[:4]
        if self.modes.constrain_scrolling:
            first, last = self.scrollregion_start, self.scrollregion_end
            first_col, last_col = self.margin_left, self.margin_right
        else:
            first, last = 0, self.height - 1
            first_col, last_col = 0, self.width - 1
        top_row = min(first + (top or 1) - 1, last)
        bottom_row = last if not bottom else min(first + bottom - 1, last)
        left_col = min(first_col + (left or 1) - 1, last_col)
        right_col = last_col if not right else min(first_col + right - 1, last_col)
        if top_row > bottom_row or left_col > right_col:
            return None
        return top_row, left_col, bottom_row, right_col

    def csi_fill_rectangle(self, params: Sequence[int | None]) -> None:
        """Fill a rectangle with a character in the current attributes (DECFRA, CSI Pch ; Pt ; Pl ; Pb ; Pr $ x).

        The character code is a printable ASCII or Latin-1 one, 32 to 126 or 160 to 255, and any other is ignored.
        """
        code = params[0] if params else None
        if code is None or not (32 <= code <= 126 or 160 <= code <= 255):
            return
        if (area := self._rectangle(params[1:])) is None:
            return
        top, left, bottom, right = area
        char = chr(code).encode(util.get_encoding(), "urwid_fallback_ascii")
        cell = (self.attrspec, self.charset.current, _Protected(char) if self.protected else char)
        for y in range(top, bottom + 1):
            line = self.term[y]
            line[left : right + 1] = [cell] * (right - left + 1)
            _mend_wide(line, left)
            _mend_wide(line, right + 1)

    def csi_erase_rectangle(self, params: Sequence[int | None]) -> None:
        """Erase a rectangle to spaces in the current attributes (DECERA, CSI Pt ; Pl ; Pb ; Pr $ z).

        Unlike erasing in a line, the spaces keep the attribute flags, such as reverse video, and DECSCA protects them
        as written characters, as in xterm.
        """
        if (area := self._rectangle(params)) is None:
            return
        top, left, bottom, right = area
        attrspec = self.attrspec
        if attrspec is not None and attrspec.hyperlink is not None:
            attrspec = attrspec_with_hyperlink(attrspec, None, unset_color="default")
        cell = (attrspec, self.charset.current, _Protected(b" ") if self.protected else b" ")
        for y in range(top, bottom + 1):
            line = self.term[y]
            line[left : right + 1] = [cell] * (right - left + 1)
            _mend_wide(line, left)
            _mend_wide(line, right + 1)

    def csi_selective_erase_rectangle(self, params: Sequence[int | None]) -> None:
        """Erase the characters DECSCA did not protect in a rectangle (DECSERA, CSI Pt ; Pl ; Pb ; Pr $ {).

        Each erased cell keeps its own attributes and holds a written space, as xterm draws it.
        After SPA, as in xterm, the protected characters are erased too.
        """
        if (area := self._rectangle(params)) is None:
            return
        top, left, bottom, right = area
        for y in range(top, bottom + 1):
            line = self.term[y]
            for x in range(left, right + 1):
                attrspec, charset, char = line[x]
                if self.modes.iso_protection or not isinstance(char, _Protected):
                    line[x] = (attrspec, charset, b" ")
            _mend_wide(line, left)
            _mend_wide(line, right + 1)

    def _change_area_attributes(
        self,
        params: Sequence[int | None],
        change: Callable[[AttrSpec | None], AttrSpec | None],
    ) -> None:
        """Replace the attributes of the cells DECCARA or DECRARA select with what *change* returns for them.

        The area is the rectangle Pt ; Pl ; Pb ; Pr in *params*, or with DECSACE in stream mode the cells from its top
        left to its bottom right, wrapping at the right edge.
        As in xterm, the stream skips the cells never written, and the rectangle makes them written spaces.
        """
        if (area := self._rectangle(params)) is None:
            return
        top, left, bottom, right = area
        rectangle = self.attribute_extent == _ATTRIBUTE_EXTENT_RECTANGLE
        # a screen holds few distinct attributes, so each is changed once
        changed: dict[AttrSpec | None, AttrSpec | None] = {}
        for y in range(top, bottom + 1):
            line = self.term[y]
            first = left if rectangle or y == top else 0
            last = right if rectangle or y == bottom else self.width - 1
            for x in range(first, last + 1):
                attrspec, charset, char = line[x]
                if char is _BLANK:
                    if not rectangle:
                        continue
                    char = b" "
                if attrspec not in changed:
                    changed[attrspec] = change(attrspec)
                line[x] = (changed[attrspec], charset, char)

    def csi_change_area_attributes(self, params: Sequence[int | None]) -> None:
        """Set or reset attributes in an area (DECCARA, CSI Pt ; Pl ; Pb ; Pr ; Ps ... $ r).

        Each Ps, in order, sets bold (1), underline (4), blink (5) or reverse video (7), resets one of them (22, 24, 25,
        27), or resets all four (0); others, such as xterm's concealed (8), are ignored, as in xterm.
        The attributes change as SGR changes them, so bold brightens a basic colour here too, and faint is kept.
        :meth:`_change_area_attributes` describes the area.
        """
        sgrs: list[int] = []
        for sgr in (sgr for sgr in params[4:] if sgr is not None):
            if sgr == 0:
                sgrs.extend(_AREA_FLAG_RESETS)
            elif sgr in _AREA_FLAGS or sgr in _AREA_FLAG_RESETS:
                sgrs.append(sgr)
        self._change_area_attributes(params[:4], lambda attrspec: _apply_area_sgr(sgrs, attrspec))

    def csi_reverse_area_attributes(self, params: Sequence[int | None]) -> None:
        """Reverse attributes in an area (DECRARA, CSI Pt ; Pl ; Pb ; Pr ; Ps ... $ t).

        Each Ps, in order, reverses bold (1), underline (4), blink (5) or reverse video (7), or all four (0); others,
        such as xterm's concealed (8), are ignored, as in xterm.
        The attributes change as SGR changes them, so bold brightens a basic colour here too, and faint is kept.
        :meth:`_change_area_attributes` describes the area.
        """
        names: list[str] = []
        for sgr in (sgr for sgr in params[4:] if sgr is not None):
            if sgr == 0:
                names.extend(_AREA_FLAGS.values())
            elif sgr in _AREA_FLAGS:
                names.append(_AREA_FLAGS[sgr])
        # reversing a flag twice leaves it as it was
        reversed_flags = [(sgr, name) for sgr, name in _AREA_FLAGS.items() if names.count(name) % 2]
        resets = {name: sgr for sgr, name in _AREA_FLAG_RESETS.items()}
        self._change_area_attributes(
            params[:4],
            lambda attrspec: _apply_area_sgr(
                [
                    resets[name] if attrspec is not None and getattr(attrspec, name) else sgr
                    for sgr, name in reversed_flags
                ],
                attrspec,
            ),
        )

    def csi_select_attribute_extent(self, params: Sequence[int | None]) -> None:
        """Make DECCARA and DECRARA act on a rectangle (2) or on a stream of cells (DECSACE, CSI Ps * x).

        Any value is kept for DECRQSS to report, as in xterm, and only 2 selects the rectangle.
        """
        self.attribute_extent = params[0] or 0

    def csi_copy_rectangle(self, params: Sequence[int | None]) -> None:
        """Copy a rectangle to another place on the screen (DECCRA).

        The sequence is ``CSI Pts ; Pls ; Pbs ; Prs ; Pps ; Ptd ; Pld ; Ppd $ v``: the source rectangle and page, then
        the destination's top left corner and page.
        The pages are ignored, since there is one, and a copy past the screen edge is cut there.
        """
        if (area := self._rectangle(params[:4])) is None:
            return
        top, left, bottom, right = area
        if (destination := self._rectangle([*params[5:7], None, None])) is None:
            return
        to_top, to_left, last, _right = destination
        rows = [self.term[y][left : right + 1] for y in range(top, bottom + 1)]
        for offset, cells in enumerate(rows[: last - to_top + 1]):
            fitting = cells[: self.width - to_left]
            line = self.term[to_top + offset]
            line[to_left : to_left + len(fitting)] = fitting
            _mend_wide(line, to_left)
            _mend_wide(line, to_left + len(fitting))

    def csi_request_checksum(self, params: Sequence[int | None]) -> None:
        """Answer DECRQCRA (``CSI Pid ; Pp ; Pt ; Pl ; Pb ; Pr * y``) with ``DCS Pid ! ~ XXXX ST``.

        The checksum is xterm's: the negated 16-bit sum of each written cell's character value plus the bits of bold
        (0x80), blink (0x40), reverse (0x20), underline (0x10) and DECSCA protection (0x04), with a cell never written,
        such as an erased one, counting 0.
        The character value is the code of an ASCII character, the low 7 bits of a Latin-1 one, 0x1B for U+00A0 and
        anything past Latin-1, 0 for DEL, the C1 controls and U+00FF, and xterm's own value for a DEC special graphics
        character; the second half of a wide character counts as a space, and a character with no width joined to
        another adds nothing.

        A box drawing character written in UTF-8 differs from xterm: this canvas stores it as the DEC graphics
        character, valued as one.

        Without parameters it is not answered, and an empty Pid is 65535, as in xterm.
        It is not answered at the VT100 level (61).
        """
        if self.conformance_level == 61 or params == [None]:
            return
        request = 0xFFFF if params[0] is None else params[0]
        if (area := self._rectangle(params[2:])) is None:
            return
        top, left, bottom, right = area
        encoding = util.get_encoding()
        # a screen holds few distinct cells, so each is valued once per request
        values: dict[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes], int] = {}
        total = 0
        for y in range(top, bottom + 1):
            for cell in self.term[y][left : right + 1]:
                # a never-written blank is equal to a written space, so it is told apart before the cache
                if cell[2] is _BLANK:
                    continue
                value = values.get(cell)
                if value is None:
                    value = _checksum_value(cell, encoding)
                    values[cell] = value
                # a protected character is equal to the same one unprotected, so its bit is added after the cache
                total += value + (_CHECKSUM_PROTECTED if isinstance(cell[2], _Protected) else 0)
        self.widget.respond(f"{DCS}{request:d}!~{-total & 0xFFFF:04X}{ST}")

    def csi_insert_columns(self, params: Sequence[int | None]) -> None:
        """Insert blank columns at the cursor column in the scrolling region (DECIC, CSI Ps ' }).

        The columns up to the right margin move, and those pushed past it are dropped.
        Nothing happens while the cursor is outside the scrolling region or the left and right margins.
        """
        x, y = self.term_cursor
        if self.scrollregion_start <= y <= self.scrollregion_end and self.margin_left <= x <= self.margin_right:
            for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                self.insert_chars((x, row), chars=params[0] or 1)

    def csi_delete_columns(self, params: Sequence[int | None]) -> None:
        """Delete columns at the cursor column in the scrolling region (DECDC, CSI Ps ' ~).

        The columns up to the right margin move, and blank ones fill the place before it.
        Nothing happens while the cursor is outside the scrolling region or the left and right margins.
        """
        x, y = self.term_cursor
        if self.scrollregion_start <= y <= self.scrollregion_end and self.margin_left <= x <= self.margin_right:
            for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                self.remove_chars((x, row), chars=params[0] or 1)

    def back_index(self) -> None:
        """Move the cursor one column left, or at the left margin insert a blank column there (DECBI)."""
        x, y = self.term_cursor
        if x == self.margin_left:
            self.csi_insert_columns([1])
        elif x > 0:
            self.set_term_cursor(x - 1, y)
        self.is_rotten_cursor = False

    def forward_index(self) -> None:
        """Move the cursor one column right, or at the right margin delete the column at the left margin (DECFI).

        Right of the right margin, the cursor stops at the screen's right edge.
        A pending wrap stays, as in xterm.
        """
        x, y = self.term_cursor
        if x == self.margin_right:
            if self.scrollregion_start <= y <= self.scrollregion_end:
                for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                    self.remove_chars((self.margin_left, row))
        elif x < self.width - 1:
            self.set_term_cursor(x + 1, y)
