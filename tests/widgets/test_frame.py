from __future__ import annotations

import unittest

import urwid
from tests.util import SelectableText
from urwid.canvas import TextCanvas
from urwid.widget import Widget
from urwid.widget.constants import Sizing


class NoMouseEventWidget:
    """A widget-like object with no ``mouse_event`` method."""

    def __init__(self, rows: int = 1, selectable: bool = False) -> None:
        self._rows = rows
        self._selectable = selectable

    def selectable(self) -> bool:
        return self._selectable

    def rows(self, size, focus: bool = False) -> int:
        return self._rows

    def render(self, size, focus: bool = False):
        maxcol = size[0]
        return TextCanvas([b" " * maxcol] * self._rows, maxcol=maxcol)

    def keypress(self, size, key):
        return key


class NoMouseEventBoxWidget:
    """A box widget-like object with no ``mouse_event`` method."""

    def selectable(self) -> bool:
        return False

    def render(self, size, focus: bool = False):
        maxcol, maxrow = size
        return TextCanvas([b" " * maxcol] * maxrow, maxcol=maxcol)


class LiarHeader(Widget):
    """Flow widget whose rendered canvas has fewer rows than it reports."""

    _sizing = frozenset([Sizing.FLOW])
    _selectable = False

    def rows(self, size, focus: bool = False) -> int:
        return 3

    def render(self, size, focus: bool = False):
        maxcol = size[0]
        return TextCanvas([b"a" * maxcol, b"b" * maxcol], maxcol=maxcol)


class LiarFooter(Widget):
    """Flow widget whose rendered canvas has fewer rows than it reports."""

    _sizing = frozenset([Sizing.FLOW])
    _selectable = False

    def rows(self, size, focus: bool = False) -> int:
        return 3

    def render(self, size, focus: bool = False):
        maxcol = size[0]
        return TextCanvas([b"a" * maxcol, b"b" * maxcol], maxcol=maxcol)


