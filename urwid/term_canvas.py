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

"""Terminal emulation canvas holding a terminal's screen, scrollback and escape sequence parser.

The module imports nothing platform-specific, so it works where :mod:`urwid.vterm`, which runs a child process on a
pty, does not.
"""

from __future__ import annotations

import copy
import functools
import types
import typing
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field

import wcwidth

from urwid import _deprecation, str_util, util, version
from urwid.ansi_parser import (
    MAX_CSI_LENGTH,
    MAX_OSC_LENGTH,
    OSC_IGNORED_CONTROLS,
    attrspec_with_hyperlink,
    led_state,
    parse_sgr_parameters,
    resolve_osc_hyperlink,
    resolve_osc_title,
    sgi_params_to_attrspec,
    split_sgr_parameters,
)
from urwid.canvas import Canvas
from urwid.display import AttrSpec
from urwid.display.escape import (
    ALT_DEC_SPECIAL_CHARS,
    DEC_SPECIAL_CHARS,
    KittyKeyboardFlag,
    PrivateMode,
    window_size_report,
)

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
    from typing import Literal

    # Imported by name for type checkers, see urwid._deprecation.
    from typing_extensions import deprecated

    class _TermCanvasOwner(typing.Protocol):
        """Widget a :class:`TermCanvas` belongs to: it holds the modes and takes what the terminal reports."""

        term_modes: TermModes

        def respond(self, string: str) -> None:
            """Answer a query in the data, as a terminal writes the reply to its child's input."""

        def set_title(self, title: str) -> None:
            """Take the window title the data set."""

        def beep(self) -> None:
            """Take a bell in the data."""

        def leds(self, which: Literal["clear", "scroll_lock", "num_lock", "caps_lock"]) -> None:
            """Take a keyboard LED change in the data."""

else:
    from urwid._deprecation import deprecated

__all__ = (
    "CHARSET_DEFAULT",
    "CHARSET_UTF8",
    "CSI_COMMANDS",
    "ESC",
    "ESC_B",
    "CSIAlias",
    "CSICommand",
    "TermCanvas",
    "TermCharset",
    "TermModes",
)

ESC = chr(27)
ESC_B = b"\x1b"

#: :data:`urwid.ansi_parser.OSC_IGNORED_CONTROLS` as bytes
_OSC_IGNORED = frozenset(char.encode("ascii") for char in OSC_IGNORED_CONTROLS)
#: the controls ignored inside a DCS, SOS, PM or APC string: those of an OSC string, and BEL, which ends only OSC
_COMMAND_STRING_IGNORED: typing.Final = _OSC_IGNORED | {b"\a"}

#: the parser states of a command string: OSC (2), the discarded rest of an over-long OSC (4), and DCS, SOS, PM or APC
#: (5), which ST alone ends
_STRING_STATES: typing.Final = frozenset((2, 4, 5))

#: the final bytes after ESC that open a DCS, SOS, PM and APC string
_COMMAND_STRING_OPENERS: typing.Final = frozenset((b"P", b"X", b"^", b"_"))

#: the Primary DA reply: a VT320 (63) with selective erase (6) and ANSI colour (22)
_PRIMARY_DEVICE_ATTRIBUTES: typing.Final = f"{ESC}[?63;6;22c"
#: the Secondary DA reply, as a VT320 sends it: the VT320 (24), firmware version 1.0 (10), no ROM cartridge (0)
_SECONDARY_DEVICE_ATTRIBUTES: typing.Final = f"{ESC}[>24;10;0c"

#: the Tertiary DA reply (DECRPTUI): the unit ID, zero as in xterm
_TERTIARY_DEVICE_ATTRIBUTES: typing.Final = f"{ESC}P!|00000000{ESC}\\"

#: the cursor styles DECSCUSR sets: 1 and 2 a blinking and a steady block, 3 and 4 underline, 5 and 6 a bar
_CURSOR_STYLES: typing.Final = range(1, 7)
#: the cursor styles drawn underlined; the others, a block or a bar, are drawn in reverse video
_UNDERLINE_CURSOR_STYLES: typing.Final = frozenset((3, 4))
#: the cursor style DECRQSS reports before a DECSCUSR, a steady block, as xterm reports its startup one
_DEFAULT_CURSOR_STYLE: typing.Final = 2

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

#: the states the DEC private modes this canvas keeps no flag for are reported in, by DECRQM:
#: 4 is permanently reset, as setting them has no effect: smooth scrolling (DECSCLM, 4) and autorepeat (DECARM, 8),
#: which the display decides, printing (DECPFF 18, DECPEX 19), as no printer is attached, and the national replacement
#: character sets (DECNRCM, 42), DECKBUM (68) and the margins (DECLRMM, 69), which are not implemented;
#: and so are cursor blinking (12), which the cursor drawn is never shown with, and the urxvt mouse encoding (1015),
#: which is never used;
#: 3 is permanently set, for ANSI mode (DECANM, 2), as VT52 mode is not implemented, and for Meta and Alt sending ESC
#: (1036, 1039), as the keys are always sent that way;
#: 2 is reset, for 132 columns (DECCOLM, 3), as xterm reports it without its c132 resource
_FIXED_PRIVATE_MODE_STATES: typing.Final = types.MappingProxyType(
    {2: 3, 3: 2, **dict.fromkeys((4, 8, 12, 18, 19, 42, 68, 69, 1015), 4), **dict.fromkeys((1036, 1039), 3)},
)

#: the DECRQCRA checksum bits of the AttrSpec flags, as xterm adds them to each character
_CHECKSUM_BITS: typing.Final = (("bold", 0x80), ("blink", 0x40), ("standout", 0x20), ("underline", 0x10))
#: the code points a cell holds at most, which bounds the cost of joining a long run of combining marks; more are
#: dropped
_MAX_CLUSTER_LENGTH: typing.Final = 32

#: the DECRQCRA checksum bit of a protected character
_CHECKSUM_PROTECTED: typing.Final = 0x04

#: the colors of the palette SGR 38;5 and 48;5 select from, and the colors of a display that draws any RGB color
_PALETTE_COLORS: typing.Final = 256
_TRUE_COLORS: typing.Final = 2**24

#: the largest count REP takes, xterm's largest parameter value; a larger one counts as this
_MAX_REPEAT: typing.Final = 65535

#: the conformance levels DECSCL selects: VT100 (61), VT200 (62) and VT300 (63), the highest and the startup one
_CONFORMANCE_LEVELS: typing.Final = range(61, 64)

#: the DECCIR rendition bits of the AttrSpec flags, and the SGR parameters DECRSPS sets them with
_RENDITION_BITS: typing.Final = (("bold", 1, 1), ("underline", 2, 4), ("blink", 4, 5), ("standout", 8, 7))
#: the AttrSpec flags DECCARA sets and DECRARA reverses, by SGR parameter, as xterm takes them
_AREA_FLAGS: typing.Final = types.MappingProxyType({sgr: name for name, _bit, sgr in _RENDITION_BITS})
#: the AttrSpec flags DECCARA resets, by SGR parameter
_AREA_FLAG_RESETS: typing.Final = types.MappingProxyType(
    {22: "bold", 24: "underline", 25: "blink", 27: "standout"},
)
#: the DECSACE value that makes DECCARA and DECRARA act on a rectangle rather than on a stream of cells
_ATTRIBUTE_EXTENT_RECTANGLE: typing.Final = 2
#: the DECCIR flag bits: origin mode, a pending SS2, a pending SS3, and a pending autowrap
_FLAG_ORIGIN: typing.Final = 1
_FLAG_SS2: typing.Final = 2
_FLAG_SS3: typing.Final = 4
_FLAG_WRAP: typing.Final = 8

#: the states the ANSI modes this canvas keeps no flag for are reported in, by DECRQM: 4 is permanently reset, for
#: KAM (keyboard locked) and the ECMA-48 modes of a VT320 that keep their reset state, as xterm reports them, and 3 is
#: permanently set, for SRM (no local echo)
_FIXED_ANSI_MODE_STATES: typing.Final = types.MappingProxyType(
    {2: 4, 12: 3, **dict.fromkeys((1, 5, 7, 10, 11, 13, 14, 15, 16, 17, 18, 19), 4)},
)

#: the SGR parameters of the attribute flags of an AttrSpec
_SGR_FLAGS: typing.Final = (
    ("bold", 1),
    ("faint", 2),
    ("italics", 3),
    ("underline", 4),
    ("blink", 5),
    ("standout", 7),
    ("strikethrough", 9),
)
#: the names of those flags in an AttrSpec foreground
_FLAG_NAMES: typing.Final = frozenset(name for name, _code in _SGR_FLAGS)

#: the character set slot each intermediate byte of a 94-character set designation (ESC I F) selects
_DESIGNATED_SLOTS: typing.Final = types.MappingProxyType({b"(": 0, b")": 1, b"*": 2, b"+": 3})
#: the slot each intermediate byte of a 96-character set designation selects
_DESIGNATED_96_SLOTS: typing.Final = types.MappingProxyType({b"-": 1, b".": 2, b"/": 3})
#: the TermCharset name of each designated final byte; any other final byte is drawn as the default set
_DESIGNATED_CHARSETS: typing.Final = types.MappingProxyType({b"0": "vt100", b"U": "ibmpc", b"K": "user"})
#: the final byte each TermCharset name is reported with, the inverse of _DESIGNATED_CHARSETS, ASCII for the default
_CHARSET_FINALS: typing.Final = types.MappingProxyType({"default": b"B", "vt100": b"0", "ibmpc": b"U", "user": b"K"})
#: the final bytes after ESC of the locking shifts into GR: LS1R, LS2R and LS3R
_GR_LOCKING_SHIFTS: typing.Final = types.MappingProxyType({b"~": 1, b"}": 2, b"|": 3})

#: the final bytes after ESC of the locking shifts LS2 and LS3 and the single shifts SS2 and SS3, with their slot
_LOCKING_SHIFTS: typing.Final = types.MappingProxyType({b"n": 2, b"o": 3})
_SINGLE_SHIFTS: typing.Final = types.MappingProxyType({b"N": 2, b"O": 3})

#: the control characters :meth:`TermCanvas.process_char` executes, also after an ESC inside an OSC string
_EXECUTED_CONTROLS = frozenset((b"\r", b"\x0f", b"\x0e", b"\n", b"\v", b"\f", b"\t", b"\b"))

#: the C0 control characters :meth:`TermCanvas.process_char` ignores: all but ESC, BEL, CAN, SUB and the executed ones
_IGNORED_CONTROLS = (
    frozenset(bytes((code,)) for code in range(0x20)) - {ESC_B, b"\a", b"\x18", b"\x1a"} - _EXECUTED_CONTROLS
)

#: the C0 and C1 control characters and DEL in UTF-8, which a UTF-8 terminal executes instead of showing a glyph
_UTF8_CONTROLS = frozenset(chr(code).encode("utf-8") for code in (*range(0x20), 0x7F, *range(0x80, 0xA0)))

#: the mouse tracking modes that replace each other: reports for presses and releases, highlight tracking, reports
#: also for drags, also for any motion
_MOUSE_TRACKING_MODES: typing.Final = frozenset(
    (
        PrivateMode.MOUSE_REPORTING,
        PrivateMode.MOUSE_HIGHLIGHT_TRACKING,
        PrivateMode.MOUSE_BUTTON_TRACKING,
        PrivateMode.MOUSE_ANY_EVENT_TRACKING,
    )
)

#: the modes that change the encoding of a mouse report from X10: UTF-8 coordinates, SGR parameters
_MOUSE_ENCODING_MODES: typing.Final = frozenset((PrivateMode.MOUSE_UTF8_MODE, PrivateMode.MOUSE_SGR_MODE))

#: the DEC private modes a Terminal recognises and ignores
_RECOGNISED_IGNORED_MODES: typing.Final = frozenset(
    (
        PrivateMode.CURSOR_BLINK,
        PrivateMode.MOUSE_URXVT_MODE,
        PrivateMode.META_SENDS_ESCAPE,
        PrivateMode.ALT_SENDS_ESCAPE,
    )
)

#: the modes that switch to the alternate screen when set and back to the main one when reset
_ALTERNATE_SCREEN_MODES: typing.Final = frozenset(
    (
        PrivateMode.ALTERNATE_SCREEN,
        PrivateMode.ALTERNATE_SCREEN_CLEARED_ON_EXIT,
        PrivateMode.ALTERNATE_SCREEN_BUFFER,
    )
)

#: the private markers of the kitty keyboard protocol's CSI u sequences: query, push, pop and set the flags
_KITTY_KEYBOARD_MARKERS: typing.Final = frozenset((b"?", b">", b"<", b"="))
#: the flags a Terminal accepts, all the protocol defines; others are dropped, so a query shows they are not set
_KITTY_KEYBOARD_ALL_FLAGS: typing.Final = ~KittyKeyboardFlag(0)

#: the entries a screen's keyboard flag stack keeps, as in kitty; a push onto a full stack drops the oldest entry
_KITTY_KEYBOARD_STACK_LIMIT: typing.Final = 8


class CSIAlias(typing.NamedTuple):
    """Entry in :data:`CSI_COMMANDS` redirecting a CSI final byte to another command's byte."""

    alias_mark: str  # can not have constructor with default first and non-default second arg
    alias: bytes


class CSICommand(typing.NamedTuple):
    """Entry in :data:`CSI_COMMANDS` describing how to parse and dispatch one CSI sequence."""

    num_args: int
    default: int
    callback: Callable[[TermCanvas, list[int], bool], typing.Any]  # return value ignored


