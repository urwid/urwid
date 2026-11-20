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


"""Colour and attribute handling and the base classes shared by all display modules."""

from __future__ import annotations

import typing

from urwid.display.common._attr_spec import _ATTRIBUTES as _ATTRIBUTES
from urwid.display.common._attr_spec import _ATTRIBUTES_OFF as _ATTRIBUTES_OFF
from urwid.display.common._attr_spec import _BG_BASIC_COLOR as _BG_BASIC_COLOR
from urwid.display.common._attr_spec import _BG_COLOR_MASK as _BG_COLOR_MASK
from urwid.display.common._attr_spec import _BG_HIGH_COLOR as _BG_HIGH_COLOR
from urwid.display.common._attr_spec import _BG_INHERIT as _BG_INHERIT
from urwid.display.common._attr_spec import _BG_MASK as _BG_MASK
from urwid.display.common._attr_spec import _BG_SHIFT as _BG_SHIFT
from urwid.display.common._attr_spec import _BG_TRUE_COLOR as _BG_TRUE_COLOR
from urwid.display.common._attr_spec import _BLINK as _BLINK
from urwid.display.common._attr_spec import _BOLD as _BOLD
from urwid.display.common._attr_spec import _COLOR_BASIC as _COLOR_BASIC
from urwid.display.common._attr_spec import _COLOR_DEFAULT as _COLOR_DEFAULT
from urwid.display.common._attr_spec import _COLOR_HIGH as _COLOR_HIGH
from urwid.display.common._attr_spec import _COLOR_KIND_SHIFT as _COLOR_KIND_SHIFT
from urwid.display.common._attr_spec import _COLOR_TRUE as _COLOR_TRUE
from urwid.display.common._attr_spec import _FAINT as _FAINT
from urwid.display.common._attr_spec import _FG_BASIC_COLOR as _FG_BASIC_COLOR
from urwid.display.common._attr_spec import _FG_COLOR_MASK as _FG_COLOR_MASK
from urwid.display.common._attr_spec import _FG_HIGH_COLOR as _FG_HIGH_COLOR
from urwid.display.common._attr_spec import _FG_INHERIT as _FG_INHERIT
from urwid.display.common._attr_spec import _FG_MASK as _FG_MASK
from urwid.display.common._attr_spec import _FG_TRUE_COLOR as _FG_TRUE_COLOR
from urwid.display.common._attr_spec import _HIGH_88_COLOR as _HIGH_88_COLOR
from urwid.display.common._attr_spec import _HIGH_TRUE_COLOR as _HIGH_TRUE_COLOR
from urwid.display.common._attr_spec import _HYPERLINK_ID_MAX_LEN as _HYPERLINK_ID_MAX_LEN
from urwid.display.common._attr_spec import _HYPERLINK_URI_MAX_LEN as _HYPERLINK_URI_MAX_LEN
from urwid.display.common._attr_spec import _INHERIT_MASK as _INHERIT_MASK
from urwid.display.common._attr_spec import _ITALICS as _ITALICS
from urwid.display.common._attr_spec import _RESOLVED_ATTRS_LIMIT as _RESOLVED_ATTRS_LIMIT
from urwid.display.common._attr_spec import _SETTING_OFF_PREFIX as _SETTING_OFF_PREFIX
from urwid.display.common._attr_spec import _SETTING_OFF_SHIFT as _SETTING_OFF_SHIFT
from urwid.display.common._attr_spec import _SETTINGS_OFF_MASK as _SETTINGS_OFF_MASK
from urwid.display.common._attr_spec import _STANDOUT as _STANDOUT
from urwid.display.common._attr_spec import _STRIKETHROUGH as _STRIKETHROUGH
from urwid.display.common._attr_spec import _UNDERLINE as _UNDERLINE
from urwid.display.common._attr_spec import _UNDERLINE_STYLE_BITS as _UNDERLINE_STYLE_BITS
from urwid.display.common._attr_spec import _UNDERLINE_STYLE_MASK as _UNDERLINE_STYLE_MASK
from urwid.display.common._attr_spec import _UNDERLINE_STYLE_NAMES as _UNDERLINE_STYLE_NAMES
from urwid.display.common._attr_spec import _UNDERLINE_STYLE_SHIFT as _UNDERLINE_STYLE_SHIFT
from urwid.display.common._attr_spec import _UNDERLINE_STYLES as _UNDERLINE_STYLES
from urwid.display.common._attr_spec import NO_HYPERLINK, AttrSpec, AttrSpecError, Hyperlink
from urwid.display.common._attr_spec import _Keep as _Keep
from urwid.display.common._colors import _BASIC_COLOR_INDEX as _BASIC_COLOR_INDEX
from urwid.display.common._colors import _BASIC_COLOR_VALUES as _BASIC_COLOR_VALUES
from urwid.display.common._colors import _BASIC_COLORS as _BASIC_COLORS
from urwid.display.common._colors import _BASIC_START as _BASIC_START
from urwid.display.common._colors import _COLOR_VALUES_88 as _COLOR_VALUES_88
from urwid.display.common._colors import _COLOR_VALUES_256 as _COLOR_VALUES_256
from urwid.display.common._colors import _CUBE_88_LOOKUP as _CUBE_88_LOOKUP
from urwid.display.common._colors import _CUBE_88_LOOKUP_16 as _CUBE_88_LOOKUP_16
from urwid.display.common._colors import _CUBE_256_LOOKUP as _CUBE_256_LOOKUP
from urwid.display.common._colors import _CUBE_256_LOOKUP_16 as _CUBE_256_LOOKUP_16
from urwid.display.common._colors import _CUBE_BLACK as _CUBE_BLACK
from urwid.display.common._colors import _CUBE_SIZE_88 as _CUBE_SIZE_88
from urwid.display.common._colors import _CUBE_SIZE_256 as _CUBE_SIZE_256
from urwid.display.common._colors import _CUBE_START as _CUBE_START
from urwid.display.common._colors import _CUBE_STEPS_88 as _CUBE_STEPS_88
from urwid.display.common._colors import _CUBE_STEPS_88_16 as _CUBE_STEPS_88_16
from urwid.display.common._colors import _CUBE_STEPS_256 as _CUBE_STEPS_256
from urwid.display.common._colors import _CUBE_STEPS_256_16 as _CUBE_STEPS_256_16
from urwid.display.common._colors import _CUBE_WHITE_88 as _CUBE_WHITE_88
from urwid.display.common._colors import _CUBE_WHITE_256 as _CUBE_WHITE_256
from urwid.display.common._colors import _DEFAULT_COLOR_NAMES as _DEFAULT_COLOR_NAMES
from urwid.display.common._colors import _GRAY_88_LOOKUP as _GRAY_88_LOOKUP
from urwid.display.common._colors import _GRAY_88_LOOKUP_101 as _GRAY_88_LOOKUP_101
from urwid.display.common._colors import _GRAY_256_LOOKUP as _GRAY_256_LOOKUP
from urwid.display.common._colors import _GRAY_256_LOOKUP_101 as _GRAY_256_LOOKUP_101
from urwid.display.common._colors import _GRAY_SIZE_88 as _GRAY_SIZE_88
from urwid.display.common._colors import _GRAY_SIZE_256 as _GRAY_SIZE_256
from urwid.display.common._colors import _GRAY_START_88 as _GRAY_START_88
from urwid.display.common._colors import _GRAY_START_256 as _GRAY_START_256
from urwid.display.common._colors import _GRAY_STEPS_88 as _GRAY_STEPS_88
from urwid.display.common._colors import _GRAY_STEPS_88_101 as _GRAY_STEPS_88_101
from urwid.display.common._colors import _GRAY_STEPS_256 as _GRAY_STEPS_256
from urwid.display.common._colors import _GRAY_STEPS_256_101 as _GRAY_STEPS_256_101
from urwid.display.common._colors import _VALID_COLOR_COUNTS as _VALID_COLOR_COUNTS
from urwid.display.common._colors import (
    BLACK,
    BROWN,
    DARK_BLUE,
    DARK_CYAN,
    DARK_GRAY,
    DARK_GREEN,
    DARK_MAGENTA,
    DARK_RED,
    DEFAULT,
    INHERIT,
    LIGHT_BLUE,
    LIGHT_CYAN,
    LIGHT_GRAY,
    LIGHT_GREEN,
    LIGHT_MAGENTA,
    LIGHT_RED,
    WHITE,
    YELLOW,
)
from urwid.display.common._colors import _color_desc_88 as _color_desc_88
from urwid.display.common._colors import _color_desc_256 as _color_desc_256
from urwid.display.common._colors import _color_desc_true as _color_desc_true
from urwid.display.common._colors import _gray_num_88 as _gray_num_88
from urwid.display.common._colors import _gray_num_256 as _gray_num_256
from urwid.display.common._colors import _parse_color_88 as _parse_color_88
from urwid.display.common._colors import _parse_color_256 as _parse_color_256
from urwid.display.common._colors import _parse_color_true as _parse_color_true
from urwid.display.common._colors import _true_to_256 as _true_to_256
from urwid.display.common._colors import _value_lookup_table as _value_lookup_table
from urwid.display.common._css import _BROWSER_SCHEMES as _BROWSER_SCHEMES
from urwid.display.common._css import _CSS_UNDERLINE_STYLES as _CSS_UNDERLINE_STYLES
from urwid.display.common._css import _browser_href as _browser_href
from urwid.display.common._css import _default_aspec as _default_aspec
from urwid.display.common._css import _default_bg_rgb as _default_bg_rgb
from urwid.display.common._css import _default_fg_rgb as _default_fg_rgb
from urwid.display.common._css import _style_to_css as _style_to_css
from urwid.display.common._css import _underline_css as _underline_css
from urwid.display.common._css import attr_spec_to_css
from urwid.display.common._screen import (
    INPUT_DESCRIPTORS_CHANGED,
    IS_WINDOWS,
    UNPRINTABLE_C1_TRANS_TABLE,
    UNPRINTABLE_TRANS_TABLE,
    UPDATE_PALETTE_ENTRY,
    BaseScreen,
    InputClosedError,
    PaletteEntrySpecs,
    RealTerminal,
    ScreenError,
)

if typing.TYPE_CHECKING:
    from urwid.display.common._screen import PaletteEntry as PaletteEntry

__all__ = (
    "BLACK",
    "BROWN",
    "DARK_BLUE",
    "DARK_CYAN",
    "DARK_GRAY",
    "DARK_GREEN",
    "DARK_MAGENTA",
    "DARK_RED",
    "DEFAULT",
    "INHERIT",
    "INPUT_DESCRIPTORS_CHANGED",
    "IS_WINDOWS",
    "LIGHT_BLUE",
    "LIGHT_CYAN",
    "LIGHT_GRAY",
    "LIGHT_GREEN",
    "LIGHT_MAGENTA",
    "LIGHT_RED",
    "NO_HYPERLINK",
    "UNPRINTABLE_C1_TRANS_TABLE",
    "UNPRINTABLE_TRANS_TABLE",
    "UPDATE_PALETTE_ENTRY",
    "WHITE",
    "YELLOW",
    "AttrSpec",
    "AttrSpecError",
    "BaseScreen",
    "Hyperlink",
    "InputClosedError",
    "PaletteEntrySpecs",
    "RealTerminal",
    "ScreenError",
    "attr_spec_to_css",
)
