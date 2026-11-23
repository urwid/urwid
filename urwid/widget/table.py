"""Table: rows of cells whose columns share widths, between a fixed header and footer."""

# The layout, its rows and their table keep one set of bookkeeping between them through their protected members.
# pylint: disable=protected-access

from __future__ import annotations

import collections
import contextlib
import itertools
import math
import numbers
import operator
import sys
import typing
import weakref
from typing import Literal

from urwid import signals
from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.command_map import Command

from .attr_map import AttrMap, AttrMapError, _attr_map_dict
from .columns import Columns, _shrink_by_slack
from .constants import Align, Sizing, WHSettings, WrapMode
from .container import WidgetContainerMixin, _WeakCallback
from .list_walker import SimpleFocusListWalker
from .listbox import ListBox

# _ScrollBarOptions is imported at run time, so code that imports it from this module keeps working.
from .scrollable import SCROLLBAR_LEFT, ScrollBar, _scrollbar_arguments, _ScrollBarOptions
from .text import Text
from .widget import Widget, WidgetError, WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Hashable, Iterable, Iterator, Sequence

    from _typeshed import SupportsRichComparison

    from urwid.canvas import Canvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .container import _UnfocusedFocusAttrFunc
    from .list_walker import ListBoxContentsProto
    from .widget import AbstractWidget

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
    """How a table divides one size between its header, its rows, its footer and its scrollbar."""

    maxcol: int
    #: the width of the header, the footer and the rows: *maxcol* less the scrollbar while it is drawn
    content: int
    #: the rows of the header shown, 0 when it is dropped
    header_rows: int
    #: the rows of the footer shown, 0 when it is dropped
    footer_rows: int
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
    *attr* maps every cell of the column; :class:`TableRow` gives the order in which it and the row maps apply.
    *priority* decides which column a lack of room hides first, see :meth:`TableLayout.widths`.
    *key* names the column wherever a column index is accepted, see :meth:`TableLayout.column_index`.
    A :class:`TableLayout` validates the specification when it takes it.
    """

    #: Header text, drawn by :class:`Table` with ``header=True``.
    label: _TagMarkup = ""
    width: Literal[WHSettings.PACK] | int | tuple[Literal[WHSettings.WEIGHT], int | float] = WHSettings.PACK
    #: The narrowest a PACK or WEIGHT column becomes before the table hides a column instead.
    #: A PACK column whose cells and label are narrower keeps the width of its widest cell and label instead, unless
    #: it holds a cell that cannot be measured, which counts as this wide.
    #: :attr:`WHSettings.PACK`, for a PACK column only, keeps it as wide as its widest cell and its label.
    min_width: int | Literal[WHSettings.PACK] = 1
    align: Literal[Align.LEFT, Align.CENTER, Align.RIGHT] = Align.LEFT
    wrap: Literal[WrapMode.SPACE, WrapMode.CLIP, WrapMode.ELLIPSIS] = WrapMode.CLIP
    #: Attribute map of the column's cells; the header label, a footer built from cells and a span row do not use it.
    attr: _AttrMapLike | None = None
    #: Columns are hidden for lack of room in ascending order of this value; equal values go rightmost first.
    priority: int = 0
    #: A name accepted in place of the column's index: any hashable object except a number, unique in a layout.
    key: Hashable | None = None


class _TableText(Text):
    """Text cell made by a layout from text markup; changing its text re-measures its column."""

    def __init__(self, markup: _TagMarkup, align: Align, wrap: WrapMode) -> None:
        self._rows: weakref.WeakSet[TableRow] = weakref.WeakSet()
        super().__init__(markup, align, wrap)

    def _invalidate(self) -> None:
        super()._invalidate()
        for row in list(self._rows):
            row._cell_changed(self)


class _TableColumns(Columns):
    """Columns of one table row, laid out with the widths its layout shares between all its rows."""

    def __init__(self, layout: TableLayout, cells: Sequence[Widget], *, span: bool, column_attrs: bool) -> None:
        self._layout = layout
        self._span = span
        # the column index at each position of the contents; the layout's display order once _sync() ran
        self._display = layout._identity
        if column_attrs and not span:
            cells = [
                cell if attr is None else AttrMap(cell, attr) for cell, attr in zip(cells, layout._attrs, strict=True)
            ]
        super().__init__(
            [(WHSettings.WEIGHT, 1, cell) for cell in cells],
            dividechars=layout.dividechars,
        )

    def _sync(self) -> None:
        """Arrange the contents in the display order of the layout.

        The focus stays on the same column while the order shows it.
        It follows the column index, not the widget, since a row may hold one widget in two columns.
        A focused column the order hides passes the focus to the nearest visible shown column by index:
        a selectable cell first, the left one of two at the same distance.
        With no visible shown column, the focus stays where it is.
        """
        layout = self._layout
        display = layout._display
        if self._span or self._display is display:
            return
        old = self._display
        contents = self.contents
        focus = contents.focus
        by_column: list[typing.Any] = [None] * len(old)
        for position, item in enumerate(contents):
            by_column[old[position]] = item
        self._display = display
        contents[:] = [by_column[index] for index in display]
        if focus is None:
            return
        column = old[focus]
        if column not in layout._shown:
            nearest = sorted(
                (
                    index
                    for index in layout._order
                    if layout._kinds[index] != WHSettings.GIVEN or layout._amounts[index]
                ),
                key=lambda index: (not by_column[index][0].selectable(), abs(index - column), index),
            )
            if nearest:
                column = nearest[0]
        self.focus_position = display.index(column)

    def column_widths(self, size: tuple[int] | tuple[int, int], focus: bool = False) -> list[int]:
        """Return the widths the layout allocates at the width in *size*, in display order.

        A full-width row gets all of it.
        """
        self._layout._record_rendered(self)
        if self._span:
            return [size[0]]
        self._sync()
        widths = self._layout.widths(size[0])
        return [widths[index] for index in self._display]

    def _select_candidates(self, *, reverse: bool, from_edge: bool) -> Iterator[int]:
        """Yield the selectable positions as :class:`Columns` does.

        A column out of :attr:`TableLayout.column_order` or of given width 0 is skipped.
        That holds also before a render at the current order has measured the widths.
        """
        self._sync()
        candidates = super()._select_candidates(reverse=reverse, from_edge=from_edge)
        if self._span:
            yield from candidates
            return
        layout = self._layout
        for position in candidates:
            index = self._display[position]
            if index in layout._shown and (layout._kinds[index] != WHSettings.GIVEN or layout._amounts[index]):
                yield position


class TableLayout:
    """Column widths shared by every row built through the layout, with or without a :class:`Table`.

    Cells are measured once, when their row is built.
    A text cell the layout made measures itself again when its text changes.
    Another widget whose width changed needs :meth:`invalidate_widths`.

    :attr:`column_order` shows, hides and reorders the columns.
    The cells of a row and every column index keep the order of :attr:`columns` whatever it is.

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
        :raises TableError: a specification or *dividechars* is invalid, or two columns have the same key;
            the message names the column index.
        """
        if not isinstance(dividechars, int) or isinstance(dividechars, bool) or dividechars < 0:
            raise TableError(f"dividechars must be an int >= 0, not {dividechars!r}")
        self._columns = tuple(columns)
        self._dividechars = dividechars
        # per column: the kind of width, the given width or the weight, and the attribute map of its cells
        self._kinds: tuple[WHSettings, ...] = ()
        self._amounts: tuple[int | float, ...] = ()
        self._attrs: tuple[dict[Hashable, Hashable] | None, ...] = ()
        kinds: list[WHSettings] = []
        amounts: list[int | float] = []
        attrs: list[dict[Hashable, Hashable] | None] = []
        for index, column in enumerate(self._columns):
            kind, amount, attr_map = self._validate_column(index, column)
            kinds.append(kind)
            amounts.append(amount)
            attrs.append(attr_map)
        self._kinds = tuple(kinds)
        self._amounts = tuple(amounts)
        self._attrs = tuple(attrs)
        labels = [Text(column.label) for column in self._columns]
        self._label_widths = tuple(label.pack(())[0] for label in labels)
        self._key_index = self._keys(labels)
        # the shown columns left to right, and every column in the order a row arranges its cells:
        # the shown ones, then the hidden ones by index; a new tuple per change, so a row compares it by identity
        self._identity = tuple(range(len(self._columns)))
        self._order = self._identity
        self._display = self._identity
        self._shown = frozenset(self._identity)
        self._drop_sequence = self._drop_order()
        # the widest measured cell of each PACK column (0 for the other columns) over the registered rows
        self._pack_max = [0] * len(self._columns)
        # the number of registered rows, span rows aside, with a cell that cannot be measured in each PACK column
        self._pack_unmeasured = [0] * len(self._columns)
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
    def _validate_column(
        index: int,
        column: TableColumn,
    ) -> tuple[WHSettings, int | float, dict[Hashable, Hashable] | None]:
        """Return the kind of width of *column*, its given width or weight, and its attribute map as a dict.

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
        if (
            kind != WHSettings.GIVEN
            and not (kind == WHSettings.PACK and column.min_width == WHSettings.PACK)
            and (not isinstance(column.min_width, int) or isinstance(column.min_width, bool) or column.min_width < 1)
        ):
            raise TableError(
                f"column {index}: min_width must be an int >= 1, or PACK for a PACK width, not {column.min_width!r}"
            )
        if not isinstance(column.priority, int) or isinstance(column.priority, bool):
            raise TableError(f"column {index}: priority must be an int, not {column.priority!r}")
        if column.align not in _TEXT_ALIGNS:
            raise TableError(f"column {index}: invalid align {column.align!r}")
        if column.wrap not in _TEXT_WRAPS:
            raise TableError(f"column {index}: invalid wrap {column.wrap!r}")
        try:
            attr_map = None if column.attr is None else _attr_map_dict(column.attr)
        except AttrMapError as exc:
            raise TableError(f"column {index}: invalid attr {column.attr!r}") from exc
        return kind, amount, attr_map

    def _keys(self, labels: Sequence[Text]) -> dict[Hashable, int]:
        """Return the column index of each explicit key and each generated key.

        A column without a key gets the text of its label, stripped and in lower case,
        unless that text is empty, is bytes, is an explicit key, or is the text of another such column.

        :raises TableError: an explicit key is a number or is not hashable, or two columns have the same one.
        """
        key_index: dict[Hashable, int] = {}
        for index, column in enumerate(self._columns):
            if column.key is None:
                continue
            # a number would read as an index: 1.0 == 1 and True == 1
            if isinstance(column.key, numbers.Number):
                raise TableError(f"column {index}: a key must not be a number, not {column.key!r}")
            try:
                other = key_index.setdefault(column.key, index)
            except TypeError as exc:
                raise TableError(f"column {index}: a key must be hashable, not {column.key!r}") from exc
            if other != index:
                raise TableError(f"column {index}: key {column.key!r} is already the key of column {other}")
        names = [
            label.text.strip().lower() if column.key is None and isinstance(label.text, str) else ""
            for column, label in zip(self._columns, labels, strict=True)
        ]
        counts = collections.Counter(names)
        for index, name in enumerate(names):
            if name and counts[name] == 1 and name not in key_index:
                key_index[name] = index
        return key_index

    @property
    def columns(self) -> tuple[TableColumn, ...]:
        """The column specifications."""
        return self._columns

    def column_index(self, column: int | Hashable) -> int:
        """Return the index of the column given by its index or its key.

        A column without a :attr:`TableColumn.key` is also found by the text of its label,
        stripped and in lower case, while no other column has that text or that key.

        >>> layout = TableLayout([TableColumn("Name"), TableColumn("Last change", key="mtime")])
        >>> layout.column_index("name"), layout.column_index("mtime"), layout.column_index(1)
        (0, 1, 1)

        :raises IndexError: *column* names no column: an ``int`` out of range, a ``bool``, or an unknown key.
        """
        if not isinstance(column, bool):
            if isinstance(column, int):
                if 0 <= column < len(self._columns):
                    return column
            else:
                with contextlib.suppress(KeyError, TypeError):
                    return self._key_index[column]
        raise IndexError(f"No Table column at index or key {column!r}")

    @property
    def column_order(self) -> tuple[int, ...]:
        """The indexes of the shown columns, left to right.

        By default it is every column, in the order of :attr:`columns`.
        Set it to an iterable of column indexes and keys, each column at most once.
        A column left out is hidden, and an empty order hides every column.
        A row whose focused cell the order hides passes the focus to the nearest visible shown cell by index,
        a selectable one first.
        Only what is drawn, and what the keys and the mouse reach, follows the order:
        the cells of a row, :meth:`widths` and every column index keep the order of :attr:`columns`.
        A lack of room hides the shown columns only, see :meth:`widths`.

        >>> layout = TableLayout([TableColumn("Name"), TableColumn("Size"), TableColumn("Note")])
        >>> layout.column_order = ("note", 0)
        >>> layout.column_order
        (2, 0)
        >>> [line.decode() for line in layout.row(["a", "1", "x"]).render((9,)).text]
        ['x    a   ']

        :raises IndexError: a value set names no column, see :meth:`column_index`.
        :raises TableError: the value set names a column twice, or is a string rather than an iterable of columns.
            A rejected value leaves the order unchanged.
        :raises TypeError: the value set is not iterable.
        """
        return self._order

    @column_order.setter
    def column_order(self, order: Iterable[int | Hashable]) -> None:
        if isinstance(order, (str, bytes)):
            raise TableError(f"column_order is an iterable of columns, not text: {order!r}")
        indexes = tuple(self.column_index(column) for column in order)
        shown = frozenset(indexes)
        if len(shown) != len(indexes):
            raise TableError(f"a column is named twice in the column order {indexes!r}")
        if indexes == self._order:
            return
        self._order = indexes
        self._shown = shown
        self._display = (*indexes, *(index for index in self._identity if index not in shown))
        self._drop_sequence = self._drop_order()
        self._layout_changed()
        # the focus moves off a hidden column by the order in force, not by the order a row was next drawn at
        for row in self._iter_rows():
            row._w._sync()

    def _drop_order(self) -> tuple[int, ...]:
        """Return the shown columns in the order a lack of room hides them.

        A column of given width 0 is never visible, so it is never in it.
        """
        place = {index: position for position, index in enumerate(self._order)}
        return tuple(
            sorted(
                (index for index in self._order if self._kinds[index] != WHSettings.GIVEN or self._amounts[index]),
                key=lambda index: (self._columns[index].priority, -place[index]),
            )
        )

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
        A width of 0 hides the column, as it does for a column out of :attr:`column_order`.
        The widths are in the order of :attr:`columns`.
        When the natural widths do not fit, the weighted columns are at their minimum first,
        then the PACK columns shrink in proportion to how far they are above their minimum,
        and as the last resort a visible column is hidden: the lowest :attr:`TableColumn.priority` first,
        the rightmost on screen of equal priorities first.
        The remaining columns are then laid out again from their natural widths.
        A hidden column stays hidden at that width even when hiding a later one leaves room for it.
        A given width never shrinks.

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

        It is the sum of the natural widths of the shown columns and their dividers,
        where a weighted column counts at its minimum.
        """
        self._check_collected()
        visible = [
            self._natural[index]
            for index in self._order
            if self._kinds[index] != WHSettings.GIVEN or self._natural[index]
        ]
        return sum(visible) + self._dividechars * max(len(visible) - 1, 0)

    def _column_spans(self, maxcol: int) -> dict[int, tuple[int, int]]:
        """Return ``{index: (start, width)}`` of each visible column at *maxcol*, left to right."""
        spans: dict[int, tuple[int, int]] = {}
        start = 0
        widths = self.widths(maxcol)
        for index in self._order:
            if width := widths[index]:
                spans[index] = (start, width)
                start += width + self._dividechars
        return spans

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
        for column, kind, amount, label, measured, unmeasured in zip(
            self._columns,
            self._kinds,
            self._amounts,
            self._label_widths,
            self._pack_max,
            self._pack_unmeasured,
            strict=True,
        ):
            if kind == WHSettings.GIVEN:
                natural.append(int(amount))
            elif kind == WHSettings.PACK:
                room = column.min_width if isinstance(column.min_width, int) and unmeasured else 1
                natural.append(max(room, label, measured))
            else:
                # The layout accepts min_width PACK on a PACK column only.
                natural.append(typing.cast("int", column.min_width))
        return tuple(natural)

    def _allocate(self, maxcol: int) -> tuple[int, ...]:
        """Compute the widths at *maxcol*, as :meth:`widths` describes."""
        natural = self._natural
        kinds = self._kinds
        # the narrowest each PACK column shrinks to; a weighted column keeps its min_width in _grow()
        minimums = {
            index: min(column.min_width, natural[index]) if isinstance(column.min_width, int) else natural[index]
            for index, column in enumerate(self._columns)
            if kinds[index] == WHSettings.PACK
        }
        visible = [index for index in self._order if kinds[index] != WHSettings.GIVEN or natural[index]]
        drops = iter(self._drop_sequence)
        while visible:
            widths = [0] * len(natural)
            for index in visible:
                widths[index] = natural[index]
            reserved = sum(widths) + self._dividechars * (len(visible) - 1)
            if reserved <= maxcol:
                self._grow([index for index in visible if kinds[index] == WHSettings.WEIGHT], widths, maxcol - reserved)
                return tuple(widths)

            deficit = reserved - maxcol
            packed = {index: minimums[index] for index in visible if kinds[index] == WHSettings.PACK}
            if sum(widths[index] - minimum for index, minimum in packed.items()) >= deficit:
                _shrink_by_slack(widths, packed, deficit)
                return tuple(widths)

            # the last resort: a row wider than maxcol is the only alternative
            visible.remove(next(drops))
        return (0,) * len(natural)

    def _grow(self, weighted: list[int], widths: list[int], extra: int) -> None:
        """Share *extra* screen columns and the minimums of the *weighted* columns by weight, as Columns does."""
        if not weighted:
            return
        # The layout accepts min_width PACK on a PACK column only.
        minimums = {index: typing.cast("int", self._columns[index].min_width) for index in weighted}
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
        unmeasured = dict.fromkeys(columns, 0)
        for row in self._iter_rows():
            widths = row._cell_widths
            for index in columns:
                if (width := widths[index]) is None:
                    unmeasured[index] += not row._span
                elif width > maxima[index]:
                    maxima[index] = width
        for index, width in maxima.items():
            self._pack_max[index] = width
            self._pack_unmeasured[index] = unmeasured[index]

    def _update_natural(self) -> None:
        """Recompute the natural widths from the maxima, and drop what was laid out with them if they changed."""
        natural = self._natural_from_maxima()
        if natural == self._natural:
            return
        self._natural = natural
        self._layout_changed()

    def _layout_changed(self) -> None:
        """Drop the allocated widths and what was laid out with them.

        The table that owns the layout is told as well.
        """
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

    def _add_widths(self, row: TableRow) -> None:
        """Count the stored widths of a row that became registered."""
        for index, width in enumerate(row._cell_widths):
            if self._kinds[index] != WHSettings.PACK:
                continue
            if width is None:
                self._pack_unmeasured[index] += not row._span
            elif width > self._pack_max[index]:
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
        self._add_widths(row)

    def _adopt(self, row: TableRow) -> None:
        """Count *row* as a row of the table that owns the layout."""
        if row._registered:
            self._check_collected()
            if row in self._free_rows:
                self._free_rows.discard(row)
                self._free_count -= 1
            return
        row._registered = True
        self._add_widths(row)

    def _release(self, rows: Iterable[TableRow]) -> None:
        """Stop counting *rows*, removed from the table that owns the layout, recomputing each column once."""
        affected: set[int] = set()
        for row in rows:
            row._registered = False
            if row._span:
                # a span row is neither measured nor counted
                continue
            for index, width in enumerate(row._cell_widths):
                # an unmeasured cell leaves the count of its column, a measured one may have been its maximum
                if width is None or width >= self._pack_max[index]:
                    affected.add(index)
        self._recompute_maxima(sorted(affected))
        self._update_natural()


class TableRow(WidgetWrap[_TableColumns], WidgetContainerMixin[int]):
    """One row of cells laid out by a :class:`TableLayout`.

    A row is selectable unless built with ``selectable=False``, whatever its cells,
    so a row of plain text can take the focus in a :class:`Table`.

    It is a container whose positions are the indexes of its cells.
    They stay the column indexes whatever :attr:`TableLayout.column_order` shows.
    A span row has one position.
    The widget at a position is the cell as the row lays it out: the cell in an :class:`AttrMap` when its column
    has an ``attr``.
    ``row[i]`` gives the cell's :attr:`base_widget`, as for any container.

    The attribute map applied to the row's canvas is, in this order:

    - :attr:`focus_attr`, or the table's ``focus_attr``, when the row renders in focus;
    - the result of the table's ``row_attr`` callable, when it returns something other than ``None``;
    - :attr:`attr`, or the table's ``attr``.

    The ``attr`` of a :class:`TableColumn` maps each cell of that column first,
    except in a span row, in the header of a :class:`Table` and in a footer the table built from cells.
    A row map given as a dict then also maps the cells' and the columns' attributes.
    The attribute a row map gives for ``None`` becomes the base layer under them.
    """

    #: whether the ``attr`` of each :class:`TableColumn` maps the cells of the row
    _column_attrs: typing.ClassVar[bool] = True

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
        super().__init__(_TableColumns(layout, self._cells, span=span, column_attrs=self._column_attrs))
        self._measure()
        for cell in self._cells:
            if isinstance(cell, _TableText):
                cell._rows.add(self)
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

    @property
    def contents(self) -> tuple[tuple[AbstractWidget, None], ...]:
        """The ``(cell, None)`` pairs of the row, read-only, in the order of the columns."""
        self._w._sync()
        contents = self._w.contents
        if self._span:
            return tuple((cell, None) for cell, _options in contents)
        by_column: list[tuple[AbstractWidget, None]] = [(cell, None) for cell, _options in contents]
        for position, index in enumerate(self._w._display):
            by_column[index] = (contents[position][0], None)
        return tuple(by_column)

    @property
    def focus(self) -> AbstractWidget | None:
        """The cell in focus, or ``None`` when the layout has no columns."""
        return self._w.focus

    @property
    def focus_position(self) -> int:
        """The index of the cell in focus.

        :raises IndexError: the layout has no columns.
            The position set is not an index of a cell.
        """
        self._w._sync()
        position = self._w.focus_position
        return position if self._span else self._w._display[position]

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        self._w._sync()
        display = self._w._display
        # any other value goes to Columns unchanged, which rejects it as it would without a column order
        if not self._span and isinstance(position, int) and 0 <= position < len(display):
            position = display.index(position)
        self._w.focus_position = position

    def __iter__(self) -> Iterator[int]:
        """Return the cell positions from first to last."""
        return iter(range(len(self._w.contents)))

    def __reversed__(self) -> Iterator[int]:
        """Return the cell positions from last to first."""
        return reversed(range(len(self._w.contents)))

    def options(self) -> None:
        """Return ``None``, the options half of every :attr:`contents` item."""

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
        new = cell.pack((), False)[0]
        for index, own in enumerate(self._cells):
            if own is not cell:
                continue
            old = self._cell_widths[index]
            if new == old:
                continue
            self._cell_widths = (*self._cell_widths[:index], new, *self._cell_widths[index + 1 :])
            if self._registered:
                self._layout._cell_width_changed(index, old, new)


class _TableEdgeRow(TableRow):
    """Header or footer row built by a table, which only the table's ``header_attr`` or ``footer_attr`` maps."""

    _column_attrs = False


