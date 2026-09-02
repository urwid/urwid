# Urwid DequeWalker classes
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

import typing
from collections.abc import Iterable

from .list_walker import ListWalker, ListWalkerError
from .monitored_deque import MonitoredDeque, MonitoredFocusDeque

if typing.TYPE_CHECKING:
    from collections.abc import Callable

_T = typing.TypeVar("_T")

__all__ = ("SimpleDequeWalker", "SimpleFocusDequeWalker")


class SimpleDequeWalker(
    MonitoredDeque[_T],
    ListWalker[int, _T],
):
    """A :class:`ListWalker` backed by a :class:`MonitoredDeque`.

    Mirrors :class:`SimpleListWalker` method-for-method,
    adapted to ``deque``'s narrower API (in particular, ``maxlen``-bounded eviction).

    .. note::
        :meth:`ListWalker.get_focus`/:meth:`ListWalker.get_next`/:meth:`ListWalker.get_prev`
        (inherited, unmodified) index via ``self[position]``, and ``deque.__getitem__``
        is O(n) (linked-block structure) rather than a list's O(1)
        -- worth bearing in mind for a very large unbounded deque,
        though the bounded/``maxlen`` scrollback use case this class targets is small enough
        that it does not matter in practice. No caching layer is provided.
    """

    def __init__(self, contents: Iterable[_T], wrap_around: bool = False, maxlen: int | None = None) -> None:
        """
        This class inherits :class:`MonitoredDeque` which means it can be treated as a deque.

        Changes made to this object (when it is treated as a deque) are detected automatically
        and will cause ListBox objects using this list walker to be updated.

        :param contents: iterable to copy into this object
        :param wrap_around: if true, jumps to beginning/end of deque on move
        :param maxlen: if set, bounds the deque's length; the oldest items are silently evicted
            from the opposite end once full
        """
        if not isinstance(contents, Iterable):
            raise ListWalkerError(f"SimpleDequeWalker expecting iterable object, got: {contents!r}")
        super().__init__(contents, maxlen)
        self.focus = 0
        self.wrap_around = wrap_around

    @property
    def contents(self) -> SimpleDequeWalker[_T]:
        """Return self.

        Provides compatibility with old SimpleListWalker class.
        """
        return self

    def _modified(self) -> None:
        if self.focus >= len(self):
            self.focus = max(0, len(self) - 1)
        ListWalker._modified(self)  # pylint: disable=protected-access

    def set_modified_callback(self, callback: Callable[[], typing.Any]) -> typing.NoReturn:
        """This function inherited from MonitoredDeque is not implemented in SimpleDequeWalker.

        Use ``connect_signal(list_walker, "modified", ...)`` instead.

        :raises NotImplementedError: always
        """
        raise NotImplementedError('Use connect_signal(list_walker, "modified", ...) instead.')

    def set_focus(self, position: int) -> None:
        """Set focus position.

        :param position: position to focus
        :raises IndexError: if there is no widget at ``position``
        """
        if not 0 <= position < len(self):
            raise IndexError(f"No widget at position {position}")

        self.focus = position
        self._modified()

    def next_position(self, position: int) -> int:
        """Return position after ``position``.

        :param position: position to start from
        :raises IndexError: if there is no next position and ``wrap_around`` is false
        """
        if len(self) - 1 <= position:
            if self.wrap_around:
                return 0
            raise IndexError
        return position + 1

    def prev_position(self, position: int) -> int:
        """Return position before ``position``.

        :param position: position to start from
        :raises IndexError: if there is no previous position and ``wrap_around`` is false
        """
        if position <= 0:
            if self.wrap_around:
                return len(self) - 1
            raise IndexError
        return position - 1

    def positions(self, reverse: bool = False) -> Iterable[int]:
        """Optional method for returning an iterable of positions.

        :param reverse: if true, return positions in reverse order
        """
        if reverse:
            return range(len(self) - 1, -1, -1)
        return range(len(self))


class SimpleFocusDequeWalker(
    MonitoredFocusDeque[_T],
    ListWalker[typing.SupportsIndex, _T],
):
    """A :class:`ListWalker` backed by a :class:`MonitoredFocusDeque`.

    Mirrors :class:`SimpleFocusListWalker` method-for-method, adapted to
    ``deque``'s narrower API. See the performance caveat documented on
    :class:`SimpleDequeWalker` -- it applies equally here.
    """

    def __init__(self, contents: Iterable[_T], wrap_around: bool = False, maxlen: int | None = None) -> None:
        """
        This class inherits :class:`MonitoredFocusDeque` which means it can be treated as a
        deque.

        Changes made to this object (when it is treated as a deque) are detected automatically
        and will cause ListBox objects using this list walker to be updated.

        Also, items added or removed before the widget in focus with normal deque methods --
        including eviction caused by ``maxlen`` -- will cause the focus to be updated
        intelligently.

        :param contents: iterable to copy into this object
        :param wrap_around: if true, jumps to beginning/end of deque on move
        :param maxlen: if set, bounds the deque's length; the oldest items are silently evicted
            from the opposite end once full, and focus is adjusted to keep tracking a sensible
            item (see :class:`MonitoredFocusDeque`)
        """
        if not isinstance(contents, Iterable):
            raise ListWalkerError(f"SimpleFocusDequeWalker expecting iterable object, got: {contents!r}")
        super().__init__(contents, maxlen)
        self.wrap_around = wrap_around

    def _modified(self) -> None:
        # Prefer ListWalker's signal emission over MonitoredDeque's callback hook.
        ListWalker._modified(self)  # pylint: disable=protected-access

    def set_modified_callback(self, callback: typing.Any) -> typing.NoReturn:
        """This function inherited from MonitoredFocusDeque is not implemented in SimpleFocusDequeWalker.

        Use ``connect_signal(list_walker, "modified", ...)`` instead.

        :raises NotImplementedError: always
        """
        raise NotImplementedError('Use connect_signal(list_walker, "modified", ...) instead.')

    def set_focus(self, position: int) -> None:
        """Set focus position.

        :param position: position to focus
        """
        self.focus = position
        self._modified()

    def next_position(self, position: typing.SupportsIndex) -> int:
        """Return position after ``position``.

        :param position: position to start from
        :raises IndexError: if there is no next position and ``wrap_around`` is false
        """
        pos = int(position)
        if len(self) - 1 <= pos:
            if self.wrap_around:
                return 0
            raise IndexError
        return pos + 1

    def prev_position(self, position: typing.SupportsIndex) -> int:
        """Return position before ``position``.

        :param position: position to start from
        :raises IndexError: if there is no previous position and ``wrap_around`` is false
        """
        pos = int(position)
        if pos <= 0:
            if self.wrap_around:
                return len(self) - 1
            raise IndexError
        return pos - 1

    def positions(self, reverse: bool = False) -> Iterable[int]:
        """Optional method for returning an iterable of positions.

        :param reverse: if true, return positions in reverse order
        """
        if reverse:
            return range(len(self) - 1, -1, -1)
        return range(len(self))
