"""Table: rows of cells whose columns share widths, under a fixed header."""

# The layout, its rows and their table keep one set of bookkeeping between them through their protected members.
# pylint: disable=protected-access

from __future__ import annotations

import itertools
import math
import sys
import typing
import weakref
from typing import Literal

from urwid import signals
from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.command_map import Command

from .attr_map import _attr_map_dict
from .columns import Columns
from .constants import Align, Sizing, WHSettings, WrapMode
from .list_walker import SimpleFocusListWalker
from .listbox import ListBox
from .scrollable import ScrollBar
from .text import Text
from .widget import Widget, WidgetError, WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Hashable, Iterable, Iterator, Sequence

    from urwid.canvas import Canvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike

    # A cell as a caller gives it: a widget, or text markup that becomes a text cell.
    _Cell: typing.TypeAlias = Widget | _TagMarkup

__all__ = ("Table", "TableColumn", "TableError", "TableLayout", "TableRow")

# The number of maxcol values whose allocated widths a layout keeps:
# a table renders at one width, and a dialog asks for the natural width beside it.
_ALLOCATIONS_KEPT = 2
_TEXT_ALIGNS = frozenset((Align.LEFT, Align.CENTER, Align.RIGHT))
_TEXT_WRAPS = frozenset((WrapMode.SPACE, WrapMode.CLIP, WrapMode.ELLIPSIS))


class TableError(WidgetError):
    """Table related errors."""


class _Arrangement(typing.NamedTuple):
    """How a table divides one size between its header, its rows and its scrollbar."""

    maxcol: int
    #: the width of the header and the rows: *maxcol* less the scrollbar while it is drawn
    content: int
    header_rows: int
    #: the rows of the body, or ``None`` for a flow size that shows every row
    body_rows: int | None
    bar: bool


class TableColumn(typing.NamedTuple):
    """Specification of one table column.

    The width is one of:

    - :attr:`WHSettings.PACK`: as wide as the widest cell that can be measured, and the label;
    - a number of screen columns, where 0 hides the column;
    - ``(WHSettings.WEIGHT, weight)``: a share of the room left by the other columns.

    *align* and *wrap* apply to the cells given as text; a cell given as a widget keeps its own.
    A :class:`TableLayout` validates the specification when it takes it.
    """

    #: Header text, drawn by :class:`Table` with ``header=True``.
    label: _TagMarkup = ""
    width: Literal[WHSettings.PACK] | int | tuple[Literal[WHSettings.WEIGHT], int | float] = WHSettings.PACK
    #: The narrowest a PACK or WEIGHT column becomes before the table hides a column instead.
    min_width: int = 1
    align: Literal[Align.LEFT, Align.CENTER, Align.RIGHT] = Align.LEFT
    wrap: Literal[WrapMode.SPACE, WrapMode.CLIP, WrapMode.ELLIPSIS] = WrapMode.CLIP


class _TableText(Text):
    """Text cell made by a layout from text markup; changing its text re-measures its column."""

    def __init__(self, markup: _TagMarkup, align: Align, wrap: WrapMode) -> None:
        self._row: weakref.ref[TableRow] | None = None
        super().__init__(markup, align, wrap)

    def _invalidate(self) -> None:
        super()._invalidate()
        row = None if self._row is None else self._row()
        if row is not None:
            row._cell_changed(self)


