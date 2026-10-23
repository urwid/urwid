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


"""Terminal emulator widget and the canvas it renders its screen on."""

from __future__ import annotations

import atexit
import copy
import errno
import fcntl
import os
import pty
import selectors
import signal
import struct
import sys
import termios
import time
import traceback
import typing
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field

from urwid import event_loop, util
from urwid.ansi_parser import (
    MAX_CSI_LENGTH,
    MAX_OSC_LENGTH,
    OSC_IGNORED_CONTROLS,
    attrspec_with_hyperlink,
    led_state,
    resolve_osc_hyperlink,
    resolve_osc_title,
    sgi_params_to_attrspec,
)
from urwid.canvas import Canvas
from urwid.display import AttrSpec, RealTerminal
from urwid.display.escape import (
    _CSI_LETTER_KEYS,
    _CSI_TILDE_KEYS,
    _CSI_U_KEYS,
    _KEY_MODIFIER_PREFIXES,
    _MOUSE_BYTE_OFFSET,
    _MOUSE_COORD_OFFSET,
    ALT_DEC_SPECIAL_CHARS,
    DEC_SPECIAL_CHARS,
    MOUSE_X10_PAST_END,
    KeyModifier,
    KittyKeyboardFlag,
    MouseBit,
    PrivateMode,
)
from urwid.widget import Sizing, Widget

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
    from typing import Literal

EOF = b""
ESC = chr(27)
ESC_B = b"\x1b"

#: :data:`urwid.ansi_parser.OSC_IGNORED_CONTROLS` as bytes
_OSC_IGNORED = frozenset(char.encode("ascii") for char in OSC_IGNORED_CONTROLS)

#: the control characters :meth:`TermCanvas.process_char` executes, also after an ESC inside an OSC string
_EXECUTED_CONTROLS = frozenset((b"\r", b"\x0f", b"\x0e", b"\n", b"\v", b"\f", b"\t", b"\b"))

#: the C0 control characters :meth:`TermCanvas.process_char` ignores: all but ESC, BEL, CAN, SUB and the executed ones
_IGNORED_CONTROLS = (
    frozenset(bytes((code,)) for code in range(0x20)) - {ESC_B, b"\a", b"\x18", b"\x1a"} - _EXECUTED_CONTROLS
)

KEY_TRANSLATIONS = {
    "enter": "\r",
    "backspace": chr(127),
    "tab": "\t",
    "esc": ESC,
    "up": f"{ESC}[A",
    "down": f"{ESC}[B",
    "right": f"{ESC}[C",
    "left": f"{ESC}[D",
    "home": f"{ESC}[1~",
    "insert": f"{ESC}[2~",
    "delete": f"{ESC}[3~",
    "end": f"{ESC}[4~",
    "page up": f"{ESC}[5~",
    "page down": f"{ESC}[6~",
    "begin paste": f"{ESC}[200~",
    "end paste": f"{ESC}[201~",
    "f1": f"{ESC}[[A",
    "f2": f"{ESC}[[B",
    "f3": f"{ESC}[[C",
    "f4": f"{ESC}[[D",
    "f5": f"{ESC}[[E",
    "f6": f"{ESC}[17~",
    "f7": f"{ESC}[18~",
    "f8": f"{ESC}[19~",
    "f9": f"{ESC}[20~",
    "f10": f"{ESC}[21~",
    "f11": f"{ESC}[23~",
    "f12": f"{ESC}[24~",
    "f13": f"{ESC}[25~",
    "f14": f"{ESC}[26~",
    "f15": f"{ESC}[28~",
    "f16": f"{ESC}[29~",
    "f17": f"{ESC}[31~",
    "f18": f"{ESC}[32~",
    "f19": f"{ESC}[33~",
    "f20": f"{ESC}[34~",
    "shift tab": f"{ESC}\t",  # kcbt of the linux terminal type the child is given
}

#: the legacy key that a key name only the keyboard protocols report (see ``extended_keys`` of the raw display)
#: collapses to in a legacy terminal, as the kitty keyboard protocol's legacy encoding sends it: Enter and Esc lose
#: shift and ctrl, Tab and Backspace lose shift, ctrl Backspace is ctrl H, and ctrl maps Space, "/", "?" and "~" to
#: NUL, US, DEL and RS. The digits are left out, because urwid names the keypad keys with them, and ctrl with the
#: keypad's middle key is "ctrl 5" too.
_LEGACY_KEYS: typing.Final = {
    "shift enter": "enter",
    "ctrl enter": "enter",
    "shift ctrl enter": "enter",
    "ctrl tab": "tab",
    "shift ctrl tab": "shift tab",
    "shift backspace": "backspace",
    "ctrl backspace": "ctrl h",
    "shift ctrl backspace": "ctrl h",
    "shift esc": "esc",
    "ctrl esc": "esc",
    "shift ctrl esc": "esc",
    "ctrl  ": "ctrl @",
    "ctrl /": "ctrl _",
    # without the shifted key in the report, as from a terminal that does not report alternate keys
    "shift ctrl /": "ctrl _",
    "ctrl ?": "backspace",
    "ctrl ~": "ctrl ^",
}

