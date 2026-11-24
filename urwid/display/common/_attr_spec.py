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


"""Display attributes: :class:`AttrSpec`, its packed representation, and hyperlinks."""

from __future__ import annotations

import dataclasses
import enum
import typing

from urwid.display.common._colors import (
    _BASIC_COLOR_INDEX,
    _BASIC_COLORS,
    _COLOR_VALUES_88,
    _COLOR_VALUES_256,
    _DEFAULT_COLOR_NAMES,
    _VALID_COLOR_COUNTS,
    DEFAULT,
    INHERIT,
    _color_desc_88,
    _color_desc_256,
    _color_desc_true,
    _parse_color_88,
    _parse_color_256,
    _parse_color_true,
    _true_to_256,
)

if typing.TYPE_CHECKING:
    from typing import Literal, Self


# fmt: off
_FG_COLOR_MASK =      0x000000ffffff
_BG_COLOR_MASK =      0xffffff000000
_FG_BASIC_COLOR =    0x1000000000000
_FG_HIGH_COLOR =     0x2000000000000
_FG_TRUE_COLOR =     0x4000000000000
_BG_BASIC_COLOR =    0x8000000000000
_BG_HIGH_COLOR =    0x10000000000000
_BG_TRUE_COLOR =    0x20000000000000
_BG_SHIFT = 24
_HIGH_88_COLOR =    0x40000000000000
_HIGH_TRUE_COLOR =  0x80000000000000
_STANDOUT =        0x100000000000000
_UNDERLINE =       0x200000000000000
_BOLD =            0x400000000000000
_BLINK =           0x800000000000000
_ITALICS =        0x1000000000000000
_STRIKETHROUGH =  0x2000000000000000
_FAINT =          0x4000000000000000
_FG_INHERIT =     0x8000000000000000
_BG_INHERIT =    0x10000000000000000
# fmt: on

# a setting turned off explicitly ('no-bold'), kept apart from "not mentioned" in every attribute, as a terminal
# keeps an SGR reset;
# the shift puts the off bits (65-71) above _BG_INHERIT (64)
_SETTING_OFF_SHIFT = 9
_SETTINGS_OFF_MASK = (
    _STANDOUT | _UNDERLINE | _BOLD | _BLINK | _ITALICS | _STRIKETHROUGH | _FAINT
) << _SETTING_OFF_SHIFT
# the style of an underline, above the off bits: 0 for a single one, else its setting's place in _UNDERLINE_STYLES
# plus one
_UNDERLINE_STYLE_SHIFT = 72
_UNDERLINE_STYLE_MASK = 0b111 << _UNDERLINE_STYLE_SHIFT

_FG_MASK = (
    _FG_COLOR_MASK
    | _FG_BASIC_COLOR
    | _FG_HIGH_COLOR
    | _STANDOUT
    | _UNDERLINE
    | _BLINK
    | _BOLD
    | _ITALICS
    | _STRIKETHROUGH
    | _FAINT
    | _FG_INHERIT
    | _SETTINGS_OFF_MASK
    | _UNDERLINE_STYLE_MASK
)
_BG_MASK = _BG_COLOR_MASK | _BG_BASIC_COLOR | _BG_HIGH_COLOR | _BG_INHERIT
_INHERIT_MASK = _FG_INHERIT | _BG_INHERIT
# the flags that give the kind of the foreground color and of the background color
_FG_KIND_MASK = _FG_BASIC_COLOR | _FG_HIGH_COLOR | _FG_TRUE_COLOR | _FG_INHERIT
_BG_KIND_MASK = _BG_BASIC_COLOR | _BG_HIGH_COLOR | _BG_TRUE_COLOR | _BG_INHERIT
# the settings of an attribute: everything but its colors and its color mode
_SETTINGS_MASK = (
    _STANDOUT
    | _UNDERLINE
    | _BOLD
    | _BLINK
    | _ITALICS
    | _STRIKETHROUGH
    | _FAINT
    | _SETTINGS_OFF_MASK
    | _UNDERLINE_STYLE_MASK
)


_ATTRIBUTES = {
    "bold": _BOLD,
    "italics": _ITALICS,
    "underline": _UNDERLINE,
    "blink": _BLINK,
    "standout": _STANDOUT,
    "strikethrough": _STRIKETHROUGH,
    "faint": _FAINT,
}
_SETTING_OFF_PREFIX = "no-"
_ATTRIBUTES_OFF = {f"{_SETTING_OFF_PREFIX}{name}": flag << _SETTING_OFF_SHIFT for name, flag in _ATTRIBUTES.items()}
#: the foreground settings of the underline styles, each also turning the underline on; 'underline' is a single one
_UNDERLINE_STYLES = ("double underline", "curly underline", "dotted underline", "dashed underline")
# setting -> its style bits
_UNDERLINE_STYLE_BITS = {name: (number + 1) << _UNDERLINE_STYLE_SHIFT for number, name in enumerate(_UNDERLINE_STYLES)}
# the names AttrSpec.underline_style returns, by the style number SGR 4:n takes minus one
_UNDERLINE_STYLE_NAMES: tuple[Literal["single", "double", "curly", "dotted", "dashed"], ...] = (
    "single",
    "double",
    "curly",
    "dotted",
    "dashed",
)
# the kinds of a color, as an underline color keeps them above its 24-bit number: the terminal's default, one of the
# 16 basic colors, an 88- or 256-color palette entry, and a 24-bit color
_COLOR_DEFAULT = 0
_COLOR_BASIC = 1
_COLOR_HIGH = 2
_COLOR_TRUE = 3
_COLOR_KIND_SHIFT = 24


