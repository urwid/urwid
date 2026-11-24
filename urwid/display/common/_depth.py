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

"""The color channels of an :class:`AttrSpec`, kept by kind from the widget to the display.

A channel is the foreground, the background or the underline color of an attribute.
Its kind says how its number is read: a basic color, an entry of the 88- or the 256-color palette, or an RGB value.
Code that holds a color as a value builds specifications from channels here, so no color mode parses, and so
quantizes, a description of it.
"""

from __future__ import annotations

import enum
import typing

from urwid.display.common._attr_spec import (
    _BG_BASIC_COLOR,
    _BG_HIGH_COLOR,
    _BG_INHERIT,
    _BG_SHIFT,
    _BG_TRUE_COLOR,
    _COLOR_BASIC,
    _COLOR_DEFAULT,
    _COLOR_HIGH,
    _COLOR_KIND_SHIFT,
    _COLOR_TRUE,
    _FG_BASIC_COLOR,
    _FG_COLOR_MASK,
    _FG_HIGH_COLOR,
    _FG_INHERIT,
    _FG_TRUE_COLOR,
    _HIGH_88_COLOR,
    _HIGH_TRUE_COLOR,
    _SETTINGS_MASK,
    AttrSpec,
)
from urwid.display.common._colors import (
    _BASIC_COLOR_VALUES,
    _COLOR_VALUES_88,
    _COLOR_VALUES_256,
    DEFAULT,
    _nearest_color,
)

if typing.TYPE_CHECKING:
    from typing import Literal

    from urwid.display.common._attr_spec import Hyperlink

    _Mode = Literal[88, 256, 16777216]
    #: the colors a display draws: none, the 8 colors of curses pairs, the 16 basic colors, a palette, or any RGB color
    Draws = Literal[1, 8, 16, 88, 256, 16777216]

# this module reads and builds the stored values of AttrSpec, the class it is the color counterpart of
# pylint: disable=protected-access


class Kind(enum.Enum):
    """How the number of a color channel is read."""

    #: the terminal's default color; for an underline, the text color
    DEFAULT = enum.auto()
    #: the color of the enclosing attribute
    INHERIT = enum.auto()
    #: one of the 16 basic colors
    BASIC = enum.auto()
    #: an entry of the 88-color palette, which only an 88-color specification holds
    INDEX_88 = enum.auto()
    #: an entry of the 256-color palette
    INDEX_256 = enum.auto()
    #: a 24-bit value, red in the high byte
    RGB = enum.auto()


class Channel(typing.NamedTuple):
    """One color of an attribute: its kind and its number."""

    kind: Kind
    number: int = 0


#: the default color, and the color of the enclosing attribute
DEFAULT_CHANNEL: typing.Final = Channel(Kind.DEFAULT)
INHERIT_CHANNEL: typing.Final = Channel(Kind.INHERIT)
# the first palette entry past the 16 basic colors, which both palettes share
_PALETTE_START: typing.Final = 16
# the 24-bit value of a channel is three bytes
_RGB_MAX: typing.Final = 0xFFFFFF
# the basic colors 8-15 are the bright versions of 0-7
_BRIGHT_START: typing.Final = 8


def rgb(red: int, green: int, blue: int) -> Channel:
    """Return the channel of a 24-bit color.

    >>> rgb(135, 175, 215)
    Channel(kind=<Kind.RGB: 6>, number=8892375)

    :raises ValueError: a component is outside 0-255.
    """
    if not all(0 <= component <= 0xFF for component in (red, green, blue)):
        raise ValueError(f"RGB components must be 0-255: {(red, green, blue)!r}")
    return Channel(Kind.RGB, (red << 16) | (green << 8) | blue)


def rgb_components(number: int) -> tuple[int, int, int]:
    """Return the red, green and blue components of the 24-bit value *number*.

    >>> rgb_components(0x87AFD7)
    (135, 175, 215)
    """
    return (number >> 16, number >> 8 & 0xFF, number & 0xFF)


def _color_channel(kind_bits: int, number: int, *, basic: int, high: int, true: int, mode_88: bool) -> Channel:
    """Return the channel of a foreground or background color, from the kind flags of that color."""
    if kind_bits & basic:
        return Channel(Kind.BASIC, number)
    if kind_bits & high:
        return Channel(Kind.INDEX_88 if mode_88 else Kind.INDEX_256, number)
    if kind_bits & true:
        return Channel(Kind.RGB, number)
    return DEFAULT_CHANNEL


