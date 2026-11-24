# Urwid SGR parameters of display attributes
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

"""SGR (Select Graphic Rendition) parameters: written from an :class:`AttrSpec`, and read back into one.

The writers, the raw display and the replies of a terminal canvas, order the parameters themselves; this module gives
the parameter of each attribute.
The readers, :mod:`urwid.ansi_parser` and the terminal canvas, apply the parameters a sequence gives.
"""

from __future__ import annotations

import types
import typing

from urwid.display.common import _BASIC_COLORS as BASIC_COLORS
from urwid.display.common import _SETTING_OFF_PREFIX, AttrSpec, _depth
from urwid.display.common import _UNDERLINE_STYLE_NAMES as UNDERLINE_STYLE_NAMES
from urwid.display.common import _UNDERLINE_STYLES as UNDERLINE_STYLE_SETTINGS

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

#: the SGR parameter that turns on each flag of an AttrSpec, in parameter order
FLAGS: typing.Final = (
    ("bold", 1),
    ("faint", 2),
    ("italics", 3),
    ("underline", 4),
    ("blink", 5),
    ("standout", 7),
    ("strikethrough", 9),
)
#: the names of those flags in an AttrSpec foreground
FLAG_NAMES: typing.Final = frozenset(name for name, _code in FLAGS)

# ECMA-48 base codes: 30-37 select a standard foreground colour and 40-47 a background one, 38 and 48 an extended one,
# and aixterm's 90-97 and 100-107 a bright one
_FOREGROUND_BASE: typing.Final = 30
_BACKGROUND_BASE: typing.Final = 40
_EXTENDED_OFFSET: typing.Final = 8
_BRIGHT_OFFSET: typing.Final = 60
# the basic colours 8-15 are the bright versions of 0-7
_BRIGHT_COLORS_START: typing.Final = 8


def color_parameters(attrspec: AttrSpec, *, background: bool, bright_flag: bool = False) -> str | None:
    """Return the SGR parameters that select the foreground or the background colour of *attrspec*.

    A 24-bit colour is written as ``38;2;r;g;b``, a palette entry as ``38;5;n``, and a basic colour as 30-37 or
    90-97; a background alike with 48, 40-47 and 100-107.

    :param attrspec: the attributes to write.
    :param background: select the background colour rather than the foreground one.
    :param bright_flag: write a bright basic colour as the normal one after SGR 1 for a foreground and SGR 5 for a
        background, for a terminal that shows those as bright, instead of as 90-97 or 100-107.
    :returns: the parameters joined with ``;``, or None for the default colour.

    >>> from urwid import AttrSpec
    >>> color_parameters(AttrSpec("light red", "h100", 256), background=False)
    '91'
    >>> color_parameters(AttrSpec("light red", "h100", 256), background=False, bright_flag=True)
    '1;31'
    >>> color_parameters(AttrSpec("light red", "h100", 256), background=True)
    '48;5;100'
    """
    if background:
        base, flag = _BACKGROUND_BASE, 5
        true, high, basic = attrspec.background_true, attrspec.background_high, attrspec.background_basic
        number, first = attrspec.background_number, 3
    else:
        base, flag = _FOREGROUND_BASE, 1
        true, high, basic = attrspec.foreground_true, attrspec.foreground_high, attrspec.foreground_basic
        number, first = attrspec.foreground_number, 0
    if true:
        components = attrspec.get_rgb_values()[first : first + 3]
        return f"{base + _EXTENDED_OFFSET:d};2;{';'.join(str(value) for value in components)}"
    if high:
        return f"{base + _EXTENDED_OFFSET:d};5;{number:d}"
    if not basic:
        return None
    if number < _BRIGHT_COLORS_START:
        return f"{base + number:d}"
    if bright_flag:
        return f"{flag:d};{base + number - _BRIGHT_COLORS_START:d}"
    return f"{base + _BRIGHT_OFFSET + number - _BRIGHT_COLORS_START:d}"


def underline_style_parameter(attrspec: AttrSpec) -> str:
    """Return the SGR parameter of the underline of *attrspec*: ``4`` for a single line, ``4:2`` to ``4:5`` otherwise.

    >>> from urwid import AttrSpec
    >>> underline_style_parameter(AttrSpec("curly underline", "default"))
    '4:3'
    """
    if (style := attrspec.underline_style) in {None, "single"}:
        return "4"
    return f"4:{UNDERLINE_STYLE_NAMES.index(typing.cast('str', style)) + 1:d}"


