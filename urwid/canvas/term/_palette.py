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

"""The palette a :class:`~urwid.canvas.term.TermCanvas` child redefines, and the color specs it is set with."""

from __future__ import annotations

import itertools
import re
import string
import typing

from urwid.display.common import _depth

if typing.TYPE_CHECKING:
    from urwid.display.common import AttrSpec

#: the Linux console's palette entries its default foreground and background are drawn with
_DEFAULT_FOREGROUND_ENTRY: typing.Final = 7
_DEFAULT_BACKGROUND_ENTRY: typing.Final = 0
#: xterm's dynamic colors OSC 10 to 12 set: the default foreground and background, and the cursor color
_DYNAMIC_FOREGROUND: typing.Final = 10
_DYNAMIC_BACKGROUND: typing.Final = 11
_DYNAMIC_CURSOR: typing.Final = 12
#: the last of xterm's dynamic colors, which a chain of colors in OSC 10 to 19 reaches
_LAST_DYNAMIC_COLOR: typing.Final = 19
#: the keys the default foreground and background colors are drawn with while they are no palette entries, as in
#: xterm, where OSC 10 and OSC 11 set them
_FOREGROUND_KEY: typing.Final = "foreground"
_BACKGROUND_KEY: typing.Final = "background"
#: the entries of xterm's palette, which OSC 4 sets: the 256 colors
_XTERM_PALETTE_ENTRIES: typing.Final = 256
#: the most hex digits an X11 color spec gives a component
_MAX_SPEC_DIGITS: typing.Final = 4
_SPEC_HEX_DIGITS: typing.Final = frozenset(string.hexdigits)
#: a component of an ``rgbi:`` color: a decimal number after optional white space, as C's strtod reads one, but
#: without the hexadecimal, infinity and NaN forms
_INTENSITY: typing.Final = re.compile(r"\s*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?", re.ASCII)
#: the linear intensity below which the sRGB transfer function is linear
_SRGB_LINEAR_LIMIT: typing.Final = 0.0031308
#: the white space C's atoi skips before a number
_C_WHITE_SPACE: typing.Final = " \t\n\v\f\r"


def _palette_entry(channel: _depth.Channel, default_entry: int | str | None) -> int | str | None:
    """Return the palette entry a color channel is drawn with, None for a color outside the palette.

    :param default_entry: the entry the default color is drawn with: a palette entry, the key of a dynamic color, or
        None when it is neither.
    """
    match channel.kind:
        case _depth.Kind.BASIC | _depth.Kind.INDEX_88 | _depth.Kind.INDEX_256:
            return channel.number
        case _depth.Kind.DEFAULT:
            return default_entry
        case _depth.Kind.RGB | _depth.Kind.INHERIT:
            return None
        case _:
            typing.assert_never(channel.kind)


def _underline_palette_entry(attr: AttrSpec) -> int | None:
    """Return the palette entry the underline color of *attr* is drawn with, None for a color outside the palette.

    An underline without a color of its own, drawn in the text color, is outside it.
    """
    line = _depth.channels(attr)[2]
    if line.kind in {_depth.Kind.BASIC, _depth.Kind.INDEX_88, _depth.Kind.INDEX_256}:
        return line.number
    return None


