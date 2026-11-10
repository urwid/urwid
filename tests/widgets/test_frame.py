from __future__ import annotations

import copy
import typing
import unittest

import urwid
import urwid.testing
from tests.util import SelectableText, assert_redraws_after_child_change
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
        class FakeWidget(urwid.Text):
            def __init__(self, rows, want_focus):
                super().__init__("")
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

        # an empty container is falsy, but it is still a header and a footer
        f = urwid.Frame(urwid.SolidFill(), urwid.Pile([]), urwid.Pile([]))
        self.assertEqual(["body", "header", "footer"], list(f.contents))
        self.assertEqual(["header", "body", "footer"], list(f))
        self.assertEqual(["footer", "body", "header"], list(reversed(f)))
        f.focus_position = "header"
        self.assertEqual((f.header, None), f.contents["header"])
        self.assertEqual(3, f.render((10, 3)).rows())

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

    def test_squish(self):
        urwid.testing.check_box_sizing(urwid.Frame(urwid.SolidFill()))
        urwid.testing.check_box_sizing(urwid.Frame(urwid.SolidFill(), header=urwid.Text("hello")))
        urwid.testing.check_box_sizing(
            urwid.Frame(urwid.SolidFill(), header=urwid.Text("hello"), footer=urwid.Text("hello"))
        )


class FrameUndrawnPartTest(unittest.TestCase):
    """A header or footer the Frame does not draw still decides when its canvas is drawn again."""

    def test_redraw_after_empty_part_changes(self) -> None:
        """Draw the Frame again when a header or footer of 0 rows gets rows."""
        for name, part, focus_part, expected in (
            ("header", "header", "body", (b"new  ", b".....", b".....")),
            ("footer", "footer", "body", (b".....", b".....", b"new  ")),
            ("header, focus on the footer", "header", "footer", (b"new  ", b".....", b"foot ")),
            ("footer, focus on the header", "footer", "header", (b"head ", b".....", b"new  ")),
        ):
            with self.subTest(name):
                empty = urwid.Pile([])
                parts = {"header": urwid.Text("head"), "footer": urwid.Text("foot"), part: empty}
                if focus_part == "body":
                    del parts["footer" if part == "header" else "header"]
                frame = urwid.Frame(urwid.SolidFill("."), focus_part=focus_part, **parts)
                assert_redraws_after_child_change(
                    self,
                    frame,
                    (5, 3),
                    lambda empty=empty: empty.contents.append((urwid.Text("new"), empty.options())),
                    expected,
                )

    def test_redraw_after_empty_part_changes_at_a_flow_size(self) -> None:
        """At a flow size, draw the Frame again when a header or footer of 0 rows gets rows."""
        for part, expected in (("header", (b"new  ", b".....")), ("footer", (b".....", b"new  "))):
            with self.subTest(part):
                empty = urwid.Pile([])
                frame = urwid.Frame(urwid.ListBox([urwid.Text(".....")]), **{part: empty})
                assert_redraws_after_child_change(
                    self,
                    frame,
                    (5,),
                    lambda empty=empty: empty.contents.append((urwid.Text("new"), empty.options())),
                    expected,
                )


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

    def test_keypress_body_on_a_short_frame(self) -> None:
        """A body that render() shows gets the keys, also when the header and the footer are trimmed.

        A frame of no rows shows no body and returns the key.
        """
        edit = urwid.Edit("", "")
        header = urwid.Text("one\ntwo\nthree")
        footer = urwid.Text("a\nb\nc")
        f = urwid.Frame(urwid.Filler(edit), header, footer)
        self.assertEqual(
            ["          ", "a         ", "b         ", "c         "], urwid.testing.render_text(f, (10, 4))
        )
        self.assertIsNone(f.keypress((10, 4), "x"))
        self.assertEqual("x", edit.edit_text)
        self.assertEqual("y", f.keypress((10, 0), "y"))


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
        with self.assertWarns(DeprecationWarning):
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
        with self.assertWarns(DeprecationWarning):
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
        with self.assertWarns(DeprecationWarning):
            f = urwid.Frame(NoMouseEventBoxWidget())
        f.render((10, 5), focus=True)
        result = f.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)


class FrameCursorCoordsTest(unittest.TestCase):
    def test_get_cursor_coords_not_selectable(self):
        f = urwid.Frame(urwid.SolidFill())
        self.assertIsNone(f.get_cursor_coords((10, 5)))

    def test_get_cursor_coords_focus_part_widget_missing(self):
        for part in ("header", "footer"):
            with self.subTest(part=part):
                f = urwid.Frame(urwid.SolidFill(), focus_part=part)
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


