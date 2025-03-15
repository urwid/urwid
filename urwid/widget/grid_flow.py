from __future__ import annotations

import typing
import warnings

from urwid.split_repr import remove_defaults

from .columns import Columns
from .constants import Align, Sizing, WHSettings
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin
from .divider import Divider
from .monitored_list import MonitoredFocusList, MonitoredList
from .padding import Padding
from .pile import Pile
from .widget import Widget, WidgetError, WidgetWarning, WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from typing_extensions import Literal


class GridFlowError(WidgetError):
    """GridFlow specific error."""


class GridFlowWarning(WidgetWarning):
    """GridFlow specific warning."""


class GridFlow(WidgetWrap[Pile], WidgetContainerMixin, WidgetContainerListContentsMixin):
    """
    The GridFlow widget is a flow widget that renders all the widgets it contains the same width,
    and it arranges them from left to right and top to bottom.
    """

    def sizing(self) -> frozenset[Sizing]:
        """Widget sizing.

        ..note:: Empty widget sizing is limited to the FLOW due to no data for width.
        """
        if self:
            return frozenset((Sizing.FLOW, Sizing.FIXED))
        return frozenset((Sizing.FLOW,))

    def __init__(
        self,
        cells: Iterable[Widget],
        cell_width: int,
        h_sep: int,
        v_sep: int,
        align: Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int],
        focus: int | Widget | None = None,
    ) -> None:
        """
        :param cells: iterable of flow widgets to display
        :param cell_width: column width for each cell
        :param h_sep: blank columns between each cell horizontally
        :param v_sep: blank rows between cells vertically
            (if more than one row is required to display all the cells)
        :param align: horizontal alignment of cells, one of:
            'left', 'center', 'right', ('relative', percentage 0=left 100=right)
        :param focus: widget index or widget instance to focus on
        """
        prepared_contents: list[tuple[Widget, tuple[Literal[WHSettings.GIVEN], int]]] = []
        focus_position: int = -1

        for idx, widget in enumerate(cells):
            prepared_contents.append((widget, (WHSettings.GIVEN, cell_width)))
            if focus_position < 0 and (focus in {widget, idx} or (focus is None and widget.selectable())):
                focus_position = idx

        focus_position = max(focus_position, 0)

        self._contents: MonitoredFocusList[tuple[Widget, tuple[Literal[WHSettings.GIVEN], int]]] = MonitoredFocusList(
            prepared_contents, focus=focus_position
        )
        self._contents.set_modified_callback(self._invalidate)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._contents_modified)
        self._cell_width = cell_width
        self.h_sep = h_sep
        self.v_sep = v_sep
        self.align = align
        self._cache_maxcol = self._get_maxcol(())
        super().__init__(self.generate_display_widget((self._cache_maxcol,)))

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
        yield "cells", [widget for widget, _ in self.contents]
        yield "cell_width", self.cell_width
        yield "h_sep", self.h_sep
        yield "v_sep", self.v_sep
        yield "align", self.align
        yield "focus", self.focus_position

    def __len__(self) -> int:
        return len(self._contents)

    def _invalidate(self) -> None:
        self._cache_maxcol = None
        super()._invalidate()

    def _contents_modified(
        self,
        _slc: tuple[int, int, int],
        new_items: Iterable[tuple[Widget, tuple[Literal["given", WHSettings.GIVEN], int]]],
    ) -> None:
        for item in new_items:
            try:
                _w, (t, _n) = item
                if t != WHSettings.GIVEN:
                    raise GridFlowError(f"added content invalid {item!r}")
            except (TypeError, ValueError) as exc:  # noqa: PERF203
                raise GridFlowError(f"added content invalid {item!r}").with_traceback(exc.__traceback__) from exc

    @property
    def cells(self):
        """
        A list of the widgets in this GridFlow

        .. note:: only for backwards compatibility. You should use the new
            standard container property :attr:`contents` to modify GridFlow
            contents.
        """
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container property `contents` to modify GridFlow."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        ml = MonitoredList(w for w, t in self.contents)

        def user_modified():
            self.cells = ml

        ml.set_modified_callback(user_modified)
        return ml

    @cells.setter
    def cells(self, widgets: Sequence[Widget]):
        warnings.warn(
            "only for backwards compatibility."
            "You should use the new standard container property `contents` to modify GridFlow."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        focus_position = self.focus_position
        self.contents = [(new, (WHSettings.GIVEN, self._cell_width)) for new in widgets]
        if focus_position < len(widgets):
            self.focus_position = focus_position

    @property
    def cell_width(self) -> int:
        """
        The width of each cell in the GridFlow. Setting this value affects
        all cells.
        """
        return self._cell_width

    @cell_width.setter
    def cell_width(self, width: int) -> None:
        focus_position = self.focus_position
        self.contents = [(w, (WHSettings.GIVEN, width)) for (w, options) in self.contents]
        self.focus_position = focus_position
        self._cell_width = width

    @property
    def contents(self) -> MonitoredFocusList[tuple[Widget, tuple[Literal[WHSettings.GIVEN], int]]]:
        """
        The contents of this GridFlow as a list of (widget, options)
        tuples.

        options is currently a tuple in the form `('fixed', number)`.
        number is the number of screen columns to allocate to this cell.
        'fixed' is the only type accepted at this time.

        This list may be modified like a normal list and the GridFlow
        widget will update automatically.

        .. seealso:: Create new options tuples with the :meth:`options` method.
        """
        return self._contents

    @contents.setter
    def contents(self, c):
        self._contents[:] = c

    def options(
        self,
        width_type: Literal["given", WHSettings.GIVEN] = WHSettings.GIVEN,
        width_amount: int | None = None,
    ) -> tuple[Literal[WHSettings.GIVEN], int]:
        """
        Return a new options tuple for use in a GridFlow's .contents list.

        width_type -- 'given' is the only value accepted
        width_amount -- None to use the default cell_width for this GridFlow
        """
        if width_type != WHSettings.GIVEN:
            raise GridFlowError(f"invalid width_type: {width_type!r}")
        if width_amount is None:
            width_amount = self._cell_width
        return (WHSettings(width_type), width_amount)

    def set_focus(self, cell: Widget | int) -> None:
        """
        Set the cell in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus_position` to get the focus.

        :param cell: contained element to focus
        :type cell: Widget or int
        """
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus_position` to set the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if isinstance(cell, int):
            try:
                if cell < 0 or cell >= len(self.contents):
                    raise IndexError(f"No GridFlow child widget at position {cell}")
            except TypeError as exc:
                raise IndexError(f"No GridFlow child widget at position {cell}").with_traceback(
                    exc.__traceback__
                ) from exc
            self.contents.focus = cell
            return

        for i, (w, _options) in enumerate(self.contents):
            if cell == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in GridFlow contents: {cell!r}")

    @property
    def focus(self) -> Widget | None:
        """the child widget in focus or None when GridFlow is empty"""
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.

        .. note:: only for backwards compatibility. You may also use the new
            standard container property :attr:`focus` to get the focus.
        """
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property `focus` to get the focus."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]

    @property
    def focus_cell(self):
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property"
            "`focus` to get the focus and `focus_position` to get/set the cell in focus by index."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.focus

    @focus_cell.setter
    def focus_cell(self, cell: Widget) -> None:
        warnings.warn(
            "only for backwards compatibility."
            "You may also use the new standard container property"
            "`focus` to get the focus and `focus_position` to get/set the cell in focus by index."
            "API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        for i, (w, _options) in enumerate(self.contents):
            if cell == w:
                self.focus_position = i
                return
        raise ValueError(f"Widget not found in GridFlow contents: {cell!r}")

    @property
    def focus_position(self) -> int | None:
        """
        index of child widget in focus.
        Raises :exc:`IndexError` if read when GridFlow is empty, or when set to an invalid index.
        """
        if not self.contents:
            raise IndexError("No focus_position, GridFlow is empty")
        return self.contents.focus

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
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
        """
        Arrange the cells into columns (and possibly a pile) for
        display, input or to calculate rows, and update the display
        widget.
        """
        maxcol = self._get_maxcol(size)

        # use cache if possible
        if self._cache_maxcol == maxcol:
            return self._w

        self._cache_maxcol = maxcol
        self._w = self.generate_display_widget((maxcol,))

        return self._w

    def generate_display_widget(self, size: tuple[int] | tuple[()]) -> Divider | Pile:
        """
        Actually generate display widget (ignoring cache)
        """
        maxcol = self._get_maxcol(size)

        divider = Divider()
        if not self.contents:
            return divider

        if self.v_sep > 1:
            # increase size of divider
            divider.top = self.v_sep - 1

        c = None
        p = Pile([])
        used_space = 0

        for i, (w, (_width_type, width_amount)) in enumerate(self.contents):
            if c is None or maxcol - used_space < width_amount:
                # starting a new row
                if self.v_sep:
                    p.contents.append((divider, p.options()))
                c = Columns([], self.h_sep)
                column_focused = False
                pad = Padding(c, self.align)
                # extra attribute to reference contents position
                pad.first_position = i
                p.contents.append((pad, p.options()))

            # Use width == maxcol in case of maxcol < width amount
            # Columns will use empty widget in case of GIVEN width > maxcol
            c.contents.append((w, c.options(WHSettings.GIVEN, min(width_amount, maxcol))))
            if (i == self.focus_position) or (not column_focused and w.selectable()):
                c.focus_position = len(c.contents) - 1
                column_focused = True
            if i == self.focus_position:
                p.focus_position = len(p.contents) - 1
            used_space = sum(x[1][1] for x in c.contents) + self.h_sep * len(c.contents)
            pad.width = used_space - self.h_sep

        if self.v_sep:
            # remove first divider
            del p.contents[:1]
        else:
            # Ensure p __selectable is updated
            p._contents_modified()  # pylint: disable=protected-access

        return p

    def _set_focus_from_display_widget(self) -> None:
        """
        Set the focus to the item in focus in the display widget.
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
        c = pile_focus.base_widget
        if c.focus:
            col_focus_position = c.focus_position
        else:
            col_focus_position = 0
        # pad.first_position was set by generate_display_widget() above
        self.focus_position = pile_focus.first_position + col_focus_position

    def keypress(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """
        Pass keypress to display widget for handling.
        Captures focus changes.
        """
        self.get_display_widget(size)

        if (key := super().keypress(size, key)) is not None:
            return key

        self._set_focus_from_display_widget()
        return None

    def pack(
        self,
        size: tuple[int] | tuple[()] = (),  # type: ignore[override]
        focus: bool = False,
    ) -> tuple[int, int]:
        if size:
            return super().pack(size, focus)
        if self:
            cols = len(self) * self.cell_width + (len(self) - 1) * self.h_sep
        else:
            cols = 0
        return cols, self.rows((cols,), focus)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        self.get_display_widget(size)
        return super().rows(size, focus=focus)

    def render(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        focus: bool = False,
    ):
        self.get_display_widget(size)
        return super().render(size, focus)

    def get_cursor_coords(self, size: tuple[int] | tuple[()]) -> tuple[int, int]:
        """Get cursor from display widget."""
        self.get_display_widget(size)
        return super().get_cursor_coords(size)

    def move_cursor_to_coords(self, size: tuple[int] | tuple[()], col: int, row: int):
        """Set the widget in focus based on the col + row."""
        self.get_display_widget(size)
        rval = super().move_cursor_to_coords(size, col, row)
        self._set_focus_from_display_widget()
        return rval

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> Literal[True]:
        self.get_display_widget(size)
        super().mouse_event(size, event, button, col, row, focus)
        self._set_focus_from_display_widget()
        return True  # at a minimum we adjusted our focus

    def get_pref_col(self, size: tuple[int] | tuple[()]):
        """Return pref col from display widget."""
        self.get_display_widget(size)
        return super().get_pref_col(size)
