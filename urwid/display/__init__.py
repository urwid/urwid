"""Package with Display implementations for urwid."""

from __future__ import annotations

__all__ = (
    "raw",
    "BLACK",
    "BROWN",
    "DARK_BLUE",
    "DARK_CYAN",
    "DARK_GRAY",
    "DARK_GREEN",
    "DARK_MAGENTA",
    "DARK_RED",
    "DEFAULT",
    "LIGHT_BLUE",
    "LIGHT_CYAN",
    "LIGHT_GRAY",
    "LIGHT_GREEN",
    "LIGHT_MAGENTA",
    "LIGHT_RED",
    "UPDATE_PALETTE_ENTRY",
    "WHITE",
    "YELLOW",
    "AttrSpec",
    "AttrSpecError",
    "BaseScreen",
    "RealTerminal",
    "ScreenError",
)

from . import raw
from .common import (
    BLACK,
    BROWN,
    DARK_BLUE,
    DARK_CYAN,
    DARK_GRAY,
    DARK_GREEN,
    DARK_MAGENTA,
    DARK_RED,
    DEFAULT,
    LIGHT_BLUE,
    LIGHT_CYAN,
    LIGHT_GRAY,
    LIGHT_GREEN,
    LIGHT_MAGENTA,
    LIGHT_RED,
    UPDATE_PALETTE_ENTRY,
    WHITE,
    YELLOW,
    AttrSpec,
    AttrSpecError,
    BaseScreen,
    RealTerminal,
    ScreenError,
)

try:
    from . import curses

    __all__ += ("curses",)
except ImportError:
    pass