KEY_TRANSLATIONS_DECCKM = {
    "up": f"{ESC}OA",
    "down": f"{ESC}OB",
    "right": f"{ESC}OC",
    "left": f"{ESC}OD",
    "f1": f"{ESC}OP",
    "f2": f"{ESC}OQ",
    "f3": f"{ESC}OR",
    "f4": f"{ESC}OS",
    "f5": f"{ESC}[15~",
}

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
#: the tracking modes a Terminal recognises and sends no reports for
_MOUSE_UNREPORTED_TRACKING_MODES: typing.Final = frozenset((None, PrivateMode.MOUSE_HIGHLIGHT_TRACKING))
#: the buttons X10 compatibility mode reports, those of the mice it was made for
_MOUSE_X10_BUTTONS: typing.Final = frozenset((1, 2, 3))
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
#: the 0-based coordinate past what the X10 and the UTF-8 encoding can carry, which xterm sends as a NUL byte
_MOUSE_COORDINATE_LIMITS: typing.Final = {
    None: MOUSE_X10_PAST_END,
    PrivateMode.MOUSE_UTF8_MODE: 2047 - _MOUSE_BYTE_OFFSET,
}
#: the button bits of a mouse report for each urwid button number, the inverse of the decoding in urwid.display.escape
_MOUSE_BUTTON_CODES: typing.Final = {
    **{button: button - 1 for button in range(1, 4)},
    **{button: MouseBit.HIGH_BUTTON + button - 4 for button in range(4, 8)},
    **{button: MouseBit.EXTRA_BUTTON + button - 8 for button in range(8, 12)},
}
#: the wheel buttons, whose release xterm does not report
_MOUSE_WHEEL_BUTTONS: typing.Final = frozenset(range(4, 8))
#: the modifier prefixes of an urwid mouse event, in the order urwid writes them, and their bits in a mouse report
_MOUSE_MODIFIERS: typing.Final = (("shift ", MouseBit.SHIFT), ("meta ", MouseBit.META), ("ctrl ", MouseBit.CTRL))
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
#: the flags whose key reports differ from the legacy keys; event types and alternate keys alone change no key press
_KITTY_KEYBOARD_REPORTING_FLAGS: typing.Final = KittyKeyboardFlag.DISAMBIGUATE | KittyKeyboardFlag.ALL_KEYS
#: the entries a screen's keyboard flag stack keeps, as in kitty; a push onto a full stack drops the oldest entry
_KITTY_KEYBOARD_STACK_LIMIT: typing.Final = 8
#: the keypad keys' codes in a CSI u report, from 0 to the middle key; urwid names these keys as the main keys
_KITTY_KEYPAD_CODES: typing.Final = range(57399, 57428)
#: the CSI u codes of Caps Lock, Scroll Lock, Num Lock and the modifier keys, which are reported only with all keys as
#: escape codes
_KITTY_MODIFIER_KEY_CODES: typing.Final = frozenset((*range(57358, 57361), *range(57441, 57455)))
#: the key of each CSI 1 ; modifiers letter report, by urwid name; "5" is left out, since it is also the digit key
_KITTY_LETTER_KEYS: typing.Final = {name: chr(final) for final, name in _CSI_LETTER_KEYS.items() if name != "5"}
#: the key of each CSI number ~ report, by urwid name: the editing keys, F3 and F5 to F12; F13 and above are CSI u keys
_KITTY_TILDE_KEYS: typing.Final = {
    name: number for number, name in _CSI_TILDE_KEYS.items() if number <= 24 and name not in _KITTY_LETTER_KEYS
}
#: the code of each key a CSI u report names by a code that is not its text, by urwid name; Backspace is 127
_KITTY_CSI_U_KEYS: typing.Final = {
    name: code for code, name in _CSI_U_KEYS.items() if code != 8 and code not in _KITTY_KEYPAD_CODES
}
#: the keys the kitty keyboard protocol sends as legacy keys without modifiers, unless all keys are escape codes
_KITTY_LEGACY_KEYS: typing.Final = frozenset(("enter", "tab", "backspace"))
#: the keys that frame pasted text, which is sent as typed in a legacy terminal whatever the keyboard flags
_PASTE_KEYS: typing.Final = frozenset(("begin paste", "end paste"))


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
    b"J": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_display(mode[0])),
    b"K": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_line(mode[0])),
    b"L": CSICommand(1, 1, lambda s, number, q: s.insert_lines(lines=number[0])),
    b"M": CSICommand(1, 1, lambda s, number, q: s.remove_lines(lines=number[0])),
    b"P": CSICommand(1, 1, lambda s, number, q: s.remove_chars(chars=number[0])),
    b"X": CSICommand(
        1,
        1,
        lambda s, number, q: s.erase(s.term_cursor, (s.term_cursor[0] + number[0] - 1, s.term_cursor[1])),
    ),
    b"a": CSIAlias("alias", b"C"),
    b"c": CSICommand(0, 0, lambda s, none, q: s.csi_get_device_attributes(q)),
    b"d": CSICommand(1, 1, lambda s, row, q: s.move_cursor(0, row[0] - 1, relative_x=True)),
    b"e": CSIAlias("alias", b"B"),
    b"f": CSIAlias("alias", b"H"),
    b"g": CSICommand(1, 0, lambda s, mode, q: s.csi_clear_tabstop(mode[0])),
    b"h": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q)),
    b"l": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q, reset=True)),
    b"m": CSICommand(1, 0, lambda s, attrs, q: s.csi_set_attr(attrs)),
    b"n": CSICommand(1, 0, lambda s, mode, q: s.csi_status_report(mode[0])),
    b"q": CSICommand(1, 0, lambda s, mode, q: s.csi_set_keyboard_leds(mode[0])),
    b"r": CSICommand(2, 0, lambda s, t_b, q: s.csi_set_scroll(t_b[0], t_b[1])),
    b"s": CSICommand(0, 0, lambda s, none, q: s.save_cursor()),
    b"u": CSICommand(0, 0, lambda s, none, q: s.restore_cursor()),
    b"`": CSIAlias("alias", b"G"),
}

#: the final bytes whose "?" form is run: the DEC private modes, the linux cursor style CSI ? Ps c (not answered), and
#: the DEC forms of the erase and status commands, which act like their ECMA-48 forms here; any other "?" form, such as
#: the kitty keyboard protocol query CSI ? u, is a different command than the one without it
_CSI_PRIVATE_FINAL_BYTES: typing.Final = frozenset((b"J", b"K", b"c", b"h", b"l", b"n"))

CHARSET_DEFAULT: Literal[1] = 1  # type annotated exclusively for buggy IDE
CHARSET_UTF8: Literal[2] = 2

# Cell with no attributes, for the cells a resize adds and the padding of lines from the scrollback.
_BLANK_CELL: tuple[AttrSpec | None, Literal["0", "U"] | None, bytes] = (None, None, b" ")


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
        self.mouse_tracking = None
        self.mouse_encoding = None
        self.alternate_screen = False

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


