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


from __future__ import annotations

import typing
import warnings
import weakref
from contextlib import suppress

from urwid.text_layout import LayoutSegment, trim_line
from urwid.util import (
    apply_target_encoding,
    calc_text_pos,
    calc_width,
    rle_append_modify,
    rle_join_modify,
    rle_len,
    rle_product,
    trim_text_attr_cs,
)

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from .widget import Widget


class CanvasCache:
    """
    Cache for rendered canvases.  Automatically populated and
    accessed by Widget render() MetaClass magic, cleared by
    Widget._invalidate().

    Stores weakrefs to the canvas objects, so an external class
    must maintain a reference for this cache to be effective.
    At present the Screen classes store the last topmost canvas
    after redrawing the screen, keeping the canvases from being
    garbage collected.

    _widgets[widget] = {(wcls, size, focus): weakref.ref(canvas), ...}
    _refs[weakref.ref(canvas)] = (widget, wcls, size, focus)
    _deps[widget} = [dependent_widget, ...]
    """

    _widgets: typing.ClassVar[
        dict[
            Widget,
            dict[
                tuple[type[Widget], tuple[int, int] | tuple[int] | tuple[()], bool],
                weakref.ReferenceType,
            ],
        ]
    ] = {}
    _refs: typing.ClassVar[
        dict[
            weakref.ReferenceType,
            tuple[type[Widget], tuple[int, int] | tuple[int] | tuple[()], bool],
        ]
    ] = {}
    _deps: typing.ClassVar[dict[Widget, list[Widget]]] = {}
    hits = 0
    fetches = 0
    cleanups = 0

    @classmethod
    def store(cls, wcls, canvas):
        """
        Store a weakref to canvas in the cache.

        wcls -- widget class that contains render() function
        canvas -- rendered canvas with widget_info (widget, size, focus)
        """
        if not canvas.cacheable:
            return

        if not canvas.widget_info:
            raise TypeError("Can't store canvas without widget_info")
        widget, size, focus = canvas.widget_info

        def walk_depends(canv):
            """
            Collect all child widgets for determining who we
            depend on.
            """
            # FIXME: is this recursion necessary?  The cache
            # invalidating might work with only one level.
            depends = []
            for _x, _y, c, _pos in canv.children:
                if c.widget_info:
                    depends.append(c.widget_info[0])
                elif hasattr(c, "children"):
                    depends.extend(walk_depends(c))
            return depends

        # use explicit depends_on if available from the canvas
        depends_on = getattr(canvas, "depends_on", None)
        if depends_on is None and hasattr(canvas, "children"):
            depends_on = walk_depends(canvas)
        if depends_on:
            for w in depends_on:
                if w not in cls._widgets:
                    return
            for w in depends_on:
                cls._deps.setdefault(w, []).append(widget)

        ref = weakref.ref(canvas, cls.cleanup)
        cls._refs[ref] = (widget, wcls, size, focus)
        cls._widgets.setdefault(widget, {})[(wcls, size, focus)] = ref

    @classmethod
    def fetch(cls, widget, wcls, size, focus):
        """
        Return the cached canvas or None.

        widget -- widget object requested
        wcls -- widget class that contains render() function
        size, focus -- render() parameters
        """
        cls.fetches += 1  # collect stats

        sizes = cls._widgets.get(widget, None)
        if not sizes:
            return None
        ref = sizes.get((wcls, size, focus), None)
        if not ref:
            return None
        canv = ref()
        if canv:
            cls.hits += 1  # more stats
        return canv

    @classmethod
    def invalidate(cls, widget):
        """
        Remove all canvases cached for widget.
        """
        try:
            for ref in cls._widgets[widget].values():
                with suppress(KeyError):
                    del cls._refs[ref]
            del cls._widgets[widget]
        except KeyError:
            pass
        if widget not in cls._deps:
            return
        dependants = cls._deps.get(widget, [])
        with suppress(KeyError):
            del cls._deps[widget]
        for w in dependants:
            cls.invalidate(w)

    @classmethod
    def cleanup(cls, ref):
        cls.cleanups += 1  # collect stats

        w = cls._refs.get(ref, None)
        del cls._refs[ref]
        if not w:
            return
        widget, wcls, size, focus = w
        sizes = cls._widgets.get(widget, None)
        if not sizes:
            return
        with suppress(KeyError):
            del sizes[(wcls, size, focus)]
        if not sizes:
            try:
                del cls._widgets[widget]
                del cls._deps[widget]
            except KeyError:
                pass

    @classmethod
    def clear(cls):
        """
        Empty the cache.
        """
        cls._widgets = {}
        cls._refs = {}
        cls._deps = {}


