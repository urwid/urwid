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

__all__: tuple[str, ...] = (
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
    "curses",
    "html_fragment",
    "lcd",
    "raw",
    "web",
)


def lazy_import(name: str, package: str | None = None) -> types.ModuleType:
    """Lazy import implementation from Python documentation.

    Useful for cases where no warnings expected for moved modules.

    :raises ImportError: *name* does not resolve to a loadable module.
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


html_fragment = lazy_import(".html_fragment", "urwid.display")
lcd = lazy_import(".lcd", "urwid.display")
web = lazy_import(".web", "urwid.display")


def __getattr__(name: str) -> types.ModuleType:
    """Lazily import `curses`, the optional stdlib-backed display submodule.

    "curses" module may be present without "_curses" private part, so lazy_import will pass and real usage fail.

    :raises AttributeError: *name* is not ``"curses"``, or the stdlib `curses` module is unavailable.
    """
    if name != "curses":
        raise AttributeError(name)
    try:
        module = importlib.import_module(".curses", __name__)
    except ImportError as exc:
        raise AttributeError(name) from exc
    globals()["curses"] = module
    return module