def channels(spec: AttrSpec) -> tuple[Channel, Channel, Channel]:
    """Return the foreground, background and underline color channels of *spec*.

    The underline channel is :data:`INHERIT_CHANNEL` when *spec* takes it from the enclosing attribute,
    and :data:`DEFAULT_CHANNEL` when it draws the underline in the text color.

    >>> channels(AttrSpec("h196", "#102030", 2**24, underline_color="dark red"))
    (Channel(kind=<Kind.INDEX_256: 5>, number=196), Channel(kind=<Kind.RGB: 6>, number=1056816), \
Channel(kind=<Kind.BASIC: 3>, number=1))
    """
    value = spec._value
    mode_88 = bool(value & _HIGH_88_COLOR)
    if value & _FG_INHERIT:
        foreground = INHERIT_CHANNEL
    else:
        foreground = _color_channel(
            value,
            spec.foreground_number,
            basic=_FG_BASIC_COLOR,
            high=_FG_HIGH_COLOR,
            true=_FG_TRUE_COLOR,
            mode_88=mode_88,
        )
    if value & _BG_INHERIT:
        background = INHERIT_CHANNEL
    else:
        background = _color_channel(
            value,
            spec.background_number,
            basic=_BG_BASIC_COLOR,
            high=_BG_HIGH_COLOR,
            true=_BG_TRUE_COLOR,
            mode_88=mode_88,
        )
    if (line := spec._underline_value) is None:
        underline = INHERIT_CHANNEL
    else:
        kind, number = line >> _COLOR_KIND_SHIFT, line & _FG_COLOR_MASK
        match kind:
            case 0:
                underline = DEFAULT_CHANNEL
            case 1:
                underline = Channel(Kind.BASIC, number)
            case 2:
                underline = Channel(Kind.INDEX_88 if mode_88 else Kind.INDEX_256, number)
            case 3:
                underline = Channel(Kind.RGB, number)
            case _:
                message = f"underline color kind {kind} is none that is stored"
                raise AssertionError(message)
    return foreground, background, underline


def declared_mode(spec: AttrSpec) -> _Mode:
    """Return the color mode *spec* was made for: 88 colors, true color, or else 256 colors."""
    if spec._value & _HIGH_88_COLOR:
        return 88
    if spec._value & _HIGH_TRUE_COLOR:
        return 16777216
    return 256


def promote(channel: Channel) -> Channel:
    """Return *channel* as it is outside 88-color mode.

    An 88-color entry above 15 becomes the RGB value of the 88-color table.
    An entry 0-15, which both palettes share, is kept by number as a 256-color entry.
    Every other channel is returned unchanged.
    """
    if channel.kind is not Kind.INDEX_88:
        return channel
    if channel.number < _PALETTE_START:
        return Channel(Kind.INDEX_256, channel.number)
    return rgb(*_COLOR_VALUES_88[channel.number])


