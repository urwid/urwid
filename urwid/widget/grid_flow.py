"""GridFlow: a container that flows widgets of equal width into a grid."""

from __future__ import annotations

import typing
import warnings
import weakref
from typing import Literal

from urwid.split_repr import remove_defaults

from .columns import Columns
from .constants import Align, Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin
from .divider import Divider
from .monitored_list import MonitoredFocusList
from .padding import Padding
from .pile import Pile
from .widget import AbstractFlowWidget, WidgetError, WidgetWarning, WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from urwid.canvas import Canvas


class GridFlowError(WidgetError):
    """GridFlow specific error."""


class GridFlowWarning(WidgetWarning):
    """GridFlow specific warning."""


GridFlowOptions = tuple[Literal[WHSettings.GIVEN], int]
GridFlowContentsItem = tuple[AbstractFlowWidget, GridFlowOptions]


class GridFlow(
    WidgetWrap["Pile | Divider"],  # quoted: pylint cannot infer a base subscripted with a "|" union
    WidgetContainerMixin[int],
    WidgetContainerListContentsMixin[GridFlowContentsItem],
):
    """Flow widget that renders all the widgets it contains the same width.

    Arranges them from left to right and top to bottom.
    """

    def sizing(self) -> frozenset[Sizing]:
        """Widget sizing.

        ..note:: Empty widget sizing is limited to the FLOW due to no data for width.
        """
        if self:
            return frozenset((Sizing.FLOW, Sizing.FIXED))
        return frozenset((Sizing.FLOW,))

    # Type checkers cannot see the WidgetWrap base built by delegate_to_widget_mixin(),
    # so the two members below are spelled out to keep GridFlow instantiable for them.
    def selectable(self) -> bool:
        """Return whether the internal Pile (or Divider) is selectable."""
        return self._w.selectable()

    @property
    def base_widget(self) -> GridFlow:
        """Return self: GridFlow is a container, not a decoration."""
        return self

    def __init__(
        self,
        cells: Iterable[AbstractFlowWidget],
        cell_width: int,
        h_sep: int,
        v_sep: int,
        align: Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int],
        focus: int | AbstractFlowWidget | None = None,
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
        self._contents.set_modified_callback(self._contents_changed)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._contents_modified)
        self._cell_width = cell_width
        self.h_sep = h_sep
        self.v_sep = v_sep
        self.align = align
        self.first_position: weakref.WeakKeyDictionary[Padding[Columns], int] = weakref.WeakKeyDictionary()
        maxcol = self._get_maxcol(())
        self._cache_maxcol: int | None = maxcol
        super().__init__(self.generate_display_widget((maxcol,)))

    def _repr_words(self) -> list[str]:
        if len(self.contents) > 1:
            contents_string = f"({len(self.contents)} items)"
        elif self.contents:
            contents_string = "(1 item)"
        else:
            contents_string = "()"
        return [*super()._repr_words(), contents_string]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "cell_width": self.cell_width,
            "h_sep": self.h_sep,
            "v_sep": self.v_sep,
            "align": self.align,
            "focus": self.focus_position if len(self._contents) > 1 else None,
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

    def __len__(self) -> int:
        """Return the number of cells."""
        return len(self._contents)

    def _invalidate(self) -> None:
        self._cache_maxcol = None
        super()._invalidate()  # type: ignore[safe-super]  # dynamic base

    def _contents_changed(self) -> None:
        """Record a contents change and invalidate the cached display widget."""
        self._contents_generation += 1
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
                _w, (t, _n) = item
                if t != WHSettings.GIVEN:
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
        focus_position = self.focus_position
        self.contents = [(w, (WHSettings.GIVEN, width)) for (w, options) in self.contents]
        self.focus_position = focus_position
        self._cell_width = width

    @property
    def contents(self) -> MonitoredFocusList[GridFlowContentsItem]:
        """The contents of this GridFlow as a list of (widget, options) tuples.

        options is currently a tuple in the form `('fixed', number)`.
        number is the number of screen columns to allocate to this cell.
        'fixed' is the only type accepted at this time.

        This list may be modified like a normal list and the GridFlow
        widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method.
        """
        return self._contents

    @contents.setter
    def contents(self, c: Sequence[GridFlowContentsItem]) -> None:
        self._contents[:] = c

    def options(
        self,
        width_type: Literal["given", WHSettings.GIVEN] = WHSettings.GIVEN,
        width_amount: int | None = None,
    ) -> GridFlowOptions:
        """
        Return a new options tuple for use in a GridFlow's .contents list.

        :param width_type: 'given' is the only value accepted
        :param width_amount: None to use the default cell_width for this GridFlow
        :raises GridFlowError: *width_type* is not ``GIVEN``.
        """
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

    def _get_maxcol(self, size: tuple[int] | tuple[()]) -> int:
        if size:
            (maxcol,) = size
            if self and maxcol < self.cell_width:
                warnings.warn(
                    f"Size is smaller than cell width ({maxcol!r} < {self.cell_width!r})",
                    GridFlowWarning,
                    stacklevel=3,
                )
        elif self:
            maxcol = len(self) * self.cell_width + (len(self) - 1) * self.h_sep
        else:
            maxcol = 0
        return maxcol

    def get_display_widget(self, size: tuple[int] | tuple[()]) -> Divider | Pile:
        """Arrange the cells into columns (and possibly a pile) for display, input or to calculate rows.

        Also updates the display widget.
        """
        maxcol = self._get_maxcol(size)

        # use cache if possible
        if self._cache_maxcol == maxcol:
            return self._w

        self._cache_maxcol = maxcol
        self._w = self.generate_display_widget((maxcol,))

        return self._w

    def generate_display_widget(self, size: tuple[int] | tuple[()]) -> Divider | Pile:
        """Actually generate display widget (ignoring cache)."""
        maxcol = self._get_maxcol(size)

        divider = Divider()
        if not self.contents:
            return divider

        if self.v_sep > 1:
            # increase size of divider
            divider.top = self.v_sep - 1

        c: Columns | None = None
        p = Pile([])
        used_space = 0

        for i, (w, (_width_type, width_amount)) in enumerate(self.contents):
            if c is None or maxcol - used_space < width_amount:
                # starting a new row
                if self.v_sep:
                    p.contents.append((divider, typing.cast("tuple[Literal[WHSettings.WEIGHT], int]", p.options())))
                c = Columns([], self.h_sep)
                column_focused = False
                pad = Padding(c, self.align)
                self.first_position[pad] = i
                p.contents.append((pad, typing.cast("tuple[Literal[WHSettings.WEIGHT], int]", p.options())))

            # Use width == maxcol in case of maxcol < width amount
            # Columns will use empty widget in case of GIVEN width > maxcol
            c.contents.append(
                (
                    w,
                    typing.cast(
                        "tuple[Literal[WHSettings.GIVEN], int, Literal[False]]",
                        c.options(
                            WHSettings.GIVEN,
                            min(width_amount, maxcol),
                        ),
                    ),
                )
            )
            if (i == self.focus_position) or (not column_focused and w.selectable()):
                c.focus_position = len(c.contents) - 1
                column_focused = True
            if i == self.focus_position:
                p.focus_position = len(p.contents) - 1
            used_space = sum(typing.cast("int", x[1][1]) for x in c.contents) + self.h_sep * len(c.contents)
            pad.width = used_space - self.h_sep

        if self.v_sep:
            # remove first divider
            del p.contents[:1]

        return p

    def _set_focus_from_display_widget(self) -> None:
        """Set the focus to the item in focus in the display widget."""
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

        self.focus_position = first_position + col_focus_position

    def keypress(
        self,
        size: tuple[int] | tuple[()],
        key: str,
    ) -> str | None:
        """Pass keypress to display widget for handling.

        Captures focus changes.
        """
        self.get_display_widget(size)
        focus_before = self.contents.focus
        generation_before = self._contents_generation

        if (processed := super().keypress(size, key)) is not None:  # type: ignore[safe-super]  # dynamic base
            return processed

        # The display widget was built before the keypress was dispatched, so a callback that
        # set the focus or changed the contents is the more recent state and must not be
        # overwritten from it: after a contents change its focus indexes the old contents.
        if self.contents.focus == focus_before and self._contents_generation == generation_before:
            self._set_focus_from_display_widget()
        return None

    def pack(
        self,
        size: tuple[int] | tuple[()] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the number of screen columns and rows this widget requires."""
        if size:
            return super().pack(size, focus)  # type: ignore[safe-super]  # dynamic base
        if self:
            cols = len(self) * self.cell_width + (len(self) - 1) * self.h_sep
        else:
            cols = 0
        return cols, self.rows((cols,), focus)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows this widget requires for the given size."""
        self.get_display_widget(size)
        return typing.cast("int", super().rows(size, focus=focus))  # int or Never - depends on kind

    def render(
        self,
        size: tuple[int] | tuple[()],
        focus: bool = False,
    ) -> Canvas:
        """Render this widget's current display widget at the given size."""
        self.get_display_widget(size)
        return super().render(size, focus)  # type: ignore[safe-super]  # dynamic base

    def get_cursor_coords(self, size: tuple[int] | tuple[()]) -> tuple[int, int]:
        """Get cursor from display widget."""
        self.get_display_widget(size)
        return typing.cast("tuple[int, int]", super().get_cursor_coords(size))

    def move_cursor_to_coords(self, size: tuple[int] | tuple[()], col: int, row: int) -> bool:
        """Set the widget in focus based on the col + row."""
        self.get_display_widget(size)
        rval = typing.cast("bool", super().move_cursor_to_coords(size, col, row))
        self._set_focus_from_display_widget()
        return rval

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> Literal[True]:
        """Handle a mouse event, updating the focus based on the resulting display widget."""
        self.get_display_widget(size)
        focus_before = self.contents.focus
        generation_before = self._contents_generation
        super().mouse_event(size, event, button, col, row, focus)  # type: ignore[safe-super]  # dynamic base
        # Same as in keypress: a callback that set the focus or changed the contents wins
        # over the display widget, which was built before the event was dispatched.
        if self.contents.focus == focus_before and self._contents_generation == generation_before:
            self._set_focus_from_display_widget()
        return True  # at a minimum we adjusted our focus

    def get_pref_col(self, size: tuple[int] | tuple[()]) -> int:
        """Return pref col from display widget."""
        self.get_display_widget(size)
        return typing.cast("int", super().get_pref_col(size))
