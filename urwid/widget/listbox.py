# Urwid listbox class
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


"""ListBox: a scrolling box container of widgets supplied by a list walker."""

from __future__ import annotations

import itertools
import operator
import typing
from collections.abc import Container, Iterable, Sized
from contextlib import suppress

from urwid import _deprecation, signals
from urwid.canvas import CanvasCombine, SolidCanvas

from .constants import Sizing, VAlign, WHSettings, normalize_valign
from .container import (
    _SELECT_COMMANDS,
    SelectNavigationMixin,
    _UnfocusedFocusAttrMixin,
)
from .deque_walker import SimpleDequeWalker, SimpleFocusDequeWalker
from .filler import calculate_top_bottom_filler
from .list_walker import (
    EstimatedSized,
    ListWalker,
    ListWalkerError,
    ScrollSupportingBody,
    SimpleFocusListWalker,
    SimpleListWalker,
)
from .widget import Widget, _select_enter_child, nocache_widget_render_instance

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterator
    from typing import Literal, Self

    from urwid.canvas import Canvas, CompositeCanvas

    from .attr_map import _AttrMapLike
    from .list_walker import ListBoxContentsProto
    from .widget import AbstractFlowWidget, AbstractWidget

    _K = typing.TypeVar("_K")
else:
    _K = typing.TypeVar("_K")

__all__ = (
    "ListBox",
    "ListBoxError",
    "ListWalker",
    "ListWalkerError",
    "SimpleDequeWalker",
    "SimpleFocusDequeWalker",
    "SimpleFocusListWalker",
    "SimpleListWalker",
    "VisibleInfo",
    "VisibleInfoFillItem",
    "VisibleInfoMiddle",
    "VisibleInfoTopBottom",
)


class ListBoxError(Exception):
    """ListBox related errors."""


def _snap_offset_inset(
    offset_inset: int,
    target_rows: int,
    maxrow: int,
    coming_from: Literal["above", "below"] | None,
    snap_rows: int,
) -> int:
    """Snap a selectable target into view without changing its cursor."""
    align_top = 0
    align_bottom = maxrow - target_rows
    if coming_from == "above" and offset_inset > align_bottom:
        if snap_rows >= offset_inset - align_bottom:
            offset_inset = align_bottom
        elif snap_rows >= offset_inset - align_top:
            offset_inset = align_top
        else:
            offset_inset -= snap_rows
    if coming_from == "below" and offset_inset < align_top:
        if snap_rows >= align_top - offset_inset:
            offset_inset = align_top
        elif snap_rows >= align_bottom - offset_inset:
            offset_inset = align_bottom
        else:
            offset_inset += snap_rows
    return offset_inset


def _pref_col_of(widget: AbstractFlowWidget, maxcol: int) -> int | str | None:
    """Return the preferred cursor column of *widget*, or ``None`` when it has none."""
    pref_col = None
    if hasattr(widget, "get_pref_col"):
        pref_col = widget.get_pref_col((maxcol,))
    if pref_col is None and hasattr(widget, "get_cursor_coords"):
        coords = widget.get_cursor_coords((maxcol,))
        if isinstance(coords, tuple):
            pref_col, _y = coords
    return pref_col


class VisibleInfoMiddle(typing.NamedTuple):
    """Named tuple for ListBox internals."""

    offset: int
    focus_widget: AbstractFlowWidget
    focus_pos: typing.Any
    focus_rows: int
    cursor: tuple[int, int] | None


class VisibleInfoFillItem(typing.NamedTuple):
    """Named tuple for ListBox internals."""

    widget: AbstractFlowWidget
    position: typing.Any
    rows: int


class VisibleInfoTopBottom(typing.NamedTuple):
    """Named tuple for ListBox internals."""

    trim: int
    fill: list[VisibleInfoFillItem]

    @classmethod
    def from_raw_data(
        cls,
        trim: int,
        fill: Iterable[tuple[AbstractFlowWidget, typing.Any, int]],
    ) -> Self:
        """Construct from not typed data.

        Useful for overridden cases.
        """
        return cls(trim=trim, fill=[VisibleInfoFillItem(*item) for item in fill])  # pragma: no cover


class VisibleInfo(typing.NamedTuple):
    """Named tuple for ListBox internals."""

    middle: VisibleInfoMiddle
    top: VisibleInfoTopBottom
    bottom: VisibleInfoTopBottom

    @classmethod
    def from_raw_data(
        cls,
        middle: tuple[int, AbstractFlowWidget, typing.Any, int, tuple[int, int] | None],
        top: tuple[int, Iterable[tuple[AbstractFlowWidget, typing.Any, int]]],
        bottom: tuple[int, Iterable[tuple[AbstractFlowWidget, typing.Any, int]]],
    ) -> Self:
        """Construct from not typed data.

        Useful for overridden cases.
        """
        return cls(  # pragma: no cover
            middle=VisibleInfoMiddle(*middle),
            top=VisibleInfoTopBottom.from_raw_data(*top),
            bottom=VisibleInfoTopBottom.from_raw_data(*bottom),
        )


class _SeenPositions(Container[typing.Any]):
    """Collection of walker positions already visited, for loops that must stop on a repeat.

    Positions are opaque objects that only promise ``==``.
    Hashable positions are kept in a set, so a lookup does not grow with the number visited.
    Once a position cannot be hashed, all of them move to a list and are compared with ``==``.
    """

    __slots__ = ("_hashed", "_listed")

    def __init__(self) -> None:
        """Create an empty collection."""
        self._hashed: set[object] = set()
        self._listed: list[object] | None = None

    def __contains__(self, position: object) -> bool:
        """Return whether a position equal to *position* was added."""
        if self._listed is not None:
            return position in self._listed
        try:
            return position in self._hashed
        except TypeError:
            return position in list(self._hashed)

    def add(self, position: object) -> None:
        """Add *position*."""
        if self._listed is None:
            try:
                self._hashed.add(position)
            except TypeError:
                self._listed = list(self._hashed)
            else:
                return
        self._listed.append(position)