class TermCharset:
    """Tracks the terminal's G0/G1 character set slots and which one is currently active."""

    __slots__ = ("_g", "_sgr_mapping", "active", "current")

    MAPPING: typing.ClassVar[dict[str, str | None]] = {
        "default": None,
        "vt100": "0",
        "ibmpc": "U",
        "user": None,
    }

    def __init__(self) -> None:
        """Initialize with the G0/G1 slots at their default charsets, G0 active."""
        self._g = [
            "default",
            "vt100",
        ]

        self._sgr_mapping = False

        # prepare defaults
        self.active = 0
        self.current: Literal["0", "U"] | None = None

        self.activate(0)

    def define(self, g: int, charset: str) -> None:
        """Redefine G'g' with new mapping."""
        self._g[g] = charset
        self.activate(g=self.active)

    def activate(self, g: int) -> None:
        """Activate the given charset slot."""
        self.active = g
        self.current = self.MAPPING.get(self._g[g], None)  # type: ignore[assignment]

    def set_sgr_ibmpc(self) -> None:
        """Set graphics rendition mapping to IBM PC CP437."""
        self._sgr_mapping = True

    def reset_sgr_ibmpc(self) -> None:
        """Reset graphics rendition mapping to IBM PC CP437."""
        self._sgr_mapping = False
        self.activate(g=self.active)

    def apply_mapping(self, char: bytes) -> bytes:
        """Map *char* through the active IBM PC/DEC special character set, tracking which slot the result came from."""
        if self._sgr_mapping or self._g[self.active] == "ibmpc":
            if (dec_pos := DEC_SPECIAL_CHARS.find(char.decode("cp437"))) >= 0:
                self.current = "0"
                return ALT_DEC_SPECIAL_CHARS[dec_pos].encode("cp437")

            self.current = "U"
            return char

        return char


