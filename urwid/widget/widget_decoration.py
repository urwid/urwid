from __future__ import annotations

import typing
import warnings

from urwid.canvas import CompositeCanvas

from .widget import Widget, delegate_to_widget_mixin

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


class WidgetDecoration(Widget):  # "decorator" was already taken
    """
    original_widget -- the widget being decorated

    This is a base class for decoration widgets, widgets
    that contain one or more widgets and only ever have
    a single focus.  This type of widget will affect the
    display or behaviour of the original_widget but it is
    not part of determining a chain of focus.

    Don't actually do this -- use a WidgetDecoration subclass
    instead, these are not real widgets:

    >>> from urwid import Text
    >>> WidgetDecoration(Text(u"hi"))
    <WidgetDecoration flow widget <Text flow widget 'hi'>>
    """

    def __init__(self, original_widget: Widget) -> None:
        self._original_widget = original_widget

    def _repr_words(self):
        return [*super()._repr_words(), repr(self._original_widget)]

    @property
    def original_widget(self) -> Widget:
        return self._original_widget

    @original_widget.setter
    def original_widget(self, original_widget: Widget) -> None:
        self._original_widget = original_widget
        self._invalidate()

    def _get_original_widget(self) -> Widget:
        warnings.warn(
            f"Method `{self.__class__.__name__}._get_original_widget` is deprecated, "
            f"please use property `{self.__class__.__name__}.original_widget`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    def _set_original_widget(self, original_widget):
        warnings.warn(
            f"Method `{self.__class__.__name__}._set_original_widget` is deprecated, "
            f"please use property `{self.__class__.__name__}.original_widget`",
            DeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = original_widget

    @property
    def base_widget(self) -> Widget:
        """
        Return the widget without decorations.  If there is only one
        Decoration then this is the same as original_widget.

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
        w = self
        while hasattr(w, "_original_widget"):
            w = w._original_widget
        return w

    def _get_base_widget(self):
        warnings.warn(
            f"Method `{self.__class__.__name__}._get_base_widget` is deprecated, "
            f"please use property `{self.__class__.__name__}.base_widget`",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.base_widget

    def selectable(self) -> bool:
        return self._original_widget.selectable()

    def sizing(self):
        return self._original_widget.sizing()


class WidgetPlaceholder(delegate_to_widget_mixin("_original_widget"), WidgetDecoration):
    """
    This is a do-nothing decoration widget that can be used for swapping
    between widgets without modifying the container of this widget.

    This can be useful for making an interface with a number of distinct
    pages or for showing and hiding menu or status bars.

    The widget displayed is stored as the self.original_widget property and
    can be changed by assigning a new widget to it.
    """

    pass


class WidgetDisable(WidgetDecoration):
    """
    A decoration widget that disables interaction with the widget it
    wraps.  This widget always passes focus=False to the wrapped widget,
    even if it somehow does become the focus.
    """

    no_cache: typing.ClassVar[list[str]] = ["rows"]
    ignore_focus = True

    def selectable(self) -> Literal[False]:
        return False

    def rows(self, size, focus: bool = False) -> int:
        return self._original_widget.rows(size, False)

    def sizing(self):
        return self._original_widget.sizing()

    def pack(self, size, focus: bool = False) -> tuple[int, int]:
        return self._original_widget.pack(size, False)

    def render(self, size, focus: bool = False) -> CompositeCanvas:
        canv = self._original_widget.render(size, False)
        return CompositeCanvas(canv)