CSI_COMMANDS: dict[bytes, CSIAlias | CSICommand] = {
    # possible values:
    #     None -> ignore sequence
    #     CSICommand(<minimum number of args>, <fallback if no argument>, callback)
    #     CSIAlias("alias", <symbol>)
    #
    # while callback is executed as:
    #     callback(<instance of TermCanvas>, arguments, has_question_mark)
    b"@": CSICommand(1, 1, lambda s, number, q: s.insert_chars(chars=number[0])),
    b"A": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative=True)),
    b"B": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative=True)),
    b"C": CSICommand(1, 1, lambda s, cols, q: s.move_cursor(cols[0], 0, relative=True)),
    b"D": CSICommand(1, 1, lambda s, cols, q: s.move_cursor(-cols[0], 0, relative=True)),
    b"E": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative_y=True)),
    b"F": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative_y=True)),
    b"G": CSICommand(1, 1, lambda s, col, q: s.move_cursor(col[0] - 1, 0, relative_y=True)),
    b"H": CSICommand(2, 1, lambda s, x_y, q: s.move_cursor(x_y[1] - 1, x_y[0] - 1)),
    b"I": CSICommand(1, 1, lambda s, count, _q: s.csi_forward_tab(count[0])),
    b"J": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_display(mode[0], selective=q or s.modes.iso_protection)),
    b"K": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_line(mode[0], selective=q or s.modes.iso_protection)),
    b"L": CSICommand(1, 1, lambda s, number, q: s.insert_lines(lines=number[0])),
    b"M": CSICommand(1, 1, lambda s, number, q: s.remove_lines(lines=number[0])),
    b"P": CSICommand(1, 1, lambda s, number, q: s.remove_chars(chars=number[0])),
    b"S": CSICommand(1, 1, lambda s, lines, q: s.csi_scroll(lines[0])),
    # SD (CSI Ps T) is run in parse_csi, which sees whether its parameter is 0
    b"T": CSICommand(0, 0, lambda s, none, q: None),
    # SD as ECMA-48 corrected it, which xterm takes too
    b"^": CSICommand(1, 1, lambda s, lines, q: s.csi_scroll(lines[0], reverse=True)),
    b"X": CSICommand(
        1,
        1,
        lambda s, number, q: s.erase(
            s.term_cursor,
            (s.term_cursor[0] + number[0] - 1, s.term_cursor[1]),
            selective=s.modes.iso_protection,
        ),
    ),
    b"Z": CSICommand(1, 1, lambda s, count, _q: s.csi_backward_tab(count[0])),
    b"a": CSIAlias("alias", b"C"),
    b"b": CSICommand(1, 1, lambda s, count, _q: s.csi_repeat(count[0])),
    b"c": CSICommand(0, 0, lambda s, none, q: s.csi_get_device_attributes(q)),
    b"d": CSICommand(1, 1, lambda s, row, q: s.move_cursor(0, row[0] - 1, relative_x=True)),
    b"e": CSIAlias("alias", b"B"),
    b"f": CSIAlias("alias", b"H"),
    b"g": CSICommand(1, 0, lambda s, mode, q: s.csi_clear_tabstop(mode[0])),
    b"h": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q)),
    b"l": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q, reset=True)),
    # SGR (CSI Pm m) is run in parse_csi, which also reads its sub-parameters
    b"m": CSICommand(0, 0, lambda s, _none, _q: None),
    b"n": CSICommand(1, 0, lambda s, mode, q: s.csi_status_report(mode[0], private=q)),
    # DECRQM (CSI ? Ps $ p, CSI Ps $ p), DECSTR (CSI ! p) and DECSCL (CSI Ps ; Ps " p) are run in parse_csi, and the
    # other forms are not implemented
    b"p": CSICommand(0, 0, lambda s, none, q: None),
    b"q": CSICommand(1, 0, lambda s, mode, q: s.csi_set_keyboard_leds(mode[0])),
    b"r": CSICommand(2, 0, lambda s, t_b, q: s.csi_set_scroll(t_b[0], t_b[1])),
    # SCOSC and SCORC save and restore what DECSC and DECRC do, as in xterm and the Linux console
    b"s": CSICommand(0, 0, lambda s, none, q: s.save_cursor(with_attrs=True)),
    b"u": CSICommand(0, 0, lambda s, none, q: s.restore_cursor(with_attrs=True)),
    # DECRQPSR (CSI Ps $ w) is answered in parse_csi, and the other forms are not implemented
    b"w": CSICommand(0, 0, lambda s, none, q: None),
    # the VT420 sequences with an intermediate byte, run in parse_csi from _INTERMEDIATE_COMMANDS: DECRQDE (CSI " v),
    # DECFRA (CSI ... $ x), DECERA (CSI ... $ z), DECSERA (CSI ... $ {), DECCRA (CSI ... $ v), DECCARA (CSI ... $ r),
    # DECRARA (CSI ... $ t), DECSACE (CSI Ps * x), DECRQCRA (CSI ... * y), DECIC (CSI Ps ' }) and DECDC (CSI Ps ' ~);
    # DECSCA (CSI Ps " q) and DECRQUPSS (CSI & u) are run there too
    b"t": CSICommand(1, 0, lambda s, operation, q: s.csi_report_window(operation[0])),
    b"v": CSICommand(0, 0, lambda s, none, q: None),
    b"x": CSICommand(0, 0, lambda s, none, q: None),
    b"y": CSICommand(0, 0, lambda s, none, q: None),
    b"z": CSICommand(0, 0, lambda s, none, q: None),
    b"{": CSICommand(0, 0, lambda s, none, q: None),
    b"}": CSICommand(0, 0, lambda s, none, q: None),
    b"~": CSICommand(0, 0, lambda s, none, q: None),
    b"`": CSIAlias("alias", b"G"),
}

#: the replies to the DEC status reports of a VT220 that are not about the cursor, by mode: no printer (15), the
#: user-defined keys unlocked (25), and a North American keyboard (1) that is ready (0) and an LK201 (0) (26)
_PRIVATE_STATUS_REPORTS: typing.Final = types.MappingProxyType({15: "13", 25: "20", 26: "27;1;0;0"})

#: the final bytes whose "?" form is run: the DEC private modes, the linux cursor style CSI ? Ps c (not answered), the
#: selective erases DECSED and DECSEL, and the DEC status reports, which csi_status_report() answers with their own
#: replies; any other "?" form, such as the kitty keyboard protocol query CSI ? u, is a different command than the one
#: without it
_CSI_PRIVATE_FINAL_BYTES: typing.Final = frozenset((b"J", b"K", b"c", b"h", b"l", b"n"))

CHARSET_DEFAULT: Literal[1] = 1  # type annotated exclusively for buggy IDE
CHARSET_UTF8: Literal[2] = 2


class _Blank(bytes):
    """A space no character was written to, such as an erased or scrolled-in cell.

    It is equal to ``b" "`` and drawn as one, but unlike a written space DECRQCRA counts it 0, as xterm counts a cell
    never written.
    Cells keep the one instance, :data:`_BLANK`, which is told apart by identity.
    """

    __slots__ = ()


#: the character of a cell never written; compared by identity
_BLANK: typing.Final = _Blank(b" ")


class _Protected(bytes):
    """A character written while DECSCA or SPA protected the characters written, which the erases may keep.

    It is equal to the character and drawn as it.
    """

    __slots__ = ()


# Cell with no attributes, for the cells a resize adds and the padding of lines from the scrollback.
_BLANK_CELL: tuple[AttrSpec | None, Literal["0", "U"] | None, bytes] = (None, None, _BLANK)


@functools.lru_cache(maxsize=1024)
def _encoded_width(char: bytes, byte_encoding: str) -> int:
    """Return how many columns *char*, encoded in *byte_encoding*, is drawn in.

    The encoding is urwid's current one, an argument so a character is measured again after it changes.
    """
    if byte_encoding == "narrow":
        return len(char)
    return str_util.calc_width(char, 0, len(char))


def _drawn_width(char: bytes) -> int:
    """Return how many columns the display draws a cell's *char* in.

    It is 2 for the first half of a wide character.
    """
    return 1 if len(char) < 2 else _encoded_width(bytes(char), str_util.get_byte_encoding())


#: a text of each kind a character can continue the grapheme cluster of: a plain character, which combining marks,
#: spacing marks and a zero width joiner continue, a regional indicator, an emoji with a zero width joiner, the Hangul
#: jamo and syllables, and a consonant with a virama, which a consonant of any script with such conjuncts continues
_CLUSTER_STARTS: typing.Final = ("a", "\U0001f1fa", "\U0001f468\u200d", "\u1100", "\u1161", "\uac00", "\u0915\u094d")


def _continues_cluster(text: str, char: str) -> bool:
    """Return whether *char*, written after a cell holding *text*, belongs to the same grapheme cluster.

    It is not cached, since a pair of cells rarely repeats in text where the second may join the first, such as Hangul.
    """
    joined = text + char
    return wcwidth.grapheme_boundary_before(joined, len(joined)) < len(text)


# sized for the characters of one text: the CJK ideographs and Hangul syllables of the Basic Multilingual Plane
@functools.lru_cache(maxsize=32768)
def _may_continue_cluster(char: str) -> bool:
    """Return whether *char* continues the grapheme cluster of some text, so that it may join a cell.

    The character after a prepended concatenation mark, such as U+0600, is not counted, which keeps this a property of
    the character alone.
    """
    return any(_continues_cluster(start, char) for start in _CLUSTER_STARTS)


def _mend_wide(line: list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]], x: int) -> None:
    """Replace a half of a wide character that lost its other half at the boundary before column *x* with a space.

    A wide character takes two cells: its own, and an empty one after it.
    The half left over holds a written space with its own attributes, as xterm draws it.
    """
    if x < len(line) and not line[x][2] and (x == 0 or _drawn_width(line[x - 1][2]) != 2):
        attrspec, charset, char = line[x]
    elif x > 0 and _drawn_width(line[x - 1][2]) == 2 and (x == len(line) or line[x][2]):
        x -= 1
        attrspec, charset, char = line[x]
    else:
        return
    line[x] = (attrspec, charset, _Protected(b" ") if isinstance(char, _Protected) else b" ")


def _fit_line(
    line: list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]],
    width: int,
) -> list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]:
    """Return a copy of *line* cut or padded with blank cells to *width*, with no wide character cut in half."""
    fitted = line[:width] + [_BLANK_CELL] * (width - len(line))
    _mend_wide(fitted, width)
    return fitted


@dataclass(eq=True, order=False)
class TermModes:
    """Terminal mode flags (ECMA-48 and DEC private modes) tracked for a :class:`TermCanvas`."""

    # ECMA-48
    display_ctrl: bool = False
    insert: bool = False
    lfnl: bool = False

    # DEC private modes
    keys_decckm: bool = False
    reverse_video: bool = False
    constrain_scrolling: bool = False
    autowrap: bool = True
    visible_cursor: bool = True
    bracketed_paste: bool = False
    synchronized_output: bool = False
    # the child is sent each new size in its input, as a window size report
    in_band_resize: bool = False
    # the mode of the mouse events the child asked for, or None when it asked for none
    mouse_tracking: PrivateMode | None = None
    # the mode of the mouse report encoding the child asked for, or None for the X10 encoding
    mouse_encoding: PrivateMode | None = None
    # the alternate screen is shown, rather than the main one
    alternate_screen: bool = False

    # the kitty keyboard protocol's flag stack of the screen shown, with the flags in effect last; empty for none
    keyboard_flags: list[int] = field(default_factory=list)

    # charset stuff
    main_charset: Literal[1, 2] = CHARSET_DEFAULT

    # the keypad is in application mode (DECKPAM, DECNKM); urwid names the keypad keys as the main keys, so the keys
    # sent do not change
    keypad_application: bool = False
    # the backarrow key sends BS rather than DEL (DECBKM)
    backarrow_sends_backspace: bool = False
    # the cursor style DECSCUSR set, 1 to 6, which the canvas draws itself in place of the display's cursor; None
    # before a DECSCUSR and after DECSTR or RIS, while the display's cursor is shown
    cursor_style: int | None = None
    # SPA selected ISO protection, until DECSCA, DECSTR or RIS: ED, EL and ECH keep the protected characters too, and
    # DECSERA erases them
    iso_protection: bool = False
    # The fields below follow every field above, which a caller may pass to the constructor by position.
    # the child is sent CSI I and CSI O when the display reports that the terminal gained and lost the focus
    focus_reporting: bool = False
    # without mouse tracking, the child is sent the mouse wheel on the alternate screen as cursor up and down keys
    alternate_scroll: bool = False

    def reset(self) -> None:
        """Reset every mode flag to its terminal-startup default."""
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
        self.focus_reporting = False
        self.alternate_scroll = False
        self.in_band_resize = False
        self.mouse_tracking = None
        self.mouse_encoding = None
        self.alternate_screen = False
        self.keypad_application = False
        self.backarrow_sends_backspace = False
        self.cursor_style = None
        self.iso_protection = False

        self.keyboard_flags = []

        # charset stuff
        self.main_charset = CHARSET_DEFAULT


@dataclass(slots=True, weakref_slot=True)
class _Screen:
    """The state a :class:`TermCanvas` keeps for the screen it does not show, the main or the alternate one."""

    term: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
    scrollback_buffer: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
    saved_cursor: tuple[int, int] | None = None
    saved_attrs: tuple[AttrSpec | None, TermCharset] | None = None
    keyboard_flags: list[int] = field(default_factory=list)
    #: the row the cursor was on when the screen was hidden, moved with the rows a resize keeps
    cursor_row: int = 0
    saved_flags: tuple[bool, bool, bool] | None = None