class TermCanvas(Canvas):
    """Canvas holding a :class:`Terminal` widget's screen and scrollback content."""

    cacheable = False

    def __init__(self, width: int, height: int, widget: Terminal) -> None:
        """Initialize an empty `width` by `height` canvas backing `widget`."""
        super().__init__()

        self.width, self.height = width, height
        self.widget = widget
        self.modes: TermModes = widget.term_modes
        self.has_focus = False

        self.scrollback_buffer: deque[list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]] = deque(
            maxlen=10000
        )
        self.scrolling_up = 0

        self.utf8_eat_bytes: int | None = None
        self.utf8_buffer = bytearray()
        self._escbuf = bytearray()

        self.coords["cursor"] = (0, 0, None)

        self.term_cursor: tuple[int, int] = (0, 0)  # do not allow to shoot in the leg at `set_term_cursor`

        self.within_escape = False
        self.parsestate = 0

        self.attrspec: AttrSpec | None = None

        self.charset = TermCharset()

        self.saved_cursor: tuple[int, int] | None = None
        self.saved_attrs: tuple[AttrSpec | None, TermCharset] | None = None

        self.is_rotten_cursor = False

        self.scrollregion_start = 0
        self.scrollregion_end = self.height - 1

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

    def set_term_cursor(self, x: int | None = None, y: int | None = None) -> None:
        """Set terminal cursor to x/y and update canvas cursor.

        If one or both axes are omitted, use the values of the current position.
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
        )
        self.term = hidden.term
        self.scrollback_buffer = hidden.scrollback_buffer
        self.saved_cursor = hidden.saved_cursor
        self.saved_attrs = hidden.saved_attrs
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

    def empty_line(self, char: bytes = b" ") -> list[tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]]:
        """Return a full row of empty characters, one per column, filled with *char*."""
        return [self.empty_char(char)] * self.width

    def empty_char(self, char: bytes = b" ") -> tuple[AttrSpec | None, Literal["0", "U"] | None, bytes]:
        """Return one empty terminal cell holding *char*, with the canvas's current attributes and charset.

        The cell does not take the current hyperlink: as in a terminal, erased and scrolled-in cells are not linked.
        """
        attrspec = self.attrspec
        if attrspec is not None and attrspec.hyperlink is not None:
            attrspec = attrspec_with_hyperlink(attrspec, None, unset_color="default")
        return (attrspec, self.charset.current, char)

    def addstr(self, data: Iterable[int]) -> None:
        """Feed a sequence of input bytes through the terminal parser, one byte at a time."""
        if self.width <= 0 or self.height <= 0:
            # not displayable, do nothing!
            return

        for byte in data:
            self.addbyte(byte)

    def resize(self, width: int, height: int) -> None:
        """Resize both screens to the given width and height, keeping the cursor and saved cursors on their lines."""
        x, y = self.term_cursor

        shift = self._resize_lines(self.term, self.scrollback_buffer, width, height)
        y += shift
        if self.saved_cursor is not None:
            self.saved_cursor = (self.saved_cursor[0], self.saved_cursor[1] + shift)
        hidden = self._hidden_screen
        hidden_shift = self._resize_lines(hidden.term, hidden.scrollback_buffer, width, height)
        if hidden.saved_cursor is not None:
            hidden.saved_cursor = (hidden.saved_cursor[0], hidden.saved_cursor[1] + hidden_shift)

        self.width = width
        self.height = height

        self.reset_scroll()

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
    ) -> int:
        """Fit *lines*, a screen of the current size, to *width* and *height* in place.

        A screen that shrinks moves its top lines to the end of *scrollback*, and one that grows takes them back from
        there, or adds blank lines at the bottom once *scrollback* is empty.

        :returns: how many rows the lines that stay on the screen moved down, negative when they moved up.
        """
        for row in range(self.height):
            lines[row] = lines[row][:width] + [_BLANK_CELL] * (width - self.width)

        shift = 0
        for _y in range(self.height, height):
            if not scrollback:
                lines.append([_BLANK_CELL] * width)
                continue

            # adjust x axis of the scrollback line to the new width
            last_line = scrollback.pop()
            lines.insert(0, last_line[:width] + [_BLANK_CELL] * (width - len(last_line)))
            shift += 1
        for _y in range(height, self.height):
            scrollback.append(lines.pop(0))
            shift -= 1

        return shift

    def set_g01(self, char: bytes, mod: bytes) -> None:
        """Set G0 or G1 according to 'char' and modifier 'mod'."""
        if self.modes.main_charset != CHARSET_DEFAULT:
            return

        if mod == b"(":
            g = 0
        else:
            g = 1

        if char == b"0":
            cset = "vt100"
        elif char == b"U":
            cset = "ibmpc"
        elif char == b"K":
            cset = "user"
        else:
            cset = "default"

        self.charset.define(g, cset)

    def parse_csi(self, char: bytes) -> None:
        """Parse ECMA-48 CSI (Control Sequence Introducer) sequences."""
        if char == b"u" and (marker := bytes(self._escbuf[:1])) in _KITTY_KEYBOARD_MARKERS:
            params = self._escbuf[1:]
            if not params.strip(b"0123456789;"):
                self.csi_keyboard_flags(marker, [int(param) if param else None for param in params.split(b";")])
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
        elif mod in {b"(", b")"}:  # define G0/G1
            self.set_g01(char, mod)
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
        elif char == b"Z":  # DECID
            self.widget.respond(f"{ESC}[?6c")
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
            if valid:
                self.widget.set_title(title)
            return
        try:
            link = resolve_osc_hyperlink(body)
        except ValueError:
            link = None
        else:
            if link is None:
                return
        self.attrspec = attrspec_with_hyperlink(self.attrspec, link, unset_color="default")

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
            self.parsestate = 2
            return
        elif self.parsestate in {2, 4} and self._escbuf[-1:] == ESC_B and char != b"\\":
            # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the string
            # unapplied and starts a new escape sequence
            self.leave_escape()
            self.within_escape = True
            self.process_char(char)
            return
        elif self.parsestate == 4 and (char == b"\a" or (self._escbuf == ESC_B and char == b"\\")):
            # end of an over-long OSC string, discarded
            pass
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
        elif self.parsestate == 0 and char in {b"%", b"#", b"(", b")"}:
            # non-CSI sequence
            self._escbuf = bytearray(char)
            self.parsestate = 3
            return
        elif self.parsestate == 3:
            self.parse_noncsi(char, bytes(self._escbuf))
        elif char in {b"c", b"D", b"E", b"H", b"M", b"Z", b"7", b"8", b">", b"="}:
            self.parse_noncsi(char)

        self.leave_escape()

    def leave_escape(self) -> None:
        """Reset the escape-sequence parser state, discarding any sequence being read."""
        self.within_escape = False
        self.parsestate = 0
        self._escbuf = bytearray()

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
        if self.modes.main_charset == CHARSET_UTF8 or util.get_encoding() == "utf8":
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
                    else:
                        char, charsets = util.apply_target_encoding(sequence)
                        if charsets == [("0", 1)]:
                            # a DEC drawing character, or a fallback to one: one cell in the DEC character set
                            self.push_cursor(char, dec_special=True)
                            return

                else:
                    # invalid multibyte sequence, stop processing
                    return
            else:
                self.utf8_eat_bytes = None
                char = bytes([byte])
        else:
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

        if char == ESC_B and self.parsestate not in {2, 4}:  # escape
            # as in a terminal, an ESC drops a sequence still being read and starts a new one
            self.leave_escape()
            self.within_escape = True
        elif self.parsestate in {2, 4} and char in b"\x18\x1a":  # CAN/SUB abort an OSC string, also with display_ctrl
            self.leave_escape()
        elif (
            self.parsestate in {2, 4}
            and char in _OSC_IGNORED
            and (self._escbuf[-1:] != ESC_B or dc or char not in _EXECUTED_CONTROLS)
        ):
            # as in a terminal, such a control character inside an OSC string is neither executed nor part of its body;
            # after an ESC, one of _EXECUTED_CONTROLS is executed by the branches below, and the ESC stays pending
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
        elif not dc and char == b"\a" and self.parsestate not in {2, 4}:  # BEL
            # inside an OSC string (parsestate 2, or 4 once over-long) BEL is its terminator
            self.widget.beep()
        elif not dc and char in b"\x18\x1a":  # CAN/SUB
            self.leave_escape()
        elif not dc and (char in _IGNORED_CONTROLS or (char == b"\x7f" and self.parsestate not in {2, 4})):
            # as in a terminal, any other C0 control character and DEL are ignored, and an escape sequence continues
            pass
        elif not dc and char == b"\x9b" and self.parsestate not in {2, 4}:  # CSI (equivalent to "ESC [")
            # like ESC, it drops a sequence still being read; inside an OSC string it is part of the string
            self.leave_escape()
            self.within_escape = True
            self.parsestate = 1
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
        self.term[y][x] = (self.attrspec, "0" if dec_special else self.charset.current, char)

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
        """Move the cursor to column 0 of the current line."""
        self.set_term_cursor(0, self.term_cursor[1])

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

        self.set_term_cursor(x, y)

    def push_cursor(self, char: bytes | None = None, *, dec_special: bool = False) -> None:
        """Move cursor one character forward wrapping lines as needed.

        If 'char' is given, put the character into the former position.

        :param char: the character to put into the former position, if any.
        :param dec_special: *char* is already in the DEC special character set: store it there, unmapped.
        """
        x, y = self.term_cursor

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
            if x + 1 < self.width:
                x += 1

            self.is_rotten_cursor = False
            self.push_char(char, x, y, dec_special=dec_special)

    def save_cursor(self, with_attrs: bool = False) -> None:
        """Save the current cursor position, and its attributes/charset when *with_attrs* is set."""
        self.saved_cursor = self.term_cursor
        if with_attrs:
            self.saved_attrs = (copy.copy(self.attrspec), copy.copy(self.charset))

    def restore_cursor(self, with_attrs: bool = False) -> None:
        """Restore the cursor position saved by :meth:`save_cursor`, and its attributes/charset when *with_attrs*."""
        if self.saved_cursor is None:
            return

        x, y = self.saved_cursor
        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

        if with_attrs and self.saved_attrs is not None:
            self.attrspec, self.charset = (copy.copy(self.saved_attrs[0]), copy.copy(self.saved_attrs[1]))

    def tab(self, tabstop: int = 8) -> None:
        """Move cursor to the next 'tabstop', leaving the cells it passes unchanged."""
        x, y = self.term_cursor

        while x < self.width - 1:
            x += 1

            if self.is_tabstop(x):
                break

        self.is_rotten_cursor = False
        self.set_term_cursor(x, y)

    def scroll(self, reverse: bool = False) -> None:
        """Append a new line at the bottom and put the topmost line into the scrollback buffer.

        If reverse is True, do exactly the opposite, but don't save into scrollback buffer.
        """
        if reverse:
            self.term.pop(self.scrollregion_end)
            self.term.insert(self.scrollregion_start, self.empty_line())
        else:
            killed = self.term.pop(self.scrollregion_start)
            self.scrollback_buffer.append(killed)
            self.term.insert(self.scrollregion_end, self.empty_line())

    def decaln(self) -> None:
        """DEC screen alignment test: Fill screen with E's."""
        for row in range(self.height):
            self.term[row] = self.empty_line(b"E")

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
            char_spec = self.empty_char()
        else:
            charset: Literal["0", "U"] | None = "0" if dec_special else self.charset.current
            char_spec = (self.attrspec, charset, char)

        x, y = position
        line = self.term[y]
        line[x:x] = [char_spec] * min(chars, self.width - x)
        del line[self.width :]

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
    ) -> None:
        """Erase a region of the terminal.

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

    def csi_set_attr(self, attrs: Sequence[int]) -> None:
        """Set graphics rendition.

        The colour/attribute-flag computation itself is delegated to the shared, platform-independent
        :func:`urwid.ansi_parser.sgi_params_to_attrspec`; SGR 10/11/12 toggle vterm's own charset/display-control
        state rather than colour/attributes, so that side effect is applied separately, here, since
        ``sgi_params_to_attrspec`` deliberately ignores it (see its docstring).

        :param attrs: the SGR numeric parameters to apply, in encounter order.
        """
        for attr in attrs:
            if attr == 10:
                self.charset.reset_sgr_ibmpc()
                self.modes.display_ctrl = False
            elif attr in (11, 12):
                self.charset.set_sgr_ibmpc()
                self.modes.display_ctrl = True

        attrspec = sgi_params_to_attrspec(attrs, self.attrspec)

        if self.modes.reverse_video:
            self.attrspec = self.reverse_attrspec(attrspec)
        else:
            self.attrspec = attrspec

    def reverse_attrspec(self, attrspec: AttrSpec | None, undo: bool = False) -> AttrSpec:
        """Put standout mode to the 'attrspec' given and remove it if 'undo' is True."""
        if attrspec is None:
            attrspec = AttrSpec("default", "default")
        attrs = [fg.strip() for fg in attrspec.foreground.split(",")]
        if "standout" in attrs and undo:
            attrs.remove("standout")
            attrspec = attrspec.copy_modified(fg=",".join(attrs))
        elif "standout" not in attrs and not undo:
            attrs.append("standout")
            attrspec = attrspec.copy_modified(fg=",".join(attrs))
        return attrspec

    def reverse_video(self, undo: bool = False) -> None:
        """Reverse video/scanmode (DECSCNM) on both screens by swapping fg and bg colors."""
        for lines in (self.term, self._hidden_screen.term):
            for line in lines:
                for x, char in enumerate(line):
                    line[x] = (self.reverse_attrspec(char[0], undo=undo), *char[1:])

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
                if self.modes.reverse_video != flag:
                    self.reverse_video(undo=not flag)
                self.modes.reverse_video = flag
            elif private_mode == PrivateMode.ORIGIN_MODE:
                self.modes.constrain_scrolling = flag
                self.set_term_cursor(0, 0)
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
            elif private_mode == PrivateMode.BRACKETED_PASTE:
                self.modes.bracketed_paste = flag
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

    def csi_clear_tabstop(self, mode: int = 0) -> None:
        """Clear tabstop at current position or if 'mode' is 3, delete all tabstops."""
        if mode == 0:
            self.set_tabstop(remove=True)
        elif mode == 3:
            self.set_tabstop(clear=True)

    def csi_get_device_attributes(self, qmark: bool) -> None:
        """Report device attributes (what are you?). In our case, we'll report ourself as a VT102 terminal."""
        if not qmark:
            self.widget.respond(f"{ESC}[?6c")

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

    def csi_status_report(self, mode: int) -> None:
        """Report various information about the terminal status.

        Information is queried by 'mode', where possible values are:
            5 -> device status report
            6 -> cursor position report
        """
        if mode == 5:
            # terminal OK
            self.widget.respond(f"{ESC}[0n")
        elif mode == 6:
            x, y = self.term_cursor
            self.widget.respond(ESC + f"[{y + 1:d};{x + 1:d}R")

    def csi_erase_line(self, mode: int) -> None:
        """Erase current line.

        Modes are:

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

    def csi_erase_display(self, mode: int) -> None:
        """Erase display.

        Modes are:

            0 -> erase from cursor to end of display.
            1 -> erase from start to cursor.
            2 -> erase the whole display.
        """
        if mode == 0:
            self.erase(self.term_cursor, (self.width - 1, self.height - 1))
        elif mode == 1:
            self.erase((0, 0), self.term_cursor)
        elif mode == 2:
            self.clear(cursor=self.term_cursor)

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
        """Clear the whole terminal screen and reset the cursor position to (0, 0) or to 'cursor'."""
        self.term = [self.empty_line() for _ in range(self.height)]

        if cursor is None:
            self.set_term_cursor(0, 0)
        else:
            self.set_term_cursor(*cursor)

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

        All parameters are ignored.
        """
        if self.scrolling_up == 0:
            yield from self.term
        else:
            viewport_range = slice(-(self.height + self.scrolling_up), -self.scrolling_up)
            for line in (*self.scrollback_buffer, *self.term)[viewport_range]:
                yield line[: self.width] + [_BLANK_CELL] * (self.width - len(line))