class _TableColumns(Columns):
    """Columns of one table row, laid out with the widths its layout shares between all its rows."""

    def __init__(self, layout: TableLayout, cells: Sequence[Widget], *, span: bool) -> None:
        self._layout = layout
        self._span = span
        super().__init__(
            [(WHSettings.WEIGHT, 1, cell) for cell in cells],
            dividechars=layout.dividechars,
        )

    def column_widths(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> list[int]:
        """Return the widths the layout allocates at the width in *size*; a full-width row gets all of it."""
        self._layout._record_rendered(self)
        if self._span:
            return [size[0]]
        return list(self._layout.widths(size[0]))


class TableLayout:
    """Column widths shared by every row built through the layout, with or without a :class:`Table`.

    Cells are measured once, when their row is built.
    A text cell the layout made measures itself again when its text changes.
    Another widget whose width changed needs :meth:`invalidate_widths`.

    >>> from urwid import Pile
    >>> layout = TableLayout([TableColumn(), TableColumn(align="right")])
    >>> pile = Pile([layout.row(["name", "1"]), layout.row(["n", "22"])])
    >>> [line.decode() for line in pile.render((10,)).text]
    ['name  1   ', 'n    22   ']
    """

    def __init__(self, columns: Sequence[TableColumn], *, dividechars: int = 1) -> None:
        """Validate the column specifications.

        :param columns: one specification per column
        :param dividechars: blank screen columns between two visible columns
        :raises TableError: a specification or *dividechars* is invalid; the message names the column index.
        """
        if not isinstance(dividechars, int) or isinstance(dividechars, bool) or dividechars < 0:
            raise TableError(f"dividechars must be an int >= 0, not {dividechars!r}")
        self._columns = tuple(columns)
        self._dividechars = dividechars
        # per column: the kind of width, the given width or the weight, and the minimum
        self._kinds: tuple[WHSettings, ...] = ()
        self._amounts: tuple[int | float, ...] = ()
        kinds: list[WHSettings] = []
        amounts: list[int | float] = []
        for index, column in enumerate(self._columns):
            kind, amount = self._validate_column(index, column)
            kinds.append(kind)
            amounts.append(amount)
        self._kinds = tuple(kinds)
        self._amounts = tuple(amounts)
        self._label_widths = tuple(Text(column.label).pack(())[0] for column in self._columns)
        # the widest measured cell of each PACK column (0 for the other columns) over the registered rows
        self._pack_max = [0] * len(self._columns)
        self._natural = self._natural_from_maxima()
        # rows built through this layout and not in a table, with their count: a smaller len() means some were
        # collected, and the maxima are recomputed without them
        self._free_rows: weakref.WeakSet[TableRow] = weakref.WeakSet()
        self._free_count = 0
        # the rows of the table that owns this layout, set by the table
        self._owner_rows: weakref.ref[_TableRows] | None = None
        self._owner_changed: weakref.WeakMethod[Callable[[], None]] | None = None
        self._allocations: dict[int, tuple[int, ...]] = {}
        # the row columns laid out since the last width change: the only ones that can hold a canvas at the old widths
        self._rendered: weakref.WeakSet[_TableColumns] = weakref.WeakSet()

    @staticmethod
    def _validate_column(index: int, column: TableColumn) -> tuple[WHSettings, int | float]:
        """Return the kind of width of *column* and its given width or weight.

        :raises TableError: *column* is not a valid specification.
        """
        if not isinstance(column, TableColumn):
            raise TableError(f"column {index}: a TableColumn is expected, not {column!r}")
        width = column.width
        if width == WHSettings.PACK:
            kind: WHSettings = WHSettings.PACK
            amount: int | float = 0
        elif isinstance(width, int) and not isinstance(width, bool):
            if width < 0:
                raise TableError(f"column {index}: a given width must be >= 0, not {width!r}")
            kind, amount = WHSettings.GIVEN, width
        elif isinstance(width, tuple) and len(width) == 2 and width[0] == WHSettings.WEIGHT:
            weight = width[1]
            if (
                not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not math.isfinite(weight)
                or weight <= 0
            ):
                raise TableError(f"column {index}: a weight must be a finite number > 0, not {weight!r}")
            kind, amount = WHSettings.WEIGHT, weight
        else:
            raise TableError(f"column {index}: invalid width {width!r}")
        if kind != WHSettings.GIVEN and (
            not isinstance(column.min_width, int) or isinstance(column.min_width, bool) or column.min_width < 1
        ):
            raise TableError(f"column {index}: min_width must be an int >= 1, not {column.min_width!r}")
        if column.align not in _TEXT_ALIGNS:
            raise TableError(f"column {index}: invalid align {column.align!r}")
        if column.wrap not in _TEXT_WRAPS:
            raise TableError(f"column {index}: invalid wrap {column.wrap!r}")
        return kind, amount

    @property
    def columns(self) -> tuple[TableColumn, ...]:
        """The column specifications."""
        return self._columns

    @property
    def dividechars(self) -> int:
        """Blank screen columns between two visible columns."""
        return self._dividechars

    def row(
        self,
        cells: Sequence[_Cell],
        *,
        data: typing.Any = None,
        attr: _AttrMapLike | None = None,
        focus_attr: _AttrMapLike | None = None,
        selectable: bool = True,
        span: bool = False,
    ) -> TableRow:
        """Build a row of this layout; see :class:`TableRow` for the arguments.

        :raises TableError: the row does not fit the columns, see :class:`TableRow`.
        """
        return TableRow(
            self,
            cells,
            data=data,
            attr=attr,
            focus_attr=focus_attr,
            selectable=selectable,
            span=span,
        )

    def widths(self, maxcol: int) -> tuple[int, ...]:
        """Return the width of each column at *maxcol* screen columns.

        The widths and a divider between every two visible columns fit in *maxcol*.
        A width of 0 hides the column.
        When the natural widths do not fit, the weighted columns are at their minimum first,
        then the PACK columns shrink in proportion to how far they are above their minimum,
        and as the last resort the rightmost visible column is hidden. A given width never shrinks.

        :raises TableError: *maxcol* is negative.
        """
        if maxcol < 0:
            raise TableError(f"maxcol must be >= 0, not {maxcol!r}")
        self._check_collected()
        if (widths := self._allocations.pop(maxcol, None)) is None:
            widths = self._allocate(maxcol)
            if len(self._allocations) >= _ALLOCATIONS_KEPT:
                del self._allocations[next(iter(self._allocations))]
        self._allocations[maxcol] = widths
        return widths

    def natural_width(self) -> int:
        """Return the smallest width at which no column shrinks or is hidden.

        It is the sum of the natural widths of the visible columns and their dividers,
        where a weighted column counts at its minimum.
        """
        self._check_collected()
        visible = [
            width for kind, width in zip(self._kinds, self._natural, strict=True) if kind != WHSettings.GIVEN or width
        ]
        return sum(visible) + self._dividechars * max(len(visible) - 1, 0)

    def invalidate_widths(self) -> None:
        """Measure every cell of every registered row again.

        Call it after a cell widget given by the caller changed its packed width.
        Text cells the layout made from text markup do not need it.
        """
        for row in self._iter_rows():
            row._measure()
        self._recompute_maxima(range(len(self._columns)))
        self._update_natural()

    def _natural_from_maxima(self) -> tuple[int, ...]:
        """Return the natural width of each column from the measured maxima."""
        natural: list[int] = []
        for column, kind, amount, label, measured in zip(
            self._columns,
            self._kinds,
            self._amounts,
            self._label_widths,
            self._pack_max,
            strict=True,
        ):
            if kind == WHSettings.GIVEN:
                natural.append(int(amount))
            elif kind == WHSettings.PACK:
                natural.append(max(column.min_width, label, measured))
            else:
                natural.append(column.min_width)
        return tuple(natural)

    def _allocate(self, maxcol: int) -> tuple[int, ...]:
        """Compute the widths at *maxcol*, as :meth:`widths` describes."""
        natural = self._natural
        kinds = self._kinds
        minimums = [column.min_width for column in self._columns]
        visible = [index for index, kind in enumerate(kinds) if kind != WHSettings.GIVEN or natural[index]]
        while visible:
            widths = [0] * len(natural)
            for index in visible:
                widths[index] = natural[index]
            reserved = sum(widths) + self._dividechars * (len(visible) - 1)
            if reserved <= maxcol:
                self._grow([index for index in visible if kinds[index] == WHSettings.WEIGHT], widths, maxcol - reserved)
                return tuple(widths)

            deficit = reserved - maxcol
            slack = {index: widths[index] - minimums[index] for index in visible if kinds[index] == WHSettings.PACK}
            total = sum(slack.values())
            if total >= deficit:
                remainder = deficit
                for index, amount in slack.items():
                    given_up = amount * deficit // total
                    widths[index] -= given_up
                    remainder -= given_up
                for _ in range(remainder):
                    widest = max(
                        (index for index in slack if widths[index] > minimums[index]),
                        key=lambda index: widths[index],
                    )
                    widths[widest] -= 1
                return tuple(widths)

            # the last resort: a row wider than maxcol is the only alternative
            visible.pop()
        return (0,) * len(natural)

    def _grow(self, weighted: list[int], widths: list[int], extra: int) -> None:
        """Share *extra* screen columns and the minimums of the *weighted* columns by weight, as Columns does."""
        if not weighted:
            return
        minimums = {index: self._columns[index].min_width for index in weighted}
        grow = extra + sum(minimums.values())
        weights = [(self._amounts[index], index) for index in weighted]
        if max(weight for weight, _index in weights) > sys.float_info.max / (len(weights) * max(grow, 1)):
            # grow * weight could overflow a float: scale the weights to at most 1, keeping their ratios
            max_weight = max(weight for weight, _index in weights)
            weights = [(weight / max_weight, index) for weight, index in weights]
        ordered = sorted(weights)
        wtotal = sum(weight for weight, _index in ordered)
        for position, (weight, index) in enumerate(ordered):
            if position == len(ordered) - 1:
                width = max(grow, minimums[index])
            else:
                width = max(int(grow * weight / wtotal + 0.5), minimums[index])
            widths[index] = width
            grow -= width
            wtotal -= weight
        # pinning to a minimum can leave the total above the room: take it back from the widest weighted columns
        excess = -grow
        while excess > 0:
            widest = max((index for index in weighted if widths[index] > minimums[index]), key=lambda i: widths[i])
            widths[widest] -= 1
            excess -= 1

    def _iter_rows(self) -> Iterator[TableRow]:
        """Yield the registered rows: those built through the layout and still alive, and those of its table."""
        owner = None if self._owner_rows is None else self._owner_rows()
        return itertools.chain(list(self._free_rows), () if owner is None else owner)

    def _recompute_maxima(self, indices: Iterable[int]) -> None:
        """Set the maxima of the PACK columns among *indices* from the stored widths, in one pass over the rows."""
        columns = [index for index in indices if self._kinds[index] == WHSettings.PACK]
        if not columns:
            return
        maxima = dict.fromkeys(columns, 0)
        for row in self._iter_rows():
            widths = row._cell_widths
            for index in columns:
                if (width := widths[index]) is not None and width > maxima[index]:
                    maxima[index] = width
        for index, width in maxima.items():
            self._pack_max[index] = width

    def _update_natural(self) -> None:
        """Recompute the natural widths from the maxima, and drop what was laid out with them if they changed."""
        natural = self._natural_from_maxima()
        if natural == self._natural:
            return
        self._natural = natural
        self._allocations.clear()
        rendered = list(self._rendered)
        self._rendered.clear()
        for columns in rendered:
            columns._invalidate()
        if self._owner_changed is not None and (callback := self._owner_changed()) is not None:
            callback()

    def _check_collected(self) -> None:
        """Recompute the maxima when a row built through the layout was collected since the last check."""
        if len(self._free_rows) != self._free_count:
            self._free_count = len(self._free_rows)
            self._recompute_maxima(range(len(self._columns)))
            self._update_natural()

    def _record_rendered(self, columns: _TableColumns) -> None:
        """Remember that *columns* was laid out with the current widths."""
        self._rendered.add(columns)

    def _add_widths(self, cell_widths: Sequence[int | None]) -> None:
        """Count the stored widths of a row that became registered."""
        for index, width in enumerate(cell_widths):
            if width is not None and width > self._pack_max[index] and self._kinds[index] == WHSettings.PACK:
                self._pack_max[index] = width
        self._update_natural()

    def _cell_width_changed(self, index: int, old: int | None, new: int | None) -> None:
        """Update the maximum of column *index* after a registered cell was measured again."""
        if self._kinds[index] != WHSettings.PACK:
            return
        if new is not None and new > self._pack_max[index]:
            self._pack_max[index] = new
        elif old is not None and old >= self._pack_max[index]:
            self._recompute_maxima((index,))
        self._update_natural()

    def _register(self, row: TableRow) -> None:
        """Register a new row as built through the layout and not in a table."""
        self._check_collected()
        self._free_rows.add(row)
        self._free_count += 1
        row._registered = True
        self._add_widths(row._cell_widths)

    def _adopt(self, row: TableRow) -> None:
        """Count *row* as a row of the table that owns the layout."""
        if row._registered:
            self._check_collected()
            if row in self._free_rows:
                self._free_rows.discard(row)
                self._free_count -= 1
            return
        row._registered = True
        self._add_widths(row._cell_widths)

    def _release(self, rows: Iterable[TableRow]) -> None:
        """Stop counting *rows*, removed from the table that owns the layout, recomputing each column once."""
        affected: set[int] = set()
        for row in rows:
            row._registered = False
            for index, width in enumerate(row._cell_widths):
                if width is not None and width >= self._pack_max[index]:
                    affected.add(index)
        self._recompute_maxima(sorted(affected))
        self._update_natural()


class TableRow(WidgetWrap[_TableColumns]):
    """One row of cells laid out by a :class:`TableLayout`.

    A row is selectable unless built with ``selectable=False``, whatever its cells,
    so a row of plain text can take the focus in a :class:`Table`.

    The attribute map applied to the row's canvas is, in this order:

    - :attr:`focus_attr`, or the table's ``focus_attr``, when the row renders in focus;
    - the result of the table's ``row_attr`` callable, when it returns something other than ``None``;
    - :attr:`attr`, or the table's ``attr``.

    A map given as a dict also maps the cells' own attributes.
    """

    def __init__(
        self,
        layout: TableLayout,
        cells: Sequence[_Cell],
        *,
        data: typing.Any = None,
        attr: _AttrMapLike | None = None,
        focus_attr: _AttrMapLike | None = None,
        selectable: bool = True,
        span: bool = False,
    ) -> None:
        """Build the row and register it with *layout*.

        :param layout: the layout whose widths the row uses
        :param cells: one widget or text markup per column; a short row is padded with empty text cells.
            Text markup becomes a text cell with the column's ``align`` and ``wrap``.
            The sequence is copied.
        :param data: any object the caller keeps with the row, such as the record it shows
        :param attr: attribute map of the row, in any form :class:`AttrMap` takes
        :param focus_attr: attribute map of the row while it renders in focus
        :param selectable: whether the row takes the focus
        :param span: one cell drawn across every column, which the column widths do not measure
        :raises TableError: *cells* is a string rather than a sequence of cells, there are more cells than columns,
            a span row does not have exactly one cell,
            or a cell widget does not support FLOW sizing.
        """
        if isinstance(cells, (str, bytes)):
            raise TableError(f"a row is a sequence of cells, not text: {cells!r}")
        columns = layout.columns
        if span:
            if len(cells) != 1:
                raise TableError(f"a span row has exactly one cell, not {len(cells)}")
        elif len(cells) > len(columns):
            raise TableError(f"{len(cells)} cells do not fit {len(columns)} columns")
        widgets: list[Widget] = []
        for index, cell in enumerate(cells):
            if isinstance(cell, Widget):
                if Sizing.FLOW not in cell.sizing():
                    raise TableError(f"cell {index}: {cell!r} does not support FLOW sizing")
                widgets.append(cell)
            else:
                column = columns[0] if span else columns[index]
                widgets.append(_TableText(cell, column.align, column.wrap))
        if not span:
            widgets.extend(_TableText("", column.align, column.wrap) for column in columns[len(widgets) :])

        self._layout = layout
        self._cells = tuple(widgets)
        self._span = span
        self.data = data
        self._attr = None if attr is None else _attr_map_dict(attr)
        self._focus_attr = None if focus_attr is None else _attr_map_dict(focus_attr)
        self._selectable = selectable
        self._index: int | None = None
        # the rows of the table the row is in, which also reach the table
        self._rows: weakref.ref[_TableRows] | None = None
        self._registered = False
        self._cell_widths: tuple[int | None, ...] = ()
        super().__init__(_TableColumns(layout, self._cells, span=span))
        self._measure()
        for cell in self._cells:
            if isinstance(cell, _TableText):
                cell._row = weakref.ref(self)
        layout._register(self)

    @property
    def layout(self) -> TableLayout:
        """The layout whose widths the row uses."""
        return self._layout

    @property
    def cells(self) -> tuple[Widget, ...]:
        """The cell widgets, including the text cells made from text markup."""
        return self._cells

    @property
    def span(self) -> bool:
        """Whether the row is one cell drawn across every column."""
        return self._span

    @property
    def index(self) -> int | None:
        """The position of the row in its table's rows, or ``None`` outside a table."""
        return self._index

    @property
    def attr(self) -> dict[Hashable, Hashable] | None:
        """Attribute map of the row, or ``None``; set in any form :class:`AttrMap` takes."""
        return None if self._attr is None else self._attr.copy()

    @attr.setter
    def attr(self, attr: _AttrMapLike | None) -> None:
        self._attr = None if attr is None else _attr_map_dict(attr)
        self._invalidate()

    @property
    def focus_attr(self) -> dict[Hashable, Hashable] | None:
        """Attribute map of the row while it renders in focus, or ``None``."""
        return None if self._focus_attr is None else self._focus_attr.copy()

    @focus_attr.setter
    def focus_attr(self, focus_attr: _AttrMapLike | None) -> None:
        self._focus_attr = None if focus_attr is None else _attr_map_dict(focus_attr)
        self._invalidate()

    def selectable(self) -> bool:
        """Return whether the row takes the focus, as set when it was built or by :meth:`set_selectable`."""
        return self._selectable

    def set_selectable(self, selectable: bool) -> None:
        """Set whether the row takes the focus."""
        self._selectable = selectable
        self._invalidate()

    def sizing(self) -> frozenset[Sizing]:
        """Return FLOW: a row is laid out at the width it is given."""
        return frozenset((Sizing.FLOW,))

    def _table(self) -> Table | None:
        """Return the table the row is in, or ``None``."""
        rows = None if self._rows is None else self._rows()
        return None if rows is None else rows._table()

    def _attr_map(self, focus: bool) -> dict[Hashable, Hashable] | None:
        """Return the attribute map to apply to a render, in the order the class describes."""
        table = self._table()
        if focus:
            focus_attr = self._focus_attr if self._focus_attr is not None or table is None else table._focus_attr
            if focus_attr is not None:
                return focus_attr
        if table is not None and table._row_attr is not None:
            computed = table._row_attr(typing.cast("int", self._index), self.data)
            if computed is not None:
                return _attr_map_dict(computed)
        return self._attr if self._attr is not None or table is None else table._attr

    def render(self, size: tuple[int], focus: bool = False) -> Canvas:  # type: ignore[override]
        """Render the cells and apply the row's attribute map."""
        canvas = self._w.render(size, focus=focus)
        if (attr_map := self._attr_map(focus)) is None:
            return canvas
        mapped = CompositeCanvas(canvas)
        mapped.fill_attr_apply(attr_map)
        return mapped

    def _measure(self) -> None:
        """Store the packed width of each cell that supports FIXED sizing, ``None`` for the others."""
        if self._span:
            self._cell_widths = (None,) * len(self._layout.columns)
            return
        self._cell_widths = tuple(
            cell.pack((), False)[0] if Sizing.FIXED in cell.sizing() else None for cell in self._cells
        )

    def _cell_changed(self, cell: _TableText) -> None:
        """Measure *cell* again after its text changed, and update its column when the row is registered."""
        if self._span:
            return
        index = next(index for index, own in enumerate(self._cells) if own is cell)
        old = self._cell_widths[index]
        new = cell.pack((), False)[0]
        if new == old:
            return
        self._cell_widths = (*self._cell_widths[:index], new, *self._cell_widths[index + 1 :])
        if self._registered:
            self._layout._cell_width_changed(index, old, new)


# set_modified_callback raises by design, as in SimpleFocusListWalker
class _TableRows(SimpleFocusListWalker[TableRow]):  # pylint: disable=abstract-method
    """The rows of a table: plain sequences become rows of its layout, and every change is validated first."""

    def __init__(self, layout: TableLayout, rows: Iterable[Sequence[_Cell] | TableRow]) -> None:
        self._layout = layout
        self._table: Callable[[], Table | None] = lambda: None
        # (first changed position, rows removed, rows added) of the change being applied; None for a reordering
        self._change: tuple[int, tuple[TableRow, ...], tuple[TableRow, ...]] | None = None
        converted = [self._convert(row) for row in rows]
        self._validate((0, 0, 1), converted)
        super().__init__(converted)
        self.set_validate_contents_modified(self._validate_modified)

    def _convert(self, row: Sequence[_Cell] | TableRow) -> TableRow:
        """Return *row* as a row of the layout.

        :raises TableError: a sequence does not fit the columns.
        """
        if isinstance(row, TableRow):
            return row
        return self._layout.row(row)

    def _validate(self, indices: tuple[int, int, int], new_items: Collection[TableRow]) -> None:
        """Reject rows of another layout and rows that would be in the table twice.

        :raises TableError: a row is of another layout or would be in the table twice.
        """
        replaced = {id(self[index]) for index in range(*indices)}
        seen: set[int] = set()
        for row in new_items:
            if not isinstance(row, TableRow) or row.layout is not self._layout:
                raise TableError(f"{row!r} is not a row of this table's layout")
            if id(row) in seen or (row._rows is not None and row._rows() is self and id(row) not in replaced):
                raise TableError(f"{row!r} would be in the table twice")
            seen.add(id(row))

    def _validate_modified(self, indices: tuple[int, int, int], new_items: Collection[TableRow]) -> None:
        """Validate a change and record it for the table's ``"modified"`` handler."""
        self._validate(indices, new_items)
        changed = range(*indices)
        first = min(changed) if changed else indices[0]
        self._change = (first, tuple(self[index] for index in changed), tuple(new_items))

    def _modify(self, focus: typing.Any, change: typing.Any, /, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        try:
            return super()._modify(focus, change, *args, **kwargs)
        finally:
            self._change = None

    def append(self, item: Sequence[_Cell] | TableRow) -> None:
        """Append a row; a sequence becomes a row of the layout."""
        super().append(self._convert(item))

    def insert(self, index: typing.SupportsIndex, item: Sequence[_Cell] | TableRow) -> None:
        """Insert a row before *index*; a sequence becomes a row of the layout."""
        super().insert(index, self._convert(item))

    def extend(self, items: Iterable[Sequence[_Cell] | TableRow]) -> None:
        """Append rows; each sequence becomes a row of the layout."""
        super().extend([self._convert(item) for item in items])

    def __setitem__(self, i: typing.SupportsIndex | slice, y: typing.Any) -> None:
        """Replace rows; each sequence becomes a row of the layout."""
        if isinstance(i, slice):
            super().__setitem__(i, [self._convert(item) for item in y])
        else:
            super().__setitem__(i, self._convert(y))


class Table(Widget):
    """Rows of cells in columns of shared widths, under a fixed header and with a focused row.

    The rows scroll in a :class:`ListBox`; the header stays on top and never takes the focus.
    It is a box and flow widget, and a fixed widget as well when no column is weighted.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`body`,
    with the old and the new position, which is ``None`` while the table is empty.
    A row replaced in place at the focus sends nothing.
    Sends ``"activate"`` with the focus position when the focused row leaves the ``activate`` command
    (:kbd:`enter` and :kbd:`space` by default) unhandled. A mouse click moves the focus and reaches the cell only.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed", "activate"]

    def __init__(
        self,
        columns: Sequence[TableColumn],
        rows: Iterable[Sequence[_Cell] | TableRow] = (),
        *,
        header: bool = True,
        header_attr: _AttrMapLike | None = None,
        dividechars: int = 1,
        attr: _AttrMapLike | None = None,
        focus_attr: _AttrMapLike | None = None,
        unfocused_focus_attr: _AttrMapLike | None = None,
        max_rows: int | None = None,
        row_attr: Callable[[int, typing.Any], _AttrMapLike | None] | None = None,
        select_navigation: bool = False,
        scrollbar: bool | None = False,
    ) -> None:
        """Create the table.

        :param columns: one specification per column; their number is the number of cells of every row
        :param rows: the initial rows, as :class:`TableRow` objects of :attr:`layout` or sequences of cells
        :param header: draw the column labels above the rows
        :param header_attr: attribute map of the header
        :param dividechars: blank screen columns between two visible columns
        :param attr: attribute map of a row without its own :attr:`TableRow.attr`
        :param focus_attr: attribute map of the focused row without its own :attr:`TableRow.focus_attr`
        :param unfocused_focus_attr: attribute map applied to the focused row while the table renders without
            focus, over the row's own map, as :attr:`ListBox.unfocused_focus_attr` does
        :param max_rows: the most rows of body a flow size shows; ``None`` shows every row
        :param row_attr: ``row_attr(index, data)`` called each time a row renders, see :attr:`row_attr`
        :param select_navigation: let the ``'next selectable'`` and ``'prev selectable'`` commands
            (:kbd:`tab` and :kbd:`shift tab`) move across the cells and then to the next or previous row
        :param scrollbar: ``True`` draws a scrollbar right of the rows, ``None`` only when the rows do not fit,
            ``False`` never; while it is on, its column counts in the natural width
        :raises TableError: a column specification, *dividechars*, *max_rows* or a row is invalid.
        """
        if max_rows is not None and (not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 0):
            raise TableError(f"max_rows must be None or an int >= 0, not {max_rows!r}")
        super().__init__()
        self._layout = TableLayout(columns, dividechars=dividechars)
        self._header = (
            TableRow(
                self._layout, [column.label for column in self._layout.columns], attr=header_attr, selectable=False
            )
            if header
            else None
        )
        self._attr = None if attr is None else _attr_map_dict(attr)
        self._focus_attr = None if focus_attr is None else _attr_map_dict(focus_attr)
        self._row_attr = row_attr
        self._max_rows = max_rows
        self._scrollbar = scrollbar
        self._select_navigation = select_navigation

        self._rows = _TableRows(self._layout, rows)
        self._rows._table = weakref.ref(self)
        rows_ref = weakref.ref(self._rows)
        self._layout._owner_rows = rows_ref
        for index, row in enumerate(self._rows):
            self._layout._adopt(row)
            row._index = index
            row._rows = rows_ref
            row._w.select_navigation = select_navigation
        self._layout._owner_changed = weakref.WeakMethod(self._widths_changed)

        self._listbox: ListBox[int] = ListBox(
            self._rows,
            select_navigation=select_navigation,
            unfocused_focus_attr=unfocused_focus_attr,
            focus_when_empty=False,
        )
        self._bar = ScrollBar(self._listbox, visible=True) if scrollbar is not False else None
        signals.connect_signal(self._rows, "modified", type(self)._rows_modified, weak_args=[self])
        # connected last, so that filling the rows during construction sends no signal
        self._rows.set_focus_moved_callback(self._focus_moved)

    def _focus_moved(self, old: int | None, new: int | None) -> None:
        self._emit("focus changed", old, new)

    @property
    def layout(self) -> TableLayout:
        """The layout of the columns, which builds and measures the rows."""
        return self._layout

    @property
    def body(self) -> _TableRows:
        """The rows of the table, below the header.

        A sequence of cells added to it becomes a :class:`TableRow` of :attr:`layout`, so ``body[i]`` is that row.
        A change is validated before it is applied, and a :exc:`TableError` leaves the rows unchanged.
        Replace every row with ``table.body[:] = rows``.
        """
        return self._rows

    @property
    def row_attr(self) -> Callable[[int, typing.Any], _AttrMapLike | None] | None:
        """``row_attr(index, data)``, called each time a row renders, or ``None``.

        A result other than ``None`` is the row's attribute map, in any form :class:`AttrMap` takes,
        over :attr:`TableRow.attr`. A focused row with a focus map uses that instead.
        A change of the rows calls it again for the rows from the changed position on;
        a data object changed in place is seen only when the row is assigned again (``body[i] = body[i]``).
        """
        return self._row_attr

    @row_attr.setter
    def row_attr(self, row_attr: Callable[[int, typing.Any], _AttrMapLike | None] | None) -> None:
        self._row_attr = row_attr
        for row in self._rows:
            row._invalidate()
        self._invalidate()

    @property
    def max_rows(self) -> int | None:
        """The most rows of body a flow size shows; ``None`` shows every row."""
        return self._max_rows

    @property
    def unfocused_focus_attr(self) -> dict[Hashable, Hashable] | None:
        """Attribute map applied to the focused row while the table renders without focus, see :class:`ListBox`."""
        return self._listbox.unfocused_focus_attr

    @unfocused_focus_attr.setter
    def unfocused_focus_attr(self, attr_map: _AttrMapLike | None) -> None:
        self._listbox.unfocused_focus_attr = attr_map

    @property
    def focus(self) -> TableRow | None:
        """The row in focus, or ``None`` when the table is empty."""
        position = self._rows.focus
        return None if position is None else self._rows[position]

    @property
    def focus_position(self) -> int:
        """The index of the row in focus.

        :raises IndexError: the table is empty, or the position set is not an index of a row.
        """
        if (position := self._rows.focus) is None:
            raise IndexError("No focus_position, Table is empty")
        return position

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        if not isinstance(position, int) or not 0 <= position < len(self._rows):
            raise IndexError(f"No Table row at position {position!r}")
        self._listbox.focus_position = position

    def selectable(self) -> bool:
        """Return whether the table has a row to focus."""
        return self._listbox.selectable()

    def sizing(self) -> frozenset[Sizing]:
        """Return BOX and FLOW, and FIXED as well when no column is weighted."""
        if any(isinstance(column.width, tuple) for column in self._layout.columns):
            return frozenset((Sizing.BOX, Sizing.FLOW))
        return frozenset((Sizing.BOX, Sizing.FLOW, Sizing.FIXED))

    def _natural_width(self) -> int:
        """Return the natural width of the columns, with the scrollbar column while the scrollbar is on."""
        bar = 0 if self._bar is None else self._bar.scrollbar_width
        return self._layout.natural_width() + bar

    def _rows_modified(self) -> None:
        """Register the rows a change added, release those it removed, and number the rows from the change on."""
        first, removed, added = (0, (), ()) if (change := self._rows._change) is None else change
        added_ids = {id(row) for row in added}
        removed_ids = {id(row) for row in removed}
        released = [row for row in removed if id(row) not in added_ids]
        for row in released:
            row._index = None
            row._rows = None
            row._w.select_navigation = False
        self._layout._release(released)
        rows_ref = weakref.ref(self._rows)
        for row in added:
            if id(row) not in removed_ids:
                row._rows = rows_ref
                row._w.select_navigation = self._select_navigation
                self._layout._adopt(row)
        for index in range(first, len(self._rows)):
            row = self._rows[index]
            row._index = index
            if self._row_attr is not None:
                row._invalidate()
        self._invalidate()

    def _widths_changed(self) -> None:
        """Drop what was laid out with the old column widths."""
        self._listbox._invalidate()
        if self._header is not None:
            self._header._invalidate()
        self._invalidate()

    def _body_rows(self, maxcol: int, limit: int) -> int:
        """Return the rows of the body at *maxcol*, counting no further than one past *limit*."""
        total = 0
        focus = self._rows.focus
        for index, row in enumerate(self._rows):
            total += row.rows((maxcol,), index == focus)
            if total > limit:
                break
        return total

    def _arrange(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> _Arrangement:
        """Divide *size* between the header, the rows and the scrollbar."""
        maxcol = size[0] if size else self._natural_width()
        bar_width = 0 if self._bar is None else self._bar.scrollbar_width

        def header_rows(content: int) -> int:
            return 0 if self._header is None else self._header.rows((content,))

        if len(size) == 2:
            limit: int | None = max(size[1] - header_rows(maxcol), 0)
        else:
            limit = self._max_rows

        if self._bar is None:
            bar = False
        elif self._scrollbar:
            bar = True
        else:
            content = max(maxcol - bar_width, 0)
            bar = limit is not None and self._body_rows(content, limit) > limit

        content = max(maxcol - bar_width, 0) if bar else maxcol
        hrows = header_rows(content)
        if len(size) == 2:
            body_rows: int | None = max(size[1] - hrows, 0)
        elif self._max_rows is not None:
            body_rows = min(self._body_rows(content, self._max_rows), self._max_rows)
        else:
            body_rows = None
        return _Arrangement(maxcol, content, hrows, body_rows, bar)

    def _body_widget_size(
        self,
        maxcol: int,
        body_rows: int | None,
        bar: bool,
    ) -> tuple[ListBox[int] | ScrollBar[ListBox[int]], tuple[int] | tuple[int, int]]:
        """Return the widget that draws the body and the size to give it."""
        widget: ListBox[int] | ScrollBar[ListBox[int]] = self._listbox
        if bar and self._bar is not None:
            widget = self._bar
        if body_rows is None:
            return widget, (maxcol,)
        return widget, (maxcol, body_rows)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the header rows and the body rows, at most :attr:`max_rows` of body.

        Without :attr:`max_rows` every row is measured.
        """
        arrangement = self._arrange(size)
        if (body_rows := arrangement.body_rows) is None:
            body_rows = self._body_rows(arrangement.content, sys.maxsize)
        return arrangement.header_rows + body_rows

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the natural width and the rows at it for ``()``, as :meth:`Widget.pack` does otherwise."""
        if not size:
            maxcol = self._natural_width()
            return maxcol, self.rows((maxcol,), focus)
        return super().pack(size, focus)

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> Canvas:
        """Render the header over the rows."""
        maxcol, content, hrows, body_rows, bar = self._arrange(size)
        combine: list[tuple[Canvas, Hashable, bool]] = []
        if self._header is not None and hrows:
            head = self._header.render((content,))
            if bar:
                head = CompositeCanvas(head)
                head.pad_trim_left_right(0, maxcol - content)
            if len(size) == 2 and hrows > size[1]:
                head = CompositeCanvas(head)
                head.trim_end(hrows - size[1])
            combine.append((head, "header", False))
        if self._rows and body_rows != 0:
            widget, body_size = self._body_widget_size(maxcol, body_rows, bar)
            combine.append((widget.render(body_size, focus), "body", True))
        elif len(size) == 2 and body_rows:
            combine.append((SolidCanvas(" ", maxcol, body_rows), "body", False))
        if not combine:
            return SolidCanvas(" ", maxcol, 0)
        return CanvasCombine(combine)

    def _body_call_size(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
    ) -> tuple[ListBox[int] | ScrollBar[ListBox[int]], tuple[int] | tuple[int, int], int] | None:
        """Return the body widget, its size and the header rows, or ``None`` when no row is shown."""
        if not self._rows:
            return None
        maxcol, _content, hrows, body_rows, bar = self._arrange(size)
        if body_rows == 0:
            return None
        widget, body_size = self._body_widget_size(maxcol, body_rows, bar)
        return widget, body_size, hrows

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the key to the rows; send ``"activate"`` for an ``activate`` command they leave unhandled.

        :returns: ``None`` if the key was handled, otherwise the key.
        """
        if (body := self._body_call_size(size)) is None:
            return key
        widget, body_size, _hrows = body
        if (unhandled := widget.keypress(body_size, key)) is None:
            return None
        if self._command_map[unhandled] == Command.ACTIVATE and self._rows.focus is not None:
            self._emit("activate", self._rows.focus)
            return None
        return unhandled

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the event to the rows; the header takes no mouse events."""
        if (body := self._body_call_size(size)) is None:
            return False
        widget, body_size, hrows = body
        if row < hrows:
            return False
        return widget.mouse_event(body_size, event, button, col, row - hrows, focus)

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focused row, below the header."""
        if (body := self._body_call_size(size)) is None:
            return None
        widget, body_size, hrows = body
        if (coords := widget.get_cursor_coords(body_size)) is None:
            return None
        return coords[0], coords[1] + hrows