def underline_color_parameter(attrspec: AttrSpec) -> str | None:
    """Return the SGR parameter of the underline colour of *attrspec*, None when it has none.

    The colour is written with the colon sub-parameters of ECMA-48: ``58:5:n`` for a basic colour or a palette entry,
    and ``58:2::r:g:b`` for a 24-bit one.

    >>> from urwid import AttrSpec
    >>> underline_color_parameter(AttrSpec("underline", "default", 256, underline_color="h196"))
    '58:5:196'
    >>> underline_color_parameter(AttrSpec("underline", "#102030", 2**24, underline_color="h196"))
    '58:5:196'
    """
    line = _depth.channels(attrspec)[2]
    match line.kind:
        case _depth.Kind.INHERIT | _depth.Kind.DEFAULT:
            return None
        case _depth.Kind.RGB:
            return f"58:2::{':'.join(str(component) for component in _depth.rgb_components(line.number))}"
        case _depth.Kind.BASIC | _depth.Kind.INDEX_88 | _depth.Kind.INDEX_256:
            return f"58:5:{line.number:d}"
        case _:
            typing.assert_never(line.kind)


_SGR_ATTR_NAMES: tuple[str, ...] = tuple(name for name, _code in FLAGS)
#: SGR parameter -> the setting it turns on
_SGR_SETS: dict[int, str] = {code: name for name, code in FLAGS}
#: SGR parameter -> the settings it turns off
_SGR_RESETS: dict[int, tuple[str, ...]] = {
    22: ("bold", "faint"),
    23: ("italics",),
    24: ("underline",),
    25: ("blink",),
    27: ("standout",),
    29: ("strikethrough",),
}

#: the SGR codes that take a color as arguments: the foreground, the background and the underline color
_EXTENDED_COLOR_SGR: typing.Final = frozenset((38, 48, 58))
#: the color models of an extended color: a palette index and RGB components
_PALETTE_COLOR_MODEL: typing.Final = 5
_RGB_COLOR_MODEL: typing.Final = 2
#: the parameters an extended color code takes, its own included, by color model
_PALETTE_LENGTH: typing.Final = 3
_RGB_LENGTH: typing.Final = 5
_EXTENDED_COLOR_LENGTHS: typing.Final = types.MappingProxyType(
    {_PALETTE_COLOR_MODEL: _PALETTE_LENGTH, _RGB_COLOR_MODEL: _RGB_LENGTH}
)
#: the SGR code of a single underline, and the underline styles its sub-parameter selects: none, single, double,
#: curly, dotted and dashed
_UNDERLINE_SGR: typing.Final = 4
#: the SGR codes of a double underline, of the underline color, and of the underline in the text color
_DOUBLE_UNDERLINE_SGR: typing.Final = 21
_UNDERLINE_COLOR_SGR: typing.Final = 58
_DEFAULT_UNDERLINE_COLOR_SGR: typing.Final = 59
#: the SGR codes that take sub-parameters, given in a group of their own
_SGR_WITH_ARGUMENTS: typing.Final = _EXTENDED_COLOR_SGR | {_UNDERLINE_SGR}
#: the values of a palette index and of an RGB component
_BYTE_VALUES: typing.Final = range(256)
_UNDERLINE_STYLES: typing.Final = range(6)


