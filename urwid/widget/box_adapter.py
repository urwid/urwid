"""BoxAdapter: a decoration that lets a box widget be used as a flow widget."""

from __future__ import annotations

import typing

from urwid.canvas import CompositeCanvas

from .constants import Sizing
from .widget_decoration import WidgetDecoration, WidgetError

if typing.TYPE_CHECKING:
    from .widget import AbstractBoxWidget


WrappedWidget = typing.TypeVar("WrappedWidget", bound="AbstractBoxWidget")


class BoxAdapterError(WidgetError):
    """BoxAdapter related errors."""


class BoxAdapter(WidgetDecoration[WrappedWidget]):
    """Adapter for using a box widget where a flow widget would usually go."""

    no_cache: typing.ClassVar[list[str]] = ["rows"]

    def __init__(self, box_widget: WrappedWidget, height: int) -> None:
        """
        Create a flow widget that contains a box widget.

        :param box_widget: box widget to wrap
        :param height: number of rows for box widget
        :raises BoxAdapterError: *box_widget* is not a BOX widget.

        >>> from urwid import SolidFill
        >>> BoxAdapter(SolidFill("x"), 5)  # 5-rows of x's
        <BoxAdapter flow widget <SolidFill box widget 'x'> height=5>
        """
        if hasattr(box_widget, "sizing") and Sizing.BOX not in box_widget.sizing():
            raise BoxAdapterError(f"{box_widget!r} is not a box widget")
        super().__init__(box_widget)

        self.height = height

    def _repr_attrs(self) -> dict[str, typing.Any]:
        return {**super()._repr_attrs(), "height": self.height}

    def sizing(self) -> frozenset[Sizing]:
        """Return the sizing modes this widget supports, which is always just FLOW."""
        return frozenset((Sizing.FLOW,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the predetermined height (behave like a flow widget).

        >>> from urwid import SolidFill
        >>> BoxAdapter(SolidFill("x"), 5).rows((20,))
        5
        """
        return self.height

    # The next few functions simply tack-on our height and pass through
    # to self._original_widget
    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        """Return the wrapped box widget's cursor coordinates for *size* at the adapter's height."""
        (maxcol,) = size
        if (get_cursor_coords := getattr(self._original_widget, "get_cursor_coords", None)) is not None:
            return typing.cast("tuple[int, int] | None", get_cursor_coords((maxcol, self.height)))
        return None

    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
        """Move the cursor of the wrapped box widget to ``(col, row)`` for *size* at the adapter's height."""
        (maxcol,) = size
        if (move_cursor_to_coords := getattr(self._original_widget, "move_cursor_to_coords", None)) is not None:
            return typing.cast("bool", move_cursor_to_coords((maxcol, self.height), col, row))
        return True

    def get_pref_col(self, size: tuple[int]) -> int | None:
        """Return the wrapped box widget's preferred cursor column for *size* at the adapter's height."""
        (maxcol,) = size
        if (get_pref_col := getattr(self._original_widget, "get_pref_col", None)) is not None:
            return typing.cast("int | None", get_pref_col((maxcol, self.height)))
        return None

    def keypress(
        self,
        size: tuple[int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """Forward the keypress to the wrapped box widget at *size* and the adapter's height."""
        (maxcol,) = size
        return self._original_widget.keypress((maxcol, self.height), key)

    def mouse_event(
        self,
        size: tuple[int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Forward the mouse event to the wrapped box widget at *size* and the adapter's height."""
        (maxcol,) = size
        if not hasattr(self._original_widget, "mouse_event"):
            return False
        return self._original_widget.mouse_event((maxcol, self.height), event, button, col, row, focus)

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render the wrapped box widget at *size* and the adapter's height."""
        (maxcol,) = size
        canv = CompositeCanvas(self._original_widget.render((maxcol, self.height), focus))
        return canv

    def __getattr__(self, name: str) -> typing.Any:
        """Pass calls to box widget."""
        return getattr(self.original_widget, name)