class FrameSelectNavigationTest(unittest.TestCase):
    """``select_navigation`` moves the focus on unhandled ``'next selectable'``/``'prev selectable'``."""

    size = (10, 5)

    def _frame(self, *, select_navigation: bool = True, header: urwid.Widget | None = None) -> urwid.Frame:
        return urwid.Frame(
            urwid.Filler(SelectableText("b")),
            header=SelectableText("h") if header is None else header,
            footer=SelectableText("f"),
            select_navigation=select_navigation,
        )

    def test_off_by_default(self) -> None:
        """Without the flag the key is returned and the entry hook keeps the focus."""
        frame = self._frame(select_navigation=False)
        self.assertEqual("tab", frame.keypress(self.size, "tab"))
        self.assertEqual("body", frame.focus_position)
        frame.enter_selectable()
        self.assertEqual("body", frame.focus_position)

    def test_traversal(self) -> None:
        """Steps go header, body, footer, and past the edge the key is returned after a reset."""
        frame = self._frame()
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual("footer", frame.focus_position)
        self.assertEqual("tab", frame.keypress(self.size, "tab"))
        self.assertEqual("header", frame.focus_position)
        self.assertEqual("shift tab", frame.keypress(self.size, "shift tab"))
        self.assertEqual("footer", frame.focus_position)
        self.assertIsNone(frame.keypress(self.size, "shift tab"))
        self.assertEqual("body", frame.focus_position)

    def test_skips_non_selectable_part(self) -> None:
        """A part that is not selectable is skipped."""
        frame = self._frame(header=urwid.Text("h"))
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual("tab", frame.keypress(self.size, "tab"))
        self.assertEqual("body", frame.focus_position)
        self.assertFalse(urwid.Frame(urwid.SolidFill(), select_navigation=True).focus_first_selectable())

    def test_parts_changed_between_presses(self) -> None:
        """A footer added after the press before is reached, and a removed one is not."""
        frame = urwid.Frame(urwid.Filler(SelectableText("b")), select_navigation=True)
        self.assertEqual("tab", frame.keypress(self.size, "tab"))
        frame.footer = SelectableText("f")
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual("footer", frame.focus_position)
        frame.footer = None
        self.assertEqual("body", frame.focus_position)
        self.assertEqual("tab", frame.keypress(self.size, "tab"))

    def test_child_keeps_handled_key(self) -> None:
        """A child that handles the key keeps it."""
        frame = urwid.Frame(urwid.Filler(urwid.Edit(allow_tab=True)), footer=SelectableText("f"))
        frame.select_navigation = True
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual("body", frame.focus_position)