class CanvasError(Exception):
    pass


class Canvas:
    """
    base class for canvases
    """

    cacheable = True

    _finalized_error = CanvasError(
        "This canvas has been finalized. Use CompositeCanvas to wrap this canvas if you need to make changes."
    )
    _renamed_error = CanvasError(
        "The old Canvas class is now called TextCanvas. Canvas is now the base class for all canvas classes."
    )

    def __init__(
        self,
        value1: typing.Any = None,
        value2: typing.Any = None,
        value3: typing.Any = None,
    ) -> None:
        """
        value1, value2, value3 -- if not None, raise a helpful error:
            the old Canvas class is now called TextCanvas.
        """
        if value1 is not None:
            raise self._renamed_error
        self._widget_info = None
        self.coords = {}
        self.shortcuts = {}

    def finalize(
        self,
        widget: Widget,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool,
    ) -> None:
        """
        Mark this canvas as finalized (should not be any future
        changes to its content). This is required before caching
        the canvas.  This happens automatically after a widget's
        'render call returns the canvas thanks to some metaclass
        magic.

        widget -- widget that rendered this canvas
        size -- size parameter passed to widget's render method
        focus -- focus parameter passed to widget's render method
        """
        if self.widget_info:
            raise self._finalized_error
        self._widget_info = widget, size, focus

    @property
    def widget_info(self):
        return self._widget_info

    def _get_widget_info(self):
        warnings.warn(
            f"Method `{self.__class__.__name__}._get_widget_info` is deprecated, "
            f"please use property `{self.__class__.__name__}.widget_info`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.widget_info

    @property
    def text(self) -> list[bytes]:
        """
        Return the text content of the canvas as a list of strings,
        one for each row.
        """
        return [b"".join([text for (attr, cs, text) in row]) for row in self.content()]

    def _text_content(self):
        warnings.warn(
            f"Method `{self.__class__.__name__}._text_content` is deprecated, "
            f"please use property `{self.__class__.__name__}.text`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.text

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int | None = None,
        rows: int | None = None,
        attr=None,
    ):
        raise NotImplementedError()

    def cols(self):
        raise NotImplementedError()

    def rows(self):
        raise NotImplementedError()

    def content_delta(self):
        raise NotImplementedError()

    def get_cursor(self) -> tuple[int, int] | None:
        c = self.coords.get("cursor", None)
        if not c:
            return None
        return c[:2]  # trim off data part

    def set_cursor(self, c):
        if self.widget_info and self.cacheable:
            raise self._finalized_error
        if c is None:
            with suppress(KeyError):
                del self.coords["cursor"]
            return
        self.coords["cursor"] = (*c, None)  # data part

    cursor = property(get_cursor, set_cursor)

    def get_pop_up(self):
        c = self.coords.get("pop up", None)
        if not c:
            return None
        return c

    def set_pop_up(self, w: Widget, left: int, top: int, overlay_width: int, overlay_height: int):
        """
        This method adds pop-up information to the canvas.  This information
        is intercepted by a PopUpTarget widget higher in the chain to
        display a pop-up at the given (left, top) position relative to the
        current canvas.

        :param w: widget to use for the pop-up
        :type w: widget
        :param left: x position for left edge of pop-up >= 0
        :type left: int
        :param top: y position for top edge of pop-up >= 0
        :type top: int
        :param overlay_width: width of overlay in screen columns > 0
        :type overlay_width: int
        :param overlay_height: height of overlay in screen rows > 0
        :type overlay_height: int
        """
        if self.widget_info and self.cacheable:
            raise self._finalized_error

        self.coords["pop up"] = (left, top, (w, overlay_width, overlay_height))

    def translate_coords(self, dx: int, dy: int):
        """
        Return coords shifted by (dx, dy).
        """
        d = {}
        for name, (x, y, data) in self.coords.items():
            d[name] = (x + dx, y + dy, data)
        return d


class TextCanvas(Canvas):
    """
    class for storing rendered text and attributes
    """

    def __init__(
        self,
        text: Sequence[bytes] | None = None,
        attr=None,
        cs=None,
        cursor: tuple[int, int] | None = None,
        maxcol: int | None = None,
        check_width: bool = True,
    ) -> None:
        """
        text -- list of strings, one for each line
        attr -- list of run length encoded attributes for text
        cs -- list of run length encoded character set for text
        cursor -- (x,y) of cursor or None
        maxcol -- screen columns taken by this canvas
        check_width -- check and fix width of all lines in text
        """
        super().__init__()
        if text is None:
            text = []

        if check_width:
            widths = []
            for t in text:
                if not isinstance(t, bytes):
                    raise CanvasError("Canvas text must be plain strings encoded in the screen's encoding", repr(text))
                widths.append(calc_width(t, 0, len(t)))
        else:
            if not isinstance(maxcol, int):
                raise TypeError(maxcol)
            widths = [maxcol] * len(text)

        if maxcol is None:
            if widths:
                # find maxcol ourselves
                maxcol = max(widths)
            else:
                maxcol = 0

        if attr is None:
            attr = [[] for _ in range(len(text))]
        if cs is None:
            cs = [[] for _ in range(len(text))]

        # pad text and attr to maxcol
        for i in range(len(text)):
            w = widths[i]
            if w > maxcol:
                raise CanvasError(f"Canvas text is wider than the maxcol specified \n{maxcol!r}\n{widths!r}\n{text!r}")
            if w < maxcol:
                text[i] += b"".rjust(maxcol - w)
            a_gap = len(text[i]) - rle_len(attr[i])
            if a_gap < 0:
                raise CanvasError(f"Attribute extends beyond text \n{text[i]!r}\n{attr[i]!r}")
            if a_gap:
                rle_append_modify(attr[i], (None, a_gap))

            cs_gap = len(text[i]) - rle_len(cs[i])
            if cs_gap < 0:
                raise CanvasError(f"Character Set extends beyond text \n{text[i]!r}\n{cs[i]!r}")
            if cs_gap:
                rle_append_modify(cs[i], (None, cs_gap))

        self._attr = attr
        self._cs = cs
        self.cursor = cursor
        self._text = text
        self._maxcol = maxcol

    def rows(self) -> int:
        """Return the number of rows in this canvas."""
        rows = len(self._text)
        if not isinstance(rows, int):
            raise TypeError(rows)
        return rows

    def cols(self) -> int:
        """Return the screen column width of this canvas."""
        return self._maxcol

    def translated_coords(self, dx: int, dy: int) -> tuple[int, int] | None:
        """
        Return cursor coords shifted by (dx, dy), or None if there
        is no cursor.
        """
        if self.cursor:
            x, y = self.cursor
            return x + dx, y + dy
        return None

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr_map=None,
    ):
        """
        Return the canvas content as a list of rows where each row
        is a list of (attr, cs, text) tuples.

        trim_left, trim_top, cols, rows may be set by
        CompositeCanvas when rendering a partially obscured
        canvas.
        """
        maxcol, maxrow = self.cols(), self.rows()
        if not cols:
            cols = maxcol - trim_left
        if not rows:
            rows = maxrow - trim_top

        if not ((0 <= trim_left < maxcol) and (cols > 0 and trim_left + cols <= maxcol)):
            raise ValueError(trim_left)
        if not ((0 <= trim_top < maxrow) and (rows > 0 and trim_top + rows <= maxrow)):
            raise ValueError(trim_top)

        if trim_top or rows < maxrow:
            text_attr_cs = zip(
                self._text[trim_top : trim_top + rows],
                self._attr[trim_top : trim_top + rows],
                self._cs[trim_top : trim_top + rows],
            )
        else:
            text_attr_cs = zip(self._text, self._attr, self._cs)

        for text, a_row, cs_row in text_attr_cs:
            if trim_left or cols < self._maxcol:
                text, a_row, cs_row = trim_text_attr_cs(  # noqa: PLW2901
                    text,
                    a_row,
                    cs_row,
                    trim_left,
                    trim_left + cols,
                )
            attr_cs = rle_product(a_row, cs_row)
            i = 0
            row = []
            for (a, cs), run in attr_cs:
                if attr_map and a in attr_map:
                    a = attr_map[a]  # noqa: PLW2901
                row.append((a, cs, text[i : i + run]))
                i += run
            yield row

    def content_delta(self, other):
        """
        Return the differences between other and this canvas.

        If other is the same object as self this will return no
        differences, otherwise this is the same as calling
        content().
        """
        if other is self:
            return [self.cols()] * self.rows()
        return self.content()


