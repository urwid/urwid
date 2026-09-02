from __future__ import annotations

import unittest

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


class WidgetDisableTest(unittest.TestCase):
    def test_blocks_selection_and_focus_render(self) -> None:
        button = urwid.Button("Ok")
        disabled = urwid.WidgetDisable(button)

        self.assertFalse(disabled.selectable())
        self.assertEqual(button.sizing(), disabled.sizing())
        self.assertEqual(button.pack(()), disabled.pack(()))
        self.assertIsNone(disabled.render((10,), focus=True).cursor)
