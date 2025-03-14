from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas
from urwid.split_repr import remove_defaults
from urwid.util import int_scale

from .constants import (
    RELATIVE_100,
    Sizing,
    VAlign,
    WHSettings,
    normalize_height,
    normalize_valign,
    simplify_height,
    simplify_valign,
)
from .widget_decoration import WidgetDecoration, WidgetError

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

WrappedWidget = typing.TypeVar("WrappedWidget")


class FillerError(WidgetError):
    pass


class Filler(WidgetDecoration[WrappedWidget]):
    def __init__(
        self,
        body: WrappedWidget,
        valign: (
            Literal["top", "middle", "bottom"] | VAlign | tuple[Literal["relative", WHSettings.RELATIVE], int]
        ) = VAlign.MIDDLE,
        height: (
            int | Literal["pack", WHSettings.PACK] | tuple[Literal["relative", WHSettings.RELATIVE], int] | None
        ) = WHSettings.PACK,
        min_height: int | None = None,
        top: int = 0,
        bottom: int = 0,
    ) -> None:
        """
        :param body: a flow widget or box widget to be filled around (stored as self.original_widget)
        :type body: Widget

        :param valign: one of:
            ``'top'``, ``'middle'``, ``'bottom'``,
            (``'relative'``, *percentage* 0=top 100=bottom)

        :param height: one of:

            ``'pack'``
              if body is a flow widget

            *given height*
              integer number of rows for self.original_widget

            (``'relative'``, *percentage of total height*)
              make height depend on container's height

        :param min_height: one of:

            ``None``
              if no minimum or if body is a flow widget

            *minimum height*
              integer number of rows for the widget when height not fixed

        :param top: a fixed number of rows to fill at the top
        :type top: int
        :param bottom: a fixed number of rows to fill at the bottom
        :type bottom: int

        If body is a flow widget, then height must be ``'pack'`` and *min_height* will be ignored.
        Sizing of the filler will be BOX/FLOW in this case.

        If height is integer, *min_height* will be ignored and sizing of filler will be BOX/FLOW.

        Filler widgets will try to satisfy height argument first by reducing the valign amount when necessary.
        If height still cannot be satisfied it will also be reduced.
        """
        super().__init__(body)

        # convert old parameters to the new top/bottom values
        if isinstance(height, tuple):
            if height[0] == "fixed top":
                if not isinstance(valign, tuple) or valign[0] != "fixed bottom":
                    raise FillerError("fixed top height may only be used with fixed bottom valign")
                top = height[1]
                height = RELATIVE_100
            elif height[0] == "fixed bottom":
                if not isinstance(valign, tuple) or valign[0] != "fixed top":
                    raise FillerError("fixed bottom height may only be used with fixed top valign")
                bottom = height[1]
                height = RELATIVE_100

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
            raise FillerError(f"invalid valign: {valign!r}")

        else:
            normalized_valign = VAlign(valign)

        # convert old flow mode parameter height=None to height='flow'
        if height is None or height == Sizing.FLOW:
            height = WHSettings.PACK

        self.top = top
        self.bottom = bottom
        self.valign_type, self.valign_amount = normalize_valign(normalized_valign, FillerError)
        self.height_type, self.height_amount = normalize_height(height, FillerError)

        if self.height_type not in {WHSettings.GIVEN, WHSettings.PACK}:
            self.min_height = min_height
        else:
            self.min_height = None

    def sizing(self) -> frozenset[Sizing]:
        """Widget sizing.

        Sizing BOX is always supported.
        Sizing FLOW is supported if: FLOW widget (a height type is PACK) or BOX widget with height GIVEN
        """
        sizing: set[Sizing] = {Sizing.BOX}
        if self.height_type in {WHSettings.PACK, WHSettings.GIVEN}:
            sizing.add(Sizing.FLOW)
        return frozenset(sizing)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Flow pack support if FLOW sizing supported."""
        if self.height_type == WHSettings.PACK:
            return self.original_widget.rows(size, focus) + self.top + self.bottom
        if self.height_type == WHSettings.GIVEN:
            return self.height_amount + self.top + self.bottom
        raise FillerError("Method 'rows' not supported for BOX widgets")  # pragma: no cover

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "valign": simplify_valign(self.valign_type, self.valign_amount),
            "height": simplify_height(self.height_type, self.height_amount),
            "top": self.top,
            "bottom": self.bottom,
            "min_height": self.min_height,
        }
        return remove_defaults(attrs, Filler.__init__)

    @property
    def body(self) -> WrappedWidget:
        """backwards compatibility, widget used to be stored as body"""
        warnings.warn(
            "backwards compatibility, widget used to be stored as body. API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    @body.setter
    def body(self, new_body: WrappedWidget) -> None:
        warnings.warn(
            "backwards compatibility, widget used to be stored as body. API will be removed in version 5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = new_body

    def get_body(self) -> WrappedWidget:
        """backwards compatibility, widget used to be stored as body"""
        warnings.warn(
            "backwards compatibility, widget used to be stored as body. API will be removed in version 4.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    def set_body(self, new_body: WrappedWidget) -> None:
        warnings.warn(
            "backwards compatibility, widget used to be stored as body. API will be removed in version 4.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = new_body

    def selectable(self) -> bool:
        """Return selectable from body."""
        return self._original_widget.selectable()

    def filler_values(self, size: tuple[int, int] | tuple[int], focus: bool) -> tuple[int, int]:
        """
        Return the number of rows to pad on the top and bottom.

        Override this method to define custom padding behaviour.
        """
        maxcol, maxrow = self.pack(size, focus)

        if self.height_type == WHSettings.PACK:
            height = self._original_widget.rows((maxcol,), focus=focus)
            return calculate_top_bottom_filler(
                maxrow,
                self.valign_type,
                self.valign_amount,
                WHSettings.GIVEN,
                height,
                None,
                self.top,
                self.bottom,
            )

        return calculate_top_bottom_filler(
            maxrow,
            self.valign_type,
            self.valign_amount,
            self.height_type,
            self.height_amount,
            self.min_height,
            self.top,
            self.bottom,
        )

    def render(
        self,
        size: tuple[int, int] | tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render self.original_widget with space above and/or below."""
        maxcol, maxrow = self.pack(size, focus)
        top, bottom = self.filler_values(size, focus)

        if self.height_type == WHSettings.PACK:
            canv = self._original_widget.render((maxcol,), focus)
        else:
            canv = self._original_widget.render((maxcol, maxrow - top - bottom), focus)
        canv = CompositeCanvas(canv)

        if maxrow and canv.rows() > maxrow and canv.cursor is not None:
            _cx, cy = canv.cursor
            if cy >= maxrow:
                canv.trim(cy - maxrow + 1, maxrow - top - bottom)
        if canv.rows() > maxrow:
            canv.trim(0, maxrow)
            return canv
        canv.pad_trim_top_bottom(top, bottom)
        return canv

    def keypress(
        self,
        size: tuple[int, int] | tuple[()],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Pass keypress to self.original_widget."""
        maxcol, maxrow = self.pack(size, True)
        if self.height_type == WHSettings.PACK:
            return self._original_widget.keypress((maxcol,), key)

        top, bottom = self.filler_values((maxcol, maxrow), True)
        return self._original_widget.keypress((maxcol, maxrow - top - bottom), key)

    def get_cursor_coords(self, size: tuple[int, int] | tuple[int]) -> tuple[int, int] | None:
        """Return cursor coords from self.original_widget if any."""
        maxcol, maxrow = self.pack(size, True)
        if not hasattr(self._original_widget, "get_cursor_coords"):
            return None

        top, bottom = self.filler_values(size, True)
        if self.height_type == WHSettings.PACK:
            coords = self._original_widget.get_cursor_coords((maxcol,))
        else:
            coords = self._original_widget.get_cursor_coords((maxcol, maxrow - top - bottom))
        if not coords:
            return None
        x, y = coords
        if y >= maxrow:
            y = maxrow - 1
        return x, y + top

    def get_pref_col(self, size: tuple[int, int] | tuple[int]) -> int | None:
        """Return pref_col from self.original_widget if any."""
        maxcol, maxrow = self.pack(size, True)
        if not hasattr(self._original_widget, "get_pref_col"):
            return None

        if self.height_type == WHSettings.PACK:
            x = self._original_widget.get_pref_col((maxcol,))
        else:
            top, bottom = self.filler_values(size, True)
            x = self._original_widget.get_pref_col((maxcol, maxrow - top - bottom))

        return x

    def move_cursor_to_coords(self, size: tuple[int, int] | tuple[int], col: int, row: int) -> bool:
        """Pass to self.original_widget."""
        maxcol, maxrow = self.pack(size, True)
        if not hasattr(self._original_widget, "move_cursor_to_coords"):
            return True

        top, bottom = self.filler_values(size, True)
        if row < top or row >= maxcol - bottom:
            return False

        if self.height_type == WHSettings.PACK:
            return self._original_widget.move_cursor_to_coords((maxcol,), col, row - top)
        return self._original_widget.move_cursor_to_coords((maxcol, maxrow - top - bottom), col, row - top)

    def mouse_event(
        self,
        size: tuple[int, int] | tuple[int],  # type: ignore[override]
        event,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass to self.original_widget."""
        maxcol, maxrow = self.pack(size, focus)
        if not hasattr(self._original_widget, "mouse_event"):
            return False

        top, bottom = self.filler_values(size, True)
        if row < top or row >= maxrow - bottom:
            return False

        if self.height_type == WHSettings.PACK:
            return self._original_widget.mouse_event((maxcol,), event, button, col, row - top, focus)
        return self._original_widget.mouse_event((maxcol, maxrow - top - bottom), event, button, col, row - top, focus)


def calculate_top_bottom_filler(
    maxrow: int,
    valign_type: Literal["top", "middle", "bottom", "relative", WHSettings.RELATIVE] | VAlign,
    valign_amount: int,
    height_type: Literal["given", "relative", "clip", WHSettings.GIVEN, WHSettings.RELATIVE, WHSettings.CLIP],
    height_amount: int,
    min_height: int | None,
    top: int,
    bottom: int,
) -> tuple[int, int]:
    """
    Return the amount of filler (or clipping) on the top and
    bottom part of maxrow rows to satisfy the following:

    valign_type -- 'top', 'middle', 'bottom', 'relative'
    valign_amount -- a percentage when align_type=='relative'
    height_type -- 'given', 'relative', 'clip'
    height_amount -- a percentage when width_type=='relative'
        otherwise equal to the height of the widget
    min_height -- a desired minimum width for the widget or None
    top -- a fixed number of rows to fill on the top
    bottom -- a fixed number of rows to fill on the bottom

    >>> ctbf = calculate_top_bottom_filler
    >>> ctbf(15, 'top', 0, 'given', 10, None, 2, 0)
    (2, 3)
    >>> ctbf(15, 'relative', 0, 'given', 10, None, 2, 0)
    (2, 3)
    >>> ctbf(15, 'relative', 100, 'given', 10, None, 2, 0)
    (5, 0)
    >>> ctbf(15, 'middle', 0, 'given', 4, None, 2, 0)
    (6, 5)
    >>> ctbf(15, 'middle', 0, 'given', 18, None, 2, 0)
    (0, 0)
    >>> ctbf(20, 'top', 0, 'relative', 60, None, 0, 0)
    (0, 8)
    >>> ctbf(20, 'relative', 30, 'relative', 60, None, 0, 0)
    (2, 6)
    >>> ctbf(20, 'relative', 30, 'relative', 60, 14, 0, 0)
    (2, 4)
    """
    if height_type == WHSettings.RELATIVE:
        maxheight = max(maxrow - top - bottom, 0)
        height = int_scale(height_amount, 101, maxheight + 1)
        if min_height is not None:
            height = max(height, min_height)
    else:
        height = height_amount

    valign = {VAlign.TOP: 0, VAlign.MIDDLE: 50, VAlign.BOTTOM: 100}.get(valign_type, valign_amount)

    # add the remainder of top/bottom to the filler
    filler = maxrow - height - top - bottom
    bottom += int_scale(100 - valign, 101, filler + 1)
    top = maxrow - height - bottom

    # reduce filler if we are clipping an edge
    if bottom < 0 < top:
        shift = min(top, -bottom)
        top -= shift
        bottom += shift
    elif top < 0 < bottom:
        shift = min(bottom, -top)
        bottom -= shift
        top += shift

    # no negative values for filler at the moment
    top = max(top, 0)
    bottom = max(bottom, 0)

    return top, bottom