class BlankCanvas(Canvas):
    """
    a canvas with nothing on it, only works as part of a composite canvas
    since it doesn't know its own size
    """

    def __init__(self) -> None:
        super().__init__(None)

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr=None,
    ):
        """
        return (cols, rows) of spaces with default attributes.
        """
        def_attr = None
        if attr and None in attr:
            def_attr = attr[None]
        line = [(def_attr, None, b"".rjust(cols))]
        for _ in range(rows):
            yield line

    def cols(self) -> typing.NoReturn:
        raise NotImplementedError("BlankCanvas doesn't know its own size!")

    def rows(self) -> typing.NoReturn:
        raise NotImplementedError("BlankCanvas doesn't know its own size!")

    def content_delta(self) -> typing.NoReturn:
        raise NotImplementedError("BlankCanvas doesn't know its own size!")


blank_canvas = BlankCanvas()


class SolidCanvas(Canvas):
    """
    A canvas filled completely with a single character.
    """

    def __init__(self, fill_char, cols: int, rows: int) -> None:
        super().__init__()
        end, col = calc_text_pos(fill_char, 0, len(fill_char), 1)
        if col != 1:
            raise ValueError(f"Invalid fill_char: {fill_char!r}")
        self._text, cs = apply_target_encoding(fill_char[:end])
        self._cs = cs[0][0]
        self.size = cols, rows
        self.cursor = None

    def cols(self) -> int:
        return self.size[0]

    def rows(self) -> int:
        return self.size[1]

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int | None = None,
        rows: int | None = None,
        attr=None,
    ):
        if cols is None:
            cols = self.size[0]
        if rows is None:
            rows = self.size[1]
        def_attr = None
        if attr and None in attr:
            def_attr = attr[None]

        line = [(def_attr, self._cs, self._text * cols)]
        for _ in range(rows):
            yield line

    def content_delta(self, other):
        """
        Return the differences between other and this canvas.
        """
        if other is self:
            return [self.cols()] * self.rows()
        return self.content()