def _mouse_report(code: int, col: int, row: int, release: bool, encoding: PrivateMode | None) -> bytes:
    """Return the bytes xterm sends for a mouse event with button byte *code* at 0-based *col* and *row*.

    :param release: the event is a release, which only the SGR encoding marks apart from the button byte.
    :param encoding: the mode of the encoding, or None for the X10 encoding.
    """
    if encoding == PrivateMode.MOUSE_SGR_MODE:
        return f"{ESC}[<{code};{col + 1};{row + 1}{'m' if release else 'M'}".encode("ascii")

    limit = _MOUSE_COORDINATE_LIMITS[encoding]
    # a coordinate past the limit is sent as the limit, and the limit as a NUL byte
    coordinates = (min(value, limit) for value in (col, row))
    values = [
        code + _MOUSE_BYTE_OFFSET,
        *(0 if value == limit else value + _MOUSE_COORD_OFFSET for value in coordinates),
    ]
    if encoding == PrivateMode.MOUSE_UTF8_MODE:
        # UTF-8 encoding: each value is a character, so one above 127 takes two bytes
        return f"{ESC}[M".encode("ascii") + "".join(map(chr, values)).encode("utf-8")
    return f"{ESC}[M".encode("ascii") + bytes(values)


class Terminal(Widget):
    """Widget that runs a child process (or callable) and renders its terminal output."""

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    signals: typing.ClassVar[list[str]] = ["closed", "beep", "leds", "title", "resize"]

    # Upper bound on the bytes drained in one feed() call while term_modes.synchronized_output is set,
    # so a child that opens a synchronized-output block (CSI ?2026h) and never closes it --
    # deliberately or by being slow -- cannot stall feed() from ever returning.
    _SYNCHRONIZED_OUTPUT_DRAIN_LIMIT: typing.ClassVar[int] = 1 << 16

    def __init__(
        self,
        command: tuple[str | bytes | os.PathLike[str] | os.PathLike[bytes], ...]
        | list[str | bytes | os.PathLike[str] | os.PathLike[bytes]]
        | Callable[[], typing.Any]
        | None,
        env: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
        main_loop: event_loop.EventLoop | None = None,
        escape_sequence: str | None = None,
        encoding: str = "utf-8",
    ) -> None:
        """Initialize a terminal emulator widget.

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

        self.escape_sequence: str = escape_sequence or "ctrl a"

        self.env = dict(env or os.environ)

        self.command = command or [self.env.get("SHELL", "/bin/sh")]

        self.encoding = encoding

        self.keygrab = False
        self.last_key: str | None = None
        # the keys between "begin paste" and "end paste" are being handled
        self._pasting = False
        # the button of the last press reported to the child, for a release or a drag that does not name its button
        self._pressed_button = 0

        self.response_buffer: list[str] = []

        self.term_modes = TermModes()

        if main_loop is not None:
            self.main_loop = main_loop
        else:
            self.main_loop = event_loop.SelectEventLoop()

        self.master: int | None = None
        self.pid: int | None = None

        self.width: int | None = None
        self.height: int | None = None
        self.term: TermCanvas | None = None
        self.has_focus = False
        self.old_tios: tuple[bytes, bytes, bytes, bytes, bytes] | None = None
        self.terminated = False

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates for this terminal."""
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
        """Fork the child process running :attr:`command` and connect it to a new pty."""
        env = self.env
        env["TERM"] = "linux"

        self.pid, self.master = pty.fork()

        if self.pid == 0:
            if callable(self.command):
                try:
                    # noinspection PyBroadException
                    try:
                        self.command()
                    except BaseException:  # noqa: BLE001  # special case
                        sys.stderr.write(traceback.format_exc())
                    for stream in (sys.stderr, sys.stdout):
                        with suppress(OSError, ValueError):
                            stream.flush()
                finally:
                    os._exit(0)
            try:
                os.execvpe(self.command[0], self.command, env)  # noqa: S606
            except (OSError, TypeError, ValueError) as exc:
                reason = getattr(exc, "strerror", None) or exc
                with suppress(OSError):
                    os.write(2, f"{os.fsdecode(self.command[0])}: {reason}\r\n".encode(errors="replace"))
            finally:
                # 127 is the shell's "command not found" status
                os._exit(127)

        if self.main_loop is None:
            fcntl.fcntl(self.master, fcntl.F_SETFL, os.O_NONBLOCK)

        atexit.register(self.terminate)

    def terminate(self) -> None:
        """Stop watching the pty, end the child process and close the pty master.

        Signals escalate from SIGHUP to SIGKILL until the child exits.
        A child that may not be signalled, such as a setuid program, only gets the hangup from closing the master.
        It is then waited for at most one second, and left unreaped if it keeps running.
        """
        if self.terminated:
            return

        self.terminated = True
        atexit.unregister(self.terminate)

        if self.pid is not None and self.pid > 0:
            self.remove_watch()
            self.set_termsize(0, 0)
            reaped = killed = False
            try:
                for sig in (signal.SIGHUP, signal.SIGCONT, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.kill(self.pid, sig)
                    except ProcessLookupError:
                        # reaped by someone else: a further signal could hit a process that reuses the pid
                        reaped = True
                        break
                    except PermissionError:
                        # e.g. a setuid child: only the hangup from closing the master below reaches it
                        break
                    killed = sig == signal.SIGKILL
                    if reaped := self._reap_child(0.1):
                        break
            finally:
                os.close(typing.cast("int", self.master))
            if killed and not reaped:
                with suppress(ChildProcessError):
                    os.waitpid(self.pid, 0)
            elif not reaped:
                self._reap_child(1.0)

        # last, so a tty that is already gone cannot stop the cleanup above
        if self.has_focus and self.old_tios:
            RealTerminal().tty_signal_keys(*self.old_tios)

    def _reap_child(self, timeout: float) -> bool:
        """Poll for the child's exit for up to *timeout* seconds, and return whether it is reaped."""
        deadline = time.monotonic() + timeout
        with suppress(ChildProcessError):  # reaped by someone else
            while os.waitpid(typing.cast("int", self.pid), os.WNOHANG)[0] == 0:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.01)
        return True

    def beep(self) -> None:
        """Emit a "beep" signal for anything listening on this widget."""
        self._emit("beep")

    def leds(self, which: Literal["clear", "scroll_lock", "num_lock", "caps_lock"]) -> None:
        """Emit a "leds" signal asking the display to set keyboard LED state *which*."""
        self._emit("leds", which)

    def respond(self, string: str) -> None:
        """Respond to the underlying application with 'string'."""
        self.response_buffer.append(string)

    def flush_responses(self) -> None:
        """Write every buffered response to the pty and clear the buffer."""
        for string in self.response_buffer:
            os.write(typing.cast("int", self.master), string.encode("ascii"))
        self.response_buffer = []

    def set_termsize(self, width: int, height: int) -> None:
        """Tell the pty the terminal window is now *width* by *height* characters."""
        winsize = struct.pack("HHHH", height, width, 0, 0)
        fcntl.ioctl(typing.cast("int", self.master), termios.TIOCSWINSZ, winsize)

    def touch_term(self, width: int, height: int) -> None:
        """Spawn the child process if needed, then resize the pty and terminal canvas to *width* by *height*."""
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

        self._emit("resize", (width, height))

    def set_title(self, title: str) -> None:
        """Emit a "title" signal with the terminal's new *title*."""
        self._emit("title", title)

    def change_focus(self, has_focus: bool) -> None:
        """Ignore SIGINT if this widget has focus."""
        if self.terminated:
            return

        focus_changed = has_focus != self.has_focus
        self.has_focus = has_focus

        if self.term is not None:
            self.term.has_focus = has_focus
            self.term.set_term_cursor()

        if not focus_changed:
            return

        if has_focus:
            self.old_tios = RealTerminal().tty_signal_keys()
            RealTerminal().tty_signal_keys(*(["undefined"] * 5))  # type: ignore[arg-type]
        elif self.old_tios:
            RealTerminal().tty_signal_keys(*self.old_tios)

    def render(self, size: tuple[int, int], focus: bool = False) -> TermCanvas:  # type: ignore[override]
        """Resize the terminal to *size*, read any pending child output, and return the terminal canvas."""
        if not self.terminated:
            self.change_focus(focus)

            width, height = size
            self.touch_term(width, height)

            if self.main_loop is None:
                self.feed()

        return self.term  # type: ignore[return-value]

    def add_watch(self) -> None:
        """Register the pty with the main loop, when there is one, so :meth:`feed` runs on new child output."""
        if self.main_loop is None:
            return
        self.main_loop.watch_file(typing.cast("int", self.master), self.feed)

    def remove_watch(self) -> None:
        """Unregister the pty from the main loop, when there is one."""
        if self.main_loop is None:
            return
        self.main_loop.remove_watch_file(typing.cast("int", self.master))

    def wait_and_feed(self, timeout: float = 1.0) -> None:
        """Block up to *timeout* seconds for pty output, then read and process whatever has arrived."""
        with selectors.DefaultSelector() as selector:
            selector.register(typing.cast("int", self.master), selectors.EVENT_READ)

            if not selector.select(timeout):
                return

        self.feed()

    def feed(self) -> None:
        """Read pending output from the pty and feed it to the terminal, terminating the child on EOF."""
        data = EOF

        try:
            data = os.read(typing.cast("int", self.master), 4096)
        except OSError as e:
            if e.errno == errno.EIO:  # EIO, child terminated
                data = EOF
            elif e.errno == errno.EWOULDBLOCK:  # empty buffer
                return
            else:
                raise

        if data == EOF:
            self.terminate()
            self._emit("closed")
            return

        self.term.addstr(data)  # type: ignore[union-attr]

        # The child just opened a synchronized-output block (CSI ?2026h) and is still writing to it:
        # draining whatever it has already queued on the pty before returning keeps the next
        # render() from ever handing out a half-painted mid-block canvas.
        # A child that never closes the block (CSI ?2026l) still gets control back
        # once _SYNCHRONIZED_OUTPUT_DRAIN_LIMIT is hit
        # or the pty simply has nothing more buffered right now.
        if self.term_modes.synchronized_output:
            # The master fd is blocking whenever there is a main loop, so read only what select() reports as ready.
            with selectors.DefaultSelector() as selector:
                selector.register(typing.cast("int", self.master), selectors.EVENT_READ)
                drained = 0
                while (
                    self.term_modes.synchronized_output
                    and drained < self._SYNCHRONIZED_OUTPUT_DRAIN_LIMIT
                    and selector.select(0)
                ):
                    try:
                        more = os.read(typing.cast("int", self.master), 4096)
                    except OSError as e:
                        if e.errno == errno.EWOULDBLOCK:
                            break
                        if e.errno != errno.EIO:
                            raise
                        more = EOF

                    if more == EOF:
                        self.terminate()
                        self._emit("closed")
                        return

                    self.term.addstr(more)  # type: ignore[union-attr]
                    drained += len(more)

        self.flush_responses()

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Translate *key* into the byte sequence the child process expects and write it to the pty.

        :returns: ``None`` when the widget used *key*, or *key* when it did not: the child has exited, the key is
            handed down to the parent outside a key grab, or the ``linux`` terminal type the child is given has no
            byte form for it, as for a cursor or function key with shift, meta or ctrl.
        """
        if self.terminated:
            return key

        grabbed = self.keygrab

        if key in _PASTE_KEYS:
            self._pasting = key == "begin paste"
            if self.term_modes.bracketed_paste:
                pass  # passthrough bracketed paste sequences
            else:  # swallow bracketed paste sequences
                self.last_key = key
                return None

        if key == "window resize":
            width, height = size
            self.touch_term(width, height)
            return None

        if self.last_key == key == self.escape_sequence:
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
            if key == "page up":
                if self.term is not None:  # there is no scrollback before the first render
                    self.term.scroll_buffer()
                self.last_key = key
                self._invalidate()
                return None

            if key == "page down":
                if self.term is not None:  # there is no scrollback before the first render
                    self.term.scroll_buffer(up=False)
                self.last_key = key
                self._invalidate()
                return None

            if self.last_key == self.escape_sequence and key != self.escape_sequence:
                # hand down keypress directly after ungrab.
                self.last_key = key
                return key

            if self.escape_sequence == key:
                # start grabbing the terminal
                self.keygrab = True
                self.last_key = key
                return None

            if self._command_map[key] is None or key == "enter":
                # printable character or escape sequence means:
                # lock in terminal...
                self.keygrab = True
                # ... and do key processing
            else:
                # hand down keypress
                self.last_key = key
                return key

        self.last_key = key

        sent = self._key_sequence(key)
        if sent is None:
            # the key is returned to the parent, so a key grab it started is not kept
            self.keygrab = grabbed
            return key

        if self.term is None:
            # Only touch_term() starts the child and creates the canvas, and render() normally calls it first.
            width, height = size
            self.touch_term(width, height)

        self.term.scroll_buffer(reset=True)  # type: ignore[union-attr]

        os.write(typing.cast("int", self.master), sent.encode(self.encoding, "ignore"))

        return None

    def mouse_event(  # pyrefly: ignore[bad-override]  # a box widget, sized by two dimensions
        self,
        size: tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Report a mouse event to the child in the tracking mode and the encoding the child turned on.

        The report bytes are the ones xterm sends for the same event.

        :returns: ``True`` when the child tracks the mouse, also for an event its tracking mode does not report.
            Such events are a drag under mode 1000, the release of a wheel button, and under X10 compatibility mode (9)
            anything but a press of buttons 1 to 3.
            ``False`` when the event is left to the parent, in these cases:

            - the child has exited;
            - the child does not track the mouse, or tracks it in highlight mode (1001), which is not implemented;
            - the view is scrolled back from the screen the child sees;
            - the event is not a press, a release or a drag.
        """
        modes = self.term_modes
        if (
            self.terminated
            or modes.mouse_tracking in _MOUSE_UNREPORTED_TRACKING_MODES
            or self.term is None
            or self.term.scrolling_up
        ):
            return False

        code = 0
        action = event
        for prefix, flag in _MOUSE_MODIFIERS:
            if action.startswith(prefix):
                code |= flag
                action = action.removeprefix(prefix)

        release = action == "mouse release"
        x10 = modes.mouse_tracking == PrivateMode.MOUSE_X10
        if action == "mouse press":
            if x10:
                # X10 compatibility reports no modifiers
                if button not in _MOUSE_X10_BUTTONS:
                    return True
                code = 0
            elif button not in _MOUSE_WHEEL_BUTTONS:
                self._pressed_button = button
        elif action == "mouse drag":
            if x10 or modes.mouse_tracking == PrivateMode.MOUSE_REPORTING:
                return True
            button = button or self._pressed_button
            code |= MouseBit.DRAG
        elif release:
            # an X10 report from the parent's terminal does not say which button was released
            button = button or self._pressed_button
            self._pressed_button = 0
            if x10 or button in _MOUSE_WHEEL_BUTTONS:
                return True
        else:
            return False

        if release and modes.mouse_encoding != PrivateMode.MOUSE_SGR_MODE:
            # without SGR, a release names no button, so it is sent also when its button is unknown
            code |= MouseBit.BUTTON
        elif button in _MOUSE_BUTTON_CODES:
            code |= _MOUSE_BUTTON_CODES[button]
        else:
            return True

        os.write(typing.cast("int", self.master), _mouse_report(code, col, row, release, modes.mouse_encoding))
        return True

    def _key_sequence(self, key: str) -> str | None:
        """Return the characters the child receives for *key*, or ``None`` when its terminal type has none.

        While the flags the child set with the kitty keyboard protocol change key reports, the keys are sent in that
        protocol, except for pasted text, which is sent as a legacy terminal sends it.
        """
        flags = self.term_modes.keyboard_flags[-1] if self.term_modes.keyboard_flags else 0
        if flags & _KITTY_KEYBOARD_REPORTING_FLAGS and not self._pasting and key not in _PASTE_KEYS:
            sent = _kitty_key_report(key, flags)
        else:
            sent = self._legacy_key_sequence(key)

        # ENTER transmits both a carriage return and linefeed in LF/NL mode.
        if self.term_modes.lfnl and sent is not None and sent.endswith("\r"):
            sent += "\n"

        return sent

    def _legacy_key_sequence(self, key: str) -> str | None:
        """Return the characters a ``linux`` terminal sends for *key*, or ``None`` when it has none."""
        meta = key.startswith("meta ")
        sent = key.removeprefix("meta ")
        sent = _LEGACY_KEYS.get(sent, sent)

        if sent.startswith("ctrl "):
            # C0 control characters only exist for "@", "A"-"Z" and "[\]^_"
            char = sent.removeprefix("ctrl ")
            # upper() of a non-ASCII letter can be an ASCII one: U+017F LATIN SMALL LETTER LONG S gives "S"
            char = char.upper() if char.isascii() else char
            if len(char) != 1 or not "@" <= char <= "_":
                return None
            sent = chr(ord(char) - ord("@"))
        elif self.term_modes.keys_decckm and sent in KEY_TRANSLATIONS_DECCKM:
            sent = KEY_TRANSLATIONS_DECCKM[sent]
        elif sent in KEY_TRANSLATIONS:
            sent = KEY_TRANSLATIONS[sent]
        elif len(sent) > 1 and (sent.isascii() or " " in sent):
            # a key name such as "shift up", "focus in" or "super \u0436" has no form under TERM=linux, and is not
            # written as text
            return None

        # Meta (Alt) sends ESC before the key's single character, as xterm does with metaSendsEscape.
        # A key that is sent as an escape sequence has no such form.
        if meta and len(sent) != 1:
            return None

        if meta:
            sent = ESC + sent

        return sent


