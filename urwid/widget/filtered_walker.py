# Urwid FilteredListWalker class
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

"""A list walker that shows the items of another list walker which pass a predicate."""

from __future__ import annotations

import bisect
import typing
from collections.abc import Sequence

from urwid import signals

from .list_walker import ListWalker, SimpleFocusListWalker

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

_T = typing.TypeVar("_T")

__all__ = ("FilteredListWalker",)


class FilteredListWalker(ListWalker[int, _T]):
    """A read-only view of a source list walker that shows only the items passing a predicate.

    The positions of the view are the indices of the source, so a position taken from the view
    addresses the same item in :attr:`source`, and no mapping between two index spaces is needed.
    Items are added, removed and moved through :attr:`source`; the view has no methods that change the list.
    Every ``"modified"`` signal of the source re-applies the predicate, and the view emits its own ``"modified"``
    once per such rebuild.
    That includes the signal the source's own ``set_focus()`` emits; the view never changes the focus of the source.

    The focus of the view stays on the same widget while that widget passes the predicate. When it does not:

    - after a change to the source, or :meth:`refilter`, the focus moves to the next visible item
      at or after the old focus position, else to the last visible item;
    - after a change of the predicate, the focus moves to the first visible item.

    An empty view has no focus. When the widget focused last becomes visible again, it takes the focus back.

    A rebuild walks the source once, so it is linear in the length of a list or a deque source.
    Reading one item or the focus indexes the source, which is linear for a deque,
    as :class:`SimpleDequeWalker` notes.

    >>> import urwid
    >>> words = ("apple", "pear", "plum", "peach", "fig", "lime")
    >>> view = urwid.FilteredListWalker([urwid.Text(word) for word in words])
    >>> view.set_focus(2)
    >>> list(view.positions())
    [0, 1, 2, 3, 4, 5]
    >>> view.set_predicate(lambda widget: widget.text.startswith("pe"))
    >>> list(view.positions())
    [1, 3]
    >>> widget, position = view.get_focus()
    >>> widget.text, position
    ('pear', 1)
    """

    __slots__ = ("_focus", "_focus_widget", "_last_focus", "_predicate", "_source", "_visible", "wrap_around")

    def __init__(
        self,
        source: ListWalker[int, _T] | Iterable[_T],
        *,
        predicate: Callable[[_T], bool] | None = None,
        wrap_around: bool = False,
    ) -> None:
        """Create a view of *source* that shows the items for which *predicate* returns true.

        :param source: a list walker that is also a sequence, such as :class:`SimpleFocusListWalker`,
            :class:`SimpleFocusDequeWalker` or their non-focus variants.
            Any other iterable of widgets is copied into a new :class:`SimpleFocusListWalker`.
        :param predicate: called with each widget of the source; ``None`` shows every widget.
        :param wrap_around: if true, moving past one end of the visible items continues at the other end.
        :raises TypeError: *source* is a list walker that is not a sequence, such as a :class:`TreeWalker`.
        :raises ListWalkerError: *source* is not iterable.
        :raises Exception: whatever *predicate* raises for a widget of *source*.
        """
        if isinstance(source, ListWalker):
            if not isinstance(source, Sequence):
                raise TypeError(
                    f"FilteredListWalker needs a list walker that is a sequence, such as SimpleFocusListWalker, "
                    f"or an iterable of widgets; got {type(source).__name__}"
                )
            walker: Sequence[_T] = source
        else:
            walker = SimpleFocusListWalker(source)
        self._source = walker
        self._predicate = predicate
        self.wrap_around = wrap_around
        # Sorted source indices of the visible items. A rebuild replaces the list rather than changing it,
        # so an iterator returned by positions() keeps working through one.
        self._visible: list[int] = []
        # A source index in _visible, or None while the view is empty.
        self._focus: int | None = None
        # The widget and the position focused last, kept while the view is empty so a rebuild can recover them.
        self._focus_widget: _T | None = None
        self._last_focus = 0
        signals.connect_signal(walker, "modified", type(self)._source_modified, weak_args=[self])
        self._rebuild(predicate, after_source_change=False)

    @property
    def source(self) -> Sequence[_T]:
        """The list walker whose items the view shows, and the one to add, remove or move items through."""
        return self._source

    @property
    def predicate(self) -> Callable[[_T], bool] | None:
        """The function that decides which widgets are visible; ``None`` shows every widget."""
        return self._predicate

    @predicate.setter
    def predicate(self, predicate: Callable[[_T], bool] | None) -> None:
        self.set_predicate(predicate)

    def set_predicate(self, predicate: Callable[[_T], bool] | None) -> None:
        """Replace the predicate and show the widgets that pass it.

        :param predicate: called with each widget of the source; ``None`` shows every widget.
        :raises Exception: whatever *predicate* raises; the view then keeps its previous predicate and items.
        """
        self._rebuild(predicate, after_source_change=False)

    def refilter(self) -> None:
        """Apply the predicate again, after widgets of the source changed in place.

        :raises Exception: whatever the predicate raises; the view then keeps its previous items.
        """
        self._rebuild(self._predicate, after_source_change=True)

    def _source_modified(self) -> None:
        """Apply the predicate to the changed source."""
        self._rebuild(self._predicate, after_source_change=True)

    def _rebuild(self, predicate: Callable[[_T], bool] | None, *, after_source_change: bool) -> None:
        """Apply *predicate*, recompute the visible positions and the focus, then emit ``"modified"``.

        Nothing is changed until every widget has been checked, so a predicate that raises leaves the view as it was.

        :param predicate: the predicate to apply and keep.
        :param after_source_change: the source or its widgets changed, rather than the predicate.
        """
        focus_widget = self._focus_widget
        visible: list[int] = []
        # Visible positions holding the focused widget; one object may be listed more than once.
        candidates: list[int] = []
        for index, widget in enumerate(self._source):
            if predicate is None or predicate(widget):
                visible.append(index)
                if widget is focus_widget:
                    candidates.append(index)
        self._predicate = predicate
        self._visible = visible
        old = self._last_focus
        if candidates:
            self._focus = min(candidates, key=lambda index: abs(index - old))
        elif visible:
            if after_source_change:
                self._focus = visible[min(bisect.bisect_left(visible, old), len(visible) - 1)]
            else:
                self._focus = visible[0]
            self._focus_widget = self._source[self._focus]
        else:
            self._focus = None
        if self._focus is not None:
            self._last_focus = self._focus
        self._modified()

    def _is_visible(self, position: int) -> bool:
        """Return whether *position* is a visible source index."""
        index = bisect.bisect_left(self._visible, position)
        return index < len(self._visible) and self._visible[index] == position

    def __len__(self) -> int:
        """Return the number of visible widgets."""
        return len(self._visible)

    def __getitem__(self, position: int) -> _T:
        """Return the widget at the visible source index *position*.

        :raises IndexError: *position* is hidden by the predicate or out of range.
        """
        if not self._is_visible(position):
            raise IndexError(f"No visible widget at position {position}")
        return self._source[position]

    def get_focus(self) -> tuple[_T, int] | tuple[None, None]:
        """Return the ``(widget, position)`` in focus, or ``(None, None)`` when no widget is visible."""
        if self._focus is None:
            return None, None
        return self._source[self._focus], self._focus

    def set_focus(self, position: int) -> None:
        """Move the focus to the visible source index *position*.

        :raises IndexError: *position* is hidden by the predicate or out of range.
        """
        if not self._is_visible(position):
            raise IndexError(f"No visible widget at position {position}")
        self._focus = self._last_focus = position
        self._focus_widget = self._source[position]
        self._modified()

    def next_position(self, position: int) -> int:
        """Return the visible position after *position*.

        :raises IndexError: there is none and :attr:`wrap_around` is false.
        """
        index = bisect.bisect_right(self._visible, position)
        if index < len(self._visible):
            return self._visible[index]
        if self.wrap_around and self._visible:
            return self._visible[0]
        raise IndexError(f"No visible widget after position {position}")

    def prev_position(self, position: int) -> int:
        """Return the visible position before *position*.

        :raises IndexError: there is none and :attr:`wrap_around` is false.
        """
        index = bisect.bisect_left(self._visible, position)
        if index > 0:
            return self._visible[index - 1]
        if self.wrap_around and self._visible:
            return self._visible[-1]
        raise IndexError(f"No visible widget before position {position}")

    def positions(self, *, reverse: bool = False) -> Iterator[int]:
        """Return the visible positions in order.

        :param reverse: return them from the last to the first.
        """
        return reversed(self._visible) if reverse else iter(self._visible)