class FrameFlowTest(unittest.TestCase):
    """A Frame at a flow size, and its FLOW sizing with ``flow`` set."""

    @staticmethod
    def make_list(count: int) -> urwid.ListBox:
        """Return a ListBox with flow set over *count* buttons."""
        return urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Button(f"b{i}") for i in range(count)]), flow=True)

    def test_sizing(self) -> None:
        """FLOW is reported only with flow set and a body that reports FLOW; setting flow redraws a parent."""
        box_flow = frozenset((urwid.BOX, urwid.FLOW))
        box = frozenset((urwid.BOX,))
        for name, frame, expected in (
            ("flow body, flow not set", urwid.Frame(self.make_list(2)), box),
            ("flow body, flow set", urwid.Frame(self.make_list(2), flow=True), box_flow),
            ("box body, flow set", urwid.Frame(urwid.ListBox([urwid.Text("a")]), flow=True), box),
            (
                "Pile body with a weighted flow list, flow set",
                urwid.Frame(urwid.Pile([("weight", 1, self.make_list(2))]), flow=True),
                box_flow,
            ),
        ):
            with self.subTest(name):
                self.assertEqual(expected, frame.sizing())

        frame = urwid.Frame(self.make_list(2), header=urwid.Text("head"))
        pile = urwid.Pile([("weight", 1, frame), ("pack", urwid.Text("end"))])
        self.assertEqual(["head  ", "< b0 >", "end   "], urwid.testing.render_text(pile, (6, 3)))
        frame.flow = True
        self.assertIn(urwid.FLOW, pile.sizing())
        self.assertEqual(["head  ", "< b0 >", "< b1 >", "end   "], urwid.testing.render_text(pile, (6,)))
        self.assertIs(True, vars(frame)["flow"])

    def test_flow_size_without_flow_set(self) -> None:
        """A flow size shows every part in full, whether or not flow is set."""
        frame = urwid.Frame(self.make_list(3), header=urwid.Text("head"), footer=urwid.Text("foot"))
        self.assertEqual(5, frame.rows((8,)))
        self.assertEqual(
            ["head    ", "< b0   >", "< b1   >", "< b2   >", "foot    "],
            urwid.testing.render_text(frame, (8,)),
        )
        self.assertEqual(["< b0   >"], urwid.testing.render_text(urwid.Frame(self.make_list(1)), (8,)))
        self.assertEqual([], urwid.testing.render_text(urwid.Frame(urwid.ListBox([])), (8,)))

    def test_check_sizing(self) -> None:
        """Every sizing mode renders the size it reports, cursor included, with any part in focus."""
        for focus_part in ("header", "body", "footer"):
            with self.subTest(focus_part=focus_part):
                frame = urwid.Frame(
                    urwid.ListBox([urwid.Text("a"), urwid.Edit("> ", "body")], flow=True),
                    header=urwid.Edit("", "head"),
                    footer=urwid.Edit("", "foot"),
                    focus_part=focus_part,
                    flow=True,
                )
                urwid.testing.check_sizing(frame, cols=10)

    def test_input_at_a_flow_size(self) -> None:
        """Keys reach the body, clicks reach the part under them, and the cursor is offset by the header rows."""
        edit = urwid.Edit("", "ab")
        ok_button = urwid.Button("ok")
        frame = urwid.Frame(
            urwid.ListBox([urwid.Text("a"), edit], flow=True),
            header=urwid.Text("head\nline"),
            footer=ok_button,
        )
        size = (8,)
        frame.render(size, focus=True)
        self.assertEqual([], urwid.testing.press(frame, size, "c"))
        self.assertEqual("abc", edit.edit_text)
        self.assertEqual((3, 3), frame.get_cursor_coords(size))

        clicked: list[urwid.Button] = []
        urwid.connect_signal(ok_button, "click", clicked.append)
        self.assertTrue(urwid.testing.click(frame, size, 2, 4))
        self.assertEqual(([ok_button], "footer"), (clicked, frame.focus_part))
        self.assertTrue(urwid.testing.click(frame, size, 0, 3))
        self.assertEqual("body", frame.focus_part)

    def test_dialog_shrinks_and_keeps_its_buttons(self) -> None:
        """In a pack Overlay with shrink_to_fit, a Frame dialog trims its header first and keeps its buttons.

        Its list scrolls with the focus in the one row it has left.
        """
        lbox = self.make_list(6)
        frame = urwid.Frame(
            lbox,
            header=urwid.Text("Pick"),
            footer=urwid.Columns([urwid.Button("ok"), urwid.Button("no")]),
            flow=True,
        )
        overlay = urwid.Overlay(
            urwid.LineBox(frame),
            urwid.SolidFill("#"),
            urwid.CENTER,
            16,
            urwid.MIDDLE,
            urwid.PACK,
            shrink_to_fit=True,
        )
        size = (18, 4)
        self.assertEqual(
            ["#┌──────────────┐#", "#│< b0         >│#", "#│< ok  >< no  >│#", "#└──────────────┘#"],
            urwid.testing.render_text(overlay, size, focus=True),
        )
        self.assertEqual([], urwid.testing.press(overlay, size, *["down"] * 5))
        self.assertEqual(5, lbox.focus_position)
        self.assertEqual("#│< b5         >│#", urwid.testing.render_text(overlay, size, focus=True)[1])
        self.assertEqual(10, len(urwid.testing.render_text(overlay, (18, 12), focus=True)) - 2)

    def test_repr(self) -> None:
        """The flag is shown in the repr when it is set."""
        for flow in (False, True):
            with self.subTest(flow=flow):
                frame = urwid.Frame(self.make_list(1), flow=flow)
                self.assertEqual(flow, "flow=True" in repr(frame))
                self.assertIn(("flow", flow, False), list(frame.__rich_repr__()))


class ReducesToFrame:
    """Reduces to a ``Frame`` with the given state, which copies restore as pickles do."""

    def __init__(self, state: object) -> None:
        """Keep the state to restore."""
        self.state = state

    def __reduce__(self) -> tuple[object, ...]:
        """Return the reduction a pickled ``Frame`` has, with the kept state."""
        return (urwid.Frame.__new__, (urwid.Frame,), self.state)


class EqualsBody:
    """Compares equal to ``'body'`` without being a string."""

    __hash__ = None  # type: ignore[assignment]

    def __eq__(self, other: object) -> bool:
        """Return whether *other* is ``'body'``."""
        return other == "body"


