# Urwid unicode character processing tables
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


from __future__ import annotations

import re
import typing
import warnings

import wcwidth

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

SAFE_ASCII_RE = re.compile("^[ -~]*$")
SAFE_ASCII_BYTES_RE = re.compile(b"^[ -~]*$")

_byte_encoding: Literal["utf8", "narrow", "wide"] = "narrow"


def get_char_width(char: str) -> Literal[0, 1, 2]:
    width = wcwidth.wcwidth(char)
    if width < 0:
        return 0
    return width


def get_width(o: int) -> Literal[0, 1, 2]:
    """Return the screen column width for unicode ordinal o."""
    return get_char_width(chr(o))


def decode_one(text: bytes | str, pos: int) -> tuple[int, int]:
    """
    Return (ordinal at pos, next position) for UTF-8 encoded text.
    """
    lt = len(text) - pos

    b2 = 0  # Fallback, not changing anything
    b3 = 0  # Fallback, not changing anything
    b4 = 0  # Fallback, not changing anything

    try:
        if isinstance(text, str):
            b1 = ord(text[pos])
            if lt > 1:
                b2 = ord(text[pos + 1])
            if lt > 2:
                b3 = ord(text[pos + 2])
            if lt > 3:
                b4 = ord(text[pos + 3])
        else:
            b1 = text[pos]
            if lt > 1:
                b2 = text[pos + 1]
            if lt > 2:
                b3 = text[pos + 2]
            if lt > 3:
                b4 = text[pos + 3]
    except Exception as e:
        raise ValueError(f"{e}: text={text!r}, pos={pos!r}, lt={lt!r}").with_traceback(e.__traceback__) from e

    if not b1 & 0x80:
        return b1, pos + 1
    error = ord("?"), pos + 1

    if lt < 2:
        return error
    if b1 & 0xE0 == 0xC0:
        if b2 & 0xC0 != 0x80:
            return error
        o = ((b1 & 0x1F) << 6) | (b2 & 0x3F)
        if o < 0x80:
            return error
        return o, pos + 2
    if lt < 3:
        return error
    if b1 & 0xF0 == 0xE0:
        if b2 & 0xC0 != 0x80:
            return error
        if b3 & 0xC0 != 0x80:
            return error
        o = ((b1 & 0x0F) << 12) | ((b2 & 0x3F) << 6) | (b3 & 0x3F)
        if o < 0x800:
            return error
        return o, pos + 3
    if lt < 4:
        return error
    if b1 & 0xF8 == 0xF0:
        if b2 & 0xC0 != 0x80:
            return error
        if b3 & 0xC0 != 0x80:
            return error
        if b4 & 0xC0 != 0x80:
            return error
        o = ((b1 & 0x07) << 18) | ((b2 & 0x3F) << 12) | ((b3 & 0x3F) << 6) | (b4 & 0x3F)
        if o < 0x10000:
            return error
        return o, pos + 4
    return error


def decode_one_uni(text: str, i: int) -> tuple[int, int]:
    """
    decode_one implementation for unicode strings
    """
    return ord(text[i]), i + 1


def decode_one_right(text: bytes, pos: int) -> tuple[int, int] | None:
    """
    Return (ordinal at pos, next position) for UTF-8 encoded text.
    pos is assumed to be on the trailing byte of a utf-8 sequence.
    """
    if not isinstance(text, bytes):
        raise TypeError(text)
    error = ord("?"), pos - 1
    p = pos
    while p >= 0:
        if text[p] & 0xC0 != 0x80:
            o, _next_pos = decode_one(text, p)
            return o, p - 1
        p -= 1
        if p == p - 4:
            return error
    return None


def set_byte_encoding(enc: Literal["utf8", "narrow", "wide"]) -> None:
    if enc not in {"utf8", "narrow", "wide"}:
        raise ValueError(enc)
    global _byte_encoding  # noqa: PLW0603  # pylint: disable=global-statement
    _byte_encoding = enc


def get_byte_encoding() -> Literal["utf8", "narrow", "wide"]:
    return _byte_encoding


def calc_string_text_pos(text: str, start_offs: int, end_offs: int, pref_col: int) -> tuple[int, int]:
    """
    Calculate the closest position to the screen column pref_col in text
    where start_offs is the offset into text assumed to be screen column 0
    and end_offs is the end of the range to search.

    :param text: string
    :param start_offs: starting text position
    :param end_offs: ending text position
    :param pref_col: target column
    :returns: (position, actual_col)

    ..note:: this method is a simplified version of `wcwidth.wcswidth` and ideally should be in wcwidth package.
    """
    if start_offs > end_offs:
        raise ValueError((start_offs, end_offs))

    cols = 0
    for idx in range(start_offs, end_offs):
        width = get_char_width(text[idx])
        if width + cols > pref_col:
            return idx, cols
        cols += width

    return end_offs, cols


