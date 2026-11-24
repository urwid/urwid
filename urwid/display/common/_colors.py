# Urwid common display code
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


"""Colour names, the 88- and 256-colour palettes, and the parsing and naming of colour descriptions."""

from __future__ import annotations

import functools
import types
import typing

from urwid.util import int_scale

if typing.TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


# AttrSpec internal values
_BASIC_START = 0  # first index of basic color aliases
_CUBE_START = 16  # first index of color cube
_CUBE_SIZE_256 = 6  # one side of the color cube
_GRAY_SIZE_256 = 24
_GRAY_START_256 = _CUBE_SIZE_256**3 + _CUBE_START
_CUBE_WHITE_256 = _GRAY_START_256 - 1
_CUBE_SIZE_88 = 4
_GRAY_SIZE_88 = 8
_GRAY_START_88 = _CUBE_SIZE_88**3 + _CUBE_START
_CUBE_WHITE_88 = _GRAY_START_88 - 1
_CUBE_BLACK = _CUBE_START

# values copied from xterm 256colres.h:
_CUBE_STEPS_256 = [0x00, 0x5F, 0x87, 0xAF, 0xD7, 0xFF]
_GRAY_STEPS_256 = [
    0x08,
    0x12,
    0x1C,
    0x26,
    0x30,
    0x3A,
    0x44,
    0x4E,
    0x58,
    0x62,
    0x6C,
    0x76,
    0x80,
    0x8A,
    0x94,
    0x9E,
    0xA8,
    0xB2,
    0xBC,
    0xC6,
    0xD0,
    0xDA,
    0xE4,
    0xEE,
]
# values copied from xterm 88colres.h:
_CUBE_STEPS_88 = [0x00, 0x8B, 0xCD, 0xFF]
_GRAY_STEPS_88 = [0x2E, 0x5C, 0x73, 0x8B, 0xA2, 0xB9, 0xD0, 0xE7]
# values copied from X11/rgb.txt and XTerm-col.ad:
_BASIC_COLOR_VALUES = (
    (0, 0, 0),
    (205, 0, 0),
    (0, 205, 0),
    (205, 205, 0),
    (0, 0, 238),
    (205, 0, 205),
    (0, 205, 205),
    (229, 229, 229),
    (127, 127, 127),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (0x5C, 0x5C, 0xFF),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
)

_COLOR_VALUES_256: tuple[tuple[int, int, int], ...] = (
    *_BASIC_COLOR_VALUES,
    *[(r, g, b) for r in _CUBE_STEPS_256 for g in _CUBE_STEPS_256 for b in _CUBE_STEPS_256],
    *[(gr, gr, gr) for gr in _GRAY_STEPS_256],
)
_COLOR_VALUES_88: tuple[tuple[int, int, int], ...] = (
    *_BASIC_COLOR_VALUES,
    *[(r, g, b) for r in _CUBE_STEPS_88 for g in _CUBE_STEPS_88 for b in _CUBE_STEPS_88],
    *[(gr, gr, gr) for gr in _GRAY_STEPS_88],
)


if len(_COLOR_VALUES_256) != 256:
    raise RuntimeError(_COLOR_VALUES_256)


if len(_COLOR_VALUES_88) != 88:
    raise RuntimeError(_COLOR_VALUES_88)


DEFAULT = "default"
#: colour keyword taking the colour from the enclosing attribute (:meth:`AttrSpec.layered_over`)
INHERIT = "inherit"
BLACK = "black"
DARK_RED = "dark red"
DARK_GREEN = "dark green"
BROWN = "brown"
DARK_BLUE = "dark blue"
DARK_MAGENTA = "dark magenta"
DARK_CYAN = "dark cyan"
LIGHT_GRAY = "light gray"
DARK_GRAY = "dark gray"
LIGHT_RED = "light red"
LIGHT_GREEN = "light green"
YELLOW = "yellow"
LIGHT_BLUE = "light blue"
LIGHT_MAGENTA = "light magenta"
LIGHT_CYAN = "light cyan"
WHITE = "white"

_BASIC_COLORS = [
    BLACK,
    DARK_RED,
    DARK_GREEN,
    BROWN,
    DARK_BLUE,
    DARK_MAGENTA,
    DARK_CYAN,
    LIGHT_GRAY,
    DARK_GRAY,
    LIGHT_RED,
    LIGHT_GREEN,
    YELLOW,
    LIGHT_BLUE,
    LIGHT_MAGENTA,
    LIGHT_CYAN,
    WHITE,
]
# name -> index, for the O(1) lookup AttrSpec needs on every color it parses
# (_BASIC_COLORS itself is kept for the reverse, index -> name, direction)
_BASIC_COLOR_INDEX = {color: index for index, color in enumerate(_BASIC_COLORS)}


