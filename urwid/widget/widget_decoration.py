from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas

from .widget import Widget, WidgetError, WidgetWarning, delegate_to_widget_mixin

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

WrappedWidget = typing.TypeVar("WrappedWidget")


class WidgetDecoration(Widget, typing.Generic[WrappedWidget]):  # pylint: disable=abstract-method
    """
    original_widget -- the widget being decorated

    This is a base class for decoration widgets,
    widgets that contain one or more widgets and only ever have a single focus.
    This type of widget will affect the display or behaviour of the original_widget,
    but it is not part of determining a chain of focus.

    Don't actually do this -- use a WidgetDecoration subclass instead, these are not real widgets:

    >>> from urwid import Text
    >>> WidgetDecoration(Text(u"hi"))
    <WidgetDecoration fixed/flow widget <Text fixed/flow widget 'hi'>>

    .. Warning:
        WidgetDecoration do not implement ``render`` method.
        Implement it or forward to the widget in the subclass.
    """

    def __init__(self, original_widget: WrappedWidget) -> None:
        # TODO(Aleksei): reduce amount of multiple inheritance usage
        # Special case: subclasses with multiple inheritance causes `super` call wrong way
        # Call parent __init__ explicit
        Widget.__init__(self)
        if not isinstance(original_widget, Widget):
            obj_class_path = f"{original_widget.__class__.__module__}.{original_widget.__class__.__name__}"
            warnings.warn(
                f"{obj_class_path} is not subclass of Widget",
                DeprecationWarning,
                stacklevel=2,
            )
        self._original_widget = original_widget

    def _repr_words(self) -> list[str]:
        return [*super()._repr_words(), repr(self._original_widget)]

    @property
    def original_widget(self) -> WrappedWidget:
        return self._original_widget

    @original_widget.setter
    def original_widget(self, original_widget: WrappedWidget) -> None:
        self._original_widget = original_widget
        self._invalidate()

    @property
    def base_widget(self) -> Widget:
        """
        Return the widget without decorations.

        If there is only one Decoration, then this is the same as original_widget.

        >>> from urwid import Text
        >>> t = Text('hello')
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
        return self._original_widget.selectable()

    def sizing(self) -> frozenset[Sizing]:
        return self._original_widget.sizing()


class WidgetPlaceholder(delegate_to_widget_mixin("_original_widget"), WidgetDecoration[WrappedWidget]):
    """
    This is a do-nothing decoration widget that can be used for swapping
    between widgets without modifying the container of this widget.

    This can be useful for making an interface with a number of distinct
    pages or for showing and hiding menu or status bars.

    The widget displayed is stored as the self.original_widget property and
    can be changed by assigning a new widget to it.
    """


class WidgetDisable(WidgetDecoration[WrappedWidget]):
    """
    A decoration widget that disables interaction with the widget it
    wraps.  This widget always passes focus=False to the wrapped widget,
    even if it somehow does become the focus.
    """

    no_cache: typing.ClassVar[list[str]] = ["rows"]
    ignore_focus = True

    def selectable(self) -> Literal[False]:
        return False

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return self._original_widget.rows(size, False)

    def sizing(self) -> frozenset[Sizing]:
        return self._original_widget.sizing()

    def pack(self, size, focus: bool = False) -> tuple[int, int]:
        return self._original_widget.pack(size, False)

    def render(self, size, focus: bool = False) -> CompositeCanvas:
        canv = self._original_widget.render(size, False)
        return CompositeCanvas(canv)
