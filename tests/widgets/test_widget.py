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


if __name__ == "__main__":
    unittest.main()
