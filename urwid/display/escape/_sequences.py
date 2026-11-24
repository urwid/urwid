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


"""Output escape sequences, the DEC special graphics character set and terminal private modes."""

from __future__ import annotations

import enum
import functools
import re
import typing

from urwid import str_util
from urwid.display.escape._keys import KittyKeyboardFlag

if typing.TYPE_CHECKING:
    from urwid.display.common import Hyperlink


within_double_byte = str_util.within_double_byte

#: the code points of the C0 control characters, and of the C1 ones
_C0_CONTROLS: typing.Final = range(0x20)
_C1_CONTROLS: typing.Final = range(0x80, 0xA0)

SO: typing.Final = "\x0e"
SI: typing.Final = "\x0f"
# Encoded once here, because `urwid.util.apply_target_encoding` splits on them for every rendered text segment.
_SO_BYTES: typing.Final = SO.encode("ascii")
_SI_BYTES: typing.Final = SI.encode("ascii")
_SI_SO: typing.Final = SI + SO

DEC_TAG: typing.Final = "0"
DEC_SPECIAL_CHARS: typing.Final = "▮◆▒␉␌␍␊°±␤␋┘┐┌└┼⎺⎻─⎼⎽├┤┴┬│≤≥π≠£·"
ALT_DEC_SPECIAL_CHARS: typing.Final = "_`abcdefghijklmnopqrstuvwxyz{|}~"

DEC_SPECIAL_CHARMAP: typing.Final[dict[int, str]] = {}


for c, alt in zip(DEC_SPECIAL_CHARS, ALT_DEC_SPECIAL_CHARS, strict=True):
    DEC_SPECIAL_CHARMAP[ord(c)] = SO + alt + SI


SAFE_ASCII_DEC_SPECIAL_RE: typing.Final = re.compile(f"^[ -~{DEC_SPECIAL_CHARS}]*$")
DEC_SPECIAL_RE: typing.Final = re.compile(f"[{DEC_SPECIAL_CHARS}]")


ESC: typing.Final = "\x1b"
# control sequence introducer
CSI: typing.Final = f"{ESC}["
# operating system command, and the string terminator ending it
OSC: typing.Final = f"{ESC}]"
ST: typing.Final = f"{ESC}\\"
# device control string, ended by ST
DCS: typing.Final = f"{ESC}P"
# OSC 8 with an empty URI ends the hyperlink the text is drawn with
HYPERLINK_CLOSE: typing.Final = f"{OSC}8;;{ST}"
# Linux console palette, console_codes(4): LINUX_SET_PALETTE then "nrrggbb" in hex, with no terminator,
# sets entry n (0-15); LINUX_RESET_PALETTE resets all 16 entries to the console default.
LINUX_SET_PALETTE: typing.Final = f"{OSC}P"
LINUX_RESET_PALETTE: typing.Final = f"{OSC}R"
# OSC 2 then the title then BEL sets the window title: every terminal with a title accepts BEL, not all accept ST.
SET_TITLE: typing.Final = f"{OSC}2;"
BEL: typing.Final = "\x07"
# XTWINOPS 22 and 23: push the icon and window title on the terminal's title stack, and pop them back
TITLE_PUSH: typing.Final = f"{CSI}22;0t"
TITLE_POP: typing.Final = f"{CSI}23;0t"
# OSC 52 then the base64 text then BEL puts the text on the system clipboard ("c")
SET_CLIPBOARD: typing.Final = f"{OSC}52;c;"