def calc_text_pos(text: str | bytes, start_offs: int, end_offs: int, pref_col: int) -> tuple[int, int]:
    """
    Calculate the closest position to the screen column pref_col in text
    where start_offs is the offset into text assumed to be screen column 0
    and end_offs is the end of the range to search.

    text may be unicode or a byte string in the target _byte_encoding

    Returns (position, actual_col).
    """
    if start_offs > end_offs:
        raise ValueError((start_offs, end_offs))

    if isinstance(text, str):
        return calc_string_text_pos(text, start_offs, end_offs, pref_col)

    if not isinstance(text, bytes):
        raise TypeError(text)

    if _byte_encoding == "utf8":
        i = start_offs
        sc = 0
        while i < end_offs:
            o, n = decode_one(text, i)
            w = get_width(o)
            if w + sc > pref_col:
                return i, sc
            i = n
            sc += w
        return i, sc

    # "wide" and "narrow"
    i = start_offs + pref_col
    if i >= end_offs:
        return end_offs, end_offs - start_offs
    if _byte_encoding == "wide" and within_double_byte(text, start_offs, i) == 2:
        i -= 1
    return i, i - start_offs


def calc_width(text: str | bytes, start_offs: int, end_offs: int) -> int:
    """
    Return the screen column width of text between start_offs and end_offs.

    text may be unicode or a byte string in the target _byte_encoding

    Some characters are wide (take two columns) and others affect the
    previous character (take zero columns).  Use the widths table above
    to calculate the screen column width of text[start_offs:end_offs]
    """

    if start_offs > end_offs:
        raise ValueError((start_offs, end_offs))

    if isinstance(text, str):
        return sum(get_char_width(char) for char in text[start_offs:end_offs])

    if _byte_encoding == "utf8":
        try:
            return sum(get_char_width(char) for char in text[start_offs:end_offs].decode("utf-8"))
        except UnicodeDecodeError as exc:
            warnings.warn(
                "`calc_width` with text encoded to bytes can produce incorrect results"
                f"due to possible offset in the middle of character: {exc}",
                UnicodeWarning,
                stacklevel=2,
            )

        i = start_offs
        sc = 0
        while i < end_offs:
            o, i = decode_one(text, i)
            w = get_width(o)
            sc += w
        return sc
    # "wide", "narrow" or all printable ASCII, just return the character count
    return end_offs - start_offs


def is_wide_char(text: str | bytes, offs: int) -> bool:
    """
    Test if the character at offs within text is wide.

    text may be unicode or a byte string in the target _byte_encoding
    """
    if isinstance(text, str):
        return get_char_width(text[offs]) == 2
    if not isinstance(text, bytes):
        raise TypeError(text)
    if _byte_encoding == "utf8":
        o, _n = decode_one(text, offs)
        return get_width(o) == 2
    if _byte_encoding == "wide":
        return within_double_byte(text, offs, offs) == 1
    return False


def move_prev_char(text: str | bytes, start_offs: int, end_offs: int) -> int:
    """
    Return the position of the character before end_offs.
    """
    if start_offs >= end_offs:
        raise ValueError((start_offs, end_offs))
    if isinstance(text, str):
        return end_offs - 1
    if not isinstance(text, bytes):
        raise TypeError(text)
    if _byte_encoding == "utf8":
        o = end_offs - 1
        while text[o] & 0xC0 == 0x80:
            o -= 1
        return o
    if _byte_encoding == "wide" and within_double_byte(text, start_offs, end_offs - 1) == 2:
        return end_offs - 2
    return end_offs - 1


def move_next_char(text: str | bytes, start_offs: int, end_offs: int) -> int:
    """
    Return the position of the character after start_offs.
    """
    if start_offs >= end_offs:
        raise ValueError((start_offs, end_offs))
    if isinstance(text, str):
        return start_offs + 1
    if not isinstance(text, bytes):
        raise TypeError(text)
    if _byte_encoding == "utf8":
        o = start_offs + 1
        while o < end_offs and text[o] & 0xC0 == 0x80:
            o += 1
        return o
    if _byte_encoding == "wide" and within_double_byte(text, start_offs, start_offs) == 1:
        return start_offs + 2
    return start_offs + 1


def within_double_byte(text: bytes, line_start: int, pos: int) -> Literal[0, 1, 2]:
    """Return whether pos is within a double-byte encoded character.

    text -- byte string in question
    line_start -- offset of beginning of line (< pos)
    pos -- offset in question

    Return values:
    0 -- not within dbe char, or double_byte_encoding == False
    1 -- pos is on the 1st half of a dbe char
    2 -- pos is on the 2nd half of a dbe char
    """
    if not isinstance(text, bytes):
        raise TypeError(text)
    v = text[pos]

    if 0x40 <= v < 0x7F:
        # might be second half of big5, uhc or gbk encoding
        if pos == line_start:
            return 0

        if text[pos - 1] >= 0x81 and within_double_byte(text, line_start, pos - 1) == 1:
            return 2
        return 0

    if v < 0x80:
        return 0

    i = pos - 1
    while i >= line_start:
        if text[i] < 0x80:
            break
        i -= 1

    if (pos - i) & 1:
        return 1
    return 2