# AttrSpec.__init__() and __set_foreground()/__set_background() are called
# once per colored run of text an application constructs, so these are
# hoisted to module scope rather than re-built as set literals on every call.
_VALID_COLOR_COUNTS = frozenset({1, 16, 88, 256, 2**24})
_DEFAULT_COLOR_NAMES = frozenset({"", "default"})


def _value_lookup_table(values: Sequence[int], size: int) -> list[int]:
    """Generate a lookup table for finding the closest item in *values*.

    :param values: list of values in ascending order, all < size
    :param size: size of lookup table and maximum value
    :returns: one entry per value from 0 to *size* - 1, holding the index into *values* of the closest item.

    >>> _value_lookup_table([0, 7, 9], 10)
    [0, 0, 0, 0, 1, 1, 1, 1, 2, 2]
    """
    middle_values = [0] + [(values[i] + values[i + 1] + 1) // 2 for i in range(len(values) - 1)] + [size]
    lookup_table = []
    for i in range(len(middle_values) - 1):
        count = middle_values[i + 1] - middle_values[i]
        lookup_table.extend([i] * count)
    return lookup_table


_CUBE_256_LOOKUP = _value_lookup_table(_CUBE_STEPS_256, 256)
_GRAY_256_LOOKUP = _value_lookup_table([0, *_GRAY_STEPS_256, 255], 256)
_CUBE_88_LOOKUP = _value_lookup_table(_CUBE_STEPS_88, 256)
_GRAY_88_LOOKUP = _value_lookup_table([0, *_GRAY_STEPS_88, 255], 256)

# convert steps to values that will be used by string versions of the colors
# 1 hex digit for rgb and 0..100 for grayscale
_CUBE_STEPS_256_16 = [int_scale(n, 0x100, 0x10) for n in _CUBE_STEPS_256]
_GRAY_STEPS_256_101 = [int_scale(n, 0x100, 101) for n in _GRAY_STEPS_256]
_CUBE_STEPS_88_16 = [int_scale(n, 0x100, 0x10) for n in _CUBE_STEPS_88]
_GRAY_STEPS_88_101 = [int_scale(n, 0x100, 101) for n in _GRAY_STEPS_88]

# create lookup tables for 1 hex digit rgb and 0..100 for grayscale values
_CUBE_256_LOOKUP_16 = [_CUBE_256_LOOKUP[int_scale(n, 16, 0x100)] for n in range(16)]
_GRAY_256_LOOKUP_101 = [_GRAY_256_LOOKUP[int_scale(n, 101, 0x100)] for n in range(101)]
_CUBE_88_LOOKUP_16 = [_CUBE_88_LOOKUP[int_scale(n, 16, 0x100)] for n in range(16)]
_GRAY_88_LOOKUP_101 = [_GRAY_88_LOOKUP[int_scale(n, 101, 0x100)] for n in range(101)]


# The functions _gray_num_256() and _gray_num_88() do not include the gray
# values from the color cube so that the gray steps are an even width.
# The color cube grays are available by using the rgb functions.  Pure
# white and black are taken from the color cube, since the gray range does
# not include them, and the basic colors are more likely to have been
# customized by an end-user.


def _gray_num_256(gnum: int) -> int:
    """Return ths color number for gray number gnum.

    Color cube black and white are returned for 0 and 25 respectively
    since those values aren't included in the gray scale.

    """
    # grays start from index 1
    gnum -= 1

    if gnum < 0:
        return _CUBE_BLACK
    if gnum >= _GRAY_SIZE_256:
        return _CUBE_WHITE_256
    return _GRAY_START_256 + gnum


def _gray_num_88(gnum: int) -> int:
    """Return ths color number for gray number gnum.

    Color cube black and white are returned for 0 and 9 respectively
    since those values aren't included in the gray scale.

    """
    # gnums start from index 1
    gnum -= 1

    if gnum < 0:
        return _CUBE_BLACK
    if gnum >= _GRAY_SIZE_88:
        return _CUBE_WHITE_88
    return _GRAY_START_88 + gnum


def _color_desc_true(num: int) -> str:
    return f"#{num:06x}"


@functools.lru_cache(maxsize=256)
def _color_desc_256(num: int) -> str:
    """Return a string description of color number *num*.

    0..15 -> 'h0'..'h15' basic colors (as high-colors)
    16..231 -> '#000'..'#fff' color cube colors
    232..255 -> 'g3'..'g93' grays

    >>> _color_desc_256(15)
    'h15'
    >>> _color_desc_256(16)
    '#000'
    >>> _color_desc_256(17)
    '#006'
    >>> _color_desc_256(230)
    '#ffd'
    >>> _color_desc_256(233)
    'g7'
    >>> _color_desc_256(234)
    'g11'

    :raises ValueError: *num* is outside the 256-colour range.

    """
    if not 0 <= num < 256:
        raise ValueError(num)
    if num < _CUBE_START:
        return f"h{num:d}"
    if num < _GRAY_START_256:
        num -= _CUBE_START
        b, num = num % _CUBE_SIZE_256, num // _CUBE_SIZE_256
        g, num = num % _CUBE_SIZE_256, num // _CUBE_SIZE_256
        r = num % _CUBE_SIZE_256
        return f"#{_CUBE_STEPS_256_16[r]:x}{_CUBE_STEPS_256_16[g]:x}{_CUBE_STEPS_256_16[b]:x}"
    return f"g{_GRAY_STEPS_256_101[num - _GRAY_START_256]:d}"


@functools.lru_cache(maxsize=88)
def _color_desc_88(num: int) -> str:
    """Return a string description of color number *num*.

    0..15 -> 'h0'..'h15' basic colors (as high-colors)
    16..79 -> '#000'..'#fff' color cube colors
    80..87 -> 'g18'..'g90' grays

    >>> _color_desc_88(0)
    'h0'
    >>> _color_desc_88(15)
    'h15'
    >>> _color_desc_88(16)
    '#000'
    >>> _color_desc_88(17)
    '#008'
    >>> _color_desc_88(78)
    '#ffc'
    >>> _color_desc_88(81)
    'g36'
    >>> _color_desc_88(82)
    'g45'

    :raises ValueError: *num* is outside the 88-colour range.

    """
    if not 0 <= num < 88:
        raise ValueError(num)
    if num < _CUBE_START:
        return f"h{num:d}"
    if num < _GRAY_START_88:
        num -= _CUBE_START
        b, num = num % _CUBE_SIZE_88, num // _CUBE_SIZE_88
        g, r = num % _CUBE_SIZE_88, num // _CUBE_SIZE_88
        return f"#{_CUBE_STEPS_88_16[r]:x}{_CUBE_STEPS_88_16[g]:x}{_CUBE_STEPS_88_16[b]:x}"
    return f"g{_GRAY_STEPS_88_101[num - _GRAY_START_88]:d}"


@functools.lru_cache(maxsize=512)
def _parse_color_true(desc: str) -> int | None:
    if (c := _parse_color_256(desc)) is not None:
        (r, g, b) = _COLOR_VALUES_256[c]
        return (r << 16) + (g << 8) + b

    if not desc.startswith("#"):
        return None

    if len(desc) == 7:
        h = desc[1:]
        return int(h, 16)

    if len(desc) == 4:
        h = f"0x{desc[1]}0{desc[2]}0{desc[3]}"
        return int(h, 16)

    return None


@functools.lru_cache(maxsize=512)
def _parse_color_256(desc: str) -> int | None:
    """Return a color number for the description *desc*.

    'h0'..'h255' -> 0..255 actual color number
    '#000'..'#fff' -> 16..231 color cube colors
    'g0'..'g100' -> 16, 232..255, 231 grays and color cube black/white
    'g#00'..'g#ff' -> 16, 232...255, 231 gray and color cube black/white

    :returns: None if desc is invalid.

    >>> _parse_color_256("h142")
    142
    >>> _parse_color_256("#f00")
    196
    >>> _parse_color_256("g100")
    231
    >>> _parse_color_256("g#80")
    244
    """
    if len(desc) > 4:
        # keep the length within reason before parsing
        return None
    try:
        if desc.startswith("h"):
            # high-color number
            num = int(desc[1:], 10)
            if num < 0 or num > 255:
                return None
            return num

        if desc.startswith("#") and len(desc) == 4:
            # color-cube coordinates
            if (rgb := int(desc[1:], 16)) >= 0:
                b, rgb = rgb % 16, rgb // 16
                g, r = rgb % 16, rgb // 16
                # find the closest rgb values
                r = _CUBE_256_LOOKUP_16[r]
                g = _CUBE_256_LOOKUP_16[g]
                b = _CUBE_256_LOOKUP_16[b]
                return _CUBE_START + (r * _CUBE_SIZE_256 + g) * _CUBE_SIZE_256 + b

            return None

        # Only remaining possibility is gray value
        if desc.startswith("g#"):
            # hex value 00..ff
            gray = int(desc[2:], 16)  # noqa: FURB166
            if gray < 0 or gray > 255:
                return None
            gray = _GRAY_256_LOOKUP[gray]
        elif desc.startswith("g"):
            # decimal value 0..100
            gray = int(desc[1:], 10)
            if gray < 0 or gray > 100:
                return None
            gray = _GRAY_256_LOOKUP_101[gray]
        else:
            return None
        if gray == 0:
            return _CUBE_BLACK
        gray -= 1
        if gray == _GRAY_SIZE_256:
            return _CUBE_WHITE_256
        return _GRAY_START_256 + gray

    except ValueError:
        return None


@functools.lru_cache(maxsize=512)
def _true_to_256(desc: str) -> str | None:
    if not (desc.startswith("#") and len(desc) == 7):
        return None

    c256 = _parse_color_256("#" + "".join(format(int(x, 16) // 16, "x") for x in (desc[1:3], desc[3:5], desc[5:7])))
    return _color_desc_256(typing.cast("int", c256))  # we control input


@functools.lru_cache(maxsize=512)
def _parse_color_88(desc: str) -> int | None:
    """Return a color number for the description *desc*.

    'h0'..'h87' -> 0..87 actual color number
    '#000'..'#fff' -> 16..79 color cube colors
    'g0'..'g100' -> 16, 80..87, 79 grays and color cube black/white
    'g#00'..'g#ff' -> 16, 80...87, 79 gray and color cube black/white

    :returns: None if desc is invalid.

    >>> _parse_color_88("h142")
    >>> _parse_color_88("h42")
    42
    >>> _parse_color_88("#f00")
    64
    >>> _parse_color_88("g100")
    79
    >>> _parse_color_88("g#80")
    83
    """
    if len(desc) == 7:
        desc = desc[0:2] + desc[3] + desc[5]
    if len(desc) > 4:
        # keep the length within reason before parsing
        return None
    try:
        if desc.startswith("h"):
            # high-color number
            num = int(desc[1:], 10)
            if num < 0 or num > 87:
                return None
            return num

        if desc.startswith("#") and len(desc) == 4:
            # color-cube coordinates
            if (rgb := int(desc[1:], 16)) >= 0:
                b, rgb = rgb % 16, rgb // 16
                g, r = rgb % 16, rgb // 16
                # find the closest rgb values
                r = _CUBE_88_LOOKUP_16[r]
                g = _CUBE_88_LOOKUP_16[g]
                b = _CUBE_88_LOOKUP_16[b]
                return _CUBE_START + (r * _CUBE_SIZE_88 + g) * _CUBE_SIZE_88 + b

            return None

        # Only remaining possibility is gray value
        if desc.startswith("g#"):
            # hex value 00..ff
            gray = int(desc[2:], 16)  # noqa: FURB166
            if gray < 0 or gray > 255:
                return None
            gray = _GRAY_88_LOOKUP[gray]
        elif desc.startswith("g"):
            # decimal value 0..100
            gray = int(desc[1:], 10)
            if gray < 0 or gray > 100:
                return None
            gray = _GRAY_88_LOOKUP_101[gray]
        else:
            return None
        if gray == 0:
            return _CUBE_BLACK
        gray -= 1
        if gray == _GRAY_SIZE_88:
            return _CUBE_WHITE_88
        return _GRAY_START_88 + gray

    except ValueError:
        return None


# the entries a color is approximated with, and their values, by the number of colors a display draws: the first 8
# and all 16 basic colors, and the entries past the basic colors of the 88- and 256-color palettes, which the terminal
# theme does not redefine
_APPROXIMATION_ENTRIES: Mapping[int, Sequence[tuple[int, tuple[int, int, int]]]] = types.MappingProxyType(
    {
        8: tuple(enumerate(_BASIC_COLOR_VALUES[:8])),
        16: tuple(enumerate(_BASIC_COLOR_VALUES)),
        88: tuple(enumerate(_COLOR_VALUES_88))[_CUBE_START:],
        256: tuple(enumerate(_COLOR_VALUES_256))[_CUBE_START:],
    }
)


@functools.lru_cache(maxsize=4096)
def _nearest_color(rgb: tuple[int, int, int], palette: typing.Literal[8, 16, 88, 256]) -> int:
    """Return the entry of *palette* nearest to *rgb*, by the least squared distance of the components.

    The 8 and 16 entries are basic colors; the 88- and 256-color entries are taken from 16 up.
    The first of two equally near entries wins.

    >>> _nearest_color((135, 175, 215), 256), _nearest_color((135, 175, 215), 88), _nearest_color((200, 0, 0), 8)
    (110, 42, 1)
    """
    red, green, blue = rgb
    entry, _value = min(
        _APPROXIMATION_ENTRIES[palette],
        key=lambda item: (item[1][0] - red) ** 2 + (item[1][1] - green) ** 2 + (item[1][2] - blue) ** 2,
    )
    return entry
