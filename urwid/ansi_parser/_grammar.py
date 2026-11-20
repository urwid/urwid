# Urwid standalone ANSI/VT100 escape-sequence line parser
#    Copyright (C) 2026  urwid contributors
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

"""The escape-sequence grammar both parsers share: the parser states, limits and control character sets."""

from __future__ import annotations

import enum
import typing

from urwid.display.escape import _C0_CONTROLS, BEL, ESC

#: CAN and SUB, which abort an escape sequence in progress.
_CANCEL = frozenset("\x18\x1a")

#: Control characters a terminal ignores inside an OSC string, unless they follow an ESC there: they are neither
#: executed nor part of the string. DEL is not among them: a terminal keeps it in the string.
OSC_IGNORED_CONTROLS = frozenset(map(chr, _C0_CONTROLS)) - {BEL, ESC, *_CANCEL}

#: The control characters ignored inside a DCS, SOS, PM or APC string: those of an OSC string, BEL, which ends only
#: OSC, and DEL, which the VT500 parser model ignores in a DCS string but keeps in an OSC string.
_COMMAND_STRING_IGNORED: typing.Final = OSC_IGNORED_CONTROLS | {BEL, "\x7f"}

#: The final bytes after ESC that open a DCS, SOS, PM and APC string, which are discarded up to their ST.
_COMMAND_STRING_OPENERS: typing.Final = frozenset("PX^_")

#: CSI parameter strings of this length or longer are skipped unparsed. Real sequences are far shorter (a truecolour
#: foreground and background SGR is under 50 characters). Staying below 640, the lowest limit
#: :func:`sys.set_int_max_str_digits` accepts, guarantees ``int()`` never rejects a parameter.
MAX_CSI_LENGTH = 256

#: OSC, DCS, SOS, PM and APC strings of this length or longer are skipped, and the rest of the string up to its
#: terminator, or up to an ESC starting a new sequence, is discarded unbuffered, so an unterminated string costs neither
#: memory nor quadratic string growth.
MAX_OSC_LENGTH = 4096


class ParseState(enum.IntEnum):
    """State of an escape-sequence parser, shared by :class:`AnsiParser` and :class:`~urwid.TermCanvas`.

    The parser is in :attr:`ESCAPE` both right after an ESC and while it reads no sequence at all; its flag for being
    within an escape sequence tells the two apart.
    """

    ESCAPE = 0
    CSI = 1
    OSC = 2
    #: the intermediate bytes of an escape sequence (ECMA-35), such as the "(" of a G0 designation
    ESC_INTERMEDIATE = 3
    #: the discarded rest of an OSC string of :data:`MAX_OSC_LENGTH` or more, up to its terminator
    OSC_OVERFLOW = 4
    #: a DCS, SOS, PM or APC string, which only ST ends
    COMMAND_STRING = 5
    #: the discarded rest of a command string of :data:`MAX_OSC_LENGTH` or more, up to its ST
    COMMAND_STRING_OVERFLOW = 6


#: the states of an OSC string, which BEL or ST ends
_OSC_STATES: typing.Final = frozenset((ParseState.OSC, ParseState.OSC_OVERFLOW))
#: the states of a DCS, SOS, PM or APC string, which only ST ends
_COMMAND_STRING_STATES: typing.Final = frozenset((ParseState.COMMAND_STRING, ParseState.COMMAND_STRING_OVERFLOW))
#: the states of a command string, in which control characters are ignored rather than executed
_STRING_STATES: typing.Final = _OSC_STATES | _COMMAND_STRING_STATES


def _csi_parameters(body: str | bytes | bytearray) -> list[int | None] | None:
    """Return the numeric parameters of the CSI parameter string *body*.

    :returns: one number per ``;``-separated parameter, None for an empty one, so an empty *body* gives ``[None]``;
        None when *body* holds anything but digits and ``;``: a sub-parameter, a private marker or an intermediate byte.

    >>> _csi_parameters("1;;38")
    [1, None, 38]
    >>> _csi_parameters(b"?25") is None
    True
    """
    parameters: list[str] | list[bytes] | list[bytearray]
    if isinstance(body, str):
        if body.strip("0123456789;"):
            return None
        parameters = body.split(";")
    else:
        if body.strip(b"0123456789;"):
            return None
        parameters = body.split(b";")
    return [int(parameter) if parameter else None for parameter in parameters]
