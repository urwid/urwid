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
    WrapMode,
    normalize_align,
    normalize_width,
    simplify_align,
    simplify_width,
)
from .widget_decoration import WidgetDecoration

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from .widget import Widget


class PaddingError(Exception):
    pass


class Padding(WidgetDecoration):
    def __init__(
        self,
        w: Widget,
        align: (
            Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int]
        ) = Align.LEFT,
        width: (
            int
            | Literal["pack", "clip", WHSettings.PACK, WHSettings.CLIP]
            | tuple[Literal["relative", WHSettings.RELATIVE], int]
        ) = RELATIVE_100,
        min_width: int | None = None,
        left: int = 0,
        right: int = 0,
    ):
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
        :type min_width: int

        :param left: a fixed number of columns to pad on the left
        :type left: int

        :param right: a fixed number of columns to pad on the right
        :type right: int

        Clipping Mode: (width= ``'clip'``)
        In clipping mode this padding widget will behave as a flow
        widget and self.original_widget will be treated as a fixed
        widget.  self.original_widget will be clipped to fit
        the available number of columns.  For example if align is
        ``'left'`` then self.original_widget may be clipped on the right.

        >>> from urwid import Divider, Text, BigText, FontRegistry
        >>> size = (7,)
        >>> def pr(w):
        ...     for t in w.render(size).text:
        ...         print(f"|{t.decode('utf-8')}|" )
        >>> pr(Padding(Text(u"Head"), ('relative', 20), 'pack'))
        | Head  |
        >>> pr(Padding(Divider(u"-"), left=2, right=1))
        |  ---- |
        >>> pr(Padding(Divider(u"*"), 'center', 3))
        |  ***  |
        >>> p=Padding(Text(u"1234"), 'left', 2, None, 1, 1)
        >>> p
        <Padding flow widget <Text flow widget '1234'> left=1 right=1 width=2>
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
        if isinstance(align, tuple) and align[0] in ("fixed left", "fixed right"):
            if align[0] == "fixed left":
                left = align[1]
                align = Align.LEFT
            else:
                right = align[1]
                align = Align.RIGHT
        if isinstance(width, tuple) and width[0] in ("fixed left", "fixed right"):
            if width[0] == "fixed left":
                left = width[1]
            else:
                right = width[1]
            width = RELATIVE_100

        # convert old clipping mode width=None to width='clip'
        if width is None:
            width = WrapMode.CLIP

        self.left = left
        self.right = right
        self._align_type, self._align_amount = normalize_align(align, PaddingError)
        self._width_type, self._width_amount = normalize_width(width, PaddingError)
        self.min_width = min_width

    def sizing(self):
        if self._width_type == WrapMode.CLIP:
            return {Sizing.FLOW}
        return self.original_widget.sizing()

    def _repr_attrs(self):
        attrs = dict(
            super()._repr_attrs(),
            align=self.align,
            width=self.width,
            left=self.left,
            right=self.right,
            min_width=self.min_width,
        )
        return remove_defaults(attrs, Padding.__init__)

    @property
    def align(self) -> Literal["left", "center", "right"] | tuple[Literal["relative"], int]:
        """
        Return the padding alignment setting.
        """
        return simplify_align(self._align_type, self._align_amount)

    @align.setter
    def align(self, align: Literal["left", "center", "right"] | tuple[Literal["relative"], int]) -> None:
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
    def width(self) -> Literal["clip", "pack"] | int | tuple[Literal["relative"], int]:
        """
        Return the padding width.
        """
        return simplify_width(self._width_type, self._width_amount)

    @width.setter
    def width(self, width: Literal["clip", "pack"] | int | tuple[Literal["relative"], int]) -> None:
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

    def render(
        self,
        size: tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas:
        left, right = self.padding_values(size, focus)

        maxcol = size[0]
        maxcol -= left + right

        if self._width_type == WrapMode.CLIP:
            canv = self._original_widget.render((), focus)
        else:
            canv = self._original_widget.render((maxcol,) + size[1:], focus)
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

    def padding_values(self, size: tuple[int] | tuple[int, int], focus: bool) -> tuple[int, int]:
        """Return the number of columns to pad on the left and right.

        Override this method to define custom padding behaviour."""
        maxcol = size[0]
        if self._width_type == WrapMode.CLIP:
            width, ignore = self._original_widget.pack((), focus=focus)
            return calculate_left_right_padding(
                maxcol,
                self._align_type,
                self._align_amount,
                WrapMode.CLIP,
                width,
                None,
                self.left,
                self.right,
            )
        if self._width_type == WHSettings.PACK:
            maxwidth = max(maxcol - self.left - self.right, self.min_width or 0)
            (width, ignore) = self._original_widget.pack((maxwidth,), focus=focus)
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

    def rows(self, size, focus=False):
        """Return the rows needed for self.original_widget."""
        (maxcol,) = size
        left, right = self.padding_values(size, focus)
        if self._width_type == WHSettings.PACK:
            pcols, prows = self._original_widget.pack((maxcol - left - right,), focus)
            return prows
        if self._width_type == WrapMode.CLIP:
            fcols, frows = self._original_widget.pack((), focus)
            return frows
        return self._original_widget.rows((maxcol - left - right,), focus=focus)

    def keypress(self, size: tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass keypress to self._original_widget."""
        maxcol = size[0]
        left, right = self.padding_values(size, True)
        maxvals = (maxcol - left - right,) + size[1:]
        return self._original_widget.keypress(maxvals, key)

    def get_cursor_coords(self, size: tuple[int] | tuple[int, int]) -> tuple[int, int] | None:
        """Return the (x,y) coordinates of cursor within self._original_widget."""
        if not hasattr(self._original_widget, "get_cursor_coords"):
            return None
        left, right = self.padding_values(size, True)
        maxcol = size[0]
        maxvals = (maxcol - left - right,) + size[1:]
        if maxvals[0] == 0:
            return None
        coords = self._original_widget.get_cursor_coords(maxvals)
        if coords is None:
            return None
        x, y = coords
        return x + left, y

    def move_cursor_to_coords(
        self,
        size: tuple[int] | tuple[int, int],
        x: int,
        y: int,
    ) -> bool:
        """Set the cursor position with (x,y) coordinates of self._original_widget.

        Returns True if move succeeded, False otherwise.
        """
        if not hasattr(self._original_widget, "move_cursor_to_coords"):
            return True
        left, right = self.padding_values(size, True)
        maxcol = size[0]
        maxvals = (maxcol - left - right,) + size[1:]
        if isinstance(x, int):
            if x < left:
                x = left
            elif x >= maxcol - right:
                x = maxcol - right - 1
            x -= left
        return self._original_widget.move_cursor_to_coords(maxvals, x, y)

    def mouse_event(
        self,
        size: tuple[int] | tuple[int, int],
        event,
        button: int,
        x: int,
        y: int,
        focus: bool,
    ):
        """Send mouse event if position is within self._original_widget."""
        if not hasattr(self._original_widget, "mouse_event"):
            return False

        left, right = self.padding_values(size, focus)
        maxcol = size[0]
        if x < left or x >= maxcol - right:
            return False
        maxvals = (maxcol - left - right,) + size[1:]
        return self._original_widget.mouse_event(maxvals, event, button, x - left, y, focus)

    def get_pref_col(self, size: tuple[int] | tuple[int, int]) -> int | None:
        """Return the preferred column from self._original_widget, or None."""
        if not hasattr(self._original_widget, "get_pref_col"):
            return None

        left, right = self.padding_values(size, True)
        maxcol = size[0]
        maxvals = (maxcol - left - right,) + size[1:]
        x = self._original_widget.get_pref_col(maxvals)
        if isinstance(x, int):
            return x + left
        return x


def calculate_left_right_padding(
    maxcol: int,
    align_type: Literal["left", "center", "right"] | Align,
    align_amount: int,
    width_type: Literal["fixed", "relative", "clip"],
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
        width = int_scale(width_amount, 101, maxwidth + 1)
        if min_width is not None:
            width = max(width, min_width)
    else:
        width = width_amount

    standard_alignments = {Align.LEFT: 0, Align.CENTER: 50, Align.RIGHT: 100}
    align = standard_alignments.get(align_type, align_amount)

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
    if width_type != WrapMode.CLIP and (left < 0 or right < 0):
        left = max(left, 0)
        right = max(right, 0)

    return left, right