def build(
    foreground: Channel,
    background: Channel,
    underline: Channel,
    *,
    settings: int,
    hyperlink: Hyperlink | None,
    mode: _Mode,
) -> AttrSpec:
    """Return the :class:`AttrSpec` holding the given channels, with no description parsed.

    The color mode follows from the channels where they need one: an 88-color entry needs 88-color mode,
    and an RGB channel needs true color mode.
    Any other set of channels takes *mode*, the mode the result is declared in.
    An 88-color entry beside an RGB channel or a 256-color entry is promoted first, as :func:`promote` does,
    and so is every 88-color entry when *mode* is not 88.

    :param foreground: the foreground channel.
    :param background: the background channel.
    :param underline: the underline channel; :data:`INHERIT_CHANNEL` takes the enclosing one.
    :param settings: the setting bits of the result, as an :class:`AttrSpec` value holds them.
    :param hyperlink: the hyperlink of the result.
    :param mode: the color mode the result is declared in, where its channels do not need another.
    :raises ValueError: a channel's number is outside the range of its kind.
    """
    kinds = {foreground.kind, background.kind, underline.kind}
    if Kind.INDEX_88 in kinds and (mode != 88 or kinds & {Kind.INDEX_256, Kind.RGB}):
        foreground, background, underline = promote(foreground), promote(background), promote(underline)
        kinds = {foreground.kind, background.kind, underline.kind}
    if Kind.RGB in kinds:
        mode = 16777216
    elif Kind.INDEX_88 in kinds:
        mode = 88
    elif mode == 88 and Kind.INDEX_256 in kinds:
        mode = 256
    value = settings & _SETTINGS_MASK
    value |= _HIGH_88_COLOR * (mode == 88) | _HIGH_TRUE_COLOR * (mode == 16777216)
    value |= _encoded(foreground, basic=_FG_BASIC_COLOR, high=_FG_HIGH_COLOR, true=_FG_TRUE_COLOR, inherit=_FG_INHERIT)
    value |= _encoded(
        background,
        basic=_BG_BASIC_COLOR,
        high=_BG_HIGH_COLOR,
        true=_BG_TRUE_COLOR,
        inherit=_BG_INHERIT,
        shift=_BG_SHIFT,
    )
    match underline.kind:
        case Kind.INHERIT:
            line = None
        case Kind.DEFAULT:
            line = _COLOR_DEFAULT << _COLOR_KIND_SHIFT
        case Kind.BASIC:
            line = _COLOR_BASIC << _COLOR_KIND_SHIFT | _checked(underline)
        case Kind.INDEX_88 | Kind.INDEX_256:
            line = _COLOR_HIGH << _COLOR_KIND_SHIFT | _checked(underline)
        case Kind.RGB:
            line = _COLOR_TRUE << _COLOR_KIND_SHIFT | _checked(underline)
        case _:
            typing.assert_never(underline.kind)
    return AttrSpec._from_value(value, line, hyperlink)


def _checked(channel: Channel) -> int:
    """Return the number of *channel*.

    :raises ValueError: the number is outside the range of the channel's kind.
    """
    limit = {Kind.BASIC: 15, Kind.INDEX_88: 87, Kind.INDEX_256: 255, Kind.RGB: _RGB_MAX}.get(channel.kind, 0)
    if not 0 <= channel.number <= limit:
        raise ValueError(f"Color number out of range for its kind: {channel!r}")
    return channel.number


def _encoded(channel: Channel, *, basic: int, high: int, true: int, inherit: int, shift: int = 0) -> int:
    """Return the value bits of a foreground or background channel, given the flags of that side."""
    match channel.kind:
        case Kind.DEFAULT:
            return 0
        case Kind.INHERIT:
            return inherit
        case Kind.BASIC:
            return basic | _checked(channel) << shift
        case Kind.INDEX_88 | Kind.INDEX_256:
            return high | _checked(channel) << shift
        case Kind.RGB:
            return true | _checked(channel) << shift
        case _:
            typing.assert_never(channel.kind)


def replace_channels(
    spec: AttrSpec | None,
    *,
    foreground: Channel | None = None,
    background: Channel | None = None,
    underline: Channel | None = None,
) -> AttrSpec:
    """Return *spec* with the named channels replaced, and every other channel, setting and link kept.

    A channel given as ``None`` is kept with its kind and number.
    No description is parsed, so the given colors are exact whatever the mode of *spec*:
    an RGB channel makes the result a true color specification.
    When the result leaves 88-color mode, the kept 88-color entries are promoted as :func:`promote` does.

    >>> replace_channels(AttrSpec("h1,bold", "dark blue"), background=rgb(1, 2, 3))
    AttrSpec('h1,bold', '#010203', colors=16777216)
    >>> replace_channels(None, foreground=Channel(Kind.INDEX_256, 196))
    AttrSpec('#f00', 'default')

    :param spec: the specification to change; ``None`` stands for the default attribute.
    :param foreground: the new foreground channel.
    :param background: the new background channel.
    :param underline: the new underline channel; :data:`INHERIT_CHANNEL` takes the enclosing one.
    :raises ValueError: a channel's number is outside the range of its kind.
    """
    if spec is None:
        spec = AttrSpec(DEFAULT, DEFAULT)
    kept_foreground, kept_background, kept_underline = channels(spec)
    return build(
        kept_foreground if foreground is None else foreground,
        kept_background if background is None else background,
        kept_underline if underline is None else underline,
        settings=spec._value,
        hyperlink=spec.hyperlink,
        mode=declared_mode(spec),
    )


