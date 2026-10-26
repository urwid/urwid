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


"""Terminal Escape Sequences for input and display."""

from __future__ import annotations

import contextlib
import enum
import functools
import re
import sys
import typing
from collections.abc import MutableMapping

from urwid import _deprecation, str_util, util

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from .common import Hyperlink

    _KeyQueueData = dict[int, "str | _KeyQueueData"]
    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _PrivateModeReport = tuple[typing.Literal["private mode report"], str, int]
    # the kitty keyboard protocol flags the terminal has in effect
    _KeyboardProtocolReport = tuple[typing.Literal["keyboard protocol report"], int]
    # an xterm key modifier resource and its value, None when the terminal reports it at its initial value
    _ModifyKeysReport = tuple[typing.Literal["modify keys report"], int, int | None]
    # the parameters of a Primary Device Attributes reply
    _DeviceAttributesReport = tuple[typing.Literal["device attributes"], tuple[int, ...]]
    _TerminalReport = _PrivateModeReport | _KeyboardProtocolReport | _ModifyKeysReport | _DeviceAttributesReport

IS_WINDOWS: typing.Final = sys.platform == "win32"

within_double_byte = str_util.within_double_byte

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

# the most common ord() calls used for numeric decode, pre-calculate once
_ORD_0: typing.Final = ord("0")
_ORD_9: typing.Final = ord("9")
# longest "Pb;Px;Py" body of an SGR mouse report accepted before its "M"/"m" terminator
_SGR_MOUSE_MAX_LEN: typing.Final = 32
# longest parameter body of a key report or a terminal reply accepted before its final byte
_CSI_PARAMETERS_MAX_LEN: typing.Final = 64

###################
# Input sequences
###################


class MoreInputRequired(Exception):
    """Raised when the input decoded so far is a prefix of a longer escape sequence."""


