"""Package with Display implementations for urwid."""

from __future__ import annotations

import importlib
import typing

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
    # Lazy imported
    "html_fragment",
    "lcd",
    "raw",
    "web",
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

# Moved modules handling
__locals: dict[str, typing.Any] = locals()  # use mutable access for pure lazy loading

# Lazy load modules
_lazy_load: frozenset[str] = frozenset(
    (
        "html_fragment",
        "lcd",
        "web",
    )
)


def __getattr__(name: str) -> typing.Any:
    """Get attributes lazy.

    :return: attribute by name
    :raises AttributeError: attribute is not defined for lazy load
    """
    if name in _lazy_load:
        mod = importlib.import_module(f"{__package__}.{name}")
        __locals[name] = mod
        return mod

    raise AttributeError(f"{name} not found in {__package__}")