class CompositeCanvas(Canvas):
    """
    class for storing a combination of canvases
    """

    def __init__(self, canv: Canvas = None) -> None:
        """
        canv -- a Canvas object to wrap this CompositeCanvas around.

        if canv is a CompositeCanvas, make a copy of its contents
        """
        # a "shard" is a (num_rows, list of cviews) tuple, one for
        # each cview starting in this shard

        # a "cview" is a tuple that defines a view of a canvas:
        # (trim_left, trim_top, cols, rows, attr_map, canv)

        # a "shard tail" is a list of tuples:
        # (col_gap, done_rows, content_iter, cview)

        # tuples that define the unfinished cviews that are part of
        # shards following the first shard.
        super().__init__()

        if canv is None:
            self.shards = []
            self.children = []
        else:
            if hasattr(canv, "shards"):
                self.shards = canv.shards
            else:
                self.shards = [(canv.rows(), [(0, 0, canv.cols(), canv.rows(), None, canv)])]
            self.children = [(0, 0, canv, None)]
            self.coords.update(canv.coords)
            for shortcut in canv.shortcuts:
                self.shortcuts[shortcut] = "wrap"

    def rows(self) -> int:
        for r, cv in self.shards:
            if not isinstance(r, int):
                raise TypeError(r, cv)
        rows = sum(r for r, cv in self.shards)
        if not isinstance(rows, int):
            raise TypeError(rows)
        return rows

    def cols(self) -> int:
        if not self.shards:
            return 0
        cols = sum([cv[2] for cv in self.shards[0][1]])
        if not isinstance(cols, int):
            raise TypeError(cols)
        return cols

    def content(self):
        """
        Return the canvas content as a list of rows where each row
        is a list of (attr, cs, text) tuples.
        """
        shard_tail = []
        for num_rows, cviews in self.shards:
            # combine shard and shard tail
            sbody = shard_body(cviews, shard_tail)

            # output rows
            for _ in range(num_rows):
                yield shard_body_row(sbody)

            # prepare next shard tail
            shard_tail = shard_body_tail(num_rows, sbody)

    def content_delta(self, other):
        """
        Return the differences between other and this canvas.
        """
        if not hasattr(other, "shards"):
            for row in self.content():
                yield row
            return

        shard_tail = []
        for num_rows, cviews in shards_delta(self.shards, other.shards):
            # combine shard and shard tail
            sbody = shard_body(cviews, shard_tail)

            # output rows
            row = []
            for _ in range(num_rows):
                # if whole shard is unchanged, don't keep
                # calling shard_body_row
                if len(row) != 1 or not isinstance(row[0], int):
                    row = shard_body_row(sbody)
                yield row

            # prepare next shard tail
            shard_tail = shard_body_tail(num_rows, sbody)

    def trim(self, top: int, count: int | None = None) -> None:
        """Trim lines from the top and/or bottom of canvas.

        top -- number of lines to remove from top
        count -- number of lines to keep, or None for all the rest
        """
        if top < 0:
            raise ValueError(f"invalid trim amount {top:d}!")
        if top >= self.rows():
            raise ValueError(f"cannot trim {top:d} lines from {self.rows():d}!")
        if self.widget_info:
            raise self._finalized_error

        if top:
            self.shards = shards_trim_top(self.shards, top)

        if count == 0:
            self.shards = []
        elif count is not None:
            self.shards = shards_trim_rows(self.shards, count)

        self.coords = self.translate_coords(0, -top)

    def trim_end(self, end: int) -> None:
        """Trim lines from the bottom of the canvas.

        end -- number of lines to remove from the end
        """
        if end <= 0:
            raise ValueError(f"invalid trim amount {end:d}!")
        if end > self.rows():
            raise ValueError(f"cannot trim {end:d} lines from {self.rows():d}!")
        if self.widget_info:
            raise self._finalized_error

        self.shards = shards_trim_rows(self.shards, self.rows() - end)

    def pad_trim_left_right(self, left: int, right: int) -> None:
        """
        Pad or trim this canvas on the left and right

        values > 0 indicate screen columns to pad
        values < 0 indicate screen columns to trim
        """
        if self.widget_info:
            raise self._finalized_error
        shards = self.shards
        if left < 0 or right < 0:
            trim_left = max(0, -left)
            cols = self.cols() - trim_left - max(0, -right)
            shards = shards_trim_sides(shards, trim_left, cols)

        rows = self.rows()
        if left > 0 or right > 0:
            top_rows, top_cviews = shards[0]
            if left > 0:
                new_top_cviews = [(0, 0, left, rows, None, blank_canvas), *top_cviews]
            else:
                new_top_cviews = top_cviews[:]  # copy

            if right > 0:
                new_top_cviews.append((0, 0, right, rows, None, blank_canvas))
            shards = [(top_rows, new_top_cviews)] + shards[1:]

        self.coords = self.translate_coords(left, 0)
        self.shards = shards

    def pad_trim_top_bottom(self, top: int, bottom: int) -> None:
        """
        Pad or trim this canvas on the top and bottom.
        """
        if self.widget_info:
            raise self._finalized_error
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
                self.shards = self.shards[:]
            self.shards.append((bottom, [(0, 0, cols, bottom, None, blank_canvas)]))

    def overlay(self, other, left: int, top: int) -> None:
        """Overlay other onto this canvas."""
        if self.widget_info:
            raise self._finalized_error

        width = other.cols()
        height = other.rows()
        right = self.cols() - left - width
        bottom = self.rows() - top - height

        if right < 0:
            raise ValueError(f"top canvas of overlay not the size expected!{(other.cols(), left, right, width)!r}")
        if bottom < 0:
            raise ValueError(f"top canvas of overlay not the size expected!{(other.rows(), top, bottom, height)!r}")

        shards = self.shards
        top_shards = []
        side_shards = self.shards
        bottom_shards = []
        if top:
            side_shards = shards_trim_top(shards, top)
            top_shards = shards_trim_rows(shards, top)
        if bottom:
            bottom_shards = shards_trim_top(side_shards, height)
            side_shards = shards_trim_rows(side_shards, height)

        left_shards = []
        right_shards = []
        if left > 0:
            left_shards = [shards_trim_sides(side_shards, 0, left)]
        if right > 0:
            right_shards = [shards_trim_sides(side_shards, max(0, left + width), right)]

        if not self.rows():
            middle_shards = []
        elif left or right:
            middle_shards = shards_join((*left_shards, other.shards, *right_shards))
        else:
            middle_shards = other.shards

        self.shards = top_shards + middle_shards + bottom_shards

        self.coords.update(other.translate_coords(left, top))

    def fill_attr(self, a) -> None:
        """
        Apply attribute a to all areas of this canvas with default
        attribute currently set to None, leaving other attributes
        intact."""
        self.fill_attr_apply({None: a})

    def fill_attr_apply(self, mapping) -> None:
        """
        Apply an attribute-mapping dictionary to the canvas.

        mapping -- dictionary of original-attribute:new-attribute items
        """
        if self.widget_info:
            raise self._finalized_error

        shards = []
        for num_rows, original_cviews in self.shards:
            new_cviews = []
            for cv in original_cviews:
                # cv[4] == attr_map
                if cv[4] is None:
                    new_cviews.append(cv[:4] + (mapping,) + cv[5:])
                else:
                    combined = dict(mapping)
                    combined.update([(k, mapping.get(v, v)) for k, v in cv[4].items()])
                    new_cviews.append(cv[:4] + (combined,) + cv[5:])
            shards.append((num_rows, new_cviews))
        self.shards = shards

    def set_depends(self, widget_list):
        """
        Explicitly specify the list of widgets that this canvas
        depends on.  If any of these widgets change this canvas
        will have to be updated.
        """
        if self.widget_info:
            raise self._finalized_error

        self.depends_on = widget_list