def escape_modifier(digit: str) -> str:
    """Translate a CSI modifier digit into the "shift "/"meta "/"ctrl " prefix combination it encodes."""
    mode = ord(digit) - ord("1")
    return "shift " * (mode & 1) + "meta " * ((mode & 2) // 2) + "ctrl " * ((mode & 4) // 4)


class KeyModifier(enum.IntFlag):
    """The modifier bits of a key report: the CSI parameter is 1 plus these bits.

    These are the kitty keyboard protocol's names. xterm sends the first three, and with its alwaysUseMods resource
    it sends its Meta key as the SUPER bit, which urwid then names ``super`` as well.
    """

    SHIFT = 1
    ALT = 2
    CTRL = 4
    SUPER = 8
    HYPER = 16
    META = 32
    CAPS_LOCK = 64
    NUM_LOCK = 128


class KittyKeyboardFlag(enum.IntFlag):
    """The kitty keyboard protocol's progressive enhancement flags, which a program sets with ``CSI = flags u``."""

    DISAMBIGUATE = 1  # disambiguate escape codes
    EVENT_TYPES = 2  # report event types
    ALTERNATE_KEYS = 4  # report alternate keys
    ALL_KEYS = 8  # report all keys as escape codes
    ASSOCIATED_TEXT = 16  # report associated text


#: the key name prefix of each modifier, in the order urwid writes them; Alt and Meta are both urwid's "meta"
_KEY_MODIFIER_PREFIXES: typing.Final = (
    ("shift ", KeyModifier.SHIFT),
    ("meta ", KeyModifier.ALT | KeyModifier.META),
    ("ctrl ", KeyModifier.CTRL),
    ("super ", KeyModifier.SUPER),
    ("hyper ", KeyModifier.HYPER),
)

#: the keys a CSI u report names by a code that is not their text, with the names of the matching legacy keys
_CSI_U_KEYS: typing.Final[dict[int, str]] = {
    8: "backspace",  # what xterm sends for Backspace when its backarrowKey resource is set
    9: "tab",
    13: "enter",
    27: "esc",
    127: "backspace",
    57358: "caps lock",
    57359: "scroll lock",
    57360: "num lock",
    57361: "print screen",
    57362: "pause",
    57363: "menu",
    **{57376 + offset: f"f{13 + offset}" for offset in range(23)},
    # the keypad keys, named as their application keypad and legacy forms are
    **{57399 + digit: str(digit) for digit in range(10)},
    57409: ".",
    57410: "/",
    57411: "*",
    57412: "-",
    57413: "+",
    57414: "enter",
    57415: "=",
    57416: ",",
    57417: "left",
    57418: "right",
    57419: "up",
    57420: "down",
    57421: "page up",
    57422: "page down",
    57423: "home",
    57424: "end",
    57425: "insert",
    57426: "delete",
    57427: "5",
    57428: "media play",
    57429: "media pause",
    57430: "media play pause",
    57431: "media reverse",
    57432: "media stop",
    57433: "media fast forward",
    57434: "media rewind",
    57435: "media track next",
    57436: "media track previous",
    57437: "media record",
    57438: "lower volume",
    57439: "raise volume",
    57440: "mute volume",
    57441: "left shift",
    57442: "left ctrl",
    57443: "left alt",
    57444: "left super",
    57445: "left hyper",
    57446: "left meta",
    57447: "right shift",
    57448: "right ctrl",
    57449: "right alt",
    57450: "right super",
    57451: "right hyper",
    57452: "right meta",
    57453: "iso level3 shift",
    57454: "iso level5 shift",
}

#: the key of each CSI number ~ report, by its number
_CSI_TILDE_KEYS: typing.Final[dict[int, str]] = {
    1: "home",
    2: "insert",
    3: "delete",
    4: "end",
    5: "page up",
    6: "page down",
    7: "home",
    8: "end",
    **dict(
        zip(
            (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34),
            (f"f{number}" for number in range(1, 21)),
            strict=True,
        )
    ),
    57427: "5",  # the keypad's middle key in the kitty keyboard protocol
}

#: the key of each CSI 1 ; modifiers letter report, by its final byte; F3 is CSI 13 ~ only, since CSI R is a cursor
#: position report
_CSI_LETTER_KEYS: typing.Final[dict[int, str]] = {
    ord(letter): key
    for letter, key in zip(
        "ABCDEFHPQS",
        ("up", "down", "right", "left", "5", "end", "home", "f1", "f2", "f4"),
        strict=True,
    )
}

#: the number xterm's modifyOtherKeys puts before the modifiers and the key's code in CSI 27 ; modifiers ; code ~
_MODIFY_OTHER_KEYS_NUMBER: typing.Final = 27


def _modified_key_name(key: str, modifiers: int) -> str:
    """Return *key* with the prefixes of the modifier bits *modifiers*; the lock bits do not change the key."""
    return "".join(prefix for prefix, bits in _KEY_MODIFIER_PREFIXES if modifiers & bits) + key


def _text_key_name(code: int, shifted_code: int | None, modifiers: int, *, shift_applied: bool) -> str | None:
    """Return the name of a key that types the character *code*, or None when *code* is not a printable character.

    A shifted letter or symbol is named by the character it types and without the shift prefix, as the legacy
    encodings name it: Alt+Shift+A is ``meta A``.

    :param shifted_code: the character the key types with shift, when the terminal reported it.
    :param shift_applied: *code* is already the character typed with shift, as xterm reports it.
    """
    if not 0 <= code <= sys.maxunicode or not (char := chr(code)).isprintable():
        return None
    if modifiers & KeyModifier.SHIFT:
        if shifted_code is not None and 0 <= shifted_code <= sys.maxunicode and chr(shifted_code).isprintable():
            char = chr(shifted_code)
        elif shift_applied or char.lower() != char or char == " ":
            pass  # an upper case letter, or a space, is the character typed with shift, whichever terminal reported it
        elif len(upper := char.upper()) == 1 and upper != char:
            char = upper
        else:
            # the shifted character of a symbol depends on the keyboard layout, which the report did not give
            return _modified_key_name(char, modifiers)
        modifiers &= ~KeyModifier.SHIFT
    return _modified_key_name(char, modifiers)


input_sequences: list[tuple[str, str]] = [
    ("[A", "up"),
    ("[B", "down"),
    ("[C", "right"),
    ("[D", "left"),
    ("[E", "5"),
    ("[F", "end"),
    ("[G", "5"),
    ("[H", "home"),
    ("[I", "focus in"),
    ("[O", "focus out"),
    ("[1~", "home"),
    ("[2~", "insert"),
    ("[3~", "delete"),
    # st in normal keypad mode
    ("[4h", "insert"),
    ("[P", "delete"),
    # F2 and F4 without modifiers in the kitty keyboard protocol, whose F1 is the CSI P above
    ("[Q", "f2"),
    ("[S", "f4"),
    ("[4~", "end"),
    ("[5~", "page up"),
    ("[6~", "page down"),
    ("[7~", "home"),
    ("[8~", "end"),
    ("[[A", "f1"),
    ("[[B", "f2"),
    ("[[C", "f3"),
    ("[[D", "f4"),
    ("[[E", "f5"),
    ("[11~", "f1"),
    ("[12~", "f2"),
    ("[13~", "f3"),
    ("[14~", "f4"),
    ("[15~", "f5"),
    ("[17~", "f6"),
    ("[18~", "f7"),
    ("[19~", "f8"),
    ("[20~", "f9"),
    ("[21~", "f10"),
    ("[23~", "f11"),
    ("[24~", "f12"),
    ("[25~", "f13"),
    ("[26~", "f14"),
    ("[28~", "f15"),
    ("[29~", "f16"),
    ("[31~", "f17"),
    ("[32~", "f18"),
    ("[33~", "f19"),
    ("[34~", "f20"),
    ("OA", "up"),
    ("OB", "down"),
    ("OC", "right"),
    ("OD", "left"),
    ("OH", "home"),
    ("OF", "end"),
    ("OP", "f1"),
    ("OQ", "f2"),
    ("OR", "f3"),
    ("OS", "f4"),
    ("Oo", "/"),
    ("Oj", "*"),
    ("Om", "-"),
    ("Ok", "+"),
    ("[Z", "shift tab"),
    ("On", "."),
    ("Ol", ","),
    ("OX", "="),
    ("OE", "5"),
    ("OM", "enter"),
    ("[200~", "begin paste"),
    ("[201~", "end paste"),
    *(
        (prefix + letter, modifier + key)
        for prefix, modifier in zip("O[", ("meta ", "shift "), strict=True)
        for letter, key in zip("abcd", ("up", "down", "right", "left"), strict=True)
    ),
    *(
        (f"[{digit}{symbol}", modifier + key)
        for modifier, symbol in zip(("shift ", "meta "), "$^", strict=True)
        for digit, key in zip("235678", ("insert", "delete", "page up", "page down", "home", "end"), strict=True)
    ),
    *((f"O{ord('p') + n:c}", str(n)) for n in range(10)),
    *(
        # modified cursor keys + home, end, 5 -- [#X and [1;#X forms
        (prefix + digit + letter, escape_modifier(digit) + key)
        for prefix in ("[", "[1;")
        for digit in "12345678"
        for letter, key in zip("ABCDEFGH", ("up", "down", "right", "left", "5", "end", "5", "home"), strict=True)
    ),
    *(
        # modified F1-F4 keys - O#X form and [1;#X form
        (prefix + digit + letter, escape_modifier(digit) + f"f{number}")
        for prefix in ("O", "[1;")
        for digit in "12345678"
        for number, letter in enumerate("PQRS", start=1)
    ),
    *(
        # modified editing and F1-F20 keys -- [N;#~ form
        (f"[{num!s};{digit}~", escape_modifier(digit) + key)
        for digit in "12345678"
        for num, key in zip(
            (2, 3, 5, 6, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34),
            (
                "insert",
                "delete",
                "page up",
                "page down",
                *(f"f{idx}" for idx in range(1, 21)),
            ),
            strict=True,
        )
    ),
    # mouse reporting (special handling done in KeyqueueTrie)
    ("[M", "mouse"),
    # mouse reporting for SGR 1006
    ("[<", "sgrmouse"),
    # report status response
    ("[0n", "status ok"),
]


class KeyqueueTrie:
    """Trie mapping terminal escape sequences to the key names they decode to."""

    __slots__ = ("data",)

    def __init__(self, sequences: Iterable[tuple[str, str]]) -> None:
        """
        Build a trie of the given ``(escape sequence, key name)`` pairs.

        :raises TypeError: two sequences collide in the trie.
        """
        self.data: _KeyQueueData = {}
        for s, result in sequences:
            if isinstance(result, dict):
                raise TypeError(result)
            self.add(self.data, s, result)

    def add(
        self,
        root: _KeyQueueData,
        s: str,
        result: str,
    ) -> None:
        """
        Add one ``(escape sequence, key name)`` pair to the trie.

        :raises RuntimeError: the sequence collides with a shorter one already in the trie.
        :raises ValueError: the sequence collides with a longer one already in the trie.
        """
        if not isinstance(root, MutableMapping) or not s:
            raise RuntimeError("trie conflict detected")

        seq_start = ord(s[0])
        if seq_start in root:
            child = root[seq_start]
            if isinstance(child, str):
                raise ValueError("trie conflict detected")

            self.add(child, s[1:], result)
            return
        if len(s) > 1:
            d: _KeyQueueData = {}
            root[seq_start] = d
            self.add(d, s[1:], result)
            return
        root[seq_start] = result

    def get(
        self,
        keys: list[int],
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str | _MouseInput | _CursorPosition | _TerminalReport, list[int]] | None:
        """Decode the longest key sequence matching the start of ``keys``, trying the trie then the special reports.

        :param keys: the codes after the ESC that starts the sequence.
        :param more_available: raise MoreInputRequired when the codes end in the middle of a sequence.
        :param csi_u_shift_applied: see `read_key_report`.
        """
        result: tuple[str | _MouseInput | _CursorPosition | _TerminalReport, list[int]] | None
        if result := self.get_recurse(self.data, keys, more_available):
            return result

        if (result := self.read_private_mode_report(keys, more_available)) is not None:
            return result

        if (result := self.read_private_report(keys, more_available)) is not None:
            return result

        if (result := self.read_modify_keys_report(keys, more_available)) is not None:
            return result

        if (result := self.read_key_report(keys, more_available, csi_u_shift_applied=csi_u_shift_applied)) is not None:
            return result

        return self.read_cursor_position(keys, more_available)

    def get_recurse(
        self,
        root: (_KeyQueueData | str),
        keys: list[int],
        more_available: bool,
    ) -> tuple[str | _MouseInput, list[int]] | None:
        """
        Walk the trie for the next key, consuming codes as it goes.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if not isinstance(root, MutableMapping):
            if root == "mouse":
                return self.read_mouse_info(keys, more_available)

            if root == "sgrmouse":
                return self.read_sgrmouse_info(keys, more_available)

            return (root, keys)

        if not keys:
            # get more keys
            if more_available:
                raise MoreInputRequired
            return None

        if keys[0] not in root:
            return None

        return self.get_recurse(root[keys[0]], keys[1:], more_available)

    def read_mouse_info(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_MouseInput, list[int]] | None:
        """Read an X10 mouse report from the codes and return the resulting input.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if len(keys) < 3:
            if more_available:
                raise MoreInputRequired
            return None

        b = keys[0] - _MOUSE_BYTE_OFFSET
        # supports 0-255
        x, y = (keys[1] - _MOUSE_COORD_OFFSET) % 256, (keys[2] - _MOUSE_COORD_OFFSET) % 256

        prefixes = []
        if b & MouseBit.SHIFT:
            prefixes.append("shift ")
        if b & MouseBit.META:
            prefixes.append("meta ")
        if b & MouseBit.CTRL:
            prefixes.append("ctrl ")
        multi_click = (b & MOUSE_MULTIPLE_CLICK_MASK) >> 9
        if multi_click == 1:
            prefixes.append("double ")
        elif multi_click == 2:
            prefixes.append("triple ")
        prefix = "".join(prefixes)

        button_bits = b & MouseBit.BUTTON
        if b & MouseBit.EXTRA_BUTTON:
            button = 8 + button_bits
        elif b & MouseBit.HIGH_BUTTON:
            button = 4 + button_bits
        else:
            button = 1 + button_bits

        if button_bits == MouseBit.BUTTON and not b & (MouseBit.HIGH_BUTTON | MouseBit.EXTRA_BUTTON):
            action = "release"
            button = 0
        elif b & MOUSE_RELEASE_FLAG:
            action = "release"
        elif b & MouseBit.DRAG:
            action = "drag"
        elif multi_click:
            action = "click"
        else:
            action = "press"

        return ((f"{prefix}mouse {action}", button, x, y), keys[3:])

    def read_sgrmouse_info(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_MouseInput, list[int]] | None:
        # Helpful links:
        # https://stackoverflow.com/questions/5966903/how-to-get-mousemove-and-mouseclick-in-bash
        # http://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
        """Read an SGR mouse report from the codes and return the resulting input.

        :returns: the mouse event and the codes left after the report,
            or None when the codes do not start with an SGR mouse report.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None

        # Anything other than "Pb;Px;Py" digits before the terminator, or a longer run, is not a report: it is
        # rejected here instead of being buffered while waiting for a terminator that may never come.
        for pos_m in range(min(len(keys), _SGR_MOUSE_MAX_LEN + 1)):
            k = keys[pos_m]
            if k in {ord("M"), ord("m")}:
                break
            if not (_ORD_0 <= k <= _ORD_9 or k == ord(";")):
                return None
        else:
            if more_available and len(keys) <= _SGR_MOUSE_MAX_LEN:
                raise MoreInputRequired
            return None

        fields = bytes(keys[:pos_m]).split(b";")
        if len(fields) != 3 or not all(fields):
            return None
        b, x, y = (int(field) for field in fields)
        action = chr(keys[pos_m])
        # Double and triple clicks are not supported.
        # They can be implemented by using a timer.
        # This timer can check if the last registered click is below a certain threshold.
        # This threshold is normally set in the operating system itself,
        # so setting one here will cause an inconsistent behaviour.

        prefixes = []
        if b & MouseBit.SHIFT:
            prefixes.append("shift ")
        if b & MouseBit.META:
            prefixes.append("meta ")
        if b & MouseBit.CTRL:
            prefixes.append("ctrl ")
        prefix = "".join(prefixes)

        button_bits = b & MouseBit.BUTTON
        if b & MouseBit.EXTRA_BUTTON:
            button = 8 + button_bits
        elif b & MouseBit.HIGH_BUTTON:
            button = 4 + button_bits
        else:
            button = 1 + button_bits
        x -= 1
        y -= 1

        if action == "M":
            if b & MouseBit.DRAG:
                action = "drag"
            else:
                action = "press"
        else:
            action = "release"

        return ((f"{prefix}mouse {action}", button, x, y), keys[pos_m + 1 :])

    def read_private_mode_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_PrivateModeReport, list[int]] | None:
        """Interpret a DECRPM reply (CSI ? Pd ; Ps $ y).

        :returns: ``('private mode report', mode, value)``.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[0] != ord("["):
            return None
        if len(keys) < 2:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[1] != ord("?"):
            return None
        # read the mode number
        mode = ""
        i = 2
        for k in keys[i:]:
            i += 1
            if k == ord(";"):
                if not mode:
                    return None
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            mode += chr(k)
        else:
            if more_available:
                raise MoreInputRequired
            return None
        if not keys[i:]:
            if more_available:
                raise MoreInputRequired
            return None
        # Ps: "0" is a valid value here (mode not recognized), unlike the mode number above.
        value = 0
        got_digit = False
        for k in keys[i:]:
            i += 1
            if k == ord("$"):
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            value = value * 10 + k - _ORD_0
            got_digit = True
        else:
            if more_available:
                raise MoreInputRequired
            return None
        if not got_digit:
            return None
        if not keys[i:]:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[i] != ord("y"):
            return None
        return (("private mode report", mode, value), keys[i + 1 :])

    def read_cursor_position(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_CursorPosition, list[int]] | None:
        """
        Interpret cursor position information being sent by the user's terminal.

        :returns: ('cursor position', x, y) where (x, y) == (0, 0) is the top left of the screen.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[0] != ord("["):
            return None
        # read y value
        y = 0
        i = 1
        for k in keys[i:]:
            i += 1
            if k == ord(";"):
                if not y:
                    return None
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            if not y and k == _ORD_0:
                return None
            y = y * 10 + k - _ORD_0
        if not keys[i:]:
            if more_available:
                raise MoreInputRequired
            return None
        # read x value
        x = 0
        for k in keys[i:]:
            i += 1
            if k == ord("R"):
                if not x:
                    return None
                return (("cursor position", x - 1, y - 1), keys[i:])
            if k < _ORD_0 or k > _ORD_9:
                return None
            if not x and k == _ORD_0:
                return None
            x = x * 10 + k - _ORD_0
        if not keys[i:] and more_available:
            raise MoreInputRequired
        return None

    @staticmethod
    def _split_csi(
        keys: list[int],
        more_available: bool,
        introducer: bytes,
        final_bytes: Iterable[int],
    ) -> tuple[list[list[str]], int, list[int]] | None:
        """Split a control sequence that starts with *introducer* and ends with one of *final_bytes*.

        :returns: the parameters, each split into its sub-parameters, the final byte and the codes after it,
            or None when the codes do not start with such a sequence.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if keys[: len(introducer)] != list(introducer[: len(keys)]):
            return None
        for pos in range(len(introducer), min(len(keys), len(introducer) + _CSI_PARAMETERS_MAX_LEN + 1)):
            k = keys[pos]
            if k in final_bytes:
                break
            if not (_ORD_0 <= k <= _ORD_9 or k in {ord(";"), ord(":")}):
                return None
        else:
            if more_available and len(keys) <= len(introducer) + _CSI_PARAMETERS_MAX_LEN:
                raise MoreInputRequired
            return None
        body = bytes(keys[len(introducer) : pos]).decode("ascii")
        return [field.split(":") for field in body.split(";")], keys[pos], keys[pos + 1 :]

    def read_private_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_KeyboardProtocolReport | _DeviceAttributesReport, list[int]] | None:
        """Interpret a kitty keyboard protocol flags reply (CSI ? flags u) or a Primary DA reply (CSI ? Ps ; ... c).

        :returns: ``('keyboard protocol report', flags)`` or ``('device attributes', parameters)``.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := self._split_csi(keys, more_available, b"[?", (ord("u"), ord("c")))) is None:
            return None
        fields, final, rest = split
        if any(len(field) != 1 or not field[0] for field in fields):
            return None
        values = tuple(int(field[0]) for field in fields)
        if final == ord("c"):
            return ("device attributes", values), rest
        if len(values) != 1:
            return None
        return ("keyboard protocol report", values[0]), rest

    def read_modify_keys_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_ModifyKeysReport, list[int]] | None:
        """Interpret xterm's reply to a key modifier options query (CSI > Pp ; Pv m, or CSI > Pp m).

        :returns: ``('modify keys report', resource, value)``, with value None when the reply omits it.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := self._split_csi(keys, more_available, b"[>", (ord("m"),))) is None:
            return None
        fields, _final, rest = split
        if len(fields) > 2 or any(len(field) != 1 for field in fields) or not fields[0][0]:
            return None
        value = int(fields[1][0]) if len(fields) == 2 and fields[1][0] else None
        return ("modify keys report", int(fields[0][0]), value), rest

    def read_key_report(
        self,
        keys: list[int],
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str, list[int]] | None:
        """Interpret a key report the trie has no entry for.

        These are the kitty keyboard protocol's CSI u reports, xterm's modifyOtherKeys reports
        (CSI 27 ; modifiers ; code ~), and the legacy CSI number ; modifiers ~ and CSI 1 ; modifiers letter forms
        with modifiers beyond shift, alt and ctrl.

        :param keys: the codes after the ESC that starts the sequence.
        :param more_available: raise MoreInputRequired when the codes end in the middle of a sequence.
        :param csi_u_shift_applied: a CSI u report carries the character typed with shift, as xterm's modifyOtherKeys
            sends it with the formatOtherKeys resource set, rather than the kitty keyboard protocol's unshifted key.
        :returns: the key name, or None when the codes do not start with a key report urwid can name.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        final_bytes = (ord("u"), ord("~"), *_CSI_LETTER_KEYS)
        if keys[1:2] and not _ORD_0 <= keys[1] <= _ORD_9:
            # a key report starts with its key's number; a private parameter starts a terminal reply instead
            return None
        if (split := self._split_csi(keys, more_available, b"[", final_bytes)) is None:
            return None
        fields, final, rest = split
        numbers = [[int(sub) if sub else None for sub in field] for field in fields]
        code, shifted_code = (numbers[0] + [None])[:2]
        modifiers = numbers[1][0] if len(numbers) > 1 and numbers[1][0] is not None else 1
        if code is None or modifiers < 1:
            return None
        modifiers -= 1

        name: str | None
        if final == ord("u"):
            if code in _CSI_U_KEYS:
                name = _modified_key_name(_CSI_U_KEYS[code], modifiers)
            else:
                name = _text_key_name(code, shifted_code, modifiers, shift_applied=csi_u_shift_applied)
        elif final == ord("~") and code == _MODIFY_OTHER_KEYS_NUMBER:
            if len(numbers) != 3 or (key_code := numbers[2][0]) is None:
                return None
            if key_code in _CSI_U_KEYS:
                name = _modified_key_name(_CSI_U_KEYS[key_code], modifiers)
            else:
                name = _text_key_name(key_code, None, modifiers, shift_applied=True)
        elif final == ord("~"):
            name = _modified_key_name(_CSI_TILDE_KEYS[code], modifiers) if code in _CSI_TILDE_KEYS else None
        else:
            name = _modified_key_name(_CSI_LETTER_KEYS[final], modifiers) if code == 1 else None

        if name is None:
            return None
        return name, rest


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

# the names of the mouse report bits before MouseBit replaced them
_RENAMED_MOUSE_BITS: typing.Final = {
    "_MOUSE_SHIFT_FLAG": MouseBit.SHIFT,
    "_MOUSE_META_FLAG": MouseBit.META,
    "_MOUSE_CTRL_FLAG": MouseBit.CTRL,
    "_MOUSE_HIGH_BUTTON_FLAG": MouseBit.HIGH_BUTTON,
    "_MOUSE_EXTRA_BUTTON_FLAG": MouseBit.EXTRA_BUTTON,
    "_MOUSE_BUTTON_MASK": MouseBit.BUTTON,
}


# Hidden from type checkers, which would otherwise accept any attribute name of this module.
if not typing.TYPE_CHECKING:

    def __getattr__(name: str) -> int:
        """Resolve a mouse report bit by the name it had before :class:`MouseBit`, warning about the rename.

        :raises AttributeError: *name* is not defined in this module.

        .. deprecated:: 5.0.0
            Use the members of :class:`MouseBit` instead of the ``_MOUSE_*_FLAG`` names and ``_MOUSE_BUTTON_MASK``.
            This API will be removed in version 6.0.
        """
        if name in _RENAMED_MOUSE_BITS:
            bit = _RENAMED_MOUSE_BITS[name]
            _deprecation.warn(
                f"{__name__}.{name} is renamed to {__name__}.MouseBit.{bit.name}.", since="5.0.0", removed_in="6.0"
            )
            return int(bit)
        raise AttributeError(f"{name} is not defined in {__name__}")


# The X10 report encodes the button byte and the two coordinate bytes by adding an offset to
# keep them in the printable ASCII range; coordinates are further offset by 1 since they are
# reported 1-based.
_MOUSE_BYTE_OFFSET: typing.Final = 32
_MOUSE_COORD_OFFSET: typing.Final = 33
# the 0-based column or row an X10 report cannot carry: xterm sends it, and any farther one, as a NUL byte,
# which decodes back to this value
MOUSE_X10_PAST_END: typing.Final = 255 - _MOUSE_BYTE_OFFSET


#################################################
# Build the input trie from input_sequences list
input_trie = KeyqueueTrie(input_sequences)
#################################################

_keyconv = {
    8: "backspace",
    9: "tab",
    10: "enter",
    13: "enter",
    127: "backspace",
    # curses-only keycodes follow..  (XXX: are these used anymore?)
    258: "down",
    259: "up",
    260: "left",
    261: "right",
    262: "home",
    263: "backspace",
    265: "f1",
    266: "f2",
    267: "f3",
    268: "f4",
    269: "f5",
    270: "f6",
    271: "f7",
    272: "f8",
    273: "f9",
    274: "f10",
    275: "f11",
    276: "f12",
    277: "shift f1",
    278: "shift f2",
    279: "shift f3",
    280: "shift f4",
    281: "shift f5",
    282: "shift f6",
    283: "shift f7",
    284: "shift f8",
    285: "shift f9",
    286: "shift f10",
    287: "shift f11",
    288: "shift f12",
    330: "delete",
    331: "insert",
    338: "page down",
    339: "page up",
    343: "enter",  # on numpad
    350: "5",  # on numpad
    360: "end",
}

if IS_WINDOWS:
    _keyconv[351] = "shift tab"
    _keyconv[358] = "end"


def process_keyqueue(
    codes: list[int],
    more_available: bool,
    *,
    keyboard_protocol: typing.Literal["kitty", "modify other keys"] | None = None,
) -> tuple[list[str | _MouseInput | _CursorPosition | _TerminalReport], list[int]]:
    """Decode `codes` into input events, consuming as much of the queue as is currently decodable.

    :param codes: list of key codes
    :param more_available: if True then raise MoreInputRequired when in the middle of a character sequence
        (escape/utf8/wide) and caller will attempt to send more key codes on the next call.
    :param keyboard_protocol: the keyboard protocol the terminal has on. With the kitty keyboard protocol, CSI P is F1
        rather than the Delete key st sends it for; with xterm's modifyOtherKeys, a CSI u report carries the character
        typed with shift.
    :returns: a ``(list of input, list of remaining key codes)`` tuple.
    :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
    """
    code = codes[0]
    if 32 <= code <= 126:
        key = chr(code)
        return [key], codes[1:]
    if code in _keyconv:
        return [_keyconv[code]], codes[1:]
    if 0 < code < 27:
        return [f"ctrl {ord('a') + code - 1:c}"], codes[1:]
    if 27 < code < 32:
        return [f"ctrl {ord('A') + code - 1:c}"], codes[1:]

    em = str_util.get_byte_encoding()

    if em == "utf8" and 127 < code < 256:
        if code & 0xE0 == 0xC0:  # 2-byte form
            need_more = 1
        elif code & 0xF0 == 0xE0:  # 3-byte form
            need_more = 2
        elif code & 0xF8 == 0xF0:  # 4-byte form
            need_more = 3
        else:
            return [f"<{code:d}>"], codes[1:]

        for i in range(1, need_more + 1):
            if len(codes) <= i:
                if more_available:
                    raise MoreInputRequired

                return [f"<{code:d}>"], codes[1:]

            k = codes[i]
            if k > 256 or k & 0xC0 != 0x80:
                return [f"<{code:d}>"], codes[1:]

        s = bytes(codes[: need_more + 1])

        try:
            return [s.decode("utf-8")], codes[need_more + 1 :]
        except UnicodeDecodeError:
            return [f"<{code:d}>"], codes[1:]

    if (
        em == "wide"
        and code < 256
        and str_util.within_double_byte(
            (start_code := code.to_bytes(1, "little")),
            0,
            0,
        )
    ):
        if not codes[1:] and more_available:
            raise MoreInputRequired
        if codes[1:] and codes[1] < 256:
            end_code = codes[1].to_bytes(1, "little")

            if str_util.within_double_byte(start_code + end_code, 0, 1):
                # a pair that is not a character of the encoding falls through and is decoded byte by byte
                with contextlib.suppress(UnicodeDecodeError):
                    return [(start_code + end_code).decode(util.get_encoding())], codes[2:]

    if 127 < code < 256:
        try:
            key = code.to_bytes(1, "little").decode(util.get_encoding())
        except UnicodeDecodeError:
            key = chr(code)  # not a character of the encoding (always for "ascii"): read the byte as Latin-1
        return [key], codes[1:]
    if code != 27:
        return [f"<{code:d}>"], codes[1:]

    if keyboard_protocol == "kitty" and codes[1:3] == [ord("["), ord("P")]:
        return ["f1"], codes[3:]

    shift_applied = keyboard_protocol == "modify other keys"
    if (result := input_trie.get(codes[1:], more_available, csi_u_shift_applied=shift_applied)) is not None:
        decoded, remaining_codes = result
        return [decoded], remaining_codes

    if codes[1:3] == [27, 27]:
        # With a third ESC following, the second one cannot start a sequence the first one prefixes as meta,
        # so decode the first one alone rather than recursing once per ESC in an arbitrarily long run.
        return ["esc"], codes[1:]

    if codes[1:]:
        # Meta keys -- ESC+Key form
        run, remaining_codes = process_keyqueue(codes[1:], more_available, keyboard_protocol=keyboard_protocol)
        # A mouse event or a terminal report (cursor position, DECRPM, a query reply) cannot take a meta prefix.
        if not isinstance(run[0], str) or run[0] == "esc" or "meta " in run[0]:
            return ["esc", *run], remaining_codes
        return [f"meta {run[0]}", *run[1:]], remaining_codes

    return ["esc"], codes[1:]


####################
# Output sequences
####################

ESC: typing.Final = "\x1b"
# control sequence introducer
CSI: typing.Final = f"{ESC}["
# operating system command, and the string terminator ending it
OSC: typing.Final = f"{ESC}]"
ST: typing.Final = f"{ESC}\\"
# OSC 8 with an empty URI ends the hyperlink the text is drawn with
HYPERLINK_CLOSE: typing.Final = f"{OSC}8;;{ST}"
# Linux console palette, console_codes(4): LINUX_SET_PALETTE then "nrrggbb" in hex, with no terminator,
# sets entry n (0-15); LINUX_RESET_PALETTE resets all 16 entries to the console default.
LINUX_SET_PALETTE: typing.Final = f"{OSC}P"
LINUX_RESET_PALETTE: typing.Final = f"{OSC}R"


class PrivateMode(enum.StrEnum):
    """DEC private modes (``CSI ? Pd h``/``l``).

    Not every member is queried or acted on, some members are for future development.
    `_raw_display_base.TermModes` carries a field for each mode the raw display queries.
    `vterm.TermModes` carries the modes a `Terminal` acts on, with one field for each group of modes that replace
    each other, such as the mouse tracking modes.
    """

    APPLICATION_CURSOR_KEYS = "1"  # DECCKM
    COLUMNS_132 = "3"  # DECCOLM
    REVERSE_VIDEO = "5"  # DECSCNM
    ORIGIN_MODE = "6"  # DECOM
    AUTO_WRAP = "7"  # DECAWM
    # Neither display controls cursor blinking; the mode is recognised and never turned on.
    CURSOR_BLINK = "12"
    CURSOR_VISIBLE = "25"  # DECTCEM
    # The alternate screen (47, 1047, 1049) and the cursor saved as DECSC saves it (1048); a Terminal implements them
    # as `vterm.TermCanvas.set_alternate_screen` describes.
    ALTERNATE_SCREEN = "47"
    ALTERNATE_SCREEN_CLEARED_ON_EXIT = "1047"
    SAVE_CURSOR = "1048"
    ALTERNATE_SCREEN_BUFFER = "1049"
    # Reports presses only, without modifiers; a Terminal uses it only while no other tracking mode is on.
    MOUSE_X10 = "9"
    MOUSE_REPORTING = "1000"
    # The program answers a press with CSI T and the terminal highlights the drag; urwid implements none of it.
    MOUSE_HIGHLIGHT_TRACKING = "1001"
    MOUSE_BUTTON_TRACKING = "1002"
    MOUSE_ANY_EVENT_TRACKING = "1003"
    MOUSE_UTF8_MODE = "1005"
    MOUSE_SGR_MODE = "1006"
    # The urxvt encoding is recognised, but never turned on or used.
    # xterm's documentation advises against it, because a report looks like CSI Pn M, which is the delete-lines command.
    MOUSE_URXVT_MODE = "1015"
    FOCUS_REPORTING = "1004"
    # A Terminal always sends Meta and Alt as ESC and the key, so it recognises these and does not track them.
    META_SENDS_ESCAPE = "1036"
    ALT_SENDS_ESCAPE = "1039"
    BRACKETED_PASTE = "2004"
    SYNCHRONIZED_OUTPUT = "2026"
    GRAPHEME_CLUSTERING = "2027"
    # Colour scheme change notifications; not queried or turned on yet.
    COLOR_SCHEME_REPORTING = "2031"

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

# DECRQM (CSI ? Pd $ p) reply is DECRPM (CSI ? Pd ; Ps $ y), recognized by KeyqueueTrie.read_private_mode_report().
# Ps: 0 = not recognized, 1-4 = recognized.
DECRQM_RECOGNIZED_VALUES: typing.Final = frozenset({1, 2, 3, 4})
# Ps of a mode the terminal can turn on: 1 set, 2 reset, 3 permanently set; 4 is permanently reset.
DECRQM_SETTABLE_VALUES: typing.Final = frozenset({1, 2, 3})

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
