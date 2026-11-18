"""Pytest configuration: prepare the pytest-xdist controller, skip modules that cannot be imported here."""

from __future__ import annotations

import importlib.util
import sys
import typing

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest

IS_WINDOWS = sys.platform == "win32"

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


def _backend_available(name: str) -> bool:
    """Return whether the module *name* can be imported.

    Importing is the only reliable probe.
    PyPy for Windows ships an ``_curses`` stub that ``find_spec`` resolves,
    but the stub raises ``ModuleNotFoundError`` on import.
    """
    try:
        importlib.import_module(name)
    except ImportError:
        return False
    return True


def pytest_configure(config: pytest.Config) -> None:
    """Import urwid in the pytest-xdist controller before the workers start.

    The controller rebuilds each warning a worker reports by importing the module that defines its class,
    on one execnet receiver thread per worker.
    Two such threads importing urwid modules for the first time at once deadlock in the import system,
    which ends the run with ``INTERNALERROR`` (pytest-dev/pytest-xdist#1422).
    Once urwid is imported, those imports are lookups in :data:`sys.modules`.
    """
    if not hasattr(config, "workerinput"):
        importlib.import_module("urwid")


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Skip collecting a platform-only or optional-backend test module that cannot run here."""
    name = collection_path.name

    if not _PLATFORM_ONLY.get(name, True):
        return True

    backend = _OPTIONAL_BACKEND.get(name)
    if backend is not None and not _backend_available(backend):
        return True

    return None
