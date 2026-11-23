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


"""Canvas base class, the canvas error, and the blank and solid canvases."""

from __future__ import annotations

import contextlib
import math
import typing

from urwid.str_util import calc_text_pos
from urwid.util import (
    apply_target_encoding,
    get_encoding,
)

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
    from typing import Literal, NotRequired

    from urwid.widget import AbstractWidget
    from urwid.widget.constants import Align, VAlign, WHSettings

    # A pop-up dimension: a number of screen cells, a percentage of the space from the pop-up's edge to the far
    # edge of the PopUpTarget, or the pop-up widget's own size.
    PopUpSize = int | tuple[Literal["relative", WHSettings.RELATIVE], float] | Literal["pack", WHSettings.PACK]
    # A pop-up position on one axis: an offset from the launcher, or an alignment inside the PopUpTarget.
    PopUpLeft = int | Literal["left", "center", "right", Align.LEFT, Align.CENTER, Align.RIGHT]
    PopUpTop = int | Literal["top", "middle", "bottom", VAlign.TOP, VAlign.MIDDLE, VAlign.BOTTOM]
    # Callback that offers a key a pop-up left unhandled to the widgets under it, see CompositeCanvas.set_pop_up.
    PopUpPassKey = Callable[[str, Callable[[str], str | None]], str | None]

    _ContentLine = list[tuple[Hashable, Literal["0", "U"] | None, bytes]]
    _CView = tuple[int, int, int, int, Mapping[Hashable, Hashable] | None, "Canvas"]

    _CanvasCoords = typing.TypedDict(
        "_CanvasCoords",
        {
            "pop up": NotRequired[tuple[int, int, tuple[AbstractWidget, PopUpSize, PopUpSize]]],
            # Same (x, y) as "pop up", so both move together; the data part is the pop-up widget and the anchor height.
            "pop up anchor": NotRequired[tuple[int, int, tuple[AbstractWidget, int]]],
            # Same (x, y) as "pop up"; the data part is the pop-up widget, the anchor width, the anchor side and the
            # callback told the side the anchor ended up on.
            "pop up anchor width": NotRequired[
                tuple[
                    int,
                    int,
                    tuple[
                        AbstractWidget,
                        int,
                        Literal["left", "right"],
                        Callable[[Literal["left", "right"]], None] | None,
                    ],
                ]
            ],
            # Same (x, y) as "pop up"; the data part is the pop-up widget and its unhandled key callback.
            "pop up unhandled key": NotRequired[tuple[int, int, tuple[AbstractWidget, Callable[[str], str | None]]]],
            # Same (x, y) as "pop up"; the data part is the pop-up widget and its callback for keys passed below it.
            "pop up pass key below": NotRequired[tuple[int, int, tuple[AbstractWidget, PopUpPassKey]]],
            # Same (x, y) as "pop up"; the data part is the pop-up widget and its outside click callback.
            "pop up click outside": NotRequired[tuple[int, int, tuple[AbstractWidget, Callable[[], None]]]],
            # Same (x, y) as "pop up"; the data part is the pop-up widget and its (columns, rows) margin.
            "pop up margin": NotRequired[tuple[int, int, tuple[AbstractWidget, int, int]]],
            # Same (x, y) as "pop up"; the data part is the pop-up widget and its alignments, None for an offset.
            "pop up align": NotRequired[tuple[int, int, tuple[AbstractWidget, str | None, str | None]]],
            "cursor": NotRequired[tuple[int, int, None]],
        },
    )


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
        """Return the text content of the canvas as a list of byte strings in the screen encoding, one for each row."""
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
        raise NotImplementedError

    def cols(self) -> int:
        """
        Return the screen column width of this canvas.

        :raises NotImplementedError: the subclass does not report its own width.
        """
        raise NotImplementedError

    def rows(self) -> int:
        """
        Return the screen row height of this canvas.

        :raises NotImplementedError: the subclass does not report its own height.
        """
        raise NotImplementedError

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

    def get_pop_up(self) -> tuple[int, int, tuple[AbstractWidget, PopUpSize, PopUpSize]] | None:
        """Return the pop-up info set on this canvas, or ``None`` if none was set."""
        return self.coords.get("pop up", None)

    def get_pop_up_anchor_height(self) -> int | None:
        """Return the anchor height set with the pop-up on this canvas, or ``None`` if none was set."""
        pop_up = self.coords.get("pop up", None)
        anchor = self.coords.get("pop up anchor", None)
        # A merged canvas can hold the anchor of one pop-up and the position of another, even at the same
        # coordinates: use only the anchor set together with this pop-up.
        if pop_up is None or anchor is None or anchor[:2] != pop_up[:2] or anchor[2][0] is not pop_up[2][0]:
            return None
        return anchor[2][1]

    def get_pop_up_anchor_width(self) -> tuple[int, Literal["left", "right"]] | None:
        """Return the horizontal anchor set with the pop-up on this canvas.

        :returns: ``(anchor_width, anchor_side)`` as given to :meth:`CompositeCanvas.set_pop_up`,
            or ``None`` when the pop-up was set without `anchor_width` or no pop-up was set.
        """
        pop_up = self.coords.get("pop up", None)
        anchor = self.coords.get("pop up anchor width", None)
        # As for the callbacks, use only the anchor set together with this pop-up.
        if pop_up is None or anchor is None or anchor[:2] != pop_up[:2] or anchor[2][0] is not pop_up[2][0]:
            return None
        return anchor[2][1], anchor[2][2]

    def get_pop_up_on_anchor_side(self) -> Callable[[Literal["left", "right"]], None] | None:
        """Return the callback set with the pop-up on this canvas to learn which side of it the anchor ended up on.

        :returns: the `on_anchor_side` callback given to :meth:`CompositeCanvas.set_pop_up`,
            or ``None`` when none was set or no pop-up was set.
        """
        pop_up = self.coords.get("pop up", None)
        anchor = self.coords.get("pop up anchor width", None)
        # As for the anchor itself, use only the callback set together with this pop-up.
        if pop_up is None or anchor is None or anchor[:2] != pop_up[:2] or anchor[2][0] is not pop_up[2][0]:
            return None
        return anchor[2][3]

    def get_pop_up_unhandled_key(self) -> Callable[[str], str | None] | None:
        """Return the unhandled key callback set with the pop-up on this canvas, or ``None`` if none was set."""
        pop_up = self.coords.get("pop up", None)
        on_key = self.coords.get("pop up unhandled key", None)
        # As for the anchor, use only the callback set together with this pop-up.
        if pop_up is None or on_key is None or on_key[:2] != pop_up[:2] or on_key[2][0] is not pop_up[2][0]:
            return None
        return on_key[2][1]

    def get_pop_up_pass_key_below(self) -> PopUpPassKey | None:
        """Return the callback for keys passed below the pop-up set on this canvas, or ``None`` if none was set."""
        pop_up = self.coords.get("pop up", None)
        pass_key = self.coords.get("pop up pass key below", None)
        # As for the anchor, use only the callback set together with this pop-up.
        if pop_up is None or pass_key is None or pass_key[:2] != pop_up[:2] or pass_key[2][0] is not pop_up[2][0]:
            return None
        return pass_key[2][1]

    def get_pop_up_click_outside(self) -> Callable[[], None] | None:
        """Return the outside click callback set with the pop-up on this canvas.

        :returns: the callback, or ``None`` when none was set.
        """
        pop_up = self.coords.get("pop up", None)
        on_click = self.coords.get("pop up click outside", None)
        # As for the anchor, use only the callback set together with this pop-up.
        if pop_up is None or on_click is None or on_click[:2] != pop_up[:2] or on_click[2][0] is not pop_up[2][0]:
            return None
        return on_click[2][1]

    def get_pop_up_align(self) -> tuple[str | None, str | None]:
        """Return the horizontal and vertical alignments set with the pop-up on this canvas.

        :returns: the ``left`` and ``top`` alignments given to :meth:`CompositeCanvas.set_pop_up`, as strings;
            ``None`` for an axis given as an offset, and ``(None, None)`` when no pop-up was set.
        """
        pop_up = self.coords.get("pop up", None)
        align = self.coords.get("pop up align", None)
        # As for the anchor, use only the alignment set together with this pop-up.
        if pop_up is None or align is None or align[:2] != pop_up[:2] or align[2][0] is not pop_up[2][0]:
            return None, None
        return align[2][1], align[2][2]

    def get_pop_up_margin(self) -> tuple[int, int] | None:
        """Return the margin set with the pop-up on this canvas.

        :returns: the ``(columns, rows)`` `margin` given to :meth:`CompositeCanvas.set_pop_up`,
            or ``None`` when the pop-up was set without a margin or no pop-up was set.
        """
        pop_up = self.coords.get("pop up", None)
        margin = self.coords.get("pop up margin", None)
        # As for the anchor, use only the margin set together with this pop-up.
        if pop_up is None or margin is None or margin[:2] != pop_up[:2] or margin[2][0] is not pop_up[2][0]:
            return None
        return margin[2][1], margin[2][2]

    def set_pop_up(
        self,
        w: AbstractWidget,
        left: PopUpLeft,
        top: PopUpTop,
        overlay_width: PopUpSize,
        overlay_height: PopUpSize,
        *,
        anchor_height: int | None = None,
        anchor_width: int | None = None,
        anchor_side: Literal["left", "right"] = "left",
        on_anchor_side: Callable[[Literal["left", "right"]], None] | None = None,
        on_unhandled_key: Callable[[str], str | None] | None = None,
        pass_key_below: PopUpPassKey | None = None,
        on_click_outside: Callable[[], None] | None = None,
        margin: tuple[int, int] | None = None,
    ) -> None:
        """Add pop-up information to the canvas.

        This information is intercepted by a PopUpTarget widget higher in the chain to
        display a pop-up at the given (left, top) position relative to the
        current canvas.

        A negative position opens the pop-up to the left of or above this canvas, for example over a launcher
        with the current item on the launcher's row. A pop-up that would extend past an edge of the
        :class:`PopUpTarget <urwid.PopUpTarget>` is moved, and shrunk when it is larger, to fit inside it.

        An alignment instead of a number places the pop-up inside the whole :class:`PopUpTarget <urwid.PopUpTarget>`,
        wherever this canvas is: ``left="center", top="middle"`` centres a dialog on the screen.
        It is applied after the size is known, so it also centres a ``"pack"`` sized pop-up.

        :param w: widget to use for the pop-up
        :param left: x position for left edge of pop-up, may be negative,
            or ``"left"``, ``"center"`` or ``"right"`` to align the pop-up inside the target
        :param top: y position for top edge of pop-up, may be negative,
            or ``"top"``, ``"middle"`` or ``"bottom"`` to align the pop-up inside the target
        :param overlay_width: width of overlay in screen columns > 0, ``("relative", percentage)`` of the columns
            from the pop-up's left edge to the right edge of the :class:`PopUpTarget <urwid.PopUpTarget>`
            (of all its columns when `left` is an alignment), with a percentage > 0,
            or ``"pack"`` for the width of `w` as a fixed widget
        :param overlay_height: height of overlay in screen rows > 0, ``("relative", percentage)`` of the rows
            from the pop-up's top edge to the bottom edge of the :class:`PopUpTarget <urwid.PopUpTarget>`
            (of all its rows when `top` is an alignment), with a percentage > 0,
            or ``"pack"`` for the rows of `w` as a flow widget at the pop-up width
        :param anchor_height: rows of the launcher directly above the pop-up, >= 0, or ``None`` to place the pop-up
            exactly as given. With an anchor, :class:`PopUpTarget <urwid.PopUpTarget>` keeps the pop-up off those
            rows: it goes below them when it fits there, above them when it fits there, and otherwise on the side
            with more rows, with its height clipped to that side. It needs `top` as a number of rows.
        :param anchor_width: columns of the anchor beside the pop-up, >= 0, such as a launcher or the menu that
            opened the pop-up, or ``None`` to place the pop-up exactly as given.
            With an anchor, :class:`PopUpTarget <urwid.PopUpTarget>` keeps the pop-up off those columns,
            by the same rule as for `anchor_height`, with the side `anchor_side` gives preferred.
            It needs `left` as a number of columns: the column of the anchor edge that the pop-up touches on its
            preferred side.
            A relative `overlay_width` is then a percentage of the columns on the preferred side.
        :param anchor_side: the side of the pop-up the anchor is on.
            ``"left"``: the anchor is the `anchor_width` columns before `left`, and the pop-up prefers to start at
            `left`, to the right of the anchor.
            ``"right"``: the anchor is the `anchor_width` columns from `left` on, and the pop-up prefers to end
            just before `left`, to the left of the anchor. It needs `anchor_width`.
        :param on_anchor_side: called by :class:`PopUpTarget <urwid.PopUpTarget>` each time it places the pop-up,
            with the side of the pop-up the anchor ended up on, in the terms of `anchor_side`.
            It differs from `anchor_side` when the pop-up moved to the other side of the anchor.
            A widget that opens a chain of pop-ups, such as submenus, uses it to know which way leads back.
            It needs `anchor_width`.
        :param on_unhandled_key: called by :class:`PopUpTarget <urwid.PopUpTarget>` with a key that `w` returned
            unhandled while it is the topmost open pop-up; it returns ``None`` when it handled the key, or the key
            to pass on. ``None`` passes every unhandled key on.
        :param pass_key_below: called by :class:`PopUpTarget <urwid.PopUpTarget>` with a key that `w` and
            `on_unhandled_key` left unhandled while `w` is the topmost open pop-up,
            and with a function that sends a key to the widgets `w` is drawn over.
            That function returns the key when those widgets leave it unhandled, and ``None`` when they handled it.
            The callback returns the key to pass on, or ``None`` when the key was handled.
            It belongs to the pop-up that was topmost when the key arrived, so it can run after that pop-up closed
            during the same keypress.
            ``None`` passes every such key on without offering it to the widgets under the pop-up.
        :param on_click_outside: called by :class:`PopUpTarget <urwid.PopUpTarget>` instead of passing on a press of
            mouse button 1, 2 or 3 outside `w` while it is the topmost open pop-up.
            ``None`` leaves such a press unhandled.
        :param margin: ``(columns, rows)`` of the :class:`PopUpTarget <urwid.PopUpTarget>` kept clear at each of its
            edges, each >= 0, or ``None`` for no margin.
            The pop-up is at most as large as the target without the margins, whatever its size was given as.
            An alignment places it inside the margins, and a relative size on an aligned axis is a percentage of the
            cells inside them.
            A pop-up placed by a number is not moved; it is shifted only to fit inside the target.
            A margin that would leave no cell inside is reduced until at least one cell is left.
        :raises CanvasError: the canvas is already finalised, the anchor height or width is negative,
            an anchor height is given with an aligned `top`, an anchor width with an aligned `left`,
            `anchor_side` is neither ``"left"`` nor ``"right"``, ``anchor_side="right"`` or `on_anchor_side` is given
            without an anchor width, a position is neither a number nor an alignment of its
            axis, an overlay dimension is not a positive integer, a positive finite percentage or ``"pack"``,
            or `margin` is not a pair of integers >= 0
        """
        if self.widget_info and self.cacheable:
            raise CanvasError(self._finalized_message)

        for position, alignments in ((left, ("left", "center", "right")), (top, ("top", "middle", "bottom"))):
            if not isinstance(position, int) and position not in alignments:
                raise CanvasError(
                    f"Pop-up position must be a number of cells or an alignment, "
                    f"got left={left!r} and top={top!r}; the alignments are {alignments!r}"
                )

        for dimension in (overlay_width, overlay_height):
            if isinstance(dimension, tuple) and len(dimension) == 2 and dimension[0] == "relative":
                valid = isinstance(dimension[1], (int, float)) and math.isfinite(dimension[1]) and dimension[1] > 0
            else:
                valid = dimension == "pack" or (isinstance(dimension, int) and dimension > 0)
            if not valid:
                raise CanvasError(
                    f"Pop-up size must be positive: a number of cells, ('relative', percentage) or 'pack', "
                    f"got overlay_width={overlay_width!r} and overlay_height={overlay_height!r}"
                )

        if anchor_height is not None and anchor_height < 0:
            raise CanvasError(f"Pop-up anchor height must not be negative, got {anchor_height!r}")

        if anchor_height is not None and not isinstance(top, int):
            raise CanvasError(f"Pop-up anchor height needs top as a number of rows, got top={top!r}")

        if anchor_width is not None and anchor_width < 0:
            raise CanvasError(f"Pop-up anchor width must not be negative, got {anchor_width!r}")

        if anchor_width is not None and not isinstance(left, int):
            raise CanvasError(f"Pop-up anchor width needs left as a number of columns, got left={left!r}")

        if anchor_side not in ("left", "right"):
            raise CanvasError(f"Pop-up anchor side must be 'left' or 'right', got {anchor_side!r}")

        if anchor_side == "right" and anchor_width is None:
            raise CanvasError("Pop-up anchor side 'right' needs an anchor width")

        if on_anchor_side is not None and anchor_width is None:
            raise CanvasError("Pop-up on_anchor_side needs an anchor width")

        match margin:
            case None:
                pass
            case (int() as columns, int() as rows) if (
                not isinstance(columns, bool) and not isinstance(rows, bool) and columns >= 0 and rows >= 0
            ):
                pass
            case _:
                raise CanvasError(f"Pop-up margin must be None or a pair of integers >= 0, got {margin!r}")

        # The coordinates are moved with this canvas, so an aligned axis keeps 0 there and its alignment beside it.
        x = left if isinstance(left, int) else 0
        y = top if isinstance(top, int) else 0
        self.coords["pop up"] = (x, y, (w, overlay_width, overlay_height))
        if anchor_height is None:
            self.coords.pop("pop up anchor", None)
        else:
            self.coords["pop up anchor"] = (x, y, (w, anchor_height))
        if anchor_width is None:
            self.coords.pop("pop up anchor width", None)
        else:
            self.coords["pop up anchor width"] = (x, y, (w, anchor_width, anchor_side, on_anchor_side))
        if on_unhandled_key is None:
            self.coords.pop("pop up unhandled key", None)
        else:
            self.coords["pop up unhandled key"] = (x, y, (w, on_unhandled_key))
        if pass_key_below is None:
            self.coords.pop("pop up pass key below", None)
        else:
            self.coords["pop up pass key below"] = (x, y, (w, pass_key_below))
        if on_click_outside is None:
            self.coords.pop("pop up click outside", None)
        else:
            self.coords["pop up click outside"] = (x, y, (w, on_click_outside))
        if margin is None:
            self.coords.pop("pop up margin", None)
        else:
            self.coords["pop up margin"] = (x, y, (w, *margin))
        if isinstance(left, int) and isinstance(top, int):
            self.coords.pop("pop up align", None)
        else:
            self.coords["pop up align"] = (
                x,
                y,
                (w, None if isinstance(left, int) else str(left), None if isinstance(top, int) else str(top)),
            )

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
        line: _ContentLine = [(def_attr, None, b"".rjust(cols))]
        for _ in range(rows):
            yield line

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

    __slots__ = (
        "_cs",
        "_text",
        "size",
    )

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
        self._cs: Literal["0", "U"] | None = cs[0][0]
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

        line: _ContentLine = [(def_attr, self._cs, self._text * cols)]
        for _ in range(rows):
            yield line