def _kitty_key_report(key: str, flags: int) -> str | None:
    """Return what a terminal sends for *key* in the kitty keyboard protocol, or ``None`` when it sends nothing.

    - Unless all keys are escape codes, a text key whose name has no modifiers is sent as its text.
    - Unless all keys are escape codes, Enter, Tab and Backspace without modifiers are sent as the legacy keys.
    - An upper case letter is reported as the lower case key with shift. With alternate keys, the report adds the
      upper case letter as the shifted key.
    - Another shifted symbol is reported as the symbol, since the key that types it depends on the keyboard layout.
    - The keypad keys are sent as the main keys, since urwid names them alike.

    :param key: the urwid key name.
    :param flags: the keyboard flags in effect, with disambiguate or all keys set.
    """
    name = key
    modifiers = 0
    for prefix, bits in _KEY_MODIFIER_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name.removeprefix(prefix)
            # urwid's "meta" is the modifier a terminal sends Alt as
            modifiers |= bits & ~KeyModifier.META
    all_keys = flags & KittyKeyboardFlag.ALL_KEYS

    if name in _KITTY_LETTER_KEYS:
        final = _KITTY_LETTER_KEYS[name]
        return f"{ESC}[1;{modifiers + 1:d}{final}" if modifiers else f"{ESC}[{final}"
    if name in _KITTY_TILDE_KEYS:
        number = _KITTY_TILDE_KEYS[name]
        return f"{ESC}[{number:d};{modifiers + 1:d}~" if modifiers else f"{ESC}[{number:d}~"

    text = ""
    if name in _KITTY_CSI_U_KEYS:
        code = _KITTY_CSI_U_KEYS[name]
        if not (modifiers or all_keys) and name in _KITTY_LEGACY_KEYS:
            return KEY_TRANSLATIONS[name]
        if code in _KITTY_MODIFIER_KEY_CODES and not all_keys:
            return None
        key_field = f"{code:d}"
    elif len(name) == 1 and name.isprintable():
        if not (modifiers or all_keys):
            return name
        if not modifiers:
            # the text the key types, which a name with a modifier does not give
            text = name
        if len(lower := name.lower()) == 1 and lower != name and lower.upper() == name:
            # an upper case letter, typed with shift
            modifiers |= KeyModifier.SHIFT
            key_field = f"{ord(lower):d}"
            if flags & KittyKeyboardFlag.ALTERNATE_KEYS:
                key_field += f":{ord(name):d}"
        else:
            key_field = f"{ord(name):d}"
    else:
        return None

    modifiers_field = f"{modifiers + 1:d}" if modifiers else ""
    if text and flags & KittyKeyboardFlag.ASSOCIATED_TEXT:
        return f"{ESC}[{key_field};{modifiers_field};{ord(text):d}u"
    if modifiers:
        return f"{ESC}[{key_field};{modifiers_field}u"
    return f"{ESC}[{key_field}u"
