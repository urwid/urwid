from __future__ import annotations

import unittest

import urwid


class PaddingTest(unittest.TestCase):
    def test_sizing(self) -> None:
        fixed_only = urwid.BigText("3", urwid.HalfBlock5x4Font())
        fixed_flow = urwid.Text("Some text", align=urwid.CENTER)
        flow_only = urwid.ProgressBar(None, None)

        with self.subTest("Fixed only"):
            widget = urwid.Padding(fixed_only)
            self.assertEqual(frozenset((urwid.FIXED,)), widget.sizing())

            cols, rows = 5, 4
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "▄▀▀▄ ",
                    "  ▄▀ ",
                    "▄  █ ",
                    " ▀▀  ",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("Fixed only + relative size & default align"):
            widget = urwid.Padding(fixed_only, width=(urwid.RELATIVE, 50))
            self.assertEqual(frozenset((urwid.FIXED,)), widget.sizing())

            cols, rows = 10, 4
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "▄▀▀▄      ",
                    "  ▄▀      ",
                    "▄  █      ",
                    " ▀▀       ",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("FIXED/FLOW"):
            widget = urwid.Padding(fixed_flow)
            self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

            cols, rows = 9, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                ["Some text"],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("FIXED/FLOW + relative size & right align"):
            widget = urwid.Padding(fixed_flow, width=(urwid.RELATIVE, 65), align=urwid.RIGHT)
            self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

            cols, rows = 14, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                ["     Some text"],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("GIVEN FLOW make FIXED"):
            widget = urwid.Padding(flow_only, width=5, align=urwid.RIGHT, right=1)
            self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

            cols, rows = 6, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [" 0 %  "],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("GIVEN FIXED = error"):
            widget = urwid.Padding(fixed_only, width=5)
            with self.assertWarns(urwid.widget.padding.PaddingWarning) as ctx, self.assertRaises(AttributeError):
                widget.sizing()
                self.assertEqual(
                    f"WHSettings.GIVEN expect BOX or FLOW widget to be used, but received {fixed_only}",
                    str(ctx.warnings[0].message),
                )

                widget.pack(())
                self.assertEqual(
                    f"WHSettings.GIVEN expect BOX or FLOW widget to be used, but received {fixed_only}",
                    str(ctx.warnings[1].message),
                )

            with self.assertRaises(ValueError) as err_ctx:
                widget.render(())

            self.assertEqual(
                "FixedWidget takes only () for size.passed: (5,)",
                str(err_ctx.exception),
            )

    def test_fixed(self) -> None:
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
        # Forward keypress
        self.assertEqual("OK", body.focus.focus.label)
        widget.keypress((), "right")
        self.assertEqual("Cancel", body.focus.focus.label)

    def test_insufficient_space(self):
        width = 10
        widget = urwid.Padding(urwid.Text("Some text"), width=width)
        with self.assertWarns(urwid.widget.PaddingWarning) as ctx:
            canvas = widget.render((width - 1,))
        self.assertEqual("Some text", str(canvas))
        self.assertEqual(width - 1, canvas.cols())

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

    def test_left_right_padding_around_text(self) -> None:
        """Inner padding."""
        padded = urwid.Padding(urwid.Text("OK"), left=1, right=1)

        self.assertEqual((4, 1), padded.pack(()))
        self.assertEqual([b" OK "], padded.render(()).text)
        self.assertEqual([b" OK   "], padded.render((6,)).text)

    def test_width_none_becomes_clip(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width=None)
        self.assertEqual(urwid.CLIP, widget.width)

    def test_sizing_clip(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width="clip")
        self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())

    def test_sizing_given_box_only_widget(self) -> None:
        """GIVEN width with a BOX-only widget should not warn (BOX in sizing)."""
        widget = urwid.Padding(urwid.SolidFill(), width=5)
        self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())

    def test_align_setter(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        widget.align = urwid.RIGHT
        self.assertEqual(urwid.RIGHT, widget.align)

    def test_width_setter(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        widget.width = 7
        self.assertEqual(7, widget.width)

    def test_pack_with_size(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        self.assertEqual((10, 1), widget.pack((10,), False))

    def test_pack_clip_raises(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width="clip")
        with self.assertRaises(urwid.PaddingError):
            widget.pack(())

    def test_padding_values_clip_no_size_raises(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width="clip")
        with self.assertRaises(urwid.PaddingError):
            widget.padding_values((), False)

    def test_pack_fixed_not_supported_warns(self) -> None:
        class FlowOnlyButPackable(urwid.Text):
            def sizing(self):
                return frozenset((urwid.FLOW,))

            def pack(self, size=(), focus=False):
                return (5, 1)

        widget = urwid.Padding(FlowOnlyButPackable("hi"), width=urwid.PACK)
        with self.assertWarns(urwid.widget.padding.PaddingWarning):
            self.assertEqual((5, 1), widget.pack(()))

    def test_pack_unexpected_width_type(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width=urwid.PACK)
        widget._width_type = "bogus"
        with self.assertRaises(urwid.PaddingError):
            widget.pack(())

    def test_render_clip(self) -> None:
        widget = urwid.Padding(urwid.BigText("1", urwid.HalfBlock5x4Font()), width="clip")
        canvas = widget.render((10,))
        self.assertEqual(10, canvas.cols())

    def test_render_empty_widget_no_size_raises(self) -> None:
        class EmptyFixed(urwid.Widget):
            _sizing = frozenset((urwid.FIXED,))

            def sizing(self):
                return frozenset((urwid.FIXED,))

            def pack(self, size=(), focus=False):
                return (0, 1)

            def render(self, size, focus=False):
                return urwid.TextCanvas([b""], maxcol=0)

        widget = urwid.Padding(EmptyFixed(), width=urwid.PACK)
        with self.assertRaises(ValueError):
            widget.render(())

    def test_padding_values_clip(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width="clip")
        self.assertEqual((0, 8), widget.padding_values((10,), False))

    def test_padding_values_pack_no_size(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width=urwid.PACK)
        self.assertEqual((0, 0), widget.padding_values((), False))

    def test_rows_clip(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"), width="clip")
        self.assertEqual(1, widget.rows((10,), False))

    def test_keypress_no_size(self) -> None:
        widget = urwid.Padding(urwid.Edit("", "hi"), width=urwid.PACK)
        self.assertEqual("right", widget.keypress((), "right"))

    def test_get_cursor_coords_no_attribute(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        self.assertIsNone(widget.get_cursor_coords((10,)))

    def test_get_cursor_coords_zero_width(self) -> None:
        widget = urwid.Padding(urwid.Edit("", "hi"), left=5, right=5)
        self.assertIsNone(widget.get_cursor_coords((10,)))

    def test_get_cursor_coords_no_size(self) -> None:
        class Stub(urwid.Text):
            def pack(self, size=(), focus=False):
                return (5, 1)

            def sizing(self):
                return frozenset((urwid.FIXED, urwid.FLOW))

            def get_cursor_coords(self, size):
                return (1, 0)

        widget = urwid.Padding(Stub("hi"), width=urwid.PACK)
        self.assertEqual((1, 0), widget.get_cursor_coords(()))

    def test_get_cursor_coords_none_from_original(self) -> None:
        class Stub(urwid.Text):
            def get_cursor_coords(self, size):
                return None

        widget = urwid.Padding(Stub("hi"))
        self.assertIsNone(widget.get_cursor_coords((10,)))

    def test_move_cursor_to_coords_no_attribute(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        self.assertTrue(widget.move_cursor_to_coords((10,), 3, 0))

    def test_move_cursor_to_coords_no_size(self) -> None:
        class Stub(urwid.Text):
            def move_cursor_to_coords(self, size, x, y):
                return True

            def pack(self, size=(), focus=False):
                return (5, 1)

            def sizing(self):
                return frozenset((urwid.FIXED, urwid.FLOW))

        widget = urwid.Padding(Stub("hi"), width=urwid.PACK)
        self.assertTrue(widget.move_cursor_to_coords((), 1, 0))

    def test_mouse_event_no_attribute(self) -> None:
        class NoMouse:
            """Plain object without a mouse_event method (unlike urwid.Widget)."""

        widget = urwid.Padding(NoMouse())
        self.assertFalse(widget.mouse_event((10,), "mouse press", 1, 0, 0, True))

    def test_mouse_event_outside_padding(self) -> None:
        widget = urwid.Padding(urwid.Button("OK"), left=3, right=3)
        self.assertFalse(widget.mouse_event((10,), "mouse press", 1, 0, 0, True))

    def test_mouse_event_inside_padding(self) -> None:
        widget = urwid.Padding(urwid.Button("OK"), left=3, right=3)
        self.assertTrue(widget.mouse_event((10,), "mouse press", 1, 4, 0, True))

    def test_mouse_event_no_size(self) -> None:
        class Stub(urwid.Text):
            def pack(self, size=(), focus=False):
                return (5, 1)

            def sizing(self):
                return frozenset((urwid.FIXED, urwid.FLOW))

            def mouse_event(self, size, event, button, col, row, focus):
                return True

        widget = urwid.Padding(Stub("hi"), width=urwid.PACK)
        self.assertTrue(widget.mouse_event((), "mouse press", 1, 1, 0, True))

    def test_get_pref_col_no_attribute(self) -> None:
        widget = urwid.Padding(urwid.Text("hi"))
        self.assertIsNone(widget.get_pref_col((10,)))

    def test_get_pref_col_with_size(self) -> None:
        widget = urwid.Padding(urwid.Edit("", "hi"), left=2, right=2)
        self.assertEqual(4, widget.get_pref_col((10,)))

    def test_get_pref_col_no_size(self) -> None:
        class Stub(urwid.Text):
            def pack(self, size=(), focus=False):
                return (5, 1)

            def sizing(self):
                return frozenset((urwid.FIXED, urwid.FLOW))

            def get_pref_col(self, size):
                return 2

        widget = urwid.Padding(Stub("hi"), left=2, right=2, width=urwid.PACK)
        self.assertEqual(4, widget.get_pref_col(()))

    def test_get_pref_col_non_int(self) -> None:
        class Stub(urwid.Text):
            def pack(self, size=(), focus=False):
                return (5, 1)

            def sizing(self):
                return frozenset((urwid.FIXED, urwid.FLOW))

            def get_pref_col(self, size):
                return None

        widget = urwid.Padding(Stub("hi"), width=urwid.PACK)
        self.assertIsNone(widget.get_pref_col((10,)))

    def test_calculate_left_right_padding_relative_align_requires_amount(self) -> None:
        with self.assertRaises(TypeError):
            urwid.widget.padding.calculate_left_right_padding(
                10,
                urwid.widget.padding.WHSettings.RELATIVE,
                None,
                urwid.widget.padding.WHSettings.GIVEN,
                5,
                None,
                0,
                0,
            )