class FrameFocusChangedSignalTest(unittest.TestCase):
    """``Frame`` sends ``"focus changed"`` after its focus part changed."""

    def test_signal(self) -> None:
        """Report every way to move the focus once.

        Construction and same-part changes are not reported.
        """
        frame = urwid.Frame(
            urwid.Filler(SelectableText("body")),
            SelectableText("header"),
            SelectableText("footer"),
            focus_part="header",
            select_navigation=True,
        )
        seen: list[tuple[urwid.Widget, str, str, str, bool]] = []

        def record(sender: urwid.Widget, old: str, new: str) -> None:
            seen.append((sender, old, new, frame.focus_part, frame.footer is None))

        urwid.connect_signal(frame, "focus changed", record)
        frame.focus_position = "header"  # unchanged: not reported
        frame.focus_position = "body"
        self.assertIsNone(frame.keypress((10, 5), "tab"))
        frame.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        frame.contents["header"] = (SelectableText("other header"), None)  # same part: not reported
        frame.focus_part = "footer"
        del frame.contents["footer"]
        self.assertEqual(
            [
                (frame, "header", "body", "body", False),
                (frame, "body", "footer", "footer", False),
                (frame, "footer", "header", "header", False),
                (frame, "header", "footer", "footer", False),
                (frame, "footer", "body", "body", True),
            ],
            seen,
        )

    def test_set_before_init(self) -> None:
        """A subclass may set the focus part before it calls the base constructor."""

        class Preset(urwid.Frame[urwid.SolidFill, SelectableText, None]):
            """A frame that chooses its focus part before the base constructor runs."""

            def __init__(self) -> None:
                self.focus_part = "header"
                super().__init__(urwid.SolidFill(), SelectableText("header"), focus_part="header")

        self.assertEqual("header", Preset().focus_part)

    def test_old_pickle_state(self) -> None:
        """The state of urwid 5.0.x, with ``focus_part`` in place of ``_focus_part``, restores the focus part."""
        frame: urwid.Frame[urwid.SolidFill, urwid.Text, None] = urwid.Frame(
            urwid.SolidFill(),
            urwid.Text("header"),
            focus_part="header",
        )
        self.assertEqual("header", copy.copy(frame).focus_part)
        old_state = {("focus_part" if name == "_focus_part" else name): value for name, value in vars(frame).items()}
        for state in (old_state, (old_state, None)):
            with self.subTest(type(state).__name__):
                restored = typing.cast(
                    "urwid.Frame[urwid.SolidFill, urwid.Text, None]",
                    copy.copy(ReducesToFrame(state)),
                )
                self.assertIs(urwid.Frame, type(restored))
                self.assertNotIn("focus_part", vars(restored))
                self.assertEqual("header", restored.focus_part)

    def test_focus_part_slot(self) -> None:
        """A subclass that keeps the focus part in a slot copies and reports focus changes."""

        class SlotFrame(urwid.Frame[urwid.SolidFill, urwid.Text, None]):
            """A frame whose focus part is a slot."""

            __slots__ = ("_focus_part",)

        frame = SlotFrame(urwid.SolidFill(), urwid.Text("header"), focus_part="header")
        self.assertEqual("header", copy.copy(frame).focus_part)
        # the state of urwid 5.0.x has the focus part in the dictionary, not in the slot
        restored = SlotFrame.__new__(SlotFrame)
        restored.__setstate__({**vars(frame), "focus_part": "header"})
        self.assertEqual("header", restored.focus_part)
        seen: list[tuple[str, str]] = []

        def record(_sender: urwid.Widget, old: str, new: str) -> None:
            seen.append((old, new))

        urwid.connect_signal(frame, "focus changed", record)
        frame.focus_position = "body"
        self.assertEqual([("header", "body")], seen)

    def test_bad_pickle_state(self) -> None:
        """A state without a valid focus part is rejected."""
        state = vars(urwid.Frame(urwid.SolidFill()))
        missing = {name: value for name, value in state.items() if name != "_focus_part"}
        bad_states: dict[str, object] = {
            "missing": missing,
            "invalid": {**state, "_focus_part": "middle"},
            "invalid old": {**missing, "focus_part": None},
            "unhashable": {**state, "_focus_part": ["body"]},
            "both names": {**state, "focus_part": "body"},
            "dictionary and slot": (state, {"_focus_part": "middle"}),
            "equal only": {**state, "_focus_part": EqualsBody()},
        }
        for label, bad_state in bad_states.items():
            with self.subTest(label), self.assertRaises(ValueError):
                copy.copy(ReducesToFrame(bad_state))

    def test_subclass_signals(self) -> None:
        """A subclass with its own signals list and a forwarding ``__getattr__`` keeps ``"focus changed"``."""

        class Labelled(urwid.Frame[urwid.SolidFill, SelectableText, None]):
            """A frame that declares a signal of its own."""

            signals: typing.ClassVar[list[str]] = ["labelled"]

            def __init__(self) -> None:
                super().__init__(urwid.SolidFill(), SelectableText("header"))
                self.label = "set after the base"

            def __getattr__(self, name: str) -> object:
                # forwards unknown names to an attribute set only after the base __init__
                return getattr(self.label, name)

        frame = Labelled()
        seen: list[tuple[str, str]] = []

        def record(_sender: urwid.Widget, old: str, new: str) -> None:
            seen.append((old, new))

        urwid.connect_signal(frame, "focus changed", record)
        frame.focus_position = "header"
        self.assertEqual(["labelled", "focus changed"], Labelled.signals)
        self.assertEqual([("body", "header")], seen)
