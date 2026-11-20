# Urwid canvas class and functions
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


"""Composite canvas, built from shards of other canvases, and the functions that combine canvases."""

from __future__ import annotations

import contextlib
import itertools
import typing
from collections.abc import Mapping

from urwid.canvas._base import Canvas, CanvasError, blank_canvas
from urwid.util import (
    LayeredAttr,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator, Sequence

    from urwid.canvas._base import _ContentLine, _CView
    from urwid.widget import AbstractWidget


class _AttrMapChain(Mapping["Hashable", "Hashable"]):
    """Attribute maps applied one after another, innermost first, as nested :class:`AttrMap` widgets apply them.

    Each map replaces the attributes it names, and places every attribute over its own ``None`` entry
    (see :meth:`LayeredAttr.layer`), so a color left 'inherit' inside a map shows the color of the map.
    A :class:`LayeredAttr` the map names as a whole is replaced; otherwise each of its layers is mapped.
    An attribute, or a layer of a :class:`LayeredAttr`, that a map sends to ``None`` is dropped and shows
    the map's ``None`` entry instead.

    A lookup never raises: an attribute no map names is passed through, placed over the ``None`` entries,
    so ``key in chain`` is true for every key. Iteration, ``len()`` and ``keys()`` list only the attributes
    the maps name.
    """

    __slots__ = ("_mapped", "_maps")

    def __init__(self, maps: tuple[Mapping[Hashable, Hashable], ...]) -> None:
        """Chain *maps*, innermost first."""
        self._maps = maps
        self._mapped: dict[Hashable, Hashable] = {}

    def append(self, mapping: Mapping[Hashable, Hashable]) -> _AttrMapChain:
        """Return a new chain with *mapping* applied after the maps of this one."""
        return _AttrMapChain((*self._maps, mapping))

    def __getitem__(self, attr: Hashable) -> Hashable:
        """Return *attr* passed through every map of the chain."""
        try:
            return self._mapped[attr]
        except KeyError:
            result = attr
        for mapping in self._maps:
            outer = mapping.get(None)
            if result is None:
                result = outer
                continue
            if isinstance(result, LayeredAttr) and result not in mapping:
                folded: Hashable = None
                for layer in reversed(result.layers):
                    if (mapped := mapping.get(layer, layer)) is not None:
                        folded = mapped if folded is None else LayeredAttr.layer(mapped, folded)
                if folded is None:
                    result = outer
                    continue
                result = folded
            elif (result := mapping.get(result, result)) is None:
                result = outer
                continue
            result = LayeredAttr.layer(result, outer)
        self._mapped[attr] = result
        return result

    def __iter__(self) -> Iterator[Hashable]:
        """Iterate over the attributes named by any map of the chain."""
        return iter({key: None for mapping in self._maps for key in mapping})

    def __len__(self) -> int:
        """Return the number of attributes named by any map of the chain."""
        return len(set(itertools.chain.from_iterable(self._maps)))

    def __bool__(self) -> bool:
        """Return whether any map of the chain names an attribute."""
        return any(self._maps)


class CompositeCanvas(Canvas):
    """class for storing a combination of canvases."""

    __slots__ = (
        "children",
        "depends_on",
        "shards",
    )

    def __init__(self, canv: Canvas | None = None) -> None:
        """
        :param canv: a Canvas object to wrap this CompositeCanvas around.

        if canv is a CompositeCanvas, make a copy of its contents
        """
        # a "shard" is a (num_rows, list of cviews) tuple,
        # one for each cview starting in this shard

        # a "cview" is a tuple that defines a view of a canvas:
        # (trim_left, trim_top, cols, rows, attr_map, canv)

        # a "shard tail" is a list of tuples:
        # (col_gap, done_rows, content_iter, cview)

        # tuples that define the unfinished cviews that are part of shards following the first shard.
        super().__init__()
        self.depends_on: Sequence[AbstractWidget] | None = None

        if canv is None:
            self.shards: list[tuple[int, list[_CView]]] = []
            self.children: list[tuple[int, int, Canvas, typing.Any]] = []
        else:
            shards = getattr(canv, "shards", None)
            if shards is not None:
                self.shards = shards
            else:
                rows = canv.rows()
                self.shards = [(rows, [(0, 0, canv.cols(), rows, None, canv)])]
            self.children = [(0, 0, canv, None)]
            self.coords.update(canv.coords)
            for shortcut in canv.shortcuts:
                self.shortcuts[shortcut] = "wrap"

    def __repr__(self) -> str:
        """Return a debug representation including the canvas size, cursor, finalized state, and children."""
        extra = [""]
        with contextlib.suppress(BaseException):
            extra.append(f"cols={self.cols()}")

        with contextlib.suppress(BaseException):
            extra.append(f"rows={self.rows()}")

        if self.cursor:
            extra.append(f"cursor={self.cursor}")
        if self.children:
            extra.append(f"children=({', '.join(repr(canv) for _, _, canv, _ in self.children)})")

        return f"<{self.__class__.__name__} finalized={bool(self.widget_info)}{' '.join(extra)} at 0x{id(self):X}>"

    def rows(self) -> int:
        """
        Return the screen row height of this canvas.

        :raises TypeError: a shard carries a non-integer row count.
        """
        rows = 0
        for r, cv in self.shards:
            if not isinstance(r, int):
                raise TypeError(r, cv)
            rows += r

        return rows

    def cols(self) -> int:
        """
        Return the screen column width of this canvas.

        :raises TypeError: the shards add up to a non-integer column count.
        """
        if not self.shards:
            return 0
        cols = 0
        for cv in self.shards[0][1]:
            cols += cv[2]
        if not isinstance(cols, int):
            raise TypeError(cols)
        return cols

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """
        Return the canvas content as a list of rows where each row is a list of (attr, cs, text) tuples.

        All parameters are ignored.
        """
        shard_tail: list[tuple[int, int, Iterator[_ContentLine] | None, _CView]] = []
        for num_rows, cviews in self.shards:
            # combine shard and shard tail
            sbody = shard_body(cviews, shard_tail, num_rows=num_rows)

            # output rows
            for _ in range(num_rows):
                yield shard_body_row(sbody)

            # prepare next shard tail
            shard_tail = shard_body_tail(num_rows, sbody)

    def trim(self, top: int, count: int | None = None) -> None:
        """Trim lines from the top and/or bottom of canvas.

        :param top: number of lines to remove from top
        :param count: number of lines to keep, or None for all the rest
        :raises ValueError: *top* is negative, or is at least the number of rows in this canvas.
        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if top < 0:
            raise ValueError(f"invalid trim amount {top:d}!")
        if top >= self.rows():
            raise ValueError(f"cannot trim {top:d} lines from {self.rows():d}!")
        if self.widget_info:
            raise CanvasError(self._finalized_message)

        if top:
            self.shards = shards_trim_top(self.shards, top)

        if count == 0:
            self.shards = self._shards_without_rows()
        elif count is not None:
            self.shards = shards_trim_rows(self.shards, count)

        self.coords = self.translate_coords(0, -top)
        self._drop_cursor_outside_rows()

    def trim_end(self, end: int) -> None:
        """Trim lines from the bottom of the canvas.

        :param end: number of lines to remove from the end
        :raises ValueError: *end* is not positive, or is greater than the number of rows in this canvas.
        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if end <= 0:
            raise ValueError(f"invalid trim amount {end:d}!")
        if end > self.rows():
            raise ValueError(f"cannot trim {end:d} lines from {self.rows():d}!")
        if self.widget_info:
            raise CanvasError(self._finalized_message)

        if end == self.rows():
            self.shards = self._shards_without_rows()
        else:
            self.shards = shards_trim_rows(self.shards, self.rows() - end)
        self._drop_cursor_outside_rows()

    def _drop_cursor_outside_rows(self) -> None:
        if (cursor := self.get_cursor()) is not None and not 0 <= cursor[1] < self.rows():
            self.cursor = None

    def _shards_without_rows(self) -> list[tuple[int, list[_CView]]]:
        # An empty shard list has no width, so a canvas trimmed to no rows keeps one blank shard of no rows.
        return [(0, [(0, 0, self.cols(), 0, None, blank_canvas)])]

    def pad_trim_left_right(self, left: int, right: int) -> None:
        """
        Pad or trim this canvas on the left and right.

        values > 0 indicate screen columns to pad
        values < 0 indicate screen columns to trim

        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)
        shards = self.shards
        if left < 0 or right < 0:
            trim_left = max(0, -left)
            cols = self.cols() - trim_left - max(0, -right)
            shards = shards_trim_sides(shards, trim_left, cols)

        rows = self.rows()
        if left > 0 or right > 0:

            def padded(cviews: list[_CView], pad_rows: int) -> list[_CView]:
                new_cviews: list[_CView] = [(0, 0, left, pad_rows, None, blank_canvas)] if left > 0 else []
                new_cviews.extend(cviews)
                if right > 0:
                    new_cviews.append((0, 0, right, pad_rows, None, blank_canvas))
                return new_cviews

            top_rows, top_cviews = shards[0]
            new_shards = [(top_rows, padded(top_cviews, rows))]
            done_rows = top_rows
            for num_rows, cviews in shards[1:]:
                # The padding started in the first shard ends with the last row,
                # so a shard of no rows after that row needs padding of its own.
                new_shards.append((num_rows, padded(cviews, 0) if done_rows == rows else cviews))
                done_rows += num_rows
            shards = new_shards

        self.coords = self.translate_coords(left, 0)
        self.shards = shards

    def pad_trim_top_bottom(self, top: int, bottom: int) -> None:
        """
        Pad or trim this canvas on the top and bottom.

        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)
        orig_shards = self.shards

        if top < 0 or bottom < 0:
            trim_top = max(0, -top)
            rows = self.rows() - trim_top - max(0, -bottom)
            self.trim(trim_top, rows)

        cols = self.cols()
        if top > 0:
            self.shards = [(top, [(0, 0, cols, top, None, blank_canvas)]), *self.shards]
            self.coords = self.translate_coords(0, top)

        if bottom > 0:
            if orig_shards is self.shards:
                self.shards = self.shards.copy()
            self.shards.append((bottom, [(0, 0, cols, bottom, None, blank_canvas)]))

    def overlay(self, other: CompositeCanvas, left: int, top: int) -> None:
        """Overlay other onto this canvas.

        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        :raises ValueError: *other* does not fit within this canvas at the given *left* and *top* offsets.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)

        width = other.cols()
        height = other.rows()
        right = self.cols() - left - width
        bottom = self.rows() - top - height

        if right < 0:
            raise ValueError(f"top canvas of overlay not the size expected!{(other.cols(), left, right, width)!r}")
        if bottom < 0:
            raise ValueError(f"top canvas of overlay not the size expected!{(other.rows(), top, bottom, height)!r}")

        self.coords.update(other.translate_coords(left, top))
        if not height:
            return  # a canvas of no rows covers nothing, and the row trims below need at least one row

        shards = self.shards
        top_shards: list[tuple[int, list[_CView]]] = []
        side_shards = self.shards
        bottom_shards: list[tuple[int, list[_CView]]] = []
        if top:
            side_shards = shards_trim_top(shards, top)
            top_shards = shards_trim_rows(shards, top)
        if bottom:
            bottom_shards = shards_trim_top(side_shards, height)
            side_shards = shards_trim_rows(side_shards, height)

        if left > 0 and right > 0:
            left_shards, right_shards = _shards_cut_columns(side_shards, ((0, left), (left + width, right)))
            middle_shards = shards_join((left_shards, other.shards, right_shards))
        elif left > 0:
            middle_shards = shards_join((shards_trim_sides(side_shards, 0, left), other.shards))
        elif right > 0:
            middle_shards = shards_join((other.shards, shards_trim_sides(side_shards, max(0, left + width), right)))
        else:
            middle_shards = other.shards

        self.shards = top_shards + middle_shards + bottom_shards

    def fill_attr(self, a: Hashable) -> None:
        """Apply attribute a to all areas of this canvas with default attribute currently set to None.

        Other attributes are left intact.
        """
        self.fill_attr_apply({None: a})

    def fill_attr_apply(self, mapping: Mapping[Hashable, Hashable]) -> None:
        """
        Apply an attribute-mapping dictionary to the canvas.

        Attributes not in *mapping* are kept, placed over ``mapping[None]`` when it is set,
        so their 'inherit' colors show it (see :class:`LayeredAttr`).
        An attribute *mapping* sends to ``None`` shows ``mapping[None]``.

        :param mapping: dictionary of original-attribute:new-attribute items
        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)

        shards: list[tuple[int, list[_CView]]] = []
        for num_rows, original_cviews in self.shards:
            new_cviews: list[_CView] = []
            for cv in original_cviews:
                # cv[4] == attr_map
                if cv[4] is None:
                    chain = _AttrMapChain((mapping,))
                elif isinstance(cv[4], _AttrMapChain):
                    chain = cv[4].append(mapping)
                else:
                    chain = _AttrMapChain((cv[4], mapping))
                new_cviews.append((*cv[:4], chain, *cv[5:]))
            shards.append((num_rows, new_cviews))
        self.shards = shards

    def set_depends(self, widget_list: Sequence[AbstractWidget]) -> None:
        """Explicitly specify the list of widgets that this canvas depends on.

        If any of these widgets change this canvas will have to be updated.

        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)

        self.depends_on = widget_list


def shard_body_row(sbody: Iterable[tuple[int, Iterator[_ContentLine] | None, _CView]]) -> _ContentLine:
    """
    Return one row, advancing the iterators in sbody.

    ** MODIFIES sbody by calling next() on its iterators **

    :raises ValueError: a shard body entry has no content iterator.
    """
    row = []
    for _done_rows, content_iter, _cview in sbody:
        if content_iter:
            row.extend(next(content_iter))
        else:
            msg = f"Invalid canvas state: content_iter is falsy: {content_iter!r}. Impossible to display."
            raise ValueError(msg)

    return row


def shard_body_tail(
    num_rows: int,
    sbody: Iterable[tuple[int, Iterator[_ContentLine] | None, _CView]],
) -> list[tuple[int, int, Iterator[_ContentLine] | None, _CView]]:
    """Return a new shard tail that follows this shard body."""
    shard_tail = []
    col_gap = 0

    for done_rows, content_iter, cview in sbody:
        cols, rows = cview[2:4]
        done_rows += num_rows  # noqa: PLW2901
        if done_rows == rows:
            col_gap += cols
            continue
        shard_tail.append((col_gap, done_rows, content_iter, cview))
        col_gap = 0
    return shard_tail


def shard_body(
    cviews: Iterable[_CView],
    shard_tail: Iterable[tuple[int, int, Iterator[_ContentLine] | None, _CView]],
    create_iter: bool = True,
    iter_default: Iterator[_ContentLine] | None = None,
    num_rows: int | None = None,
) -> list[tuple[int, Iterator[_ContentLine] | None, _CView]]:
    """
    Return a list of (done_rows, content_iter, cview) tuples for this shard and shard tail.

    If a canvas in cviews is None
    or if create_iter is False
    then no iterator is created for content_iter.

    iter_default is the value used for content_iter when no iterator is created.

    num_rows is the row count of the shard being processed. It is used to bound a blank
    filler cview if cviews run out before a shard_tail gap is filled (see below); pass it
    whenever the caller knows how many rows this shard spans.

    :raises CanvasError: the cviews overflow the gaps left by *shard_tail*.
    """
    col = 0
    body: list[tuple[int, Iterator[_ContentLine] | None, _CView]] = []  # build the next shard tail
    cviews_iter = iter(cviews)
    new_iter: Iterator[_ContentLine] | None
    for col_gap, done_rows, content_iter, tail_cview in shard_tail:
        while col_gap:
            try:
                cview = next(cviews_iter)
            except StopIteration:
                # The shards are inconsistent: this shard's cviews don't add up to the width
                # the previous shard's tail expects to continue into. Rather than raising
                # (crashing the whole app) or leaving the row short (a corrupted-looking
                # canvas), pad the unmet gap with blank filler so the canvas stays rectangular.
                fill_rows = num_rows if num_rows is not None else done_rows + 1
                filler_cview = (0, 0, col_gap, fill_rows, None, blank_canvas)
                new_iter = blank_canvas.content(0, 0, col_gap, fill_rows, None) if create_iter else iter_default
                body.append((0, new_iter, filler_cview))
                col += col_gap
                col_gap = 0  # noqa: PLW2901
                break
            (trim_left, trim_top, cols, rows, attr_map, canv) = cview[:6]
            col += cols
            col_gap -= cols  # noqa: PLW2901
            if col_gap < 0:
                raise CanvasError("cviews overflow gaps in shard_tail!")
            if create_iter and canv:
                new_iter = canv.content(trim_left, trim_top, cols, rows, attr_map)
            else:
                new_iter = iter_default
            body.append((0, new_iter, cview))
        body.append((done_rows, content_iter, tail_cview))
    for cview in cviews_iter:
        (trim_left, trim_top, cols, rows, attr_map, canv) = cview[:6]
        if create_iter and canv:
            new_iter = canv.content(trim_left, trim_top, cols, rows, attr_map)
        else:
            new_iter = iter_default
        body.append((0, new_iter, cview))
    return body


def shards_trim_top(
    shards: Iterable[tuple[int, list[_CView]]],
    top: int,
) -> list[tuple[int, list[_CView]]]:
    """
    Return shards with top rows removed.

    :raises ValueError: *top* is not positive.
    :raises CanvasError: *top* is at least the number of rows in *shards*, so nothing would be left.
    """
    if top <= 0:
        raise ValueError(top)

    shard_iter = iter(shards)
    shard_tail: list[tuple[int, int, Iterator[_ContentLine] | None, _CView]] = []
    # skip over shards that are completely removed
    for num_rows, cviews in shard_iter:
        if top < num_rows:
            break
        sbody = shard_body(cviews, shard_tail, False, num_rows=num_rows)
        shard_tail = shard_body_tail(num_rows, sbody)
        top -= num_rows
    else:
        raise CanvasError("tried to trim shards out of existence")

    sbody = shard_body(cviews, shard_tail, False, num_rows=num_rows)
    shard_tail = shard_body_tail(num_rows, sbody)
    # trim the top of this shard
    new_sbody = [(0, content_iter, cview_trim_top(cv, done_rows + top)) for done_rows, content_iter, cv in sbody]

    sbody = new_sbody

    new_shards = [(num_rows - top, [cv for done_rows, content_iter, cv in sbody])]

    # write out the rest of the shards
    new_shards.extend(shard_iter)

    return new_shards


def shards_trim_rows(
    shards: Iterable[tuple[int, list[_CView]]],
    keep_rows: int,
) -> list[tuple[int, list[_CView]]]:
    """
    Return the topmost keep_rows rows from shards.

    :raises ValueError: *keep_rows* is negative.
    """
    if keep_rows < 0:
        raise ValueError(keep_rows)

    new_shards = []
    done_rows = 0
    for num_rows, cviews in shards:
        if done_rows >= keep_rows:
            break
        new_cviews = []
        for cv in cviews:
            if cv[3] + done_rows > keep_rows:
                new_cviews.append(cview_trim_rows(cv, keep_rows - done_rows))
            else:
                new_cviews.append(cv)

        if num_rows + done_rows > keep_rows:
            new_shards.append((keep_rows - done_rows, new_cviews))
        else:
            new_shards.append((num_rows, new_cviews))
        done_rows += num_rows

    return new_shards


def shards_trim_sides(
    shards: Iterable[tuple[int, list[_CView]]],
    left: int,
    cols: int,
) -> list[tuple[int, list[_CView]]]:
    """
    Return shards with starting from column left and cols total width.

    :raises ValueError: *left* is negative, or *cols* is not positive.
    """
    if left < 0:
        raise ValueError(left)
    if cols <= 0:
        raise ValueError(cols)
    return _shards_cut_columns(shards, ((left, cols),))[0]


def _shards_cut_columns(
    shards: Iterable[tuple[int, list[_CView]]],
    column_ranges: Sequence[tuple[int, int]],
) -> list[list[tuple[int, list[_CView]]]]:
    """Return the shards of each ``(left, cols)`` column range.

    *shards* is walked once for all ranges.
    Each range starts at a non-negative column and has a positive width.

    :returns: one shard list per entry of *column_ranges*, in the same order.
    :raises CanvasError: the cviews of a shard overflow the gaps the shards above it leave.
    """
    shard_tail: list[tuple[int, int, Iterator[_ContentLine] | None, _CView]] = []
    results: list[list[tuple[int, list[_CView]]]] = [[] for _ in column_ranges]
    for num_rows, cviews in shards:
        # Cviews starting in this shard get this shard's marker and continued ones keep an earlier one:
        # done_rows cannot tell them apart, since it stays 0 for a cview continued past a shard of no rows.
        started_here: Iterator[_ContentLine] = iter(())
        sbody = shard_body(cviews, shard_tail, False, started_here, num_rows=num_rows)
        shard_tail = shard_body_tail(num_rows, sbody)
        for new_shards, (left, cols) in zip(results, column_ranges, strict=True):
            right = left + cols
            new_cviews = []
            col = 0
            for _done_rows, content_iter, cv in sbody:
                next_col = col + cv[2]
                if content_iter is not started_here or next_col <= left or col >= right:
                    col = next_col
                    continue
                if col < left:
                    cv = cview_trim_left(cv, left - col)  # noqa: PLW2901
                    col = left
                if next_col > right:
                    cv = cview_trim_cols(cv, right - col)  # noqa: PLW2901
                new_cviews.append(cv)
                col = next_col
            if not new_cviews:
                prev_num_rows, prev_cviews = new_shards[-1]
                new_shards[-1] = (prev_num_rows + num_rows, prev_cviews)
            else:
                new_shards.append((num_rows, new_cviews))
    return results


def shards_join(shard_lists: Iterable[Iterable[tuple[int, list[_CView]]]]) -> list[tuple[int, list[_CView]]]:
    """Return the result of joining shard lists horizontally.

    All shards lists must have the same number of rows.
    """
    shards_iters: list[Iterator[tuple[int, list[_CView]]]] = [iter(sl) for sl in shard_lists]
    shards_current: list[tuple[int, list[_CView] | None]] = [next(i) for i in shards_iters]

    new_shards = []
    while True:
        new_cviews = []
        num_rows = min(r for r, _cv in shards_current)

        shards_next: list[tuple[int, list[_CView] | None]] = []
        for rows, cviews in shards_current:
            if cviews:
                new_cviews.extend(cviews)
            shards_next.append((rows - num_rows, None))

        shards_current = shards_next
        new_shards.append((num_rows, new_cviews))

        # advance to next shards
        try:
            for i in range(len(shards_current)):
                if shards_current[i][0] > 0:
                    continue
                shards_current[i] = next(shards_iters[i])
        except StopIteration:
            break
    return new_shards


def cview_trim_rows(cv: _CView, rows: int) -> _CView:
    """Return a copy of *cv* with its row count replaced by *rows*."""
    return (*cv[:3], rows, *cv[4:])


def cview_trim_top(cv: _CView, trim: int) -> _CView:
    """Return a copy of *cv* with *trim* rows removed from the top."""
    return (cv[0], trim + cv[1], cv[2], cv[3] - trim, *cv[4:])


def cview_trim_left(cv: _CView, trim: int) -> _CView:
    """Return a copy of *cv* with *trim* columns removed from the left."""
    return (cv[0] + trim, cv[1], cv[2] - trim, *cv[3:])


def cview_trim_cols(cv: _CView, cols: int) -> _CView:
    """Return a copy of *cv* with its column count replaced by *cols*."""
    return (*cv[:2], cols, *cv[3:])


def CanvasCombine(canvas_info: Iterable[tuple[Canvas, typing.Any, bool]]) -> CompositeCanvas:
    """Stack canvases in l vertically and return resulting canvas.

    :param canvas_info: list of (canvas, position, focus) tuples:

                        position
                            a value that widget.set_focus will accept or None if not allowed
                        focus
                            True if this canvas is the one that would be in focus if the whole widget is in focus
    """
    clist = [(CompositeCanvas(c), p, f) for c, p, f in canvas_info]

    combined_canvas = CompositeCanvas()
    shards = []
    children: list[tuple[int, int, Canvas, typing.Any]] = []
    row = 0
    focus_index = 0

    for n, (canv, pos, focus) in enumerate(clist):
        if focus:
            focus_index = n
        children.append((0, row, canv, pos))
        shards.extend(canv.shards)
        combined_canvas.coords.update(canv.translate_coords(0, row))
        for shortcut in canv.shortcuts:
            combined_canvas.shortcuts[shortcut] = pos
        row += canv.rows()

    if focus_index:
        children = [children[focus_index], *children[:focus_index], *children[focus_index + 1 :]]

    combined_canvas.shards = shards
    combined_canvas.children = children
    return combined_canvas


def CanvasOverlay(top_c: Canvas, bottom_c: Canvas, left: int, top: int) -> CompositeCanvas:
    """Overlay canvas top_c onto bottom_c at position (left, top)."""
    if not isinstance(top_c, CompositeCanvas):
        top_c = CompositeCanvas(top_c)
    overlayed_canvas = CompositeCanvas(bottom_c)
    overlayed_canvas.overlay(top_c, left, top)
    overlayed_canvas.children = [(left, top, top_c, None), (0, 0, bottom_c, None)]
    overlayed_canvas.shortcuts = {}  # disable background shortcuts
    for shortcut in top_c.shortcuts:
        overlayed_canvas.shortcuts[shortcut] = "fg"
    return overlayed_canvas


def CanvasJoin(canvas_info: Iterable[tuple[Canvas, typing.Any, bool, int]]) -> CompositeCanvas:
    """
    Join canvases in l horizontally. Return result.

    :param canvas_info: list of (canvas, position, focus, cols) tuples:

                        position
                            value that widget.set_focus will accept or None if not allowed
                        focus
                            True if this canvas is the one that would be in focus if the whole widget is in focus
                        cols
                            is the number of screen columns that this widget will require,
                            if larger than the actual canvas.cols() value then this widget
                            will be padded on the right.
    """
    l2 = []
    focus_item = 0
    maxrow = 0

    for n, (canv, pos, focus, cols) in enumerate(canvas_info):
        rows = canv.rows()
        pad_right = cols - canv.cols()
        if focus:
            focus_item = n
        maxrow = max(maxrow, rows)
        l2.append((canv, pos, pad_right, rows))

    shard_lists = []
    children: list[tuple[int, int, Canvas, typing.Any]] = []
    joined_canvas = CompositeCanvas()
    col = 0
    for canv, pos, pad_right, rows in l2:
        composite_canvas = CompositeCanvas(canv)
        if pad_right:
            composite_canvas.pad_trim_left_right(0, pad_right)
        if rows < maxrow:
            composite_canvas.pad_trim_top_bottom(0, maxrow - rows)
        joined_canvas.coords.update(composite_canvas.translate_coords(col, 0))
        for shortcut in composite_canvas.shortcuts:
            joined_canvas.shortcuts[shortcut] = pos
        shard_lists.append(composite_canvas.shards)
        children.append((col, 0, composite_canvas, pos))
        col += composite_canvas.cols()

    if focus_item:
        children = [children[focus_item], *children[:focus_item], *children[focus_item + 1 :]]

    joined_canvas.shards = shards_join(shard_lists)
    joined_canvas.children = children
    return joined_canvas