def compose(inner: AttrSpec, outer: AttrSpec, *, settings: AttrSpec) -> AttrSpec:
    """Return *inner* with its inherited channels taken from *outer*, each channel keeping its kind.

    The result is declared in the larger color mode the two attributes need, as :meth:`AttrSpec.colors` gives it,
    and an 88-color entry that leaves 88-color mode is promoted as :func:`promote` does.

    :param inner: the attribute placed over *outer*.
    :param outer: the enclosing attribute.
    :param settings: a specification holding the settings and the hyperlink of the result; its colors are not read.
    """
    inner_foreground, inner_background, inner_underline = channels(inner)
    outer_foreground, outer_background, outer_underline = channels(outer)
    colors = max(inner.colors, outer.colors)
    return build(
        outer_foreground if inner_foreground.kind is Kind.INHERIT else inner_foreground,
        outer_background if inner_background.kind is Kind.INHERIT else inner_background,
        outer_underline if inner_underline.kind is Kind.INHERIT else inner_underline,
        settings=settings._value,
        hyperlink=settings.hyperlink,
        mode=88 if colors == 88 else 16777216 if colors == 16777216 else 256,
    )


def rgb_values(channel: Channel) -> tuple[int, int, int]:
    """Return the red, green and blue of a color channel, as xterm's default palettes give them."""
    match channel.kind:
        case Kind.BASIC:
            return _BASIC_COLOR_VALUES[channel.number]
        case Kind.INDEX_88:
            return _COLOR_VALUES_88[channel.number]
        case Kind.INDEX_256:
            return _COLOR_VALUES_256[channel.number]
        case Kind.RGB:
            return rgb_components(channel.number)
        case Kind.DEFAULT | Kind.INHERIT:
            message = f"{channel.kind} has no RGB value"
            raise ValueError(message)
        case _:
            typing.assert_never(channel.kind)


def _converted(channel: Channel, draws: Draws) -> Channel:
    """Return *channel* as a display that draws *draws* colors draws it.

    A basic color or a palette entry 0-15 keeps its number wherever the display has it, since the terminal theme
    defines those, and is folded to 0-7 for 8 colors.
    Any other color is approximated by the nearest color the display has, past the 16 basic colors where it has a
    palette.
    """
    if channel.kind in {Kind.DEFAULT, Kind.INHERIT}:
        return channel
    if draws == 1:
        return DEFAULT_CHANNEL
    if channel.kind is Kind.BASIC or (channel.kind is not Kind.RGB and channel.number < _PALETTE_START):
        if draws == 8:
            return Channel(Kind.BASIC, channel.number % _BRIGHT_START)
        if draws == 16 or channel.kind is Kind.BASIC:
            return Channel(Kind.BASIC, channel.number) if draws == 16 else channel
        return Channel(Kind.INDEX_88 if draws == 88 else Kind.INDEX_256, channel.number)
    match draws:
        case 8 | 16:
            return Channel(Kind.BASIC, _nearest_color(rgb_values(channel), draws))
        case 88:
            if channel.kind is Kind.INDEX_88:
                return channel
            return Channel(Kind.INDEX_88, _nearest_color(rgb_values(channel), 88))
        case 256:
            if channel.kind is Kind.INDEX_256:
                return channel
            return Channel(Kind.INDEX_256, _nearest_color(rgb_values(channel), 256))
        case 16777216:
            return promote(channel)
        case _:
            typing.assert_never(draws)


def convert(spec: AttrSpec, draws: Draws) -> AttrSpec:
    """Return *spec* with each color channel converted to what a display drawing *draws* colors draws.

    The settings and the hyperlink are kept.
    *spec* itself is returned when no channel changes.

    >>> convert(AttrSpec("#87afd7", "h22", 2**24), 256)
    AttrSpec('#8ad', '#060')
    >>> convert(AttrSpec("h22", "light red", 88), 2**24)
    AttrSpec('#008bcd', 'light red', colors=16777216)
    >>> convert(AttrSpec("#c80000", "light blue", 2**24), 8)
    AttrSpec('dark red', 'dark blue')
    """
    old = channels(spec)
    new = tuple(_converted(channel, draws) for channel in old)
    mode: _Mode = 88 if draws == 88 else 16777216 if draws == 16777216 else 256
    if new == old and (mode == declared_mode(spec) or draws in {1, 8, 16}):
        return spec
    foreground, background, underline = new
    return build(foreground, background, underline, settings=spec._value, hyperlink=spec.hyperlink, mode=mode)
