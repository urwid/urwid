"""Base classes for decoration widgets that wrap a single child widget."""

from __future__ import annotations

import sys
import typing

from urwid import _deprecation
from urwid.canvas import CompositeCanvas

from .widget import AbstractWidget, Widget, WidgetError, WidgetWarning, _select_enter_child, delegate_to_widget_mixin

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from .constants import Sizing
    from .widget import _DelegateToWidgetMixin


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
        """Wrap `original_widget`, warning when it does not implement the Widget API.

        .. deprecated:: 2.4.0
            Wrapping an object that does not implement the Widget API (see ``AbstractWidget``) is deprecated.
            Support will be removed in version 7.0.
        """
        super().__init__()
        if not isinstance(original_widget, AbstractWidget):
            obj_class_path = f"{original_widget.__class__.__module__}.{original_widget.__class__.__name__}"
            _deprecation.warn(f"{obj_class_path} is not implementing Widget API.", since="2.4.0", removed_in="7.0")
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
        The walk stops at a :mod:`unittest.mock` object.

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
        # Each mock returns a new child mock for `_original_widget`, so the walk would never reach a visited object.
        # Mocks exist only if unittest.mock is already imported, so it is not imported here.
        # The module may still be importing in another thread, so the class can be missing from it.
        mock_type = getattr(sys.modules.get("unittest.mock"), "NonCallableMock", None)
        mock_types: tuple[type, ...] = (mock_type,) if mock_type is not None else ()
        while not isinstance(w, mock_types) and (w := getattr(w, "_original_widget", w)) not in visited:
            visited.add(w)
        return w

    def selectable(self) -> bool:
        """Return whether the wrapped widget can take the input focus."""
        return self._original_widget.selectable()

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Forward the entry hook to :attr:`original_widget`, when it has one.

        A container with ``select_navigation`` calls this when it moves its focus to this widget,
        see :ref:`select-navigation`.
        The hook goes to the widget that :meth:`keypress` sends keys to:
        a subclass that sends keys elsewhere overrides this method to match.

        :param reverse: start at the last selectable widget instead of the first one.
        """
        _select_enter_child(self._original_widget, reverse=reverse)

    def sizing(self) -> frozenset[Sizing]:
        """Return the set of sizing modes supported by the wrapped widget."""
        return self._original_widget.sizing()


if typing.TYPE_CHECKING:
    _WidgetPlaceholderDelegate = _DelegateToWidgetMixin
else:
    _WidgetPlaceholderDelegate = delegate_to_widget_mixin("_original_widget")


class WidgetPlaceholder(
    _WidgetPlaceholderDelegate,
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

    While :attr:`disabled` is ``True``, this widget is never selectable, reports no cursor,
    and always passes ``focus=False`` to the wrapped widget, even if it somehow does become the focus.
    While it is ``False``, focus, input and the cursor pass through to the wrapped widget unchanged.
    The look of a disabled widget is left to the application, for example an :class:`AttrMap` around it.

    :param original_widget: the widget being disabled
    :param disabled: start disabled; ``False`` starts with the wrapped widget enabled

    >>> from urwid import Button
    >>> w = WidgetDisable(Button("Ok"))
    >>> w.selectable()
    False
    >>> w.disabled = False
    >>> w.selectable()
    True
    """

    no_cache: typing.ClassVar[list[str]] = ["rows"]

    def __init__(self, original_widget: WrappedWidget, *, disabled: bool = True) -> None:
        """Wrap `original_widget`, disabled unless *disabled* is ``False``."""
        super().__init__(original_widget)
        self._disabled = disabled

    @property
    def disabled(self) -> bool:
        """Whether interaction with the wrapped widget is disabled; setting it redraws the widget."""
        return self._disabled

    @disabled.setter
    def disabled(self, disabled: bool) -> None:
        self._disabled = disabled
        self._invalidate()

    def selectable(self) -> bool:
        """Return ``False`` while disabled, otherwise whether the wrapped widget can take the input focus."""
        return not self._disabled and self._original_widget.selectable()

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Forward the entry hook to :attr:`original_widget` unless disabled: a disabled widget is never entered."""
        if not self._disabled:
            super().enter_selectable(reverse=reverse)

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Return *key* unhandled while disabled, otherwise pass it to the wrapped widget."""
        if self._disabled:
            return super().keypress(size, key)
        return self._original_widget.keypress(size, key)

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Leave the event unhandled while disabled, otherwise pass it to the wrapped widget."""
        if self._disabled:
            return super().mouse_event(size, event, button, col, row, focus)
        return self._original_widget.mouse_event(size, event, button, col, row, focus)

    # The cursor methods are properties so that hasattr() is False while disabled or when the wrapped widget lacks
    # the method: containers probe for them to decide whether a widget has a cursor.
    @property
    def get_cursor_coords(self) -> Callable[[tuple[()] | tuple[int] | tuple[int, int]], tuple[int, int] | None]:
        """Return the wrapped widget's `get_cursor_coords` method while enabled, if it has one."""
        return typing.cast(
            "Callable[[tuple[()] | tuple[int] | tuple[int, int]], tuple[int, int] | None]",
            self._enabled_original_attr("get_cursor_coords"),
        )

    @property
    def get_pref_col(self) -> Callable[[tuple[()] | tuple[int] | tuple[int, int]], int | None]:
        """Return the wrapped widget's `get_pref_col` method while enabled, if it has one."""
        return typing.cast(
            "Callable[[tuple[()] | tuple[int] | tuple[int, int]], int | None]",
            self._enabled_original_attr("get_pref_col"),
        )

    @property
    def move_cursor_to_coords(self) -> Callable[[tuple[()] | tuple[int] | tuple[int, int], int, int], bool]:
        """Return the wrapped widget's `move_cursor_to_coords` method while enabled, if it has one."""
        return typing.cast(
            "Callable[[tuple[()] | tuple[int] | tuple[int, int], int, int], bool]",
            self._enabled_original_attr("move_cursor_to_coords"),
        )

    def _enabled_original_attr(self, name: str) -> typing.Any:
        """Return attribute *name* of the wrapped widget.

        :raises AttributeError: the widget is disabled, or the wrapped widget has no such attribute.
        """
        if self._disabled:
            raise AttributeError(f"{self.__class__.__name__} is disabled and has no {name!r}")
        return getattr(self._original_widget, name)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """Return the number of rows the wrapped widget occupies, passing ``focus=False`` while disabled."""
        # AttributeError is a valid case
        return self._original_widget.rows(size, focus and not self._disabled)  # type: ignore[attr-defined,no-any-return]

    def sizing(self) -> frozenset[Sizing]:
        """Return the set of sizing modes supported by the wrapped widget."""
        return self._original_widget.sizing()

    def pack(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> tuple[int, int]:
        """Return the size required by the wrapped widget, passing ``focus=False`` while disabled."""
        return self._original_widget.pack(size, focus and not self._disabled)

    def render(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        focus: bool = False,
    ) -> CompositeCanvas:
        """Render the wrapped widget into a canvas, passing ``focus=False`` while disabled."""
        canv = self._original_widget.render(size, focus and not self._disabled)
        return CompositeCanvas(canv)
