# Urwid MonitoredList class
#    Copyright (C) 2004-2011  Ian Ward
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

"""Lists that call a callback when their contents or focus change."""

from __future__ import annotations

import functools
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Iterator
    from typing import Concatenate, ParamSpec, Self

    ArgSpec = ParamSpec("ArgSpec")
    Ret = typing.TypeVar("Ret")

__all__ = ("MonitoredFocusList", "MonitoredList")

_T = typing.TypeVar("_T")
_S = typing.TypeVar("_S")


def _call_modified(
    fn: Callable[Concatenate[MonitoredList[typing.Any], ArgSpec], Ret],
) -> Callable[Concatenate[MonitoredList[typing.Any], ArgSpec], Ret]:
    @functools.wraps(fn)
    def call_modified_wrapper(
        self: MonitoredList[typing.Any],
        /,
        *args: ArgSpec.args,
        **kwargs: ArgSpec.kwargs,
    ) -> Ret:
        rval = fn(self, *args, **kwargs)
        self._modified()  # pylint: disable=protected-access
        return rval

    return call_modified_wrapper


class MonitoredList(list[_T], typing.Generic[_T]):
    """Trigger a callback any time its contents are changed with the usual list operations append, extend, etc."""

    _modified_callback: Callable[[], typing.Any] | None = None

    def _modified(self) -> None:
        if self._modified_callback is not None:
            self._modified_callback()

    def set_modified_callback(self, callback: Callable[[], typing.Any]) -> None:
        r"""Assign a callback function with no parameters that is called any time the list is modified.

        Callback's return value is ignored.

        >>> import sys
        >>> ml = MonitoredList([1, 2, 3])
        >>> ml.set_modified_callback(lambda: sys.stdout.write("modified\n"))
        >>> ml
        MonitoredList([1, 2, 3])
        >>> ml.append(10)
        modified
        >>> len(ml)
        4
        >>> ml += [11, 12, 13]
        modified
        >>> ml[:] = ml[:2] + ml[-2:]
        modified
        >>> ml
        MonitoredList([1, 2, 12, 13])
        """
        self._modified_callback = callback

    def __repr__(self) -> str:
        """Return a constructor-call-like representation of the list's contents."""
        return f"{self.__class__.__name__}({list(self)!r})"

    # noinspection PyMethodParameters
    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield this list's items, for `rich`'s repr protocol."""
        for item in self:
            yield None, item

    # list.__add__/__rmul__ return a new list, not Self, and leave this list unchanged, so they do not notify.
    @typing.overload
    def __add__(self, __value: list[_T], /) -> list[_T]: ...

    @typing.overload
    def __add__(self, __value: list[_S], /) -> list[_T | _S]: ...

    def __add__(self, __value: list[typing.Any]) -> list[typing.Any]:
        """Return a new list with the items of `__value` appended."""
        return super().__add__(__value)

    @_call_modified
    def __delitem__(self, __key: typing.SupportsIndex | slice) -> None:
        """Delete the item or slice at `__key`."""
        super().__delitem__(__key)

    @_call_modified
    def __iadd__(self, __value: Iterable[_T]) -> Self:  # type: ignore[override]
        """Extend the list in place with the items from `__value`."""
        return super().__iadd__(__value)

    def __rmul__(self, __value: typing.SupportsIndex) -> list[_T]:
        """Return a new list with this list's items repeated `__value` times."""
        return super().__rmul__(__value)

    @_call_modified
    def __imul__(self, __value: typing.SupportsIndex) -> Self:
        """Repeat the list's contents `__value` times in place."""
        return super().__imul__(__value)

    @typing.overload
    def __setitem__(self, __key: typing.SupportsIndex, __value: _T) -> None: ...

    @typing.overload
    def __setitem__(self, __key: slice, __value: Iterable[_T]) -> None: ...

    @_call_modified
    def __setitem__(self, __key: typing.SupportsIndex | slice, __value: _T | Iterable[_T]) -> None:
        """Set the item or slice at `__key` to `__value`."""
        if isinstance(__key, slice):
            super().__setitem__(__key, typing.cast("Iterable[_T]", __value))
        else:
            super().__setitem__(__key, typing.cast("_T", __value))

    @_call_modified
    def append(self, __object: _T) -> None:
        """Append ``__object`` to the end of the list."""
        super().append(__object)

    @_call_modified
    def extend(self, __iterable: Iterable[_T]) -> None:
        """Extend the list with items from ``__iterable``."""
        super().extend(__iterable)

    @_call_modified
    def pop(self, __index: typing.SupportsIndex = -1) -> _T:
        """Remove and return the item at ``__index`` (default the last item)."""
        return super().pop(__index)

    @_call_modified
    def insert(self, __index: typing.SupportsIndex, __object: _T) -> None:
        """Insert ``__object`` before ``__index``."""
        super().insert(__index, __object)

    @_call_modified
    def remove(self, __value: _T) -> None:
        """Remove the first occurrence of ``__value``."""
        super().remove(__value)

    @_call_modified
    def reverse(self) -> None:
        """Reverse the list in place."""
        super().reverse()

    @_call_modified
    def sort(self, *, key: Callable[[_T], typing.Any] | None = None, reverse: bool = False) -> None:
        """Sort the list in place."""
        # pyrefly: ignore[no-matching-overload]  # an optional key is forwarded as is
        super().sort(key=key, reverse=reverse)

    @_call_modified
    def clear(self) -> None:
        """Remove all items from the list."""
        super().clear()


