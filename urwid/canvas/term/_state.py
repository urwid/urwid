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

"""Terminal modes and character set slots a :class:`~urwid.canvas.term.TermCanvas` tracks."""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, field

from urwid import util
from urwid.canvas.term._cells import CHARSET_DEFAULT
from urwid.display.escape import (
    _C0_CONTROLS,
    _C1_CONTROLS,
    ALT_DEC_SPECIAL_CHARS,
    DEC_SPECIAL_CHARS,
    PrivateMode,
)

if typing.TYPE_CHECKING:
    from typing import Literal

#: the terminal types a TermCanvas emulates, the Linux console or xterm, which the child is given as TERM
TermType: typing.TypeAlias = typing.Literal["linux", "xterm-256color"]
TERM_TYPES: typing.Final = frozenset(typing.get_args(TermType))


#: the final byte each TermCharset name is reported with, the inverse of _DESIGNATED_CHARSETS, ASCII for the default
_CHARSET_FINALS: typing.Final = types.MappingProxyType({"default": b"B", "vt100": b"0", "ibmpc": b"U", "user": b"K"})


#: the C0 and C1 control characters and DEL in UTF-8, which a UTF-8 terminal executes instead of showing a glyph
_UTF8_CONTROLS = frozenset(chr(code).encode("utf-8") for code in (*_C0_CONTROLS, 0x7F, *_C1_CONTROLS))


@dataclass(eq=True, order=False, slots=True, weakref_slot=True)
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
    # DECLRMM: CSI Pl ; Pr s sets the left and right margins (DECSLRM) rather than saving the cursor (SCOSC)
    left_right_margins: bool = False

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
        self.left_right_margins = False

        self.keyboard_flags = []

        # charset stuff
        self.main_charset = CHARSET_DEFAULT


class TermCharset:
    """Tracks the terminal's G0 to G3 character set slots and which one is currently active."""

    __slots__ = ("_finals", "_g", "_sets96", "_sgr_mapping", "_single", "active", "current", "gr")

    MAPPING: typing.ClassVar[dict[str, str | None]] = {
        "default": None,
        "vt100": "0",
        "ibmpc": "U",
        "user": None,
    }

    def __init__(self, *, g1_graphics: bool = True) -> None:
        """Initialize with G0, G2 and G3 at the default charset, G0 active.

        :param g1_graphics: G1 starts as DEC special graphics, as on the Linux console; otherwise it starts at the
            default charset, as in xterm.
        """
        g1 = "vt100" if g1_graphics else "default"
        # a tuple, so a copy kept by DECSC is not changed by a later designation
        self._g: tuple[str, ...] = ("default", g1, "default", "default")
        # the final byte each slot was designated with, and a bit per slot designated with a 96-character set
        self._finals: tuple[bytes, ...] = (b"B", _CHARSET_FINALS[g1], b"B", b"B")
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
