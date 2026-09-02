# Urwid ListWalker classes
#    Copyright (C) 2004-2012  Ian Ward
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

from urwid import signals

from .monitored_list import MonitoredFocusList, MonitoredList

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from .widget import AbstractWidget

    _T = typing.TypeVar("_T")
    _K = typing.TypeVar("_K")
    _K_contra = typing.TypeVar("_K_contra", contravariant=True)
    _V_co = typing.TypeVar("_V_co", covariant=True)

    class ListWalkerContainer(typing.Protocol[_K, _V_co]):
        def __getitem__(self, key: _K) -> _V_co: ...

        def next_position(self, position: _K) -> _K: ...

        def prev_position(self, position: _K) -> _K: ...

    class ListBoxContentsProto(typing.Protocol[_K_contra]):
        """Read-only `(widget, options)` view over the :class:`ListBox` body."""

        def __getitem__(self, key: _K_contra) -> tuple[AbstractWidget, None]: ...

        def __len__(self) -> int: ...

else:
    _T = typing.TypeVar("_T")
    _K = typing.TypeVar("_K")
    _V_co = typing.TypeVar("_V_co", covariant=True)

__all__ = (
    "EstimatedSized",
    "ListWalker",
    "ListWalkerError",
    "ScrollSupportingBody",
    "SimpleFocusListWalker",
    "SimpleListWalker",
)


class ListWalkerError(Exception):
    pass


@typing.runtime_checkable
class ScrollSupportingBody(typing.Protocol):
    """Protocol for ListWalkers."""

    def get_focus(self) -> tuple[AbstractWidget, _K]: ...

    def set_focus(self, position: _K) -> None: ...

    def get_next(self, position: _K) -> tuple[AbstractWidget, _K] | tuple[None, None]: ...

    def get_prev(self, position: _K) -> tuple[AbstractWidget, _K] | tuple[None, None]: ...


@typing.runtime_checkable
class EstimatedSized(typing.Protocol):
    """Widget can estimate it's size.

    PEP 424 defines API for memory-efficiency.
    For the ListBox it's a sign of the limited body length.
    The main use-case is lazy-load, where real length calculation is expensive.
    """

    def __length_hint__(self) -> int: ...


class ListWalker(
    typing.Generic[_K, _V_co],
    metaclass=signals.MetaSignals,
):
    # mixin not named as mixin
    signals: typing.ClassVar[list[str]] = ["modified"]

    def _modified(self) -> None:
        signals.emit_signal(self, "modified")

    def get_focus(self) -> tuple[_V_co, _K] | tuple[None, None]:
        """Return the ``(widget, position)`` currently in focus.

        This default implementation relies on a ``focus`` attribute and a ``__getitem__()``
        method defined in a subclass.

        Override and don't call this method if these are not defined.

        :returns: ``(widget, position)`` or ``(None, None)``
        """
        try:
            # pylint: disable=no-member,unsubscriptable-object
            focus = self.focus  # type: ignore[attr-defined]  # we're OK with fail
            return typing.cast("ListWalkerContainer[_K, _V_co]", self)[focus], focus
        except (IndexError, KeyError, TypeError):
            return None, None

    def get_next(
        self,
        position: _K,
    ) -> tuple[_V_co, _K] | tuple[None, None]:
        """Return the ``(widget, position)`` after ``position``.

        This default implementation relies on a ``next_position()`` method and a
        ``__getitem__()`` method defined in a subclass.

        Override and don't call this method if these are not defined.

        :param position: position to start from
        :returns: ``(widget, position)`` or ``(None, None)``
        """
        try:
            # pylint: disable=no-member,unsubscriptable-object
            position = typing.cast("ListWalkerContainer[_K, _V_co]", self).next_position(position)
            return typing.cast("ListWalkerContainer[_K, _V_co]", self)[position], position
        except (IndexError, KeyError):
            return None, None

    def get_prev(
        self,
        position: _K,
    ) -> tuple[_V_co, _K] | tuple[None, None]:
        """Return the ``(widget, position)`` before ``position``.

        This default implementation relies on a ``prev_position()`` method and a
        ``__getitem__()`` method defined in a subclass.

        Override and don't call this method if these are not defined.

        :param position: position to start from
        :returns: ``(widget, position)`` or ``(None, None)``
        """
        try:
            # pylint: disable=no-member,unsubscriptable-object
            position = typing.cast("ListWalkerContainer[_K, _V_co]", self).prev_position(position)
            return typing.cast("ListWalkerContainer[_K, _V_co]", self)[position], position
        except (IndexError, KeyError):
            return None, None


class SimpleListWalker(
    MonitoredList[_T],
    ListWalker[int, _T],
):
    def __init__(self, contents: Iterable[_T], wrap_around: bool = False) -> None:
        """
        This class inherits :class:`MonitoredList` which means it can be treated as a list.

        Changes made to this object (when it is treated as a list) are detected automatically
        and will cause ListBox objects using this list walker to be updated.

        :param contents: list to copy into this object
        :param wrap_around: if true, jumps to beginning/end of list on move
        """
        if not isinstance(contents, Iterable):
            raise ListWalkerError(f"SimpleListWalker expecting list like object, got: {contents!r}")
        super().__init__(contents)
        self.focus = 0
        self.wrap_around = wrap_around

    @property
    def contents(self) -> Self:
        """Return self.

        Provides compatibility with old SimpleListWalker class.
        """
        return self

    def _modified(self) -> None:
        if self.focus >= len(self):
            self.focus = max(0, len(self) - 1)
        ListWalker._modified(self)  # pylint: disable=protected-access

    def set_modified_callback(self, callback: Callable[[], typing.Any]) -> typing.NoReturn:
        """This function inherited from MonitoredList is not implemented in SimpleListWalker.

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


class SimpleFocusListWalker(
    MonitoredFocusList[_T],
    ListWalker[typing.SupportsIndex, _T],
):
    def __init__(self, contents: Iterable[_T], wrap_around: bool = False) -> None:
        """
        This class inherits :class:`MonitoredList` which means it can be treated as a list.

        Changes made to this object (when it is treated as a list) are detected automatically
        and will cause ListBox objects using this list walker to be updated.

        Also, items added or removed before the widget in focus with normal list methods will
        cause the focus to be updated intelligently.

        :param contents: list to copy into this object
        :param wrap_around: if true, jumps to beginning/end of list on move
        """
        if not isinstance(contents, Iterable):
            raise ListWalkerError(f"SimpleFocusListWalker expecting iterable object, got: {contents!r}")
        super().__init__(contents)
        self.wrap_around = wrap_around

    def _modified(self) -> None:
        # Prefer ListWalker's signal emission over MonitoredList's callback hook.
        ListWalker._modified(self)  # pylint: disable=protected-access

    def set_modified_callback(self, callback: typing.Any) -> typing.NoReturn:
        """This function inherited from MonitoredList is not implemented in SimpleFocusListWalker.

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
