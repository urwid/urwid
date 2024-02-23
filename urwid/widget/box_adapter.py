from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas

from .constants import Sizing
from .widget_decoration import WidgetDecoration, WidgetError

WrappedWidget = typing.TypeVar("WrappedWidget")


class BoxAdapterError(WidgetError):
    pass


class BoxAdapter(WidgetDecoration[WrappedWidget]):
    """
    Adapter for using a box widget where a flow widget would usually go
    """

    no_cache: typing.ClassVar[list[str]] = ["rows"]

    def __init__(self, box_widget: WrappedWidget, height: int) -> None:
        """
        Create a flow widget that contains a box widget

        :param box_widget: box widget to wrap
        :type box_widget: Widget
        :param height: number of rows for box widget
        :type height: int

        >>> from urwid import SolidFill
        >>> BoxAdapter(SolidFill(u"x"), 5) # 5-rows of x's
        <BoxAdapter flow widget <SolidFill box widget 'x'> height=5>
        """
        if hasattr(box_widget, "sizing") and Sizing.BOX not in box_widget.sizing():
            raise BoxAdapterError(f"{box_widget!r} is not a box widget")
        super().__init__(box_widget)

        self.height = height

    def _repr_attrs(self) -> dict[str, typing.Any]:
        return {**super()._repr_attrs(), "height": self.height}

    # originally stored as box_widget, keep for compatibility
    @property
    def box_widget(self) -> WrappedWidget:
        warnings.warn(
            "original stored as original_widget, keep for compatibility",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    @box_widget.setter
    def box_widget(self, widget: WrappedWidget) -> None:
        warnings.warn(
            "original stored as original_widget, keep for compatibility",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = widget

    def sizing(self) -> frozenset[Sizing]:
        return frozenset((Sizing.FLOW,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the predetermined height (behave like a flow widget)

        >>> from urwid import SolidFill
        >>> BoxAdapter(SolidFill(u"x"), 5).rows((20,))
        5
        """
        return self.height

    # The next few functions simply tack-on our height and pass through
    # to self._original_widget
    def get_cursor_coords(self, size: tuple[int]) -> int | None:
        (maxcol,) = size
        if not hasattr(self._original_widget, "get_cursor_coords"):
            return None
        return self._original_widget.get_cursor_coords((maxcol, self.height))

    def get_pref_col(self, size: tuple[int]) -> int | None:
        (maxcol,) = size
        if not hasattr(self._original_widget, "get_pref_col"):
            return None
        return self._original_widget.get_pref_col((maxcol, self.height))

    def keypress(
        self,
        size: tuple[int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        (maxcol,) = size
        return self._original_widget.keypress((maxcol, self.height), key)

    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int):
        (maxcol,) = size
        if not hasattr(self._original_widget, "move_cursor_to_coords"):
            return True
        return self._original_widget.move_cursor_to_coords((maxcol, self.height), col, row)

    def mouse_event(
        self,
        size: tuple[int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        (maxcol,) = size
        if not hasattr(self._original_widget, "mouse_event"):
            return False
        return self._original_widget.mouse_event((maxcol, self.height), event, button, col, row, focus)

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        (maxcol,) = size
        canv = CompositeCanvas(self._original_widget.render((maxcol, self.height), focus))
        return canv

    def __getattr__(self, name: str):
        """
        Pass calls to box widget.
        """
        return getattr(self.original_widget, name)
