from __future__ import annotations

import unittest

import urwid


class PaddingTest(unittest.TestCase):
    def test_fixed(self):
        """Test real-world like scenario with padded contents."""
        col_list = [
            urwid.SolidFill(),
            urwid.Button("OK", align=urwid.CENTER),
            urwid.SolidFill(),
            urwid.Button("Cancel", align=urwid.CENTER),
            urwid.SolidFill(),
        ]
        body = urwid.Pile(
            (
                (urwid.Text("Window content text here and it should not touch line", align=urwid.CENTER)),
                (urwid.PACK, urwid.Columns(col_list, dividechars=1, box_columns=(0, 2, 4))),
            )
        )
        widget = urwid.LineBox(
            urwid.Pile(
                (
                    urwid.Text("Modal window", align=urwid.CENTER),
                    urwid.Divider("─"),
                    urwid.Padding(body, width=urwid.PACK, left=1, right=1),
                )
            )
        )
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

        cols, rows = 57, 6
        self.assertEqual((cols, rows), widget.pack(()))
        canvas = widget.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())
        self.assertEqual(
            [
                "┌───────────────────────────────────────────────────────┐",
                "│                      Modal window                     │",
                "│───────────────────────────────────────────────────────│",
                "│ Window content text here and it should not touch line │",
                "│            <   OK   >            < Cancel >           │",
                "└───────────────────────────────────────────────────────┘",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )

    def ptest(self, desc, align, width, maxcol, left, right, min_width=None):
        p = urwid.Padding(None, align, width, min_width)
        l, r = p.padding_values((maxcol,), False)
        assert (l, r) == (left, right), f"{desc} expected {left, right} but got {l, r}"

    def petest(self, desc, align, width):
        self.assertRaises(urwid.PaddingError, lambda: urwid.Padding(None, align, width))

    def test_create(self):
        self.petest("invalid pad", 6, 5)
        self.petest("invalid pad type", ("bad", 2), 5)
        self.petest("invalid width", "center", "42")
        self.petest("invalid width type", "center", ("gouranga", 4))

    def test_values(self):
        self.ptest("left align 5 7", "left", 5, 7, 0, 2)
        self.ptest("left align 7 7", "left", 7, 7, 0, 0)
        self.ptest("left align 9 7", "left", 9, 7, 0, 0)
        self.ptest("right align 5 7", "right", 5, 7, 2, 0)
        self.ptest("center align 5 7", "center", 5, 7, 1, 1)
        self.ptest("fixed left", ("fixed left", 3), 5, 10, 3, 2)
        self.ptest("fixed left reduce", ("fixed left", 3), 8, 10, 2, 0)
        self.ptest("fixed left shrink", ("fixed left", 3), 18, 10, 0, 0)
        self.ptest("fixed left, right", ("fixed left", 3), ("fixed right", 4), 17, 3, 4)
        self.ptest("fixed left, right, min_width", ("fixed left", 3), ("fixed right", 4), 10, 3, 2, 5)
        self.ptest("fixed left, right, min_width 2", ("fixed left", 3), ("fixed right", 4), 10, 2, 0, 8)
        self.ptest("fixed right", ("fixed right", 3), 5, 10, 2, 3)
        self.ptest("fixed right reduce", ("fixed right", 3), 8, 10, 0, 2)
        self.ptest("fixed right shrink", ("fixed right", 3), 18, 10, 0, 0)
        self.ptest("fixed right, left", ("fixed right", 3), ("fixed left", 4), 17, 4, 3)
        self.ptest("fixed right, left, min_width", ("fixed right", 3), ("fixed left", 4), 10, 2, 3, 5)
        self.ptest("fixed right, left, min_width 2", ("fixed right", 3), ("fixed left", 4), 10, 0, 2, 8)
        self.ptest("relative 30", ("relative", 30), 5, 10, 1, 4)
        self.ptest("relative 50", ("relative", 50), 5, 10, 2, 3)
        self.ptest("relative 130 edge", ("relative", 130), 5, 10, 5, 0)
        self.ptest("relative -10 edge", ("relative", -10), 4, 10, 0, 6)
        self.ptest("center relative 70", "center", ("relative", 70), 10, 1, 2)
        self.ptest("center relative 70 grow 8", "center", ("relative", 70), 10, 1, 1, 8)

    def mctest(self, desc, left, right, size, cx, innercx):
        class Inner:
            def __init__(self, desc, innercx):
                self.desc = desc
                self.innercx = innercx

            def move_cursor_to_coords(self, size, cx, cy):
                assert cx == self.innercx, desc

        i = Inner(desc, innercx)
        p = urwid.Padding(i, ("fixed left", left), ("fixed right", right))
        p.move_cursor_to_coords(size, cx, 0)

    def test_cursor(self):
        self.mctest("cursor left edge", 2, 2, (10, 2), 2, 0)
        self.mctest("cursor left edge-1", 2, 2, (10, 2), 1, 0)
        self.mctest("cursor right edge", 2, 2, (10, 2), 7, 5)
        self.mctest("cursor right edge+1", 2, 2, (10, 2), 8, 5)

    def test_reduced_padding_cursor(self):
        # FIXME: This is at least consistent now, but I don't like it.
        # pack() on an Edit should leave room for the cursor
        # fixing this gets deep into things like Edit._shift_view_to_cursor
        # though, so this might not get fixed for a while

        p = urwid.Padding(urwid.Edit("", ""), width="pack", left=4)
        self.assertEqual(p.render((10,), True).cursor, None)
        self.assertEqual(p.get_cursor_coords((10,)), None)
        self.assertEqual(p.render((4,), True).cursor, None)
        self.assertEqual(p.get_cursor_coords((4,)), None)

        p = urwid.Padding(urwid.Edit("", ""), width=("relative", 100), left=4)
        self.assertEqual(p.render((10,), True).cursor, (4, 0))
        self.assertEqual(p.get_cursor_coords((10,)), (4, 0))
        self.assertEqual(p.render((4,), True).cursor, None)
        self.assertEqual(p.get_cursor_coords((4,)), None)
