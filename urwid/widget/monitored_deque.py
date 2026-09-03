# Urwid MonitoredDeque class
#    Copyright (C) 2026  urwid contributors
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

from __future__ import annotations

import collections
import functools
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from typing_extensions import Concatenate, ParamSpec

    ArgSpec = ParamSpec("ArgSpec")
    Ret = typing.TypeVar("Ret")

__all__ = ("MonitoredDeque", "MonitoredFocusDeque")

_T = typing.TypeVar("_T")


def _call_modified(
    fn: Callable[Concatenate[MonitoredDeque[typing.Any], ArgSpec], Ret],
) -> Callable[Concatenate[MonitoredDeque[typing.Any], ArgSpec], Ret]:
    @functools.wraps(fn)
    def call_modified_wrapper(
        self: MonitoredDeque[typing.Any],
        /,
        *args: ArgSpec.args,
        **kwargs: ArgSpec.kwargs,
    ) -> Ret:
        rval = fn(self, *args, **kwargs)
        self._modified()  # pylint: disable=protected-access
        return rval

    return call_modified_wrapper


class MonitoredDeque(collections.deque[_T], typing.Generic[_T]):
    """
    This class can trigger a callback any time its contents are changed
    with the usual deque operations append, extend, etc.

    It mirrors :class:`MonitoredList`, adapted to ``collections.deque``'s
    narrower API. Deliberate differences from :class:`MonitoredList`:

    * ``sort()`` is not provided -- ``deque`` itself has no such method.
    * ``__add__``/``__rmul__``/``__imul__`` are not provided -- ``deque``
      itself raises ``TypeError`` for concatenation/repetition, so there is
      nothing meaningful to wrap.
    * ``maxlen`` needs no dedicated property: it is already a read-only
      attribute inherited from ``deque``.

    **Eviction notification**: a bounded (``maxlen``-limited) deque may
    silently evict an item from the opposite end during ``append``,
    ``appendleft``, ``extend`` or ``extendleft``. As with every other
    mutation, ``_modified()`` fires exactly once per call in that case too
    -- there is deliberately no separate "eviction" signal, matching
    :class:`MonitoredList`'s existing philosophy (e.g. ``extend()`` fires
    once regardless of how many items were added). This keeps the
    ``_modified_callback`` contract (``Callable[[], Any]``, no parameters)
    unchanged and leaves room for a future, dedicated eviction signal
    without that being a breaking change. :class:`MonitoredFocusDeque`, the
    one place that needs eviction *detail* to keep focus correct, computes
    it itself from ``len(self)``/``self.maxlen`` before calling ``super()``
    -- exactly as :class:`MonitoredFocusList` already computes its own
    focus adjustments rather than relying on :class:`MonitoredList` to
    supply them.
    """

    _modified_callback: Callable[[], typing.Any] | None = None

    def __init__(self, iterable: Iterable[_T] = (), maxlen: int | None = None) -> None:
        super().__init__(iterable, maxlen)

    def _modified(self) -> None:
        if self._modified_callback is not None:
            self._modified_callback()

    def set_modified_callback(self, callback: Callable[[], typing.Any]) -> None:
        """
        Assign a callback function with no parameters that is called any
        time the deque is modified.  Callback's return value is ignored.

        >>> import sys
        >>> md = MonitoredDeque([1, 2, 3])
        >>> md.set_modified_callback(lambda: sys.stdout.write("modified\\n"))
        >>> md
        MonitoredDeque([1, 2, 3])
        >>> md.append(10)
        modified
        >>> len(md)
        4
        >>> md += [11, 12, 13]
        modified
        >>> md.clear()
        modified
        >>> md
        MonitoredDeque([])

        Eviction from a bounded deque still fires the callback exactly once:

        >>> bounded = MonitoredDeque([1, 2, 3], maxlen=3)
        >>> bounded.set_modified_callback(lambda: sys.stdout.write("modified\\n"))
        >>> bounded.append(4)
        modified
        >>> bounded
        MonitoredDeque([2, 3, 4], maxlen=3)
        """
        self._modified_callback = callback

    def __repr__(self) -> str:
        if self.maxlen is None:
            return f"{self.__class__.__name__}({list(self)!r})"
        return f"{self.__class__.__name__}({list(self)!r}, maxlen={self.maxlen!r})"

    # noinspection PyMethodParameters
    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        for item in self:
            yield None, item
        yield "maxlen", self.maxlen

    @_call_modified
    def __setitem__(self, __key: typing.SupportsIndex, __value: _T) -> None:  # type: ignore[override]
        # deque has no slice assignment, unlike list/MutableSequence -- see the class docstring.
        super().__setitem__(__key, __value)

    @_call_modified
    def __delitem__(self, __key: typing.SupportsIndex) -> None:  # type: ignore[override]
        # deque has no slice deletion, unlike list/MutableSequence -- see the class docstring.
        super().__delitem__(__key)

    @_call_modified
    def __iadd__(self, __value: Iterable[_T]) -> MonitoredDeque[_T]:
        return super().__iadd__(__value)

    @_call_modified
    def append(self, __object: _T) -> None:
        super().append(__object)

    @_call_modified
    def appendleft(self, __object: _T) -> None:
        super().appendleft(__object)

    @_call_modified
    def extend(self, __iterable: Iterable[_T]) -> None:
        super().extend(__iterable)

    @_call_modified
    def extendleft(self, __iterable: Iterable[_T]) -> None:
        super().extendleft(__iterable)

    @_call_modified
    def pop(self) -> _T:  # type: ignore[override]  # deque.pop takes no argument, unlike list.pop
        return super().pop()

    @_call_modified
    def popleft(self) -> _T:
        return super().popleft()

    @_call_modified
    def insert(self, __index: typing.SupportsIndex, __object: _T) -> None:
        super().insert(int(__index), __object)

    @_call_modified
    def remove(self, __value: _T) -> None:
        super().remove(__value)

    @_call_modified
    def reverse(self) -> None:
        super().reverse()

    @_call_modified
    def rotate(self, __n: int = 1) -> None:
        super().rotate(__n)

    @_call_modified
    def clear(self) -> None:
        super().clear()


