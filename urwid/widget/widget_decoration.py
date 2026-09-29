"""Base classes for decoration widgets that wrap a single child widget."""

from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas

from .widget import AbstractWidget, Widget, WidgetError, WidgetWarning, delegate_to_widget_mixin

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from .constants import Sizing


__all__ = (
    "WidgetDecoration",
    "WidgetDisable",
    "WidgetError",
    "WidgetPlaceholder",
    "WidgetWarning",
    "delegate_to_widget_mixin",
)

WrappedWidget = typing.TypeVar("WrappedWidget", bound="AbstractWidget")


class WidgetDecoration(Widget, typing.Generic[WrappedWidget]):  # pylint: disable=abstract-method
    """
    Base class for decoration widgets: widgets that contain one or more widgets and only ever have a single focus.

    This type of widget will affect the display or behaviour of the original_widget,
    but it is not part of determining a chain of focus.

    :param original_widget: the widget being decorated

    Don't actually do this - use a WidgetDecoration subclass instead, these are not real widgets:

    >>> from urwid import Text
    >>> WidgetDecoration(Text("hi"))
    <WidgetDecoration fixed/flow widget <Text fixed/flow widget 'hi'>>

    .. warning::
        WidgetDecoration does not implement the ``render`` method.
        Implement it, or forward to the wrapped widget, in the subclass.
    """

    def __init__(self, original_widget: WrappedWidget) -> None:
        super().__init__()
        if not isinstance(original_widget, AbstractWidget):
            obj_class_path = f"{original_widget.__class__.__module__}.{original_widget.__class__.__name__}"
            warnings.warn(
                f"{obj_class_path} is not implementing Widget API",
                DeprecationWarning,
                stacklevel=2,
            )
        self._original_widget = original_widget

    def _repr_words(self) -> list[str]:
        return [*super()._repr_words(), repr(self._original_widget)]

    @property
    def original_widget(self) -> WrappedWidget:
        """Return the widget this decoration wraps."""
        return self._original_widget

    @original_widget.setter
    def original_widget(self, original_widget: WrappedWidget) -> None:
        self._original_widget = original_widget
        self._invalidate()

    @property
    def base_widget(self) -> AbstractWidget:
        """
        Return the widget without decorations.

        If there is only one Decoration, then this is the same as original_widget.

        >>> from urwid import Text
        >>> t = Text("hello")
        >>> wd1 = WidgetDecoration(t)
        >>> wd2 = WidgetDecoration(wd1)
        >>> wd3 = WidgetDecoration(wd2)
        >>> wd3.original_widget is wd2
        True
        >>> wd3.base_widget is t
        True
        """
        visited = {self}
        w = self
        while (w := getattr(w, "_original_widget", w)) not in visited:
            visited.add(w)
        return w

    def selectable(self) -> bool:
        """Return whether the wrapped widget can take the input focus."""
        return self._original_widget.selectable()

    def sizing(self) -> frozenset[Sizing]:
        """Return the set of sizing modes supported by the wrapped widget."""
        return self._original_widget.sizing()


class WidgetPlaceholder(
    delegate_to_widget_mixin("_original_widget"),  # type: ignore[misc]
    WidgetDecoration[WrappedWidget],
):
    """Do-nothing decoration widget that can be used for swapping between widgets.

    Swaps happen without modifying the container of this widget.

    This can be useful for making an interface with a number of distinct
    pages or for showing and hiding menu or status bars.

    The widget displayed is stored as the self.original_widget property and
    can be changed by assigning a new widget to it.
    """


class WidgetDisable(WidgetDecoration[WrappedWidget]):
    """Decoration widget that disables interaction with the widget it wraps.

    This widget always passes focus=False to the wrapped widget, even if it somehow does become the focus.
    """

    no_cache: typing.ClassVar[list[str]] = ["rows"]
    ignore_focus = True

    def selectable(self) -> Literal[False]:
        """Return ``False``: a disabled widget never takes the input focus."""
        return False

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows the wrapped widget occupies, always passing ``focus=False``."""
        # AttributeError is a valid case
        return self._original_widget.rows(size, False)  # type: ignore[attr-defined,no-any-return]

    def sizing(self) -> frozenset[Sizing]:
        """Return the set of sizing modes supported by the wrapped widget."""
        return self._original_widget.sizing()

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the size required by the wrapped widget, always passing ``focus=False``."""
        return self._original_widget.pack(size, False)

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render the wrapped widget into a canvas, always passing ``focus=False``."""
        canv = self._original_widget.render(size, False)
        return CompositeCanvas(canv)