class PrivateMode(enum.StrEnum):
    """DEC private modes (``CSI ? Pd h``/``l``).

    Not every member is queried or acted on, some members are for future development.
    `_raw_display_base.TermModes` carries a field for each mode the raw display queries.
    `canvas.term.TermModes` carries the modes a `Terminal` acts on, with one field for each group of modes that replace
    each other, such as the mouse tracking modes.
    """

    # Cursor and screen
    APPLICATION_CURSOR_KEYS = "1"  # DECCKM
    COLUMNS_132 = "3"  # DECCOLM
    REVERSE_VIDEO = "5"  # DECSCNM
    ORIGIN_MODE = "6"  # DECOM
    AUTO_WRAP = "7"  # DECAWM
    # Neither display controls cursor blinking; the mode is recognised and never turned on.
    CURSOR_BLINK = "12"
    CURSOR_VISIBLE = "25"  # DECTCEM
    # The left and right margins DECSLRM sets apply while it is set; a Terminal sets it only at the VT400 level.
    LEFT_RIGHT_MARGIN = "69"  # DECLRMM

    # Keyboard
    NUMERIC_KEYPAD = "66"  # DECNKM: the keypad in application mode when set
    BACKARROW_KEY = "67"  # DECBKM: the backarrow key sends BS when set, DEL when reset
    # A Terminal always sends Meta and Alt as ESC and the key, so it recognises these and does not track them.
    META_SENDS_ESCAPE = "1036"
    ALT_SENDS_ESCAPE = "1039"

    # Alternate screen
    # The alternate screen (47, 1047, 1049) and the cursor saved as DECSC saves it (1048); a Terminal implements them
    # as `canvas.term.TermCanvas.set_alternate_screen` describes.
    ALTERNATE_SCREEN = "47"
    # On the alternate screen and without mouse tracking, the terminal sends the wheel as cursor up and down keys.
    ALTERNATE_SCROLL = "1007"
    ALTERNATE_SCREEN_CLEARED_ON_EXIT = "1047"
    SAVE_CURSOR = "1048"
    ALTERNATE_SCREEN_BUFFER = "1049"

    # Mouse tracking: the events reported
    # Reports presses only, without modifiers; a Terminal uses it only while no other tracking mode is on.
    MOUSE_X10 = "9"
    MOUSE_REPORTING = "1000"
    # The program answers a press with CSI T and the terminal highlights the drag; urwid implements none of it.
    MOUSE_HIGHLIGHT_TRACKING = "1001"
    MOUSE_BUTTON_TRACKING = "1002"
    MOUSE_ANY_EVENT_TRACKING = "1003"

    # Mouse tracking: the report encoding
    MOUSE_UTF8_MODE = "1005"
    MOUSE_SGR_MODE = "1006"
    # The urxvt encoding is recognised, but never turned on or used.
    # xterm's documentation advises against it, because a report looks like CSI Pn M, which is the delete-lines command.
    MOUSE_URXVT_MODE = "1015"

    # Reports and notifications the terminal sends in the input
    FOCUS_REPORTING = "1004"
    BRACKETED_PASTE = "2004"
    # Colour scheme change notifications; not queried or turned on yet.
    COLOR_SCHEME_REPORTING = "2031"
    # In-band resize notifications: the terminal reports each size change in the input, as CSI 48 ; rows ; cols t.
    IN_BAND_RESIZE = "2048"

    # Output
    SYNCHRONIZED_OUTPUT = "2026"
    GRAPHEME_CLUSTERING = "2027"

    @functools.cached_property
    def query(self) -> str:
        """Return the DECRQM query (CSI ? Pd $ p) asking the terminal to report *mode*'s state."""
        return f"{CSI}?{self}$p"

    @functools.cached_property
    def enable_seq(self) -> str:
        """Enable sequence."""
        return f"{CSI}?{self}h"

    @functools.cached_property
    def disable_seq(self) -> str:
        """Disable sequence."""
        return f"{CSI}?{self}l"


CURSOR_HOME: typing.Final = f"{CSI}H"
CURSOR_HOME_COL: typing.Final = "\r"

APP_KEYPAD_MODE: typing.Final = f"{ESC}="
NUM_KEYPAD_MODE: typing.Final = f"{ESC}>"

# RESET_SCROLL_REGION = ESC+"[;r"
# RESET = ESC+"c"

REPORT_STATUS: typing.Final = f"{CSI}5n"
REPORT_CURSOR_POSITION: typing.Final = f"{CSI}6n"
# Primary DA; every terminal answers it, so its reply arriving first means an earlier query got no answer
REPORT_DEVICE_ATTRIBUTES: typing.Final = f"{CSI}c"
# XTVERSION, replied as DCS > | name and version ST
REPORT_TERMINAL_VERSION: typing.Final = f"{CSI}>0q"
# DECRQSS for the graphic rendition, replied as DCS 1 $ r SGR parameters m ST, or DCS 0 $ r ST
REQUEST_RENDITION: typing.Final = f"{DCS}$qm{ST}"
# the default foreground and background colors (OSC 10 and OSC 11 queries), replied as OSC 10 ; color ST and OSC 11 ;
# color ST, or ended by BEL
REPORT_DEFAULT_COLORS: typing.Final = f"{OSC}10;?{ST}{OSC}11;?{ST}"


def request_capability(name: str) -> str:
    r"""Return the XTGETTCAP query for the terminfo capability *name*, replied as DCS 1 + r or DCS 0 + r.

    >>> request_capability("RGB")
    '\x1bP+q524742\x1b\\'

    :raises UnicodeEncodeError: *name* is not ASCII, as no terminfo capability name is.
    """
    return f"{DCS}+q{name.encode('ascii').hex().upper()}{ST}"


# kitty keyboard protocol: the flags query (replied as CSI ? flags u), and pushing and popping the flags on the
# terminal's per-screen stack
KITTY_KEYBOARD_QUERY: typing.Final = f"{CSI}?u"
# report alternate keys, so a shifted symbol is named by what it types
KITTY_KEYBOARD_FLAGS: typing.Final = KittyKeyboardFlag.DISAMBIGUATE | KittyKeyboardFlag.ALTERNATE_KEYS
KITTY_KEYBOARD_PUSH: typing.Final = f"{CSI}>{KITTY_KEYBOARD_FLAGS}u"
KITTY_KEYBOARD_POP: typing.Final = f"{CSI}<u"

