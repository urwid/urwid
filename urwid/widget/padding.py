from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas, SolidCanvas
from urwid.split_repr import remove_defaults
from urwid.util import int_scale

from .constants import (
    RELATIVE_100,
    Align,
    Sizing,
    WHSettings,
    normalize_align,
    normalize_width,
    simplify_align,
    simplify_width,
)
from .widget_decoration import WidgetDecoration, WidgetError, WidgetWarning

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Literal

WrappedWidget = typing.TypeVar("WrappedWidget")


class PaddingError(WidgetError):
    """Padding related errors."""


class PaddingWarning(WidgetWarning):
    """Padding related warnings."""


class Padding(WidgetDecoration[WrappedWidget], typing.Generic[WrappedWidget]):
    def __init__(
        self,
        w: WrappedWidget,
        align: (
            Literal["left", "center", "right"]
            | Align
            | tuple[Literal["relative", WHSettings.RELATIVE, "fixed left", "fixed right"], int]
        ) = Align.LEFT,
        width: (
            int
            | Literal["pack", "clip", WHSettings.PACK, WHSettings.CLIP]
            | tuple[Literal["relative", WHSettings.RELATIVE, "fixed left", "fixed right"], int]
        ) = RELATIVE_100,
        min_width: int | None = None,
        left: int = 0,
        right: int = 0,
    ) -> None:
        """
        :param w: a box, flow or fixed widget to pad on the left and/or right
            this widget is stored as self.original_widget
        :type w: Widget

        :param align: one of: ``'left'``, ``'center'``, ``'right'``
            (``'relative'``, *percentage* 0=left 100=right)

        :param width: one of:

            *given width*
              integer number of columns for self.original_widget

            ``'pack'``
              try to pack self.original_widget to its ideal size

            (``'relative'``, *percentage of total width*)
              make width depend on the container's width

            ``'clip'``
              to enable clipping mode for a fixed widget

        :param min_width: the minimum number of columns for
            self.original_widget or ``None``
        :type min_width: int | None

        :param left: a fixed number of columns to pad on the left
        :type left: int

        :param right: a fixed number of columns to pad on the right
        :type right: int

        Clipping Mode: (width= ``'clip'``)
        In clipping mode this padding widget will behave as a flow
        widget and self.original_widget will be treated as a fixed widget.
        self.original_widget will be clipped to fit the available number of columns.
        For example if align is ``'left'`` then self.original_widget may be clipped on the right.

        Pack Mode: (width= ``'pack'``)
        In pack mode is supported FIXED operation if it is supported by the original widget.

        >>> from urwid import Divider, Text, BigText, FontRegistry
        >>> from urwid.util import set_temporary_encoding
        >>> size = (7,)
        >>> def pr(w):
        ...     with set_temporary_encoding("utf-8"):
        ...         for t in w.render(size).text:
        ...             print(f"|{t.decode('utf-8')}|" )
        >>> pr(Padding(Text(u"Head"), ('relative', 20), 'pack'))
        | Head  |
        >>> pr(Padding(Divider(u"-"), left=2, right=1))
        |  ---- |
        >>> pr(Padding(Divider(u"*"), 'center', 3))
        |  ***  |
        >>> p=Padding(Text(u"1234"), 'left', 2, None, 1, 1)
        >>> p
        <Padding fixed/flow widget <Text fixed/flow widget '1234'> left=1 right=1 width=2>
        >>> pr(p)   # align against left
        | 12    |
        | 34    |
        >>> p.align = 'right'
        >>> pr(p)   # align against right
        |    12 |
        |    34 |
        >>> pr(Padding(Text(u"hi\\nthere"), 'right', 'pack')) # pack text first
        |  hi   |
        |  there|
        >>> pr(Padding(BigText("1,2,3", FontRegistry['Thin 3x3']()), width="clip"))
        | ┐  ┌─┐|
        | │  ┌─┘|
        | ┴ ,└─ |
        """
        super().__init__(w)

        # convert obsolete parameters 'fixed left' and 'fixed right':
        if isinstance(align, tuple) and align[0] in {"fixed left", "fixed right"}:
            if align[0] == "fixed left":
                left = align[1]
                align = Align.LEFT
            else:
                right = align[1]
                align = Align.RIGHT
        if isinstance(width, tuple) and width[0] in {"fixed left", "fixed right"}:
            if width[0] == "fixed left":
                left = width[1]
            else:
                right = width[1]
            width = RELATIVE_100

        # convert old clipping mode width=None to width='clip'
        if width is None:
            width = WHSettings.CLIP

        self.left = left
        self.right = right
        self._align_type, self._align_amount = normalize_align(align, PaddingError)
        self._width_type, self._width_amount = normalize_width(width, PaddingError)
        self.min_width = min_width

    def sizing(self) -> frozenset[Sizing]:
        """Widget sizing.

        Rules:
        * width == CLIP: only FLOW is supported, and wrapped widget should support FIXED
        * width == GIVEN: FIXED is supported, and wrapped widget should support FLOW
        * All other cases: use sizing of target widget
        """
        if self._width_type == WHSettings.CLIP:
            return frozenset((Sizing.FLOW,))

        sizing = set(self.original_widget.sizing())
        if self._width_type == WHSettings.GIVEN:
            if Sizing.FLOW in sizing:
                sizing.add(Sizing.FIXED)

            elif Sizing.BOX not in sizing:
                warnings.warn(
                    f"WHSettings.GIVEN expect BOX or FLOW widget to be used, but received {self.original_widget}",
                    PaddingWarning,
                    stacklevel=3,
                )

        return frozenset(sizing)

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "align": self.align,
            "width": self.width,
            "left": self.left,
            "right": self.right,
            "min_width": self.min_width,
        }
        return remove_defaults(attrs, Padding.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        yield "w", self.original_widget
        yield "align", self.align
        yield "width", self.width
        yield "min_width", self.min_width
        yield "left", self.left
        yield "right", self.right

    @property
    def align(
        self,
    ) -> Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int]:
        """
        Return the padding alignment setting.
        """
        return simplify_align(self._align_type, self._align_amount)

    @align.setter
    def align(
        self, align: Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int]
    ) -> None:
        """
        Set the padding alignment.
        """
        self._align_type, self._align_amount = normalize_align(align, PaddingError)
        self._invalidate()

    def _get_align(self) -> Literal["left", "center", "right"] | tuple[Literal["relative"], int]:
        warnings.warn(
            f"Method `{self.__class__.__name__}._get_align` is deprecated, "
            f"please use property `{self.__class__.__name__}.align`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.align

    def _set_align(self, align: Literal["left", "center", "right"] | tuple[Literal["relative"], int]) -> None:
        warnings.warn(
            f"Method `{self.__class__.__name__}._set_align` is deprecated, "
            f"please use property `{self.__class__.__name__}.align`",
            DeprecationWarning,
            stacklevel=2,
        )
        self.align = align

    @property
    def width(
        self,
    ) -> (
        Literal["clip", "pack", WHSettings.CLIP, WHSettings.PACK]
        | int
        | tuple[Literal["relative", WHSettings.RELATIVE], int]
    ):
        """
        Return the padding width.
        """
        return simplify_width(self._width_type, self._width_amount)

    @width.setter
    def width(
        self,
        width: (
            Literal["clip", "pack", WHSettings.CLIP, WHSettings.PACK]
            | int
            | tuple[Literal["relative", WHSettings.RELATIVE], int]
        ),
    ) -> None:
        """
        Set the padding width.
        """
        self._width_type, self._width_amount = normalize_width(width, PaddingError)
        self._invalidate()

    def _get_width(self) -> Literal["clip", "pack"] | int | tuple[Literal["relative"], int]:
        warnings.warn(
            f"Method `{self.__class__.__name__}._get_width` is deprecated, "
            f"please use property `{self.__class__.__name__}.width`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.width

    def _set_width(self, width: Literal["clip", "pack"] | int | tuple[Literal["relative"], int]) -> None:
        warnings.warn(
            f"Method `{self.__class__.__name__}._set_width` is deprecated, "
            f"please use property `{self.__class__.__name__}.width`",
            DeprecationWarning,
            stacklevel=2,
        )
        self.width = width

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        if size:
            return super().pack(size, focus)
        if self._width_type == WHSettings.CLIP:
            raise PaddingError("WHSettings.CLIP makes Padding FLOW-only widget")

        expand = self.left + self.right
        w_sizing = self.original_widget.sizing()

        if self._width_type == WHSettings.GIVEN:
            if Sizing.FLOW not in w_sizing:
                warnings.warn(
                    f"WHSettings.GIVEN expect FLOW widget to be used for FIXED pack/render, "
                    f"but received {self.original_widget}",
                    PaddingWarning,
                    stacklevel=3,
                )

            return (
                max(self._width_amount, self.min_width or 1) + expand,
                self.original_widget.rows((self._width_amount,), focus),
            )

        if Sizing.FIXED not in w_sizing:
            warnings.warn(
                f"Padded widget should support FIXED sizing for FIXED render, but received {self.original_widget}",
                PaddingWarning,
                stacklevel=3,
            )
        width, height = self.original_widget.pack(size, focus)

        if self._width_type == WHSettings.PACK:
            return max(width, self.min_width or 1) + expand, height

        if self._width_type == WHSettings.RELATIVE:
            return max(int(width * 100 / self._width_amount + 0.5), self.min_width or 1) + expand, height

        raise PaddingError(f"Unexpected width type: {self._width_type.upper()})")

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas:
        left, right = self.padding_values(size, focus)

        if self._width_type == WHSettings.CLIP:
            canv = self._original_widget.render((), focus)
        elif size:
            maxcol = size[0] - (left + right)
            if self._width_type == WHSettings.GIVEN and maxcol < self._width_amount:
                warnings.warn(
                    f"{self}.render(size={size}, focus={focus}): too narrow size ({maxcol!r} < {self._width_amount!r})",
                    PaddingWarning,
                    stacklevel=3,
                )
            canv = self._original_widget.render((maxcol,) + size[1:], focus)
        elif self._width_type == WHSettings.GIVEN:
            canv = self._original_widget.render((self._width_amount,) + size[1:], focus)
        else:
            canv = self._original_widget.render((), focus)

        if canv.cols() == 0:
            canv = SolidCanvas(" ", size[0], canv.rows())
            canv = CompositeCanvas(canv)
            canv.set_depends([self._original_widget])
            return canv

        canv = CompositeCanvas(canv)
        canv.set_depends([self._original_widget])
        if left != 0 or right != 0:
            canv.pad_trim_left_right(left, right)

        return canv

    def padding_values(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool,
    ) -> tuple[int, int]:
        """Return the number of columns to pad on the left and right.

        Override this method to define custom padding behaviour."""
        if self._width_type == WHSettings.CLIP:
            width, _ignore = self._original_widget.pack((), focus=focus)
            if not size:
                raise PaddingError("WHSettings.CLIP makes Padding FLOW-only widget")
            return calculate_left_right_padding(
                size[0],
                self._align_type,
                self._align_amount,
                WHSettings.CLIP,
                width,
                None,
                self.left,
                self.right,
            )

        if self._width_type == WHSettings.PACK:
            if size:
                maxcol = size[0]
                maxwidth = max(maxcol - self.left - self.right, self.min_width or 0)
                (width, _ignore) = self._original_widget.pack((maxwidth,), focus=focus)
            else:
                (width, _ignore) = self._original_widget.pack((), focus=focus)
                maxcol = width + self.left + self.right

            return calculate_left_right_padding(
                maxcol,
                self._align_type,
                self._align_amount,
                WHSettings.GIVEN,
                width,
                self.min_width,
                self.left,
                self.right,
            )

        if size:
            maxcol = size[0]
        elif self._width_type == WHSettings.GIVEN:
            maxcol = self._width_amount + self.left + self.right
        else:
            maxcol = (
                max(self._original_widget.pack((), focus=focus)[0] * 100 // self._width_amount, self.min_width or 1)
                + self.left
                + self.right
            )

        return calculate_left_right_padding(
            maxcol,
            self._align_type,
            self._align_amount,
            self._width_type,
            self._width_amount,
            self.min_width,
            self.left,
            self.right,
        )

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the rows needed for self.original_widget."""
        (maxcol,) = size
        left, right = self.padding_values(size, focus)
        if self._width_type == WHSettings.PACK:
            _pcols, prows = self._original_widget.pack((maxcol - left - right,), focus)
            return prows
        if self._width_type == WHSettings.CLIP:
            _fcols, frows = self._original_widget.pack((), focus)
            return frows
        return self._original_widget.rows((maxcol - left - right,), focus=focus)

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass keypress to self._original_widget."""
        left, right = self.padding_values(size, True)
        if size:
            maxvals = (size[0] - left - right,) + size[1:]
            return self._original_widget.keypress(maxvals, key)
        return self._original_widget.keypress((), key)

    def get_cursor_coords(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the (x,y) coordinates of cursor within self._original_widget."""
        if not hasattr(self._original_widget, "get_cursor_coords"):
            return None

        left, right = self.padding_values(size, True)
        if size:
            maxvals = (size[0] - left - right,) + size[1:]
            if maxvals[0] == 0:
                return None
        else:
            maxvals = ()

        coords = self._original_widget.get_cursor_coords(maxvals)
        if coords is None:
            return None

        x, y = coords
        return x + left, y

    def move_cursor_to_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        x: int,
        y: int,
    ) -> bool:
        """Set the cursor position with (x,y) coordinates of self._original_widget.

        Returns True if move succeeded, False otherwise.
        """
        if not hasattr(self._original_widget, "move_cursor_to_coords"):
            return True

        left, right = self.padding_values(size, True)
        if size:
            maxcol = size[0]
            maxvals = (maxcol - left - right,) + size[1:]
        else:
            maxcol = self.pack((), True)[0]
            maxvals = ()

        if isinstance(x, int):
            if x < left:
                x = left
            elif x >= maxcol - right:
                x = maxcol - right - 1
            x -= left

        return self._original_widget.move_cursor_to_coords(maxvals, x, y)

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Send mouse event if position is within self._original_widget."""
        if not hasattr(self._original_widget, "mouse_event"):
            return False

        left, right = self.padding_values(size, focus)
        if size:
            maxcol = size[0]
            if col < left or col >= maxcol - right:
                return False
            maxvals = (maxcol - left - right,) + size[1:]
        else:
            maxvals = ()

        return self._original_widget.mouse_event(maxvals, event, button, col - left, row, focus)

    def get_pref_col(self, size: tuple[()] | tuple[int] | tuple[int, int]) -> int | None:
        """Return the preferred column from self._original_widget, or None."""
        if not hasattr(self._original_widget, "get_pref_col"):
            return None

        left, right = self.padding_values(size, True)
        if size:
            maxvals = (size[0] - left - right,) + size[1:]
        else:
            maxvals = ()

        x = self._original_widget.get_pref_col(maxvals)
        if isinstance(x, int):
            return x + left
        return x


def calculate_left_right_padding(
    maxcol: int,
    align_type: Literal["left", "center", "right"] | Align,
    align_amount: int,
    width_type: Literal["fixed", "relative", "clip", "given", WHSettings.RELATIVE, WHSettings.CLIP, WHSettings.GIVEN],
    width_amount: int,
    min_width: int | None,
    left: int,
    right: int,
) -> tuple[int, int]:
    """
    Return the amount of padding (or clipping) on the left and
    right part of maxcol columns to satisfy the following:

    align_type -- 'left', 'center', 'right', 'relative'
    align_amount -- a percentage when align_type=='relative'
    width_type -- 'fixed', 'relative', 'clip'
    width_amount -- a percentage when width_type=='relative'
        otherwise equal to the width of the widget
    min_width -- a desired minimum width for the widget or None
    left -- a fixed number of columns to pad on the left
    right -- a fixed number of columns to pad on the right

    >>> clrp = calculate_left_right_padding
    >>> clrp(15, 'left', 0, 'given', 10, None, 2, 0)
    (2, 3)
    >>> clrp(15, 'relative', 0, 'given', 10, None, 2, 0)
    (2, 3)
    >>> clrp(15, 'relative', 100, 'given', 10, None, 2, 0)
    (5, 0)
    >>> clrp(15, 'center', 0, 'given', 4, None, 2, 0)
    (6, 5)
    >>> clrp(15, 'left', 0, 'clip', 18, None, 0, 0)
    (0, -3)
    >>> clrp(15, 'right', 0, 'clip', 18, None, 0, -1)
    (-2, -1)
    >>> clrp(15, 'center', 0, 'given', 18, None, 2, 0)
    (0, 0)
    >>> clrp(20, 'left', 0, 'relative', 60, None, 0, 0)
    (0, 8)
    >>> clrp(20, 'relative', 30, 'relative', 60, None, 0, 0)
    (2, 6)
    >>> clrp(20, 'relative', 30, 'relative', 60, 14, 0, 0)
    (2, 4)
    """
    if width_type == WHSettings.RELATIVE:
        maxwidth = max(maxcol - left - right, 0)
        width = int(maxwidth * width_amount / 100 + 0.5)
        if min_width is not None:
            width = max(width, min_width)
    else:
        width = width_amount

    align = {Align.LEFT: 0, Align.CENTER: 50, Align.RIGHT: 100}.get(align_type, align_amount)

    # add the remainder of left/right the padding
    padding = maxcol - width - left - right
    right += int_scale(100 - align, 101, padding + 1)
    left = maxcol - width - right

    # reduce padding if we are clipping an edge
    if right < 0 < left:
        shift = min(left, -right)
        left -= shift
        right += shift
    elif left < 0 < right:
        shift = min(right, -left)
        right -= shift
        left += shift

    # only clip if width_type == 'clip'
    if width_type != WHSettings.CLIP and (left < 0 or right < 0):
        left = max(left, 0)
        right = max(right, 0)

    return left, right
