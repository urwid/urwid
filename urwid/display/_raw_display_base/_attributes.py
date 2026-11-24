# Urwid raw display module
#    Copyright (C) 2004-2009  Ian Ward
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


"""Attribute and palette output of the raw display :class:`Screen`."""

from __future__ import annotations

import operator
import typing

from urwid.display import _sgr, escape
from urwid.display._raw_display_base._base import _ScreenBase
from urwid.display._raw_display_base._detection import _ColorCount, _is_linux_console
from urwid.display.common import (
    _COLOR_VALUES_88,
    _COLOR_VALUES_256,
    _RESOLVED_ATTRS_LIMIT,
    AttrSpec,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Mapping


# Index into the (basic, mono, high_88, high_256, high_true) tuple that
# BaseScreen.register_palette_entry() emits via UPDATE_PALETTE_ENTRY, keyed by this screen's
# current color count.
_ATTRSPEC_INDEX_BY_COLORS: Mapping[_ColorCount, int] = {16: 0, 1: 1, 88: 2, 256: 3, 16777216: 4}


class _AttributesScreen(_ScreenBase):  # pylint: disable=abstract-method  # a platform screen completes it
    """Write display attributes and palette changes to the terminal of a raw display :class:`Screen`."""

    __slots__ = ()

    def _attr_to_escape(self, a: Hashable) -> str:
        """Convert canvas run attribute a to an escape sequence for the terminal.

        With :attr:`hyperlinks` on, the escape of an attribute with a hyperlink ends with the OSC 8 sequence opening it.
        """
        rendition, link = self._attr_escape_parts(a)
        return rendition + link

    def _attr_escape_parts(self, a: Hashable) -> tuple[str, str]:
        """Return the escape of canvas run attribute *a* in two parts: its SGR sequence, and its OSC 8 hyperlink.

        The hyperlink part is empty without :attr:`hyperlinks` or without a link.
        """
        if found := self._pal_escape.get(a):
            return found
        spec = self._drawn_spec(a)
        link = ""
        if self._terminal_properties.hyperlinks and spec.hyperlink is not None and spec.hyperlink.uri:
            link = escape.hyperlink_open(spec.hyperlink)
        found = (self._attrspec_to_escape(spec), link)
        if len(self._pal_escape) >= _RESOLVED_ATTRS_LIMIT:
            self._pal_escape.clear()
        self._pal_escape[a] = found
        return found

    def _drawn_spec(self, a: Hashable) -> AttrSpec:
        """Return the :class:`AttrSpec` canvas run attribute *a* is drawn with, in the colors the terminal draws."""
        colors = self._terminal_properties.colors
        if self.term.lower() == "fbterm" and colors == 16777216:
            # fbterm's own color sequences take palette entries only
            colors = 256
        return self._drawn_attr(a, _ATTRSPEC_INDEX_BY_COLORS[colors], colors)

    def _attrspec_to_escape(self, a: AttrSpec) -> str:
        r"""Convert AttrSpec instance a to an escape sequence for the terminal.

        >>> from urwid.display.raw import Screen  # this class is abstract
        >>> s = Screen()
        >>> s.set_terminal_properties(colors=256)
        >>> a2e = s._attrspec_to_escape
        >>> a2e(s.AttrSpec("brown", "dark green"))
        '\x1b[0;33;42m'
        >>> a2e(s.AttrSpec("#fea,underline", "#d0d"))
        '\x1b[0;38;5;229;4;48;5;164m'
        >>> s.set_terminal_properties(underline_styles=True)
        >>> a2e(s.AttrSpec("default,curly underline", "default", underline_color="#f00"))
        '\x1b[0;39;4:3;58:5:196;49m'
        """
        st = "".join(
            self._underline_parameters(a) if name == "underline" else f"{code:d};" * getattr(a, name)
            for name, code in _sgr.FLAGS
        )
        if self.term.lower() == "fbterm":
            # fbterm takes a palette color from its own sequences, after SGR for the default colors and the settings;
            # an unset color has no palette entry, as entry 0 is black. Its 39 also ends underline, so it comes first.
            escapes = f"{escape.CSI}0;39;49;{st}".removesuffix(";") + "m"
            if a.foreground_basic or a.foreground_high:
                escapes += f"{escape.CSI}1;{a.foreground_number:d}}}"
            if a.background_basic or a.background_high:
                escapes += f"{escape.CSI}2;{a.background_number:d}}}"
            return escapes

        properties = self._terminal_properties
        fg = _sgr.color_parameters(a, background=False, bright_flag=properties.fg_bright_is_bold) or "39"
        bg = _sgr.color_parameters(a, background=True, bright_flag=properties.bg_bright_is_blink) or "49"
        return f"{escape.CSI}0;{fg};{st}{bg}m"

    def _underline_parameters(self, a: AttrSpec) -> str:
        """Return the SGR parameters of the underline of *a*, each followed by ``;``, empty without an underline.

        Its style and its color are written only to a terminal that draws them.
        """
        if not a.underline:
            return ""
        if not self._terminal_properties.underline_styles:
            return "4;"
        color = _sgr.underline_color_parameter(a)
        return f"{_sgr.underline_style_parameter(a)};" + (f"{color};" if color is not None else "")

    def reset_default_terminal_palette(self) -> None:
        """Attempt to set the terminal palette to default values as taken from xterm.

        Uses a number of colors from the current set_terminal_properties() screen setting.
        """
        if self._terminal_properties.colors == 1:
            return
        if self._terminal_properties.colors == 2**24:
            colors = 256
        else:
            colors = self._terminal_properties.colors

        values = _COLOR_VALUES_88 if colors == 88 else _COLOR_VALUES_256
        entries = [(n, *values[n]) for n in range(min(colors, 256))]
        self.modify_terminal_palette(entries)

    def modify_terminal_palette(self, entries: Iterable[tuple[int, int, int, int]]) -> None:
        """Attempt to set part of the terminal palette; this does not work on all terminals.

        The changes are sent as a single escape sequence so they should all take effect at the same time.
        The Linux console takes one sequence per entry instead, and applies each as it arrives.

        0 <= index < 256 (some terminals will only have 16 or 88 colors)
        0 <= red, green, blue < 256

        The Linux console has only entries 0-15 and skips the others.
        Which terminal is in use, and so which entries it has, is up to the caller to check (:attr:`term`)
        before relying on the change.

        :param entries: list of (index, red, green, blue) tuples.
        :raises TypeError: an index or a red, green or blue value is not an integer.
        :raises ValueError: on the Linux console, an index or a red, green or blue value is outside 0-255,
            which its sequence cannot carry.
        """
        checked: list[tuple[int, int, int, int]] = []
        for entry in entries:
            try:
                index, red, green, blue = map(operator.index, entry)
            except TypeError as exc:
                raise TypeError(f"Palette entry has a value that is not an integer: {entry!r}") from exc
            checked.append((index, red, green, blue))
        entries = checked

        if _is_linux_console(self.term):
            sequences: list[str] = []
            applied: list[tuple[int, int, int, int]] = []
            for index, red, green, blue in entries:
                if index not in range(256) or any(value not in range(256) for value in (red, green, blue)):
                    raise ValueError(f"Linux console palette entry out of range: {(index, red, green, blue)!r}")
                if index < 16:
                    sequences.append(f"{escape.LINUX_SET_PALETTE}{index:x}{red:02x}{green:02x}{blue:02x}")
                    applied.append((index, red, green, blue))
            entries = applied
            self.write("".join(sequences))
        elif self.term.lower() == "fbterm":
            modify = [f"{index:d};{red:d};{green:d};{blue:d}" for index, red, green, blue in entries]
            self.write(f"{escape.CSI}3;{';'.join(modify)}}}")
        else:
            modify = [f"{index:d};rgb:{red:02x}/{green:02x}/{blue:02x}" for index, red, green, blue in entries]
            self.write(f"{escape.OSC}4;{';'.join(modify)}{escape.ST}")
        self.flush()
        self._modified_palette_entries.update(index for index, _red, _green, _blue in entries)
