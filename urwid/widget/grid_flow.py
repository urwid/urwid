"""GridFlow: a container that flows widgets into a grid of rows."""

from __future__ import annotations

import typing
import warnings
import weakref
from typing import Literal

from urwid.command_map import Command
from urwid.split_repr import remove_defaults

from .columns import Columns
from .constants import Align, Sizing, WHSettings
from .container import (
    _SELECT_COMMANDS,
    SelectNavigationListContentsMixin,
    _UnfocusedFocusAttrMixin,
    _WeakCallback,
)
from .divider import Divider
from .monitored_list import MonitoredFocusList
from .padding import Padding
from .pile import Pile
from .widget import AbstractFlowWidget, WidgetError, WidgetWarning, WidgetWrap, _InvalidatingAttribute

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from urwid.canvas import Canvas

    from .attr_map import _AttrMapLike
    from .container import _UnfocusedFocusAttrFunc
    from .widget import AbstractFixedWidget


class GridFlowError(WidgetError):
    """GridFlow specific error."""


class GridFlowWarning(WidgetWarning):
    """GridFlow specific warning."""


def _cell_span(columns: Columns, index: int) -> tuple[int, int]:
    """Return the offset and the width of cell *index* in a row of the display widget.

    Every cell of the row has a ``'given'`` width, and a cell 0 columns wide has no divider, as :class:`Columns` lays
    it out.
    """
    widths = [typing.cast("int", options[1]) for _w, options in columns.contents]
    return sum(columns.dividechars + width for width in widths[:index] if width > 0), widths[index]


GridFlowOptions = tuple[Literal[WHSettings.GIVEN], int] | tuple[Literal[WHSettings.PACK], None]
GridFlowContentsItem = tuple[AbstractFlowWidget, GridFlowOptions]


