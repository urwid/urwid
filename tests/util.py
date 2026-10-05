from __future__ import annotations

import gc
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