class MonitoredFocusDeque(MonitoredDeque[_T], typing.Generic[_T]):
    """
    This class can trigger a callback any time its contents are modified,
    and any time the focus index is changed.

    Reuses the ``focus``/``_focus_changed``/``set_focus_changed_callback``
    machinery verbatim from :class:`MonitoredFocusList`.

    Deliberately **not** provided (an intentional simplification, unlike
    :class:`MonitoredFocusList`): ``_validate_contents_modified_callback``/
    ``set_validate_contents_modified`` and the slice-based
    ``_adjust_focus_on_contents_modified``. ``deque`` has no slice mutation,
    so there is no meaningful external-validation hook analogous to the list
    version. Instead a single-index helper, ``_adjust_focus_on_single_change``,
    is used by every mutating method below, since every ``deque`` mutation
    touches either a single item or the whole collection.

    **Edge cases:**

    * If the deque becomes empty, ``focus`` reads as ``None`` via the
      inherited getter -- no special-case code is needed for this.
    * If the focus item itself is evicted by a bounded ``append``/
      ``appendleft``, focus lands on the new boundary element -- it is
      never left dangling.
    * ``maxlen=0`` is legal (``deque(maxlen=0)`` stays permanently empty);
      ``focus`` stays ``None`` throughout, since ``not self`` is always
      true in that case:

      >>> mfd = MonitoredFocusDeque([1, 2, 3], maxlen=0)
      >>> mfd
      MonitoredFocusDeque([], maxlen=0, focus=None)
      >>> mfd.append(1)
      >>> print(mfd.focus)
      None
      >>> mfd
      MonitoredFocusDeque([], maxlen=0, focus=None)

    Replacing an item at a given index never changes which index is in
    focus (there is no dedicated ``__setitem__`` override for this reason --
    the inherited :meth:`MonitoredDeque.__setitem__` already covers it):

    >>> mfd = MonitoredFocusDeque([0, 1, 2, 3], focus=2)
    >>> mfd[0] = 9
    >>> mfd
    MonitoredFocusDeque([9, 1, 2, 3], focus=2)

    A longer example, exercising ``maxlen``, ``appendleft`` past capacity
    with a visible focus shift, ``popleft`` and ``rotate``:

    >>> mfd = MonitoredFocusDeque([1, 2, 3], maxlen=3, focus=2)
    >>> mfd
    MonitoredFocusDeque([1, 2, 3], maxlen=3, focus=2)
    >>> mfd.appendleft(0)
    >>> mfd
    MonitoredFocusDeque([0, 1, 2], maxlen=3, focus=2)
    """

    _focus_changed_callback: Callable[[int], typing.Any] | None = None

    def __init__(
        self,
        iterable: Iterable[_T] = (),
        maxlen: int | None = None,
        *,
        focus: int = 0,
    ) -> None:
        """
        This is a deque that tracks one item as the focus item.  If items
        are inserted or removed -- including items silently evicted by a
        bounded (``maxlen``-limited) deque -- it will update the focus.

        >>> mfd = MonitoredFocusDeque([10, 11, 12, 13, 14], focus=3)
        >>> mfd
        MonitoredFocusDeque([10, 11, 12, 13, 14], focus=3)
        >>> del mfd[1]
        >>> mfd
        MonitoredFocusDeque([10, 12, 13, 14], focus=2)
        >>> mfd.popleft()
        10
        >>> mfd
        MonitoredFocusDeque([12, 13, 14], focus=1)
        >>> mfd.clear()
        >>> mfd
        MonitoredFocusDeque([], focus=None)
        """
        super().__init__(iterable, maxlen)
        self._focus = focus

    def __repr__(self) -> str:
        if self.maxlen is None:
            return f"{self.__class__.__name__}({list(self)!r}, focus={self.focus!r})"
        return f"{self.__class__.__name__}({list(self)!r}, maxlen={self.maxlen!r}, focus={self.focus!r})"

    @property
    def focus(self) -> int | None:
        """
        Get/set the focus index.  This value is read as None when the
        deque is empty, and may only be set to a value between 0 and
        len(self)-1 or an IndexError will be raised.

        Return the index of the item "in focus" or None if
        the deque is empty.

        >>> MonitoredFocusDeque([1, 2, 3], focus=2).focus
        2
        >>> MonitoredFocusDeque().focus
        """
        if not self:
            return None
        return self._focus

    @focus.setter
    def focus(self, index: int) -> None:
        """Set the focus index.

        May call ``self._focus_changed`` when the focus is modified, passing the new focus
        position to the callback just before changing the old focus setting. The callback may
        be assigned with :meth:`set_focus_changed_callback`.

        :param index: index into this deque; any index out of range raises an ``IndexError``,
            except when the deque is empty, in which case the index passed is ignored

        >>> mfd = MonitoredFocusDeque([9, 10, 11])
        >>> mfd.focus = 2
        >>> mfd.focus
        2
        >>> mfd.focus = -2
        Traceback (most recent call last):
        ...
        IndexError: focus index is out of range: -2
        """
        if not self:
            self._focus = 0
            return
        if not isinstance(index, int):
            raise TypeError("index must be an integer")
        if index < 0 or index >= len(self):
            raise IndexError(f"focus index is out of range: {index}")

        if index != self._focus:
            self._focus_changed(index)
        self._focus = index

    def _focus_changed(self, new_focus: int) -> None:
        if self._focus_changed_callback is not None:
            self._focus_changed_callback(new_focus)

    def set_focus_changed_callback(self, callback: Callable[[int], typing.Any]) -> None:
        """Assign a callback to be called when the focus index changes for any reason.

        The callback is called as ``callback(new_focus)``.

        :param callback: called with the new focus index whenever the focus changes

        >>> import sys
        >>> mfd = MonitoredFocusDeque([1, 2, 3], focus=1)
        >>> mfd.set_focus_changed_callback(lambda f: sys.stdout.write("focus: %d\\n" % (f,)))
        >>> mfd.insert(1, 11)
        focus: 2
        >>> mfd
        MonitoredFocusDeque([1, 11, 2, 3], focus=2)
        >>> del mfd[0]
        focus: 1
        >>> mfd.focus = 0
        focus: 0
        """
        self._focus_changed_callback = callback

    def _adjust_focus_on_single_change(self, index: int, num_removed: int, num_inserted: int) -> int:
        """Compute the focus position for after a change applied at ``index``.

        Follows the same "focus follows the point of change, clamped to new length" logic as
        :meth:`MonitoredFocusList._adjust_focus_on_contents_modified`, specialised to the
        always-single-item-or-whole-collection mutations a deque supports.

        :param index: position at which the change is applied
        :param num_removed: number of items removed at ``index``
        :param num_inserted: number of items inserted at ``index``
        :returns: the focus position for after the change is applied
        """
        focus = self._focus
        if index <= focus < index + num_removed:
            focus = index + num_inserted
        elif index + num_removed <= focus:
            focus += num_inserted - num_removed

        new_len = len(self) - num_removed + num_inserted
        return max(0, min(focus, new_len - 1))

    # override all the deque methods that modify the deque, except __setitem__: replacing an item at a given
    # index never changes which index is in focus, so the inherited MonitoredDeque.__setitem__ needs no
    # focus-adjustment wrapper here (see the class docstring for a worked example).

    def __delitem__(self, index: typing.SupportsIndex) -> None:  # type: ignore[override]
        """Delete the item at ``index``, adjusting focus to follow the point of removal.

        :param index: position to delete

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3, 4], focus=2)
        >>> del mfd[3]
        >>> mfd
        MonitoredFocusDeque([0, 1, 2, 4], focus=2)
        >>> del mfd[-1]
        >>> mfd
        MonitoredFocusDeque([0, 1, 2], focus=2)
        >>> del mfd[0]
        >>> mfd
        MonitoredFocusDeque([1, 2], focus=1)
        >>> del mfd[1]
        >>> mfd
        MonitoredFocusDeque([1], focus=0)
        >>> del mfd[0]
        >>> mfd
        MonitoredFocusDeque([], focus=None)
        """
        idx = int(index)
        if idx < 0:
            idx += len(self)
        focus = self._adjust_focus_on_single_change(idx, 1, 0)
        super().__delitem__(index)
        self.focus = focus

    def append(self, item: _T) -> None:
        """Append ``item`` to the right end of the deque.

        Unless the deque was empty, focus is unaffected -- unless the deque is already at
        ``maxlen``, in which case the head item is evicted and focus follows it:
        ``focus = max(0, focus - 1)``.

        :param item: item to append

        >>> mfd = MonitoredFocusDeque([0, 1, 2], focus=2)
        >>> mfd.append(6)
        >>> mfd
        MonitoredFocusDeque([0, 1, 2, 6], focus=2)
        >>> bounded = MonitoredFocusDeque([0, 1, 2], maxlen=3, focus=2)
        >>> bounded.append(6)
        >>> bounded
        MonitoredFocusDeque([1, 2, 6], maxlen=3, focus=1)
        """
        was_full = self.maxlen is not None and len(self) == self.maxlen
        if not self:
            focus = 0
        elif was_full:
            focus = max(0, self._focus - 1)
        else:
            focus = self._focus
        super().append(item)
        self.focus = focus

    def appendleft(self, item: _T) -> None:
        """Append ``item`` to the left end of the deque.

        Unless the deque was empty, focus shifts right by one to keep tracking the same item --
        unless the deque is already at ``maxlen``, in which case the tail item is evicted: focus
        is clamped to the new tail, landing there if it was the evicted item.

        :param item: item to append

        >>> mfd = MonitoredFocusDeque([0, 1, 2], focus=0)
        >>> mfd.appendleft(6)
        >>> mfd
        MonitoredFocusDeque([6, 0, 1, 2], focus=1)
        >>> bounded = MonitoredFocusDeque([0, 1, 2], maxlen=3, focus=2)
        >>> bounded.appendleft(6)
        >>> bounded
        MonitoredFocusDeque([6, 0, 1], maxlen=3, focus=2)
        """
        was_full = self.maxlen is not None and len(self) == self.maxlen
        if not self:
            focus = 0
        elif was_full:
            focus = min(self._focus + 1, len(self) - 1)
        else:
            focus = self._focus + 1
        super().appendleft(item)
        self.focus = focus

    def extend(self, items: Iterable[_T]) -> None:
        """Extend the deque with ``items`` on the right end.

        :param items: items to append, in order

        >>> mfd = MonitoredFocusDeque([0, 1, 2], focus=2)
        >>> mfd.extend((6, 7, 8))
        >>> mfd
        MonitoredFocusDeque([0, 1, 2, 6, 7, 8], focus=2)
        >>> bounded = MonitoredFocusDeque([0, 1, 2], maxlen=4, focus=2)
        >>> bounded.extend((6, 7, 8))
        >>> bounded
        MonitoredFocusDeque([2, 6, 7, 8], maxlen=4, focus=0)
        """
        items_list = list(items)
        if self.maxlen is not None:
            evicted = max(0, len(items_list) - (self.maxlen - len(self)))
        else:
            evicted = 0
        focus = max(0, self._focus - evicted) if self else 0
        super().extend(items_list)
        self.focus = focus

    def extendleft(self, items: Iterable[_T]) -> None:
        """Extend the deque with ``items`` on the left end, each item prepended in turn.

        :param items: items to prepend, in order (so the last item ends up leftmost)

        >>> mfd = MonitoredFocusDeque([0, 1, 2], focus=0)
        >>> mfd.extendleft((6, 7, 8))
        >>> mfd
        MonitoredFocusDeque([8, 7, 6, 0, 1, 2], focus=3)
        >>> bounded = MonitoredFocusDeque([0, 1, 2], maxlen=4, focus=0)
        >>> bounded.extendleft((6, 7))
        >>> bounded
        MonitoredFocusDeque([7, 6, 0, 1], maxlen=4, focus=2)
        """
        items_list = list(items)
        focus = self._focus + len(items_list) if self else 0
        if self.maxlen is not None:
            focus = min(focus, self.maxlen - 1)
        super().extendleft(items_list)
        self.focus = focus

    def pop(self) -> _T:  # type: ignore[override]  # deque.pop takes no argument, unlike list.pop
        """Remove and return the tail item.

        Focus is unaffected unless it pointed at the tail item, in which case it moves to the
        new tail.

        :returns: the removed item

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3], focus=3)
        >>> mfd.pop()
        3
        >>> mfd
        MonitoredFocusDeque([0, 1, 2], focus=2)
        """
        focus = self._adjust_focus_on_single_change(len(self) - 1, 1, 0)
        rval = super().pop()
        self.focus = focus
        return rval

    def popleft(self) -> _T:
        """Remove and return the head item.

        Focus moves left by one, clamped at 0.

        :returns: the removed item

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3], focus=2)
        >>> mfd.popleft()
        0
        >>> mfd
        MonitoredFocusDeque([1, 2, 3], focus=1)
        """
        focus = self._adjust_focus_on_single_change(0, 1, 0)
        rval = super().popleft()
        self.focus = focus
        return rval

    def insert(self, index: typing.SupportsIndex, item: _T) -> None:
        """Insert ``item`` before ``index``.

        Note ``deque.insert`` itself raises ``IndexError`` on an already-full bounded deque,
        rather than evicting -- so there is no eviction case to handle here.

        :param index: position before which to insert
        :param item: item to insert

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3], focus=2)
        >>> mfd.insert(-1, -1)
        >>> mfd
        MonitoredFocusDeque([0, 1, 2, -1, 3], focus=2)
        >>> mfd.insert(0, -2)
        >>> mfd
        MonitoredFocusDeque([-2, 0, 1, 2, -1, 3], focus=3)
        """
        idx = int(index)
        if idx < 0:
            idx = max(0, len(self) + idx)
        else:
            idx = min(idx, len(self))
        focus = self._adjust_focus_on_single_change(idx, 0, 1)
        super().insert(index, item)
        self.focus = focus

    def remove(self, value: _T) -> None:
        """Remove the first occurrence of ``value``, adjusting focus to follow the removal.

        :param value: value to remove
        :raises ValueError: if ``value`` is not present

        >>> mfd = MonitoredFocusDeque([-2, 0, 1, -3, 2, -1, 3], focus=4)
        >>> mfd.remove(-3)
        >>> mfd
        MonitoredFocusDeque([-2, 0, 1, 2, -1, 3], focus=3)
        """
        index = self.index(value)
        focus = self._adjust_focus_on_single_change(index, 1, 0)
        super().remove(value)
        self.focus = focus

    def reverse(self) -> None:
        """Reverse the deque in place, keeping focus on the same item.

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3, 4], focus=1)
        >>> mfd.reverse()
        >>> mfd
        MonitoredFocusDeque([4, 3, 2, 1, 0], focus=3)
        """
        super().reverse()
        self.focus = max(0, len(self) - self._focus - 1)

    def rotate(self, n: int = 1) -> None:
        """Rotate the deque ``n`` steps to the right (or left, for negative ``n``).

        Carries the focus item along with the rotation -- there is no list precedent for this
        method.

        :param n: number of steps to rotate right (negative rotates left)

        >>> mfd = MonitoredFocusDeque([0, 1, 2, 3, 4], focus=0)
        >>> mfd.rotate()
        >>> mfd
        MonitoredFocusDeque([4, 0, 1, 2, 3], focus=1)
        >>> mfd.rotate(-2)
        >>> mfd
        MonitoredFocusDeque([1, 2, 3, 4, 0], focus=4)
        """
        super().rotate(n)
        if self:
            self.focus = (self._focus + n) % len(self)

    def clear(self) -> None:
        """Remove all items and reset focus to ``None``.

        >>> mfd = MonitoredFocusDeque([0, 1, 2], focus=1)
        >>> mfd.clear()
        >>> mfd
        MonitoredFocusDeque([], focus=None)
        """
        super().clear()
        self.focus = 0


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