# xterm's modifyOtherKeys key modifier resource, and its query (XTQMODKEYS)
MODIFY_OTHER_KEYS_RESOURCE: typing.Final = 4
MODIFY_OTHER_KEYS_QUERY: typing.Final = f"{CSI}?{MODIFY_OTHER_KEYS_RESOURCE}m"


def set_modify_other_keys(value: int | None) -> str:
    r"""Return the XTMODKEYS sequence that sets modifyOtherKeys to *value*, or resets it to its initial value for None.

    >>> set_modify_other_keys(None)
    '\x1b[>4m'
    """
    if value is None:
        return f"{CSI}>{MODIFY_OTHER_KEYS_RESOURCE}m"
    return f"{CSI}>{MODIFY_OTHER_KEYS_RESOURCE};{value:d}m"


# level 2 reports every key pressed with a modifier, Ctrl+C included
MODIFY_OTHER_KEYS_ON: typing.Final = set_modify_other_keys(2)


def window_size_report(cols: int, rows: int) -> str:
    r"""Return the in-band resize notification (mode 2048) a terminal sends for a text area of *cols* by *rows*.

    The size in pixels is sent as 0, which stands for unknown.

    >>> window_size_report(80, 24)
    '\x1b[48;24;80;0;0t'
    """
    return f"{CSI}48;{rows:d};{cols:d};0;0t"


class ModeReportState(enum.IntEnum):
    """State of a mode in a DECRPM reply (CSI ? Pd ; Ps $ y, or CSI Pd ; Ps $ y for an ANSI mode), its Ps."""

    NOT_RECOGNIZED = 0
    SET = 1
    RESET = 2
    PERMANENTLY_SET = 3
    PERMANENTLY_RESET = 4


# DECRQM (CSI ? Pd $ p) reply is DECRPM (CSI ? Pd ; Ps $ y), recognized by KeyqueueTrie.read_private_mode_report().
DECRQM_RECOGNIZED_VALUES: typing.Final = frozenset(ModeReportState) - {ModeReportState.NOT_RECOGNIZED}
# Ps of a mode the terminal can turn on; a permanently reset one cannot be.
DECRQM_SETTABLE_VALUES: typing.Final = DECRQM_RECOGNIZED_VALUES - {ModeReportState.PERMANENTLY_RESET}

INSERT_ON: typing.Final = f"{CSI}4h"
INSERT_OFF: typing.Final = f"{CSI}4l"

# select the IBM PC character set for a charset "U" run, and back
IBMPC_ON: typing.Final = f"{CSI}11m"
IBMPC_OFF: typing.Final = f"{CSI}10m"


def set_cursor_position(x: int, y: int) -> str:
    """
    Return the escape sequence that moves the cursor to column *x*, row *y*.

    :raises TypeError: *x* or *y* is not an integer.
    """
    if not isinstance(x, int):
        raise TypeError(x)
    if not isinstance(y, int):
        raise TypeError(y)

    return f"{CSI}{y + 1:d};{x + 1:d}H"


def move_cursor_right(x: int) -> str:
    """Return the escape sequence that moves the cursor right by *x* columns, or "" when *x* is not positive."""
    if x < 1:
        return ""
    return f"{CSI}{x:d}C"


def move_cursor_up(x: int) -> str:
    """Return the escape sequence that moves the cursor up by *x* rows, or "" when *x* is not positive."""
    if x < 1:
        return ""
    return f"{CSI}{x:d}A"


def move_cursor_down(x: int) -> str:
    """Return the escape sequence that moves the cursor down by *x* rows, or "" when *x* is not positive."""
    if x < 1:
        return ""
    return f"{CSI}{x:d}B"


def hyperlink_open(link: Hyperlink) -> str:
    r"""Return the OSC 8 sequence that draws the following text as hyperlink *link*.

    >>> from urwid.display.common import Hyperlink
    >>> hyperlink_open(Hyperlink("https://urwid.org", id="home"))
    '\x1b]8;id=home;https://urwid.org\x1b\\'
    """
    params = f"id={link.id}" if link.id else ""
    return f"{OSC}8;{params};{link.uri}{ST}"


HIDE_CURSOR: typing.Final = PrivateMode.CURSOR_VISIBLE.disable_seq
SHOW_CURSOR: typing.Final = PrivateMode.CURSOR_VISIBLE.enable_seq

_MOUSE_MODES: typing.Final = (
    PrivateMode.MOUSE_REPORTING,
    PrivateMode.MOUSE_BUTTON_TRACKING,
    PrivateMode.MOUSE_SGR_MODE,
)
MOUSE_TRACKING_ON: typing.Final = "".join(mode.enable_seq for mode in _MOUSE_MODES)
MOUSE_TRACKING_OFF: typing.Final = "".join(mode.disable_seq for mode in reversed(_MOUSE_MODES))

DESIGNATE_G1_SPECIAL: typing.Final = f"{ESC})0"

ERASE_IN_LINE_RIGHT: typing.Final = f"{CSI}K"
