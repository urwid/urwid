from __future__ import annotations

import unittest

import urwid


class OverlayTest(unittest.TestCase):
    def test_sizing_flow_fixed(self) -> None:
        top_w = urwid.Text("Flow and Fixed widget")
        bottom_w = urwid.SolidFill("#")
        widgets = {"top_w": top_w, "bottom_w": bottom_w}

        for description, kwargs, sizing in (
            (
                "Fixed render no size",
                {
                    **widgets,
                    "align": urwid.CENTER,
                    "width": None,
                    "valign": urwid.MIDDLE,
                    "height": None,
                },
                frozenset((urwid.BOX, urwid.FIXED)),
            ),
            (
                "Fixed render + corners",
                {
                    **widgets,
                    "align": urwid.CENTER,
                    "width": None,
                    "valign": urwid.MIDDLE,
                    "height": None,
                    "left": 1,
                    "right": 1,
                    "top": 1,
                    "bottom": 1,
                },
                frozenset((urwid.BOX, urwid.FIXED)),
            ),
            (
                "Fixed render from FLOW",
                {
                    **widgets,
                    "align": urwid.CENTER,
                    "width": 10,
                    "valign": urwid.MIDDLE,
                    "height": None,
                },
                frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)),
            ),
            (
                "Fixed render from FLOW + corners",
                {
                    **widgets,
                    "align": urwid.CENTER,
                    "width": 10,
                    "valign": urwid.MIDDLE,
                    "height": None,
                    "left": 1,
                    "right": 1,
                    "top": 1,
                    "bottom": 1,
                },
                frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)),
            ),
        ):
            with self.subTest(description):
                widget = urwid.Overlay(**kwargs)
                self.assertEqual(sizing, widget.sizing())

                def_cols, def_rows = top_w.pack()

                if kwargs["width"] is None:
                    args_cols = def_cols
                else:
                    args_cols = kwargs["width"]

                cols = args_cols + kwargs.get("left", 0) + kwargs.get("right", 0)
                rows = top_w.rows((args_cols,)) + kwargs.get("top", 0) + kwargs.get("bottom", 0)
                self.assertEqual((cols, rows), widget.pack(()))

                canvas = widget.render(())
                self.assertEqual(cols, canvas.cols())
                self.assertEqual(rows, canvas.rows())

        with self.subTest("Fixed Relative"):
            min_width = 23
            relative_width = 90
            widget = urwid.Overlay(
                top_w,
                bottom_w,
                align=urwid.CENTER,
                width=(urwid.RELATIVE, relative_width),
                valign=urwid.MIDDLE,
                height=None,
                min_width=23,
            )
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols = int(min_width * 100 / relative_width + 0.5)
            rows = top_w.rows((min_width,))
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual("#Flow and Fixed widget  ##", str(canvas))

        with self.subTest("Flow Relative"):
            cols = 25
            min_width = 23
            relative_width = 90
            widget = urwid.Overlay(
                top_w,
                bottom_w,
                align=urwid.CENTER,
                width=(urwid.RELATIVE, relative_width),
                valign=urwid.MIDDLE,
                height=None,
                min_width=23,
            )
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

            rows = top_w.rows((min_width,))
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual("#Flow and Fixed widget  #", str(canvas))

        with self.subTest("Fixed Relative + corners"):
            min_width = 23
            relative_width = 90
            widget = urwid.Overlay(
                top_w,
                bottom_w,
                align=urwid.CENTER,
                width=(urwid.RELATIVE, relative_width),
                valign=urwid.MIDDLE,
                height=None,
                min_width=23,
                top=1,
                bottom=1,
            )
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols = int(min_width * 100 / relative_width + 0.5)
            rows = top_w.rows((min_width,)) + 2
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                "##########################\n" "#Flow and Fixed widget  ##\n" "##########################",
                str(canvas),
            )

        with self.subTest("Fixed Relative + corners"):
            cols = 25
            min_width = 23
            relative_width = 90
            widget = urwid.Overlay(
                top_w,
                bottom_w,
                align=urwid.CENTER,
                width=(urwid.RELATIVE, relative_width),
                valign=urwid.MIDDLE,
                height=None,
                min_width=23,
                top=1,
                bottom=1,
            )
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

            rows = top_w.rows((min_width,)) + 2
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual(
                "#########################\n" "#Flow and Fixed widget  #\n" "#########################",
                str(canvas),
            )

    def test_sizing_box_fixed_given(self):
        top_w = urwid.SolidFill("*")
        bottom_w = urwid.SolidFill("#")

        min_width = 5
        min_height = 3

        widget = urwid.Overlay(
            top_w,
            bottom_w,
            align=urwid.CENTER,
            width=min_width,
            valign=urwid.MIDDLE,
            height=min_height,
            top=1,
            bottom=1,
            left=2,
            right=2,
        )
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

        cols = min_width + 4
        rows = min_height + 2
        for description, call_args in (
            ("All GIVEN FIXED", ()),
            ("ALL GIVEN FLOW", (cols,)),
            ("ALL GIVEN BOX", (cols, rows)),
        ):
            with self.subTest(description):
                self.assertEqual((cols, rows), widget.pack(call_args))
                canvas = widget.render(call_args)
                self.assertEqual(cols, canvas.cols())
                self.assertEqual(rows, canvas.rows())

                self.assertEqual(
                    [
                        "#########",
                        "##*****##",
                        "##*****##",
                        "##*****##",
                        "#########",
                    ],
                    [line.decode("utf-8") for line in canvas.text],
                )

    def test_sizing_box_fixed_relative(self):
        top_w = urwid.SolidFill("*")
        bottom_w = urwid.SolidFill("#")

        relative_width = 50
        relative_height = 50
        min_width = 4
        min_height = 2

        widget = urwid.Overlay(
            top_w,
            bottom_w,
            align=urwid.CENTER,
            width=(urwid.RELATIVE, relative_width),
            valign=urwid.MIDDLE,
            height=(urwid.RELATIVE, relative_height),
            min_width=min_width,
            min_height=min_height,
            top=1,
            bottom=1,
            left=2,
            right=2,
        )
        cols = int(min_width * 100 / relative_width + 0.5)
        rows = int(min_height * 100 / relative_height + 0.5)
        for description, call_args in (
            ("All GIVEN FIXED", ()),
            ("ALL GIVEN FLOW", (cols,)),
            ("ALL GIVEN BOX", (cols, rows)),
        ):
            with self.subTest(description):
                self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

                self.assertEqual((cols, rows), widget.pack(call_args))
                canvas = widget.render(call_args)
                self.assertEqual(cols, canvas.cols())
                self.assertEqual(rows, canvas.rows())

                self.assertEqual(
                    [
                        "########",
                        "##****##",
                        "##****##",
                        "########",
                    ],
                    [line.decode("utf-8") for line in canvas.text],
                )

    def test_relative(self):
        ovl = urwid.Overlay(
            urwid.Text("aaa"),
            urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE),
            width=urwid.PACK,
            height=urwid.PACK,
            align=(urwid.RELATIVE, 30),
            valign=(urwid.RELATIVE, 70),
        )
        self.assertEqual(
            ovl.contents[1][1],
            (urwid.RELATIVE, 30, urwid.PACK, None, None, 0, 0, urwid.RELATIVE, 70, urwid.PACK, None, None, 0, 0),
        )
        self.assertEqual(
            (
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░aaa░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
                "░░░░░░░░░░░░░░░░░░░░",
            ),
            ovl.render((20, 10)).decoded_text,
        )

    def test_old_params(self):
        o1 = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            ("fixed left", 5),
            ("fixed right", 4),
            ("fixed top", 3),
            ("fixed bottom", 2),
        )
        self.assertEqual(
            o1.contents[1][1],
            ("left", None, "relative", 100, None, 5, 4, "top", None, "relative", 100, None, 3, 2),
        )
        o2 = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            ("fixed right", 5),
            ("fixed left", 4),
            ("fixed bottom", 3),
            ("fixed top", 2),
        )
        self.assertEqual(
            o2.contents[1][1],
            ("right", None, "relative", 100, None, 4, 5, "bottom", None, "relative", 100, None, 2, 3),
        )

    def test_get_cursor_coords(self):
        self.assertEqual(
            urwid.Overlay(
                urwid.Filler(urwid.Edit()),
                urwid.SolidFill("B"),
                "right",
                1,
                "bottom",
                1,
            ).get_cursor_coords((2, 2)),
            (1, 1),
        )

    def test_length(self):
        ovl = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("O"),
            "center",
            ("relative", 20),
            "middle",
            ("relative", 20),
        )
        self.assertEqual(2, len(ovl))
        self.assertEqual(2, len(ovl.contents))

    def test_common(self):
        s1 = urwid.SolidFill("1")
        s2 = urwid.SolidFill("2")
        o = urwid.Overlay(s1, s2, "center", ("relative", 50), "middle", ("relative", 50))
        self.assertEqual(o.focus, s1)
        self.assertEqual(o.focus_position, 1)
        self.assertRaises(IndexError, lambda: setattr(o, "focus_position", None))
        self.assertRaises(IndexError, lambda: setattr(o, "focus_position", 2))

        self.assertEqual(o.contents[0], (s2, urwid.Overlay._DEFAULT_BOTTOM_OPTIONS))
        self.assertEqual(
            o.contents[1],
            (s1, ("center", None, "relative", 50, None, 0, 0, "middle", None, "relative", 50, None, 0, 0)),
        )
