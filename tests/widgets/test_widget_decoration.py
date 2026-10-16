from __future__ import annotations

import typing
import unittest
import warnings

import urwid


class WidgetWrapTest(unittest.TestCase):
    def test_delegates_sizing_pack_and_render(self) -> None:
        wrapped = urwid.WidgetWrap(urwid.Text("hello"))

        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), wrapped.sizing())
        self.assertFalse(wrapped.selectable())
        self.assertEqual((5, 1), wrapped.pack(()))
        self.assertEqual([b"hello"], wrapped.render(()).text)

    def test_replace_wrapped_widget(self) -> None:
        wrap = urwid.WidgetWrap(urwid.Button("edit me"))
        self.assertTrue(wrap.selectable())
        self.assertEqual("left", wrap.keypress((12,), "left"))

        wrap._w = urwid.Text("gone")
        self.assertFalse(wrap.selectable())
        self.assertEqual([b"gone"], wrap.render(()).text)


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


class _EndlessAttributes:
    """Callable non-widget that returns a new object for every missing attribute, as `unittest.mock.MagicMock` does.

    A lookup deeper than `max_depth` raises, so a walk that never stops fails instead of exhausting memory.
    """

    max_depth: typing.ClassVar[int] = 100

    def __init__(self, depth: int = 0) -> None:
        self.depth = depth

    def __getattr__(self, name: str) -> _EndlessAttributes:
        if self.depth >= self.max_depth:
            message = f"walked {self.depth} objects deep through {name!r}"
            raise AssertionError(message)
        return _EndlessAttributes(self.depth + 1)

    def __call__(self, *_args: object, **_kwargs: object) -> _EndlessAttributes:
        return self


class _WrapWithOriginalWidget(urwid.WidgetWrap[urwid.AttrMap[urwid.Text]]):
    """WidgetWrap that also exposes its wrapped widget as `_original_widget`, as some applications do."""

    def __init__(self, text: urwid.Text) -> None:
        self._original_widget = urwid.AttrMap(text, None)
        super().__init__(self._original_widget)


class BaseWidgetTest(unittest.TestCase):
    """Walking decorations with `WidgetDecoration.base_widget`."""

    def test_stops_at_non_widget(self) -> None:
        """Return a wrapped non-widget instead of looking for decorations inside it."""
        inner = _EndlessAttributes()
        # Python 3.12 and later find no protocol members on it and warn that it is not a widget; 3.11 finds them all.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            mapped = urwid.AttrMap(typing.cast("urwid.Widget", inner), None)

        self.assertIs(inner, mapped.base_widget)
        # Python 3.11 reads base_widget when Columns checks its widgets against the AbstractWidget protocol.
        self.assertIs(mapped, urwid.Columns([mapped]).contents[0][0])

    def test_follows_widget_with_original_widget(self) -> None:
        """Walk through a widget that is not a decoration but has `_original_widget`."""
        text = urwid.Text("hello")

        self.assertIs(text, urwid.AttrMap(_WrapWithOriginalWidget(text), None).base_widget)


class WidgetDisableTest(unittest.TestCase):
    def test_blocks_selection_and_focus_render(self) -> None:
        button = urwid.Button("Ok")
        disabled = urwid.WidgetDisable(button)

        self.assertFalse(disabled.selectable())
        self.assertEqual(button.sizing(), disabled.sizing())
        self.assertEqual(button.pack(()), disabled.pack(()))
        self.assertIsNone(disabled.render((10,), focus=True).cursor)