class MonitoredFocusList(MonitoredList[_T], typing.Generic[_T]):
    """Trigger a callback any time its contents are modified, before and/or after modification.

    Also triggers a callback any time the focus index is changed.
    """

    _focus_changed_callback: Callable[[int], typing.Any] | None = None
    _validate_contents_modified_callback: Callable[[tuple[int, int, int], Collection[_T]], int | None] | None = None

    def __init__(self, *args: typing.Any, focus: int = 0, **kwargs: typing.Any) -> None:
        """Initialize a list that tracks one item as the focus item.

        If items are inserted or removed it will update the focus.

        >>> ml = MonitoredFocusList([10, 11, 12, 13, 14], focus=3)
        >>> ml
        MonitoredFocusList([10, 11, 12, 13, 14], focus=3)
        >>> del ml[1]
        >>> ml
        MonitoredFocusList([10, 12, 13, 14], focus=2)
        >>> ml[:2] = [50, 51, 52, 53]
        >>> ml
        MonitoredFocusList([50, 51, 52, 53, 13, 14], focus=4)
        >>> ml[4] = 99
        >>> ml
        MonitoredFocusList([50, 51, 52, 53, 99, 14], focus=4)
        >>> ml[:] = []
        >>> ml
        MonitoredFocusList([], focus=None)
        """
        super().__init__(*args, **kwargs)

        self._focus = focus

    def __repr__(self) -> str:
        """Return a constructor-call-like representation of the list's contents and focus."""
        return f"{self.__class__.__name__}({list(self)!r}, focus={self.focus!r})"

    @property
    def focus(self) -> int | None:
        """Get/set the focus index.

        This value is read as None when the list is empty, and may only be set to a value between 0 and
        len(self)-1 or an IndexError will be raised.

        Return the index of the item "in focus" or None if
        the list is empty.

        >>> MonitoredFocusList([1, 2, 3], focus=2).focus
        2
        >>> MonitoredFocusList().focus
        """
        if not self:
            return None
        return self._focus

    @focus.setter
    def focus(self, index: int) -> None:
        """Set the focus index.

        :param index: index into this list, any index out of range will raise an IndexError, except when the list is
            empty and the index passed is ignored.
        :raises TypeError: *index* is not an integer.
        :raises IndexError: *index* is outside the range of this sequence.

        This function may call self._focus_changed when the focus
        is modified, passing the new focus position to the
        callback just before changing the old focus setting.
        The callback may be assigned with set_focus_changed_callback().

        >>> ml = MonitoredFocusList([9, 10, 11])
        >>> ml.focus = 2
        ... ml.focus
        2
        >>> ml.focus = 0
        ... ml.focus
        0
        >>> ml.focus = -2
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
        r"""
        Assign a callback to be called when the focus index changes for any reason.

        :param callback: a callable in the form ``callback(new_focus)``, where ``new_focus`` is the new focus index.

        >>> import sys
        >>> ml = MonitoredFocusList([1, 2, 3], focus=1)
        >>> ml.set_focus_changed_callback(lambda f: sys.stdout.write("focus: %d\n" % (f,)))
        >>> ml
        MonitoredFocusList([1, 2, 3], focus=1)
        >>> ml.append(10)
        >>> ml.insert(1, 11)
        focus: 2
        >>> ml
        MonitoredFocusList([1, 11, 2, 3, 10], focus=2)
        >>> del ml[:2]
        focus: 0
        >>> ml[:0] = [12, 13, 14]
        focus: 3
        >>> ml.focus = 5
        focus: 5
        >>> ml
        MonitoredFocusList([12, 13, 14, 2, 3, 10], focus=5)
        """
        self._focus_changed_callback = callback

    def _validate_contents_modified(
        self,
        indices: tuple[int, int, int],
        new_items: Collection[_T],
    ) -> int | None:
        if self._validate_contents_modified_callback is not None:
            return self._validate_contents_modified_callback(indices, new_items)
        return None

    def set_validate_contents_modified(
        self,
        callback: Callable[[tuple[int, int, int], Collection[_T]], int | None],
    ) -> None:
        """Assign a callback function to handle validating changes to the list.

        This may raise an exception if the change should not be performed.
        It may also return an integer position to be the new focus after the
        list is modified, or None to use the default behaviour.

        :param callback: a callable in the form ``callback(indices, new_items)``, where ``indices`` is a
            ``(start, stop, step)`` tuple whose range covers the items being modified, and ``new_items`` is an
            iterable of items replacing those at ``range(*indices)`` - empty if items are being removed, and, if
            ``step == 1``, of any length.
        """
        self._validate_contents_modified_callback = callback

    def _adjust_focus_on_contents_modified(self, slc: slice, new_items: Collection[_T] = ()) -> int:
        """Default behaviour is to move the focus to the item following any removed items.

        Unless that item was simply replaced, failing that choose the last item in the list.

        returns focus position for after change is applied
        """
        num_new_items = len(new_items)
        start, stop, step = indices = slc.indices(len(self))
        num_removed = len(list(range(*indices)))

        focus = self._validate_contents_modified(indices, new_items)
        if focus is not None:
            return focus

        focus = self._focus
        if step == 1:
            if start + num_new_items <= focus < stop:
                focus = stop
            # adjust for added/removed items
            if stop <= focus:
                focus += num_new_items - (stop - start)

        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            if not num_new_items:
                # extended slice being removed
                if focus in range(start, stop, step):
                    focus += 1

                # adjust for removed items
                focus -= sum(index < focus for index in range(start, stop, step))

        return min(focus, len(self) + num_new_items - num_removed - 1)

    def _modify(
        self,
        focus: int | Callable[[], int],
        change: Callable[ArgSpec, Ret],
        /,
        *args: ArgSpec.args,
        **kwargs: ArgSpec.kwargs,
    ) -> Ret:
        """Apply ``change(*args, **kwargs)``, set the focus, then send the modified notification once.

        The notification comes last so that its callback sees the new focus, and a focus it sets is kept.

        :param focus: the new focus index, or a callable returning it, called after the change
        :param change: the unmonitored operation applying the change
        :returns: what ``change`` returns
        :raises Exception: whatever ``change`` raises, leaving the focus as it was and notifying nothing;
            or whatever the focus-changed or the modified callback raises.
        :raises TypeError: the new focus is not an integer; the change is applied and notified.
        :raises IndexError: the new focus is out of range; the change is applied and notified.
        """
        rval = change(*args, **kwargs)
        try:
            self.focus = focus() if callable(focus) else focus
        finally:
            self._modified()
        return rval

    # override all the list methods that modify the list

    def __delitem__(self, y: typing.SupportsIndex | slice) -> None:
        """Delete items by index or slice, updating focus accordingly.

        >>> ml = MonitoredFocusList([0, 1, 2, 3, 4], focus=2)
        >>> del ml[3]
        >>> ml
        MonitoredFocusList([0, 1, 2, 4], focus=2)
        >>> del ml[-1]
        >>> ml
        MonitoredFocusList([0, 1, 2], focus=2)
        >>> del ml[0]
        >>> ml
        MonitoredFocusList([1, 2], focus=1)
        >>> del ml[1]
        >>> ml
        MonitoredFocusList([1], focus=0)
        >>> del ml[0]
        >>> ml
        MonitoredFocusList([], focus=None)
        >>> ml = MonitoredFocusList([5, 4, 6, 4, 5, 4, 6, 4, 5], focus=4)
        >>> del ml[1::2]
        >>> ml
        MonitoredFocusList([5, 6, 5, 6, 5], focus=2)
        >>> del ml[::2]
        >>> ml
        MonitoredFocusList([6, 6], focus=1)
        >>> ml = MonitoredFocusList([0, 1, 2, 3, 4, 6, 7], focus=2)
        >>> del ml[-2:]
        >>> ml
        MonitoredFocusList([0, 1, 2, 3, 4], focus=2)
        >>> del ml[-4:-2]
        >>> ml
        MonitoredFocusList([0, 3, 4], focus=1)
        >>> del ml[:]
        >>> ml
        MonitoredFocusList([], focus=None)
        """
        if isinstance(y, slice):
            focus = self._adjust_focus_on_contents_modified(y)
        else:
            idx = int(y)
            focus = self._adjust_focus_on_contents_modified(slice(idx, idx + 1 or None))
        self._modify(focus, super(MonitoredList, self).__delitem__, y)

    @typing.overload
    def __setitem__(self, i: typing.SupportsIndex, y: _T) -> None: ...

    @typing.overload
    def __setitem__(self, i: slice, y: Iterable[_T]) -> None: ...

    def __setitem__(self, i: typing.SupportsIndex | slice, y: _T | Iterable[_T]) -> None:
        """Replace items by index or slice, updating focus accordingly.

        >>> def modified(indices, new_items):
        ...     print(f"range{indices!r} <- {new_items!r}")
        >>> ml = MonitoredFocusList([0, 1, 2, 3], focus=2)
        >>> ml.set_validate_contents_modified(modified)
        >>> ml[0] = 9
        range(0, 1, 1) <- [9]
        >>> ml[2] = 6
        range(2, 3, 1) <- [6]
        >>> ml.focus
        2
        >>> ml[-1] = 8
        range(3, 4, 1) <- [8]
        >>> ml
        MonitoredFocusList([9, 1, 6, 8], focus=2)
        >>> ml[1::2] = [12, 13]
        range(1, 4, 2) <- [12, 13]
        >>> ml[::2] = [10, 11]
        range(0, 4, 2) <- [10, 11]
        >>> ml[-3:-1] = [21, 22, 23]
        range(1, 3, 1) <- [21, 22, 23]
        >>> ml
        MonitoredFocusList([10, 21, 22, 23, 13], focus=2)
        >>> ml[:] = []
        range(0, 5, 1) <- []
        >>> ml
        MonitoredFocusList([], focus=None)
        """
        if isinstance(i, slice):
            new_items = list(typing.cast("Iterable[_T]", y))
            focus = self._adjust_focus_on_contents_modified(i, new_items)
            self._modify(focus, super(MonitoredList, self).__setitem__, i, new_items)
        else:
            item = typing.cast("_T", y)
            idx = int(i)
            focus = self._adjust_focus_on_contents_modified(slice(idx, idx + 1 or None), [item])
            self._modify(focus, super(MonitoredList, self).__setitem__, i, item)

    def __imul__(self, n: typing.SupportsIndex) -> Self:
        """Repeat the list's contents `n` times in place, adjusting focus accordingly.

        >>> def modified(indices, new_items):
        ...     print(f"range{indices!r} <- {list(new_items)!r}")
        >>> ml = MonitoredFocusList([0, 1, 2], focus=2)
        >>> ml.set_validate_contents_modified(modified)
        >>> ml *= 3
        range(3, 3, 1) <- [0, 1, 2, 0, 1, 2]
        >>> ml
        MonitoredFocusList([0, 1, 2, 0, 1, 2, 0, 1, 2], focus=2)
        >>> ml *= 0
        range(0, 9, 1) <- []
        >>> print(ml.focus)
        None
        """
        multiplier = int(n)
        if multiplier > 0:
            focus = self._adjust_focus_on_contents_modified(slice(len(self), len(self)), list(self) * (multiplier - 1))
        else:  # all contents are being removed
            focus = self._adjust_focus_on_contents_modified(slice(0, len(self)))
        self._modify(focus, super(MonitoredList, self).__imul__, multiplier)
        return self

    def append(self, item: _T) -> None:
        """Append `item` to the list, adjusting focus accordingly.

        >>> def modified(indices, new_items):
        ...     print(f"range{indices!r} <- {new_items!r}")
        >>> ml = MonitoredFocusList([0, 1, 2], focus=2)
        >>> ml.set_validate_contents_modified(modified)
        >>> ml.append(6)
        range(3, 3, 1) <- [6]
        """
        focus = self._adjust_focus_on_contents_modified(slice(len(self), len(self)), [item])
        self._modify(focus, super(MonitoredList, self).append, item)

    def extend(self, items: Iterable[_T]) -> None:
        """Extend the list with `items`, adjusting focus accordingly.

        >>> def modified(indices, new_items):
        ...     print(f"range{indices!r} <- {list(new_items)!r}")
        >>> ml = MonitoredFocusList([0, 1, 2], focus=2)
        >>> ml.set_validate_contents_modified(modified)
        >>> ml.extend((6, 7, 8))
        range(3, 3, 1) <- [6, 7, 8]
        """
        items_list = list(items)
        focus = self._adjust_focus_on_contents_modified(slice(len(self), len(self)), items_list)
        self._modify(focus, super(MonitoredList, self).extend, items_list)

    def insert(self, index: typing.SupportsIndex, item: _T) -> None:
        """Insert `item` before `index`, adjusting focus accordingly.

        >>> ml = MonitoredFocusList([0, 1, 2, 3], focus=2)
        >>> ml.insert(-1, -1)
        >>> ml
        MonitoredFocusList([0, 1, 2, -1, 3], focus=2)
        >>> ml.insert(0, -2)
        >>> ml
        MonitoredFocusList([-2, 0, 1, 2, -1, 3], focus=3)
        >>> ml.insert(3, -3)
        >>> ml
        MonitoredFocusList([-2, 0, 1, -3, 2, -1, 3], focus=4)
        """
        focus = self._adjust_focus_on_contents_modified(slice(index, index), [item])
        self._modify(focus, super(MonitoredList, self).insert, index, item)

    def pop(self, index: typing.SupportsIndex = -1) -> _T:
        """Remove and return the item at `index`, adjusting focus accordingly.

        >>> ml = MonitoredFocusList([-2, 0, 1, -3, 2, 3], focus=4)
        >>> ml.pop(3)
        -3
        >>> ml
        MonitoredFocusList([-2, 0, 1, 2, 3], focus=3)
        >>> ml.pop(0)
        -2
        >>> ml
        MonitoredFocusList([0, 1, 2, 3], focus=2)
        >>> ml.pop(-1)
        3
        >>> ml
        MonitoredFocusList([0, 1, 2], focus=2)
        >>> ml.pop(2)
        2
        >>> ml
        MonitoredFocusList([0, 1], focus=1)
        """
        focus = self._adjust_focus_on_contents_modified(slice(index, int(index) + 1 or None))
        return self._modify(focus, super(MonitoredList, self).pop, index)

    def remove(self, value: _T) -> None:
        """Remove the first occurrence of `value`, adjusting focus accordingly.

        >>> ml = MonitoredFocusList([-2, 0, 1, -3, 2, -1, 3], focus=4)
        >>> ml.remove(-3)
        >>> ml
        MonitoredFocusList([-2, 0, 1, 2, -1, 3], focus=3)
        >>> ml.remove(-2)
        >>> ml
        MonitoredFocusList([0, 1, 2, -1, 3], focus=2)
        >>> ml.remove(3)
        >>> ml
        MonitoredFocusList([0, 1, 2, -1], focus=2)
        """
        index = self.index(value)
        focus = self._adjust_focus_on_contents_modified(slice(index, index + 1 or None))
        self._modify(focus, super(MonitoredList, self).remove, value)

    def reverse(self) -> None:
        """Reverse the list in place, adjusting focus accordingly.

        >>> ml = MonitoredFocusList([0, 1, 2, 3, 4], focus=1)
        >>> ml.reverse()
        >>> ml
        MonitoredFocusList([4, 3, 2, 1, 0], focus=3)
        """
        self._modify(max(0, len(self) - self._focus - 1), super(MonitoredList, self).reverse)

    def sort(
        self,
        *,
        key: Callable[[_T], typing.Any] | None = None,
        reverse: bool = False,
    ) -> None:
        """Sort the list in place, adjusting focus accordingly.

        >>> ml = MonitoredFocusList([-2, 0, 1, -3, 2, -1, 3], focus=4)
        >>> ml.sort()
        >>> ml
        MonitoredFocusList([-3, -2, -1, 0, 1, 2, 3], focus=5)
        """
        if not self:
            return None
        value = self[self._focus]
        return self._modify(
            lambda: self.index(value),
            # pyrefly: ignore[no-matching-overload]  # an optional key is forwarded as is
            lambda: super(MonitoredList, self).sort(key=key, reverse=reverse),
        )

    def clear(self) -> None:
        """Remove all items and reset focus to ``None``."""
        focus = self._adjust_focus_on_contents_modified(slice(0, 0))
        self._modify(focus, super(MonitoredList, self).clear)


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()
