from __future__ import annotations

import importlib.util
import sys
import typing

if typing.TYPE_CHECKING:
    from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_GRAALPY = sys.implementation.name == "graalpy"

# Modules that import only on one platform. Urwid picks between them at runtime
# (see `urwid/display/raw.py` and the `sys.platform` guards in `urwid/__init__.py`),
# so `--doctest-modules` has to make the same choice instead of importing everything.
_PLATFORM_ONLY: typing.Final[dict[str, bool]] = {
    "_posix_raw_display.py": not IS_WINDOWS,
    "vterm.py": not IS_WINDOWS,
    "test_vterm.py": not IS_WINDOWS,
    "_win32.py": IS_WINDOWS,
    "_win32_raw_display.py": IS_WINDOWS,
    # ZMQEventLoop crashes the interpreter on Windows, so urwid never imports it there.
    "zmq_loop.py": not IS_WINDOWS,
}

# Modules importing an optional backend at top level. Urwid keeps working without the
# backend installed, and their doctests have to be skipped on the same condition.
_OPTIONAL_BACKEND: typing.Final[dict[str, str]] = {
    "curses.py": "_curses",
    "glib_loop.py": "gi",
    "tornado_loop.py": "tornado",
    "trio_loop.py": "trio",
    "twisted_loop.py": "twisted",
    "zmq_loop.py": "zmq",
}

# GraalPy ships a pure-Python `curses` package (so `find_spec("curses")` succeeds) but no compiled
# `_curses` extension backing it, so importing `curses` itself raises
# ModuleNotFoundError for `_curses` rather than failing to resolve up front. Treated as always
# unavailable there rather than probed with `find_spec`, since a partial/shim module on a
# non-CPython interpreter is not reliable evidence either way.
_UNAVAILABLE_ON_GRAALPY: typing.Final[frozenset[str]] = frozenset({"_curses"})


def _backend_available(name: str) -> bool:
    if IS_GRAALPY and name in _UNAVAILABLE_ON_GRAALPY:
        return False
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    name = collection_path.name

    if not _PLATFORM_ONLY.get(name, True):
        return True

    backend = _OPTIONAL_BACKEND.get(name)
    if backend is not None and not _backend_available(backend):
        return True

    return None
