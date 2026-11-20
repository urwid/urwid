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


"""Key names, modifiers and the key tables shared by the input decoder and the terminal widget."""

from __future__ import annotations

import enum
import sys
import types
import typing


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

#: the number of the keypad's middle key in the kitty keyboard protocol
_KITTY_KEYPAD_MIDDLE: typing.Final = 57427
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
    _KITTY_KEYPAD_MIDDLE: "5",
}

#: the number each key is sent with as CSI number ~, the first of the numbers the decoder takes for it
_TILDE_KEY_NUMBERS: typing.Final = types.MappingProxyType(
    {key: number for number, key in reversed(_CSI_TILDE_KEYS.items())}
)
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
    # the keys sent as CSI number ~, except the kitty keyboard protocol's keypad 5, which only a kitty report carries
    *((f"[{number:d}~", key) for number, key in _CSI_TILDE_KEYS.items() if number != _KITTY_KEYPAD_MIDDLE),
    # st in normal keypad mode
    ("[4h", "insert"),
    ("[P", "delete"),
    # F2 and F4 without modifiers in the kitty keyboard protocol, whose F1 is the CSI P above
    ("[Q", "f2"),
    ("[S", "f4"),
    ("[[A", "f1"),
    ("[[B", "f2"),
    ("[[C", "f3"),
    ("[[D", "f4"),
    ("[[E", "f5"),
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
        # home and end are sent modified as CSI 1 ; # H and F instead
        for num, key in _CSI_TILDE_KEYS.items()
        if key not in {"home", "end"} and num != _KITTY_KEYPAD_MIDDLE
    ),
    # mouse reporting (special handling done in KeyqueueTrie)
    ("[M", "mouse"),
    # mouse reporting for SGR 1006
    ("[<", "sgrmouse"),
    # report status response
    ("[0n", "status ok"),
]