def _x11_rgb(spec: str) -> tuple[int, int, int] | None:
    """Return the 8-bit red, green and blue of the X11 color *spec*, or None for a spec of another form.

    The forms read are xterm's numeric ones, whose prefix is case-insensitive:

    - ``rgb:r/g/b``, each component 1 to 4 hex digits, scaled to the full range;
    - ``#rgb``, the components with the same number of hex digits, 1 to 4, as the high bits;
    - ``rgbi:r/g/b``, each component a linear intensity from 0 to 1, encoded with the sRGB transfer function.
      A component outside 0 to 1 is not read.

    In the ``rgb:`` and ``rgbi:`` forms, anything after a ``/`` that follows the third component is ignored, as in
    xterm.
    Color names and the other X11 forms, such as ``CIEXYZ:``, are not read.

    >>> _x11_rgb("rgb:f/8/0"), _x11_rgb("RGB:123/456/789"), _x11_rgb("#f80"), _x11_rgb("#123456789abc")
    ((255, 136, 0), (18, 69, 120), (240, 128, 0), (18, 86, 154))
    >>> _x11_rgb("rgb:1/2/3/4"), _x11_rgb("rgb:1/2/3junk")
    ((17, 34, 51), None)
    >>> _x11_rgb("rgbi:0/0.5/1"), _x11_rgb("RGBI:1e-1/ .25/0.003"), _x11_rgb("rgbi:1.5/0/0")
    ((0, 188, 255), (89, 137, 10), None)
    >>> _x11_rgb("rgb:12/34"), _x11_rgb("#12345"), _x11_rgb("orange")
    (None, None, None)
    """
    lower = spec.lower()
    if lower.startswith("rgb:"):
        components = lower.removeprefix("rgb:").split("/", 3)[:3]
        if len(components) != 3 or not all(
            0 < len(component) <= _MAX_SPEC_DIGITS and _SPEC_HEX_DIGITS.issuperset(component)
            for component in components
        ):
            return None
        red, green, blue = (int(component, 16) * 0xFFFF // (16 ** len(component) - 1) >> 8 for component in components)
        return red, green, blue
    if lower.startswith("rgbi:"):
        parts = lower.removeprefix("rgbi:").split("/", 3)[:3]
        if len(parts) != 3 or not all(_INTENSITY.fullmatch(part) for part in parts):
            return None
        intensities = [float(part) for part in parts]
        if not all(0 <= intensity <= 1 for intensity in intensities):
            return None
        red, green, blue = (
            round(
                255 * (12.92 * intensity if intensity <= _SRGB_LINEAR_LIMIT else 1.055 * intensity ** (1 / 2.4) - 0.055)
            )
            for intensity in intensities
        )
        return red, green, blue
    if lower.startswith("#"):
        digits = lower.removeprefix("#")
        size, rest = divmod(len(digits), 3)
        if rest or not 0 < size <= _MAX_SPEC_DIGITS or not _SPEC_HEX_DIGITS.issuperset(digits):
            return None
        red, green, blue = (
            int(digits[start : start + size], 16) << 4 * (4 - size) >> 8 for start in (0, size, 2 * size)
        )
        return red, green, blue
    return None


def _xterm_color_reply(rgb: tuple[int, int, int]) -> str:
    """Return the color *rgb* as xterm answers a color query with it, 16 bits per component.

    >>> _xterm_color_reply((205, 0, 255))
    'rgb:cdcd/0000/ffff'
    """
    return "rgb:" + "/".join(f"{component:02x}" * 2 for component in rgb)


def _xterm_palette_entry(index: str, *, leading_number: bool) -> int | None:
    """Return the xterm palette entry the decimal *index* of an OSC 4 or OSC 104 names, None outside 0 to 255.

    :param leading_number: read *index* as C's ``atoi`` does, as xterm reads an OSC 4 index: the number after any
        leading white space, 0 without one; otherwise *index* is the number alone.

    >>> [_xterm_palette_entry(index, leading_number=True) for index in ("7", "", "x", " +1", "12y", "-1", "256")]
    [7, 0, 0, 1, 12, None, None]
    >>> [_xterm_palette_entry(index, leading_number=False) for index in ("007", "", "x", " 1", "0" * 5000 + "1")]
    [7, None, None, None, 1]
    """
    if leading_number:
        number = index.lstrip(_C_WHITE_SPACE)
        sign = number[:1] if number[:1] in {"+", "-"} else ""
        digits = "".join(itertools.takewhile(string.digits.__contains__, number[len(sign) :]))
    elif index.isascii() and index.isdecimal():
        sign, digits = "", index
    else:
        return None
    # a number of more significant digits is past 255 and is not converted, so int()'s limit on digits is never reached
    significant = digits.lstrip("0")
    if len(significant) > len(str(_XTERM_PALETTE_ENTRIES)):
        return None
    value = int(sign + (significant or "0")) if digits else 0
    return value if 0 <= value < _XTERM_PALETTE_ENTRIES else None
