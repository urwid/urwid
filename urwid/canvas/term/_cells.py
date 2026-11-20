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

"""Cells of a :class:`~urwid.canvas.term.TermCanvas` screen line, and the helpers that measure and mend them."""

from __future__ import annotations

import functools
import typing

import wcwidth

from urwid import str_util
from urwid.display import AttrSpec
from urwid.display.common import _UNDERLINE_STYLES as UNDERLINE_STYLE_SETTINGS
from urwid.display.escape import ESC

if typing.TYPE_CHECKING:
    from typing import Literal


ESC_B = ESC.encode("ascii")


#: the code points a cell holds at most, which bounds the cost of joining a long run of combining marks; more are
#: dropped
_MAX_CLUSTER_LENGTH: typing.Final = 32


#: the DECCIR rendition bits of the AttrSpec flags, and the SGR parameters DECRSPS sets them with
_RENDITION_BITS: typing.Final = (("bold", 1, 1), ("underline", 2, 4), ("blink", 4, 5), ("standout", 8, 7))


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


def _with_flag(attrspec: AttrSpec | None, flag: str, *, remove: bool = False) -> AttrSpec:
    """Return *attrspec* with the foreground setting *flag*, such as ``standout``, added, or removed with *remove*.

    None stands for the default colours.
    """
    if attrspec is None:
        attrspec = AttrSpec("default", "default")
    attrs = [fg.strip() for fg in attrspec.foreground.split(",")]
    # an underline in a style is the underline setting too
    found = [attr for attr in attrs if attr == flag or (flag == "underline" and attr in UNDERLINE_STYLE_SETTINGS)]
    if found and remove:
        attrs.remove(found[0])
        attrspec = attrspec.copy_modified(fg=",".join(attrs))
    elif not found and not remove:
        attrs.append(flag)
        attrspec = attrspec.copy_modified(fg=",".join(attrs))
    return attrspec