def shard_body_row(sbody):
    """
    Return one row, advancing the iterators in sbody.

    ** MODIFIES sbody by calling next() on its iterators **
    """
    row = []
    for _done_rows, content_iter, cview in sbody:
        if content_iter:
            row.extend(next(content_iter))
        else:  # noqa: PLR5501
            # need to skip this unchanged canvas
            if row and isinstance(row[-1], int):
                row[-1] = row[-1] + cview[2]
            else:
                row.append(cview[2])

    return row


def shard_body_tail(num_rows: int, sbody):
    """
    Return a new shard tail that follows this shard body.
    """
    shard_tail = []
    col_gap = 0
    done_rows = 0
    for done_rows, content_iter, cview in sbody:
        cols, rows = cview[2:4]
        done_rows += num_rows  # noqa: PLW2901
        if done_rows == rows:
            col_gap += cols
            continue
        shard_tail.append((col_gap, done_rows, content_iter, cview))
        col_gap = 0
    return shard_tail


def shards_delta(shards, other_shards):
    """
    Yield shards1 with cviews that are the same as shards2
    having canv = None.
    """
    other_shards_iter = iter(other_shards)
    other_num_rows = other_cviews = None
    done = other_done = 0
    for num_rows, cviews in shards:
        if other_num_rows is None:
            other_num_rows, other_cviews = next(other_shards_iter)
        while other_done < done:
            other_done += other_num_rows
            other_num_rows, other_cviews = next(other_shards_iter)
        if other_done > done:
            yield (num_rows, cviews)
            done += num_rows
            continue
        # top-aligned shards, compare each cview
        yield (num_rows, shard_cviews_delta(cviews, other_cviews))
        other_done += other_num_rows
        other_num_rows = None
        done += num_rows