class _TableHeaderRow(_TableEdgeRow):
    """Header row built by a table, whose focused cell a focus map can mark."""

    def __init__(
        self,
        layout: TableLayout,
        *,
        attr: _AttrMapLike | None,
        focus_map: dict[Hashable, Hashable] | None,
    ) -> None:
        """Build the row of the column labels; *focus_map* maps the cell that renders in focus."""
        super().__init__(layout, [column.label for column in layout.columns], attr=attr, selectable=False)
        if focus_map is not None:
            # each cell keeps its own options, which fit the AttrMap around it
            wrapped: list[typing.Any] = [
                (AttrMap(cell, None, focus_map), options) for cell, options in self._w.contents
            ]
            self._w.contents[:] = wrapped


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
        """Reject rows of another layout, the footer, and rows that would be in the table twice.

        :raises TableError: a row is of another layout, is the footer of the table, or would be in the table twice.
        """
        replaced = {id(self[index]) for index in range(*indices)}
        seen: set[int] = set()
        table = self._table()
        for row in new_items:
            if not isinstance(row, TableRow) or row.layout is not self._layout:
                raise TableError(f"{row!r} is not a row of this table's layout")
            if table is not None and row is table._footer:
                raise TableError(f"{row!r} is the footer of the table")
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


class Table(Widget, WidgetContainerMixin[int]):
    """Rows of cells in columns of shared widths, between a fixed header and footer, and with a focused row.

    The rows scroll in a :class:`ListBox`.
    The header stays on top and the footer stays at the bottom.
    Neither takes the focus, except the header of a sortable table.
    It is a container whose positions are the indexes of the rows in :attr:`body`.
    The header and the footer are not in it.
    A focus path goes on through the focused :class:`TableRow` to its focused cell.
    It is a box and flow widget, and a fixed widget as well when no column is weighted.

    A box size that does not fit the whole table drops the header or the footer by *header_drop* and *footer_drop*.
    A part with a threshold is dropped while keeping it leaves the body fewer rows than the threshold.
    The part with the larger threshold is dropped first; on equal thresholds the footer goes first.
    A part that is kept but does not fit is cut at the bottom.
    The header keeps its rows first, so the footer is cut first.

    Sends ``"focus changed"`` after :attr:`focus_position` changed, also through a change of :attr:`body`,
    with the old and the new position, which is ``None`` while the table is empty.
    A row replaced in place at the focus sends nothing.
    Sends ``"activate"`` with the focus position when the focused row leaves the ``activate`` command
    (:kbd:`enter` and :kbd:`space` by default) unhandled.
    A handler whose result is true consumes the key; otherwise the key is returned, as :class:`Overlay` does for
    ``"menu"``. Every handler runs, whatever the earlier ones returned.
    A mouse click moves the focus and reaches the cell only.
    Sends ``"edge reached"`` with ``"top"`` or ``"bottom"`` when its rows send it, see :class:`ListBox`,
    so that a handler can add rows at that end, such as the next batch of a list loaded in parts.
    In a sortable table, :kbd:`up` at the first row sends ``"top"`` before the header takes the focus.

    :meth:`sort` reorders the rows by a column or a key and records :attr:`sort_column` and :attr:`sort_reverse`.

    A table built with ``sortable=True`` also offers its header for sorting:

    - It sends ``"header activated"`` with the column index for a click with button 1 on a header label,
      and for the ``activate`` command on the focused header label.
      The result of the handlers is used as for ``"activate"``.
      The table does not sort by itself: a handler calls :meth:`sort`.
    - :kbd:`up` at the first row focuses the header, see :attr:`header_column`.
      :kbd:`left` and :kbd:`right` move over the visible labels.
      :kbd:`down`, and :kbd:`tab` with *select_navigation*, go back to the rows.
      Every other key is returned, so :kbd:`up` and :kbd:`shift tab` leave the table.
    - The label of the sorted column carries a mark from *sort_marks*.

    A parent that moves its own focus away and back without the entry hook :meth:`enter_selectable`
    finds the header focus as it left it.
    """

    signals: typing.ClassVar[list[str]] = ["focus changed", "activate", "header activated", "edge reached"]

    def __init__(
        self,
        columns: Sequence[TableColumn],
        rows: Iterable[Sequence[_Cell] | TableRow] = (),
        *,
        header: bool = True,
        header_attr: _AttrMapLike | None = None,
        footer: Sequence[_Cell] | None = None,
        footer_attr: _AttrMapLike | None = None,
        header_drop: int | None = None,
        footer_drop: int | None = None,
        dividechars: int = 1,
        attr: _AttrMapLike | None = None,
        focus_attr: _AttrMapLike | None = None,
        unfocused_focus_attr: _AttrMapLike | None = None,
        unfocused_focus_attr_func: Callable[[TableRow], _AttrMapLike | None] | None = None,
        max_rows: int | None = None,
        row_attr: Callable[[int, typing.Any], _AttrMapLike | None] | None = None,
        select_navigation: bool = False,
        wheel: Literal["focus", "view"] = "focus",
        home_end: Literal["any", "selectable"] = "any",
        scrollbar: bool | None = False,
        sortable: bool = False,
        sort_marks: tuple[str, str] | None = (" ^", " v"),
        header_focus_attr: _AttrMapLike | None = None,
        **scrollbar_options: typing.Unpack[_ScrollBarOptions],
    ) -> None:
        """Create the table.

        :param columns: one specification per column; their number is the number of cells of every row
        :param rows: the initial rows, as :class:`TableRow` objects of :attr:`layout` or sequences of cells
        :param header: draw the column labels above the rows
        :param header_attr: attribute map of the header
        :param footer: the cells of a row drawn below the rows, see :attr:`footer`; ``None`` draws no footer
        :param footer_attr: attribute map of a footer built from cells
        :param header_drop: in a box size whose rows do not all fit, drop the header while keeping it
            leaves the body fewer rows than this; ``None`` never drops it
        :param footer_drop: the same threshold for the footer
        :param dividechars: blank screen columns between two visible columns
        :param attr: attribute map of a row without its own :attr:`TableRow.attr`
        :param focus_attr: attribute map of the focused row without its own :attr:`TableRow.focus_attr`
        :param unfocused_focus_attr: attribute map applied to the focused row while the table renders without
            focus, over the row's own map, as :attr:`ListBox.unfocused_focus_attr` does
        :param unfocused_focus_attr_func: function that gives that map for the focused row,
            instead of *unfocused_focus_attr*; see :attr:`unfocused_focus_attr_func`
        :param max_rows: the most rows of body a flow size shows; ``None`` shows every row
        :param row_attr: ``row_attr(index, data)`` called each time a row renders, see :attr:`row_attr`
        :param select_navigation: let the ``'next selectable'`` and ``'prev selectable'`` commands
            (:kbd:`tab` and :kbd:`shift tab`) move across the cells and then to the next or previous row
        :param wheel: what a notch of the mouse wheel moves; see :attr:`wheel`
        :param home_end: what :kbd:`home` and :kbd:`end` move the focus to; see :attr:`home_end`
        :param scrollbar: ``True`` draws a scrollbar beside the rows, ``None`` only when the rows do not fit,
            ``False`` never; while it is on, its column counts in the natural width
        :param sortable: offer the header for sorting, see the class description; needs *header*
        :param sort_marks: the suffixes of the sorted column's label, ascending first, such as
            ``(ScrollBar.Symbols.ARROW_TRIANGLE_UP, ScrollBar.Symbols.ARROW_TRIANGLE_DOWN)``;
            ``None`` draws no mark. Drawn only while *sortable* is set.
        :param header_focus_attr: attribute map of the focused header label, in any form :class:`AttrMap` takes;
            used only while *sortable* is set
        :param scrollbar_options: the :class:`ScrollBar` parameters with a ``scrollbar_`` prefix,
            such as ``scrollbar_thumb_char``, ``scrollbar_end_markers``, ``scrollbar_side`` and ``scrollbar_attr``;
            ignored while *scrollbar* is ``False``
        :raises TableError: a column specification, *dividechars*, *max_rows*, a drop threshold, a row, the footer,
            *sort_marks* or *header_focus_attr* is invalid.
            *sortable* is set without *header*.
        :raises TypeError: a keyword argument is neither a parameter of the table nor one of *scrollbar_options*,
            also while *scrollbar* is ``False``.
        :raises ValueError: :class:`ScrollBar` rejects the value of a ``scrollbar_`` parameter.
            Also when *home_end* is neither ``"any"`` nor ``"selectable"``.
        """
        bar_options = _scrollbar_arguments("Table", scrollbar_options)
        if max_rows is not None and (not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 0):
            raise TableError(f"max_rows must be None or an int >= 0, not {max_rows!r}")
        for name, threshold in (("header_drop", header_drop), ("footer_drop", footer_drop)):
            if threshold is not None and (
                not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1
            ):
                raise TableError(f"{name} must be None or an int >= 1, not {threshold!r}")
        if sortable and not header:
            raise TableError("a sortable table needs a header")
        match sort_marks:
            case None | tuple((str(), str())):
                pass
            case _:
                raise TableError(f"sort_marks must be None or a tuple of two str, not {sort_marks!r}")
        try:
            header_focus_map = None if header_focus_attr is None else _attr_map_dict(header_focus_attr)
        except AttrMapError as exc:
            raise TableError(f"invalid header_focus_attr {header_focus_attr!r}") from exc
        super().__init__()
        self._layout = TableLayout(columns, dividechars=dividechars)
        self._sortable = sortable
        self._header = (
            _TableHeaderRow(self._layout, attr=header_attr, focus_map=header_focus_map if sortable else None)
            if header
            else None
        )
        self._sort_marks = sort_marks
        self._sort_column: int | None = None
        self._sort_reverse = False
        # whether the header has the focus, and the column it was last given; see header_column
        self._header_focused = False
        self._header_column: int | None = None
        self._footer: TableRow | None = None
        self._footer_attr = footer_attr
        self.footer = footer
        self._header_drop = header_drop
        self._footer_drop = footer_drop
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
            # see the unfocused_focus_attr_func setter
            unfocused_focus_attr_func=typing.cast("_UnfocusedFocusAttrFunc | None", unfocused_focus_attr_func),
            focus_when_empty=False,
            wheel=wheel,
            home_end=home_end,
        )
        self._bar = ScrollBar(self._listbox, visible=True, **bar_options) if scrollbar is not False else None
        signals.connect_signal(self._rows, "modified", type(self)._rows_modified, weak_args=[self])
        signals.connect_signal(self._listbox, "edge reached", Table._edge_reached, weak_args=[self])
        # connected last, so that filling the rows during construction sends no signal
        self._rows.set_focus_moved_callback(_WeakCallback(self, type(self)._focus_moved))

    def _focus_moved(self, old: int | None, new: int | None) -> None:
        self._emit("focus changed", old, new)

    def _edge_reached(self, _listbox: ListBox[int], end: Literal["top", "bottom"]) -> None:
        """Send ``"edge reached"`` from the table for *end*, sent by the rows."""
        self._emit("edge reached", end)

    @property
    def layout(self) -> TableLayout:
        """The layout of the columns, which builds and measures the rows."""
        return self._layout

    @property
    def sortable(self) -> bool:
        """Whether the header is offered for sorting, as set when the table was built."""
        return self._sortable

    @property
    def sort_column(self) -> int | None:
        """The index of the column given to the last :meth:`sort`, or ``None``."""
        return self._sort_column

    @property
    def sort_reverse(self) -> bool:
        """The *reverse* given to the last :meth:`sort`."""
        return self._sort_reverse

    @typing.overload
    def sort(self, column: int | Hashable, *, key: None = None, reverse: bool = False) -> None: ...

    @typing.overload
    def sort(
        self,
        column: int | Hashable | None = None,
        *,
        key: Callable[[TableRow], SupportsRichComparison],
        reverse: bool = False,
    ) -> None: ...

    def sort(
        self,
        column: int | Hashable | None = None,
        *,
        key: Callable[[TableRow], SupportsRichComparison] | None = None,
        reverse: bool = False,
    ) -> None:
        """Sort the rows, keeping the focus on the same row.

        Without *key*, the rows are ordered by the text of their cell in *column*, compared as strings,
        so a numeric column needs a *key*.
        With *key* and *column*, *column* only says which label carries the mark of a sortable table.
        The new order is computed before anything changes, so an exception from it leaves the table as it was.
        A ``"modified"`` or ``"focus changed"`` handler already sees the new :attr:`sort_column` and mark.
        The rows are not sorted again when they change later: call :meth:`sort` again.

        A handler toggles the direction with
        ``table.sort(column, reverse=table.sort_column == column and not table.sort_reverse)``.

        >>> table = Table([TableColumn("Name")], [["b"], ["a"]], sortable=True)
        >>> table.sort(0)
        >>> [row.cells[0].text for row in table.body]
        ['a', 'b']

        :param column: the column to sort by, as its index or its key (see :meth:`TableLayout.column_index`),
            or ``None`` with *key*; a column hidden by :attr:`TableLayout.column_order` sorts as well
        :param key: ``key(row)`` with the :class:`TableRow`, as :meth:`list.sort` takes it
        :param reverse: sort in descending order
        :raises TableError: neither *column* nor *key* is given.
            Without *key*, a row is a span row or its cell in *column* is not a :class:`Text`.
        :raises IndexError: *column* names no column.
        """
        if column is not None:
            column = self._layout.column_index(column)
        if key is None:
            if column is None:
                raise TableError("sort() needs a column or a key")
            key = self._text_key(column)
        ordered = sorted(self._rows, key=key, reverse=reverse)
        previous = self._sort_column
        self._sort_column = column
        self._sort_reverse = reverse
        if self._sortable and self._header is not None and self._sort_marks is not None:
            labels = self._layout.columns
            if previous is not None and previous != column:
                typing.cast("_TableText", self._header.cells[previous]).set_text(labels[previous].label)
            if column is not None:
                mark = self._sort_marks[1] if reverse else self._sort_marks[0]
                typing.cast("_TableText", self._header.cells[column]).set_text([labels[column].label, mark])
        rank = {id(row): position for position, row in enumerate(ordered)}
        self._rows.sort(key=lambda row: rank[id(row)])

    @staticmethod
    def _text_key(column: int) -> Callable[[TableRow], str | bytes]:
        """Return a sort key giving the text of the cell in *column*.

        The key raises :exc:`TableError` for a span row and for a cell that is not a :class:`Text`.
        """

        def key(row: TableRow) -> str | bytes:
            cell = None if row.span else row.cells[column].base_widget
            if not isinstance(cell, Text):
                raise TableError(f"row {row.index}: column {column} has no text to sort by; pass a key to sort()")
            return cell.text

        return key

    @property
    def header_column(self) -> int | None:
        """The header column that has the focus, or ``None`` while the rows have it.

        Set a column index or key to focus the header there, or ``None`` to give the focus back to the rows.
        A size or a :attr:`TableLayout.column_order` that hides the column shows the focus
        on the nearest visible column on its left on screen, or on its right when none is on the left.
        A column out of the order counts as right of the last one.
        A size that drops the header, or hides every column, leaves the focus with the rows while it lasts.

        :raises TableError: the table is not sortable, or it has no rows.
        :raises IndexError: the value set names no column (see :meth:`TableLayout.column_index`),
            the column is not in :attr:`TableLayout.column_order`, or it has a given width of 0.
        """
        return self._header_column if self._header_focused else None

    @header_column.setter
    def header_column(self, column: int | Hashable | None) -> None:
        if not self._sortable:
            raise TableError("only a sortable table focuses its header")
        if column is None:
            self._header_focused = False
            self._invalidate()
            return
        if not self._rows:
            raise TableError("an empty table cannot focus its header")
        index = self._layout.column_index(column)
        if index not in self._layout._shown or self._layout.columns[index].width == 0:
            raise IndexError(f"No visible Table column at index or key {column!r}")
        self._header_column = index
        self._header_focused = True
        self._invalidate()

    def forget_header_column(self) -> None:
        """Forget the header label that :kbd:`up` returns to.

        The focus goes back to the rows, and :kbd:`up` at the first row focuses the first visible label again,
        as in a new table.
        Setting :attr:`header_column` to ``None`` only gives the focus back and keeps the label.
        """
        self._header_column = None
        self._header_focused = False
        self._invalidate()

    def _header_target(self, arrangement: _Arrangement) -> int | None:
        """Return the header column the focus is shown on at *arrangement*, or ``None`` when it cannot be shown.

        It is the stored column when it is visible, otherwise the nearest visible column on its left on screen,
        or on its right when none is on the left; the first visible column when none is stored.
        """
        if not self._rows or not arrangement.header_rows:
            return None
        visible = list(self._layout._column_spans(arrangement.content))
        if not visible:
            return None
        stored = self._header_column
        if stored is None:
            return visible[0]
        if stored in visible:
            return stored
        place = self._layout._display.index
        left = [index for index in visible if place(index) < place(stored)]
        return left[-1] if left else visible[0]

    @property
    def body(self) -> _TableRows:
        """The rows of the table, below the header.

        A sequence of cells added to it becomes a :class:`TableRow` of :attr:`layout`, so ``body[i]`` is that row.
        A change is validated before it is applied, and a :exc:`TableError` leaves the rows unchanged.
        Replace every row with ``table.body[:] = rows``.
        """
        return self._rows

    @property
    def footer(self) -> TableRow | None:
        """The row below the rows, such as totals or a summary, or ``None``.

        It shares the column widths, and its cells count in the PACK widths.
        Set it to a sequence of cells, which becomes a row mapped by ``footer_attr`` alone,
        to a :class:`TableRow` of :attr:`layout`, which keeps its own maps and may be a span row, or to ``None``.
        A text cell of the footer re-measures its column when its text changes, as in any row.

        :raises TableError: a row is of another layout or is in :attr:`body`, or the cells do not fit the columns.
        """
        return self._footer

    @footer.setter
    def footer(self, footer: Sequence[_Cell] | TableRow | None) -> None:
        if isinstance(footer, TableRow):
            if footer.layout is not self._layout:
                raise TableError(f"{footer!r} is not a row of this table's layout")
            if footer._rows is not None:
                raise TableError(f"{footer!r} is in the body of a table")
            if not footer._registered:
                # a row removed from the body is released, and its cells count in the widths again only once registered
                self._layout._register(footer)
            self._footer = footer
        elif footer is None:
            self._footer = None
        else:
            self._footer = _TableEdgeRow(self._layout, footer, attr=self._footer_attr, selectable=False)
        self._invalidate()

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
    def unfocused_focus_attr_func(self) -> Callable[[TableRow], _AttrMapLike | None] | None:
        """Function that gives :attr:`unfocused_focus_attr` for the focused row.

        It is called with the :class:`TableRow`, and its map is applied over the row's own map.
        See :attr:`ListBox.unfocused_focus_attr_func`.
        """
        return typing.cast("Callable[[TableRow], _AttrMapLike | None] | None", self._listbox.unfocused_focus_attr_func)

    @unfocused_focus_attr_func.setter
    def unfocused_focus_attr_func(self, func: Callable[[TableRow], _AttrMapLike | None] | None) -> None:
        # the list box holds TableRows only, so a function of a TableRow is called with one
        self._listbox.unfocused_focus_attr_func = typing.cast("_UnfocusedFocusAttrFunc | None", func)

    @property
    def wheel(self) -> Literal["focus", "view"]:
        """What a notch of the mouse wheel over the rows moves, see :attr:`ListBox.wheel`."""
        return self._listbox.wheel

    @wheel.setter
    def wheel(self, wheel: Literal["focus", "view"]) -> None:
        """Set what a notch of the mouse wheel moves.

        :raises ValueError: *wheel* is neither ``"focus"`` nor ``"view"``.
        """
        self._listbox.wheel = wheel

    @property
    def home_end(self) -> Literal["any", "selectable"]:
        """What :kbd:`home` and :kbd:`end` move the focus to among the rows, see :attr:`ListBox.home_end`."""
        return self._listbox.home_end

    @home_end.setter
    def home_end(self, home_end: Literal["any", "selectable"]) -> None:
        """Set what :kbd:`home` and :kbd:`end` move the focus to.

        :raises ValueError: *home_end* is neither ``"any"`` nor ``"selectable"``.
        """
        self._listbox.home_end = home_end

    @property
    def contents(self) -> ListBoxContentsProto[int]:
        """The ``(row, None)`` pairs of :attr:`body`, read-only, as :attr:`ListBox.contents` gives them."""
        return self._listbox.contents

    def __iter__(self) -> Iterator[int]:
        """Return the row positions from first to last."""
        return iter(self._listbox)

    def __reversed__(self) -> Iterator[int]:
        """Return the row positions from last to first."""
        return reversed(self._listbox)

    def options(self) -> None:
        """Return ``None``, the options half of every :attr:`contents` item."""

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
        self.set_focus(position)

    def set_focus(self, position: int, coming_from: Literal["above", "below"] | None = None) -> None:
        """Focus the row at *position*, as :meth:`ListBox.set_focus` does.

        A row on screen from the old focus is brought just into view.
        Without *coming_from*:

        - a row on screen keeps its cursor and nested focus;
        - a row off screen is centred and keeps its nested focus.

        With *coming_from*:

        - a row on screen takes the cursor from that edge, at the preferred column;
        - a row off screen is placed at that edge and keeps its nested focus.

        The focus leaves the header of a sortable table.

        :param position: the index of the row
        :param coming_from: ``"above"`` or ``"below"`` when the old focus is on that side of the new one
        :raises IndexError: *position* is not an index of a row.
        :raises ListBoxError: *coming_from* is not ``"above"``, ``"below"`` or ``None``.
        """
        if not isinstance(position, int) or not 0 <= position < len(self._rows):
            raise IndexError(f"No Table row at position {position!r}")
        self._end_header_focus()
        self._listbox.set_focus(position, coming_from)

    def selectable(self) -> bool:
        """Return whether the table has a row to focus."""
        return self._listbox.selectable()

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Start at the first selectable cell of the first selectable row, or at the last one when *reverse* is set.

        It is the entry hook a parent container calls.
        It moves the focus within the rows only when the table was built with ``select_navigation``,
        see :ref:`select-navigation`.
        It always takes the focus off the header of a sortable table.

        :param reverse: start at the last selectable cell of the last selectable row instead.
        """
        self._end_header_focus()
        self._listbox.enter_selectable(reverse=reverse)

    def _end_header_focus(self) -> None:
        """Give the focus back to the rows when the header has it."""
        if self._header_focused:
            self._header_focused = False
            self._invalidate()

    def sizing(self) -> frozenset[Sizing]:
        """Return BOX and FLOW, and FIXED as well when no column is weighted.

        A weighted column counts also while :attr:`TableLayout.column_order` hides it.
        """
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
        if not self._rows:
            self._header_focused = False
        self._invalidate()

    def _widths_changed(self) -> None:
        """Drop what was laid out with the old column widths."""
        self._listbox._invalidate()
        for edge in (self._header, self._footer):
            if edge is not None:
                edge._invalidate()
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

    def _edge_rows(self, content: int, maxrow: int | None) -> tuple[int, int]:
        """Return the rows shown of the header and of the footer at *content* columns.

        A flow size, with *maxrow* ``None``, shows both whole.
        A box size drops them by their thresholds, then cuts what is left to *maxrow*.
        The header keeps its rows first, so the footer is cut first.
        """
        hrows = 0 if self._header is None else self._header.rows((content,))
        frows = 0 if self._footer is None else self._footer.rows((content,))
        if maxrow is None:
            return hrows, frows
        thresholds = [
            (threshold, part)
            for part, threshold in (("footer", self._footer_drop), ("header", self._header_drop))
            if threshold is not None
        ]
        # a stable sort keeps the footer ahead of the header on equal thresholds
        thresholds.sort(key=operator.itemgetter(0), reverse=True)
        for threshold, part in thresholds:
            body = maxrow - hrows - frows
            # every later threshold is smaller, so the body satisfies those as well
            if body >= threshold or self._body_rows(content, max(body, 0)) <= body:
                break
            if part == "header":
                hrows = 0
            else:
                frows = 0
        hrows = min(hrows, maxrow)
        return hrows, min(frows, maxrow - hrows)

    def _arrange(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> _Arrangement:
        """Divide *size* between the header, the rows, the footer and the scrollbar."""
        maxcol = size[0] if size else self._natural_width()
        bar_width = 0 if self._bar is None else self._bar.scrollbar_width
        maxrow = size[1] if len(size) == 2 else None

        if maxrow is not None:
            limit: int | None = maxrow - sum(self._edge_rows(maxcol, maxrow))
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
        hrows, frows = self._edge_rows(content, maxrow)
        if maxrow is not None:
            body_rows: int | None = maxrow - hrows - frows
        elif self._max_rows is not None:
            body_rows = min(self._body_rows(content, self._max_rows), self._max_rows)
        else:
            body_rows = None
        return _Arrangement(maxcol, content, hrows, frows, body_rows, bar)

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
        """Return the header, body and footer rows, at most :attr:`max_rows` of body.

        Without :attr:`max_rows` every row is measured.
        """
        arrangement = self._arrange(size)
        if (body_rows := arrangement.body_rows) is None:
            body_rows = self._body_rows(arrangement.content, sys.maxsize)
        return arrangement.header_rows + body_rows + arrangement.footer_rows

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
        """Render the header, the rows and the footer, top to bottom.

        While the header has the focus, it is rendered with *focus* and the rows without it.
        """
        arrangement = self._arrange(size)
        maxcol, content, hrows, frows, body_rows, bar = arrangement
        header_column = self._header_target(arrangement) if self._header_focused else None

        def edge(row: TableRow, rows: int, row_focus: bool = False) -> CompositeCanvas:
            """Render *row* over the scrollbar column, cut to *rows* rows."""
            canvas = CompositeCanvas(row.render((content,), row_focus))
            if bar and self._bar is not None:
                if self._bar.scrollbar_side == SCROLLBAR_LEFT:
                    canvas.pad_trim_left_right(maxcol - content, 0)
                else:
                    canvas.pad_trim_left_right(0, maxcol - content)
            if canvas.rows() > rows:
                canvas.trim_end(canvas.rows() - rows)
            return canvas

        combine: list[tuple[Canvas, Hashable, bool]] = []
        if self._header is not None and hrows:
            if header_column is None:
                combine.append((edge(self._header, hrows), "header", False))
            else:
                if self._header.focus_position != header_column:
                    self._header.focus_position = header_column
                header = edge(self._header, hrows, focus)
                if focus:
                    header.cursor = self._header_cursor(arrangement, header_column)
                combine.append((header, "header", True))
        if self._rows and body_rows != 0:
            widget, body_size = self._body_widget_size(maxcol, body_rows, bar)
            body_focus = focus and header_column is None
            combine.append((widget.render(body_size, body_focus), "body", header_column is None))
        elif body_rows:
            combine.append((SolidCanvas(" ", maxcol, body_rows), "body", False))
        if self._footer is not None and frows:
            combine.append((edge(self._footer, frows), "footer", False))
        if not combine:
            return SolidCanvas(" ", maxcol, 0)
        return CanvasCombine(combine)

    def _header_cursor(self, arrangement: _Arrangement, column: int) -> tuple[int, int]:
        """Return the cursor on the first screen column of the label of the visible *column*."""
        start = self._layout._column_spans(arrangement.content)[column][0]
        if arrangement.bar and self._bar is not None and self._bar.scrollbar_side == SCROLLBAR_LEFT:
            start += arrangement.maxcol - arrangement.content
        return start, 0

    def _body_call_size(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
    ) -> tuple[ListBox[int] | ScrollBar[ListBox[int]], tuple[int] | tuple[int, int], _Arrangement] | None:
        """Return the body widget, its size and the arrangement of *size*, or ``None`` when no row is shown."""
        if not self._rows:
            return None
        arrangement = self._arrange(size)
        if arrangement.body_rows == 0:
            return None
        widget, body_size = self._body_widget_size(arrangement.maxcol, arrangement.body_rows, arrangement.bar)
        return widget, body_size, arrangement

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass the key to the rows; send ``"activate"`` for an ``activate`` command they leave unhandled.

        While the header of a sortable table has the focus, the key goes to the header instead,
        as the class description says.

        :returns: ``None`` if the rows, the header or a handler handled the key, otherwise the key.
            A handler handles the key by returning a true value.
        """
        if self._header_focused:
            arrangement = self._arrange(size)
            if (column := self._header_target(arrangement)) is not None:
                return self._header_keypress(arrangement, column, key)
            self._end_header_focus()
        if (body := self._body_call_size(size)) is None:
            return key
        widget, body_size, arrangement = body
        if (unhandled := widget.keypress(body_size, key)) is None:
            return None
        command = self._command_map[unhandled]
        if command == Command.ACTIVATE:
            if self._rows.focus is not None and signals.emit_signal(self, "activate", self, self._rows.focus):
                return None
        elif command == Command.UP and self._sortable and (column := self._header_target(arrangement)) is not None:
            if self._header_column is None:
                self._header_column = column
            self._header_focused = True
            self._invalidate()
            return None
        return unhandled

    def _header_keypress(self, arrangement: _Arrangement, column: int, key: str) -> str | None:
        """Handle *key* while the header has the focus, shown on the visible *column*."""
        command = self._command_map[key]
        if command in {Command.LEFT, Command.RIGHT}:
            visible = list(self._layout._column_spans(arrangement.content))
            position = visible.index(column) + (1 if command == Command.RIGHT else -1)
            if not 0 <= position < len(visible):
                return key
            self._header_column = visible[position]
            self._invalidate()
            return None
        if command == Command.ACTIVATE:
            self._header_column = column
            return None if signals.emit_signal(self, "header activated", self, column) else key
        if command == Command.DOWN or (self._select_navigation and command == Command.SELECT_NEXT):
            self._end_header_focus()
            return None
        return key

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the event to the rows; the footer takes no mouse events.

        The header takes none either, except a press of button 1 on a label of a sortable table,
        which focuses that label when the table has rows and sends ``"header activated"``.
        A press of button 1 on the rows gives the focus back to them.

        :returns: whether the rows or a ``"header activated"`` handler handled the event.
        """
        if self._sortable:
            arrangement = self._arrange(size)
            if row < arrangement.header_rows:
                return self._header_click(arrangement, event, button, col)
            if self._header_focused and self._header_target(arrangement) is None:
                self._end_header_focus()
        if (body := self._body_call_size(size)) is None:
            return False
        widget, body_size, arrangement = body
        row -= arrangement.header_rows
        if row < 0:
            return False
        if arrangement.footer_rows:
            if (body_rows := arrangement.body_rows) is None:
                body_rows = self._body_rows(arrangement.content, sys.maxsize)
            if row >= body_rows:
                return False
        if event == "mouse press" and button == 1:
            self._end_header_focus()
        return widget.mouse_event(body_size, event, button, col, row, focus)

    def _header_click(self, arrangement: _Arrangement, event: str, button: int, col: int) -> bool:
        """Handle a mouse event on the header of a sortable table, *col* screen columns from its left edge."""
        if event != "mouse press" or button != 1:
            return False
        if arrangement.bar and self._bar is not None and self._bar.scrollbar_side == SCROLLBAR_LEFT:
            col -= arrangement.maxcol - arrangement.content
        column = next(
            (
                index
                for index, (start, width) in self._layout._column_spans(arrangement.content).items()
                if start <= col < start + width
            ),
            None,
        )
        if column is None:
            return False
        if self._rows:
            self._header_column = column
            self._header_focused = True
            self._invalidate()
        return signals.emit_signal(self, "header activated", self, column)

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the cursor coordinates of the focused row, below the header, or of the focused header label."""
        if self._header_focused:
            arrangement = self._arrange(size)
            if (column := self._header_target(arrangement)) is not None:
                return self._header_cursor(arrangement, column)
        if (body := self._body_call_size(size)) is None:
            return None
        widget, body_size, arrangement = body
        if (coords := widget.get_cursor_coords(body_size)) is None:
            return None
        return coords[0], coords[1] + arrangement.header_rows
