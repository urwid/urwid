from __future__ import annotations

import unittest

import urwid


class AttrMapTest(unittest.TestCase):
    def test_keyword_maps_and_original_widget(self) -> None:
        text = urwid.Text("hi")
        mapped = urwid.AttrMap(text, attr_map="idle", focus_map="focus")

        self.assertIs(text, mapped.original_widget)
        self.assertIs(text, mapped.base_widget)
        self.assertEqual({None: "idle"}, mapped.attr_map)
        self.assertEqual({None: "focus"}, mapped.focus_map)
        self.assertEqual(text.sizing(), mapped.sizing())

    def test_dict_maps_and_assignment(self) -> None:
        text = urwid.Text(("word", "hi"))
        mapped = urwid.AttrMap(text, attr_map={"word": "greeting", None: "bg"}, focus_map={"word": "hot"})

        mapped.attr_map = {None: "idle"}
        mapped.focus_map = {None: "focus"}
        self.assertEqual({None: "idle"}, mapped.attr_map)
        self.assertEqual({None: "focus"}, mapped.focus_map)

        mapped.focus_map = {None: None}
        self.assertEqual({None: None}, mapped.focus_map)

    def test_render_applies_focus_map(self) -> None:
        mapped = urwid.AttrMap(urwid.Text("hi"), "greeting", "fgreet")
        size = (5,)

        self.assertEqual([("greeting", None, b"hi   ")], next(mapped.render(size, focus=False).content()))
        self.assertEqual([("fgreet", None, b"hi   ")], next(mapped.render(size, focus=True).content()))

    def test_wraps_listbox_original_widget(self) -> None:
        items = (urwid.Text("one"), urwid.Text("two"), urwid.Text("three"))
        listbox = urwid.ListBox(urwid.SimpleListWalker(items))
        mapped = urwid.AttrMap(listbox, attr_map="body")

        self.assertIs(listbox, mapped.original_widget)
        self.assertEqual(0, mapped.original_widget.focus_position)
        mapped.original_widget.focus_position = 2
        self.assertEqual(2, listbox.focus_position)
        self.assertIs(items[2], mapped.original_widget.focus)
        self.assertEqual([items[2]], mapped.original_widget.get_focus_widgets())

    def test_none_attr_map_passthrough(self) -> None:
        text = urwid.Text("x")
        mapped = urwid.AttrMap(text, None)

        self.assertEqual({None: None}, mapped.attr_map)
        self.assertIsNone(mapped.focus_map)
        self.assertEqual([b"x"], mapped.render(()).text)