class TermCharset:
    """Tracks the terminal's G0 to G3 character set slots and which one is currently active."""

    __slots__ = ("_finals", "_g", "_sets96", "_sgr_mapping", "_single", "active", "current", "gr")

    MAPPING: typing.ClassVar[dict[str, str | None]] = {
        "default": None,
        "vt100": "0",
        "ibmpc": "U",
        "user": None,
    }

    def __init__(self) -> None:
        """Initialize with G1 as DEC special graphics and G0, G2 and G3 at the default charset, G0 active."""
        # a tuple, so a copy kept by DECSC is not changed by a later designation
        self._g: tuple[str, ...] = ("default", "vt100", "default", "default")
        # the final byte each slot was designated with, and a bit per slot designated with a 96-character set
        self._finals: tuple[bytes, ...] = (b"B", b"0", b"B", b"B")
        self._sets96 = 0
        #: the slot invoked into GR by LS1R, LS2R or LS3R; GR is not drawn from, only reported
        self.gr = 2

        self._sgr_mapping = False

        # the slot a single shift (SS2, SS3) selects for the next character, None outside a single shift
        self._single: int | None = None

        # prepare defaults
        self.active = 0
        self.current: Literal["0", "U"] | None = None

        self.activate(0)

    def define(self, g: int, charset: str, *, final: bytes | None = None, size96: bool = False) -> None:
        """Redefine G'g' with new mapping.

        :param g: the slot, 0 to 3 for G0 to G3.
        :param charset: the name of the character set, a key of :attr:`MAPPING`.
        :param final: the final byte of the designation, reported by DECCIR; the one *charset* is known by by default.
            A final that is not one byte from ``0`` to ``~``, or is ``;``, cannot be reported and is replaced so too.
        :param size96: the designation is of a 96-character set.
        """
        if final is None or len(final) != 1 or not 0x30 <= final[0] < 0x7F or final == b";":
            final = _CHARSET_FINALS[charset]
        self._g = (*self._g[:g], charset, *self._g[g + 1 :])
        self._finals = (*self._finals[:g], final, *self._finals[g + 1 :])
        self._sets96 = self._sets96 | (1 << g) if size96 else self._sets96 & ~(1 << g)
        self.activate(g=self.active)

    @property
    def designations(self) -> tuple[bytes, int]:
        """Return the final bytes G0 to G3 were designated with, and a bit per slot holding a 96-character set."""
        return b"".join(self._finals), self._sets96

    @property
    def single_shifted(self) -> int | None:
        """Return the slot a pending single shift draws the next character from, or None without one."""
        return self._single

    def activate(self, g: int) -> None:
        """Activate the given charset slot.

        A pending single shift still applies to the next character.
        """
        self.active = g
        self.current = self.MAPPING.get(self._g[self._shown], None)  # type: ignore[assignment]

    @property
    def _shown(self) -> int:
        """Return the slot the next character is drawn from: the single shift's, else the active one."""
        return self.active if self._single is None else self._single

    def single_shift(self, g: int) -> None:
        """Draw the next character only from slot *g*, as SS2 and SS3 do."""
        self._single = g
        self.activate(self.active)

    def end_single_shift(self) -> None:
        """End a single shift after the character it applied to."""
        if self._single is not None:
            self._single = None
            self.activate(self.active)

    def set_sgr_ibmpc(self) -> None:
        """Set graphics rendition mapping to IBM PC CP437."""
        self._sgr_mapping = True

    def reset_sgr_ibmpc(self) -> None:
        """Reset graphics rendition mapping to IBM PC CP437."""
        self._sgr_mapping = False
        self.activate(g=self.active)

    @property
    def ibmpc_mapped(self) -> bool:
        """Return whether the characters written are mapped as the IBM PC character set, by SGR 11 or a designation."""
        return self._sgr_mapping or self._g[self._shown] == "ibmpc"

    def apply_mapping(self, char: bytes) -> bytes:
        """Map *char* through the active IBM PC/DEC special character set, tracking which slot the result came from.

        A display writes a charset "U" cell to the host terminal unchanged.
        With the UTF-8 encoding a control character there would be executed by the host terminal,
        so it is stored as ``?``.
        """
        if self._sgr_mapping or self._g[self._shown] == "ibmpc":
            if (dec_pos := DEC_SPECIAL_CHARS.find(char.decode("cp437"))) >= 0:
                self.current = "0"
                return ALT_DEC_SPECIAL_CHARS[dec_pos].encode("cp437")

            self.current = "U"
            if char in _UTF8_CONTROLS and util.get_encoding_mode() == "utf8":
                return b"?"
            return char

        return char


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


def _with_flag(attrspec: AttrSpec | None, flag: str, *, remove: bool = False) -> AttrSpec:
    """Return *attrspec* with the foreground setting *flag*, such as ``standout``, added, or removed with *remove*.

    None stands for the default colours.
    """
    if attrspec is None:
        attrspec = AttrSpec("default", "default")
    attrs = [fg.strip() for fg in attrspec.foreground.split(",")]
    if flag in attrs and remove:
        attrs.remove(flag)
        attrspec = attrspec.copy_modified(fg=",".join(attrs))
    elif flag not in attrs and not remove:
        attrs.append(flag)
        attrspec = attrspec.copy_modified(fg=",".join(attrs))
    return attrspec


def _apply_area_sgr(sgrs: Sequence[int], attrspec: AttrSpec | None) -> AttrSpec | None:
    """Return *attrspec* with the SGR parameters *sgrs* of DECCARA or DECRARA applied, keeping faint.

    SGR 22 also ends faint, which neither control changes, so faint is set again, as xterm keeps it.
    """
    faint = [2] if attrspec is not None and attrspec.faint and 22 in sgrs else []
    return sgi_params_to_attrspec([*sgrs, *faint], attrspec)


def _sgr_parameters(attrspec: AttrSpec | None) -> str:
    """Return the SGR parameters that select *attrspec* from the default attributes.

    The parameters start with ``0``.
    Colours are written as SGR 30-37, 90-97, 38;5;n or 38;2;r;g;b, and the background alike, in the semicolon form a
    :class:`TermCanvas` reads back.
    The hyperlink is not part of SGR and is left out.

    >>> _sgr_parameters(None)
    '0'
    >>> _sgr_parameters(AttrSpec("light red,bold", "h100", 256))
    '0;1;91;48;5;100'
    """
    if attrspec is None:
        return "0"
    parameters = ["0", *(str(code) for name, code in _SGR_FLAGS if getattr(attrspec, name))]
    rgb = attrspec.get_rgb_values()
    for base, true, high, basic, number, values in (
        (30, attrspec.foreground_true, attrspec.foreground_high, attrspec.foreground_basic,
         attrspec.foreground_number, rgb[0:3]),
        (40, attrspec.background_true, attrspec.background_high, attrspec.background_basic,
         attrspec.background_number, rgb[3:6]),
    ):  # fmt: skip
        if true:
            parameters.append(f"{base + 8};2;{';'.join(str(value) for value in values)}")
        elif high:
            parameters.append(f"{base + 8};5;{number:d}")
        elif basic:
            parameters.append(str(base + number if number < 8 else base + 60 + number - 8))
    return ";".join(parameters)


