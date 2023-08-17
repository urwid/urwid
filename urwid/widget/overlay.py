from __future__ import annotations

import typing
import warnings

from urwid.canvas import CanvasOverlay, CompositeCanvas

from .constants import (
    RELATIVE_100,
    Align,
    Sizing,
    VAlign,
    WHSettings,
    WrapMode,
    normalize_align,
    normalize_height,
    normalize_valign,
    normalize_width,
    simplify_align,
    simplify_height,
    simplify_valign,
    simplify_width,
)
from .container import WidgetContainerListContentsMixin, WidgetContainerMixin
from .filler import calculate_top_bottom_filler
from .padding import calculate_left_right_padding
from .widget import Widget

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


class OverlayError(Exception):
    pass


class Overlay(Widget, WidgetContainerMixin, WidgetContainerListContentsMixin):
    """
    Overlay contains two box widgets and renders one on top of the other
    """

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    _DEFAULT_BOTTOM_OPTIONS = (
        Align.LEFT,
        None,
        WHSettings.RELATIVE,
        100,
        None,
        0,
        0,
        VAlign.TOP,
        None,
        WHSettings.RELATIVE,
        100,
        None,
        0,
        0,
    )

    def __init__(
        self,
        top_w: Widget,
        bottom_w: Widget,
        align: (
            Literal["left", "center", "right"]
            | Align
            | tuple[Literal["relative", "fixed left", "fixed right", WHSettings.RELATIVE], int]
        ),
        width: Literal["pack", WHSettings.PACK] | int | tuple[Literal["relative", WHSettings.RELATIVE], int] | None,
        valign: (
            Literal["top", "middle", "bottom"]
            | VAlign
            | tuple[Literal["relative", "fixed top", "fixed bottom", WHSettings.RELATIVE], int]
        ),
        height: Literal["pack", WHSettings.PACK] | int | tuple[Literal["relative", WHSettings.RELATIVE], int] | None,
        min_width: int | None = None,
        min_height: int | None = None,
        left: int = 0,
        right: int = 0,
        top: int = 0,
        bottom: int = 0,
    ) -> None:
        """
        :param top_w: a flow, box or fixed widget to overlay "on top"
        :type top_w: Widget
        :param bottom_w: a box widget to appear "below" previous widget
        :type bottom_w: Widget
        :param align: alignment, one of ``'left'``, ``'center'``, ``'right'`` or
            (``'relative'``, *percentage* 0=left 100=right)
        :type align: str
        :param width: width type, one of:

            ``'pack'``
              if *top_w* is a fixed widget
            *given width*
              integer number of columns wide
            (``'relative'``, *percentage of total width*)
              make *top_w* width related to container width

        :param valign: alignment mode, one of ``'top'``, ``'middle'``, ``'bottom'`` or
            (``'relative'``, *percentage* 0=top 100=bottom)
        :param height: one of:

            ``'pack'``
              if *top_w* is a flow or fixed widget
            *given height*
              integer number of rows high
            (``'relative'``, *percentage of total height*)
              make *top_w* height related to container height
        :param min_width: the minimum number of columns for *top_w* when width
            is not fixed
        :type min_width: int
        :param min_height: minimum number of rows for *top_w* when height
            is not fixed
        :type min_height: int
        :param left: a fixed number of columns to add on the left
        :type left: int
        :param right: a fixed number of columns to add on the right
        :type right: int
        :param top: a fixed number of rows to add on the top
        :type top: int
        :param bottom: a fixed number of rows to add on the bottom
        :type bottom: int

        Overlay widgets behave similarly to :class:`Padding` and :class:`Filler`
        widgets when determining the size and position of *top_w*. *bottom_w* is
        always rendered the full size available "below" *top_w*.
        """
        super().__init__()

        self.top_w = top_w
        self.bottom_w = bottom_w

        self.set_overlay_parameters(align, width, valign, height, min_width, min_height, left, right, top, bottom)

    @staticmethod
    def options(
        align_type: Literal["left", "center", "right", "relative"] | Align,
        align_amount: int | None,
        width_type: Literal["clip", "pack", "relative", "given"] | WHSettings,
        width_amount: int | None,
        valign_type: Literal["top", "middle", "bottom", "relative"] | VAlign,
        valign_amount: int | None,
        height_type: Literal["flow", "pack", "relative", "given"] | WHSettings,
        height_amount: int | None,
        min_width: int | None = None,
        min_height: int | None = None,
        left: int = 0,
        right: int = 0,
        top: int = 0,
        bottom: int = 0,
    ):
        """
        Return a new options tuple for use in this Overlay's .contents mapping.

        This is the common container API to create options for replacing the
        top widget of this Overlay.  It is provided for completeness
        but is not necessarily the easiest way to change the overlay parameters.
        See also :meth:`.set_overlay_parameters`
        """

        return (
            align_type,
            align_amount,
            width_type,
            width_amount,
            min_width,
            left,
            right,
            valign_type,
            valign_amount,
            height_type,
            height_amount,
            min_height,
            top,
            bottom,
        )

    def set_overlay_parameters(
        self,
        align: (
            Literal["left", "center", "right"] | Align | tuple[Literal["relative", "fixed left", "fixed right"], int]
        ),
        width: int | None,
        valign: (
            Literal["top", "middle", "bottom"] | VAlign | tuple[Literal["relative", "fixed top", "fixed bottom"], int]
        ),
        height: int | None,
        min_width: int | None = None,
        min_height: int | None = None,
        left: int = 0,
        right: int = 0,
        top: int = 0,
        bottom: int = 0,
    ):
        """
        Adjust the overlay size and position parameters.

        See :class:`__init__() <Overlay>` for a description of the parameters.
        """

        # convert obsolete parameters 'fixed ...':
        if isinstance(align, tuple):
            if align[0] == "fixed left":
                left = align[1]
                align = Align.LEFT
            elif align[0] == "fixed right":
                right = align[1]
                align = Align.RIGHT
        if isinstance(width, tuple):
            if width[0] == "fixed left":
                left = width[1]
                width = RELATIVE_100
            elif width[0] == "fixed right":
                right = width[1]
                width = RELATIVE_100
        if isinstance(valign, tuple):
            if valign[0] == "fixed top":
                top = valign[1]
                valign = VAlign.TOP
            elif valign[0] == "fixed bottom":
                bottom = valign[1]
                valign = VAlign.BOTTOM
        if isinstance(height, tuple):
            if height[0] == "fixed bottom":
                bottom = height[1]
                height = RELATIVE_100
            elif height[0] == "fixed top":
                top = height[1]
                height = RELATIVE_100

        if width is None:  # more obsolete values accepted
            width = WHSettings.PACK
        if height is None:
            height = WHSettings.PACK

        align_type, align_amount = normalize_align(align, OverlayError)
        width_type, width_amount = normalize_width(width, OverlayError)
        valign_type, valign_amount = normalize_valign(valign, OverlayError)
        height_type, height_amount = normalize_height(height, OverlayError)

        if height_type in (WHSettings.GIVEN, WHSettings.PACK):
            min_height = None

        # use container API to set the parameters
        self.contents[1] = (
            self.top_w,
            self.options(
                align_type,
                align_amount,
                width_type,
                width_amount,
                valign_type,
                valign_amount,
                height_type,
                height_amount,
                min_width,
                min_height,
                left,
                right,
                top,
                bottom,
            ),
        )

    def selectable(self) -> bool:
        """Return selectable from top_w."""
        return self.top_w.selectable()

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        """Pass keypress to top_w."""
        return self.top_w.keypress(self.top_w_size(size, *self.calculate_padding_filler(size, True)), key)

    @property
    def focus(self) -> Widget:
        """
        Read-only property returning the child widget in focus for
        container widgets.  This default implementation
        always returns ``None``, indicating that this widget has no children.
        """
        return self.top_w

    def _get_focus(self) -> Widget:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus` is deprecated, "
            f"please use `{self.__class__.__name__}.focus` property",
            DeprecationWarning,
            stacklevel=3,
        )
        return self.top_w

    @property
    def focus_position(self) -> Literal[1]:
        """
        Return the top widget position (currently always 1).
        """
        return 1

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        Set the widget in focus.  Currently only position 0 is accepted.

        position -- index of child widget to be made focus
        """
        if position != 1:
            raise IndexError(f"Overlay widget focus_position currently must always be set to 1, not {position}")

    def _get_focus_position(self) -> int | None:
        warnings.warn(
            f"method `{self.__class__.__name__}._get_focus_position` is deprecated, "
            f"please use `{self.__class__.__name__}.focus_position` property",
            DeprecationWarning,
            stacklevel=3,
        )
        return 1

    def _set_focus_position(self, position: int) -> None:
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        warnings.warn(
            f"method `{self.__class__.__name__}._set_focus_position` is deprecated, "
            f"please use `{self.__class__.__name__}.focus_position` property",
            DeprecationWarning,
            stacklevel=3,
        )
        if position != 1:
            raise IndexError(f"Overlay widget focus_position currently must always be set to 1, not {position}")

    @property
    def contents(self):
        """
        a list-like object similar to::

            [(bottom_w, bottom_options)),
             (top_w, top_options)]

        This object may be used to read or update top and bottom widgets and
        top widgets's options, but no widgets may be added or removed.

        `top_options` takes the form
        `(align_type, align_amount, width_type, width_amount, min_width, left,
        right, valign_type, valign_amount, height_type, height_amount,
        min_height, top, bottom)`

        bottom_options is always
        `('left', None, 'relative', 100, None, 0, 0,
        'top', None, 'relative', 100, None, 0, 0)`
        which means that bottom widget always covers the full area of the Overlay.
        writing a different value for `bottom_options` raises an
        :exc:`OverlayError`.
        """

        class OverlayContents:
            def __len__(inner_self):
                return 2

            __getitem__ = self._contents__getitem__
            __setitem__ = self._contents__setitem__

        return OverlayContents()

    @contents.setter
    def contents(self, new_contents):
        if len(new_contents) != 2:
            raise ValueError("Contents length for overlay should be only 2")
        self.contents[0] = new_contents[0]
        self.contents[1] = new_contents[1]

    def _contents__getitem__(self, index: Literal[0, 1]):
        if index == 0:
            return (self.bottom_w, self._DEFAULT_BOTTOM_OPTIONS)
        if index == 1:
            return (
                self.top_w,
                (
                    self.align_type,
                    self.align_amount,
                    self.width_type,
                    self.width_amount,
                    self.min_width,
                    self.left,
                    self.right,
                    self.valign_type,
                    self.valign_amount,
                    self.height_type,
                    self.height_amount,
                    self.min_height,
                    self.top,
                    self.bottom,
                ),
            )
        raise IndexError(f"Overlay.contents has no position {index!r}")

    def _contents__setitem__(self, index: Literal[0, 1], value):
        try:
            value_w, value_options = value
        except (ValueError, TypeError) as exc:
            raise OverlayError(f"added content invalid: {value!r}").with_traceback(exc.__traceback__) from exc
        if index == 0:
            if value_options != self._DEFAULT_BOTTOM_OPTIONS:
                raise OverlayError(f"bottom_options must be set to {self._DEFAULT_BOTTOM_OPTIONS!r}")
            self.bottom_w = value_w
        elif index == 1:
            try:
                (
                    align_type,
                    align_amount,
                    width_type,
                    width_amount,
                    min_width,
                    left,
                    right,
                    valign_type,
                    valign_amount,
                    height_type,
                    height_amount,
                    min_height,
                    top,
                    bottom,
                ) = value_options
            except (ValueError, TypeError) as exc:
                raise OverlayError(f"top_options is invalid: {value_options!r}").with_traceback(
                    exc.__traceback__
                ) from exc
            # normalize first, this is where errors are raised
            align_type, align_amount = normalize_align(simplify_align(align_type, align_amount), OverlayError)
            width_type, width_amount = normalize_width(simplify_width(width_type, width_amount), OverlayError)
            valign_type, valign_amoun = normalize_valign(simplify_valign(valign_type, valign_amount), OverlayError)
            height_type, height_amount = normalize_height(simplify_height(height_type, height_amount), OverlayError)
            self.align_type = align_type
            self.align_amount = align_amount
            self.width_type = width_type
            self.width_amount = width_amount
            self.valign_type = valign_type
            self.valign_amount = valign_amount
            self.height_type = height_type
            self.height_amount = height_amount
            self.left = left
            self.right = right
            self.top = top
            self.bottom = bottom
            self.min_width = min_width
            self.min_height = min_height
        else:
            raise IndexError(f"Overlay.contents has no position {index!r}")
        self._invalidate()

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Return cursor coords from top_w, if any."""
        if not hasattr(self.top_w, "get_cursor_coords"):
            return None
        (maxcol, maxrow) = size
        left, right, top, bottom = self.calculate_padding_filler(size, True)
        x, y = self.top_w.get_cursor_coords((maxcol - left - right, maxrow - top - bottom))
        if y >= maxrow:  # required??
            y = maxrow - 1
        return x + left, y + top

    def calculate_padding_filler(self, size: tuple[int, int], focus: bool) -> tuple[int, int, int, int]:
        """Return (padding left, right, filler top, bottom)."""
        (maxcol, maxrow) = size
        height = None
        if self.width_type == WHSettings.PACK:
            width, height = self.top_w.pack((), focus=focus)
            if not height:
                raise OverlayError("fixed widget must have a height")
            left, right = calculate_left_right_padding(
                maxcol,
                self.align_type,
                self.align_amount,
                WrapMode.CLIP,
                width,
                None,
                self.left,
                self.right,
            )
        else:
            left, right = calculate_left_right_padding(
                maxcol,
                self.align_type,
                self.align_amount,
                self.width_type,
                self.width_amount,
                self.min_width,
                self.left,
                self.right,
            )

        if height:
            # top_w is a fixed widget
            top, bottom = calculate_top_bottom_filler(
                maxrow,
                self.valign_type,
                self.valign_amount,
                WHSettings.GIVEN,
                height,
                None,
                self.top,
                self.bottom,
            )
            if maxrow - top - bottom < height:
                bottom = maxrow - top - height
        elif self.height_type == WHSettings.PACK:
            # top_w is a flow widget
            height = self.top_w.rows((maxcol,), focus=focus)
            top, bottom = calculate_top_bottom_filler(
                maxrow,
                self.valign_type,
                self.valign_amount,
                WHSettings.GIVEN,
                height,
                None,
                self.top,
                self.bottom,
            )
            if height > maxrow:  # flow widget rendered too large
                bottom = maxrow - height
        else:
            top, bottom = calculate_top_bottom_filler(
                maxrow,
                self.valign_type,
                self.valign_amount,
                self.height_type,
                self.height_amount,
                self.min_height,
                self.top,
                self.bottom,
            )
        return left, right, top, bottom

    def top_w_size(self, size, left, right, top, bottom):
        """Return the size to pass to top_w."""
        if self.width_type == WHSettings.PACK:
            # top_w is a fixed widget
            return ()
        maxcol, maxrow = size
        if self.width_type != WHSettings.PACK and self.height_type == WHSettings.PACK:
            # top_w is a flow widget
            return (maxcol - left - right,)
        return (maxcol - left - right, maxrow - top - bottom)

    def render(self, size: tuple[int, int], focus: bool = False) -> CompositeCanvas:
        """Render top_w overlayed on bottom_w."""
        left, right, top, bottom = self.calculate_padding_filler(size, focus)
        bottom_c = self.bottom_w.render(size)
        if not bottom_c.cols() or not bottom_c.rows():
            return CompositeCanvas(bottom_c)

        top_c = self.top_w.render(self.top_w_size(size, left, right, top, bottom), focus)
        top_c = CompositeCanvas(top_c)
        if left < 0 or right < 0:
            top_c.pad_trim_left_right(min(0, left), min(0, right))
        if top < 0 or bottom < 0:
            top_c.pad_trim_top_bottom(min(0, top), min(0, bottom))

        return CanvasOverlay(top_c, bottom_c, left, top)

    def mouse_event(self, size: tuple[int, int], event, button: int, col: int, row: int, focus: bool) -> bool | None:
        """Pass event to top_w, ignore if outside of top_w."""
        if not hasattr(self.top_w, "mouse_event"):
            return False

        left, right, top, bottom = self.calculate_padding_filler(size, focus)
        maxcol, maxrow = size
        if col < left or col >= maxcol - right or row < top or row >= maxrow - bottom:
            return False

        return self.top_w.mouse_event(
            self.top_w_size(size, left, right, top, bottom), event, button, col - left, row - top, focus
        )
