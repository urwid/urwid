"""Package with Display implementations for urwid."""

from __future__ import annotations

import importlib.util
import sys
import typing

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

if typing.TYPE_CHECKING:
    import types

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

try:
    from . import curses

    __all__ += ("curses",)
except ImportError:
    pass


def lazy_import(name: str, package: str | None = None) -> types.ModuleType:
    """Lazy import implementation from Python documentation.

    Useful for cases where no warnings expected for moved modules.
    """
    spec = importlib.util.find_spec(name, package)
    if not spec:
        raise ImportError(f"No module named {name!r}")
    if not spec.loader:
        raise ImportError(f"Module named {name!r} is invalid")

    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    if not package:
        sys.modules[name] = module
    else:
        sys.modules[f"{package.rstrip('.')}.{name.lstrip('.')}"] = module
    loader.exec_module(module)
    return module


html_fragment = lazy_import(".html_fragment", __package__)
lcd = lazy_import(".lcd", __package__)
web = lazy_import(".web", __package__)
