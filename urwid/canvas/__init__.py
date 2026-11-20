# Urwid canvas class and functions
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

"""Canvases: the rendered, cacheable output of widgets, and the functions that combine them."""

from __future__ import annotations

import typing

from urwid.canvas._base import BlankCanvas, Canvas, CanvasError, SolidCanvas, blank_canvas
from urwid.canvas._cache import CanvasCache
from urwid.canvas._cache import _walk_depends as _walk_depends
from urwid.canvas._composite import (
    CanvasCombine,
    CanvasJoin,
    CanvasOverlay,
    CompositeCanvas,
    cview_trim_cols,
    cview_trim_left,
    cview_trim_rows,
    cview_trim_top,
    shard_body,
    shard_body_row,
    shard_body_tail,
    shards_join,
    shards_trim_rows,
    shards_trim_sides,
    shards_trim_top,
)
from urwid.canvas._composite import _AttrMapChain as _AttrMapChain
from urwid.canvas._composite import _shards_cut_columns as _shards_cut_columns
from urwid.canvas._text import _CONTROL_CHARS as _CONTROL_CHARS
from urwid.canvas._text import _CONTROL_RE as _CONTROL_RE
from urwid.canvas._text import _CONTROL_UTF8_RE as _CONTROL_UTF8_RE
from urwid.canvas._text import _DRAWN_RUN_RE as _DRAWN_RUN_RE
from urwid.canvas._text import TextCanvas, apply_text_layout
from urwid.canvas._text import _AttrWalk as _AttrWalk
from urwid.canvas._text import _drawn_ranges as _drawn_ranges

if typing.TYPE_CHECKING:
    # The pop-up type aliases exist for type checkers only, so they are re-exported here and not in __all__.
    from urwid.canvas._base import PopUpLeft as PopUpLeft
    from urwid.canvas._base import PopUpPassKey as PopUpPassKey
    from urwid.canvas._base import PopUpSize as PopUpSize
    from urwid.canvas._base import PopUpTop as PopUpTop

__all__ = (
    "BlankCanvas",
    "Canvas",
    "CanvasCache",
    "CanvasCombine",
    "CanvasError",
    "CanvasJoin",
    "CanvasOverlay",
    "CompositeCanvas",
    "SolidCanvas",
    "TextCanvas",
    "apply_text_layout",
    "blank_canvas",
    "cview_trim_cols",
    "cview_trim_left",
    "cview_trim_rows",
    "cview_trim_top",
    "shard_body",
    "shard_body_row",
    "shard_body_tail",
    "shards_join",
    "shards_trim_rows",
    "shards_trim_sides",
    "shards_trim_top",
)
