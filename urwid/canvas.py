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


"""Canvases: the rendered, cacheable output of widgets, and the functions that combine them."""

from __future__ import annotations

import contextlib
import dataclasses
import itertools
import re
import typing
import weakref
from collections.abc import Mapping

import wcwidth

from urwid.str_util import calc_text_pos, calc_width, get_byte_encoding
from urwid.text_layout import LayoutSegment, trim_line
from urwid.util import (
    LayeredAttr,
    apply_target_encoding,
    get_encoding,
    rle_append_modify,
    rle_join_modify,
    rle_len,
    rle_product,
    trim_text_attr_cs,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator, Sequence
    from typing import Literal, NotRequired

    from .widget import AbstractWidget

    _ContentLine = list[tuple[Hashable, Literal["0", "U"] | None, bytes]]
    _CView = tuple[int, int, int, int, Mapping[Hashable, Hashable] | None, "Canvas"]

    _CanvasCoords = typing.TypedDict(
        "_CanvasCoords",
        {
            "pop up": NotRequired[tuple[int, int, tuple[AbstractWidget, int, int]]],
            "cursor": NotRequired[tuple[int, int, None]],
        },
    )


def _walk_depends(canv: Canvas) -> list[AbstractWidget]:
    """Collect all child widgets of *canv* for determining who a cached canvas depends on."""
    # FIXME: is this recursion necessary?  The cache invalidating might work with only one level.
    depends = []
    for _x, _y, c, _pos in canv.children:  # type: ignore[attr-defined]  # we made `hasattr` check
        if c.widget_info:
            depends.append(c.widget_info[0])
        elif hasattr(c, "children"):
            depends.extend(_walk_depends(c))
    return depends


class CanvasCache:
    """Cache for rendered canvases.

    Automatically populated and accessed by Widget render() MetaClass magic, cleared by
    Widget._invalidate().

    Stores weakrefs to the canvas objects, so an external class
    must maintain a reference for this cache to be effective.
    At present the Screen classes store the last topmost canvas
    after redrawing the screen, keeping the canvases from being
    garbage collected.

    _widgets[widget] = {(wcls, size, focus): weakref.ref(canvas), ...}
    _refs[weakref.ref(canvas)] = (widget, wcls, size, focus)
    _deps[widget] = {dependent_widget, ...}
    _children[dependent_widget] = {widget, ...}

    _children is the reverse of _deps.
    It removes a dependent widget from _deps once that widget has no cached canvas left.
    Widgets are not guaranteed to be weak-referenceable, so neither index can use weak references.
    """

    _widgets: typing.ClassVar[
        dict[
            AbstractWidget,
            dict[
                tuple[type[AbstractWidget], tuple[int, int] | tuple[int] | tuple[()], bool],
                weakref.ReferenceType[Canvas],
            ],
        ]
    ] = {}
    _refs: typing.ClassVar[
        dict[
            weakref.ReferenceType[Canvas],
            tuple[AbstractWidget, type[AbstractWidget], tuple[int, int] | tuple[int] | tuple[()], bool],
        ]
    ] = {}
    _deps: typing.ClassVar[dict[AbstractWidget, set[AbstractWidget]]] = {}
    _children: typing.ClassVar[dict[AbstractWidget, set[AbstractWidget]]] = {}
    hits = 0
    fetches = 0
    cleanups = 0

    @classmethod
    def store(cls, wcls: type[AbstractWidget], canvas: Canvas) -> None:
        """
        Store a weakref to canvas in the cache.

        :param wcls: widget class that contains render() function
        :param canvas: rendered canvas with widget_info (widget, size, focus)
        :raises TypeError: *canvas* has not been finalized, so it carries no widget_info.
        """
        if not canvas.cacheable:
            return

        info = canvas.widget_info
        if not info:
            raise TypeError("Can't store canvas without widget_info")
        widget, size, focus = info

        # use explicit depends_on if available from the canvas
        depends_on = getattr(canvas, "depends_on", None)
        if depends_on is None and hasattr(canvas, "children"):
            depends_on = _walk_depends(canvas)
        widgets = cls._widgets
        if depends_on:
            for w in depends_on:
                if w not in widgets:
                    return

        # cleanup() is a weakref callback and can run between any two lines below.
        # It drops a widget's dependencies once its sizes are empty,
        # so they are added only after the live canvas keeps the sizes non-empty.
        key = (wcls, size, focus)
        ref = weakref.ref(canvas, cls.cleanup)
        cls._refs[ref] = (widget, wcls, size, focus)
        sizes = widgets.get(widget)
        if sizes is None:
            sizes = widgets[widget] = {key: ref}
        else:
            sizes[key] = ref
        if not depends_on or widgets.get(widget) is not sizes:
            # A cleanup dropped the emptied sizes before ref was added to them: the canvas is not cached.
            return

        cls._children.setdefault(widget, set()).update(depends_on)
        deps = cls._deps
        for w in depends_on:
            deps.setdefault(w, set()).add(widget)
            if widget not in deps.get(w, ()):
                # A cleanup emptied and dropped the set between the lookup and the add.
                deps[w] = {widget}

    @classmethod
    def fetch(
        cls,
        widget: AbstractWidget,
        wcls: type[AbstractWidget],
        size: tuple[int, int] | tuple[int] | tuple[()],
        focus: bool,
    ) -> Canvas | None:
        """
        Return the cached canvas or None.

        :param widget: widget object requested
        :param wcls: widget class that contains render() function
        :param size: size parameter passed to the widget's render method
        :param focus: focus parameter passed to the widget's render method
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
    def invalidate(cls, widget: AbstractWidget) -> None:
        """Remove all canvases cached for widget."""
        sizes = cls._widgets.pop(widget, None)
        if sizes:
            refs = cls._refs
            for ref in sizes.values():
                refs.pop(ref, None)
        cls._forget(widget)

        # The popped set is out of reach of every other frame, so the recursion cannot change it.
        dependants = cls._deps.pop(widget, None)
        if not dependants:
            return
        for w in dependants:
            cls.invalidate(w)

    @classmethod
    def cleanup(cls, ref: weakref.ReferenceType[Canvas]) -> None:
        """Drop the cache entry for a canvas weakref once the canvas it points to has been garbage collected."""
        cls.cleanups += 1  # collect stats

        w = cls._refs.pop(ref, None)
        if not w:
            return
        widget, wcls, size, focus = w
        key = (wcls, size, focus)
        sizes = cls._widgets.get(widget, None)
        # A later store() for the same key replaced ref: that entry belongs to a live canvas.
        if not sizes or sizes.get(key) is not ref:
            return
        sizes.pop(key, None)
        if not sizes:
            cls._widgets.pop(widget, None)
            # Dependants still cached under another key must not keep this widget alive through _children.
            children = cls._children
            for dependant in cls._deps.pop(widget, ()):
                siblings = children.get(dependant)
                if siblings is not None:
                    siblings.discard(widget)
            cls._forget(widget)

    @classmethod
    def _forget(cls, widget: AbstractWidget) -> None:
        """Remove *widget* from the dependants of every widget its cached canvases depended on."""
        # Iterate the popped set: no other frame can reach it, so a nested cleanup() cannot change it.
        children = cls._children.pop(widget, None)
        if not children:
            return
        deps = cls._deps
        for child in children:
            dependants = deps.get(child)
            if dependants is not None:
                dependants.discard(widget)
                if not dependants:
                    deps.pop(child, None)

    @classmethod
    def clear(cls) -> None:
        """Empty the cache."""
        cls._widgets = {}
        cls._refs = {}
        cls._deps = {}
        cls._children = {}


class CanvasError(Exception):
    """Raised for errors in canvas content or canvas cache management."""


class Canvas:
    """base class for canvases."""

    __slots__ = ("__dict__", "__weakref__", "_widget_info", "coords", "shortcuts")

    cacheable = True

    # A message rather than a shared exception: re-raising one instance chains every traceback onto it,
    # and those frames keep the canvases and widgets of every failed call alive.
    _finalized_message: typing.ClassVar[str] = (
        "This canvas has been finalized. Use CompositeCanvas to wrap this canvas if you need to make changes."
    )

    def __init__(self) -> None:
        """Initialize the base canvas state shared by all canvas subclasses."""
        self._widget_info: tuple[AbstractWidget, tuple[()] | tuple[int] | tuple[int, int], bool] | None = None
        self.coords: _CanvasCoords = {}
        self.shortcuts: dict[str, str] = {}

    def finalize(
        self,
        widget: AbstractWidget,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool,
    ) -> None:
        """Mark this canvas as finalized (should not be any future changes to its content).

        This is required before caching the canvas.  This happens automatically after a widget's
        'render call returns the canvas thanks to some metaclass magic.

        :param widget: widget that rendered this canvas
        :param size: size parameter passed to widget's render method
        :param focus: focus parameter passed to widget's render method
        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info:
            raise CanvasError(self._finalized_message)
        self._widget_info = widget, size, focus

    @property
    def widget_info(self) -> tuple[AbstractWidget, tuple[()] | tuple[int] | tuple[int, int], bool] | None:
        """Return the ``(widget, size, focus)`` this canvas was finalized with, or ``None`` if not yet finalized."""
        return self._widget_info

    @property
    def text(self) -> list[bytes]:
        """Return the text content of the canvas as a list of strings, one for each row."""
        return [b"".join(text for (attr, cs, text) in row) for row in self.content()]

    @property
    def decoded_text(self) -> Sequence[str]:
        """Decoded text content of the canvas as a sequence of strings, one for each row."""
        encoding = get_encoding()
        return tuple(line.decode(encoding) for line in self.text)

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """
        Return the canvas content as a list of rows of ``(attr, cs, text)`` tuples.

        :raises NotImplementedError: the subclass does not implement the canvas content protocol.
        """
        raise NotImplementedError()

    def cols(self) -> int:
        """
        Return the screen column width of this canvas.

        :raises NotImplementedError: the subclass does not report its own width.
        """
        raise NotImplementedError()

    def rows(self) -> int:
        """
        Return the screen row height of this canvas.

        :raises NotImplementedError: the subclass does not report its own height.
        """
        raise NotImplementedError()

    def get_cursor(self) -> tuple[int, int] | None:
        """Return the cursor position as ``(x, y)``, or ``None`` if no cursor is set."""
        if c := self.coords.get("cursor", None):
            return c[:2]  # trim off data part

        return None

    def set_cursor(self, c: tuple[int, int] | None) -> None:
        """
        Set the cursor position to ``(x, y)``, or remove it when *c* is ``None``.

        :raises CanvasError: this canvas has already been finalized and can no longer be modified.
        """
        if self.widget_info and self.cacheable:
            raise CanvasError(self._finalized_message)
        if c is None:
            self.coords.pop("cursor", None)
            return
        self.coords["cursor"] = (*c, None)  # data part

    cursor = property(get_cursor, set_cursor)

    def get_pop_up(self) -> tuple[int, int, tuple[AbstractWidget, int, int]] | None:
        """Return the pop-up info set on this canvas, or ``None`` if none was set."""
        return self.coords.get("pop up", None)

    def set_pop_up(
        self,
        w: AbstractWidget,
        left: int,
        top: int,
        overlay_width: int,
        overlay_height: int,
    ) -> None:
        """Add pop-up information to the canvas.

        This information is intercepted by a PopUpTarget widget higher in the chain to
        display a pop-up at the given (left, top) position relative to the
        current canvas.

        :param w: widget to use for the pop-up
        :param left: x position for left edge of pop-up >= 0
        :param top: y position for top edge of pop-up >= 0
        :param overlay_width: width of overlay in screen columns > 0
        :param overlay_height: height of overlay in screen rows > 0
        :raises CanvasError: the canvas is already finalised, the position is negative
            or the overlay size is not positive
        """
        if self.widget_info and self.cacheable:
            raise CanvasError(self._finalized_message)

        if left < 0 or top < 0:
            raise CanvasError(f"Pop-up position must not be negative, got left={left!r} and top={top!r}")

        if overlay_width <= 0 or overlay_height <= 0:
            raise CanvasError(
                f"Pop-up size must be positive, "
                f"got overlay_width={overlay_width!r} and overlay_height={overlay_height!r}"
            )

        self.coords["pop up"] = (left, top, (w, overlay_width, overlay_height))

    def translate_coords(self, dx: int, dy: int) -> _CanvasCoords:
        """Return coords shifted by (dx, dy)."""
        d: _CanvasCoords = {}
        for name, (x, y, data) in self.coords.items():  # type: ignore[misc]
            # MyPy issue with expansion of TypedDict
            d[name] = (x + dx, y + dy, data)  # type: ignore[has-type, literal-required]
        return d

    def __repr__(self) -> str:
        """Return a debug representation including the canvas size, cursor, and finalized state."""
        extra = [""]
        with contextlib.suppress(BaseException):
            extra.append(f"cols={self.cols()}")

        with contextlib.suppress(BaseException):
            extra.append(f"rows={self.rows()}")

        if self.cursor:
            extra.append(f"cursor={self.cursor}")

        return f"<{self.__class__.__name__} finalized={bool(self.widget_info)}{' '.join(extra)} at 0x{id(self):X}>"

    def __str__(self) -> str:
        """Return the canvas content decoded to text, one line per row."""
        with contextlib.suppress(BaseException):
            return "\n".join(self.decoded_text)

        return repr(self)


class TextCanvas(Canvas):
    """class for storing rendered text and attributes."""

    def __init__(
        self,
        text: list[bytes] | None = None,
        attr: list[list[tuple[Hashable, int]]] | None = None,
        cs: list[list[tuple[Literal["0", "U"] | None, int]]] | None = None,
        cursor: tuple[int, int] | None = None,
        maxcol: int | None = None,
        check_width: bool = True,
    ) -> None:
        """Build a text canvas from the given lines and attributes.

        :param text: list of strings, one for each line
        :param attr: list of run length encoded attributes for text
        :param cs: list of run length encoded character set for text
        :param cursor: (x,y) of cursor or None
        :param maxcol: screen columns taken by this canvas
        :param check_width: check and fix width of all lines in text
        :raises CanvasError: a line of *text* is not a plain string in the screen encoding, is wider than *maxcol*, or
            has an attribute or character set run extending beyond its text.
        :raises TypeError: *maxcol* is not an integer.
        """
        super().__init__()
        if text is None:
            text = []

        if check_width:
            widths = []
            for t in text:
                if not isinstance(t, bytes):
                    raise CanvasError(
                        "Canvas text must be plain strings encoded in the screen's encoding",
                        repr(text),
                    )
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
        for i, (w, a_row, cs_row) in enumerate(zip(widths, attr, cs, strict=False)):
            if w > maxcol:
                raise CanvasError(
                    f"Canvas text is wider than the maxcol specified:\n"
                    f"maxcol={maxcol!r}\n"
                    f"widths={widths!r}\n"
                    f"text={text!r}\n"
                    f"urwid target encoding={get_encoding()}"
                )
            t = text[i]
            if w < maxcol:
                t += b"".rjust(maxcol - w)
                text[i] = t
            a_gap = len(t) - rle_len(a_row)
            if a_gap < 0:
                raise CanvasError(f"Attribute extends beyond text \n{t!r}\n{a_row!r}")
            if a_gap:
                rle_append_modify(a_row, (None, a_gap))

            cs_gap = len(t) - rle_len(cs_row)
            if cs_gap < 0:
                raise CanvasError(f"Character Set extends beyond text \n{t!r}\n{cs_row!r}")
            if cs_gap:
                rle_append_modify(cs_row, (None, cs_gap))  # type: ignore[arg-type]  # str|None is Hashable

        self._attr = attr
        self._cs = cs
        self.cursor = cursor
        self._text = text
        self._maxcol = maxcol

    def rows(self) -> int:
        """Return the number of rows in this canvas."""
        return len(self._text)

    def cols(self) -> int:
        """Return the screen column width of this canvas."""
        return self._maxcol

    def translated_coords(self, dx: int, dy: int) -> tuple[int, int] | None:
        """Return cursor coords shifted by (dx, dy), or None if there is no cursor."""
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
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """Return the canvas content as a list of rows where each row is a list of (attr, cs, text) tuples.

        trim_left, trim_top, cols, rows may be set by
        CompositeCanvas when rendering a partially obscured
        canvas.

        :raises ValueError: *trim_left* or *trim_top*, together with *cols* or *rows*, selects a region outside this
            canvas.
        """
        maxcol, maxrow = self.cols(), self.rows()
        if not cols:
            cols = maxcol - trim_left
        if not rows:
            rows = maxrow - trim_top

        # a canvas without columns (empty text) has one region only: all of it, zero columns wide
        if not (
            (0 <= trim_left < maxcol and cols > 0 and trim_left + cols <= maxcol) or maxcol == trim_left == cols == 0
        ):
            raise ValueError(trim_left)
        if not ((0 <= trim_top < maxrow) and (rows > 0 and trim_top + rows <= maxrow)):
            raise ValueError(trim_top)

        if trim_top or rows < maxrow:
            text_attr_cs = zip(
                self._text[trim_top : trim_top + rows],
                self._attr[trim_top : trim_top + rows],
                self._cs[trim_top : trim_top + rows],
                strict=False,
            )
        else:
            text_attr_cs = zip(self._text, self._attr, self._cs, strict=False)

        for text, a_row, cs_row in text_attr_cs:
            if trim_left or cols < self._maxcol:
                text, a_row, cs_row = trim_text_attr_cs(  # type: ignore[assignment]  # noqa: PLW2901
                    text,
                    a_row,
                    cs_row,  # type: ignore[arg-type]  # str|None is Hashable
                    trim_left,
                    trim_left + cols,
                )

            attr_cs = typing.cast(
                "list[tuple[tuple[Hashable, Literal['0', 'U'] | None], int]]",
                rle_product(a_row, cs_row),  # type: ignore[arg-type]  # str|None is Hashable
            )
            i = 0
            row = []
            for (a, cs), run in attr_cs:
                if attr:
                    a = attr.get(a, a)  # noqa: PLW2901  # single lookup instead of `in` + `[]`
                row.append((a, cs, text[i : i + run]))
                i += run
            yield row


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
            pass
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
        return len({key for mapping in self._maps for key in mapping})

    def __bool__(self) -> bool:
        """Return whether any map of the chain names an attribute."""
        return any(self._maps)


class BlankCanvas(Canvas):
    """A canvas with nothing on it.

    Only works as part of a composite canvas since it doesn't know its own size.
    """

    __slots__ = ()

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """Return (cols, rows) of spaces with default attributes."""
        def_attr = attr.get(None) if attr else None
        line = [(def_attr, None, b"".rjust(cols))]
        for _ in range(rows):
            yield line  # type: ignore[misc]  # Yes, list is invariant, but we return it

    def cols(self) -> typing.NoReturn:
        """
        Raise :exc:`NotImplementedError`: a BlankCanvas does not know its own size.

        :raises NotImplementedError: a BlankCanvas does not know its own size.
        """
        raise NotImplementedError("BlankCanvas doesn't know its own size!")

    def rows(self) -> typing.NoReturn:
        """
        Raise :exc:`NotImplementedError`: a BlankCanvas does not know its own size.

        :raises NotImplementedError: a BlankCanvas does not know its own size.
        """
        raise NotImplementedError("BlankCanvas doesn't know its own size!")


blank_canvas = BlankCanvas()


class SolidCanvas(Canvas):
    """A canvas filled completely with a single character."""

    def __init__(self, fill_char: str | bytes, cols: int, rows: int) -> None:
        """
        Build a canvas of *cols* by *rows* screen cells, every one holding *fill_char*.

        :raises ValueError: *fill_char* is not exactly one screen column wide.
        """
        super().__init__()
        end, col = calc_text_pos(fill_char, 0, len(fill_char), 1)
        if col != 1:
            raise ValueError(f"Invalid fill_char: {fill_char!r}")
        self._text, cs = apply_target_encoding(fill_char[:end])
        self._cs = cs[0][0]
        self.size = cols, rows
        self.cursor = None

    def cols(self) -> int:
        """Return the screen column width of this canvas."""
        return self.size[0]

    def rows(self) -> int:
        """Return the screen row height of this canvas."""
        return self.size[1]

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int | None = None,
        rows: int | None = None,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """Return the canvas content as rows of ``(attr, cs, text)`` tuples, each row filled with *fill_char*."""
        if cols is None:
            cols = self.size[0]
        if rows is None:
            rows = self.size[1]
        def_attr = attr.get(None) if attr else None

        line = [(def_attr, self._cs, self._text * cols)]
        for _ in range(rows):
            yield line


class CompositeCanvas(Canvas):
    """class for storing a combination of canvases."""

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
            self.shards = []
        elif count is not None:
            self.shards = shards_trim_rows(self.shards, count)

        self.coords = self.translate_coords(0, -top)

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

        self.shards = shards_trim_rows(self.shards, self.rows() - end)

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
            top_rows, top_cviews = shards[0]
            if left > 0:
                new_top_cviews = [(0, 0, left, rows, None, blank_canvas), *top_cviews]
            else:
                new_top_cviews = top_cviews.copy()

            if right > 0:
                new_top_cviews.append((0, 0, right, rows, None, blank_canvas))
            shards = [(top_rows, new_top_cviews), *shards[1:]]

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


def shard_body_row(sbody: list[tuple[int, Iterator[_ContentLine] | None, _CView]]) -> _ContentLine:
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
    sbody: list[tuple[int, Iterator[_ContentLine] | None, _CView]],
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
    shard_tail: list[tuple[int, int, Iterator[_ContentLine] | None, _CView]],
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
                # The shard calculation is inconsistent: this shard's cviews don't add up
                # to the width the previous shard's tail expects to continue into. This is
                # a known open issue (https://github.com/urwid/urwid/issues/340) that we
                # haven't been able to root-cause; rather than raising (crashing the whole
                # app) or silently leaving the row short (a corrupted-looking canvas), pad
                # the unmet gap with blank filler so the canvas stays rectangular.
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
    shards: list[tuple[int, list[_CView]]],
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
    shards: list[tuple[int, list[_CView]]],
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
    shard_tail: list[tuple[int, int, Iterator[_ContentLine] | None, _CView]] = []
    new_shards: list[tuple[int, list[_CView]]] = []
    right = left + cols
    for num_rows, cviews in shards:
        sbody = shard_body(cviews, shard_tail, False, num_rows=num_rows)
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


def shards_join(shard_lists: Iterable[list[tuple[int, list[_CView]]]]) -> list[tuple[int, list[_CView]]]:
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
    children = []
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
    combined_canvas.children = children  # type: ignore[assignment]  # `CompositeCanvas` is subtype of `Canvas`
    return combined_canvas


def CanvasOverlay(top_c: CompositeCanvas, bottom_c: Canvas, left: int, top: int) -> CompositeCanvas:
    """Overlay canvas top_c onto bottom_c at position (left, top)."""
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
        children = [children[focus_item], *children[:focus_item], *children[focus_item + 1 :]]

    joined_canvas.shards = shards_join(shard_lists)
    joined_canvas.children = children  # type: ignore[assignment]  # `CompositeCanvas` is subtype of `Canvas`
    return joined_canvas


# C0 and C1 control characters and DEL, other than TAB and LF, which the layout places,
# and SO and SI, which select the DEC line-drawing character set
_CONTROL_CHARS = "\x00-\x08\x0b-\x0d\x10-\x1f\x7f-\x9f"
_CONTROL_RE = re.compile(f"[{_CONTROL_CHARS}]")
_CONTROL_UTF8_RE = re.compile(rb"[\x00-\x08\x0b-\x0d\x10-\x1f\x7f]|\xc2[\x80-\x9f]")
_DRAWN_RUN_RE = re.compile(f"[^{_CONTROL_CHARS}]+")


def _drawn_ranges(text: str | bytes, start: int, end: int, sc: int) -> list[tuple[int, int]] | None:
    """Return the ranges of text[start:end] to draw so that they take the *sc* screen columns the layout measured.

    The layout measures a segment either with :func:`calc_width`, which takes every escape sequence and control
    character as zero columns, or with :func:`calc_text_pos`, which takes the control characters as zero columns
    and the rest of an escape sequence, such as ``[31m`` after ESC, as printable text.
    Leaving out what the measure that gives *sc* takes as zero columns draws exactly *sc* columns,
    and nothing reaches the display for it to draw as ``?`` or to run as a terminal command.

    :returns: ``None`` to draw the segment unchanged: it has no control character,
        it is a byte string in an encoding that measures every byte as one column, or neither measure gives *sc*.
    """
    if isinstance(text, bytes):
        if get_byte_encoding() != "utf8" or not _CONTROL_UTF8_RE.search(text, start, end):
            return None
        try:
            decoded = text[start:end].decode("utf-8")
        except UnicodeDecodeError:
            return None
        offsets: Sequence[int] = list(
            itertools.accumulate((len(char.encode("utf-8")) for char in decoded), initial=start)
        )
    else:
        if not _CONTROL_RE.search(text, start, end):
            return None
        decoded = text[start:end]
        offsets = range(start, end + 1)

    whole: list[tuple[int, int]] = []
    pos = 0
    for part, is_sequence in wcwidth.iter_sequences(decoded):
        # calc_width keeps the text a sequence displays, such as that of OSC 66 text sizing
        kept = wcwidth.strip_sequences(part) if is_sequence else part
        at = pos + part.rfind(kept)
        whole.extend((at + found.start(), at + found.end()) for found in _DRAWN_RUN_RE.finditer(kept))
        pos += len(part)
    controls_only = [found.span() for found in _DRAWN_RUN_RE.finditer(decoded)]
    for ranges in (whole, controls_only):
        drawn = "".join(decoded[s:e] for s, e in ranges)
        if calc_width(drawn, 0, len(drawn)) == sc:
            return [(offsets[s], offsets[e]) for s, e in ranges]
    return None


@dataclasses.dataclass
class _AttrWalk:
    counter: int = 0  # counter for moving through elements of a
    offset: int = 0  # current offset into text of attr[ak]


def apply_text_layout(
    text: str | bytes,
    attr: list[tuple[Hashable, int]],
    ls: list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]],
    maxcol: int,
) -> TextCanvas:
    """Build a :class:`TextCanvas` by encoding *text* and *attr* according to the line layout *ls*.

    Control characters and escape sequences that the layout measured as zero columns are left out of the canvas,
    so that each line is drawn in the screen columns the layout measured.
    """
    t: list[bytes] = []
    a: list[list[tuple[Hashable, int]]] = []
    c: list[list[tuple[Literal["0", "U"] | None, int]]] = []

    aw = _AttrWalk()

    def arange(start_offs: int, end_offs: int) -> list[tuple[Hashable, int]]:
        """Return an attribute list for the range of text specified."""
        if start_offs < aw.offset:
            aw.counter = 0
            aw.offset = 0
        o: list[tuple[Hashable, int]] = []
        # the loop should run at least once, the '=' part ensures that
        while aw.offset <= end_offs:
            if len(attr) <= aw.counter:
                # run out of attributes
                o.append((None, end_offs - max(start_offs, aw.offset)))
                break
            at, run = attr[aw.counter]
            if aw.offset + run <= start_offs:
                # move forward through attr to find start_offs
                aw.counter += 1
                aw.offset += run
                continue
            if end_offs <= aw.offset + run:
                o.append((at, end_offs - max(start_offs, aw.offset)))
                break
            o.append((at, aw.offset + run - max(start_offs, aw.offset)))
            aw.counter += 1
            aw.offset += run
        return o

    # one search of the whole text spares the search of each segment for text without control characters
    has_control = bool(_CONTROL_UTF8_RE.search(text) if isinstance(text, bytes) else _CONTROL_RE.search(text))

    for line_layout in ls:
        # trim the line to fit within maxcol
        line_layout = trim_line(line_layout, text, 0, maxcol)  # noqa: PLW2901

        line = []
        linea: list[tuple[Hashable, int]] = []
        linec: list[tuple[Literal["0", "U"] | None, int]] = []

        def attrrange(
            start_offs: int,
            end_offs: int,
            destw: int,
            *,
            src: str | bytes = text,
            runs: list[tuple[Hashable, int]] | None = None,
        ) -> None:
            """Add attributes based on attributes between start_offs and end_offs.

            :param src: the text *start_offs* and *end_offs* index, which encodes to *destw* bytes
            :param runs: the attributes of src[start_offs:end_offs], ``None`` to look them up in *attr*
            """
            # pylint: disable=cell-var-from-loop
            if start_offs == end_offs:
                [(at, run)] = arange(start_offs, end_offs)  # pylint: disable=unbalanced-tuple-unpacking
                rle_append_modify(linea, (at, destw))  # noqa: B023
                return
            if runs is None:
                runs = arange(start_offs, end_offs)
            if destw == end_offs - start_offs:
                for at, run in runs:
                    rle_append_modify(linea, (at, run))  # noqa: B023
                return
            # encoded version has different width
            o = start_offs
            for at, run in runs:
                if o + run == end_offs:
                    rle_append_modify(linea, (at, destw))  # noqa: B023
                    return
                tseg = src[o : o + run]
                tseg, cs = apply_target_encoding(tseg)
                segw = rle_len(cs)

                rle_append_modify(linea, (at, segw))  # noqa: B023
                o += run
                destw -= segw

        for seg in line_layout:
            # if seg is None: assert 0, ls
            s = LayoutSegment(seg)
            if s.end:
                offs = typing.cast("int", s.offs)  # s.end is set
                if not has_control or (drawn := _drawn_ranges(text, offs, s.end, s.sc)) is None:
                    tseg, cs = apply_target_encoding(text[offs : s.end])
                    attrrange(offs, s.end, rle_len(cs))
                else:
                    seg_text = typing.cast("str", text[:0]).join(
                        typing.cast("str", text[start:end]) for start, end in drawn
                    )
                    tseg, cs = apply_target_encoding(seg_text)
                    runs: list[tuple[Hashable, int]] = []
                    for start, end in drawn:
                        for run in arange(start, end):
                            rle_append_modify(runs, run)
                    attrrange(0, len(seg_text), rle_len(cs), src=seg_text, runs=runs)
                line.append(tseg)
                rle_join_modify(linec, cs)  # type: ignore[arg-type]
            elif s.text:
                tseg, cs = apply_target_encoding(s.text)
                line.append(tseg)
                attrrange(typing.cast("int", s.offs), typing.cast("int", s.offs), len(tseg))  # s.text is set
                rle_join_modify(linec, cs)  # type: ignore[arg-type]
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
