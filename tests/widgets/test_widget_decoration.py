from __future__ import annotations

import typing
import unittest
import warnings
from unittest import mock

import urwid


class WidgetPlaceholderTest(unittest.TestCase):
    def test_swap_original_widget(self) -> None:
        first = urwid.Text("first")
        second = urwid.Button("second")
        placeholder = urwid.WidgetPlaceholder(first)

        self.assertIs(first, placeholder.original_widget)
        self.assertIs(first, placeholder.base_widget)
        self.assertEqual([b"first"], placeholder.render(()).text)

        placeholder.original_widget = second
        self.assertIs(second, placeholder.original_widget)
        self.assertTrue(placeholder.selectable())
        self.assertEqual([b"< second >"], placeholder.render(()).text)


class _DepthLimitedMock(mock.MagicMock):
    """MagicMock that raises once `_original_widget` is read from a child mock deeper than `max_depth`.

    A walk that never stops then fails instead of exhausting memory.
    Only `_original_widget` is limited: an error raised while creating a magic method such as `__hash__`
    may reach the caller as an unrelated `TypeError`.
    """

    max_depth: typing.ClassVar[int] = 100

    def _get_child_mock(self, /, **kwargs: object) -> mock.MagicMock:
        if kwargs.get("name") == "_original_widget":
            depth = 0
            parent: mock.NonCallableMock | None = self
            while parent is not None:
                depth += 1
                parent = parent._mock_new_parent
            if depth > self.max_depth:
                message = f"read _original_widget from a child mock {depth} levels deep"
                raise AssertionError(message)
        return super()._get_child_mock(**kwargs)


class _WrapWithOriginalWidget(urwid.WidgetWrap[urwid.AttrMap[urwid.Text]]):
    """WidgetWrap that also exposes its wrapped widget as `_original_widget`, as some applications do."""

    def __init__(self, text: urwid.Text) -> None:
        self._original_widget = urwid.AttrMap(text, None)
        super().__init__(self._original_widget)


class _ScratchDecoration:
    """Decoration that implements the AbstractWidget protocol without subclassing Widget."""

    __slots__ = ("_original_widget",)

    def __init__(self, original_widget: urwid.Widget) -> None:
        self._original_widget = original_widget

    @property
    def base_widget(self) -> urwid.AbstractWidget:
        """Return the base of the wrapped widget."""
        return self._original_widget.base_widget

    @property
    def focus(self) -> urwid.AbstractWidget | None:
        """Return the focus of the wrapped widget."""
        return self._original_widget.focus

    def sizing(self) -> frozenset[urwid.Sizing]:
        """Return the sizing modes of the wrapped widget."""
        return self._original_widget.sizing()

    def selectable(self) -> bool:
        """Return whether the wrapped widget is selectable."""
        return self._original_widget.selectable()

    def pack(self, size: typing.Any, focus: bool = False) -> tuple[int, int]:
        """Return the size the wrapped widget needs."""
        return self._original_widget.pack(size, focus)

    def keypress(self, size: typing.Any, key: str) -> str | None:
        """Pass the key to the wrapped widget."""
        return self._original_widget.keypress(size, key)

    def mouse_event(
        self,
        size: typing.Any,
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the mouse event to the wrapped widget."""
        return self._original_widget.mouse_event(size, event, button, col, row, focus)

    def render(self, size: typing.Any, focus: bool = False) -> urwid.Canvas:
        """Render the wrapped widget."""
        return self._original_widget.render(size, focus)

    def _invalidate(self) -> None:
        """Do nothing: the decoration caches no canvas of its own."""


class BaseWidgetTest(unittest.TestCase):
    """Walking decorations with `WidgetDecoration.base_widget`."""

    def test_stops_at_mock(self) -> None:
        """Return a wrapped mock instead of looking for decorations inside it."""
        inner = _DepthLimitedMock()
        # Python 3.12 and later find no protocol members on a mock and warn that it is not a widget.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            mapped = urwid.AttrMap(inner, None)

        self.assertIs(inner, mapped.base_widget)
        # Python 3.11 reads base_widget when Columns checks its widgets against the AbstractWidget protocol.
        self.assertIs(mapped, urwid.Columns([mapped]).contents[0][0])

    def test_follows_any_object_with_original_widget(self) -> None:
        """Walk through objects that are not WidgetDecoration subclasses but have `_original_widget`."""
        text = urwid.Text("hello")
        for label, wrapper in (
            ("WidgetWrap", _WrapWithOriginalWidget(text)),
            ("AbstractWidget implementation", _ScratchDecoration(text)),
        ):
            with self.subTest(label):
                self.assertIs(text, urwid.AttrMap(wrapper, None).base_widget)


class WidgetDisableTest(unittest.TestCase):
    def test_blocks_selection_and_focus_render(self) -> None:
        button = urwid.Button("Ok")
        disabled = urwid.WidgetDisable(button)

        self.assertFalse(disabled.selectable())
        self.assertEqual(button.sizing(), disabled.sizing())
        self.assertEqual(button.pack(()), disabled.pack(()))
        self.assertIsNone(disabled.render((10,), focus=True).cursor)