# BaseScreen.resolve_attr() memo size: attrs built from AttrSpec instances (ANSI text, terminals) are unbounded
_RESOLVED_ATTRS_LIMIT = 4096
# urwid's own caps on Hyperlink fields: VTE and iTerm2 refuse longer URIs, and VTE refuses longer ids
_HYPERLINK_URI_MAX_LEN = 2083
_HYPERLINK_ID_MAX_LEN = 250


class AttrSpecError(Exception):
    """Raised when an :class:`AttrSpec` is constructed with an invalid color specification."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class Hyperlink:
    """Terminal hyperlink (OSC 8) carried by an :class:`AttrSpec`.

    The fields keep the names of the OSC 8 specification.
    Only printable ASCII is accepted, so a link cannot inject other escape sequences.
    The URI is limited to 2083 characters and the id to 250: these are urwid's compatibility limits,
    taken from the terminals that refuse longer values (VTE and iTerm2 for the URI, VTE for the id).
    The specification itself sets no limit.

    An empty URI is the explicit "no link" state, :data:`NO_HYPERLINK`:
    it hides the link of an enclosing attribute.

    :param uri: the link target
    :param id: groups the cells of one link that the terminal highlights together,
        when the link is drawn in several separate runs
    :raises ValueError: *uri* or *id* holds a character outside printable ASCII or is too long,
        *id* holds ``:`` or ``;``, or *id* is given with an empty *uri*.

    >>> Hyperlink("https://urwid.org", id="home")
    Hyperlink(uri='https://urwid.org', id='home')
    """

    uri: str
    _: dataclasses.KW_ONLY
    id: str = ""

    def __post_init__(self) -> None:
        """Validate the fields as the class docstring describes."""
        for name, value, limit in (
            ("uri", self.uri, _HYPERLINK_URI_MAX_LEN),
            ("id", self.id, _HYPERLINK_ID_MAX_LEN),
        ):
            if not (value.isascii() and value.isprintable()):
                raise ValueError(f"Hyperlink {name} must be printable ASCII: {value!r}")
            if len(value) > limit:
                raise ValueError(
                    f"Hyperlink {name} is {len(value):d} characters long, "
                    f"over urwid's compatibility limit of {limit:d}, as some terminals refuse longer values"
                )
        if ":" in self.id or ";" in self.id:
            raise ValueError(f"Hyperlink id must not contain ':' or ';': {self.id!r}")
        if not self.uri and self.id:
            raise ValueError(f"Hyperlink id {self.id!r} given without a URI")


#: hyperlink of an attribute that hides the link of the enclosing attribute
NO_HYPERLINK = Hyperlink("")


class _Keep(enum.Enum):
    """Default of :meth:`AttrSpec.copy_modified` arguments for which ``None`` is a real value."""

    KEEP = enum.auto()


class AttrSpec:
    """Text attribute specification, encoding foreground and background colors and display settings."""

    __slots__ = ("__hash_value", "__hyperlink", "__underline_color", "__value")

    def __init__(
        self,
        fg: str = INHERIT,
        bg: str = INHERIT,
        colors: Literal[1, 16, 88, 256, 16777216] = 256,
        *,
        hyperlink: Hyperlink | str | None = None,
        underline_color: str | None = None,
    ) -> None:
        """
        :param fg: a string containing a comma-separated foreground color and settings

              Color values:
              'default' (use the terminal's default foreground),
              'inherit' (take the color from the enclosing attribute, see :meth:`layered_over`),
              'black', 'dark red', 'dark green', 'brown', 'dark blue',
              'dark magenta', 'dark cyan', 'light gray', 'dark gray',
              'light red', 'light green', 'yellow', 'light blue',
              'light magenta', 'light cyan', 'white'

              High-color example values:
              '#009' (0% red, 0% green, 60% red, like HTML colors)
              '#23facc' (RRGGBB hex color code)
              '#fcc' (100% red, 80% green, 80% blue)
              'g40' (40% gray, decimal), 'g#cc' (80% gray, hex),
              '#000', 'g0', 'g#00' (black),
              '#fff', 'g100', 'g#ff' (white)
              'h8' (color number 8), 'h255' (color number 255);
              with 2**24 colors 'hN' is kept as palette entry N, and the cube and gray forms are 24-bit colors

              Setting:
              'bold', 'italics', 'underline', 'blink', 'standout', 'strikethrough', 'faint';
              with 'no-' in front ('no-bold') a setting is turned off rather than taken from the
              enclosing attribute; it is part of the attribute, so 'red,no-bold' and 'red' are unequal.
              'double underline', 'curly underline', 'dotted underline' and 'dashed underline' are an
              underline in that style, which a terminal without underline styles draws as 'underline'

              Some terminals use 'bold' for bright colors.
              Most terminals ignore the 'blink' setting.
              If the color is not given then 'default' will be assumed.

        :param bg: a string containing the background color

              Color values:
              'default' (use the terminal's default background),
              'inherit' (take the color from the enclosing attribute),
              'black', 'dark red', 'dark green', 'brown', 'dark blue',
              'dark magenta', 'dark cyan', 'light gray'

              High-color exaples:
              see fg examples above

              An empty string will be treated the same as 'default'.

        :param colors: the maximum colors available for the specification

                   Valid values include: 1, 16, 88, 256, and 2**24.  High-color
                   values are only usable with 88, 256, or 2**24 colors.  With
                   1 color only the foreground settings may be used.
                   Any display draws the result: a color it does not have is drawn as the nearest one it has.

        :param hyperlink: the terminal hyperlink of the text, a string being its URI;
            ``None`` takes the link of the enclosing attribute, and :data:`NO_HYPERLINK` hides it.
        :param underline_color: the color of the underline, given as a background color is;
            ``None`` and 'inherit' take it from the enclosing attribute, and 'default' draws it in the text color.
            A terminal without underline colors draws it in the text color.
        :raises AttrSpecError: *colors* is not a supported palette size.
            *fg*, *bg* or *underline_color* is invalid, or needs more colours than *colors*.
        :raises ValueError: *hyperlink* is a string that is not a valid :class:`Hyperlink` URI.

        >>> AttrSpec("dark red", "light gray", 16)
        AttrSpec('dark red', 'light gray')
        >>> AttrSpec("yellow, underline, bold", "dark blue")
        AttrSpec('yellow,bold,underline', 'dark blue')
        >>> AttrSpec("#ddb", "#004", 256)  # closest colors will be found
        AttrSpec('#dda', '#006')
        >>> AttrSpec("#ddb", "#004", 88)
        AttrSpec('#ccc', '#000', colors=88)
        >>> AttrSpec("inherit,bold", "dark blue")
        AttrSpec('inherit,bold', 'dark blue')
        >>> AttrSpec(hyperlink="https://urwid.org")
        AttrSpec('inherit', 'inherit', hyperlink=Hyperlink(uri='https://urwid.org', id=''))
        >>> AttrSpec("default,curly underline", "default", underline_color="light red")
        AttrSpec('default,curly underline', 'default', underline_color='light red')
        """
        if colors not in _VALID_COLOR_COUNTS:
            raise AttrSpecError(f"invalid number of colors ({colors:d}).")
        self.__value = 0 | _HIGH_88_COLOR * (colors == 88) | _HIGH_TRUE_COLOR * (colors == 2**24)
        self.__set_foreground(fg)
        self.__set_background(bg)
        self.__underline_color: int | None = None
        if underline_color is not None and underline_color != INHERIT:
            number, kind = self.__parse_color(underline_color)
            if number is None:
                message = f"Unrecognised color specification in underline color ({underline_color!r})"
                raise AttrSpecError(message)
            self.__underline_color = kind << _COLOR_KIND_SHIFT | number
        if self.colors > colors:
            raise AttrSpecError(
                f"foreground/background/underline ({fg!r}/{bg!r}/{underline_color!r}) require more colors than have "
                f"been specified ({colors:d})."
            )
        self.__hyperlink = Hyperlink(hyperlink) if isinstance(hyperlink, str) else hyperlink
        # attributes that differ only in their underline colors share a hash, and __eq__ tells them apart
        self.__hash_value = hash((self.__class__, self.__value, self.__hyperlink))

    def copy_modified(
        self,
        fg: str | None = None,
        bg: str | None = None,
        colors: Literal[1, 16, 88, 256, 16777216] | None = None,
        *,
        hyperlink: Hyperlink | str | Literal[_Keep.KEEP] | None = _Keep.KEEP,
        underline_color: str | Literal[_Keep.KEEP] | None = _Keep.KEEP,
    ) -> Self:
        """Return a new :class:`AttrSpec`, replacing *fg*, *bg*, *colors*, *hyperlink* and/or *underline_color*.

        Without *colors*, the result uses 88 colors or true color when this specification was made for them,
        else 256 colors, so a color can be added to a specification that has none.
        A given color is parsed in the color mode of the result.
        A color that is not given keeps its kind and number, a palette entry included.
        Only when *colors* names a mode that cannot hold it, it is converted as that mode parses its description:
        approximated at 256 and 88 colors, and an 88-color entry above 15 becomes its RGB value at true color.
        The hyperlink and the underline color are kept unless given; ``None`` makes the result take the enclosing one.

        The result is built with this object's class.
        The *hyperlink* and *underline_color* keywords are passed to its constructor only when the result has them,
        so a subclass whose constructor takes only *fg*, *bg* and *colors* works for every other change.

        :raises AttrSpecError: *colors* is not a supported palette size, or *fg*, *bg* or *underline_color* is invalid
            or needs more colors than the result has.
            A kept color that *colors* cannot hold, such as a palette entry with 16 colors, raises as well.
        :raises ValueError: *hyperlink* is a string that is not a valid :class:`Hyperlink` URI.
        :raises TypeError: the result has a link or an underline color, and the constructor of this object's class does
            not accept it.

        >>> AttrSpec("inherit,bold", "inherit").copy_modified(bg="dark blue")
        AttrSpec('inherit,bold', 'dark blue')
        >>> AttrSpec(hyperlink="https://urwid.org").copy_modified(hyperlink=None)
        AttrSpec('inherit', 'inherit')
        """
        new_colors = self.__color_mode() if colors is None else colors
        if fg is None:
            foreground = (
                self.__kept_color(self.__value & _FG_KIND_MASK, self.foreground_number, new_colors)
                + self.foreground[len(self._foreground_color()) :]
            )
        else:
            foreground = fg

        if bg is None:
            background = self.__kept_color(self.__value & _BG_KIND_MASK, self.background_number, new_colors)
        else:
            background = bg

        extra: dict[str, typing.Any] = {}
        if (link := self.__hyperlink if hyperlink is _Keep.KEEP else hyperlink) is not None:
            extra["hyperlink"] = link
        if underline_color is _Keep.KEEP:
            line = None if self.__underline_color is None else self.__kept_underline_color(new_colors)
        else:
            line = underline_color
        if line is not None:
            extra["underline_color"] = line
        return self.__class__(foreground, background, new_colors, **extra)

    def __kept_color(self, bits: int, number: int, colors: int) -> str:
        """Return the description of a kept foreground or background color for a result in color mode *colors*.

        :param bits: this specification's value masked to the kind flags of the foreground or the background.
        :param number: the color number of that field.
        """
        if bits & _INHERIT_MASK:
            return INHERIT
        if bits & (_FG_BASIC_COLOR | _BG_BASIC_COLOR):
            return _BASIC_COLORS[number]
        if bits & (_FG_HIGH_COLOR | _BG_HIGH_COLOR):
            return self.__kept_high_color(number, colors)
        if bits & (_FG_TRUE_COLOR | _BG_TRUE_COLOR):
            return _color_desc_true(number)
        return DEFAULT

    def __kept_underline_color(self, colors: int) -> str:
        """Return the description of the kept underline color for a result in color mode *colors*."""
        line = typing.cast("int", self.__underline_color)
        if line >> _COLOR_KIND_SHIFT == _COLOR_HIGH:
            return self.__kept_high_color(line & _FG_COLOR_MASK, colors)
        return typing.cast("str", self.underline_color)

    def __kept_high_color(self, number: int, colors: int) -> str:
        """Return the description of palette entry *number* that a result in color mode *colors* parses.

        A true color result keeps the entry, and an 88-color entry above 15 becomes its RGB value.
        Any other mode parses the description of the entry in this specification's palette, as an approximation
        where that mode has another palette.
        """
        if colors != 2**24:
            return _color_desc_88(number) if self.__value & _HIGH_88_COLOR else _color_desc_256(number)
        if self.__value & _HIGH_88_COLOR and number >= 16:
            red, green, blue = _COLOR_VALUES_88[number]
            return _color_desc_true((red << 16) + (green << 8) + blue)
        return f"h{number:d}"

    def __color_mode(self) -> Literal[88, 256, 16777216]:
        """Return the color mode this specification was made for: 88 colors, true color, or else 256 colors."""
        if self.__value & _HIGH_88_COLOR:
            return 88
        if self.__value & _HIGH_TRUE_COLOR:
            return 16777216
        return 256

    def __hash__(self) -> int:
        """Instance is immutable and hashable."""
        return self.__hash_value

    @property
    def _value(self) -> int:
        """Read-only value access."""
        return self.__value

    @property
    def _underline_value(self) -> int | None:
        """Return the stored underline color: its kind above its 24-bit number, ``None`` for the enclosing one."""
        return self.__underline_color

    @classmethod
    def _from_value(cls, value: int, underline_color: int | None, hyperlink: Hyperlink | None) -> AttrSpec:
        """Return a plain :class:`AttrSpec` holding the stored *value*, *underline_color* and *hyperlink* as they are.

        The caller builds valid values: no description is parsed, so no color mode can change a color.
        """
        spec = object.__new__(AttrSpec)
        spec.__value = value
        spec.__underline_color = underline_color
        spec.__hyperlink = hyperlink
        spec.__hash_value = hash((AttrSpec, value, hyperlink))
        return spec

    @property
    def hyperlink(self) -> Hyperlink | None:
        """Return the terminal hyperlink, ``None`` when it is taken from the enclosing attribute."""
        return self.__hyperlink

    def style_only(self) -> AttrSpec:
        """Return this attribute without its hyperlink, for code that only draws colors and settings.

        >>> AttrSpec("yellow", "dark blue", hyperlink="https://urwid.org").style_only()
        AttrSpec('yellow', 'dark blue')
        """
        if self.__hyperlink is None:
            return self
        return self.copy_modified(hyperlink=None)

    @property
    def foreground_basic(self) -> bool:
        """Return whether the foreground color is one of the 16 basic colors."""
        return self.__value & _FG_BASIC_COLOR != 0

    @property
    def foreground_high(self) -> bool:
        """Return whether the foreground color is a 88- or 256-color palette entry."""
        return self.__value & _FG_HIGH_COLOR != 0

    @property
    def foreground_true(self) -> bool:
        """Return whether the foreground color is a 24-bit true color."""
        return self.__value & _FG_TRUE_COLOR != 0

    @property
    def foreground_number(self) -> int:
        """Return the encoded foreground color number."""
        return self.__value & _FG_COLOR_MASK

    @property
    def foreground_inherit(self) -> bool:
        """Return whether the foreground color is taken from the enclosing attribute."""
        return self.__value & _FG_INHERIT != 0

    @property
    def background_basic(self) -> bool:
        """Return whether the background color is one of the 16 basic colors."""
        return self.__value & _BG_BASIC_COLOR != 0

    @property
    def background_high(self) -> bool:
        """Return whether the background color is a 88- or 256-color palette entry."""
        return self.__value & _BG_HIGH_COLOR != 0

    @property
    def background_true(self) -> bool:
        """Return whether the background color is a 24-bit true color."""
        return self.__value & _BG_TRUE_COLOR != 0

    @property
    def background_number(self) -> int:
        """Return the encoded background color number."""
        return (self.__value & _BG_COLOR_MASK) >> _BG_SHIFT

    @property
    def background_inherit(self) -> bool:
        """Return whether the background color is taken from the enclosing attribute."""
        return self.__value & _BG_INHERIT != 0

    @property
    def italics(self) -> bool:
        """Return whether the italics setting is enabled."""
        return self.__value & _ITALICS != 0

    @property
    def bold(self) -> bool:
        """Return whether the bold setting is enabled."""
        return self.__value & _BOLD != 0

    @property
    def underline(self) -> bool:
        """Return whether the underline setting is enabled."""
        return self.__value & _UNDERLINE != 0

    @property
    def underline_style(self) -> Literal["single", "double", "curly", "dotted", "dashed"] | None:
        """Return the style of the underline, or ``None`` without an underline.

        >>> AttrSpec("default,curly underline", "default").underline_style
        'curly'
        """
        if not self.underline:
            return None
        return _UNDERLINE_STYLE_NAMES[(self.__value & _UNDERLINE_STYLE_MASK) >> _UNDERLINE_STYLE_SHIFT]

    @property
    def underline_color(self) -> str | None:
        """Return the underline color, 'default' for the text color, or ``None`` when the enclosing one is taken."""
        if self.__underline_color is None:
            return None
        kind, number = self.__underline_color >> _COLOR_KIND_SHIFT, self.__underline_color & _FG_COLOR_MASK
        match kind:
            case 0:
                return DEFAULT
            case 1:
                return _BASIC_COLORS[number]
            case 2:
                return self.__high_color_desc(number)
            case 3:
                return _color_desc_true(number)
            case _:
                message = f"underline color kind {kind} is none that is stored"
                raise AssertionError(message)

    def underline_rgb_values(self) -> tuple[int, int, int] | None:
        """Return the ``(red, green, blue)`` components of the underline color, each 0-255.

        Values are taken from the XTerm defaults, as :meth:`get_rgb_values` takes them.

        :returns: the components, or ``None`` when the underline takes the text color or the enclosing color.

        >>> AttrSpec(underline_color="#ccf", colors=88).underline_rgb_values()
        (205, 205, 255)
        """
        if not self.__underline_color or not self.__underline_color >> _COLOR_KIND_SHIFT:
            return None
        kind, number = self.__underline_color >> _COLOR_KIND_SHIFT, self.__underline_color & _FG_COLOR_MASK
        if kind == _COLOR_TRUE:
            return (number >> 16, number >> 8 & 0xFF, number & 0xFF)
        if kind == _COLOR_HIGH and self.__value & _HIGH_88_COLOR:
            return _COLOR_VALUES_88[number]
        return _COLOR_VALUES_256[number]

    @property
    def blink(self) -> bool:
        """Return whether the blink setting is enabled."""
        return self.__value & _BLINK != 0

    @property
    def standout(self) -> bool:
        """Return whether the standout setting is enabled."""
        return self.__value & _STANDOUT != 0

    @property
    def strikethrough(self) -> bool:
        """Return whether the strikethrough setting is enabled."""
        return self.__value & _STRIKETHROUGH != 0

    @property
    def faint(self) -> bool:
        """Return whether the faint setting is enabled."""
        return self.__value & _FAINT != 0

    @property
    def colors(self) -> Literal[1, 16, 88, 256, 16777216]:
        """
        Return the maximum colors required for this object.

        Returns 16777216, 256, 88, 16 or 1.
        """
        line_kind = (self.__underline_color or 0) >> _COLOR_KIND_SHIFT
        if self.__value & _HIGH_88_COLOR:
            return 88
        if self.__value & (_BG_TRUE_COLOR | _FG_TRUE_COLOR) or line_kind == _COLOR_TRUE:
            return 16777216  # we have to return explicit 2**24 instead of inline calculation
        if self.__value & (_BG_HIGH_COLOR | _FG_HIGH_COLOR) or line_kind == _COLOR_HIGH:
            return 256
        if self.__value & (_BG_BASIC_COLOR | _FG_BASIC_COLOR) or line_kind == _COLOR_BASIC:
            return 16
        return 1

    def __repr__(self) -> str:
        """Return an executable python representation of the AttrSpec object."""
        args = f"{self.foreground!r}, {self.background!r}"
        if (mode := self.__color_mode()) != 256:
            # the descriptions of the getters are parsed back in the mode the specification was made for
            args = f"{args}, colors={mode:d}"
        if self.__hyperlink is not None:
            args = f"{args}, hyperlink={self.__hyperlink!r}"
        if self.__underline_color is not None:
            args = f"{args}, underline_color={self.underline_color!r}"
        return f"{self.__class__.__name__}({args})"

    def _foreground_color(self) -> str:
        """Return only the color component of the foreground."""
        if self.foreground_inherit:
            return INHERIT
        if not (self.foreground_basic or self.foreground_high or self.foreground_true):
            return "default"
        if self.foreground_basic:
            return _BASIC_COLORS[self.foreground_number]
        if self.foreground_true:
            return _color_desc_true(self.foreground_number)
        return self.__high_color_desc(self.foreground_number)

    def __high_color_desc(self, number: int) -> str:
        """Return the description of palette entry *number*, which parses back to it in this specification's mode.

        In true color mode it is ``hN``, since a cube or gray description would parse as a 24-bit color there.
        """
        if self.__value & _HIGH_88_COLOR:
            return _color_desc_88(number)
        if self.__value & _HIGH_TRUE_COLOR:
            return f"h{number:d}"
        return _color_desc_256(number)

    @property
    def foreground(self) -> str:
        """Return the foreground color and settings as a comma-separated string."""
        return (
            self._foreground_color()
            + ",bold" * self.bold
            + ",italics" * self.italics
            + ",standout" * self.standout
            + ",blink" * self.blink
            + f",{self.__underline_setting()}" * self.underline
            + ",strikethrough" * self.strikethrough
            + ",faint" * self.faint
            + "".join(f",{name}" for name, flag in _ATTRIBUTES_OFF.items() if self.__value & flag)
        )

    def __underline_setting(self) -> str:
        """Return the foreground setting of the underline: 'underline', or the setting of its style."""
        style = (self.__value & _UNDERLINE_STYLE_MASK) >> _UNDERLINE_STYLE_SHIFT
        return _UNDERLINE_STYLES[style - 1] if style else "underline"

    def __set_foreground(self, foreground: str) -> None:
        """
        Parse and store the foreground colour and settings.

        :raises AttrSpecError: *foreground* names an unrecognised colour, repeats a setting, or gives more than one
            colour.
        """
        color = None
        scolor: int | None
        flags = 0
        # handle comma-separated foreground
        for part in foreground.split(","):
            part = part.strip()  # noqa: PLW2901
            if (style_bits := _UNDERLINE_STYLE_BITS.get(part)) is not None:
                # an underline in a style: the underline setting, with its style
                if flags & (_UNDERLINE | _UNDERLINE << _SETTING_OFF_SHIFT):
                    message = f"Setting {part!r} repeats or contradicts another in foreground ({foreground!r})"
                    raise AttrSpecError(message)
                flags |= _UNDERLINE | style_bits
                continue
            if (on_flag := _ATTRIBUTES.get(part.removeprefix(_SETTING_OFF_PREFIX))) is not None:
                # parse and store "settings"/attributes in flags, a setting and its "no-" form being one setting
                off_flag = on_flag << _SETTING_OFF_SHIFT
                attribute_flag = off_flag if part.startswith(_SETTING_OFF_PREFIX) else on_flag
                if flags & (on_flag | off_flag):
                    raise AttrSpecError(
                        f"Setting {part!r} repeats or contradicts another in foreground ({foreground!r})"
                    )
                flags |= attribute_flag
                continue
            # past this point we must be specifying a color
            if part == INHERIT:
                scolor = 0
                flags |= _FG_INHERIT
            else:
                scolor, kind = self.__parse_color(part)
                flags |= (0, _FG_BASIC_COLOR, _FG_HIGH_COLOR, _FG_TRUE_COLOR)[kind]
            # _parse_color_*() return None for unrecognized colors
            if scolor is None:
                raise AttrSpecError(f"Unrecognised color specification {part!r} in foreground ({foreground!r})")
            if color is not None:
                raise AttrSpecError(f"More than one color given for foreground ({foreground!r})")
            color = scolor
        if color is None:
            color = 0
        self.__value = (self.__value & ~_FG_MASK) | color | flags

    @property
    def background(self) -> str:
        """Return the background color."""
        if self.background_inherit:
            return INHERIT
        if not (self.background_basic or self.background_high or self.background_true):
            return "default"
        if self.background_basic:
            return _BASIC_COLORS[self.background_number]
        if self.background_true:
            return _color_desc_true(self.background_number)
        return self.__high_color_desc(self.background_number)

    def __set_background(self, background: str) -> None:
        """
        Parse and store the background colour.

        :raises AttrSpecError: *background* names an unrecognised colour.
        """
        color: int | None
        if background == INHERIT:
            color, flags = 0, _BG_INHERIT
        else:
            color, kind = self.__parse_color(background)
            flags = (0, _BG_BASIC_COLOR, _BG_HIGH_COLOR, _BG_TRUE_COLOR)[kind]
        if color is None:
            raise AttrSpecError(f"Unrecognised color specification in background ({background!r})")
        self.__value = (self.__value & ~_BG_MASK) | (color << _BG_SHIFT) | flags

    def __parse_color(self, color: str) -> tuple[int | None, int]:
        """Return the number and the kind of *color*, a color other than 'inherit', in this specification's mode.

        :returns: the number, ``None`` when *color* is not recognised, and one of the ``_COLOR_*`` kinds.
        """
        if color in _DEFAULT_COLOR_NAMES:
            return 0, _COLOR_DEFAULT
        if (basic_color := _BASIC_COLOR_INDEX.get(color)) is not None:
            return basic_color, _COLOR_BASIC
        if self.__value & _HIGH_88_COLOR:
            return _parse_color_88(color), _COLOR_HIGH
        if self.__value & _HIGH_TRUE_COLOR:
            # a palette entry keeps its slot, which the terminal may have redefined
            if color.startswith("h") and (index := _parse_color_256(color)) is not None:
                return index, _COLOR_HIGH
            return _parse_color_true(color), _COLOR_TRUE
        return _parse_color_256(_true_to_256(color) or color), _COLOR_HIGH

    def get_rgb_values(self) -> tuple[int | None, int | None, int | None, int | None, int | None, int | None]:
        """Return ``(fg_red, fg_green, fg_blue, bg_red, bg_green, bg_blue)`` color components.

        Each component is in the range 0-255.
        Values are taken from the XTerm defaults and may not exactly match the user's terminal.

        If the foreground or background is 'default' or 'inherit' then all their components will be returned as None.

        >>> AttrSpec("yellow", "#ccf", colors=88).get_rgb_values()
        (255, 255, 0, 205, 205, 255)
        >>> AttrSpec("default", "g92").get_rgb_values()
        (None, None, None, 238, 238, 238)

        :raises ValueError: this AttrSpec holds a colour number outside the 88-colour range.
        """
        fg_red, fg_green, fg_blue = self.__rgb_values(
            self.foreground_number,
            basic=self.foreground_basic,
            high=self.foreground_high,
            true=self.foreground_true,
        )
        bg_red, bg_green, bg_blue = self.__rgb_values(
            self.background_number,
            basic=self.background_basic,
            high=self.background_high,
            true=self.background_true,
        )
        return (fg_red, fg_green, fg_blue, bg_red, bg_green, bg_blue)

    def __rgb_values(
        self,
        number: int,
        *,
        basic: bool,
        high: bool,
        true: bool,
    ) -> tuple[int, int, int] | tuple[None, None, None]:
        """Return the components of one color of the given kind, ``None`` for each of a default or inherited one.

        :raises ValueError: an 88-color specification holds a number outside the 88-color range.
        """
        if true:
            return (number >> 16, number >> 8 & 0xFF, number & 0xFF)
        if not (basic or high):
            return (None, None, None)
        if self.__value & _HIGH_88_COLOR:
            if number >= 88:
                raise ValueError(f"Invalid AttrSpec _value: {number!r}")
            return _COLOR_VALUES_88[number]
        return _COLOR_VALUES_256[number]

    def layered_over(
        self,
        outer: AttrSpec,
        *,
        colors: Literal[1, 16, 88, 256, 16777216] | None = None,
    ) -> AttrSpec:
        """Return this attribute with its 'inherit' colors and its missing hyperlink taken from *outer*.

        An attribute with no 'inherit' color is opaque: its colors and settings are kept,
        and only an underline color or a hyperlink it lacks is taken from *outer*.
        With *colors* given, an opaque attribute also keeps its color mode, and the underline color it takes is
        parsed in that mode; *colors* is not used.
        Otherwise, each setting this attribute turns on ('bold') or off ('no-bold') is kept,
        and a setting it does not mention is taken from *outer*.
        The result may still inherit a color, when *outer* inherits it too.
        The hyperlink is resolved on its own: without one, this attribute takes the hyperlink of *outer*.
        The result is a plain :class:`AttrSpec` whenever it differs from this attribute.

        Without *colors*, every color keeps its kind, so a palette entry stays one beside a 24-bit color,
        and the result is declared in the mode its colors need.
        An 88-color entry above 15 that ends up beside a color of another mode becomes its RGB value.
        With *colors*, an attribute that is not opaque has each color described as its own color mode names it and
        parsed in *colors*, which approximates a color that mode does not have.

        Paths::

            no 'inherit' color (opaque)
              +- nothing to take from *outer* ------------> this attribute
              +- *colors* None ---------------------------> colors kept by kind, *outer*'s underline color
              +- *colors* given --------------------------> own mode, *outer*'s underline color parsed in it
            'inherit' color
              +- *colors* None ---------------------------> channels of both by kind, larger mode
              +- *colors* given --------------------------> descriptions of both parsed in *colors*

        :param outer: the enclosing attribute
        :param colors: the color mode of a result that is not opaque;
            ``None`` keeps each color as it is, in the larger color mode of the two attributes
        :raises AttrSpecError: with *colors*, a color of an attribute that is not opaque, or the underline color an
            opaque one takes, needs more colors than that result has.

        >>> AttrSpec("dark red,bold", "inherit").layered_over(AttrSpec("inherit,underline", "dark blue"))
        AttrSpec('dark red,bold,underline', 'dark blue')
        >>> AttrSpec("dark red", "default").layered_over(AttrSpec("yellow", "dark blue"))
        AttrSpec('dark red', 'default')
        >>> AttrSpec("inherit,no-bold", "inherit").layered_over(AttrSpec("yellow,bold,underline", "dark blue"))
        AttrSpec('yellow,underline,no-bold', 'dark blue')
        >>> AttrSpec("dark red", "default").layered_over(AttrSpec("yellow,bold", "dark blue", hyperlink="https://a.b"))
        AttrSpec('dark red', 'default', hyperlink=Hyperlink(uri='https://a.b', id=''))
        >>> AttrSpec("h196", "inherit").layered_over(AttrSpec("default", "#102030", 2**24))
        AttrSpec('h196', '#102030', colors=16777216)
        """
        # _depth builds on this module, so it is imported where it is used
        from urwid.display.common import _depth  # pylint: disable=import-outside-toplevel

        link = self.__hyperlink if self.__hyperlink is not None else outer.hyperlink
        if not self.__value & _INHERIT_MASK:
            if link is self.__hyperlink and (self.__underline_color is not None or outer.underline_color is None):
                return self
            if colors is None:
                foreground, background, line = _depth.channels(self)
                if line.kind is _depth.Kind.INHERIT:
                    line = _depth.channels(outer)[2]
                return _depth.build(
                    foreground,
                    background,
                    line,
                    settings=self.__value,
                    hyperlink=link,
                    mode=self.__color_mode(),
                )
            return AttrSpec(
                self.foreground,
                self.background,
                self.__color_mode(),
                hyperlink=link,
                underline_color=self.underline_color
                if self.__underline_color is not None
                else outer.__released_colors()[2],  # pylint: disable=protected-access  # the same class
            )
        own_settings = self.foreground.split(",")[1:]
        outer_settings = outer.foreground.split(",")[1:]
        settings = ""
        for name, off_name in zip(_ATTRIBUTES, _ATTRIBUTES_OFF, strict=True):
            # the inner attribute's own state, else the outer one's, else not mentioned; an underline keeps its style
            forms = (name, off_name, *(_UNDERLINE_STYLES if name == "underline" else ()))
            for state in (own_settings, outer_settings):
                if (form := next((form for form in forms if form in state), None)) is not None:
                    settings += f",{form}"
                    break
        if colors is None:
            return _depth.compose(self, outer, settings=AttrSpec(DEFAULT + settings, hyperlink=link))
        own = self.__released_colors()
        enclosing = outer.__released_colors()  # pylint: disable=protected-access  # the same class
        return AttrSpec(
            (enclosing if self.foreground_inherit else own)[0] + settings,
            (enclosing if self.background_inherit else own)[1],
            colors,
            hyperlink=link,
            underline_color=own[2] if self.__underline_color is not None else enclosing[2],
        )

    def __released_colors(self) -> tuple[str, str, str | None]:
        """Return the foreground, background and underline colors as a specification of one color mode names them.

        A palette entry is named in the cube or gray form of its palette, also in a true color specification.
        The underline color is ``None`` when it is taken from the enclosing attribute.
        """
        return (
            self.__kept_color(self.__value & _FG_KIND_MASK, self.foreground_number, 256),
            self.__kept_color(self.__value & _BG_KIND_MASK, self.background_number, 256),
            None if self.__underline_color is None else self.__kept_underline_color(256),
        )

    def __eq__(self, other: object) -> bool:
        """Return whether `other` is an :class:`AttrSpec` with the same value, hyperlink and underline color."""
        return (
            isinstance(other, AttrSpec)
            and self.__value == other._value
            and self.__hyperlink == other.hyperlink
            and self.underline_color == other.underline_color
        )

    def __ne__(self, other: object) -> bool:
        """Return whether `other` is not equal to this :class:`AttrSpec`."""
        return not self == other