def shard_cviews_delta(cviews, other_cviews):
    """ """
    other_cviews_iter = iter(other_cviews)
    other_cv = None
    cols = other_cols = 0
    for cv in cviews:
        if other_cv is None:
            other_cv = next(other_cviews_iter)
        while other_cols < cols:
            other_cols += other_cv[2]
            other_cv = next(other_cviews_iter)
        if other_cols > cols:
            yield cv
            cols += cv[2]
            continue
        # top-left-aligned cviews, compare them
        if cv[5] is other_cv[5] and cv[:5] == other_cv[:5]:
            yield cv[:5] + (None,) + cv[6:]
        else:
            yield cv
        other_cols += other_cv[2]
        other_cv = None
        cols += cv[2]


def shard_body(cviews, shard_tail, create_iter: bool = True, iter_default=None):
    """
    Return a list of (done_rows, content_iter, cview) tuples for
    this shard and shard tail.

    If a canvas in cviews is None (eg. when unchanged from
    shard_cviews_delta()) or if create_iter is False then no
    iterator is created for content_iter.

    iter_default is the value used for content_iter when no iterator
    is created.
    """
    col = 0
    body = []  # build the next shard tail
    cviews_iter = iter(cviews)
    for col_gap, done_rows, content_iter, tail_cview in shard_tail:
        while col_gap:
            try:
                cview = next(cviews_iter)
            except StopIteration:
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


