from __future__ import annotations

import typing
import warnings
from collections.abc import MutableSequence

from urwid.canvas import CanvasOverlay, CompositeCanvas
from urwid.split_repr import remove_defaults

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
from .widget import Widget, WidgetError, WidgetWarning

if typing.TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from typing_extensions import Literal


TopWidget = typing.TypeVar("TopWidget")
BottomWidget = typing.TypeVar("BottomWidget")


class OverlayError(WidgetError):
    """Overlay specific errors."""


class OverlayWarning(WidgetWarning):
    """Overlay specific warnings."""


def _check_widget_subclass(widget: Widget) -> None:
    if not isinstance(widget, Widget):
        obj_class_path = f"{widget.__class__.__module__}.{widget.__class__.__name__}"
        warnings.warn(
            f"{obj_class_path} is not subclass of Widget",
            DeprecationWarning,
            stacklevel=3,
        )


class OverlayOptions(typing.NamedTuple):
    align: Align | Literal[WHSettings.RELATIVE]
    align_amount: int | None
    width_type: WHSettings
    width_amount: int | None
    min_width: int | None
    left: int
    right: int
    valign_type: VAlign | Literal[WHSettings.RELATIVE]
    valign_amount: int | None
    height_type: WHSettings
    height_amount: int | None
    min_height: int | None
    top: int
    bottom: int