class FrameTest(unittest.TestCase):
    def ftbtest(self, desc: str, focus_part, header_rows, footer_rows, size, focus, top, bottom):
        class FakeWidget:
            def __init__(self, rows, want_focus):
                self.ret_rows = rows
                self.want_focus = want_focus

            def rows(self, size, focus=False):
                assert self.want_focus == focus
                return self.ret_rows

        with self.subTest(desc):
            header = footer = None
            if header_rows:
                header = FakeWidget(header_rows, focus and focus_part == "header")
            if footer_rows:
                footer = FakeWidget(footer_rows, focus and focus_part == "footer")

            f = urwid.Frame(urwid.SolidFill(), header, footer, focus_part)

            rval = f.frame_top_bottom(size, focus)
            exp = (top, bottom), (header_rows, footer_rows)
            self.assertEqual(exp, rval)

    def test(self):
        self.ftbtest("simple", "body", 0, 0, (9, 10), True, 0, 0)
        self.ftbtest("simple h", "body", 3, 0, (9, 10), True, 3, 0)
        self.ftbtest("simple f", "body", 0, 3, (9, 10), True, 0, 3)
        self.ftbtest("simple hf", "body", 3, 3, (9, 10), True, 3, 3)
        self.ftbtest("almost full hf", "body", 4, 5, (9, 10), True, 4, 5)
        self.ftbtest("full hf", "body", 5, 5, (9, 10), True, 4, 5)
        self.ftbtest("x full h+1f", "body", 6, 5, (9, 10), False, 4, 5)
        self.ftbtest("full h+1f", "body", 6, 5, (9, 10), True, 4, 5)
        self.ftbtest("full hf+1", "body", 5, 6, (9, 10), True, 3, 6)
        self.ftbtest("F full h+1f", "footer", 6, 5, (9, 10), True, 5, 5)
        self.ftbtest("F full hf+1", "footer", 5, 6, (9, 10), True, 4, 6)
        self.ftbtest("F full hf+5", "footer", 5, 11, (9, 10), True, 0, 10)
        self.ftbtest("full hf+5", "body", 5, 11, (9, 10), True, 0, 9)
        self.ftbtest("H full hf+1", "header", 5, 6, (9, 10), True, 5, 5)
        self.ftbtest("H full h+1f", "header", 6, 5, (9, 10), True, 6, 4)
        self.ftbtest("H full h+5f", "header", 11, 5, (9, 10), True, 10, 0)

    def test_common(self):
        s1 = urwid.SolidFill("1")

        f = urwid.Frame(s1)
        self.assertEqual(f.focus, s1)
        self.assertEqual(f.focus_position, "body")
        self.assertRaises(IndexError, lambda: setattr(f, "focus_position", None))
        self.assertRaises(IndexError, lambda: setattr(f, "focus_position", "header"))

        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        t3 = urwid.Text("three")
        f = urwid.Frame(s1, t1, t2, "header")
        self.assertEqual(f.focus, t1)
        self.assertEqual(f.focus_position, "header")
        f.focus_position = "footer"
        self.assertEqual(f.focus, t2)
        self.assertEqual(f.focus_position, "footer")
        self.assertRaises(IndexError, lambda: setattr(f, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(f, "focus_position", 2))
        del f.contents["footer"]
        self.assertEqual(f.footer, None)
        self.assertEqual(f.focus_position, "body")
        f.contents.update(footer=(t3, None), header=(t2, None))
        self.assertEqual(f.header, t2)
        self.assertEqual(f.footer, t3)

        def set1():
            f.contents["body"] = t1

        self.assertRaises(urwid.FrameError, set1)

        def set2():
            f.contents["body"] = (t1, "given")

        self.assertRaises(urwid.FrameError, set2)

    def test_focus(self):
        header = urwid.Text("header")
        body = urwid.ListBox((urwid.Text("first"), urwid.Text("second")))
        footer = urwid.Text("footer")

        with self.subTest("default"):
            widget = urwid.Frame(body, header, footer)
            self.assertEqual(body, widget.focus)
            self.assertEqual("body", widget.focus_part)

        with self.subTest("body"):
            widget = urwid.Frame(body, header, footer, focus_part=body)
            self.assertEqual(body, widget.focus)
            self.assertEqual("body", widget.focus_part)

        with self.subTest("header"):
            widget = urwid.Frame(body, header, footer, focus_part=header)
            self.assertEqual(header, widget.focus)
            self.assertEqual("header", widget.focus_part)

        with self.subTest("footer"):
            widget = urwid.Frame(body, header, footer, focus_part=footer)
            self.assertEqual(footer, widget.focus)
            self.assertEqual("footer", widget.focus_part)

    def test_init_invalid_focus_part(self):
        self.assertRaises(ValueError, urwid.Frame, urwid.SolidFill(), focus_part="not a part")

    def test_header_setter_resets_focus(self):
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        self.assertEqual("header", f.focus_position)
        f.header = None
        self.assertEqual("body", f.focus_position)

    def test_footer_setter_resets_focus(self):
        footer = urwid.Text("footer")
        f = urwid.Frame(urwid.SolidFill(), footer=footer, focus_part="footer")
        self.assertEqual("footer", f.focus_position)
        f.footer = None
        self.assertEqual("body", f.focus_position)

    def test_sizing(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertEqual(frozenset([urwid.Sizing.BOX]), f.sizing())


class FrameContentsTest(unittest.TestCase):
    def test_getitem_missing_header_footer(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertRaises(KeyError, lambda: f.contents["header"])
        self.assertRaises(KeyError, lambda: f.contents["footer"])
        self.assertEqual((f.body, None), f.contents["body"])

    def test_getitem_existing_header_footer(self):
        header = urwid.Text("header")
        footer = urwid.Text("footer")
        f = urwid.Frame(urwid.SolidFill(), header, footer)
        self.assertEqual((header, None), f.contents["header"])
        self.assertEqual((footer, None), f.contents["footer"])

    def test_setitem_invalid_key(self):
        f = urwid.Frame(urwid.SolidFill())

        def set_invalid():
            f.contents["invalid"] = (urwid.Text("x"), None)

        self.assertRaises(KeyError, set_invalid)

    def test_setitem_header_footer(self):
        f = urwid.Frame(urwid.SolidFill())
        header = urwid.Text("header")
        footer = urwid.Text("footer")
        f.contents["header"] = (header, None)
        f.contents["footer"] = (footer, None)
        self.assertEqual(header, f.header)
        self.assertEqual(footer, f.footer)

    def test_setitem_body(self):
        f = urwid.Frame(urwid.SolidFill("x"))
        new_body = urwid.SolidFill("y")
        f.contents["body"] = (new_body, None)
        self.assertEqual(new_body, f.body)

    def test_delitem_invalid_key(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertRaises(KeyError, lambda: f.contents.__delitem__("body"))

    def test_delitem_missing_header(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertRaises(KeyError, lambda: f.contents.__delitem__("header"))

    def test_delitem_header(self):
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header)
        del f.contents["header"]
        self.assertIsNone(f.header)

    def test_contents_keys(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertEqual(["body"], f._contents_keys())

        header = urwid.Text("header")
        footer = urwid.Text("footer")
        f = urwid.Frame(urwid.SolidFill(), header, footer)
        self.assertEqual(["body", "header", "footer"], f._contents_keys())

    def test_options(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertIsNone(f.options())

    def test_contents_iter_len_dict(self):
        # regression test: FrameContents.__iter__/__len__ used to recurse
        # into themselves via the inherited MutableMapping.keys().
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header)
        self.assertEqual(["body", "header"], list(f.contents))
        self.assertEqual(["body", "header"], list(f.contents.keys()))
        self.assertEqual(2, len(f.contents))
        self.assertEqual({"body": (f.body, None), "header": (header, None)}, dict(f.contents))

    def test_iter_reversed(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertEqual(["body"], list(f))
        self.assertEqual(["body"], list(reversed(f)))

        header = urwid.Text("header")
        footer = urwid.Text("footer")
        f = urwid.Frame(urwid.SolidFill(), header, footer)
        self.assertEqual(["header", "body", "footer"], list(f))
        self.assertEqual(["footer", "body", "header"], list(reversed(f)))


class FrameRenderTest(unittest.TestCase):
    def test_render_no_header_footer(self):
        f = urwid.Frame(urwid.SolidFill("x"))
        canvas = f.render((5, 3))
        self.assertEqual([b"xxxxx"] * 3, canvas.text)

    def test_render_with_header_and_footer(self):
        header = urwid.Text("head")
        footer = urwid.Text("foot")
        f = urwid.Frame(urwid.SolidFill("x"), header, footer)
        canvas = f.render((5, 4))
        self.assertEqual([b"head ", b"xxxxx", b"xxxxx", b"foot "], canvas.text)

    def test_render_header_trimmed(self):
        header = urwid.Text("one\ntwo\nthree")
        f = urwid.Frame(urwid.SolidFill("x"), header)
        canvas = f.render((5, 2))
        self.assertEqual([b"one  ", b"xxxxx"], canvas.text)

    def test_render_footer_trimmed(self):
        footer = urwid.Text("a\nb\nc")
        f = urwid.Frame(urwid.SolidFill("x"), None, footer)
        canvas = f.render((5, 2))
        self.assertEqual([b"xxxxx", b"a    "], canvas.text)

    def test_render_zero_rows(self):
        f = urwid.Frame(urwid.SolidFill("x"))
        canvas = f.render((5, 0))
        self.assertEqual([], canvas.text)

    def test_render_header_row_mismatch_raises(self):
        f = urwid.Frame(urwid.SolidFill("x"), LiarHeader())
        self.assertRaises(RuntimeError, f.render, (5, 5))

    def test_render_footer_row_mismatch_raises(self):
        f = urwid.Frame(urwid.SolidFill("x"), None, LiarFooter())
        self.assertRaises(RuntimeError, f.render, (5, 5))


class FrameKeypressTest(unittest.TestCase):
    def test_keypress_to_body(self):
        edit = urwid.Edit("", "")
        f = urwid.Frame(urwid.Filler(edit))
        f.render((10, 3), focus=True)
        self.assertIsNone(f.keypress((10, 3), "x"))
        self.assertEqual("x", edit.edit_text)

    def test_keypress_to_header_selectable(self):
        header = urwid.Edit("", "")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        f.render((10, 3), focus=True)
        self.assertIsNone(f.keypress((10, 3), "x"))
        self.assertEqual("x", header.edit_text)

    def test_keypress_to_header_not_selectable(self):
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        self.assertEqual("x", f.keypress((10, 3), "x"))

    def test_keypress_to_footer_selectable(self):
        footer = urwid.Edit("", "")
        f = urwid.Frame(urwid.SolidFill(), None, footer, focus_part="footer")
        f.render((10, 3), focus=True)
        self.assertIsNone(f.keypress((10, 3), "x"))
        self.assertEqual("x", footer.edit_text)

    def test_keypress_to_footer_not_selectable(self):
        footer = urwid.Text("footer")
        f = urwid.Frame(urwid.SolidFill(), None, footer, focus_part="footer")
        self.assertEqual("x", f.keypress((10, 3), "x"))

    def test_keypress_focus_part_widget_missing(self):
        f = urwid.Frame(urwid.SolidFill(), focus_part="header")
        self.assertEqual("x", f.keypress((10, 3), "x"))

    def test_keypress_body_not_selectable(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertEqual("x", f.keypress((10, 3), "x"))

    def test_keypress_body_no_remaining_rows(self):
        edit = urwid.Filler(urwid.Edit("", ""))
        header = urwid.Text("one\ntwo\nthree")
        footer = urwid.Text("a\nb\nc")
        f = urwid.Frame(edit, header, footer)
        self.assertEqual("x", f.keypress((10, 4), "x"))


class FrameMouseEventTest(unittest.TestCase):
    def test_mouse_event_header_changes_focus(self):
        header = urwid.Edit("", "")
        f = urwid.Frame(urwid.SolidFill(), header)
        self.assertEqual("body", f.focus_position)
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertEqual("header", f.focus_position)
        self.assertIsNotNone(result)

    def test_mouse_event_header_not_selectable_no_focus_change(self):
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header)
        f.render((10, 5), focus=True)
        f.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertEqual("body", f.focus_position)

    def test_mouse_event_header_no_mouse_event_attr(self):
        header = NoMouseEventWidget(rows=1)
        f = urwid.Frame(urwid.SolidFill(), header)
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)

    def test_mouse_event_footer_changes_focus(self):
        footer = urwid.Edit("", "")
        f = urwid.Frame(urwid.SolidFill(), None, footer)
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 4, True)
        self.assertEqual("footer", f.focus_position)
        self.assertIsNotNone(result)

    def test_mouse_event_footer_no_mouse_event_attr(self):
        footer = NoMouseEventWidget(rows=1)
        f = urwid.Frame(urwid.SolidFill(), None, footer)
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 4, True)
        self.assertFalse(result)

    def test_mouse_event_body_changes_focus(self):
        edit = urwid.Filler(urwid.Edit("", ""))
        header = urwid.Text("header")
        f = urwid.Frame(edit, header, focus_part="header")
        f.render((10, 5), focus=True)
        self.assertEqual("header", f.focus_position)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 3, True)
        self.assertEqual("body", f.focus_position)
        self.assertIsNotNone(result)

    def test_mouse_event_body_no_mouse_event_attr(self):
        f = urwid.Frame(NoMouseEventBoxWidget())
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)


class FrameCursorCoordsTest(unittest.TestCase):
    def test_get_cursor_coords_not_selectable(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertIsNone(f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_no_support(self):
        header = urwid.Text("header")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        self.assertIsNone(f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_body(self):
        edit = urwid.Filler(urwid.Edit("", "hi"), valign="top")
        f = urwid.Frame(edit)
        self.assertEqual((2, 0), f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_header(self):
        header = urwid.Edit("", "hi")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        self.assertEqual((2, 0), f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_footer(self):
        footer = urwid.Edit("", "hi")
        f = urwid.Frame(urwid.SolidFill(), None, footer, focus_part="footer")
        self.assertEqual((2, 4), f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_selectable_no_get_cursor_coords_method(self):
        header = SelectableText("header")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        self.assertIsNone(f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_coords_none(self):
        header = urwid.Edit("", "")
        f = urwid.Frame(urwid.SolidFill(), header, focus_part="header")
        header.set_edit_text("")
        original = header.get_cursor_coords
        header.get_cursor_coords = lambda size: None
        try:
            self.assertIsNone(f.get_cursor_coords((10, 5)))
        finally:
            header.get_cursor_coords = original
