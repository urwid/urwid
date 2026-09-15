from __future__ import annotations

import unittest

import urwid


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