def parse_sgr_parameters(body: str) -> list[tuple[int, ...]]:
    """Return the SGR codes of the CSI parameter string *body*, as :func:`split_sgr_parameters` splits them.

    A group of sub-parameters (ECMA-48 5.4.2), a code and its arguments separated by colons, is kept as one code:

    - an extended color, ``38:5:n`` or an RGB color, ``38:2:r:g:b`` or ``38:2:id:r:g:b`` with the color space id
      of ITU T.416, as the code its semicolon form splits into, without the color space id;
    - an underline style, ``4:n`` with n from 0 (none) to 5, as ``(4, n)``;
    - any other group is left out.

    An empty parameter is 0.

    >>> parse_sgr_parameters("1;4:3;38:2::255:0:0;48;5;11")
    [(1,), (4, 3), (38, 2, 255, 0, 0), (48, 5, 11)]
    >>> parse_sgr_parameters("")
    [(0,)]

    :param body: the parameters: digits, separated by ``;`` and ``:``.
    :raises ValueError: a parameter is not a number.
    """
    params: list[int | tuple[int, ...]] = []
    for group in body.split(";"):
        code, *args = (int(param) if param else 0 for param in group.split(":"))
        if not args:
            params.append(code)
        elif code in _EXTENDED_COLOR_SGR and args[0] in _EXTENDED_COLOR_LENGTHS:
            model, *color = args
            # the components after the code and the color model
            length = _EXTENDED_COLOR_LENGTHS[model] - 2
            if model == _RGB_COLOR_MODEL and len(color) == length + 1:
                del color[0]  # the color space id
            if len(color) == length:
                params.append((code, model, *color))
        elif code == _UNDERLINE_SGR and len(args) == 1 and args[0] in _UNDERLINE_STYLES:
            params.append((code, args[0]))
    return split_sgr_parameters(params)


def split_sgr_parameters(params: Sequence[int | tuple[int, ...]]) -> list[tuple[int, ...]]:
    """Split SGR parameters into one tuple per code, with the arguments of an extended color code.

    A tuple among *params* is a code already split, such as a group of sub-parameters, and is kept as it is.
    An extended color code whose color model is unknown, or whose arguments are cut short, is a code of its own,
    and so is each parameter after it.

    >>> split_sgr_parameters([1, 38, 5, 11, 48, 2, 1, 2, 3, (4, 3), 0])
    [(1,), (38, 5, 11), (48, 2, 1, 2, 3), (4, 3), (0,)]
    """
    codes: list[tuple[int, ...]] = []
    idx = 0
    while idx < len(params):
        if isinstance(param := params[idx], tuple):
            codes.append(param)
            idx += 1
            continue
        length = 1
        if param in _EXTENDED_COLOR_SGR and idx + 1 < len(params):
            length = _EXTENDED_COLOR_LENGTHS.get(typing.cast("int", params[idx + 1]), 1)
            if idx + length > len(params) or any(isinstance(arg, tuple) for arg in params[idx : idx + length]):
                length = 1
        codes.append(tuple(typing.cast("Sequence[int]", params[idx : idx + length])))
        idx += length
    return codes