class GridFlow(
    WidgetWrap["Pile | Divider"],  # quoted: pylint cannot infer a base subscripted with a "|" union
    SelectNavigationListContentsMixin[GridFlowContentsItem],
    _UnfocusedFocusAttrMixin,
):
    """Flow widget that arranges the widgets it contains into rows.

    Arranges them from left to right and top to bottom.
    Each cell is :attr:`cell_width` wide unless its options in :attr:`contents` give it its own width,
    or make it as wide as its widget packs to.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`contents`.
    Its handlers receive the container, the old and the new focus position, which is ``None`` while it is empty.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed"]

    #: Number of blank columns between two cells.
    h_sep = _InvalidatingAttribute[int]()
    #: Number of blank rows between two rows of cells.
    v_sep = _InvalidatingAttribute[int]()
    #: Alignment of each row of cells.
    align = _InvalidatingAttribute[
        Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int]
    ]()

    def sizing(self) -> frozenset[Sizing]:
        """Widget sizing.

        .. note:: Sizing is limited to FLOW when there is no width to give a fixed size:
            the GridFlow is empty, or a ``'pack'`` cell holds a widget without FIXED sizing.
        """
        if self and all(
            width_type == WHSettings.GIVEN or Sizing.FIXED in w.sizing()
            for w, (width_type, _width_amount) in self.contents
        ):
            return frozenset((Sizing.FLOW, Sizing.FIXED))
        return frozenset((Sizing.FLOW,))

    # base_widget is typed as GridFlow rather than Widget.
    def selectable(self) -> bool:
        """Return whether the internal Pile (or Divider) is selectable."""
        return self._w.selectable()

    @property
    def base_widget(self) -> GridFlow:
        """Return self: GridFlow is a container, not a decoration."""
        return self

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Start at the first selectable cell, or at the last one when *reverse* is set.

        It is the entry hook a parent container calls, and acts only when :attr:`select_navigation` is set,
        see :ref:`select-navigation`.

        :param reverse: start at the last selectable cell instead of the first one.
        """
        # WidgetWrap comes first in the bases: its forwarding to the generated display widget would win otherwise.
        SelectNavigationListContentsMixin.enter_selectable(self, reverse=reverse)

    def __init__(
        self,
        cells: Iterable[AbstractFlowWidget],
        cell_width: int,
        h_sep: int,
        v_sep: int,
        align: Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int],
        focus: int | AbstractFlowWidget | None = None,
        *,
        select_navigation: bool = False,
        unfocused_focus_attr: _AttrMapLike | None = None,
        unfocused_focus_attr_func: _UnfocusedFocusAttrFunc | None = None,
    ) -> None:
        """Create the GridFlow widget.

        :param cells: iterable of flow widgets to display
        :param cell_width: column width for each cell
        :param h_sep: blank columns between each cell horizontally
        :param v_sep: blank rows between cells vertically
            (if more than one row is required to display all the cells)
        :param align: horizontal alignment of cells, one of:
            'left', 'center', 'right', ('relative', percentage 0=left 100=right)
        :param focus: widget index or widget instance to focus on
        :param select_navigation: handle the ``'next selectable'`` and ``'prev selectable'`` commands
            over the cells in their contents order, see :ref:`select-navigation`.
        :param unfocused_focus_attr: attribute map applied to the focus child while the grid renders without
            focus, in any form :class:`AttrMap` takes; see :attr:`unfocused_focus_attr`.
        :param unfocused_focus_attr_func: function that gives the map applied to the focus child while the grid
            renders without focus, instead of *unfocused_focus_attr*; see :attr:`unfocused_focus_attr_func`.
        """
        prepared_contents: list[GridFlowContentsItem] = []
        focus_position: int = -1

        for idx, widget in enumerate(cells):
            prepared_contents.append((widget, (WHSettings.GIVEN, cell_width)))
            if focus_position < 0 and (focus in {widget, idx} or (focus is None and widget.selectable())):
                focus_position = idx

        focus_position = max(focus_position, 0)

        self._contents: MonitoredFocusList[GridFlowContentsItem] = MonitoredFocusList(
            prepared_contents,
            focus=focus_position,
        )
        # Bumped on every contents change, so input handlers can tell that the display widget went stale.
        self._contents_generation = 0
        self._contents.set_modified_callback(_WeakCallback(self, type(self)._contents_changed))
        self._contents.set_focus_changed_callback(_WeakCallback(self, type(self)._focus_changed))
        self._contents.set_focus_moved_callback(_WeakCallback(self, type(self)._emit, "focus changed"))
        self._contents.set_validate_contents_modified(_WeakCallback(self, type(self)._contents_modified))
        self._cell_width = cell_width
        self.h_sep = h_sep
        self.v_sep = v_sep
        self.align = align
        self.select_navigation = select_navigation
        self._set_unfocused_focus_attr(unfocused_focus_attr)
        self._unfocused_focus_attr_func = unfocused_focus_attr_func
        self.first_position: weakref.WeakKeyDictionary[Padding[Columns], int] = weakref.WeakKeyDictionary()
        # The cursor column kept for the focus cell, as an offset inside that cell, so it survives rebuilds of the
        # display widget. It always belongs to the current focus cell: a focus or contents change drops it.
        self._pref_col: int | None = None
        maxcol, widths = self._layout(())
        # The width laid out in, each cell's width and which cells are selectable, which picks the focus cell of each
        # row: a 'pack' cell can change its width, and any cell its selectability, without invalidating the GridFlow.
        self._cache_key: tuple[int, tuple[int, ...], tuple[bool, ...]] | None = (
            maxcol,
            widths,
            tuple(w.selectable() for w, _ in self.contents),
        )
        super().__init__(self.generate_display_widget((maxcol,)))

    def _repr_words(self) -> list[str]:
        """Return the base repr words followed by the number of items in the contents."""
        if len(self.contents) > 1:
            contents_string = f"({len(self.contents)} items)"
        elif self.contents:
            contents_string = "(1 item)"
        else:
            contents_string = "()"
        return [*super()._repr_words(), contents_string]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor arguments that differ from their defaults, for the repr.

        The focus position is included only when there is more than one item.
        """
        attrs = {
            **super()._repr_attrs(),
            "cell_width": self.cell_width,
            "h_sep": self.h_sep,
            "v_sep": self.v_sep,
            "align": self.align,
            "focus": self.focus_position if len(self._contents) > 1 else None,
            "select_navigation": self.select_navigation,
            "unfocused_focus_attr": self._unfocused_focus_attr,
            "unfocused_focus_attr_func": self._unfocused_focus_attr_func,
        }
        return remove_defaults(attrs, GridFlow.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        """Yield this widget's constructor arguments as `(name, value)` pairs, for `rich`'s repr protocol."""
        yield "cells", [widget for widget, _ in self.contents]
        yield "cell_width", self.cell_width
        yield "h_sep", self.h_sep
        yield "v_sep", self.v_sep
        yield "align", self.align
        yield "focus", self.focus_position
        yield "select_navigation", self.select_navigation, False
        yield "unfocused_focus_attr", self._unfocused_focus_attr, None
        yield "unfocused_focus_attr_func", self._unfocused_focus_attr_func, None

    def __len__(self) -> int:
        """Return the number of cells."""
        return len(self._contents)

    def _invalidate(self) -> None:
        """Drop the cached display widget and the cached canvases."""
        self._cache_key = None
        super()._invalidate()

    def _focus_changed(self, _focus: int) -> None:
        """Drop the cursor column kept for the cell losing the focus.

        The cached display widget is invalidated too.
        """
        self._pref_col = None
        self._invalidate()

    def _contents_changed(self) -> None:
        """Record a contents change.

        The kept cursor column is dropped, and the cached display widget is invalidated.
        """
        self._contents_generation += 1
        self._pref_col = None
        self._invalidate()

    def _contents_modified(
        self,
        _slc: tuple[int, int, int],
        new_items: Iterable[GridFlowContentsItem],
    ) -> None:
        """
        Reject contents changes that would put an invalid item into the GridFlow.

        :raises GridFlowError: an added item is not a valid ``(widget, options)`` pair.
        """
        for item in new_items:
            try:
                _w, (t, n) = item
                if t != WHSettings.GIVEN and not (t == WHSettings.PACK and n is None):
                    raise GridFlowError(f"added content invalid {item!r}")
            except (TypeError, ValueError) as exc:
                raise GridFlowError(f"added content invalid {item!r}").with_traceback(exc.__traceback__) from exc

    @property
    def cell_width(self) -> int:
        """The width of each cell in the GridFlow.

        Setting this value affects all cells.
        """
        return self._cell_width

    @cell_width.setter
    def cell_width(self, width: int) -> None:
        """Set every cell to *width* screen columns, keeping the focus position.

        :param width: the new width of each cell
        :raises IndexError: the GridFlow is empty.
        """
        focus_position = self.focus_position
        self.contents = [(w, (WHSettings.GIVEN, width)) for (w, options) in self.contents]
        self.focus_position = focus_position
        self._cell_width = width

    @property
    def contents(self) -> MonitoredFocusList[GridFlowContentsItem]:
        """The contents of this GridFlow as a list of (widget, options) tuples.

        options is a tuple in one of these forms:

        - `('given', number)`: the cell is number screen columns wide.
        - `('pack', None)`: the cell is as wide as its widget packs to, at most the width of the GridFlow.

        This list may be modified like a normal list and the GridFlow
        widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method.
        """
        return self._contents

    @contents.setter
    def contents(self, new_contents: Sequence[GridFlowContentsItem]) -> None:
        """Replace the contents with *new_contents*.

        :param new_contents: `(widget, options)` tuples, with options made by the :meth:`options` method
        :raises GridFlowError: an item is not a valid ``(widget, options)`` pair.
        """
        self._contents.replace(new_contents)

    @typing.overload
    def options(
        self,
        width_type: Literal["pack", WHSettings.PACK],
        width_amount: None = None,
    ) -> tuple[Literal[WHSettings.PACK], None]: ...

    @typing.overload
    def options(
        self,
        width_type: Literal["given", WHSettings.GIVEN] = ...,
        width_amount: int | None = None,
    ) -> tuple[Literal[WHSettings.GIVEN], int]: ...

    def options(
        self,
        width_type: Literal["given", "pack", WHSettings.GIVEN, WHSettings.PACK] = WHSettings.GIVEN,
        width_amount: int | None = None,
    ) -> GridFlowOptions:
        """
        Return a new options tuple for use in a GridFlow's .contents list.

        Each cell keeps the width its options give, so the cells of one GridFlow may differ in width.
        A ``'pack'`` cell is measured each time the GridFlow is laid out:

        >>> import urwid
        >>> grid = urwid.GridFlow([], 1, 1, 0, "left")
        >>> grid.contents.extend((urwid.Text(label), grid.options("pack")) for label in ("Open", "Quit"))
        >>> grid.render(()).text
        [b'Open Quit']

        :param width_type: ``'given'`` for a cell *width_amount* screen columns wide,
            ``'pack'`` for a cell as wide as its widget packs to.
        :param width_amount: for ``'given'``, None to use the default cell_width for this GridFlow;
            for ``'pack'``, None.
        :raises GridFlowError: *width_type* is neither ``GIVEN`` nor ``PACK``, or a ``PACK`` cell is given a width.
        """
        if width_type == WHSettings.PACK:
            if width_amount is not None:
                raise GridFlowError(f"a 'pack' cell takes no width_amount: {width_amount!r}")
            return (WHSettings.PACK, None)
        if width_type != WHSettings.GIVEN:
            raise GridFlowError(f"invalid width_type: {width_type!r}")
        if width_amount is None:
            width_amount = self._cell_width
        return (WHSettings.GIVEN, width_amount)

    @property
    def focus(self) -> AbstractFlowWidget | None:
        """The child widget in focus or None when GridFlow is empty."""
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @property
    def focus_position(self) -> int:
        """Index of child widget in focus.

        Raises :exc:`IndexError` if read when GridFlow is empty, or when set to an invalid index.

        :raises IndexError: the GridFlow is empty.
        """
        if (focus := self.contents.focus) is not None:
            return focus

        raise IndexError("No focus_position, GridFlow is empty")

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        :param position: index of child widget to be made focus
        :raises IndexError: *position* is not an index of a child widget.
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError(f"No GridFlow child widget at position {position}")
        except TypeError as exc:
            raise IndexError(f"No GridFlow child widget at position {position}").with_traceback(
                exc.__traceback__
            ) from exc
        self.contents.focus = position

    def _layout(self, size: tuple[int] | tuple[()]) -> tuple[int, tuple[int, ...]]:
        """Return the number of screen columns to lay the cells out in, and the width of each cell.

        A flow size gives the width directly, and a ``'pack'`` cell is at most that wide.
        A :exc:`GridFlowWarning` is issued when that width is narrower than the widest ``'given'`` cell.
        A fixed size uses the width of all cells in one row, with each ``'pack'`` cell at its fixed width.
        A cell 0 columns wide takes no space and no divider, as :class:`Columns` hides it.

        :param size: ``(maxcol,)`` for a flow size, ``()`` for a fixed size
        :returns: the width in screen columns, 0 for an empty GridFlow with a fixed size, and the cell widths
            in contents order.
        """
        widths: list[int] = []
        widest_given = 0
        for w, (width_type, width_amount) in self.contents:
            if width_type == WHSettings.GIVEN:
                widths.append(typing.cast("int", width_amount))
                widest_given = max(widest_given, typing.cast("int", width_amount))
            elif not size:
                widths.append(typing.cast("AbstractFixedWidget", w).pack(())[0])
            else:
                # As Columns does for 'pack': a FLOW widget packed at maxcol may claim all of it, so its fixed width
                # comes first, unless it is too wide.
                (maxcol,) = size
                width = typing.cast("AbstractFixedWidget", w).pack(())[0] if Sizing.FIXED in w.sizing() else 0
                if not width or width > maxcol:
                    width = w.pack(size)[0]
                widths.append(min(width, maxcol))

        if not size:
            visible = [width for width in widths if width > 0]
            return sum(visible) + (len(visible) - 1) * self.h_sep if visible else 0, tuple(widths)

        (maxcol,) = size
        if maxcol < widest_given:
            warnings.warn(
                f"Size is smaller than cell width ({maxcol!r} < {widest_given!r})",
                GridFlowWarning,
                stacklevel=3,
            )
        return maxcol, tuple(widths)

    def get_display_widget(self, size: tuple[int] | tuple[()]) -> Divider | Pile:
        """Arrange the cells into columns (and possibly a pile) for display, input or to calculate rows.

        Also updates the display widget.
        The display widget is reused while the width, every cell's width and every cell's ``selectable()``
        stay the same.
        The row of the focus cell gets the cursor column kept for that cell, and every other row none.
        """
        maxcol, widths = self._layout(size)
        key = (maxcol, widths, tuple(w.selectable() for w, _ in self.contents))

        if self._cache_key != key:
            self._w = self.generate_display_widget((maxcol,))
            # after the assignment: setting _w invalidates, which clears the cache key
            self._cache_key = key
        elif isinstance(self._w, Pile):
            # a reused display widget starts from the preferred columns a new one has
            self._w.pref_col = 0
            for row, _options in self._w.contents:
                if isinstance(row, Padding):
                    typing.cast("Columns", row.original_widget).pref_col = None

        if self._pref_col is not None:
            pad = typing.cast("Padding[Columns]", self._w.focus)
            columns = pad.original_widget
            x, width = _cell_span(columns, self.focus_position - self.first_position[pad])
            columns.pref_col = x + min(self._pref_col, max(width - 1, 0))

        return self._w

    def generate_display_widget(self, size: tuple[int] | tuple[()]) -> Divider | Pile:
        """Actually generate display widget (ignoring cache)."""
        maxcol, widths = self._layout(size)

        divider = Divider()
        if not self.contents:
            return divider

        if self.v_sep > 1:
            # increase size of divider
            divider.top = self.v_sep - 1

        c: Columns | None = None
        p = Pile([])
        used_space = 0

        for i, ((w, _options), width_amount) in enumerate(zip(self.contents, widths, strict=True)):
            # A cell takes at most maxcol columns, as it is added below. A cell 0 columns wide fits in any row,
            # and a row of only such cells has room for any cell, so no row shows nothing.
            width = min(width_amount, maxcol)
            if c is None or (width > 0 and maxcol - used_space < width):
                # starting a new row
                if self.v_sep:
                    p.contents.append((divider, p.options()))
                c = Columns([], self.h_sep)
                column_focused = False
                pad = Padding(c, self.align)
                self.first_position[pad] = i
                p.contents.append((pad, p.options()))

            # Use width == maxcol in case of maxcol < width amount
            # Columns will use empty widget in case of GIVEN width > maxcol
            c.contents.append(
                (
                    w,
                    c.options(
                        WHSettings.GIVEN,
                        width,
                    ),
                )
            )
            if (i == self.focus_position) or (not column_focused and w.selectable()):
                c.focus_position = len(c.contents) - 1
                column_focused = True
            if i == self.focus_position:
                p.focus_position = len(p.contents) - 1
                # only the row holding the focus cell marks it, so the other rows' own focus cells stay plain
                c.unfocused_focus_attr = self._unfocused_focus_attr
                c.unfocused_focus_attr_func = self._unfocused_focus_attr_func
            # Columns draws no divider next to a column 0 columns wide
            visible = [width for _w, (_t, width, _b) in c.contents if typing.cast("int", width) > 0]
            used_space = sum(typing.cast("int", width) for width in visible) + self.h_sep * len(visible)
            pad.width = max(used_space - self.h_sep, 0)

        if self.v_sep:
            # remove first divider
            del p.contents[0]

        return p

    def _set_focus_from_display_widget(self) -> None:
        """Set the focus to the item in focus in the display widget.

        The cursor column of its row is kept for that cell,
        unless a "focus changed" handler moved the focus again or changed the contents.
        """
        # display widget (self._w) is always built as:
        #
        # Pile([
        #     Padding(
        #         Columns([ # possibly
        #         cell, ...])),
        #     Divider(), # possibly
        #     ...])

        pile_focus = self._w.focus
        if not pile_focus:
            return

        c = typing.cast("Columns", pile_focus.base_widget)
        if c.focus:
            col_focus_position = c.focus_position
        else:
            col_focus_position = 0

        first_position = self.first_position[typing.cast("Padding[Columns]", pile_focus)]

        # The cursor column the row got from the display widget is kept as an offset inside the focus cell:
        # 'left' and 'right' become its first and last column.
        pref_col: int | None = None
        if (col := c.pref_col) is not None:
            x, width = _cell_span(c, col_focus_position)
            if col in {Align.LEFT, Align.RIGHT}:
                offset = 0 if col == Align.LEFT else width - 1
            else:
                offset = typing.cast("int", col) - x
            pref_col = min(max(offset, 0), max(width - 1, 0))

        position = first_position + col_focus_position
        generation = self._contents_generation
        self.focus_position = position
        # This runs after the focus change, which drops the column kept for the cell before.
        # A "focus changed" handler runs inside the setter: when it moved the focus or changed the contents,
        # the column belongs to no cell.
        if self.contents.focus == position and self._contents_generation == generation:
            self._pref_col = pref_col

    def keypress(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]  # flow and fixed only, no box size
        key: str,
    ) -> str | None:
        """Pass keypress to display widget for handling.

        Captures focus changes.
        With :attr:`select_navigation`, unhandled ``'next selectable'`` and ``'prev selectable'`` commands
        move the focus to the next or previous selectable cell.
        A key other than up, down, page up and page down drops the kept cursor column, as in :class:`Columns`.
        """
        if self._command_map[key] not in {Command.UP, Command.DOWN, Command.PAGE_UP, Command.PAGE_DOWN}:
            self._pref_col = None
        self.get_display_widget(size)
        focus_before = self.contents.focus
        generation_before = self._contents_generation

        if (processed := super().keypress(size, key)) is not None:
            if self.select_navigation and self._command_map[processed] in _SELECT_COMMANDS:
                return self._select_keypress_unhandled(processed)
            return processed

        # The display widget was built before the keypress was dispatched, so a callback that
        # set the focus or changed the contents is the more recent state and must not be
        # overwritten from it: after a contents change its focus indexes the old contents.
        if self.contents.focus == focus_before and self._contents_generation == generation_before:
            self._set_focus_from_display_widget()
        return None

    def pack(  # type: ignore[override]  # flow and fixed only, no box size
        self,
        size: tuple[int] | tuple[()] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the number of screen columns and rows this widget requires."""
        if size:
            return super().pack(size, focus)
        cols, _widths = self._layout(())
        return cols, self.rows((cols,), focus)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows this widget requires for the given size."""
        self.get_display_widget(size)
        return super().rows(size, focus=focus)

    def render(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]  # flow and fixed only, no box size
        focus: bool = False,
    ) -> Canvas:
        """Render this widget's current display widget at the given size."""
        self.get_display_widget(size)
        return super().render(size, focus)

    def get_cursor_coords(self, size: tuple[int] | tuple[()]) -> tuple[int, int] | None:
        """Get cursor from display widget, or None if the widget in focus shows no cursor."""
        self.get_display_widget(size)
        return super().get_cursor_coords(size)

    def move_cursor_to_coords(self, size: tuple[int] | tuple[()], col: int, row: int) -> bool:
        """Set the widget in focus based on the col + row.

        The column, limited to the cell that gets the focus, is kept as the preferred column.
        A cell that changes the contents while it moves its cursor leaves no column kept.
        """
        self.get_display_widget(size)
        generation_before = self._contents_generation
        rval = super().move_cursor_to_coords(size, col, row)
        self._set_focus_from_display_widget()
        if self._contents_generation != generation_before:
            # the column was read from the display widget of the old contents
            self._pref_col = None
        return rval

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]  # flow and fixed only, no box size
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Handle a mouse event, updating the focus based on the resulting display widget.

        An event that moves the focus to another cell leaves no cursor column kept.

        :returns: ``True`` when a cell handled the event or the focus moved to another cell, otherwise the
            result of the display widget, so an event such as the mouse wheel stays unhandled for a parent
            like :class:`ListBox`.
        """
        self.get_display_widget(size)
        focus_before = self.contents.focus
        generation_before = self._contents_generation
        handled = super().mouse_event(size, event, button, col, row, focus)
        # Same as in keypress: a callback that set the focus or changed the contents wins
        # over the display widget, which was built before the event was dispatched.
        if self.contents.focus == focus_before and self._contents_generation == generation_before:
            self._set_focus_from_display_widget()
        if self.contents.focus != focus_before:
            # no cursor column comes with a click, so the kept one belongs to the cell left behind
            self._pref_col = None
        return handled or self.contents.focus != focus_before

    def get_pref_col(self, size: tuple[int] | tuple[()]) -> int | None:
        """Return pref col from display widget, or None if the widget in focus has no preferred column."""
        self.get_display_widget(size)
        return super().get_pref_col(size)