def shards_trim_top(shards, top: int):
    """
    Return shards with top rows removed.
    """
    if top <= 0:
        raise ValueError(top)

    shard_iter = iter(shards)
    shard_tail = []
    # skip over shards that are completely removed
    for num_rows, cviews in shard_iter:
        if top < num_rows:
            break
        sbody = shard_body(cviews, shard_tail, False)
        shard_tail = shard_body_tail(num_rows, sbody)
        top -= num_rows
    else:
        raise CanvasError("tried to trim shards out of existence")

    sbody = shard_body(cviews, shard_tail, False)
    shard_tail = shard_body_tail(num_rows, sbody)
    # trim the top of this shard
    new_sbody = []
    for done_rows, content_iter, cv in sbody:
        new_sbody.append((0, content_iter, cview_trim_top(cv, done_rows + top)))
    sbody = new_sbody

    new_shards = [(num_rows - top, [cv for done_rows, content_iter, cv in sbody])]

    # write out the rest of the shards
    new_shards.extend(shard_iter)

    return new_shards


def shards_trim_rows(shards, keep_rows: int):
    """
    Return the topmost keep_rows rows from shards.
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


def shards_trim_sides(shards, left: int, cols: int):
    """
    Return shards with starting from column left and cols total width.
    """
    if left < 0:
        raise ValueError(left)
    if cols <= 0:
        raise ValueError(cols)
    shard_tail = []
    new_shards = []
    right = left + cols
    for num_rows, cviews in shards:
        sbody = shard_body(cviews, shard_tail, False)
        shard_tail = shard_body_tail(num_rows, sbody)
        new_cviews = []
        col = 0
        for done_rows, _content_iter, cv in sbody:
            cv_cols = cv[2]
            next_col = col + cv_cols
            if done_rows or next_col <= left or col >= right:
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
    return new_shards


def shards_join(shard_lists):
    """
    Return the result of joining shard lists horizontally.
    All shards lists must have the same number of rows.
    """
    shards_iters = [iter(sl) for sl in shard_lists]
    shards_current = [next(i) for i in shards_iters]

    new_shards = []
    while True:
        new_cviews = []
        num_rows = min([r for r, cv in shards_current])

        shards_next = []
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


def cview_trim_rows(cv, rows: int):
    return cv[:3] + (rows,) + cv[4:]


def cview_trim_top(cv, trim: int):
    return (cv[0], trim + cv[1], cv[2], cv[3] - trim) + cv[4:]


def cview_trim_left(cv, trim: int):
    return (cv[0] + trim, cv[1], cv[2] - trim) + cv[3:]


def cview_trim_cols(cv, cols: int):
    return cv[:2] + (cols,) + cv[3:]


def CanvasCombine(canvas_info):
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
    children = []
    row = 0
    focus_index = 0
    n = 0
    for canv, pos, focus in clist:
        if focus:
            focus_index = n
        children.append((0, row, canv, pos))
        shards.extend(canv.shards)
        combined_canvas.coords.update(canv.translate_coords(0, row))
        for shortcut in canv.shortcuts:
            combined_canvas.shortcuts[shortcut] = pos
        row += canv.rows()
        n += 1

    if focus_index:
        children = [children[focus_index]] + children[:focus_index] + children[focus_index + 1 :]

    combined_canvas.shards = shards
    combined_canvas.children = children
    return combined_canvas


def CanvasOverlay(top_c, bottom_c, left: int, top: int):
    """
    Overlay canvas top_c onto bottom_c at position (left, top).
    """
    overlayed_canvas = CompositeCanvas(bottom_c)
    overlayed_canvas.overlay(top_c, left, top)
    overlayed_canvas.children = [(left, top, top_c, None), (0, 0, bottom_c, None)]
    overlayed_canvas.shortcuts = {}  # disable background shortcuts
    for shortcut in top_c.shortcuts:
        overlayed_canvas.shortcuts[shortcut] = "fg"
    return overlayed_canvas


def CanvasJoin(canvas_info):
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
    n = 0
    for canv, pos, focus, cols in canvas_info:
        rows = canv.rows()
        pad_right = cols - canv.cols()
        if focus:
            focus_item = n
        if rows > maxrow:
            maxrow = rows
        l2.append((canv, pos, pad_right, rows))
        n += 1

    shard_lists = []
    children = []
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
        children = [children[focus_item]] + children[:focus_item] + children[focus_item + 1 :]

    joined_canvas.shards = shards_join(shard_lists)
    joined_canvas.children = children
    return joined_canvas


def apply_text_layout(text, attr, ls, maxcol: int):
    t = []
    a = []
    c = []

    class AttrWalk:
        pass

    aw = AttrWalk
    aw.k = 0  # counter for moving through elements of a
    aw.off = 0  # current offset into text of attr[ak]

    def arange(start_offs: int, end_offs: int):
        """Return an attribute list for the range of text specified."""
        if start_offs < aw.off:
            aw.k = 0
            aw.off = 0
        o = []
        # the loop should run at least once, the '=' part ensures that
        while aw.off <= end_offs:
            if len(attr) <= aw.k:
                # run out of attributes
                o.append((None, end_offs - max(start_offs, aw.off)))
                break
            at, run = attr[aw.k]
            if aw.off + run <= start_offs:
                # move forward through attr to find start_offs
                aw.k += 1
                aw.off += run
                continue
            if end_offs <= aw.off + run:
                o.append((at, end_offs - max(start_offs, aw.off)))
                break
            o.append((at, aw.off + run - max(start_offs, aw.off)))
            aw.k += 1
            aw.off += run
        return o

    for line_layout in ls:
        # trim the line to fit within maxcol
        line_layout = trim_line(line_layout, text, 0, maxcol)  # noqa: PLW2901

        line = []
        linea = []
        linec = []

        def attrrange(start_offs: int, end_offs: int, destw: int) -> None:
            """
            Add attributes based on attributes between
            start_offs and end_offs.
            """
            if start_offs == end_offs:
                [(at, run)] = arange(start_offs, end_offs)
                rle_append_modify(linea, (at, destw))  # noqa: B023
                return
            if destw == end_offs - start_offs:
                for at, run in arange(start_offs, end_offs):
                    rle_append_modify(linea, (at, run))  # noqa: B023
                return
            # encoded version has different width
            o = start_offs
            for at, run in arange(start_offs, end_offs):
                if o + run == end_offs:
                    rle_append_modify(linea, (at, destw))  # noqa: B023
                    return
                tseg = text[o : o + run]
                tseg, cs = apply_target_encoding(tseg)
                segw = rle_len(cs)

                rle_append_modify(linea, (at, segw))  # noqa: B023
                o += run
                destw -= segw

        for seg in line_layout:
            # if seg is None: assert 0, ls
            s = LayoutSegment(seg)
            if s.end:
                tseg, cs = apply_target_encoding(text[s.offs : s.end])
                line.append(tseg)
                attrrange(s.offs, s.end, rle_len(cs))
                rle_join_modify(linec, cs)
            elif s.text:
                tseg, cs = apply_target_encoding(s.text)
                line.append(tseg)
                attrrange(s.offs, s.offs, len(tseg))
                rle_join_modify(linec, cs)
            elif s.offs:
                if s.sc:
                    line.append(b"".rjust(s.sc))
                    attrrange(s.offs, s.offs, s.sc)
            else:
                line.append(b"".rjust(s.sc))
                linea.append((None, s.sc))
                linec.append((None, s.sc))

        t.append(b"".join(line))
        a.append(linea)
        c.append(linec)

    return TextCanvas(t, a, c, maxcol=maxcol)