class TermCanvas(Canvas):
    """Canvas holding a terminal's screen and scrollback content, for the widget that owns it."""

    cacheable = False

    def __init__(
        self,
        width: int,
        height: int,
        widget: _TermCanvasOwner,
        *,
        scroll_on_output: bool = True,
    ) -> None:
        """Initialize an empty `width` by `height` canvas backing `widget`.

        :param scroll_on_output: move a view scrolled back from the bottom to the bottom when output arrives.
            When off, the view stays on the lines it shows while new lines scroll into the scrollback below them.
        """
        super().__init__()

        self.width, self.height = width, height
        self.widget = widget
        self.modes: TermModes = widget.term_modes
        self.has_focus = False
        #: Whether output returns a scrolled-back view to the bottom, see :meth:`__init__`.
        self.scroll_on_output = scroll_on_output

        self.scrollback_buffer: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]] = deque(
            maxlen=10000
        )
        self.scrolling_up = 0

        self.utf8_eat_bytes: int | None = None
        self.utf8_buffer = bytearray()
        self._escbuf = bytearray()
        # the OSC string being read had a sequence that is not valid UTF-8, in UTF-8 mode
        self._osc_invalid_utf8 = False

        self.coords["cursor"] = (0, 0, None)

        self.term_cursor: tuple[int, int] = (0, 0)  # do not allow to shoot in the leg at `set_term_cursor`

        self.within_escape = False
        self.parsestate = 0

        self.attrspec: AttrSpec | None = None
        #: DECSCA or SPA: the characters written are protected
        self.protected = False
        #: DECSACE: 2 makes DECCARA and DECRARA act on a rectangle, and any other value on a stream of cells
        self.attribute_extent = 0

        self.charset = TermCharset()

        self.saved_cursor: tuple[int, int] | None = None
        self.saved_attrs: tuple[AttrSpec | None, TermCharset] | None = None
        #: origin mode, a pending autowrap and DECSCA, saved with the attributes by DECSC, or None when nothing is saved
        self.saved_flags: tuple[bool, bool, bool] | None = None

        self.is_rotten_cursor = False
        # the character the last input wrote in a cell of its own, whether it is a DEC special graphics character,
        # and whether it is wide; None when the last input was anything else, such as a control function
        self._last_graphic: tuple[bytes, bool, bool] | None = None
        # the character REP repeats: the one written just before the escape sequence being read
        self._repeat_graphic: tuple[bytes, bool, bool] | None = None
        #: the colors the display draws, as its screen reports them, which the XTGETTCAP replies describe;
        #: None while unknown. The widget the canvas belongs to sets it.
        self.display_colors: Literal[1, 16, 88, 256, 16777216] | None = None

        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1

        #: the conformance level DECSCL selected, 61 to 63: at 61 the VT300 reports are not answered
        self.conformance_level = _CONFORMANCE_LEVELS[-1]

        self.tabstops: list[int] = []
        self.term: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]] = []
        # the screen not shown: the alternate one while the main one is shown, and the other way round
        self._hidden_screen = _Screen([], deque(maxlen=0))
        # a new canvas starts on its main screen, also for modes an earlier canvas left on the alternate one
        self.modes.alternate_screen = False

        self.reset()

    @property
    def escbuf(self) -> bytes:
        """Return the buffered bytes of the escape sequence being parsed."""
        return bytes(self._escbuf)

    @escbuf.setter
    def escbuf(self, value: bytes) -> None:
        self._escbuf = bytearray(value)

    @property
    def reads_utf8(self) -> bool:
        """Whether input bytes are decoded as UTF-8.

        They are when the data selected UTF-8 (``ESC % G``) or urwid's encoding is UTF-8.
        Otherwise each byte is one character in urwid's encoding.
        """
        return self.modes.main_charset == CHARSET_UTF8 or util.get_encoding_mode() == "utf8"

    def set_term_cursor(self, x: int | None = None, y: int | None = None) -> None:
        """Set terminal cursor to x/y and update canvas cursor.

        If one or both axes are omitted, use the values of the current position.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        self.term_cursor = x, y = self.constrain_coords(x, y)

        # with a cursor style set, content() draws the cursor and the display shows none
        self.cursor = self._shown_cursor() if self.modes.cursor_style is None else None

    def _shown_cursor(self) -> tuple[int, int] | None:
        """Return the cursor's column and row in the view, or None while it is hidden, out of focus or scrolled away."""
        x, y = self.term_cursor
        if self.has_focus and self.modes.visible_cursor and self.scrolling_up < self.height - y:
            return x, y + self.scrolling_up
        return None

    def reset_scroll(self) -> None:
        """Reset scrolling region to full terminal size."""
        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1

    def scroll_buffer(self, up: bool = True, reset: bool = False, lines: int | None = None) -> None:
        """Scroll the scrolling buffer up (up=True) or down (up=False) the given amount of lines.

        Scrolls half the screen height when *lines* is omitted.

        If just 'reset' is True, set the scrollbuffer view to the current terminal content.
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
        """Reset the terminal to its startup state on the main screen.

        The main screen is cleared. It keeps its scrollback. The alternate screen is replaced by a blank one.
        """
        if self.modes.alternate_screen:
            self._swap_screens()

        self._escbuf = bytearray()
        self.within_escape = False
        self.parsestate = 0

        self.attrspec = None
        self.protected = False
        self.attribute_extent = 0
        self.charset = TermCharset()

        self.saved_cursor = None
        self.saved_attrs = None
        self.saved_flags = None

        self.is_rotten_cursor = False
        self._last_graphic = self._repeat_graphic = None

        self.reset_scroll()

        self.init_tabstops()

        self.conformance_level = _CONFORMANCE_LEVELS[-1]

        # terminal modes
        self.modes.reset()

        # initialize self.term
        self.clear()
        # the alternate screen keeps no scrollback, as in xterm: the lines scrolled off it are dropped
        self._hidden_screen = _Screen([[_BLANK_CELL] * self.width for _ in range(self.height)], deque(maxlen=0))

    def _swap_screens(self) -> None:
        """Swap the screen shown with the one kept apart.

        The cursor position stays where it is.
        """
        hidden = self._hidden_screen
        self._hidden_screen = _Screen(
            self.term,
            self.scrollback_buffer,
            self.saved_cursor,
            self.saved_attrs,
            self.modes.keyboard_flags,
            self.term_cursor[1],
            self.saved_flags,
        )
        self.term = hidden.term
        self.scrollback_buffer = hidden.scrollback_buffer
        self.saved_cursor = hidden.saved_cursor
        self.saved_attrs = hidden.saved_attrs
        self.saved_flags = hidden.saved_flags
        self.modes.keyboard_flags = hidden.keyboard_flags
        self.modes.alternate_screen = not self.modes.alternate_screen
        self.scroll_buffer(reset=True)

    def set_alternate_screen(self, mode: PrivateMode, flag: bool) -> None:
        """Switch to or from the alternate screen for DEC private *mode*, as xterm does.

        Each screen keeps its own content, scrollback, cursor saved by DECSC and keyboard flags. The cursor position
        is shared.

        - 47 switches to the alternate screen when set, and back to the main one when reset.
        - 1047 also clears the alternate screen before switching back from it.
        - 1049 also saves the cursor as DECSC does before switching to the alternate screen.
        - 1049 also clears the alternate screen after switching to it.
        - 1049 also restores the saved cursor after switching back to the main screen.

        :param mode: one of the modes in :data:`_ALTERNATE_SCREEN_MODES`.
        :param flag: the mode is set rather than reset.
        """
        if flag:
            if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
                self.save_cursor(with_attrs=True)
            if not self.modes.alternate_screen:
                self._swap_screens()
            if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
                self.clear(cursor=self.term_cursor)
            return

        if self.modes.alternate_screen:
            if mode == PrivateMode.ALTERNATE_SCREEN_CLEARED_ON_EXIT:
                self.clear(cursor=self.term_cursor)
            self._swap_screens()
        if mode == PrivateMode.ALTERNATE_SCREEN_BUFFER:
            self.restore_cursor(with_attrs=True)

    def init_tabstops(self, extend: bool = False) -> None:
        """Set every column to a tabstop, or, when *extend* is set, grow the existing tabstops to the new width."""
        tablen, mod = divmod(self.width, 8)
        if mod > 0:
            tablen += 1

        if extend:
            while len(self.tabstops) < tablen:
                self.tabstops.append(1 << 0)
        else:
            self.tabstops = [1 << 0] * tablen

    def set_tabstop(self, x: int | None = None, remove: bool = False, clear: bool = False) -> None:
        """Set, remove, or (with *clear*) remove every tabstop, at column *x* or the cursor's column by default."""
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
            self.tabstops[div] |= 1 << mod

    def is_tabstop(self, x: int | None = None) -> bool:
        """Return whether column *x* (the cursor's column by default) is a tabstop."""
        if x is None:
            x = self.term_cursor[0]

        div, mod = divmod(x, 8)
        return (self.tabstops[div] & (1 << mod)) > 0

    def empty_line(self, char: bytes = _BLANK) -> list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]:
        """Return a full row of empty characters, one per column, filled with *char*."""
        return [self.empty_char(char)] * self.width

    def empty_char(self, char: bytes = _BLANK) -> tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]:
        """Return one empty terminal cell holding *char*, with the canvas's current colours and charset.

        As in xterm, an erased or scrolled-in cell takes the colours only: not bold, underline, reverse video or the
        other attribute flags, and not the current hyperlink.
        By default it holds a space never written, which DECRQCRA counts as xterm does.
        """
        attrspec = self.attrspec
        if attrspec is not None and attrspec.hyperlink is not None:
            attrspec = attrspec_with_hyperlink(attrspec, None, unset_color="default")
        if attrspec is None:
            return (None, self.charset.current, char)
        if any(getattr(attrspec, name) for name, _code in _SGR_FLAGS):
            colour = ",".join(
                part for part in (part.strip() for part in attrspec.foreground.split(",")) if part not in _FLAG_NAMES
            )
            attrspec = attrspec.copy_modified(fg=colour or "default")
        if attrspec.foreground == "default" and attrspec.background == "default":
            return (None, self.charset.current, char)
        return (attrspec, self.charset.current, char)

    def addstr(self, data: Iterable[int]) -> None:
        """Feed a sequence of input bytes through the terminal parser, one byte at a time."""
        if self.width <= 0 or self.height <= 0:
            # not displayable, do nothing!
            return

        if self.scrolling_up and self.scroll_on_output and data:
            self.scroll_buffer(reset=True)
        for byte in data:
            self.addbyte(byte)

    def resize(self, width: int, height: int) -> None:
        """Resize both screens to the given width and height.

        A screen that shrinks drops its blank bottom rows below the cursor first, so the cursor stays on its line
        unless a row below it holds content; the cursor and the saved cursors move with the rows that stay.
        For the hidden screen, that row is the one its cursor was on when it was hidden.
        A view scrolled back keeps showing the same top line.
        """
        x, y = self.term_cursor

        shift = self._resize_lines(self.term, self.scrollback_buffer, width, height, cursor_row=y)
        y += shift
        if self.saved_cursor is not None:
            self.saved_cursor = (self.saved_cursor[0], self.saved_cursor[1] + shift)
        hidden = self._hidden_screen
        hidden_shift = self._resize_lines(
            hidden.term,
            hidden.scrollback_buffer,
            width,
            height,
            cursor_row=hidden.cursor_row,
        )
        hidden.cursor_row += hidden_shift
        if hidden.saved_cursor is not None:
            hidden.saved_cursor = (hidden.saved_cursor[0], hidden.saved_cursor[1] + hidden_shift)

        self.width = width
        self.height = height

        self.reset_scroll()
        if self.scrolling_up:
            # the lines moved into the scrollback, or taken back from it, would otherwise move the view
            self.scrolling_up = max(0, min(self.scrolling_up - shift, len(self.scrollback_buffer)))

        x, y = self.constrain_coords(x, y)
        self.set_term_cursor(x, y)

        # extend tabs
        self.init_tabstops(extend=True)

    def _resize_lines(
        self,
        lines: list[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]],
        scrollback: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]],
        width: int,
        height: int,
        *,
        cursor_row: int | None = None,
    ) -> int:
        """Fit *lines*, a screen of the current size, to *width* and *height* in place.

        A screen that shrinks moves its top lines to the end of *scrollback*, and one that grows takes them back from
        there, or adds blank lines at the bottom once *scrollback* is empty.
        With *cursor_row*, a shrinking screen first drops the blank lines at its bottom below that row,
        so the lines above stay on the screen.
        A blank line is spaces with no attributes, in any character set.

        :returns: how many rows the lines that stay on the screen moved down, negative when they moved up.
        """
        for row in range(self.height):
            lines[row] = _fit_line(lines[row], width)

        shift = 0
        for _y in range(self.height, height):
            if not scrollback:
                lines.append([_BLANK_CELL] * width)
                continue

            # adjust x axis of the scrollback line to the new width
            last_line = scrollback.pop()
            lines.insert(0, _fit_line(last_line, width))
            shift += 1
        for _y in range(height, self.height):
            if (
                cursor_row is not None
                and len(lines) - 1 > cursor_row + shift
                and all(attr is None and text == b" " for attr, _charset, text in lines[-1])
            ):
                lines.pop()
                continue
            scrollback.append(lines.pop(0))
            shift -= 1

        return shift

    def set_g01(self, char: bytes, mod: bytes) -> None:
        """Designate the character set of final byte *char* to the slot of intermediate byte *mod*.

        The slots are G0 for ``(``, G2 for ``*``, G3 for ``+`` and G1 for any other byte.
        """
        if self.modes.main_charset != CHARSET_DEFAULT:
            return

        g = _DESIGNATED_SLOTS.get(mod, 1)
        self.charset.define(g, _DESIGNATED_CHARSETS.get(char, "default"), final=char)

    def parse_csi(self, char: bytes) -> None:
        """Parse ECMA-48 CSI (Control Sequence Introducer) sequences."""
        if char == b"u" and (marker := bytes(self._escbuf[:1])) in _KITTY_KEYBOARD_MARKERS:
            params = self._escbuf[1:]
            if not params.strip(b"0123456789;"):
                self.csi_keyboard_flags(marker, [int(param) if param else None for param in params.split(b";")])
            return

        if char == b"p" and self._escbuf.endswith(b"$"):
            # DECRQM for a DEC private mode, CSI ? Ps $ p, or an ANSI mode, CSI Ps $ p
            if self._escbuf.startswith(b"?"):
                if (mode := self._escbuf[1:-1]).isdigit():
                    self.csi_report_private_mode(int(mode))
            elif (mode := self._escbuf[:-1]).isdigit():
                self.csi_report_mode(int(mode))
            return

        if char == b"c" and bytes(self._escbuf) in {b"=", b"=0"}:
            # Tertiary DA: CSI = c, a DCS reply, which a VT100 (level 61) does not send
            if self.conformance_level > 61:
                self.widget.respond(_TERTIARY_DEVICE_ATTRIBUTES)
            return

        if (handler := _INTERMEDIATE_COMMANDS.get((bytes(self._escbuf[-1:]), char))) is not None:
            params = self._escbuf[:-1]
            if not params.strip(b"0123456789;"):
                handler(self, [int(param) if param else None for param in params.split(b";")])
            return

        if char == b"T":
            # SD: as in xterm, which takes more parameters as its mouse highlight tracking, only no parameter or one
            # other than 0 scrolls
            if not self._escbuf or (self._escbuf.isdigit() and int(self._escbuf) > 0):
                self.csi_scroll(int(self._escbuf or b"1"), reverse=True)
            return

        if char == b"p" and self._escbuf == b"!":
            # DECSTR: CSI ! p
            self.soft_reset()
            return

        if char == b"p" and self._escbuf.endswith(b'"'):
            # DECSCL: CSI Ps1 ; Ps2 " p; Ps2 chooses 7-bit or 8-bit controls, and only 7-bit ones are sent
            level, *_controls = self._escbuf[:-1].split(b";")
            if level.isdigit() and int(level) in _CONFORMANCE_LEVELS:
                self.soft_reset()
                self.conformance_level = int(level)
            return

        if char == b"w" and self._escbuf.endswith(b"$"):
            # DECRQPSR: CSI Ps $ w, which a VT100 (level 61) does not answer
            if (report := self._escbuf[:-1]).isdigit() and self.conformance_level > 61:
                self.csi_report_presentation_state(int(report))
            return

        if char == b"c" and bytes(self._escbuf) in {b">", b">0"}:
            # Secondary DA: CSI > c
            self.widget.respond(_SECONDARY_DEVICE_ATTRIBUTES)
            return

        if char == b"q" and bytes(self._escbuf) in {b">", b">0"}:
            # XTVERSION, the query of the terminal's name and version
            self.widget.respond(f"{ESC}P>|urwid({version.version}){ESC}\\")
            return

        if char == b"m" and not self._escbuf.strip(b"0123456789;:"):
            self.csi_set_attr(parse_sgr_parameters(self._escbuf.decode("ascii")))
            return

        qmark = self._escbuf.startswith(b"?")
        body = self._escbuf[1 if qmark else 0 :]
        if body.strip(b"0123456789;") or (qmark and char not in _CSI_PRIVATE_FINAL_BYTES):
            # sub-parameters, other private markers and intermediate bytes select sequences not implemented here
            return

        escbuf = []
        for arg in body.split(b";"):
            try:
                num = int(arg)
            except ValueError:
                num = None

            escbuf.append(num)

        if (cmd_ := CSI_COMMANDS[char]) is not None:
            if isinstance(cmd_, CSIAlias):
                csi_cmd: CSICommand = CSI_COMMANDS[cmd_.alias]  # type: ignore[assignment]
            else:
                csi_cmd = cmd_

            number_of_args, default_value, cmd = csi_cmd
            while len(escbuf) < number_of_args:
                escbuf.append(default_value)
            for i in range(len(escbuf)):
                if escbuf[i] is None or escbuf[i] == 0:
                    escbuf[i] = default_value

            with suppress(ValueError):
                cmd(self, typing.cast("list[int]", escbuf), qmark)
                # ignore arguments that the command's callback rejects.

    def parse_noncsi(self, char: bytes, mod: bytes = b"") -> None:
        """Parse escape sequences which are not CSI."""
        if mod == b"#" and char == b"8":
            self.decaln()
        elif mod == b"#":
            # the single-character sequences below take no intermediate byte
            pass
        elif mod == b"%":  # select main character set
            if char == b"@":
                self.modes.main_charset = CHARSET_DEFAULT
            elif char in b"G8":
                # 8 is obsolete and only for backwards compatibility
                self.modes.main_charset = CHARSET_UTF8
        elif mod in _DESIGNATED_SLOTS:  # define G0 to G3
            self.set_g01(char, mod)
        elif mod in _DESIGNATED_96_SLOTS:
            # a 96-character set, such as ISO Latin-1 (A), for G1 to G3: drawn as the default set and reported by DECCIR
            if self.modes.main_charset == CHARSET_DEFAULT:
                self.charset.define(_DESIGNATED_96_SLOTS[mod], "default", final=char, size96=True)
        elif mod:
            # another intermediate byte, such as S7C1T/S8C1T (ESC SP F, ESC SP G): accepted and not applied
            pass
        elif char in _GR_LOCKING_SHIFTS:
            self.charset.gr = _GR_LOCKING_SHIFTS[char]
        elif char == b"6":  # DECBI
            self.back_index()
        elif char == b"9":  # DECFI
            self.forward_index()
        elif char in _LOCKING_SHIFTS:
            self.charset.activate(_LOCKING_SHIFTS[char])
        elif char in _SINGLE_SHIFTS:
            self.charset.single_shift(_SINGLE_SHIFTS[char])
        elif char in {b"=", b">"}:  # DECKPAM, DECKPNM
            self.modes.keypad_application = char == b"="
        elif char == b"M":  # reverse line feed
            self.linefeed(reverse=True)
        elif char == b"D":  # line feed
            self.linefeed()
        elif char == b"c":  # reset terminal
            self.reset()
        elif char == b"E":  # newline
            self.newline()
        elif char == b"H":  # set tabstop
            self.set_tabstop()
        elif char == b"V":  # SPA
            self.protected = self.modes.iso_protection = True
        elif char == b"W":  # EPA, which also ends what DECSCA protects
            self.protected = False
        elif char == b"Z":  # DECID
            self.widget.respond(_PRIMARY_DEVICE_ATTRIBUTES)
        elif char == b"7":  # save current state
            self.save_cursor(with_attrs=True)
        elif char == b"8":  # restore current state
            self.restore_cursor(with_attrs=True)

    def parse_osc(self, buf: bytes) -> None:
        """Parse operating system command: a window title, or an OSC 8 hyperlink for the text written after it.

        The OSC bodies are recognised by :func:`urwid.ansi_parser.resolve_osc_title` and
        :func:`urwid.ansi_parser.resolve_osc_hyperlink`, shared with :class:`~urwid.ANSIText`.
        An invalid OSC 8 command ends the current link, so the text after it does not point at the previous target;
        :meth:`parse_escape` ends it for an over-long one, which never reaches this method.
        The body is in the encoding :meth:`addbyte` passes characters on in, and as in tmux, a title that is not
        valid in it is not set.
        A string that had a sequence that is not valid UTF-8, in UTF-8 mode, sets no title and ends the current link.

        :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
        """
        encoding = util.get_encoding()
        try:
            body = buf.decode(encoding)
        except UnicodeDecodeError:
            # still recognised, so an OSC 8 command ends the current link below
            body = buf.decode(encoding, "replace")
            valid = False
        else:
            valid = True
        title = resolve_osc_title(body)
        if title is not None:
            if valid and not self._osc_invalid_utf8:
                self.widget.set_title(title)
            return
        try:
            link = resolve_osc_hyperlink(body)
        except ValueError:
            link = None
        else:
            if link is None:
                return
            if self._osc_invalid_utf8:
                link = None
        self.attrspec = attrspec_with_hyperlink(self.attrspec, link, unset_color="default")

    def parse_dcs(self, body: bytes) -> None:
        """Apply the DCS string *body*, given without its ``ESC P`` and ST framing.

        DECRQSS and XTGETTCAP are answered and DECRSPS is applied, except at the VT100 level (61).
        Any other DCS string is ignored.
        """
        if self.conformance_level == 61:
            return
        if body.startswith(b"$q"):
            self.dcs_request_setting(body[2:])
        elif body.startswith(b"1$t"):
            self.dcs_restore_cursor_information(body[3:])
        elif body.startswith(b"2$t"):
            self.dcs_restore_tab_stops(body[3:])
        elif body.startswith(b"+q"):
            self.dcs_request_termcap(body[2:])

    def parse_escape(self, char: bytes) -> None:
        """Feed *char* through the escape-sequence state machine, dispatching to CSI/OSC/non-CSI parsing as needed."""
        if self.parsestate == 1:
            # within CSI
            if char in CSI_COMMANDS:
                if len(self._escbuf) < MAX_CSI_LENGTH:
                    self.parse_csi(char)
                self.parsestate = 0
            elif b" " <= char <= b"?":  # parameter and intermediate bytes, ECMA-48 5.4
                # past the limit the parameters are dropped, and the sequence is skipped by its length
                if len(self._escbuf) < MAX_CSI_LENGTH:
                    self._escbuf += char
                return
        elif self.parsestate == 0 and char == b"]":
            # start of OSC
            self._escbuf = bytearray()
            self._osc_invalid_utf8 = False
            self.parsestate = 2
            return
        elif self.parsestate == 0 and char in _COMMAND_STRING_OPENERS:
            # start of a DCS, SOS, PM or APC string; the opening byte is kept, to tell a DCS from the others at ST
            self._escbuf = bytearray(char)
            self.parsestate = 5
            return
        elif self.parsestate in _STRING_STATES and self._escbuf[-1:] == ESC_B and char != b"\\":
            # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the string
            # unapplied and starts a new escape sequence
            self.leave_escape()
            self.within_escape = True
            self.process_char(char)
            return
        elif self.parsestate == 4 and (char == b"\a" or (self._escbuf == ESC_B and char == b"\\")):
            # end of an over-long OSC string, discarded
            pass
        elif self.parsestate == 5 and self._escbuf[-1:] == ESC_B and char == b"\\":
            # end of a DCS, SOS, PM or APC string; only a DCS that was kept whole is applied
            if self._escbuf.startswith(b"P") and len(self._escbuf) < MAX_OSC_LENGTH:
                self.parse_dcs(bytes(self._escbuf[1:-1]))
        elif self.parsestate == 5:
            if len(self._escbuf) < MAX_OSC_LENGTH:
                self._escbuf += char
            else:
                # past the limit only the last byte is replaced, which is enough to recognise ST, also when *char* is a
                # multibyte character, so the buffer does not grow
                self._escbuf[-1:] = char[-1:]
            return
        elif self.parsestate == 2 and char == b"\a":
            # end of OSC
            self.parse_osc(bytes(self._escbuf.lstrip(b"0")))
        elif self.parsestate == 2 and self._escbuf[-1:] + char == f"{ESC}\\".encode("iso8859-1"):
            # end of OSC
            self.parse_osc(bytes(self._escbuf[:-1].lstrip(b"0")))
        elif self.parsestate == 2 and not self._escbuf and char == b"R":
            # reset palette
            pass
        elif self.parsestate in {2, 4}:
            if self.parsestate == 2 and len(self._escbuf) < MAX_OSC_LENGTH:
                self._escbuf += char
                # an ESC is no digit: the next byte decides whether it starts ST or a new sequence
                if char != ESC_B and self._escbuf.startswith(b"P") and len(self._escbuf) == 8:
                    # the Linux console's palette set, ESC ] P n rr gg bb, ends with its 7th hex digit; not applied
                    self.leave_escape()
            else:
                if self.parsestate == 2 and self._escbuf.lstrip(b"0").startswith(b"8;"):
                    # an over-long OSC 8 is refused like any other invalid one, ending the current link
                    self.attrspec = attrspec_with_hyperlink(self.attrspec, None, unset_color="default")
                # the rest of an over-long OSC string: only the last byte is kept,
                # which is enough to recognise either terminator
                self.parsestate = 4
                self._escbuf = bytearray(char)
            return
        elif self.parsestate == 0 and char == b"[":
            # start of CSI
            self._escbuf = bytearray()
            self.parsestate = 1
            return
        elif self.parsestate in {0, 3} and b" " <= char <= b"/":
            # an intermediate byte of an escape sequence (ECMA-35), such as the "(" of a G0 designation; past the
            # limit the intermediate bytes are dropped, and the sequence still ends at its final byte
            if self.parsestate == 0:
                self._escbuf = bytearray()
                self.parsestate = 3
            if len(self._escbuf) < MAX_CSI_LENGTH:
                self._escbuf += char
            return
        elif self.parsestate == 3:
            self.parse_noncsi(char, bytes(self._escbuf))
        elif char in {
            b"c",
            b"D",
            b"E",
            b"H",
            b"M",
            b"V",
            b"W",
            b"Z",
            b"7",
            b"6",
            b"8",
            b"9",
            b">",
            b"=",
            *_LOCKING_SHIFTS,
            *_SINGLE_SHIFTS,
            *_GR_LOCKING_SHIFTS,
        }:
            self.parse_noncsi(char)

        self.leave_escape()

    def leave_escape(self) -> None:
        """Reset the escape-sequence parser state, discarding any sequence being read."""
        self.within_escape = False
        self.parsestate = 0
        self._escbuf = bytearray()
        self._osc_invalid_utf8 = False

    def get_utf8_len(self, bytenum: int) -> int:
        """Process startbyte and return the number of bytes following it to get a valid UTF-8 multibyte sequence.

        :param bytenum: an integer ordinal
        """
        length = 0

        while bytenum & 0x40:
            bytenum <<= 1
            length += 1

        return length

    def addbyte(self, byte: int) -> None:
        """Parse main charset and add the processed byte(s) to the terminal state machine.

        :param byte: an integer ordinal
        """
        if self.reads_utf8:
            continuation = 0x80 <= byte < 0xC0
            pending = self.utf8_eat_bytes is not None
            # A lone continuation byte, or a sequence cut short by a byte that does not continue it, is not valid UTF-8,
            # and parse_osc() refuses an OSC string that had one.
            if self.parsestate == 2 and continuation != pending:
                self._osc_invalid_utf8 = True
            if byte >= 0xC0:
                # start multibyte sequence
                self.utf8_eat_bytes = self.get_utf8_len(byte)
                self.utf8_buffer = bytearray([byte])
                return
            if 0x80 <= byte < 0xC0 and self.utf8_eat_bytes is not None:
                if self.utf8_eat_bytes > 1:
                    # continue multibyte sequence
                    self.utf8_eat_bytes -= 1
                    self.utf8_buffer.append(byte)
                    return

                # end multibyte sequence
                self.utf8_eat_bytes = None

                if sequence := (self.utf8_buffer + bytes([byte])).decode("utf-8", "ignore"):
                    if self.within_escape:
                        # an escape sequence takes bytes, not cells: no DEC drawing character here
                        char = sequence.encode(util.get_encoding(), "urwid_fallback_ascii")
                    elif "\x80" <= sequence < "\xa0" and not (self.charset.ibmpc_mapped or self.modes.display_ctrl):
                        # as in xterm, a C1 control written in UTF-8 is neither run nor drawn; the IBM PC mapping and
                        # display control mode draw it
                        return
                    else:
                        char, charsets = util.apply_target_encoding(sequence)
                        if charsets == [("0", 1)]:
                            # a DEC drawing character, or a fallback to one: one cell in the DEC character set
                            self.push_cursor(char, dec_special=True)
                            return
                        if char == b"\x9b":
                            # A character whose byte in urwid's encoding is 0x9B (U+203A in cp1252, U+042B in cp866)
                            # is a cell, as the display draws that byte; process_char() would run it as CSI.
                            self.push_cursor(char)
                            return
                        if "\x80" <= sequence < "\xa0":
                            # left to push_cursor(), as the IBM PC mapping draws it
                            width = 1
                        else:
                            width = _drawn_width(char)
                            # most characters start a cluster, which is known without looking at the cell before them
                            if (width == 0 or _may_continue_cluster(sequence)) and self.combine_char(
                                char,
                                sequence,
                                width=width,
                            ):
                                return
                        if width == 0:
                            # a character with no width that joins no character has no cell to take
                            return
                        if width == 2:
                            self.push_wide_char(char)
                            return

                else:
                    # an invalid multibyte sequence is dropped, and parse_osc() refuses an OSC string that had one
                    if self.parsestate == 2:
                        self._osc_invalid_utf8 = True
                    return
            else:
                self.utf8_eat_bytes = None
                if continuation and not (self.modes.display_ctrl and byte < 0xA0):
                    # A lone continuation byte is not valid UTF-8 and is dropped, as in xterm. That includes 0x9B and
                    # bytes inside an escape sequence. Display control mode shows the C1 controls in that range.
                    return
                char = bytes([byte])
        else:
            # a sequence pending when urwid's encoding stopped being UTF-8 is not continued by bytes read in another one
            self.utf8_eat_bytes = None
            char = bytes([byte])

        self.process_char(char)

    def process_char(self, char: int | bytes) -> None:
        """
        Process a single character (single- and multi-byte).

        :param char: a byte string
        """
        x, y = self.term_cursor

        if isinstance(char, int):
            char = char.to_bytes(1, "little")

        dc = self.modes.display_ctrl
        # as in xterm, REP repeats only a character written just before it: a control character, or a control function
        # such as SGR, between them cancels the repeat
        graphic, self._last_graphic = self._last_graphic, None
        if not self.within_escape or char < b" " or char == b"\x7f":
            self._repeat_graphic = None

        if char == ESC_B and self.parsestate not in _STRING_STATES:  # escape
            # as in a terminal, an ESC drops a sequence still being read and starts a new one
            self.leave_escape()
            self.within_escape = True
            self._repeat_graphic = graphic
        elif self.parsestate in _STRING_STATES and char in b"\x18\x1a":
            # CAN/SUB abort a command string, also with display_ctrl
            self.leave_escape()
        elif (
            self.parsestate in _STRING_STATES
            and char in (_COMMAND_STRING_IGNORED if self.parsestate == 5 else _OSC_IGNORED)
            and (self._escbuf[-1:] != ESC_B or dc or char not in _EXECUTED_CONTROLS)
        ):
            # as in a terminal, such a control character inside a command string is neither executed nor part of its
            # body; after an ESC, one of _EXECUTED_CONTROLS is executed by the branches below, and the ESC stays pending
            pass
        elif not dc and char == b"\r":  # carriage return CR
            self.carriage_return()
        elif not dc and char == b"\x0f":  # activate G0
            self.charset.activate(0)
        elif not dc and char == b"\x0e":  # activate G1
            self.charset.activate(1)
        elif not dc and char in b"\n\v\f":  # line feed LF/VT/FF
            self.linefeed()
            if self.modes.lfnl:
                self.carriage_return()
        elif not dc and char == b"\t":  # char tab
            self.tab()
        elif not dc and char == b"\b":  # backspace BS
            if x > 0:
                self.set_term_cursor(x - 1, y)
            self.is_rotten_cursor = False
        elif not dc and char == b"\a" and self.parsestate not in {2, 4}:  # BEL
            # inside an OSC string (parsestate 2, or 4 once over-long) BEL is its terminator
            self.widget.beep()
        elif not dc and char in b"\x18\x1a":  # CAN/SUB
            self.leave_escape()
        elif not dc and (char in _IGNORED_CONTROLS or (char == b"\x7f" and self.parsestate not in {2, 4})):
            # as in a terminal, any other C0 control character and DEL are ignored, and an escape sequence continues
            pass
        elif not dc and char == b"\x9b" and self.parsestate not in _STRING_STATES:  # CSI (equivalent to "ESC [")
            # like ESC, it drops a sequence still being read; inside a command string it is part of the string
            self.leave_escape()
            self.within_escape = True
            self.parsestate = 1
            self._repeat_graphic = graphic
        elif self.within_escape:
            self.parse_escape(char)
        else:
            self.push_cursor(char)

    def set_char(
        self,
        char: bytes,
        x: int | None = None,
        y: int | None = None,
        *,
        dec_special: bool = False,
    ) -> None:
        """Set character of either the current cursor position or a position given by 'x' and/or 'y' to 'char'.

        The other half of a wide character the cell was part of becomes a space.

        :param char: the character to store.
        :param x: the column, the cursor's when not given.
        :param y: the row, the cursor's when not given.
        :param dec_special: store *char* in the DEC special character set instead of the active one.
        """
        if x is None:
            x = self.term_cursor[0]
        if y is None:
            y = self.term_cursor[1]

        x, y = self.constrain_coords(x, y)
        if self.protected:
            char = _Protected(char)
        line = self.term[y]
        replaced = line[x][2]
        line[x] = (self.attrspec, "0" if dec_special else self.charset.current, char)
        if not replaced or (len(replaced) > 1 and _drawn_width(replaced) == 2):
            # a wide character written over loses its other half
            _mend_wide(line, x)
            _mend_wide(line, x + 1)

    def constrain_coords(self, x: int, y: int, ignore_scrolling: bool = False) -> tuple[int, int]:
        """Check if x/y are within the terminal and return the corrected version.

        If 'ignore_scrolling' is set, constrain within the full size of the screen and not within scrolling region.
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
        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            if y >= self.height:
                y = self.height - 1
            elif y < 0:
                y = 0

        return x, y

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
        A cluster the display draws one column wider than its character, such as a heart with an emoji variation
        selector, takes the next cell as its second half, and the cursor moves past it; in the last column it moves to
        the next line with autowrap, as in kitty.

        It does not join the cluster:

        - when the cluster would hold more than :data:`_MAX_CLUSTER_LENGTH` code points;
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

    def save_cursor(self, with_attrs: bool = False) -> None:
        """Save the current cursor position.

        With *with_attrs*, as DECSC, the attributes, DECSCA, the character sets, origin mode and a pending autowrap are
        saved too.
        """
        self.saved_cursor = self.term_cursor
        if with_attrs:
            self.saved_attrs = (copy.copy(self.attrspec), copy.copy(self.charset))
            self.saved_flags = (self.modes.constrain_scrolling, self.is_rotten_cursor, self.protected)

    def restore_cursor(self, with_attrs: bool = False) -> None:
        """Restore the cursor position saved by :meth:`save_cursor`.

        Without *with_attrs* only the position is restored, a pending autowrap ends, and nothing happens when no
        position was saved.

        With *with_attrs*, as DECRC, the attributes, DECSCA, the character sets, origin mode and a pending autowrap are
        restored too.
        Whatever :meth:`save_cursor` did not save with them is reset instead, as in xterm: the cursor moves home when no
        position was saved, and the attributes, DECSCA, the character sets and origin mode take their startup values.
        """
        if self.saved_cursor is None and not with_attrs:
            return
        x, y = (0, 0) if self.saved_cursor is None else self.saved_cursor
        origin, wrap, protected = (False, False, False) if self.saved_flags is None else self.saved_flags

        if with_attrs:
            if self.saved_attrs is None:
                self.csi_set_attr([0])
                self.charset = TermCharset()
            else:
                self.attrspec, self.charset = (copy.copy(self.saved_attrs[0]), copy.copy(self.saved_attrs[1]))
            self.protected = protected
            # origin mode first, since it decides how the position is constrained
            self.modes.constrain_scrolling = origin

        self.set_term_cursor(x, y)
        self.is_rotten_cursor = with_attrs and wrap

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

    def csi_report_window(self, operation: int) -> None:
        """Answer the XTWINOPS size reports: the text area in pixels (14) and in characters (18).

        The size in pixels is reported as 0 by 0, which stands for unknown, as the pty the child reads its size from
        gives no pixels.
        The other window operations are ignored, since the size of the canvas is set by the widget it belongs to.
        """
        match operation:
            case 14:
                self.widget.respond(f"{ESC}[4;0;0t")
            case 18:
                self.widget.respond(f"{ESC}[8;{self.height:d};{self.width:d}t")

    def scroll(self, reverse: bool = False, *, scrollback: bool = True) -> None:
        """Append a new line at the bottom of the scrolling region and remove its topmost line.

        The removed line goes into the scrollback buffer when the region starts at the top row, as in xterm.
        A region below the top row drops it, and so does a scroll without *scrollback*.
        If reverse is True, do exactly the opposite, but don't save into scrollback buffer.
        """
        if reverse:
            self.term.pop(self.scrollregion_end)
            self.term.insert(self.scrollregion_start, self.empty_line())
        else:
            killed = self.term.pop(self.scrollregion_start)
            self.term.insert(self.scrollregion_end, self.empty_line())
            if self.scrollregion_start > 0 or not scrollback:
                return
            self.scrollback_buffer.append(killed)
            if self.scrolling_up and not self.scroll_on_output:
                # the view moves up with the lines it shows
                self.scrolling_up = min(self.scrolling_up + 1, len(self.scrollback_buffer))

    def csi_scroll(self, lines: int, *, reverse: bool = False) -> None:
        """Scroll the scrolling region up by *lines*, or down with *reverse*.

        This is SU (``CSI Ps S``), and SD (``CSI Ps T`` and ``CSI Ps ^``).
        The cursor and a pending wrap stay.
        As in xterm, the lines scrolled off the top are not saved in the scrollback.
        """
        for _ in range(min(lines, self.scrollregion_end - self.scrollregion_start + 1)):
            self.scroll(reverse=reverse, scrollback=False)

    def decaln(self) -> None:
        """DEC screen alignment test: fill the screen with E's, without attributes and in ASCII, as xterm does."""
        cell: tuple[AttrSpec | None, Literal["0", "U"] | None, bytes] = (None, None, b"E")
        for row in range(self.height):
            self.term[row] = [cell] * self.width

    def blank_line(self, row: int) -> None:
        """Blank a single line at the specified row, without modifying other lines."""
        self.term[row] = self.empty_line()

    def insert_chars(
        self,
        position: tuple[int, int] | None = None,
        chars: int = 1,
        char: bytes | None = None,
        *,
        dec_special: bool = False,
    ) -> None:
        """Insert 'chars' number of empty characters (or those given by 'char') before 'position'.

        Defaults to the current position if 'position' is not specified,
        pushing subsequent characters of the line to the right without wrapping.
        With *dec_special*, 'char' is stored in the DEC special character set instead of the active one.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        if char is None:
            # inserted blanks are written spaces, as in xterm
            char_spec = self.empty_char(b" ")
        else:
            charset: Literal["0", "U"] | None = "0" if dec_special else self.charset.current
            char_spec = (self.attrspec, charset, _Protected(char) if self.protected else char)

        x, y = position
        line = self.term[y]
        chars = min(chars, self.width - x)
        line[x:x] = [char_spec] * chars
        del line[self.width :]
        _mend_wide(line, x)
        _mend_wide(line, x + chars)
        _mend_wide(line, self.width)

    def remove_chars(self, position: tuple[int, int] | None = None, chars: int = 1) -> None:
        """Remove 'chars' number of empty characters from 'position'.

        Defaults to the current position if 'position' is not specified,
        pulling subsequent characters of the line to the left without joining any subsequent lines.
        """
        if position is None:
            position = self.term_cursor

        if chars == 0:
            chars = 1

        x, y = position
        chars = min(chars, self.width - x)
        line = self.term[y]
        del line[x : x + chars]
        line += [self.empty_char()] * chars
        _mend_wide(line, x)

    def insert_lines(self, row: int | None = None, lines: int = 1) -> None:
        """Insert 'lines' empty lines at 'row', or the cursor row, pushing the lines below down the scrolling region.

        Lines pushed past the bottom of the scrolling region are dropped.
        Nothing happens when the row is outside the scrolling region.
        """
        if row is None:
            row = self.term_cursor[1]

        if lines == 0:
            lines = 1

        if not self.scrollregion_start <= row <= self.scrollregion_end:
            return

        for _ in range(min(lines, self.scrollregion_end - row + 1)):
            self.term.insert(row, self.empty_line())
            self.term.pop(self.scrollregion_end + 1)

    def remove_lines(self, row: int | None = None, lines: int = 1) -> None:
        """Remove 'lines' lines at 'row', or the cursor row, pulling the lines below up the scrolling region.

        Empty lines fill the bottom of the scrolling region.
        Nothing happens when the row is outside the scrolling region.
        """
        if row is None:
            row = self.term_cursor[1]

        if lines == 0:
            lines = 1

        if not self.scrollregion_start <= row <= self.scrollregion_end:
            return

        for _ in range(min(lines, self.scrollregion_end - row + 1)):
            self.term.pop(row)
            self.term.insert(self.scrollregion_end, self.empty_line())

    def erase(
        self,
        start: tuple[int, int] | tuple[int, int, bool],
        end: tuple[int, int] | tuple[int, int, bool],
        *,
        selective: bool = False,
    ) -> None:
        """Erase a region of the terminal.

        As in xterm, the cells of a row erased up to its last column hold spaces never written, and the cells of a row
        erased short of it hold written spaces, which DECRQCRA counts.
        With *selective*, as DECSED and DECSEL, or as ED, EL and ECH after SPA, the protected characters are kept, and
        each run of cells between them is erased as a row would be.
        A pending wrap ends, as in xterm.

        The 'start' tuple (x, y) defines the starting position of the erase, while end (x, y) the last position.

        For example if the terminal size is 4x3, start=(1, 1) and end=(1, 2)
        would erase the following region:

        ....
        .XXX
        XX..
        """
        # pyrefly: ignore[bad-argument-type]  # the optional third element widens to bool | int
        sx, sy = self.constrain_coords(*start)
        # pyrefly: ignore[bad-argument-type]  # the optional third element widens to bool | int
        ex, ey = self.constrain_coords(*end)

        self.is_rotten_cursor = False
        blank = self.empty_char()
        written = self.empty_char(b" ")
        for y in range(sy, ey + 1):
            line = self.term[y]
            first = sx if y == sy else 0
            last = ex if y == ey else self.width - 1
            runs = [(first, last)]
            if selective:
                kept = [x for x in range(first, last + 1) if isinstance(line[x][2], _Protected)]
                runs = list(zip((first, *(x + 1 for x in kept)), (*(x - 1 for x in kept), last), strict=True))
            for run_first, run_last in runs:
                if run_first <= run_last:
                    cell = blank if run_last == self.width - 1 else written
                    line[run_first : run_last + 1] = [cell] * (run_last - run_first + 1)
                    _mend_wide(line, run_first)
                    _mend_wide(line, run_last + 1)

    def csi_set_attr(self, attrs: Sequence[int]) -> None:
        """Set graphics rendition.

        The colour/attribute-flag computation itself is delegated to the shared, platform-independent
        :func:`urwid.ansi_parser.sgi_params_to_attrspec`; SGR 10/11/12 toggle vterm's own charset/display-control
        state rather than colour/attributes, so that side effect is applied separately, here, since
        ``sgi_params_to_attrspec`` deliberately ignores it (see its docstring).

        :param attrs: the SGR numeric parameters to apply, in encounter order.
            The arguments of an extended color are never read as SGR 10 to 12.
        """
        for code in split_sgr_parameters(attrs):
            if code == (10,):
                self.charset.reset_sgr_ibmpc()
                self.modes.display_ctrl = False
            elif code in {(11,), (12,)}:
                self.charset.set_sgr_ibmpc()
                self.modes.display_ctrl = True

        self.attrspec = sgi_params_to_attrspec(attrs, self.attrspec)

    def reverse_attrspec(self, attrspec: AttrSpec | None, undo: bool = False) -> AttrSpec:
        """Put standout mode to the 'attrspec' given and remove it if 'undo' is True."""
        return _with_flag(attrspec, "standout", remove=undo)

    @deprecated(
        "TermCanvas.reverse_video() is deprecated, set TermCanvas.modes.reverse_video instead. "
        "Deprecated since urwid 5.1.3, will be removed in version 8.0.",
        category=None,
    )
    def reverse_video(self, undo: bool = False) -> None:
        """Turn the reverse video mode (DECSCNM) on, or off if *undo* is True.

        .. deprecated:: 5.1.3
            Set :attr:`TermCanvas.modes.reverse_video <TermModes.reverse_video>` instead.
            This method will be removed in version 8.0.
        """
        _deprecation.warn(
            "TermCanvas.reverse_video() is deprecated, set TermCanvas.modes.reverse_video instead.",
            since="5.1.3",
            removed_in="8.0",
            category=PendingDeprecationWarning,
        )
        self.modes.reverse_video = not undo

    def set_mode(
        self,
        mode: int,
        flag: bool,
        qmark: bool,
        reset: bool,
    ) -> None:
        """Set a single mode, as a helper for csi_set_modes."""
        if qmark:
            # DEC private mode
            private_mode = str(mode)
            if private_mode == PrivateMode.APPLICATION_CURSOR_KEYS:
                # cursor keys send an ESC O prefix, rather than ESC [
                self.modes.keys_decckm = flag
            elif private_mode == PrivateMode.COLUMNS_132:
                # deccolm just clears the screen
                self.clear()
            elif private_mode == PrivateMode.REVERSE_VIDEO:
                # content() applies the mode, so a change touches no cell
                self.modes.reverse_video = flag
            elif private_mode == PrivateMode.ORIGIN_MODE:
                self.modes.constrain_scrolling = flag
                self.set_term_cursor(0, 0)
                self.is_rotten_cursor = False
            elif private_mode == PrivateMode.AUTO_WRAP:
                self.modes.autowrap = flag
            elif private_mode == PrivateMode.CURSOR_VISIBLE:
                self.modes.visible_cursor = flag
                self.set_term_cursor()
            elif private_mode == PrivateMode.MOUSE_X10:
                # X10 compatibility is a last resort: it does not replace a tracking mode the child turned on,
                # and its reset ends only itself.
                if flag and self.modes.mouse_tracking is None:
                    self.modes.mouse_tracking = PrivateMode(private_mode)
                elif not flag and self.modes.mouse_tracking == PrivateMode.MOUSE_X10:
                    self.modes.mouse_tracking = None
            elif private_mode in _MOUSE_TRACKING_MODES:
                # As in xterm, the tracking modes replace each other, and resetting any of them stops tracking.
                self.modes.mouse_tracking = PrivateMode(private_mode) if flag else None
            elif private_mode in _MOUSE_ENCODING_MODES:
                # As in xterm, the encodings replace each other, and a reset only ends the encoding it names.
                if flag:
                    self.modes.mouse_encoding = PrivateMode(private_mode)
                elif self.modes.mouse_encoding == private_mode:
                    self.modes.mouse_encoding = None
            elif private_mode in _RECOGNISED_IGNORED_MODES:
                pass  # for the reason given at each member of PrivateMode
            elif private_mode in _ALTERNATE_SCREEN_MODES:
                self.set_alternate_screen(PrivateMode(private_mode), flag)
            elif private_mode == PrivateMode.SAVE_CURSOR:
                # set saves the cursor as DECSC does, and reset restores it as DECRC does
                if flag:
                    self.save_cursor(with_attrs=True)
                else:
                    self.restore_cursor(with_attrs=True)
            elif private_mode == PrivateMode.NUMERIC_KEYPAD:
                self.modes.keypad_application = flag
            elif private_mode == PrivateMode.BACKARROW_KEY:
                self.modes.backarrow_sends_backspace = flag
            elif private_mode == PrivateMode.BRACKETED_PASTE:
                self.modes.bracketed_paste = flag
            elif private_mode == PrivateMode.FOCUS_REPORTING:
                self.modes.focus_reporting = flag
            elif private_mode == PrivateMode.ALTERNATE_SCROLL:
                self.modes.alternate_scroll = flag
            elif private_mode == PrivateMode.IN_BAND_RESIZE:
                self.modes.in_band_resize = flag
                # the mode asks for a report of the current size on each set, also when it was already set
                if flag:
                    self.widget.respond(window_size_report(self.width, self.height))
            elif private_mode == PrivateMode.SYNCHRONIZED_OUTPUT:
                # Synchronized output (https://gist.github.com/christianparpart/d8a62cc1ab659194337d73e399004036):
                # the child program is asking that its writes not be displayed until it closes the
                # block with CSI ?2026l.
                # Terminal.feed() reads that flag to keep draining the pty instead of handing a mid-update canvas
                # back to the next render() pass.
                self.modes.synchronized_output = flag
        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            # ECMA-48
            if mode == 3:
                self.modes.display_ctrl = flag
            elif mode == 4:
                self.modes.insert = flag
            elif mode == 20:
                self.modes.lfnl = flag

    def private_mode_state(self, mode: str) -> bool | None:
        """Return whether DEC private *mode* is set.

        :returns: the state, or None for a mode this canvas keeps no state for.
        """
        modes = self.modes
        match mode:
            case PrivateMode.APPLICATION_CURSOR_KEYS:
                return modes.keys_decckm
            case PrivateMode.REVERSE_VIDEO:
                return modes.reverse_video
            case PrivateMode.ORIGIN_MODE:
                return modes.constrain_scrolling
            case PrivateMode.AUTO_WRAP:
                return modes.autowrap
            case PrivateMode.CURSOR_VISIBLE:
                return modes.visible_cursor
            case PrivateMode.NUMERIC_KEYPAD:
                return modes.keypad_application
            case PrivateMode.BACKARROW_KEY:
                return modes.backarrow_sends_backspace
            case PrivateMode.BRACKETED_PASTE:
                return modes.bracketed_paste
            case PrivateMode.FOCUS_REPORTING:
                return modes.focus_reporting
            case PrivateMode.ALTERNATE_SCROLL:
                return modes.alternate_scroll
            case PrivateMode.SYNCHRONIZED_OUTPUT:
                return modes.synchronized_output
            case PrivateMode.IN_BAND_RESIZE:
                return modes.in_band_resize
            case _ if mode == PrivateMode.MOUSE_X10 or mode in _MOUSE_TRACKING_MODES:
                return modes.mouse_tracking == mode
            case _ if mode in _MOUSE_ENCODING_MODES:
                return modes.mouse_encoding == mode
            case _ if mode in _ALTERNATE_SCREEN_MODES:
                return modes.alternate_screen
        return None

    def csi_report_private_mode(self, mode: int) -> None:
        """Answer a DECRQM query for DEC private *mode* with a DECRPM reply (CSI ? mode ; state $ y).

        The state is 1 for a set mode, 2 for a reset one, and 0 for a mode this canvas keeps no state for.
        The modes in :data:`_FIXED_PRIVATE_MODE_STATES` are reported in the state it gives them.
        """
        state = self.private_mode_state(str(mode))
        if mode in _FIXED_PRIVATE_MODE_STATES:
            value = _FIXED_PRIVATE_MODE_STATES[mode]
        else:
            value = 0 if state is None else 1 if state else 2
        self.widget.respond(f"{ESC}[?{mode:d};{value:d}$y")

    def csi_report_mode(self, mode: int) -> None:
        """Answer a DECRQM query for ANSI *mode* with a DECRPM reply (CSI mode ; state $ y).

        The state is 1 for a set mode and 2 for a reset one.
        KAM (2) is reported as permanently reset (4), and SRM (12) as permanently set (3), since neither changes, and
        so are the ECMA-48 modes of a VT320 that keep their reset state (1, 5, 7, 10, 11 and 13 to 19), as in xterm.
        Any other mode this canvas keeps no state for is reported as 0.
        """
        modes = self.modes
        match mode:
            case 3:
                value = 1 if modes.display_ctrl else 2
            case 4:
                value = 1 if modes.insert else 2
            case 20:
                value = 1 if modes.lfnl else 2
            case _:
                value = _FIXED_ANSI_MODE_STATES.get(mode, 0)
        self.widget.respond(f"{ESC}[{mode:d};{value:d}$y")

    def soft_reset(self) -> None:
        """Reset the modes, margins, attributes and character sets DECSTR resets, as xterm does.

        The cursor is shown with the startup style, insert, origin, cursor key and keypad application modes are reset,
        and autowrap is set.
        The scrolling region is the whole screen again, without moving the cursor.
        The attributes are reset as by SGR 0, DECSCA and SPA stop protecting characters, ED, EL and ECH erase the
        protected ones again, and the character sets are the startup ones.
        The cursor saved by DECSC is the home position with these attributes and character sets, origin mode off and no
        pending autowrap.
        """
        modes = self.modes
        modes.visible_cursor = True
        modes.insert = False
        modes.constrain_scrolling = False
        modes.autowrap = True
        modes.keys_decckm = False
        modes.keypad_application = False
        modes.cursor_style = None
        self.reset_scroll()
        self.csi_set_attr([0])
        self.protected = False
        self.modes.iso_protection = False
        self.charset = TermCharset()
        self.saved_cursor = (0, 0)
        self.saved_attrs = (copy.copy(self.attrspec), TermCharset())
        self.saved_flags = (False, False, False)
        self.set_term_cursor()

    def dcs_request_setting(self, request: bytes) -> None:
        """Answer a DECRQSS query for the setting *request* names with a DECRPSS reply (DCS Ps $ r Pt ST).

        The reply follows xterm:

        - a valid request gets Ps 1, and Pt is the control sequence that restores the setting;
        - a setting this canvas does not report gets Ps 0 and an empty Pt.

        The settings reported are SGR (``m``), DECSTBM (``r``), DECSCL (``"p``), DECSCA (``"q``), DECSCPP (``$|``),
        DECSLRM (``s``), DECSNLS (``*|``), DECSLPP (``t``), DECSACE (``*x``) and DECSCUSR (`` q``).
        """
        match request:
            case b"m":
                setting = f"{_sgr_parameters(self.attrspec)}m"
            case b"r":
                setting = f"{self.scrollregion_start + 1:d};{self.scrollregion_end + 1:d}r"
            case b'"p':
                # 7-bit controls (1), the only ones sent
                setting = f'{self.conformance_level:d};1"p'
            case b'"q':
                # as in xterm, the characters SPA protects are not reported
                setting = f'{self.protected and not self.modes.iso_protection:d}"q'
            case b"$|":
                # DECSCPP: the columns per page
                setting = f"{self.width:d}$|"
            case b"s":
                # DECSLRM: the left and right margins, the screen's edges, since DECLRMM cannot be set
                setting = f"1;{self.width:d}s"
            case b"*|":
                # DECSNLS: the lines per screen
                setting = f"{self.height:d}*|"
            case b"t":
                # DECSLPP: the lines per page
                setting = f"{self.height:d}t"
            case b"*x":
                setting = f"{self.attribute_extent:d}*x"
            case b" q":
                # DECSCUSR: the cursor style
                style = self.modes.cursor_style
                setting = f"{_DEFAULT_CURSOR_STYLE if style is None else style:d} q"
            case _:
                self.widget.respond(f"{ESC}P0$r{ESC}\\")
                return
        self.widget.respond(f"{ESC}P1$r{setting}{ESC}\\")

    def csi_report_presentation_state(self, report: int) -> None:
        """Answer DECRQPSR for *report* 1 with DECCIR and for *report* 2 with DECTABSR.

        Any other report is not answered.

        DECCIR is ``DCS 1 $ u Pr ; Pc ; Pp ; Srend ; Satt ; Sflag ; Pgl ; Pgr ; Scss ; Sdesig ST``, as xterm sends it:

        - the 1-based cursor row and column on the screen, also in origin mode, and page 1;
        - ``@`` plus the bits of bold (1), underline (2), blink (4) and reverse (8);
        - ``@`` plus 1 while DECSCA protects the characters written, where xterm adds 1 once DECSCA has protected any
          since the last reset, and neither adds it for SPA;
        - ``@`` plus the bits of origin mode (1), a pending SS2 (2) or SS3 (4), and a pending autowrap (8);
        - the slots invoked into GL and GR;
        - ``@`` plus a bit per slot holding a 96-character set, and the final bytes G0 to G3 were designated with.

        DECTABSR is ``DCS 2 $ u Pt ST``, with the 1-based columns of the tab stops separated by ``/``.
        """
        match report:
            case 1:
                x, y = self.term_cursor
                rendition = sum(bit for name, bit, _sgr in _RENDITION_BITS if getattr(self.attrspec, name, False))
                single = self.charset.single_shifted
                flags = (
                    _FLAG_ORIGIN * self.modes.constrain_scrolling
                    + _FLAG_SS2 * (single == 2)
                    + _FLAG_SS3 * (single == 3)
                    + _FLAG_WRAP * self.is_rotten_cursor
                )
                finals, sets96 = self.charset.designations
                # as in xterm, the characters SPA protects are not reported
                protection = self.protected and not self.modes.iso_protection
                body = (
                    f"{y + 1:d};{x + 1:d};1;{chr(0x40 + rendition)};{chr(0x40 + protection)};{chr(0x40 + flags)};"
                    f"{self.charset.active:d};{self.charset.gr:d};{chr(0x40 + sets96)};{finals.decode('ascii')}"
                )
                self.widget.respond(f"{ESC}P1$u{body}{ESC}\\")
            case 2:
                stops = "/".join(str(x + 1) for x in range(self.width) if self.is_tabstop(x))
                self.widget.respond(f"{ESC}P2$u{stops}{ESC}\\")

    def dcs_restore_cursor_information(self, body: bytes) -> None:
        """Restore the cursor, its attributes and the character sets from a DECCIR report *body* (DECRSPS 1).

        A body that is not in the form :meth:`csi_report_presentation_state` describes is ignored whole.
        The colours are kept, since DECCIR does not carry them.
        DECSCA is restored too, which xterm does not do; while SPA protects, which DECCIR does not report, the
        protection is kept.
        """
        fields = body.split(b";")
        if len(fields) != 10:
            return
        row, col, _page, rendition, protection, flags, gl, gr, sets96, finals = fields
        bits = [
            field[0] - 0x40
            for field in (rendition, protection, flags, sets96)
            if len(field) == 1 and 0x40 <= field[0] < 0x50
        ]
        if len(bits) != 4 or not (row.isdigit() and col.isdigit()):
            return
        if {gl, gr} - {b"0", b"1", b"2", b"3"} or len(finals) != 4 or not all(0x30 <= final < 0x7F for final in finals):
            return
        rendition_bits, protection_bits, flag_bits, sets96_bits = bits
        if not self.modes.iso_protection:
            self.protected = bool(protection_bits & 1)
        # origin mode first, since it decides how the cursor position is constrained
        self.modes.constrain_scrolling = bool(flag_bits & _FLAG_ORIGIN)
        self.set_term_cursor(int(col) - 1, int(row) - 1)
        self.is_rotten_cursor = bool(flag_bits & _FLAG_WRAP)
        # SGR 22 also ends faint, which DECCIR does not carry, so faint is set again, as xterm keeps it
        faint = [2] if getattr(self.attrspec, "faint", False) else []
        self.csi_set_attr(
            [22, 24, 25, 27, *faint, *(sgr for _name, bit, sgr in _RENDITION_BITS if rendition_bits & bit)],
        )
        for g, final in enumerate(finals):
            final_byte = bytes((final,))
            self.charset.define(
                g,
                _DESIGNATED_CHARSETS.get(final_byte, "default"),
                final=final_byte,
                size96=bool(sets96_bits & (1 << g)),
            )
        self.charset.activate(int(gl))
        self.charset.gr = int(gr)
        self.charset.end_single_shift()
        if flag_bits & (_FLAG_SS2 | _FLAG_SS3):
            self.charset.single_shift(2 if flag_bits & _FLAG_SS2 else 3)

    def dcs_request_termcap(self, names: bytes) -> None:
        """Answer an XTGETTCAP query (DCS + q Pt ST) for the capability names in *names*.

        Each name is hex-encoded, and the names are separated by ``;``.
        The capabilities answered describe the colors of the display, :attr:`display_colors`:

        - ``Co`` and ``colors``, the termcap and terminfo names of the color count, for a display with colors,
          at most the 256 of the palette;
        - ``RGB``, 8 bits per channel, for a display that draws any RGB color.

        The reply follows xterm:

        - the names are answered in order up to the first one that is not answered;
        - those answered are listed in one DCS 1 + r Pt ST, Pt holding ``name=value;`` for each, the value hex-encoded
          as the name is;
        - when the first name is not answered, the reply is DCS 0 + r ST.
        """
        values: dict[str, str] = {}
        if self.display_colors is not None and self.display_colors > 1:
            values["Co"] = values["colors"] = str(min(self.display_colors, _PALETTE_COLORS))
            if self.display_colors == _TRUE_COLORS:
                values["RGB"] = "8"
        answered = ""
        for name in names.split(b";"):
            try:
                hex_name = name.decode("ascii")
                key = bytes.fromhex(hex_name).decode("ascii")
            except ValueError:
                break
            if key not in values:
                break
            answered += f"{hex_name}={values[key].encode('ascii').hex().upper()};"
        self.widget.respond(f"{ESC}P1+r{answered}{ESC}\\" if answered else f"{ESC}P0+r{ESC}\\")

    def dcs_restore_tab_stops(self, body: bytes) -> None:
        """Set the tab stops to the 1-based columns of a DECTABSR report *body* (DECRSPS 2), separated by ``/``.

        An empty body clears every tab stop, and a body with anything but such columns is ignored whole.
        A column past the right edge is dropped.
        """
        columns = body.split(b"/") if body else []
        if not all(column.isdigit() for column in columns):
            return
        self.set_tabstop(clear=True)
        for column in columns:
            if 0 < int(column) <= self.width:
                self.set_tabstop(int(column) - 1)

    def _rectangle(self, params: Sequence[int | None]) -> tuple[int, int, int, int] | None:
        """Return the rectangle the parameters Pt ; Pl ; Pb ; Pr of a VT420 rectangular area sequence select.

        A missing or zero parameter selects the edge of the page, and a parameter past the edge selects the edge.
        In origin mode the rows count from the top margin and stop at the bottom margin, as in xterm.

        :returns: the 0-based top row, left column, bottom row and right column, all included, or None for a rectangle
            whose top is below its bottom or whose left is right of its right.
        """
        top, left, bottom, right = (*params, None, None, None, None)[:4]
        if self.modes.constrain_scrolling:
            first, last = self.scrollregion_start, self.scrollregion_end
        else:
            first, last = 0, self.height - 1
        top_row = min(first + (top or 1) - 1, last)
        bottom_row = last if not bottom else min(first + bottom - 1, last)
        left_col = min((left or 1) - 1, self.width - 1)
        right_col = self.width - 1 if not right else min(right - 1, self.width - 1)
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

    def csi_select_protection(self, params: Sequence[int | None]) -> None:
        """Protect the characters written from now on from the selective erases, or stop (DECSCA, CSI Ps " q).

        1 protects them, and 0, 2 or no parameter stops; any other value is ignored, as in xterm.
        Any value ends the ISO protection SPA selected, so ED, EL and ECH erase the protected characters again.
        """
        self.modes.iso_protection = False
        if params[0] in {None, 0, 1, 2}:
            self.protected = params[0] == 1

    def csi_request_user_preferred_supplemental_set(self, _params: Sequence[int | None]) -> None:
        """Answer DECRQUPSS (``CSI & u``) with DECAUPSS for ISO Latin-1, ``DCS 1 ! u A ST``.

        That is the 96-character set a designation such as ``ESC - A`` draws.
        It is not answered at the VT100 level (61), like the other DCS replies.
        """
        if self.conformance_level > 61:
            self.widget.respond(f"{ESC}P1!uA{ESC}\\")

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
        It is not answered at the VT100 level (61), like the other DCS replies.
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
        self.widget.respond(f"{ESC}P{request:d}!~{-total & 0xFFFF:04X}{ESC}\\")

    def csi_report_displayed_extent(self, _params: Sequence[int | None]) -> None:
        """Answer DECRQDE (``CSI " v``) with DECRPDE.

        The reply is the height and the width, and column, row and page 1 at the top left.
        """
        self.widget.respond(f'{ESC}[{self.height:d};{self.width:d};1;1;1"w')

    def csi_insert_columns(self, params: Sequence[int | None]) -> None:
        """Insert blank columns at the cursor column in the scrolling region (DECIC, CSI Ps ' }).

        Nothing happens while the cursor is outside the scrolling region.
        """
        x, y = self.term_cursor
        if self.scrollregion_start <= y <= self.scrollregion_end:
            for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                self.insert_chars((x, row), chars=params[0] or 1)

    def csi_delete_columns(self, params: Sequence[int | None]) -> None:
        """Delete columns at the cursor column in the scrolling region (DECDC, CSI Ps ' ~).

        Nothing happens while the cursor is outside the scrolling region.
        """
        x, y = self.term_cursor
        if self.scrollregion_start <= y <= self.scrollregion_end:
            for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                self.remove_chars((x, row), chars=params[0] or 1)

    def back_index(self) -> None:
        """Move the cursor one column left, or at the left edge insert a blank column there (DECBI)."""
        x, y = self.term_cursor
        if x > 0:
            self.set_term_cursor(x - 1, y)
        else:
            self.csi_insert_columns([1])
        self.is_rotten_cursor = False

    def forward_index(self) -> None:
        """Move the cursor one column right, or at the right edge delete the leftmost column (DECFI)."""
        x, y = self.term_cursor
        if x < self.width - 1:
            self.set_term_cursor(x + 1, y)
        elif self.scrollregion_start <= y <= self.scrollregion_end:
            for row in range(self.scrollregion_start, self.scrollregion_end + 1):
                self.remove_chars((0, row))
        self.is_rotten_cursor = False

    def csi_set_cursor_style(self, params: Sequence[int | None]) -> None:
        """Set the cursor style DECSCUSR (``CSI Ps SP q``) selects.

        0 selects 1, as in xterm, and any value past 6 is ignored.
        From then on :meth:`content` draws the cursor cell itself, see :attr:`TermModes.cursor_style`.
        """
        style = params[0] or 1
        if style in _CURSOR_STYLES:
            self.modes.cursor_style = style
            self.set_term_cursor()

    def csi_set_modes(
        self,
        modes: Iterable[int],
        qmark: bool,
        reset: bool = False,
    ) -> None:
        """Set (DECSET/ECMA-48) or reset modes (DECRST/ECMA-48) if reset is True."""
        flag = not reset

        for mode in modes:
            self.set_mode(mode, flag, qmark, reset)

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

    def csi_get_device_attributes(self, qmark: bool) -> None:
        """Report the primary device attributes: a VT220 with ANSI colour."""
        if not qmark:
            self.widget.respond(_PRIMARY_DEVICE_ATTRIBUTES)

    def csi_keyboard_flags(self, marker: bytes, params: Sequence[int | None]) -> None:
        """Act on a kitty keyboard protocol sequence for the flag stack of the screen shown.

        An empty stack means no flags. The sequences are:

        - ``CSI ? u``, answered with ``CSI ? flags u``.
        - ``CSI > flags u``, which pushes *flags*.
        - ``CSI < number u``, which pops *number* entries, 1 by default.
        - ``CSI = flags ; mode u``, which changes the entry on top, or adds one to an empty stack. *mode* 1, the
          default, sets *flags*. *mode* 2 adds them. *mode* 3 removes them.

        :param marker: the private marker that selects the sequence: ``?``, ``>``, ``<`` or ``=``.
        :param params: the parameters after it, None for an empty one.
        :raises ValueError: *marker* is none of these.
        """
        stack = self.modes.keyboard_flags
        flags = int((params[0] or 0) & _KITTY_KEYBOARD_ALL_FLAGS)
        current = stack[-1] if stack else 0
        if marker == b"?":
            self.widget.respond(f"{ESC}[?{current:d}u")
        elif marker == b">":
            stack.append(flags)
            del stack[:-_KITTY_KEYBOARD_STACK_LIMIT]
        elif marker == b"<":
            del stack[-(params[0] or 1) :]
        elif marker == b"=":
            mode = params[1] if len(params) > 1 and params[1] is not None else 1
            if mode == 1:
                current = flags
            elif mode == 2:
                current |= flags
            elif mode == 3:
                current &= ~flags
            else:
                return
            if stack:
                stack[-1] = current
            else:
                stack.append(current)
        else:
            msg = f"Not a kitty keyboard protocol marker: {marker!r}"
            raise ValueError(msg)

    def csi_status_report(self, mode: int, *, private: bool = False) -> None:
        """Answer a device status report (DSR) query for *mode*, as xterm does.

        :param mode: the report asked for:

            - 5, the device status report: the terminal is OK;
            - 6, the cursor position report, with the row counted from the top margin in origin mode, as CUP takes it.
        :param private: the DEC form, ``CSI ? Ps n``, was sent.
            Its cursor position report (DECXCPR) adds page 1, and it also answers 15 (no printer), 25 (user-defined
            keys unlocked) and 26 (a North American keyboard, ready, an LK201).
        """
        prefix = "?" if private else ""
        if mode == 5:
            self.widget.respond(f"{ESC}[{prefix}0n")
        elif mode == 6:
            x, y = self.term_cursor
            if self.modes.constrain_scrolling:
                y -= self.scrollregion_start
            self.widget.respond(f"{ESC}[{prefix}{y + 1:d};{x + 1:d}{';1' if private else ''}R")
        elif private and mode in _PRIVATE_STATUS_REPORTS:
            self.widget.respond(f"{ESC}[?{_PRIVATE_STATUS_REPORTS[mode]}n")

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

    def csi_set_keyboard_leds(self, mode: int = 0) -> None:
        """Set keyboard LEDs.

        This currently just emits a signal, so it can be processed by another widget or the main application.

        The mode-to-state-name mapping is delegated to the shared :func:`urwid.ansi_parser.led_state`, so it is
        maintained in exactly one place.

        :param mode: one of ``0`` (clear all LEDs), ``1`` (set scroll lock LED), ``2`` (set num lock LED) or
            ``3`` (set caps lock LED).
        """
        state = led_state(mode)

        if state is not None:
            self.widget.leds(state)  # type: ignore[arg-type]

    def clear(self, cursor: tuple[int, int] | None = None) -> None:
        """Clear the whole terminal screen and move the cursor to (0, 0) or to 'cursor'.

        A pending wrap ends, as in xterm.
        """
        self.term = [self.empty_line() for _ in range(self.height)]

        if cursor is None:
            self.set_term_cursor(0, 0)
        else:
            self.set_term_cursor(*cursor)
        self.is_rotten_cursor = False

    def cols(self) -> int:
        """Return the canvas's number of columns."""
        return self.width

    def rows(self) -> int:
        """Return the canvas's number of rows."""
        return self.height

    def content(  # type: ignore[override]
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]:
        """Canvas content.

        The cells store the attributes the child set.
        While the reverse video mode (DECSCNM) is on, every line is yielded with its attributes in standout.
        After a DECSCUSR the shown cursor cell is drawn in reverse video for a block or a bar, or underlined for an
        underline, and the blinking styles are drawn steady.
        A cell that is already in reverse video, or already underlined for an underline, is drawn without it.

        All parameters are ignored.
        """
        lines = self._screen_lines()
        style = self.modes.cursor_style
        if style is None or (shown := self._shown_cursor()) is None:
            yield from lines
            return
        cursor_x, cursor_y = shown
        for row, line in enumerate(lines):
            if row != cursor_y or cursor_x >= len(line):
                yield line
                continue
            # a copy, so the screen's own row is not changed
            drawn = list(line)
            if not drawn[cursor_x][2] and cursor_x > 0:
                # the second half of a wide character: its first half draws both
                cursor_x -= 1
            cell_attr, charset, text = drawn[cursor_x]
            # the flag is turned off on a cell that already has it, so the cursor stays visible there
            flag = "underline" if style in _UNDERLINE_CURSOR_STYLES else "standout"
            cell_attr = _with_flag(cell_attr, flag, remove=cell_attr is not None and getattr(cell_attr, flag))
            drawn[cursor_x] = (cell_attr, charset, text)
            yield drawn

    def _screen_lines(self) -> Iterator[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]:
        """Yield the rows in view, with their attributes in standout while the reverse video mode (DECSCNM) is on."""
        lines: Iterable[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]]
        if self.scrolling_up == 0:
            lines = self.term
        else:
            viewport_range = slice(-(self.height + self.scrolling_up), -self.scrolling_up)
            lines = (_fit_line(line, self.width) for line in (*self.scrollback_buffer, *self.term)[viewport_range])

        if not self.modes.reverse_video:
            yield from lines
            return

        # a screen holds few distinct attributes, so each one is reversed once per call
        reversed_attrs: dict[AttrSpec | None, AttrSpec] = {}
        for line in lines:
            reversed_line: list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]] = []
            for cell_attr, charset, text in line:
                if cell_attr not in reversed_attrs:
                    reversed_attrs[cell_attr] = self.reverse_attrspec(cell_attr)
                reversed_line.append((reversed_attrs[cell_attr], charset, text))
            yield reversed_line


#: the CSI sequences with an intermediate byte before the final one, by intermediate and final byte, run with their
#: parameters, None for an empty one
_INTERMEDIATE_COMMANDS: typing.Final[Mapping[tuple[bytes, bytes], Callable[[TermCanvas, list[int | None]], None]]] = (
    types.MappingProxyType(
        {
            (b'"', b"v"): TermCanvas.csi_report_displayed_extent,
            (b"$", b"x"): TermCanvas.csi_fill_rectangle,
            (b"$", b"z"): TermCanvas.csi_erase_rectangle,
            (b"$", b"{"): TermCanvas.csi_selective_erase_rectangle,
            (b"$", b"r"): TermCanvas.csi_change_area_attributes,
            (b"$", b"t"): TermCanvas.csi_reverse_area_attributes,
            (b"*", b"x"): TermCanvas.csi_select_attribute_extent,
            (b'"', b"q"): TermCanvas.csi_select_protection,
            (b"&", b"u"): TermCanvas.csi_request_user_preferred_supplemental_set,
            (b"$", b"v"): TermCanvas.csi_copy_rectangle,
            (b"*", b"y"): TermCanvas.csi_request_checksum,
            (b"'", b"}"): TermCanvas.csi_insert_columns,
            (b"'", b"~"): TermCanvas.csi_delete_columns,
            (b" ", b"q"): TermCanvas.csi_set_cursor_style,
        }
    )
)
