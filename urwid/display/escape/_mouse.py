# Urwid escape sequences common to curses_display and raw_display
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


"""Mouse report bits, flags and byte offsets of the X10 and SGR mouse encodings."""

from __future__ import annotations

import enum
import typing

# This is added to button value to signal mouse release by curses_display
# and raw_display when we know which button was released.  NON-STANDARD
MOUSE_RELEASE_FLAG: typing.Final = 2048

# This 2-bit mask is used to check if the mouse release from curses or gpm
# is a double or triple release. 00 means single click, 01 double,
# 10 triple. NON-STANDARD
MOUSE_MULTIPLE_CLICK_MASK: typing.Final = 1536

# This is added to button value at mouse release to differentiate between
# single, double and triple press. Double release adds this times one,
# triple release adds this times two.  NON-STANDARD
MOUSE_MULTIPLE_CLICK_FLAG: typing.Final = 512


class MouseBit(enum.IntFlag):
    """Bits of the button byte of an X10 or SGR mouse report, as xterm's ctlseqs documents them.

    ``&`` and ``|`` are those of :class:`int` and return a plain :class:`int`.
    The :class:`enum.Flag` operators build a flag object for each operation, which makes decoding a report about
    twenty times slower.
    """

    # The button offset within its group. 3 with neither group flag set means "released" (X10 report only);
    # with either group flag set it is the group's 4th button (7 or 11), which has no release encoding.
    BUTTON = 3
    SHIFT = 4
    META = 8
    CTRL = 16
    DRAG = 32
    HIGH_BUTTON = 64  # set to report buttons 4-7 (e.g. a wheel)
    EXTRA_BUTTON = 128  # set to report buttons 8-11 (e.g. side buttons)

    # int's own operators, typed by the enum as returning a flag
    __and__ = int.__and__  # type: ignore[assignment]
    __rand__ = int.__rand__  # type: ignore[assignment]
    __or__ = int.__or__  # type: ignore[assignment]
    __ror__ = int.__ror__  # type: ignore[assignment]


# MouseBit.DRAG as a plain int, for code outside urwid that reads it
MOUSE_DRAG_FLAG: typing.Final = int(MouseBit.DRAG)  # noqa: FURB123
#: the modifier prefixes of an urwid mouse event, in the order urwid writes them, and their bits in a mouse report
_MOUSE_MODIFIER_PREFIXES: typing.Final = (
    ("shift ", MouseBit.SHIFT),
    ("meta ", MouseBit.META),
    ("ctrl ", MouseBit.CTRL),
)


def _mouse_button(bits: int) -> int:
    """Return the urwid button number the button bits of a mouse report select.

    The numbers are 1 to 3 for the main buttons, 4 to 7 for the wheel and 8 to 11 for the extra buttons.
    The X10 release code, button bits 3 without a button group bit, gives 4; the decoder reports it as a release.
    """
    button_bits = bits & MouseBit.BUTTON
    if bits & MouseBit.EXTRA_BUTTON:
        return 8 + button_bits
    if bits & MouseBit.HIGH_BUTTON:
        return 4 + button_bits
    return 1 + button_bits


# the names of the mouse report bits before MouseBit replaced them
_RENAMED_MOUSE_BITS: typing.Final = {
    "_MOUSE_SHIFT_FLAG": MouseBit.SHIFT,
    "_MOUSE_META_FLAG": MouseBit.META,
    "_MOUSE_CTRL_FLAG": MouseBit.CTRL,
    "_MOUSE_HIGH_BUTTON_FLAG": MouseBit.HIGH_BUTTON,
    "_MOUSE_EXTRA_BUTTON_FLAG": MouseBit.EXTRA_BUTTON,
    "_MOUSE_BUTTON_MASK": MouseBit.BUTTON,
}


# The X10 report encodes the button byte and the two coordinate bytes by adding an offset to
# keep them in the printable ASCII range; coordinates are further offset by 1 since they are
# reported 1-based.
_MOUSE_BYTE_OFFSET: typing.Final = 32
_MOUSE_COORD_OFFSET: typing.Final = 33
# the largest code a terminal sends for one byte of an X10 report
_MOUSE_BYTE_MAX: typing.Final = 255
# the 0-based column or row an X10 report cannot carry: xterm sends it, and any farther one, as a NUL byte,
# which decodes back to this value
MOUSE_X10_PAST_END: typing.Final = 255 - _MOUSE_BYTE_OFFSET
# the codes after ESC that start an X10 report
_NEXT_MOUSE_REPORT: typing.Final = (ord("["), ord("M"))


# longest "Pb;Px;Py" body of an SGR mouse report accepted before its "M"/"m" terminator
_SGR_MOUSE_MAX_LEN: typing.Final = 32