def sgi_params_to_attrspec(
    params: Sequence[int | tuple[int, ...]],
    previous: AttrSpec | None,
    *,
    unset_color: typing.Literal["default", "inherit"] = "default",
    bright_is_bold: bool = True,
) -> AttrSpec | None:
    """Resolve a sequence of SGR (Select Graphic Rendition) numeric parameters against a previous attribute spec.

    Ignore unsupported parameters, and extended colors with an out-of-range value.
    Charset parameters 10-12 are handled by the caller.
    The underline styles are SGR 4:n, n from 0 (none) to 5, and 21 for a double underline, as ECMA-48 defines it.
    The underline color is SGR 58, given as SGR 38 gives a color, and SGR 59 draws the underline in the text color.
    The hyperlink of *previous* is kept, also through SGR 0, since OSC 8 sets it independently of SGR.

    :param params: the SGR numeric parameters to apply, in encounter order;
        a tuple is a code already split, as :func:`parse_sgr_parameters` and :func:`split_sgr_parameters` give it.
    :param previous: the :class:`~urwid.AttrSpec` in effect before ``params`` is applied, or ``None`` if none is
        in effect yet.
    :param unset_color: the color given to a foreground or background no parameter has set, or SGR 39/49/0 reset:
        'default' for the terminal default, 'inherit' for the color of the enclosing attribute.
        With 'inherit', SGR 22/23/24/25/27/29 turn their settings off ('no-bold') rather than leaving them to the
        enclosing attribute, and SGR 0 leaves every setting to it again.
    :param bright_is_bold: whether bold also selects the bright variant of a basic foreground when the attribute
        uses only the 16 basic colors, as on a terminal that draws bold text in bright colors; if false, bold stays
        a setting of its own.
    :returns: the resulting :class:`~urwid.AttrSpec`, or ``None`` for "no attributes".

    >>> sgi_params_to_attrspec([31], None)
    AttrSpec('dark red', 'default')
    >>> sgi_params_to_attrspec([0], AttrSpec("dark red", "default"))
    >>> sgi_params_to_attrspec([31], None, unset_color="inherit")
    AttrSpec('dark red', 'inherit')
    >>> sgi_params_to_attrspec([24], None, unset_color="inherit")
    AttrSpec('inherit,no-underline', 'inherit')
    >>> sgi_params_to_attrspec([31, 1], None)
    AttrSpec('light red,bold', 'default')
    >>> sgi_params_to_attrspec([31, 1], None, bright_is_bold=False)
    AttrSpec('dark red,bold', 'default')
    >>> sgi_params_to_attrspec([(4, 3), 58, 5, 9], None)
    AttrSpec('default,curly underline', 'default', underline_color='light red')
    """
    hyperlink = None if previous is None else previous.hyperlink
    # the style of the underline, as SGR 4:n numbers it minus one, and its color channel
    underline_style = 0
    underline_color = _depth.INHERIT_CHANNEL if previous is None else _depth.promote(_depth.channels(previous)[2])

    attributes: set[str] = set()
    # settings an SGR reset turned off; with 'inherit' colors they stay off over the enclosing attribute
    turned_off: set[str] = set()
    # fg/bg hold a palette index (0-255), or a 0xRRGGBB value when fg_rgb/bg_rgb is set.
    fg_rgb = bg_rgb = False
    if previous is None:
        fg: int | None = None
        bg: int | None = None
        colors: int = 1
    else:
        for name in _SGR_ATTR_NAMES:
            if getattr(previous, name):
                attributes.add(name)
        if previous.underline:
            underline_style = UNDERLINE_STYLE_NAMES.index(typing.cast("str", previous.underline_style))
        turned_off.update(
            part.removeprefix(_SETTING_OFF_PREFIX)
            for part in previous.foreground.split(",")
            if part.startswith(_SETTING_OFF_PREFIX)
        )

        # an 88-color entry above 15 is no 256-color entry, so it is taken as its RGB value
        previous_fg, previous_bg, _previous_line = (_depth.promote(channel) for channel in _depth.channels(previous))
        unset_kinds = {_depth.Kind.DEFAULT, _depth.Kind.INHERIT}
        fg = None if previous_fg.kind in unset_kinds else previous_fg.number
        fg_rgb = previous_fg.kind is _depth.Kind.RGB
        # undo the bold brightening applied below, so it can be reapplied or dropped with the new bold state
        if bright_is_bold and fg is not None and fg >= 8 and previous.colors == 16 and "bold" in attributes:
            fg -= 8

        bg = None if previous_bg.kind in unset_kinds else previous_bg.number
        bg_rgb = previous_bg.kind is _depth.Kind.RGB

        colors = previous.colors
        if fg_rgb or bg_rgb or underline_color.kind is _depth.Kind.RGB:
            colors = 16777216  # 2 ** 24

    for code in split_sgr_parameters(params):
        attr = code[0]
        if len(code) > 1 and attr not in _SGR_WITH_ARGUMENTS:
            # a group parse_sgr_parameters drops, given by the caller
            continue
        if 30 <= attr <= 37:
            fg, fg_rgb = attr - 30, False
            colors = max(16, colors)
        elif 40 <= attr <= 47:
            bg, bg_rgb = attr - 40, False
            colors = max(16, colors)
        elif 90 <= attr <= 97:
            fg, fg_rgb = attr - 90 + 8, False
            colors = max(16, colors)
        elif 100 <= attr <= 107:
            bg, bg_rgb = attr - 100 + 8, False
            colors = max(16, colors)
        elif attr == _DOUBLE_UNDERLINE_SGR or (
            attr == _UNDERLINE_SGR and (len(code) == 1 or (len(code) == 2 and code[1] in _UNDERLINE_STYLES[1:]))
        ):
            # 4, 4:1 to 4:5, and 21: an underline in a style
            attributes.add("underline")
            turned_off.discard("underline")
            underline_style = 1 if attr == _DOUBLE_UNDERLINE_SGR else (code[1] - 1 if len(code) > 1 else 0)
        elif code == (_UNDERLINE_SGR, 0):
            # 4:0, no underline, as SGR 24
            attributes.discard("underline")
            turned_off.add("underline")
        elif attr == _UNDERLINE_COLOR_SGR and code[1:2] == (_PALETTE_COLOR_MODEL,) and len(code) == _PALETTE_LENGTH:
            if (color := code[2]) in _BYTE_VALUES:
                basic = color < len(BASIC_COLORS)
                underline_color = _depth.Channel(_depth.Kind.BASIC if basic else _depth.Kind.INDEX_256, color)
                colors = max(len(BASIC_COLORS) if basic else 256, colors)
        elif attr == _UNDERLINE_COLOR_SGR and code[1:2] == (_RGB_COLOR_MODEL,) and len(code) == _RGB_LENGTH:
            if all(component in _BYTE_VALUES for component in code[2:]):
                underline_color = _depth.rgb(*code[2:])
                colors = 16777216  # 2 ** 24
        elif attr == _DEFAULT_UNDERLINE_COLOR_SGR:
            # the underline in the text color: over an enclosing attribute that says so, else as the terminal starts
            underline_color = _depth.DEFAULT_CHANNEL if unset_color == "inherit" else _depth.INHERIT_CHANNEL
        elif attr in {38, 48} and code[1:2] == (_PALETTE_COLOR_MODEL,) and len(code) == _PALETTE_LENGTH:
            color = code[2]
            if 0 <= color <= 255:
                colors = max(256, colors)
                if attr == 38:
                    fg, fg_rgb = color, False
                else:
                    bg, bg_rgb = color, False
        elif attr in {38, 48} and code[1:2] == (_RGB_COLOR_MODEL,) and len(code) == _RGB_LENGTH:
            if all(0 <= component <= 255 for component in code[2:]):
                color = (code[2] << 16) + (code[3] << 8) + code[4]
                colors = 16777216  # 2 ** 24
                if attr == 38:
                    fg, fg_rgb = color, True
                else:
                    bg, bg_rgb = color, True
        elif attr == 39:
            fg = None
        elif attr == 49:
            bg = None
        elif attr in (10, 11, 12):
            # vterm-only charset/display-control side effects; left to the caller
            pass
        elif len(code) == 1 and attr in _SGR_SETS:
            # an underline style out of range is dropped
            attributes.add(_SGR_SETS[attr])
            turned_off.discard(_SGR_SETS[attr])
        elif attr in _SGR_RESETS:
            attributes.difference_update(_SGR_RESETS[attr])
            turned_off.update(_SGR_RESETS[attr])
        elif attr == 0:
            fg = bg = None
            underline_color = _depth.INHERIT_CHANNEL
            fg_rgb = bg_rgb = False
            colors = 1
            attributes.clear()
            turned_off.clear()

    if bright_is_bold and "bold" in attributes and colors == 16 and fg is not None and fg < 8:
        fg += 8

    def _channel(req_color: int | None, rgb: bool) -> _depth.Channel:
        if req_color is None:
            return _depth.INHERIT_CHANNEL if unset_color == "inherit" else _depth.DEFAULT_CHANNEL
        if rgb:
            return _depth.Channel(_depth.Kind.RGB, req_color)
        # a palette entry 0-15 is a basic color while the attribute uses only the basic colors
        if req_color > 15 or colors == 256:
            return _depth.Channel(_depth.Kind.INDEX_256, req_color)
        return _depth.Channel(_depth.Kind.BASIC, req_color)

    foreground = _channel(fg, fg_rgb)
    background = _channel(bg, bg_rgb)

    if unset_color == "inherit":
        attributes.update(f"{_SETTING_OFF_PREFIX}{name}" for name in turned_off)
    if "underline" in attributes and underline_style:
        attributes.discard("underline")
        attributes.add(UNDERLINE_STYLE_SETTINGS[underline_style - 1])

    unset = _depth.INHERIT_CHANNEL if unset_color == "inherit" else _depth.DEFAULT_CHANNEL
    if (
        not attributes
        and foreground == background == unset
        and hyperlink is None
        and underline_color == _depth.INHERIT_CHANNEL
    ):
        return None

    # the settings, parsed once; the colors are set as channels, so no color mode changes them
    settings = AttrSpec(
        ",".join((unset_color, *sorted(attributes))),
        unset_color,
        16777216 if colors == 16777216 else 256,  # 2 ** 24
        hyperlink=hyperlink,
    )
    return _depth.replace_channels(settings, foreground=foreground, background=background, underline=underline_color)
