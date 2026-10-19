from __future__ import annotations

import gc
import sys
import typing

import urwid

if typing.TYPE_CHECKING:
    import unittest
    import weakref
    from collections.abc import Collection

# GraalPy for Python 3.11 (GraalVM 24) keeps some unreachable objects through any number of gc.collect() passes
# and never frees a class created at run time. GraalPy for Python 3.12 (GraalVM 25) frees both.
GC_KEEPS_UNREACHABLE = sys.implementation.name == "graalpy" and sys.version_info < (3, 12)
SKIP_GC_REASON = "GraalPy for Python 3.11 keeps some unreachable objects through gc.collect()"


class PaletteScreen(urwid.BaseScreen):
    """Screen with a palette and no terminal, for resolving display attributes."""

    def draw_screen(self, size: tuple[int, int], canvas: urwid.Canvas) -> None:
        """Drawing is unsupported."""
        raise NotImplementedError


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


def wstest(w: urwid.Widget) -> None:
    """Render the box widget *w* with zero and one rows and with zero and one columns."""
    c = w.render((80, 0), focus=False)
    assert c.rows() == 0
    c = w.render((80, 0), focus=True)
    assert c.rows() == 0
    c = w.render((80, 1), focus=False)
    assert c.rows() == 1
    c = w.render((0, 25), focus=False)
    c = w.render((1, 25), focus=False)


def fwstest(test_case: unittest.TestCase, w: urwid.Widget) -> None:
    """Check that the flow widget *w* rendered with zero and one columns matches its rows and cursor."""

    def t(cols: int, focus: bool):
        wrows = w.rows((cols,), focus)
        c = w.render((cols,), focus)
        test_case.assertEqual(c.rows(), wrows, f"Canvas rows {c.rows()} != widget rows {wrows}")
        if focus and hasattr(w, "get_cursor_coords"):
            gcc = w.get_cursor_coords((cols,))
            test_case.assertEqual(c.cursor, gcc, f"Canvas cursor {c.cursor} != widget cursor {gcc}")

    for cols, focus in ((0, False), (1, False), (0, True), (1, True)):
        with test_case.subTest(f"{w.__class__.__name__} cols={cols} and focus={focus}"):
            t(cols, focus)
