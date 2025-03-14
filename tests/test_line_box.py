from __future__ import annotations

import unittest

import urwid
from urwid.util import get_encoding


class LineBoxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_linebox_pack(self):
        # Bug #346 'pack' Padding does not run with LineBox
        t = urwid.Text("AAA\nCCC\nDDD")
        size = t.pack()
        l = urwid.LineBox(t)

        self.assertEqual(l.pack()[0], size[0] + 2)
        self.assertEqual(l.pack()[1], size[1] + 2)

    def test_border(self):
        wrapped = urwid.Text("Text\non\nfour\nlines", align=urwid.CENTER)
        l = urwid.LineBox(wrapped, tlcorner="╭", trcorner="╮", blcorner="╰", brcorner="╯")
        cols, rows = 7, 6
        self.assertEqual((cols, rows), l.pack(()))

        canvas = l.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())

        self.assertEqual(
            [
                "╭─────╮",
                "│ Text│",
                "│  on │",
                "│ four│",
                "│lines│",
                "╰─────╯",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )

    def test_header(self):
        wrapped = urwid.Text("Some text")
        l = urwid.LineBox(wrapped, title="Title", tlcorner="╭", trcorner="╮", blcorner="╰", brcorner="╯")
        cols, rows = 11, 3
        self.assertEqual((cols, rows), l.pack(()))

        canvas = l.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())

        self.assertEqual(
            [
                "╭─ Title ─╮",
                "│Some text│",
                "╰─────────╯",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )

        l.set_title("New")
        self.assertEqual(
            [
                "╭── New ──╮",
                "│Some text│",
                "╰─────────╯",
            ],
            [line.decode("utf-8") for line in l.render(()).text],
        )

    def test_negative(self):
        wrapped = urwid.Text("")
        with self.assertRaises(ValueError) as ctx:
            l = urwid.LineBox(wrapped, title="Title", tline="")

        self.assertEqual("Cannot have a title when tline is empty string", str(ctx.exception))

        l = urwid.LineBox(wrapped, tline="")
        with self.assertRaises(ValueError) as ctx:
            l.set_title("Fail")

        self.assertEqual("Cannot set title when tline is unset", str(ctx.exception))

    def test_partial_contour(self):
        def mark_pressed(btn: urwid.Button) -> None:
            nonlocal pressed

            pressed = True

        pressed = False
        wrapped = urwid.Button("Wrapped", on_press=mark_pressed)

        with self.subTest("No top line -> no top"):
            l = urwid.LineBox(wrapped, tline="")
            cols, rows = 13, 2
            self.assertEqual((cols, rows), l.pack(()))

            canvas = l.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                [
                    "│< Wrapped >│",
                    "└───────────┘",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )
            self.assertIsNone(l.keypress((), "enter"))
            self.assertTrue(pressed)

        pressed = False

        with self.subTest("No right side elements -> no side"):
            l = urwid.LineBox(wrapped, rline="")
            cols, rows = 12, 3
            self.assertEqual((cols, rows), l.pack(()))

            canvas = l.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                [
                    "┌───────────",
                    "│< Wrapped >",
                    "└───────────",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )
            self.assertIsNone(l.keypress((), "enter"))
            self.assertTrue(pressed)

        pressed = False

        with self.subTest("No left side elements -> no side"):
            l = urwid.LineBox(wrapped, lline="")
            cols, rows = 12, 3
            self.assertEqual((cols, rows), l.pack(()))

            canvas = l.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                [
                    "───────────┐",
                    "< Wrapped >│",
                    "───────────┘",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )
            self.assertIsNone(l.keypress((), "enter"))
            self.assertTrue(pressed)

        pressed = False

        with self.subTest("No bottom line -> no bottom"):
            l = urwid.LineBox(wrapped, bline="")
            cols, rows = 13, 2
            self.assertEqual((cols, rows), l.pack(()))

            canvas = l.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                [
                    "┌───────────┐",
                    "│< Wrapped >│",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )
            self.assertIsNone(l.keypress((), "enter"))
            self.assertTrue(pressed)

        pressed = False

    def test_columns_of_lineboxes(self):
        # BUG #748
        # Using PACK: width of widget 1 is 4, width of widget 2 is 5.
        # With equal weight widget 1 will be rendered also 5.
        columns = urwid.Columns(
            [
                (urwid.PACK, urwid.LineBox(urwid.Text("lol"), rline="", trcorner="", brcorner="")),
                (urwid.PACK, urwid.LineBox(urwid.Text("wtf"), tlcorner="┬", blcorner="┴")),
            ]
        )
        canvas = columns.render(())
        self.assertEqual(
            [
                "┌───┬───┐",
                "│lol│wtf│",
                "└───┴───┘",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )

    def test_replace_widget(self):
        old_widget = urwid.Text("some text")
        lb_widget = urwid.LineBox(old_widget)
        canvas = lb_widget.render(())
        self.assertEqual(
            [
                "┌─────────┐",
                "│some text│",
                "└─────────┘",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )
        self.assertIs(old_widget, lb_widget.original_widget)
        new_widget = urwid.widget.Button("now it's a button")
        lb_widget.original_widget = new_widget
        canvas = lb_widget.render(())
        self.assertEqual(
            [
                "┌─────────────────────┐",
                "│< now it's a button >│",
                "└─────────────────────┘",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )
        self.assertIs(new_widget, lb_widget.original_widget)
