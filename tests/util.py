from __future__ import annotations

import errno
import gc
import selectors
import typing

import urwid

if typing.TYPE_CHECKING:
    import weakref
    from collections.abc import Collection


class SelectableText(urwid.Text):
    def selectable(self):
        return True

    def keypress(self, size, key):
        return key


def collect_and_count_alive(refs: Collection[weakref.ReferenceType[typing.Any]]) -> int:
    """Collect garbage until a pass frees none of the objects behind *refs*, and return how many are alive.

    A tracing collector (PyPy, GraalPy) frees an object released by a weakref callback only in a pass after the one
    that ran the callback, and GraalPy, once a thread has been started, can defer a pass's callbacks to the next one.
    Stopping after an unchanged pass takes at least two passes, so the callbacks of the last freeing pass have run.
    """
    before = None
    for _ in range(10):
        gc.collect()
        alive = sum(ref() is not None for ref in refs)
        if alive == before:
            break
        before = alive
    return alive


class Index:
    """Integer-like object whose ``__index__`` and ``__int__`` give different values."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __index__(self) -> int:
        return self.value

    def __int__(self) -> int:
        return 1


class CountingIndex:
    """Integer-like object that counts how often ``__index__`` is called."""

    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.calls = 0

    def __index__(self) -> int:
        self.calls += 1
        return self.value


class TtyRefusingSelector(selectors.SelectSelector):
    """Stand-in for ``KqueueSelector`` on macOS, which refuses to register a descriptor opened from ``/dev/tty``."""

    def register(self, fileobj: typing.Any, events: int, data: typing.Any = None) -> selectors.SelectorKey:
        """Refuse *fileobj* with ``EINVAL``."""
        raise OSError(errno.EINVAL, "Invalid argument")