class Overlay(Widget, WidgetContainerMixin, WidgetContainerListContentsMixin, typing.Generic[TopWidget, BottomWidget]):
    """Overlay contains two widgets and renders one on top of the other.

    Top widget can be Box, Flow or Fixed.
    Bottom widget should be Box.
    """

    _selectable = True

    _DEFAULT_BOTTOM_OPTIONS = OverlayOptions(
        align=Align.LEFT,
        align_amount=None,
        width_type=WHSettings.RELATIVE,
        width_amount=100,
        min_width=None,
        left=0,
        right=0,
        valign_type=VAlign.TOP,
        valign_amount=None,
        height_type=WHSettings.RELATIVE,
        height_amount=100,
        min_height=None,
        top=0,
        bottom=0,
    )

    def __init__(
        self,
        top_w: TopWidget,
        bottom_w: BottomWidget,
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
        :param top_w: a flow, box or fixed widget to overlay "on top".
        :type top_w: Widget
        :param bottom_w: a box widget to appear "below" previous widget.
        :type bottom_w: Widget
        :param align: alignment, one of ``'left'``, ``'center'``, ``'right'`` or
            (``'relative'``, *percentage* 0=left 100=right)
        :type align: Literal["left", "center", "right"] | tuple[Literal["relative"], int]
        :param width: width type, one of:
            ``'pack'``
              if *top_w* is a fixed widget
            *given width*
              integer number of columns wide
            (``'relative'``, *percentage of total width*)
              make *top_w* width related to container width
        :type width: Literal["pack"] | int | tuple[Literal["relative"], int]
        :param valign: alignment mode, one of ``'top'``, ``'middle'``, ``'bottom'`` or
            (``'relative'``, *percentage* 0=top 100=bottom)
        :type valign: Literal["top", "middle", "bottom"] | tuple[Literal["relative"], int]
        :param height: one of:
            ``'pack'``
              if *top_w* is a flow or fixed widget
            *given height*
              integer number of rows high
            (``'relative'``, *percentage of total height*)
              make *top_w* height related to container height
        :type height: Literal["pack"] | int | tuple[Literal["relative"], int]
        :param min_width: the minimum number of columns for *top_w* when width is not fixed.
        :type min_width: int
        :param min_height: minimum number of rows for *top_w* when height is not fixed.
        :type min_height: int
        :param left: a fixed number of columns to add on the left.
        :type left: int
        :param right: a fixed number of columns to add on the right.
        :type right: int
        :param top: a fixed number of rows to add on the top.
        :type top: int
        :param bottom: a fixed number of rows to add on the bottom.
        :type bottom: int

        Overlay widgets behave similarly to :class:`Padding` and :class:`Filler`
        widgets when determining the size and position of *top_w*. *bottom_w* is
        always rendered the full size available "below" *top_w*.
        """
        super().__init__()

        self.top_w = top_w
        self.bottom_w = bottom_w

        self.set_overlay_parameters(align, width, valign, height, min_width, min_height, left, right, top, bottom)

        _check_widget_subclass(top_w)
        _check_widget_subclass(bottom_w)

    def sizing(self) -> frozenset[Sizing]:
        """Actual widget sizing.

        :returns: Sizing information depends on the top widget sizing and sizing parameters.
        :rtype: frozenset[Sizing]

        Rules:
        * BOX sizing is always supported provided by the bottom widget
        * FLOW sizing is supported if top widget has:
        * * PACK height type and FLOW supported by the TOP widget
        * * BOX supported by TOP widget AND height amount AND height type GIVEN of min_height
        * FIXED sizing is supported if top widget has:
        * * PACK width type and FIXED supported by the TOP widget
        * * width amount and GIVEN width or min_width AND:
        * * * FLOW supported by the TOP widget AND PACK height type
        * * * BOX supported by the TOP widget AND height_amount and GIVEN height or min height
        """
        sizing = {Sizing.BOX}
        top_sizing = self.top_w.sizing()
        if self.width_type == WHSettings.PACK:
            if Sizing.FIXED in top_sizing:
                sizing.add(Sizing.FIXED)
            else:
                warnings.warn(
                    f"Top widget {self.top_w} should support sizing {Sizing.FIXED.upper()} "
                    f"for width type {WHSettings.PACK.upper()}",
                    OverlayWarning,
                    stacklevel=3,
                )

        elif self.height_type == WHSettings.PACK:
            if Sizing.FLOW in top_sizing:
                sizing.add(Sizing.FLOW)

                if self.width_amount and (self.width_type == WHSettings.GIVEN or self.min_width):
                    sizing.add(Sizing.FIXED)
            else:
                warnings.warn(
                    f"Top widget {self.top_w} should support sizing {Sizing.FLOW.upper()} "
                    f"for height type {self.height_type.upper()}",
                    OverlayWarning,
                    stacklevel=3,
                )

        elif self.height_amount and (self.height_type == WHSettings.GIVEN or self.min_height):
            if Sizing.BOX in top_sizing:
                sizing.add(Sizing.FLOW)
                if self.width_amount and (self.width_type == WHSettings.GIVEN or self.min_width):
                    sizing.add(Sizing.FIXED)
            else:
                warnings.warn(
                    f"Top widget {self.top_w} should support sizing {Sizing.BOX.upper()} "
                    f"for height type {self.height_type.upper()}",
                    OverlayWarning,
                    stacklevel=3,
                )

        return frozenset(sizing)

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int] = (),
        focus: bool = False,
    ) -> tuple[int, int]:
        if size:
            return super().pack(size, focus)

        extra_cols = (self.left or 0) + (self.right or 0)
        extra_rows = (self.top or 0) + (self.bottom or 0)

        if self.width_type == WHSettings.PACK:
            cols, rows = self.top_w.pack((), focus)
            return cols + extra_cols, rows + extra_rows

        if not self.width_amount:
            raise OverlayError(
                f"Requested FIXED render for {self.top_w} with "
                f"width_type={self.width_type.upper()}, "
                f"width_amount={self.width_amount!r}, "
                f"height_type={self.height_type.upper()}, "
                f"height_amount={self.height_amount!r}"
                f"min_width={self.min_width!r}, "
                f"min_height={self.min_height!r}"
            )

        if self.width_type == WHSettings.GIVEN:
            w_cols = self.width_amount
            cols = w_cols + extra_cols
        elif self.width_type == WHSettings.RELATIVE and self.min_width:
            w_cols = self.min_width
            cols = int(w_cols * 100 / self.width_amount + 0.5)
        else:
            raise OverlayError(
                f"Requested FIXED render for {self.top_w} with "
                f"width_type={self.width_type.upper()}, "
                f"width_amount={self.width_amount!r}, "
                f"height_type={self.height_type.upper()}, "
                f"height_amount={self.height_amount!r}"
                f"min_width={self.min_width!r}, "
                f"min_height={self.min_height!r}"
            )

        if self.height_type == WHSettings.PACK:
            return cols, self.top_w.rows((w_cols,), focus) + extra_rows

        if not self.height_amount:
            raise OverlayError(
                f"Requested FIXED render for {self.top_w} with "
                f"width_type={self.width_type.upper()}, "
                f"width_amount={self.width_amount!r}, "
                f"height_type={self.height_type.upper()}, "
                f"height_amount={self.height_amount!r}"
                f"min_width={self.min_width!r}, "
                f"min_height={self.min_height!r}"
            )

        if self.height_type == WHSettings.GIVEN:
            return cols, self.height_amount + extra_rows

        if self.height_type == WHSettings.RELATIVE and self.min_height:
            return cols, int(self.min_height * 100 / self.height_amount + 0.5)

        raise OverlayError(
            f"Requested FIXED render for {self.top_w} with "
            f"width_type={self.width_type.upper()}, "
            f"width_amount={self.width_amount!r}, "
            f"height_type={self.height_type.upper()}, "
            f"height_amount={self.height_amount!r}"
            f"min_width={self.min_width!r}, "
            f"min_height={self.min_height!r}"
        )

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Widget rows amount for FLOW sizing."""
        extra_height = (self.top or 0) + (self.bottom or 0)
        if self.height_type == WHSettings.GIVEN:
            return self.height_amount + extra_height
        if self.height_type == WHSettings.RELATIVE and self.min_height:
            return int(self.min_height * 100 / self.height_amount + 0.5)

        if self.height_type == WHSettings.PACK:
            extra_height = (self.top or 0) + (self.bottom or 0)
            if self.width_type == WHSettings.GIVEN and self.width_amount:
                return self.top_w.rows((self.width_amount,), focus) + extra_height
            if self.width_type == WHSettings.RELATIVE:
                width = max(int(size[0] * self.width_amount / 100 + 0.5), (self.min_width or 0))
                return self.top_w.rows((width,), focus) + extra_height

        raise OverlayError(
            f"Requested rows for {self.top_w} with size {size!r}"
            f"width_type={self.width_type.upper()}, "
            f"width_amount={self.width_amount!r}, "
            f"height_type={self.height_type.upper()}, "
            f"height_amount={self.height_amount!r}"
            f"min_width={self.min_width!r}, "
            f"min_height={self.min_height!r}"
        )

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "top_w": self.top_w,
            "bottom_w": self.bottom_w,
            "align": self.align,
            "width": self.width,
            "valign": self.valign,
            "height": self.height,
            "min_width": self.min_width,
            "min_height": self.min_height,
            "left": self.left,
            "right": self.right,
            "top": self.top,
            "bottom": self.bottom,
        }
        return remove_defaults(attrs, Overlay.__init__)

    def __rich_repr__(self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
        yield "top", self.top_w
        yield "bottom", self.bottom_w
        yield "align", self.align
        yield "width", self.width
        yield "valign", self.valign
        yield "height", self.height
        yield "min_width", self.min_width
        yield "min_height", self.min_height
        yield "left", self.left
        yield "right", self.right
        yield "top", self.top
        yield "bottom", self.bottom

    @property
    def align(self) -> Align | tuple[Literal[WHSettings.RELATIVE], int]:
        return simplify_align(self.align_type, self.align_amount)

    @property
    def width(
        self,
    ) -> (
        Literal[WHSettings.CLIP, WHSettings.PACK]
        | int
        | tuple[Literal[WHSettings.RELATIVE], int]
        | tuple[Literal[WHSettings.WEIGHT], int | float]
    ):
        return simplify_width(self.width_type, self.width_amount)

    @property
    def valign(self) -> VAlign | tuple[Literal[WHSettings.RELATIVE], int]:
        return simplify_valign(self.valign_type, self.valign_amount)

    @property
    def height(
        self,
    ) -> (
        int
        | Literal[WHSettings.FLOW, WHSettings.PACK]
        | tuple[Literal[WHSettings.RELATIVE], int]
        | tuple[Literal[WHSettings.WEIGHT], int | float]
    ):
        return simplify_height(self.height_type, self.height_amount)

    @staticmethod
    def options(
        align_type: Literal["left", "center", "right", "relative", WHSettings.RELATIVE] | Align,
        align_amount: int | None,
        width_type: Literal["clip", "pack", "relative", "given"] | WHSettings,
        width_amount: int | None,
        valign_type: Literal["top", "middle", "bottom", "relative", WHSettings.RELATIVE] | VAlign,
        valign_amount: int | None,
        height_type: Literal["flow", "pack", "relative", "given"] | WHSettings,
        height_amount: int | None,
        min_width: int | None = None,
        min_height: int | None = None,
        left: int = 0,
        right: int = 0,
        top: int = 0,
        bottom: int = 0,
    ) -> OverlayOptions:
        """
        Return a new options tuple for use in this Overlay's .contents mapping.

        This is the common container API to create options for replacing the
        top widget of this Overlay.  It is provided for completeness
        but is not necessarily the easiest way to change the overlay parameters.
        See also :meth:`.set_overlay_parameters`
        """
        if align_type in {Align.LEFT, Align.CENTER, Align.RIGHT}:
            align = Align(align_type)
        elif align_type == WHSettings.RELATIVE:
            align = WHSettings.RELATIVE
        else:
            raise ValueError(f"Unknown alignment type {align_type!r}")

        if valign_type in {VAlign.TOP, VAlign.MIDDLE, VAlign.BOTTOM}:
            valign = VAlign(valign_type)
        elif valign_type == WHSettings.RELATIVE:
            valign = WHSettings.RELATIVE
        else:
            raise ValueError(f"Unknown vertical alignment type {valign_type!r}")

        return OverlayOptions(
            align,
            align_amount,
            WHSettings(width_type),
            width_amount,
            min_width,
            left,
            right,
            valign,
            valign_amount,
            WHSettings(height_type),
            height_amount,
            min_height,
            top,
            bottom,
        )

    def set_overlay_parameters(
        self,
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
        Adjust the overlay size and position parameters.

        See :class:`__init__() <Overlay>` for a description of the parameters.
        """

        # convert obsolete parameters 'fixed ...':
        if isinstance(align, tuple):
            if align[0] == "fixed left":
                left = align[1]
                normalized_align = Align.LEFT
            elif align[0] == "fixed right":
                right = align[1]
                normalized_align = Align.RIGHT
            else:
                normalized_align = align
        else:
            normalized_align = Align(align)

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
                normalized_valign = VAlign.TOP
            elif valign[0] == "fixed bottom":
                bottom = valign[1]
                normalized_valign = VAlign.BOTTOM
            else:
                normalized_valign = valign

        elif not isinstance(valign, (VAlign, str)):
            raise OverlayError(f"invalid valign: {valign!r}")

        else:
            normalized_valign = VAlign(valign)

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

        align_type, align_amount = normalize_align(normalized_align, OverlayError)
        width_type, width_amount = normalize_width(width, OverlayError)
        valign_type, valign_amount = normalize_valign(normalized_valign, OverlayError)
        height_type, height_amount = normalize_height(height, OverlayError)

        if height_type in {WHSettings.GIVEN, WHSettings.PACK}:
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

    def keypress(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        key: str,
    ) -> str | None:
        """Pass keypress to top_w."""
        real_size = self.pack(size, True)
        return self.top_w.keypress(
            self.top_w_size(real_size, *self.calculate_padding_filler(real_size, True)),
            key,
        )

    @property
    def focus(self) -> TopWidget:
        """
        Read-only property returning the child widget in focus for
        container widgets.  This default implementation
        always returns ``None``, indicating that this widget has no children.
        """
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

    @property
    def contents(self) -> MutableSequence[tuple[TopWidget | BottomWidget, OverlayOptions]]:
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

        # noinspection PyMethodParameters
        class OverlayContents(
            MutableSequence[
                tuple[
                    typing.Union[TopWidget, BottomWidget],
                    OverlayOptions,
                ]
            ]
        ):
            # pylint: disable=no-self-argument
            def __len__(inner_self) -> int:
                return 2

            __getitem__ = self._contents__getitem__
            __setitem__ = self._contents__setitem__

            def __delitem__(self, index: int | slice) -> typing.NoReturn:
                raise TypeError("OverlayContents is fixed-sized sequence")

            def insert(self, index: int | slice, value: typing.Any) -> typing.NoReturn:
                raise TypeError("OverlayContents is fixed-sized sequence")

            def __repr__(inner_self) -> str:
                return repr(f"<{inner_self.__class__.__name__}({[inner_self[0], inner_self[1]]})> for {self}")

            def __rich_repr__(inner_self) -> Iterator[tuple[str | None, typing.Any] | typing.Any]:
                for val in inner_self:
                    yield None, val

            def __iter__(inner_self) -> Iterator[tuple[Widget, OverlayOptions]]:
                for idx in range(2):
                    yield inner_self[idx]

        return OverlayContents()

    @contents.setter
    def contents(self, new_contents: Sequence[tuple[width, OverlayOptions]]) -> None:
        if len(new_contents) != 2:
            raise ValueError("Contents length for overlay should be only 2")
        self.contents[0] = new_contents[0]
        self.contents[1] = new_contents[1]

    def _contents__getitem__(
        self,
        index: Literal[0, 1],
    ) -> tuple[TopWidget | BottomWidget, OverlayOptions]:
        if index == 0:
            return (self.bottom_w, self._DEFAULT_BOTTOM_OPTIONS)

        if index == 1:
            return (
                self.top_w,
                OverlayOptions(
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

    def _contents__setitem__(
        self,
        index: Literal[0, 1],
        value: tuple[TopWidget | BottomWidget, OverlayOptions],
    ) -> None:
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
            valign_type, valign_amount = normalize_valign(simplify_valign(valign_type, valign_amount), OverlayError)
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

    def get_cursor_coords(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
    ) -> tuple[int, int] | None:
        """Return cursor coords from top_w, if any."""
        if not hasattr(self.top_w, "get_cursor_coords"):
            return None
        real_size = self.pack(size, True)
        (maxcol, maxrow) = real_size
        left, right, top, bottom = self.calculate_padding_filler(real_size, True)
        x, y = self.top_w.get_cursor_coords((maxcol - left - right, maxrow - top - bottom))
        if y >= maxrow:  # required??
            y = maxrow - 1
        return x + left, y + top

    def calculate_padding_filler(
        self,
        size: tuple[int, int],
        focus: bool,
    ) -> tuple[int, int, int, int]:
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

    def top_w_size(
        self,
        size: tuple[int, int],
        left: int,
        right: int,
        top: int,
        bottom: int,
    ) -> tuple[()] | tuple[int] | tuple[int, int]:
        """Return the size to pass to top_w."""
        if self.width_type == WHSettings.PACK:
            # top_w is a fixed widget
            return ()
        maxcol, maxrow = size
        if self.width_type != WHSettings.PACK and self.height_type == WHSettings.PACK:
            # top_w is a flow widget
            return (maxcol - left - right,)
        return (maxcol - left - right, maxrow - top - bottom)

    def render(self, size: tuple[()] | tuple[int] | tuple[int, int], focus: bool = False) -> CompositeCanvas:
        """Render top_w overlayed on bottom_w."""
        real_size = self.pack(size, focus)

        left, right, top, bottom = self.calculate_padding_filler(real_size, focus)
        bottom_c = self.bottom_w.render(real_size)
        if not bottom_c.cols() or not bottom_c.rows():
            return CompositeCanvas(bottom_c)

        top_c = self.top_w.render(self.top_w_size(real_size, left, right, top, bottom), focus)
        top_c = CompositeCanvas(top_c)
        if left < 0 or right < 0:
            top_c.pad_trim_left_right(min(0, left), min(0, right))
        if top < 0 or bottom < 0:
            top_c.pad_trim_top_bottom(min(0, top), min(0, bottom))

        return CanvasOverlay(top_c, bottom_c, left, top)

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass event to top_w, ignore if outside of top_w."""
        if not hasattr(self.top_w, "mouse_event"):
            return False

        real_size = self.pack(size, focus)

        left, right, top, bottom = self.calculate_padding_filler(real_size, focus)
        maxcol, maxrow = real_size
        if col < left or col >= maxcol - right or row < top or row >= maxrow - bottom:
            return False

        return self.top_w.mouse_event(
            self.top_w_size(real_size, left, right, top, bottom),
            event,
            button,
            col - left,
            row - top,
            focus,
        )