class ListBox(Widget, SelectNavigationMixin[_K], _UnfocusedFocusAttrMixin):
    """Vertically stacked list of widgets."""

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    @typing.overload
    def __init__(
        self,
        body: ListWalker[_K, AbstractFlowWidget],
        *,
        select_navigation: bool = False,
        unfocused_focus_attr: _AttrMapLike | None = None,
        focus_when_empty: bool = True,
    ) -> None: ...

    @typing.overload
    def __init__(
        self: ListBox[int],
        body: Iterable[AbstractFlowWidget],
        *,
        select_navigation: bool = False,
        unfocused_focus_attr: _AttrMapLike | None = None,
        focus_when_empty: bool = True,
    ) -> None: ...

    def __init__(
        self,
        body: ListWalker[_K, AbstractFlowWidget] | Iterable[AbstractFlowWidget],
        *,
        select_navigation: bool = False,
        unfocused_focus_attr: _AttrMapLike | None = None,
        focus_when_empty: bool = True,
    ) -> None:
        """Create the ListBox widget.

        :param body: a ListWalker subclass such as :class:`SimpleFocusListWalker`
            that contains widgets to be displayed inside the list box
        :param select_navigation: handle the ``'next selectable'`` and ``'prev selectable'`` commands,
            see :ref:`select-navigation`.
        :param unfocused_focus_attr: attribute map applied to the focus child while the list box renders without
            focus, in any form :class:`AttrMap` takes; see :attr:`unfocused_focus_attr`.
        :param focus_when_empty: whether the ListBox accepts the input focus while its body is empty;
            ``False`` lets a container move the focus past an empty ListBox.

        .. deprecated:: 4.0.2
            Passing a *body* that is not a :class:`ListWalker` but has a ``get_focus`` method is deprecated.
            Support will be removed in version 7.0.
        """
        super().__init__()
        if isinstance(body, ListWalker):
            self._body: ListWalker[typing.Any, AbstractFlowWidget] = body
        elif getattr(body, "get_focus", None):
            self._body = typing.cast("ListWalker[typing.Any, AbstractFlowWidget]", body)
            _deprecation.warn(
                f"ListWalker or Iterable[Widget] argument expected, got: {type(body)}.",
                since="4.0.2",
                removed_in="7.0",
            )
        else:
            self._body = SimpleListWalker(body)

        self.body = self._body  # Initialization hack

        # offset_rows is the number of rows between the top of the view
        # and the top of the focused item
        self.offset_rows = 0
        # inset_fraction is used when the focused widget is off the
        # top of the view.  it is the fraction of the widget cut off
        # at the top.  (numerator, denominator)
        self.inset_fraction = (0, 1)

        # pref_col is the preferred column for the cursor when moving
        # between widgets that use the cursor (edit boxes etc.)
        self.pref_col: int | str = "left"

        # variable for delayed focus change used by set_focus
        self.set_focus_pending: (
            Literal["first selectable"] | tuple[Literal["above", "below"] | None, AbstractWidget, typing.Any] | None
        ) = "first selectable"

        # variable for delayed valign change used by set_focus_valign
        self.set_focus_valign_pending: tuple[VAlign | Literal[WHSettings.RELATIVE], int | None] | None = None

        # used for scrollable protocol
        self._rows_max_cached = 0
        self._rendered_size = 0, 0

        self.select_navigation = select_navigation
        self._set_unfocused_focus_attr(unfocused_focus_attr)
        # whether selectable() reports True while the body has no focus widget
        self.focus_when_empty = focus_when_empty

    def selectable(self) -> bool:
        """Return whether the ListBox accepts the input focus.

        With :attr:`focus_when_empty` ``False`` it does not while its body is empty.
        """
        return self._selectable and (self.focus_when_empty or self._body.get_focus()[0] is not None)

    def _invalidate(self) -> None:
        """Drop the cached canvases and the cached :meth:`rows_max` result."""
        self._rows_max_cached = 0
        super()._invalidate()

    @property
    def body(self) -> ListWalker[_K, AbstractFlowWidget]:
        """A ListWalker subclass such as :class:`SimpleFocusListWalker` that contains widgets.

        The widgets are to be displayed inside the list box.

        .. deprecated:: 4.0.2
            Assigning a body that is not a :class:`ListWalker` but has a ``get_focus`` method is deprecated.
            Support will be removed in version 7.0.
        """
        return typing.cast("ListWalker[_K, AbstractFlowWidget]", self._body)

    @body.setter
    def body(self, body: Iterable[AbstractFlowWidget] | ListWalker[_K, AbstractFlowWidget]) -> None:
        with suppress(AttributeError):
            signals.disconnect_signal(self._body, "modified", type(self)._invalidate, weak_args=[self])
            # _body may be not yet assigned

        if isinstance(body, ListWalker):
            self._body = body
        elif getattr(body, "get_focus", None):
            self._body = typing.cast("ListWalker[typing.Any, AbstractFlowWidget]", body)
            _deprecation.warn(
                f"ListWalker or Iterable[Widget] argument expected, got: {type(body)}.",
                since="4.0.2",
                removed_in="7.0",
            )
        else:
            self._body = SimpleListWalker(body)
        try:
            # A weak reference lets a ListBox over a long-lived walker be collected; the handler goes with it.
            signals.connect_signal(self._body, "modified", type(self)._invalidate, weak_args=[self])
        except NameError:
            # our list walker has no modified signal,
            # so we must not cache our canvases because we don't know when our content has changed
            self.render = nocache_widget_render_instance(self)  # type: ignore[method-assign,assignment]
        self._invalidate()

    @property
    def __len__(self) -> Callable[[], int]:
        """
        Return the length of the body, when the body reports one.

        :raises AttributeError: the body is not :class:`Sized`.
        """
        if isinstance(self._body, Sized):
            return self._body.__len__
        raise AttributeError(f"{self._body.__class__.__name__} is not Sized")

    @property
    def __length_hint__(self) -> Callable[[], int]:  # pylint: disable=invalid-length-hint-returned
        """
        Return an estimated length of the body, when the body can provide one.

        :raises AttributeError: the body is neither :class:`Sized` nor implements ``__length_hint__``.
        """
        if isinstance(self._body, (Sized, EstimatedSized)):
            return lambda: operator.length_hint(self._body)
        raise AttributeError(f'{self._body.__class__.__name__} is not Sized and do not implement "__length_hint__"')

    def calculate_visible(
        self,
        size: tuple[int, int],
        focus: bool = False,
    ) -> VisibleInfo | tuple[None, None, None]:
        """Return the widgets that would be displayed in the ListBox given the current *size* and *focus*.

        see :meth:`Widget.render` for parameter details

        :returns: (*middle*, *top*, *bottom*) or (``None``, ``None``, ``None``)

        *middle*
            (*row offset*(when +ve) or *inset*(when -ve),
            *focus widget*, *focus position*, *focus rows*,
            *cursor coords* or ``None``)
        *top*
            (*# lines to trim off top*,
            list of (*widget*, *position*, *rows*) tuples above focus in order from bottom to top)
        *bottom*
            (*# lines to trim off bottom*,
            list of (*widget*, *position*, *rows*) tuples below focus in order from top to bottom)
        """
        (maxcol, maxrow) = size

        # 0. set the focus if a change is pending; with no rows it waits for a size that has some
        if maxrow and (self.set_focus_pending or self.set_focus_valign_pending):
            self._set_focus_complete((maxcol, maxrow), focus)

        # 1. start with the focus widget
        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:  # list box is empty?
            return None, None, None

        return self._calculate_visible_around(
            (maxcol, maxrow),
            focus,
            (focus_widget, focus_pos),
            self.get_focus_offset_inset((maxcol, maxrow)),
        )

    def _calculate_visible_around(
        self,
        size: tuple[int, int],
        focus: bool,
        focus_at: tuple[AbstractFlowWidget, typing.Any],
        offset_inset: tuple[int, int],
    ) -> VisibleInfo:
        """Return what :meth:`calculate_visible` returns, laid out around the widget and position in *focus_at*.

        The body's focus is neither read nor moved, so the layout around a position other than the focus has no
        side effect on the body.

        :param focus_at: the widget to lay out as the focus, and its position in the body.
        :param offset_inset: rows between the top of the list box and the start of that widget,
            and rows of that widget hidden above the top of the list box.
        """
        (maxcol, maxrow) = size
        focus_widget, focus_pos = focus_at
        offset_rows, inset_rows = offset_inset

        #    force at least one line of focus to be visible
        if maxrow and offset_rows >= maxrow:
            offset_rows = maxrow - 1

        #    adjust position so cursor remains visible
        cursor = None
        if maxrow and focus_widget.selectable() and focus and hasattr(focus_widget, "get_cursor_coords"):
            cursor = focus_widget.get_cursor_coords((maxcol,))

        if cursor is not None:
            _cx, cy = cursor
            effective_cy = cy + offset_rows - inset_rows

            if effective_cy < 0:  # cursor above top?
                inset_rows = cy
            elif effective_cy >= maxrow:  # cursor below bottom?
                offset_rows = maxrow - cy - 1
                if offset_rows < 0:  # need to trim the top
                    inset_rows, offset_rows = -offset_rows, 0

        #    set trim_top by focus trimmimg
        trim_top = inset_rows
        focus_rows = focus_widget.rows((maxcol,), True)

        # 2. collect the widgets above the focus
        pos = focus_pos
        fill_lines = offset_rows
        fill_above = []
        top_pos = pos
        # A body that wraps around hands out the same widgets again once the list is exhausted.
        shown_pos = _SeenPositions()
        shown_pos.add(focus_pos)
        while fill_lines > 0:
            prev, pos = self._body.get_prev(pos)
            if prev is None or pos in shown_pos:  # run out of widgets above?
                offset_rows -= fill_lines
                break
            shown_pos.add(pos)
            top_pos = pos

            p_rows = prev.rows((maxcol,))
            if p_rows:  # filter out 0-height widgets
                fill_above.append(VisibleInfoFillItem(prev, pos, p_rows))
            if p_rows > fill_lines:  # crosses top edge?
                trim_top = p_rows - fill_lines
                break
            fill_lines -= p_rows

        trim_bottom = max(focus_rows + offset_rows - inset_rows - maxrow, 0)

        # 3. collect the widgets below the focus
        pos = focus_pos
        fill_lines = maxrow - focus_rows - offset_rows + inset_rows
        fill_below = []
        while fill_lines > 0:
            next_pos, pos = self._body.get_next(pos)
            if next_pos is None or pos in shown_pos:  # run out of widgets below?
                break
            shown_pos.add(pos)

            n_rows = next_pos.rows((maxcol,))
            if n_rows:  # filter out 0-height widgets
                fill_below.append(VisibleInfoFillItem(next_pos, pos, n_rows))
            if n_rows > fill_lines:  # crosses bottom edge?
                trim_bottom = n_rows - fill_lines
                fill_lines -= n_rows
                break
            fill_lines -= n_rows

        # 4. fill from top again if necessary & possible
        fill_lines = max(0, fill_lines)

        if fill_lines > 0 and trim_top > 0:
            if fill_lines <= trim_top:
                trim_top -= fill_lines
                offset_rows += fill_lines
                fill_lines = 0
            else:
                fill_lines -= trim_top
                offset_rows += trim_top
                trim_top = 0
        pos = top_pos
        while fill_lines > 0:
            prev, pos = self._body.get_prev(pos)
            if prev is None or pos in shown_pos:
                break
            shown_pos.add(pos)

            p_rows = prev.rows((maxcol,))
            fill_above.append(VisibleInfoFillItem(prev, pos, p_rows))
            if p_rows > fill_lines:  # more than required
                trim_top = p_rows - fill_lines
                offset_rows += fill_lines
                break
            fill_lines -= p_rows
            offset_rows += p_rows

        # 5. return the interesting bits
        return VisibleInfo(
            VisibleInfoMiddle(offset_rows - inset_rows, focus_widget, focus_pos, focus_rows, cursor),
            VisibleInfoTopBottom(trim_top, fill_above),
            VisibleInfoTopBottom(trim_bottom, fill_below),
        )

    def _check_support_scrolling(self) -> None:
        """
        Reject the body if it cannot support the scrolling protocol.

        :raises ListBoxError: the body does not implement the scrolling protocol, its size cannot be estimated, or it
            wraps around, which leaves the scroll position undefined.
        """
        from .treetools import TreeWalker

        if not isinstance(self._body, ScrollSupportingBody):
            raise ListBoxError(f"{self} body do not implement methods required for scrolling protocol")

        if not isinstance(self._body, (Sized, EstimatedSized, TreeWalker)):
            raise ListBoxError(
                f"{self} body is not a Sized, can not estimate it's size and not a TreeWalker."
                f"Scroll is not allowed due to risk of infinite cycle of widgets load."
            )

        if getattr(self._body, "wrap_around", False):
            raise ListBoxError("Body is wrapped around. Scroll position calculation is undefined.")

    def _walk_body(self, position: typing.Any, forward: bool) -> Iterator[tuple[AbstractFlowWidget, typing.Any]]:
        """Yield the widgets and positions after *position*, or before it when *forward* is false.

        :raises ListBoxError: the walk comes back to *position*: the body wraps around without saying so.
        """
        start = position
        while True:
            widget, position = self._body.get_next(position) if forward else self._body.get_prev(position)
            if widget is None:
                return
            if position == start:
                raise ListBoxError("Body is wrapped around. Scroll position calculation is undefined.")
            yield widget, position

    def get_scrollpos(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Return the current scrolling position."""
        self._check_support_scrolling()

        if not self._body:
            return 0

        if size is not None:
            self._rendered_size = size

        visible = typing.cast("VisibleInfo", self.calculate_visible(self._rendered_size, focus))

        start_row = visible.top.trim
        maxcol = self._rendered_size[0]

        if visible.top.fill:
            pos = visible.top.fill[-1].position
        else:
            pos = visible.middle.focus_pos

        for prev, _pos in self._walk_body(pos, forward=False):
            start_row += prev.rows((maxcol,))

        return start_row

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the rows of all widgets in the body at the width in *size*.

        The focus widget is measured in focus and the others out of focus, as a render measures them,
        whatever *focus* is.
        A child whose row count depends on its focus breaks the box layout as well,
        which a render reports as a :exc:`ListBoxError`.

        >>> from urwid import Text
        >>> ListBox([Text("one two"), Text("three")]).rows((5,))
        3

        :raises ListBoxError: the body does not support the scrolling protocol, or it wraps around.
        """
        self._check_support_scrolling()
        return self._body_rows(size[0])

    def _body_rows(self, maxcol: int) -> int:
        """Return the rows of all widgets in the body at width *maxcol*, the focus widget measured in focus."""
        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            return 0

        rows = focus_widget.rows((maxcol,), True)
        for forward in (False, True):
            for widget, _pos in self._walk_body(focus_pos, forward=forward):
                rows += widget.rows((maxcol,))
        return rows

    def rows_max(self, size: tuple[int, int] | None = None, focus: bool = False) -> int:
        """Scrollable protocol for sized iterable and not wrapped around contents."""
        self._check_support_scrolling()

        if size is not None:
            self._rendered_size = size

        if size or not self._rows_max_cached:
            self._rows_max_cached = self._body_rows(self._rendered_size[0])

        return self._rows_max_cached

    def _box_size(self, size: tuple[int] | tuple[int, int], focus: bool) -> tuple[int, int]:
        """Return *size* as a box size, measuring the body for a flow size."""
        if len(size) == 1:
            return (size[0], self.rows((size[0],), focus))
        return size

    def require_relative_scroll(self, size: tuple[int, int], focus: bool = False) -> bool:
        """Widget require relative scroll due to performance limitations of real lines count calculation."""
        return isinstance(self._body, (Sized, EstimatedSized)) and (size[1] * 3 < operator.length_hint(self.body))

    def get_first_visible_pos(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the index of the first visible item."""
        self._check_support_scrolling()

        if not self._body:
            return 0

        visible = typing.cast("VisibleInfo", self.calculate_visible(size, focus))
        if visible.top.fill:
            first_pos = visible.top.fill[-1].position
        else:
            first_pos = self.focus_position

        return sum(1 for _ in self._walk_body(first_pos, forward=False))

    def get_visible_amount(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the number of items currently visible."""
        self._check_support_scrolling()

        if not self._body:
            return 1

        visible = typing.cast("VisibleInfo", self.calculate_visible(size, focus))
        return 1 + len(visible.top.fill) + len(visible.bottom.fill)

    def render(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas | SolidCanvas:
        """
        Render ListBox and return canvas.

        see :meth:`Widget.render` for details

        A flow *size* renders every widget of the body, with the rows :meth:`rows` reports.

        :raises ListBoxError: the rendered contents do not fit the reported rows, a child widget renders a different
            number of rows or cursor coordinates than it calculated, or the list walker returns a next position pointing
            at itself.
        """
        (maxcol, maxrow) = self._rendered_size = self._box_size(size, focus)

        middle, top, bottom = self.calculate_visible((maxcol, maxrow), focus=focus)
        if middle is None:
            return SolidCanvas(" ", maxcol, maxrow)

        _ignore, focus_widget, focus_pos, focus_rows, cursor = middle  # pylint: disable=unpacking-non-sequence
        trim_top, fill_above = typing.cast("VisibleInfoTopBottom", top)  # pylint: disable=unpacking-non-sequence
        trim_bottom, fill_below = typing.cast("VisibleInfoTopBottom", bottom)  # pylint: disable=unpacking-non-sequence

        combinelist: list[tuple[Canvas, Hashable, bool]] = []
        rows = 0
        fill_above.reverse()  # fill_above is in bottom-up order
        for widget, w_pos, w_rows in fill_above:
            canvas = widget.render((maxcol,))
            if w_rows != canvas.rows():
                raise ListBoxError(
                    f"Widget {widget!r} at position {w_pos!r} "
                    f"within listbox calculated {w_rows:d} rows "
                    f"but rendered {canvas.rows():d}!"
                )
            rows += w_rows
            combinelist.append((canvas, w_pos, False))

        focus_canvas = focus_widget.render((maxcol,), focus=focus)
        if not focus:
            focus_canvas = self._mark_unfocused_focus(focus_canvas)

        if focus_canvas.rows() != focus_rows:
            raise ListBoxError(
                f"Focus Widget {focus_widget!r} at position {focus_pos!r} "
                f"within listbox calculated {focus_rows:d} rows "
                f"but rendered {focus_canvas.rows():d}!"
            )
        c_cursor = focus_canvas.cursor
        if cursor is not None and cursor != c_cursor:
            raise ListBoxError(
                f"Focus Widget {focus_widget!r} at position {focus_pos!r} "
                f"within listbox calculated cursor coords {cursor!r} "
                f"but rendered cursor coords {c_cursor!r}!"
            )

        rows += focus_rows
        combinelist.append((focus_canvas, focus_pos, True))

        for widget, w_pos, w_rows in fill_below:
            canvas = widget.render((maxcol,))
            if w_rows != canvas.rows():
                raise ListBoxError(
                    f"Widget {widget!r} at position {w_pos!r} "
                    f"within listbox calculated {w_rows:d} "
                    f"rows but rendered {canvas.rows():d}!"
                )
            rows += w_rows
            combinelist.append((canvas, w_pos, False))

        final_canvas = CanvasCombine(combinelist)

        if trim_top:
            final_canvas.trim(trim_top)
            rows -= trim_top
        if trim_bottom:
            final_canvas.trim_end(trim_bottom)
            rows -= trim_bottom

        if rows > maxrow:
            raise ListBoxError(
                f"Listbox contents too long!\nRender top={top!r}, middle={middle!r}, bottom={bottom!r}\n"
            )

        if rows < maxrow:
            if trim_bottom != 0:
                raise ListBoxError(
                    f"Listbox contents too short!\n"
                    f"Render top={top!r}, middle={middle!r}, bottom={bottom!r}\n"
                    f"Trim bottom={trim_bottom!r}"
                )

            bottom_pos = focus_pos
            if fill_below:
                bottom_pos = fill_below[-1][1]

            rendered_positions = [idx for _, idx, _ in combinelist]
            next_widget, next_pos = self._body.get_next(bottom_pos)
            while next_widget is not None and next_pos is not None and next_pos not in rendered_positions:
                if next_widget.rows((maxcol,), False):
                    raise ListBoxError(
                        f"Listbox contents too short!\n"
                        f"Render top={top!r}, middle={middle!r}, bottom={bottom!r}\n"
                        f"Not rendered not empty widgets available "
                        f"(first is {next_widget!r} with position {next_pos!r})"
                    )

                next_widget, next_next_pos = self._body.get_next(next_pos)
                if next_pos == next_next_pos:
                    raise ListBoxError(
                        f"Next position after {next_pos!r} is invalid (points to itself)\n"
                        f"Looks like bug with {self._body!r}"
                    )
                next_pos = next_next_pos

            final_canvas.pad_trim_top_bottom(0, maxrow - rows)

        return final_canvas

    def get_cursor_coords(self, size: tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """See :meth:`Widget.get_cursor_coords` for details."""
        (maxcol, maxrow) = self._box_size(size, True)

        middle, _top, _bottom = self.calculate_visible((maxcol, maxrow), True)
        if middle is None:
            return None

        offset_inset, _ignore1, _ignore2, _ignore3, cursor = middle  # pylint: disable=unpacking-non-sequence
        if not cursor:
            return None

        x, y = cursor
        y += offset_inset
        if y < 0 or y >= maxrow:
            return None
        return (x, y)

    def set_focus_valign(
        self,
        valign: Literal["top", "middle", "bottom"] | VAlign | tuple[Literal["relative", WHSettings.RELATIVE], int],
    ) -> None:
        """Set the focus widget's display offset and inset.

        :param valign: one of: 'top', 'middle', 'bottom' ('relative', percentage 0=top 100=bottom)
        """
        vt, va = normalize_valign(valign, ListBoxError)
        self.set_focus_valign_pending = vt, va
        self._invalidate()

    def set_focus(self, position: _K, coming_from: Literal["above", "below"] | None = None) -> None:
        """
        Set the focus position and try to keep the old focus in view.

        Without *coming_from*, preserve the target widget's cursor and nested focus.
        With *coming_from*, move its cursor from the indicated edge.

        :param position: a position compatible with :meth:`self._body.set_focus`
        :param coming_from: set to 'above' or 'below' if you know that
                            old position is above or below the new position.
        :raises ListBoxError: *coming_from* is not ``'above'``, ``'below'`` or ``None``.
        :raises TypeError: the body does not implement ``set_focus``.
        :raises IndexError: the ListBox is empty.
        """
        if coming_from not in {"above", "below", None}:
            raise ListBoxError(f"coming_from value invalid: {coming_from!r}")

        if not hasattr(self._body, "set_focus"):
            raise TypeError(f"{type(self._body)}.set_focus is not implemented.")

        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            raise IndexError("Can't set focus, ListBox is empty")

        self.set_focus_pending = coming_from, focus_widget, focus_pos
        self._body.set_focus(position)

    @property
    def focus(self) -> AbstractFlowWidget | None:
        """
        The child widget in focus or None when ListBox is empty.

        Return the widget in focus according to our :obj:`list walker <ListWalker>`.
        """
        return self._body.get_focus()[0]

    def _get_focus_position(self) -> _K:
        """Return the list walker position of the widget in focus.

        The type of value returned depends on the :obj:`list walker <ListWalker>`.

        :raises IndexError: the ListBox is empty.
        """
        w, pos = self._body.get_focus()
        if w is None:
            raise IndexError("No focus_position, ListBox is empty")
        # the walker reports position `None` only together with the widget
        return typing.cast("_K", pos)

    @property  # type: ignore[override]  # walker positions are not limited to int | str
    def focus_position(self) -> _K:
        """Return the position of the child widget in focus.

        The valid values for this position depend on the list walker in use.

        :raises IndexError: the ListBox is empty.
        """
        return self._get_focus_position()

    @focus_position.setter
    def focus_position(self, position: _K) -> None:
        """Set the focus to *position* through :meth:`set_focus`, so an override in a subclass applies.

        :raises IndexError: *position* is not valid for the list walker.
        """
        self.set_focus(position)

    def _contents(self) -> ListBoxContentsProto[_K]:
        # noinspection PyMethodParameters
        class ListBoxContents(Sized):
            """Mapping-like view onto this ListBox's items, indexed by position."""

            # pylint: disable=no-self-argument

            __getitem__ = self._contents__getitem__

            def __len__(inner_self) -> int:
                return self.__len__()

            def __repr__(inner_self) -> str:
                return f"<{inner_self.__class__.__name__} for {self!r} at 0x{id(inner_self):X}>"

        return ListBoxContents()

    def _contents__getitem__(self, key: _K) -> tuple[AbstractFlowWidget, None]:
        # try list walker protocol v2 first
        """
        Return the ``(widget, options)`` pair at *key*, for the container contents protocol.

        :raises TypeError: the body does not implement ``set_focus``.
        :raises KeyError: *key* is not a position in the body.
        """
        if hasattr(self._body, "__getitem__"):
            try:
                # pyrefly: ignore[bad-index]  # pyrefly does not narrow on hasattr(..., "__getitem__")
                return (self._body[key], None)
            except (IndexError, KeyError) as exc:
                raise KeyError(f"ListBox.contents key not found: {key!r}").with_traceback(exc.__traceback__) from exc
        # fall back to v1
        if not hasattr(self._body, "set_focus"):
            raise TypeError(f"{type(self._body)}.set_focus is not implemented.")

        _w, old_focus = self._body.get_focus()

        try:
            self._body.set_focus(key)
            widget, _pos = self._body.get_focus()
        except (IndexError, KeyError) as exc:
            raise KeyError(f"ListBox.contents key not found: {key!r}").with_traceback(exc.__traceback__) from exc
        finally:
            self._body.set_focus(old_focus)
        if widget is None:
            raise KeyError(f"ListBox.contents key not found: {key!r}")
        return (widget, None)

    @property
    def contents(self) -> ListBoxContentsProto[_K]:
        """An object that allows reading widgets from the ListBox's list walker.

        Widgets are read as a `(widget, options)` tuple. `None` is currently the only value for options.

        .. warning::

            This object may not be used to set or iterate over contents.

            You must use the list walker stored as
            :attr:`.body` to perform manipulation and iteration, if supported.
        """
        return self._contents()

    def options(self) -> None:
        """
        There are currently no options for ListBox contents.

        Return None as a placeholder for future options.
        """

    def _set_focus_valign_complete(self, size: tuple[int, int], focus: bool) -> None:
        """Finish setting the offset and inset now that we have have a maxcol & maxrow."""
        (maxcol, maxrow) = size
        pending = self.set_focus_valign_pending
        if pending is None:  # pragma: no cover  # only called with a pending valign
            return
        vt, va = pending
        self.set_focus_valign_pending = None
        self.set_focus_pending = None

        focus_widget, _focus_pos = self._body.get_focus()
        if focus_widget is None:
            return

        rows = focus_widget.rows((maxcol,), focus)
        rtop, _rbot = calculate_top_bottom_filler(
            maxrow,
            vt,
            va,
            WHSettings.GIVEN,
            rows,
            None,
            0,
            0,
        )

        # A 0-height focus aligned at or near the bottom would start below the last row: put it on the last row.
        self.shift_focus((maxcol, maxrow), min(rtop, maxrow - 1))

    def _set_focus_first_selectable(self, size: tuple[int, int], focus: bool) -> None:
        """Choose the first visible, selectable widget below the current focus as the focus widget.

        :raises TypeError: the body does not implement ``set_focus``.
        """
        (maxcol, maxrow) = size
        self.set_focus_valign_pending = None
        self.set_focus_pending = None
        middle, top, bottom = self.calculate_visible((maxcol, maxrow), focus=focus)
        if middle is None or top is None or bottom is None:
            return

        row_offset, focus_widget, _focus_pos, focus_rows, _cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_top, _fill_above = top  # pylint: disable=unpacking-non-sequence
        trim_bottom, fill_below = bottom  # pylint: disable=unpacking-non-sequence

        if focus_widget.selectable():
            return

        if not hasattr(self._body, "set_focus"):
            raise TypeError(f"{type(self._body)}.set_focus is not implemented.")

        if trim_bottom:
            fill_below = fill_below[:-1]
        new_row_offset = row_offset + focus_rows
        for widget, pos, rows in fill_below:
            if widget.selectable():
                self._body.set_focus(pos)
                self.shift_focus((maxcol, maxrow), new_row_offset)
                return
            new_row_offset += rows

    def _body_widget_at(self, position: typing.Any) -> AbstractFlowWidget | None:
        """Return the body's widget at *position* without moving the body's focus.

        It steps from a neighbour back to *position* with ``get_prev()`` and ``get_next()``.
        A body that has no ``__getitem__`` supports that too.

        :returns: the widget, or ``None`` when *position* is no longer in the body.
        """
        try:
            prev_widget, prev_pos = self._body.get_prev(position)
            if prev_widget is not None:
                widget, pos = self._body.get_next(prev_pos)
            else:
                next_widget, next_pos = self._body.get_next(position)
                if next_widget is None:
                    return None
                widget, pos = self._body.get_prev(next_pos)
        except (IndexError, KeyError):
            # A body may reject a position it no longer holds instead of reporting no neighbour.
            return None
        return widget if pos == position else None

    def _set_focus_complete(self, size: tuple[int, int], focus: bool) -> None:
        """Finish setting the position now that we have maxcol & maxrow.

        :raises TypeError: the body does not implement ``set_focus``.
        """
        (maxcol, maxrow) = size
        self._invalidate()
        if self.set_focus_pending == "first selectable":
            return self._set_focus_first_selectable((maxcol, maxrow), focus)
        if self.set_focus_valign_pending is not None:
            return self._set_focus_valign_complete((maxcol, maxrow), focus)
        pending = self.set_focus_pending
        if pending is None or isinstance(pending, str):  # pragma: no cover  # nothing to complete
            return None
        coming_from, _focus_widget, focus_pos = pending
        self.set_focus_pending = None

        # new position
        new_focus_widget, position = self._body.get_focus()
        if focus_pos == position or new_focus_widget is None:
            # nothing moved, or the body was emptied after ListBox.set_focus()
            return None

        if not hasattr(self._body, "set_focus"):
            raise TypeError(f"{type(self._body)}.set_focus is not implemented.")

        # The old focus is laid out where it is, without moving the body's focus back to it,
        # so the body reports the single move ListBox.set_focus() made.
        old_widget = self._body_widget_at(focus_pos)
        if old_widget is not None:
            visible = self._calculate_visible_around(
                (maxcol, maxrow),
                focus,
                (old_widget, focus_pos),
                self._offset_inset_of(old_widget, maxcol),
            )

            # The new focus among the rows around the old one: (widget, position, offset, side the old focus is on).
            found: tuple[AbstractFlowWidget, typing.Any, int, Literal["above", "below"]] | None = None
            offset = visible.middle.offset
            for row_widget, pos, rows in visible.top.fill:
                offset -= rows
                if pos == position:
                    found = row_widget, pos, offset, "below"
                    break
            if found is None:
                offset = visible.middle.offset + visible.middle.focus_rows
                for row_widget, pos, rows in visible.bottom.fill:
                    if pos == position:
                        found = row_widget, pos, offset, "above"
                        break
                    offset += rows

            if found is not None:
                target, pos, offset, side = found
                # An undirected focus change must preserve the target's cursor and nested focus.
                if coming_from is None and target.selectable():
                    offset = _snap_offset_inset(offset, target.rows((maxcol,), True), maxrow, side, maxrow - 1)
                # change_focus() reads the preferred column from the body's focus, which is the new focus already:
                # hand it the old focus's column, and keep that column when the move is undirected.
                old_pref_col = _pref_col_of(old_widget, maxcol)
                pref_col = self.pref_col if old_pref_col is None else old_pref_col
                if coming_from is None:
                    self.change_focus((maxcol, maxrow), pos, offset)
                    self.pref_col = pref_col
                else:
                    self.change_focus((maxcol, maxrow), pos, offset, side, (pref_col,))
                return None

        # The new focus is not visible from the old one, or the body lost the old focus position
        # after ListBox.set_focus().
        widget, position = self._body.get_focus()
        # the body focuses the new position, so it has a focus widget
        rows = typing.cast("AbstractFlowWidget", widget).rows((maxcol,), focus)

        if coming_from == "below":
            offset = 0
        elif coming_from == "above":
            offset = maxrow - rows
        else:
            offset = (maxrow - rows) // 2
        self.shift_focus((maxcol, maxrow), offset)
        return None

    def shift_focus(self, size: tuple[int, int], offset_inset: int) -> None:
        """Move the location of the current focus relative to the top.

        This is used internally by methods that know the widget's *size*.

        See also :meth:`.set_focus_valign`.

        :param size: see :meth:`Widget.render` for details
        :param offset_inset: either the number of rows between the
            top of the listbox and the start of the focus widget (+ve
            value) or the number of lines of the focus widget hidden off
            the top edge of the listbox (-ve value) or ``0`` if the top edge
            of the focus widget is aligned with the top edge of the
            listbox.
        :raises ListBoxError: *offset_inset* falls outside the listbox rows or the rows of the focus widget.
        """
        (maxcol, maxrow) = size

        if offset_inset >= 0:
            if offset_inset >= maxrow:
                raise ListBoxError(f"Invalid offset_inset: {offset_inset!r}, only {maxrow!r} rows in list box")
            self.offset_rows = offset_inset
            self.inset_fraction = (0, 1)
        else:
            target, _ignore = self._body.get_focus()
            tgt_rows = typing.cast("AbstractFlowWidget", target).rows((maxcol,), True)
            if offset_inset + tgt_rows <= 0:
                raise ListBoxError(f"Invalid offset_inset: {offset_inset!r}, only {tgt_rows!r} rows in target!")
            self.offset_rows = 0
            self.inset_fraction = (-offset_inset, tgt_rows)
        self._invalidate()

    def update_pref_col_from_focus(self, size: tuple[int, int]) -> None:
        """Update self.pref_col from the focus widget."""
        # TODO: should this not be private?
        (maxcol, _maxrow) = size

        widget, _old_pos = self._body.get_focus()
        if widget is None:
            return

        pref_col = _pref_col_of(widget, maxcol)
        if pref_col is not None:
            self.pref_col = pref_col

    def change_focus(
        self,
        size: tuple[int, int],
        position: _K,
        offset_inset: int = 0,
        coming_from: Literal["above", "below"] | None = None,
        cursor_coords: tuple[int | str, int] | tuple[int | str] | None = None,
        snap_rows: int | None = None,
    ) -> None:
        """Change the current focus widget.

        This is used internally by methods that know the widget's *size*.

        See also :meth:`.set_focus`.

        :param size: see :meth:`Widget.render` for details
        :param position: a position compatible with :meth:`self._body.set_focus`
        :param offset_inset: either the number of rows between the
            top of the listbox and the start of the focus widget (+ve
            value) or the number of lines of the focus widget hidden off
            the top edge of the listbox (-ve value) or 0 if the top edge
            of the focus widget is aligned with the top edge of the
            listbox (default if unspecified)
        :param coming_from: either 'above', 'below' or unspecified `None`
        :param cursor_coords: (x, y) tuple indicating the desired column and row for the cursor,
            a (x,) tuple indicating only the column for the cursor, or unspecified
        :param snap_rows: the maximum number of extra rows to scroll
            when trying to "snap" a selectable focus into the view
        :raises TypeError: the body does not implement ``set_focus``.
        :raises ListBoxError: *offset_inset* leaves no row of the target visible, or *cursor_coords* names a row outside
            the target widget.
        :raises ValueError: the cursor row is unspecified and *coming_from* is neither ``'above'`` nor ``'below'``.
        """
        (maxcol, maxrow) = size

        if not hasattr(self._body, "set_focus"):
            raise TypeError(f"{type(self._body)}.set_focus is not implemented.")

        # update pref_col before change
        if cursor_coords:
            self.pref_col = cursor_coords[0]
        else:
            self.update_pref_col_from_focus((maxcol, maxrow))

        self._invalidate()

        self._body.set_focus(position)
        widget, _ignore = self._body.get_focus()
        # focus was just set to `position`, so the walker has a focus widget
        target = typing.cast("AbstractFlowWidget", widget)
        tgt_rows = target.rows((maxcol,), True)
        if snap_rows is None:
            snap_rows = maxrow - 1

        if target.selectable():
            offset_inset = _snap_offset_inset(offset_inset, tgt_rows, maxrow, coming_from, snap_rows)

        # convert offset_inset to offset_rows or inset_fraction
        if offset_inset >= 0:
            self.offset_rows = offset_inset
            self.inset_fraction = (0, 1)
        else:
            if offset_inset + tgt_rows <= 0:
                raise ListBoxError(f"Invalid offset_inset: {offset_inset}, only {tgt_rows} rows in target!")
            self.offset_rows = 0
            self.inset_fraction = (-offset_inset, tgt_rows)

        if cursor_coords is None:
            if coming_from is None:
                return  # must either know row or coming_from
            cursor_coords = (self.pref_col,)

        if not hasattr(target, "move_cursor_to_coords"):
            return

        attempt_rows: Iterable[int] = []

        if len(cursor_coords) == 1:
            # only column (not row) specified
            # start from closest edge and move inwards
            (pref_col,) = cursor_coords
            if coming_from == "above":
                attempt_rows = range(tgt_rows)
            else:
                if coming_from != "below":
                    raise ValueError("must specify coming_from ('above' or 'below') if cursor row is not specified")
                attempt_rows = range(tgt_rows, -1, -1)
        else:
            # both column and row specified
            # start from preferred row and move back to closest edge
            (pref_col, pref_row) = cursor_coords
            if pref_row < 0 or pref_row >= tgt_rows:
                raise ListBoxError(
                    f"cursor_coords row outside valid range for target. pref_row:{pref_row!r} target_rows:{tgt_rows!r}"
                )

            if coming_from == "above":
                attempt_rows = range(pref_row, -1, -1)
            elif coming_from == "below":
                attempt_rows = range(pref_row, tgt_rows)
            else:
                attempt_rows = range(pref_row, pref_row + 1)

        for row in attempt_rows:
            if target.move_cursor_to_coords((maxcol,), pref_col, row):
                break

    def get_focus_offset_inset(self, size: tuple[int, int]) -> tuple[int, int]:
        """Return (offset rows, inset rows) for focus widget.

        :raises ListBoxError: the stored inset fraction is invalid or exceeds the rows of the focus widget.
        """
        (maxcol, _maxrow) = size
        focus_widget, _pos = self._body.get_focus()
        return self._offset_inset_of(typing.cast("AbstractFlowWidget", focus_widget), maxcol)

    def _offset_inset_of(self, focus_widget: AbstractFlowWidget, maxcol: int) -> tuple[int, int]:
        """Return (offset rows, inset rows) for *focus_widget* placed where the focus is.

        :raises ListBoxError: the stored inset fraction is invalid or exceeds the rows of *focus_widget*.
        """
        focus_rows = focus_widget.rows((maxcol,), True)
        offset_rows = self.offset_rows
        inset_rows = 0
        if offset_rows == 0:
            inum, iden = self.inset_fraction
            if inum < 0 or iden < 0 or inum >= iden:
                raise ListBoxError(f"Invalid inset_fraction: {self.inset_fraction!r}")
            inset_rows = focus_rows * inum // iden
            if inset_rows and inset_rows >= focus_rows:
                raise ListBoxError("urwid inset_fraction error (please report)")
        return offset_rows, inset_rows

    def make_cursor_visible(self, size: tuple[int, int]) -> None:
        """Shift the focus widget so that its cursor is visible."""
        (maxcol, maxrow) = size

        focus_widget, _pos = self._body.get_focus()
        if focus_widget is None:
            return
        if not focus_widget.selectable():
            return
        if not hasattr(focus_widget, "get_cursor_coords"):
            return
        cursor = focus_widget.get_cursor_coords((maxcol,))
        if cursor is None:
            return
        _cx, cy = cursor
        offset_rows, inset_rows = self.get_focus_offset_inset((maxcol, maxrow))

        if cy < inset_rows:
            self.shift_focus((maxcol, maxrow), -(cy))
            return

        if offset_rows - inset_rows + cy >= maxrow:
            self.shift_focus((maxcol, maxrow), maxrow - cy - 1)
            return

    def keypress(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Move selection through the list elements scrolling when necessary.

        Keystrokes are first passed to widget in focus in case that widget can handle them.
        A list box with no rows shows nothing and returns every key unhandled.

        Keystrokes handled by this widget are:

        :kbd:`up`
            up one line (or widget)
        :kbd:`down`
            down one line (or widget)
        :kbd:`page up`
            move cursor up one listbox length (or widget)
        :kbd:`page down`
            move cursor down one listbox length (or widget)

        With :attr:`select_navigation`, unhandled ``'next selectable'`` and ``'prev selectable'`` commands
        move the focus to the next or previous selectable widget.
        """
        from urwid.command_map import Command

        (maxcol, maxrow) = self._box_size(size, True)
        if not maxrow:
            return key

        if self.set_focus_pending or self.set_focus_valign_pending:
            self._set_focus_complete((maxcol, maxrow), focus=True)

        focus_widget, _pos = self._body.get_focus()
        if focus_widget is None:  # empty listbox, can't do anything
            return key

        if focus_widget.selectable():
            if handled := focus_widget.keypress((maxcol,), key):
                key = handled
            else:
                self.make_cursor_visible((maxcol, maxrow))
                return None

        if self.select_navigation and self._command_map[key] in _SELECT_COMMANDS:
            return self._select_keypress_unhandled(key)

        def actual_key(unhandled: str | bool | None) -> str | None:
            if unhandled:
                return key
            return None

        # pass off the heavy lifting
        if self._command_map[key] == Command.UP:
            return actual_key(self._keypress_up((maxcol, maxrow)))

        if self._command_map[key] == Command.DOWN:
            return actual_key(self._keypress_down((maxcol, maxrow)))

        if self._command_map[key] == Command.PAGE_UP:
            return actual_key(self._keypress_page_up((maxcol, maxrow)))

        if self._command_map[key] == Command.PAGE_DOWN:
            return actual_key(self._keypress_page_down((maxcol, maxrow)))

        if self._command_map[key] == Command.MAX_LEFT:
            return actual_key(self._keypress_max_left((maxcol, maxrow)))  # type: ignore[func-returns-value]

        if self._command_map[key] == Command.MAX_RIGHT:
            return actual_key(self._keypress_max_right((maxcol, maxrow)))  # type: ignore[func-returns-value]

        return key

    def _select_walk(
        self,
        position: typing.Any,
        *,
        forward: bool,
        seen: _SeenPositions,
        edges: tuple[typing.Any, typing.Any] | None,
    ) -> Iterator[tuple[AbstractFlowWidget, typing.Any]]:
        """Yield the widgets and positions after *position*, or before it when *forward* is false.

        The walk ends at the end of the body or at a position already in *seen*, which a cyclic walker repeats.

        :param edges: the first and last positions of a wrapping body, where the walk ends as well;
            ``None`` for a body that ends on its own.
        """
        edge = None if edges is None else edges[1] if forward else edges[0]
        while True:
            if edges is not None and position == edge:
                return
            widget, position = self._body.get_next(position) if forward else self._body.get_prev(position)
            if widget is None or position in seen:
                return
            seen.add(position)
            yield widget, position

    def _select_wrap_edges(self) -> tuple[typing.Any, typing.Any] | None:
        """Return the first and last positions of a body created with ``wrap_around``.

        Such a walker steps from its last position to its first one, so its edges are where a walk stops.

        :returns: ``None`` for a body that does not wrap, has no ``positions()``, or yields no position.
        """
        body = self._body
        if not getattr(body, "wrap_around", False) or not hasattr(body, "positions"):
            return None
        missing = object()
        first = next(iter(body.positions()), missing)
        last = next(iter(body.positions(reverse=True)), missing)
        if first is missing or last is missing:
            return None
        return first, last

    def _select_candidates(self, *, reverse: bool, from_edge: bool) -> Iterator[_K]:
        """Yield the positions of the selectable widgets in the traversal order.

        The body is walked lazily from the focus, so a step reads only up to the next selectable widget.

        :param reverse: yield them from the bottom to the top.
        :param from_edge: start at the top (bottom when *reverse*) of the body instead of after the focus.
        """
        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            return
        edges = self._select_wrap_edges()
        seen = _SeenPositions()
        seen.add(focus_pos)
        if from_edge:
            # Selectable positions between the focus and the edge, nearest to the focus first.
            before_focus = [
                position
                for widget, position in self._select_walk(focus_pos, forward=reverse, seen=seen, edges=edges)
                if widget.selectable()
            ]
            yield from reversed(before_focus)
            if focus_widget.selectable():
                yield typing.cast("_K", focus_pos)
        for widget, position in self._select_walk(focus_pos, forward=not reverse, seen=seen, edges=edges):
            if widget.selectable():
                yield position

    def _select_enter_focus(self, *, reverse: bool) -> None:
        """Call the entry hook of the widget in focus."""
        _select_enter_child(self.focus, reverse=reverse)

    def scroll_to_top(self) -> None:
        """Move the focus to the first position of the body and show it at the top, as :kbd:`home` does.

        The first position gets the focus whether its widget is selectable or not,
        unlike :meth:`focus_first_selectable`.
        An empty body is left as it is.

        :raises TypeError: the body does not implement ``positions``.
        """
        if not hasattr(self.body, "positions"):
            raise TypeError(f"{type(self.body)}.positions is not implemented.")

        for position in self.body.positions():
            self.focus_position = position
            self.set_focus_valign(VAlign.TOP)
            return

    def scroll_to_bottom(self) -> None:
        """Move the focus to the last position of the body and show it at the bottom, as :kbd:`end` does.

        The last position gets the focus whether its widget is selectable or not,
        unlike :meth:`focus_last_selectable`.
        An empty body is left as it is.

        :raises TypeError: the body does not implement ``positions``.
        """
        if not hasattr(self.body, "positions"):
            raise TypeError(f"{type(self.body)}.positions is not implemented.")

        for position in self.body.positions(reverse=True):
            self.focus_position = position
            self.set_focus_valign(VAlign.BOTTOM)
            return

    def focus_next_match(
        self,
        predicate: Callable[[AbstractFlowWidget], bool],
        *,
        reverse: bool = False,
        wrap: bool = True,
    ) -> _K | None:
        """Move the focus to the next widget for which *predicate* returns true.

        The body is walked lazily from the position next to the focus in the search direction, so a match before the
        end of the body is found without reading the rest of it.
        A wrapped search reads the other side of the focus whole, and checks the widget in focus last,
        so a single match is found again.

        >>> import urwid
        >>> listbox = urwid.ListBox([urwid.Text(word) for word in ("apple", "pear", "plum", "peach")])
        >>> listbox.focus_next_match(lambda widget: widget.text.startswith("p"))
        1
        >>> listbox.focus_next_match(lambda widget: widget.text.startswith("p"), reverse=True)
        3
        >>> listbox.focus_next_match(lambda widget: widget.text == "apple", wrap=False) is None
        True
        >>> listbox.focus_position
        3

        :param predicate: called with each candidate widget.
        :param reverse: search towards the top of the body.
        :param wrap: continue from the other end of the body once this end is reached.
            Only a body that ends, or declares ``wrap_around``, has an end to stop at; one that cycles without
            declaring it is searched once round from the focus either way.
        :returns: the new focus position, or ``None`` when nothing matches and the focus stays where it was.
        """
        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            return None
        edges = self._select_wrap_edges()
        seen = _SeenPositions()
        seen.add(focus_pos)

        def wrapped() -> Iterator[tuple[AbstractFlowWidget, typing.Any]]:
            # Walked only once the first side is exhausted, since both walks share `seen`.
            # The walk goes from the focus outwards, so it is read whole and searched from its far end.
            yield from reversed(list(self._select_walk(focus_pos, forward=reverse, seen=seen, edges=edges)))
            yield focus_widget, focus_pos

        candidates = self._select_walk(focus_pos, forward=not reverse, seen=seen, edges=edges)
        for widget, position in itertools.chain(candidates, wrapped()) if wrap else candidates:
            if predicate(widget):
                self.focus_position = position
                return typing.cast("_K", position)
        return None

    def _keypress_max_left(self, size: tuple[int, int]) -> None:
        """Move the focus to the first position of the body, through :meth:`scroll_to_top`."""
        self.scroll_to_top()

    def _keypress_max_right(self, size: tuple[int, int]) -> None:
        """Move the focus to the last position of the body, through :meth:`scroll_to_bottom`."""
        self.scroll_to_bottom()

    def _keypress_up(self, size: tuple[int, int]) -> bool | None:
        (maxcol, maxrow) = size

        middle, top, _bottom = self.calculate_visible((maxcol, maxrow), True)
        if middle is None or top is None:
            return True

        focus_row_offset, focus_widget, focus_pos, _ignore, cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_top, fill_above = top  # pylint: disable=unpacking-non-sequence

        row_offset = focus_row_offset

        # look for selectable widget above
        pos = focus_pos
        widget = None
        for widget, pos, rows in fill_above:
            row_offset -= rows
            if rows and widget.selectable():
                # this one will do
                self.change_focus((maxcol, maxrow), pos, row_offset, "below")
                return None

        # at this point we must scroll
        row_offset += 1
        self._invalidate()

        # A wrapping body of 0-height widgets returns to a position without moving row_offset: stop there.
        scrolled = _SeenPositions()
        while row_offset > 0:
            # need to scroll in another candidate widget
            widget, pos = self._body.get_prev(pos)
            if widget is None or (pos, row_offset) in scrolled:
                # cannot scroll any further
                return True  # keypress not handled
            scrolled.add((pos, row_offset))
            rows = widget.rows((maxcol,), True)
            row_offset -= rows
            if rows and widget.selectable():
                # this one will do
                self.change_focus((maxcol, maxrow), typing.cast("_K", pos), row_offset, "below")
                return None

        if not focus_widget.selectable() or focus_row_offset + 1 >= maxrow:
            # just take top one if focus is not selectable
            # or if focus has moved out of view
            if widget is None:
                self.shift_focus((maxcol, maxrow), row_offset)
                return None
            # pyrefly: ignore[bad-argument-type]  # pos is not None when widget is not None
            self.change_focus((maxcol, maxrow), pos, row_offset, "below")
            return None

        # check if cursor will stop scroll from taking effect
        if cursor is not None:
            _x, y = cursor
            if y + focus_row_offset + 1 >= maxrow:
                # cursor position is a problem,
                # choose another focus
                if widget is None:
                    # try harder to get prev widget
                    widget, pos = self._body.get_prev(pos)
                    if widget is None:
                        return None  # can't do anything
                    rows = widget.rows((maxcol,), True)
                    row_offset -= rows

                if -row_offset >= rows:
                    # must scroll further than 1 line
                    row_offset = -(rows - 1)

                # pyrefly: ignore[bad-argument-type]  # pos is not None when widget is not None
                self.change_focus((maxcol, maxrow), pos, row_offset, "below")
                return None

        # if all else fails, just shift the current focus.
        self.shift_focus((maxcol, maxrow), focus_row_offset + 1)
        return None

    def _keypress_down(self, size: tuple[int, int]) -> bool | None:
        (maxcol, maxrow) = size

        middle, _top, bottom = self.calculate_visible((maxcol, maxrow), True)
        if middle is None:
            return True

        focus_row_offset, focus_widget, focus_pos, focus_rows, cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_bottom, fill_below = typing.cast("VisibleInfoTopBottom", bottom)  # pylint: disable=unpacking-non-sequence

        row_offset = focus_row_offset + focus_rows
        rows = focus_rows

        # look for selectable widget below
        pos = focus_pos
        widget = None
        for widget, pos, rows in fill_below:
            if rows and widget.selectable():
                # this one will do
                self.change_focus((maxcol, maxrow), pos, row_offset, "above")
                return None
            row_offset += rows

        # at this point we must scroll
        row_offset -= 1
        self._invalidate()

        # A wrapping body of 0-height widgets returns to a position without moving row_offset: stop there.
        scrolled = _SeenPositions()
        while row_offset < maxrow:
            # need to scroll in another candidate widget
            widget, pos = self._body.get_next(pos)
            if widget is None or (pos, row_offset) in scrolled:
                # cannot scroll any further
                return True  # keypress not handled
            scrolled.add((pos, row_offset))
            rows = widget.rows((maxcol,))
            if rows and widget.selectable():
                # this one will do
                self.change_focus((maxcol, maxrow), typing.cast("_K", pos), row_offset, "above")
                return None
            row_offset += rows

        if not focus_widget.selectable() or focus_row_offset + focus_rows - 1 <= 0:
            # just take bottom one if current is not selectable
            # or if focus has moved out of view
            if widget is None:
                self.shift_focus((maxcol, maxrow), row_offset - rows)
                return None
            # pyrefly: ignore[bad-argument-type]  # pos is not None when widget is not None
            self.change_focus((maxcol, maxrow), pos, row_offset - rows, "above")
            return None

        # check if cursor will stop scroll from taking effect
        if cursor is not None:
            _x, y = cursor
            if y + focus_row_offset - 1 < 0:
                # cursor position is a problem,
                # choose another focus
                if widget is None:
                    # try harder to get next widget
                    widget, pos = self._body.get_next(pos)
                    if widget is None:
                        return None  # can't do anything
                else:
                    row_offset -= rows

                if row_offset >= maxrow:
                    # must scroll further than 1 line
                    row_offset = maxrow - 1

                self.change_focus(
                    (maxcol, maxrow),
                    # pyrefly: ignore[bad-argument-type]  # pos is not None when widget is not None
                    pos,
                    row_offset,
                    "above",
                )
                return None

        # if all else fails, keep the current focus.
        self.shift_focus((maxcol, maxrow), focus_row_offset - 1)
        return None

    def _keypress_page_up(self, size: tuple[int, int]) -> bool | None:
        (maxcol, maxrow) = size

        middle, top, _bottom = self.calculate_visible((maxcol, maxrow), True)
        if middle is None or top is None:
            return True

        row_offset, focus_widget, focus_pos, focus_rows, cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_top, fill_above = top  # pylint: disable=unpacking-non-sequence

        # topmost_visible is row_offset rows above top row of
        # focus (+ve) or -row_offset rows below top row of focus (-ve)
        topmost_visible = row_offset

        # scroll_from_row is (first match)
        # 1. topmost visible row if focus is not selectable
        # 2. row containing cursor if focus has a cursor
        # 3. top row of focus widget if it is visible
        # 4. topmost visible row otherwise
        if not focus_widget.selectable():
            scroll_from_row = topmost_visible
        elif cursor is not None:
            _x, y = cursor
            scroll_from_row = -y
        elif row_offset >= 0:
            scroll_from_row = 0
        else:
            scroll_from_row = topmost_visible

        # snap_rows is maximum extra rows to scroll when
        # snapping to new a focus
        snap_rows = topmost_visible - scroll_from_row

        # move row_offset to the new desired value (1 "page" up)
        row_offset = scroll_from_row + maxrow

        # not used below:
        del scroll_from_row, topmost_visible

        # gather potential target widgets and add current focus
        t = [(row_offset, focus_widget, focus_pos, focus_rows)]
        pos = focus_pos
        # include widgets from calculate_visible(..)
        for widget, pos, rows in fill_above:
            row_offset -= rows
            t.append((row_offset, widget, pos, rows))
        # add newly visible ones, including within snap_rows
        snap_region_start = len(t)
        # A wrapping body of 0-height widgets returns to a position without moving row_offset: stop there.
        scrolled = _SeenPositions()
        while row_offset > -snap_rows:
            prev_widget, pos = self._body.get_prev(pos)
            if prev_widget is None or (pos, row_offset) in scrolled:
                break
            scrolled.add((pos, row_offset))
            rows = prev_widget.rows((maxcol,))
            row_offset -= rows
            # determine if one below puts current one into snap rgn
            if row_offset > 0:
                snap_region_start += 1
            t.append((row_offset, prev_widget, pos, rows))

        # if we can't fill the top we need to adjust the row offsets
        row_offset, _w, _p, _r = t[-1]
        if row_offset > 0:
            adjust = -row_offset
            t = [(ro + adjust, w, p, r) for (ro, w, p, r) in t]

        # if focus_widget (first in t) is off edge, remove it
        row_offset, _w, _p, _r = t[0]
        if row_offset >= maxrow:
            del t[0]
            snap_region_start -= 1

        # we'll need this soon
        self.update_pref_col_from_focus((maxcol, maxrow))

        # choose the topmost selectable and (newly) visible widget
        # search within snap_rows then visible region
        search_order = list(range(snap_region_start, len(t))) + list(range(snap_region_start - 1, -1, -1))
        # assert 0, repr((t, search_order))
        bad_choices = []
        cut_off_selectable_chosen = 0
        for i in search_order:
            row_offset, widget, pos, rows = t[i]
            if not widget.selectable():
                continue

            if not rows:
                continue

            # try selecting this widget
            pref_row = max(0, -row_offset)

            # if completely within snap region, adjust row_offset
            if rows + row_offset <= 0:
                self.change_focus(
                    (maxcol, maxrow),
                    pos,
                    -(rows - 1),
                    "below",
                    (self.pref_col, rows - 1),
                    snap_rows - ((-row_offset) - (rows - 1)),
                )
            else:
                self.change_focus(
                    (maxcol, maxrow),
                    pos,
                    row_offset,
                    "below",
                    (self.pref_col, pref_row),
                    snap_rows,
                )

            # if we're as far up as we can scroll, take this one
            if fill_above and self._body.get_prev(fill_above[-1][1]) == (None, None):
                pass  # return

            # find out where that actually puts us
            middle, top, _bottom = self.calculate_visible((maxcol, maxrow), True)
            act_middle = typing.cast("VisibleInfoMiddle", middle)
            act_row_offset, _ign1, _ign2, _ign3, _ign4 = act_middle  # pylint: disable=unpacking-non-sequence

            # discard chosen widget if it will reduce scroll amount
            # because of a fixed cursor (absolute last resort)
            if act_row_offset > row_offset + snap_rows:
                bad_choices.append(i)
                continue
            if act_row_offset < row_offset:
                bad_choices.append(i)
                continue

            # also discard if off top edge (second last resort)
            if act_row_offset < 0:
                bad_choices.append(i)
                cut_off_selectable_chosen = 1
                continue

            return None

        # anything selectable is better than what follows:
        if cut_off_selectable_chosen:
            return None

        if fill_above and focus_widget.selectable() and self._body.get_prev(fill_above[-1][1]) == (None, None):
            # if we're at the top and have a selectable, return
            pass  # return

        # if still none found choose the topmost widget
        good_choices = [j for j in search_order if j not in bad_choices]
        for i in good_choices + search_order:
            row_offset, widget, pos, rows = t[i]
            if pos == focus_pos:
                continue

            if not rows:  # never focus a 0-height widget
                continue

            # if completely within snap region, adjust row_offset
            if rows + row_offset <= 0:
                snap_rows -= (-row_offset) - (rows - 1)
                row_offset = -(rows - 1)

            self.change_focus((maxcol, maxrow), pos, row_offset, "below", None, snap_rows)
            return None

        # no choices available, just shift current one
        self.shift_focus((maxcol, maxrow), min(maxrow - 1, row_offset))

        # final check for pathological case where we may fall short
        middle, top, _bottom = self.calculate_visible((maxcol, maxrow), True)
        act_middle = typing.cast("VisibleInfoMiddle", middle)
        act_row_offset, _act_w, pos, _act_rows, _act_cursor = act_middle  # pylint: disable=unpacking-non-sequence
        if act_row_offset >= row_offset:
            # no problem
            return None

        # fell short, try to select anything else above
        if not t:
            return None
        _last_offset, _last_w, pos, _last_rows = t[-1]
        prev_widget, pos = self._body.get_prev(pos)
        if prev_widget is None:
            # no dice, we're stuck here
            return None
        # bring in only one row if possible
        rows = prev_widget.rows((maxcol,), True)
        if not rows:  # never focus a 0-height widget
            return None
        self.change_focus(
            (maxcol, maxrow),
            typing.cast("_K", pos),
            -(rows - 1),
            "below",
            (self.pref_col, rows - 1),
            0,
        )
        return None

    def _keypress_page_down(self, size: tuple[int, int]) -> bool | None:
        (maxcol, maxrow) = size

        middle, _top, bottom = self.calculate_visible((maxcol, maxrow), True)
        if middle is None or bottom is None:
            return True

        row_offset, focus_widget, focus_pos, focus_rows, cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_bottom, fill_below = bottom  # pylint: disable=unpacking-non-sequence

        # bottom_edge is maxrow-focus_pos rows below top row of focus
        bottom_edge = maxrow - row_offset

        # scroll_from_row is (first match)
        # 1. bottom edge if focus is not selectable
        # 2. row containing cursor + 1 if focus has a cursor
        # 3. bottom edge of focus widget if it is visible
        # 4. bottom edge otherwise
        if not focus_widget.selectable():
            scroll_from_row = bottom_edge
        elif cursor is not None:
            _x, y = cursor
            scroll_from_row = y + 1
        elif bottom_edge >= focus_rows:
            scroll_from_row = focus_rows
        else:
            scroll_from_row = bottom_edge

        # snap_rows is maximum extra rows to scroll when
        # snapping to new a focus
        snap_rows = bottom_edge - scroll_from_row

        # move row_offset to the new desired value (1 "page" down)
        row_offset = -scroll_from_row

        # not used below:
        del scroll_from_row, bottom_edge

        # gather potential target widgets and add current focus
        t = [(row_offset, focus_widget, focus_pos, focus_rows)]
        pos = focus_pos
        row_offset += focus_rows
        # include widgets from calculate_visible(..)
        for widget, pos, rows in fill_below:
            t.append((row_offset, widget, pos, rows))
            row_offset += rows
        # add newly visible ones, including within snap_rows
        snap_region_start = len(t)
        # A wrapping body of 0-height widgets returns to a position without moving row_offset: stop there.
        scrolled = _SeenPositions()
        while row_offset < maxrow + snap_rows:
            next_widget, pos = self._body.get_next(pos)
            if next_widget is None or (pos, row_offset) in scrolled:
                break
            scrolled.add((pos, row_offset))
            rows = next_widget.rows((maxcol,))
            t.append((row_offset, next_widget, pos, rows))
            row_offset += rows
            # determine if one above puts current one into snap rgn
            if row_offset < maxrow:
                snap_region_start += 1

        # if we can't fill the bottom we need to adjust the row offsets
        row_offset, _w, _p, rows = t[-1]
        if row_offset + rows < maxrow:
            adjust = maxrow - (row_offset + rows)
            t = [(ro + adjust, w, p, r) for (ro, w, p, r) in t]

        # if focus_widget (first in t) is off edge, remove it
        row_offset, _w, _p, rows = t[0]
        if row_offset + rows <= 0:
            del t[0]
            snap_region_start -= 1

        # we'll need this soon
        self.update_pref_col_from_focus((maxcol, maxrow))

        # choose the bottommost selectable and (newly) visible widget
        # search within snap_rows then visible region
        search_order = list(range(snap_region_start, len(t))) + list(range(snap_region_start - 1, -1, -1))
        # assert 0, repr((t, search_order))
        bad_choices = []
        cut_off_selectable_chosen = 0
        for i in search_order:
            row_offset, widget, pos, rows = t[i]
            if not widget.selectable():
                continue

            if not rows:
                continue

            # try selecting this widget
            pref_row = min(maxrow - row_offset - 1, rows - 1)

            # if completely within snap region, adjust row_offset
            if row_offset >= maxrow:
                self.change_focus(
                    (maxcol, maxrow),
                    pos,
                    maxrow - 1,
                    "above",
                    (self.pref_col, 0),
                    snap_rows + maxrow - row_offset - 1,
                )
            elif row_offset + rows <= 0:
                self.change_focus(
                    (maxcol, maxrow),
                    pos,
                    -(rows - 1),
                    "above",
                    (self.pref_col, rows - 1),
                    snap_rows - ((-row_offset) - (rows - 1)),
                )
            else:
                self.change_focus(
                    (maxcol, maxrow),
                    pos,
                    row_offset,
                    "above",
                    (self.pref_col, pref_row),
                    snap_rows,
                )

            # find out where that actually puts us
            middle, _top, bottom = self.calculate_visible((maxcol, maxrow), True)
            act_middle = typing.cast("VisibleInfoMiddle", middle)
            act_row_offset, _ign1, _ign2, _ign3, _ign4 = act_middle  # pylint: disable=unpacking-non-sequence

            # discard chosen widget if it will reduce scroll amount
            # because of a fixed cursor (absolute last resort)
            if act_row_offset < row_offset - snap_rows:
                bad_choices.append(i)
                continue
            if act_row_offset > row_offset:
                bad_choices.append(i)
                continue

            # also discard if off top edge (second last resort)
            if act_row_offset + rows > maxrow:
                bad_choices.append(i)
                cut_off_selectable_chosen = 1
                continue

            return None

        # anything selectable is better than what follows:
        if cut_off_selectable_chosen:
            return None

        # if still none found choose the bottommost widget
        good_choices = [j for j in search_order if j not in bad_choices]
        for i in good_choices + search_order:
            row_offset, widget, pos, rows = t[i]
            if pos == focus_pos:
                continue

            if not rows:  # never focus a 0-height widget
                continue

            # if completely within snap region, adjust row_offset
            if row_offset >= maxrow:
                snap_rows -= snap_rows + maxrow - row_offset - 1
                row_offset = maxrow - 1
            elif row_offset + rows <= 0:
                snap_rows -= (-row_offset) - (rows - 1)
                row_offset = -(rows - 1)

            self.change_focus((maxcol, maxrow), pos, row_offset, "above", None, snap_rows)
            return None

        # no choices available, just shift current one
        # The bottom fill puts a trailing 0-height widget at row maxrow, below the last row: use the last row.
        self.shift_focus((maxcol, maxrow), min(maxrow - 1, max(1 - focus_rows, row_offset)))

        # final check for pathological case where we may fall short
        middle, _top, bottom = self.calculate_visible((maxcol, maxrow), True)
        act_middle = typing.cast("VisibleInfoMiddle", middle)
        act_row_offset, _act_w, pos, _act_rows, _act_cursor = act_middle  # pylint: disable=unpacking-non-sequence
        if act_row_offset <= row_offset:
            # no problem
            return None

        # fell short, try to select anything else below
        if not t:
            return None
        _last_offset, _last_w, pos, _last_rows = t[-1]
        next_widget, pos = self._body.get_next(pos)
        if next_widget is None:
            # no dice, we're stuck here
            return None
        # bring in only one row if possible
        rows = next_widget.rows((maxcol,), True)
        if not rows:  # never focus a 0-height widget
            return None
        self.change_focus(
            (maxcol, maxrow),
            typing.cast("_K", pos),
            maxrow - 1,
            "above",
            (self.pref_col, 0),
            0,
        )
        return None

    def mouse_event(
        self,
        size: tuple[int] | tuple[int, int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the event to the contained widgets.

        May change focus on button 1 press.

        .. deprecated:: 2.4.0
            Support for a contained widget that does not implement ``mouse_event`` is deprecated.
            Support will be removed in version 7.0.
        """
        from urwid.util import is_mouse_press

        (maxcol, maxrow) = self._box_size(size, focus)
        middle, top, bottom = self.calculate_visible((maxcol, maxrow), focus=True)
        if middle is None or top is None or bottom is None:
            return False

        _ignore, focus_widget, focus_pos, focus_rows, _cursor = middle  # pylint: disable=unpacking-non-sequence
        trim_top, fill_above = top  # pylint: disable=unpacking-non-sequence
        _ignore, fill_below = bottom  # pylint: disable=unpacking-non-sequence

        fill_above.reverse()  # fill_above is in bottom-up order
        w_list = [*fill_above, (focus_widget, focus_pos, focus_rows), *fill_below]

        wrow = -trim_top
        for w, w_pos, w_rows in w_list:  # noqa: B007  # magic with scope
            if wrow + w_rows > row:
                break
            wrow += w_rows
        else:
            return False

        focus = focus and w == focus_widget
        if is_mouse_press(event) and button == 1 and w.selectable():
            self.change_focus((maxcol, maxrow), w_pos, wrow)

        if not hasattr(w, "mouse_event"):
            _deprecation.warn(
                f"{w.__class__.__module__}.{w.__class__.__name__} is not implementing Widget API.",
                since="2.4.0",
                removed_in="7.0",
            )
            return False

        if w.mouse_event((maxcol,), event, button, col, row - wrow, focus):
            return True

        if is_mouse_press(event):
            if button == 4:
                return not self._keypress_up((maxcol, maxrow))

            if button == 5:
                return not self._keypress_down((maxcol, maxrow))

        return False

    def ends_visible(self, size: tuple[int, int], focus: bool = False) -> list[Literal["top", "bottom"]]:
        """
        Return a list that may contain ``'top'`` and/or ``'bottom'``.

        i.e. this function will return one of: [], [``'top'``],
        [``'bottom'``] or [``'top'``, ``'bottom'``].

        convenience function for checking whether the top and bottom
        of the list are visible
        """
        (maxcol, maxrow) = size
        result: list[Literal["top", "bottom"]] = []
        middle, top, bottom = self.calculate_visible((maxcol, maxrow), focus=focus)
        if middle is None or top is None or bottom is None:  # empty listbox
            return ["top", "bottom"]
        trim_top, above = top  # pylint: disable=unpacking-non-sequence
        trim_bottom, below = bottom  # pylint: disable=unpacking-non-sequence

        if trim_bottom == 0:
            row_offset, _w, pos, rows, _c = middle  # pylint: disable=unpacking-non-sequence
            row_offset += rows
            for _w, pos, rows in below:  # noqa: B007  # magic with scope
                row_offset += rows
            if row_offset < maxrow or (self._body.get_next(pos) == (None, None)):
                result.append("bottom")

        if trim_top == 0:
            row_offset, _w, pos, _rows, _c = middle  # pylint: disable=unpacking-non-sequence
            for _w, pos, rows in above:  # noqa: B007  # magic with scope
                row_offset -= rows
            if self._body.get_prev(pos) == (None, None):
                result.insert(0, "top")

        return result

    def __iter__(self) -> Iterator[_K]:
        """
        Return an iterator over the positions in this ListBox.

        If self._body does not implement positions() then iterate
        from the focus widget down to the bottom, then from above
        the focus up to the top.  This is the best we can do with
        a minimal list walker implementation.
        """
        if positions_fn := getattr(self._body, "positions", None):
            yield from positions_fn()
            return

        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            return
        pos = focus_pos
        while True:
            yield typing.cast("_K", pos)
            w, pos = self._body.get_next(pos)
            if not w:
                break
        pos = focus_pos
        while True:
            w, pos = self._body.get_prev(pos)
            if not w:
                break
            yield typing.cast("_K", pos)

    def __reversed__(self) -> Iterator[_K]:
        """
        Return a reversed iterator over the positions in this ListBox.

        If :attr:`body` does not implement :meth:`positions` then iterate
        from above the focus widget up to the top, then from the focus
        widget down to the bottom.  Note that this is not actually the
        reverse of what `__iter__()` produces, but this is the best we can
        do with a minimal list walker implementation.
        """
        if positions_fn := getattr(self._body, "positions", None):
            yield from positions_fn(reverse=True)
            return

        focus_widget, focus_pos = self._body.get_focus()
        if focus_widget is None:
            return
        pos = focus_pos
        while True:
            w, pos = self._body.get_prev(pos)
            if not w:
                break
            yield typing.cast("_K", pos)
        pos = focus_pos
        while True:
            yield typing.cast("_K", pos)
            w, pos = self._body.get_next(pos)
            if not w:
                break
