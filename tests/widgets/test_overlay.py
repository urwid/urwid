from __future__ import annotations

import unittest
import warnings

import urwid
from urwid.widget import overlay as overlay_mod


class NotAWidget:
    """A top widget deliberately missing the :class:`urwid.AbstractWidget` protocol methods.

    See :meth:`Pile._check_widget_subclass` (`tests/widgets/test_pile.py`) for the same pattern.
    """


class FixedCursorSolidFill(urwid.SolidFill):
    """A box widget reporting a cursor row far beyond any size it will ever be rendered at."""

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int]:
        return 0, 100


class ZeroHeightFixed(urwid.Widget):
    """A FIXED widget whose `pack()` reports zero rows."""

    _sizing = frozenset((urwid.FIXED,))

    def pack(self, size: tuple[()] = (), focus: bool = False) -> tuple[int, int]:
        return 5, 0

    def render(self, size: tuple[()] | tuple[int, int], focus: bool = False) -> urwid.Canvas:
        maxcol, maxrow = size or (5, 0)
        return urwid.SolidCanvas(" ", maxcol, maxrow)


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
                "##########################\n#Flow and Fixed widget  ##\n##########################",
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
                "#########################\n#Flow and Fixed widget  #\n#########################",
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

    def test_pack_width_not_fitting_is_clipped(self):
        """An oversized PACK width is clipped into the available columns instead of raising.

        Regression test: negative padding used to be passed to the canvas overlay as a position,
        producing a canvas wider than the size requested.
        """
        top_w = urwid.Text("Some long text")
        self.assertEqual((14, 1), top_w.pack(()))

        ovl = urwid.Overlay(
            top_w,
            urwid.SolidFill("#"),
            urwid.CENTER,
            urwid.PACK,
            urwid.MIDDLE,
            urwid.PACK,
        )
        self.assertEqual((-2, -2, 1, 1), ovl.calculate_padding_filler((10, 3), False))

        canvas = ovl.render((10, 3))
        self.assertEqual(10, canvas.cols())
        self.assertEqual(3, canvas.rows())
        self.assertEqual(("##########", "me long te", "##########"), canvas.decoded_text)

        with self.subTest("clipped on both axes"):
            top_w = urwid.LineBox(urwid.Text("Some long text"))
            self.assertEqual((16, 3), top_w.pack(()))

            ovl = urwid.Overlay(
                top_w,
                urwid.SolidFill("#"),
                urwid.CENTER,
                urwid.PACK,
                urwid.MIDDLE,
                urwid.PACK,
            )
            self.assertEqual((-3, -3, 0, -1), ovl.calculate_padding_filler((10, 2), False))

            canvas = ovl.render((10, 2))
            self.assertEqual(10, canvas.cols())
            self.assertEqual(2, canvas.rows())
            self.assertEqual(("──────────", "me long te"), canvas.decoded_text)

    def test_pack_height_measured_at_top_widget_width(self):
        """A PACK height is measured at the width top_w is given, not at the full width.

        Regression test for https://github.com/urwid/urwid/issues/471: the row count was measured
        at the full width of the overlay, so a wrapping flow widget was placed too low
        and mouse events below the wrapped text were dropped.
        """
        check_box = urwid.CheckBox("x")
        top_w = urwid.Pile([urwid.Text("one two three"), check_box])
        self.assertEqual(4, top_w.rows((5,)))
        self.assertEqual(2, top_w.rows((20,)))

        ovl = urwid.Overlay(top_w, urwid.SolidFill("#"), urwid.CENTER, 5, urwid.MIDDLE, urwid.PACK)
        self.assertEqual((7, 8, 3, 3), ovl.calculate_padding_filler((20, 10), False))

        self.assertEqual(
            (
                "####################",
                "####################",
                "####################",
                "#######one  ########",
                "#######two  ########",
                "#######three########",
                "#######[ ] x########",
                "####################",
                "####################",
                "####################",
            ),
            ovl.render((20, 10)).decoded_text,
        )

        # the check box is rendered on the last row of top_w, so a click there must reach it
        self.assertTrue(ovl.mouse_event((20, 10), "mouse press", 1, 8, 6, True))
        self.assertTrue(check_box.state)

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

    def test_replaced_top_w_is_rendered(self):
        """Replacing the top widget invalidates the canvas rendered from the previous one.

        Regression test: `top_w` used to be a plain attribute, so the canvas cached for the
        overlay survived the replacement and the old widget kept being rendered until something
        else invalidated the overlay. The first canvas is kept referenced on purpose:
        :class:`urwid.CanvasCache` holds weak references, so a canvas dropped by the test takes
        the stale cache entry with it and the replacement would render correctly either way.
        """
        ovl = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("."),
            urwid.CENTER,
            4,
            urwid.MIDDLE,
            2,
        )
        cached = ovl.render((8, 4))
        self.assertEqual(("........", "..XXXX..", "..XXXX..", "........"), cached.decoded_text)

        ovl.top_w = urwid.SolidFill("O")

        self.assertEqual(("........", "..OOOO..", "..OOOO..", "........"), ovl.render((8, 4)).decoded_text)

    def test_replaced_bottom_w_is_rendered(self):
        """Replacing the bottom widget invalidates the canvas rendered from the previous one.

        The counterpart of `test_replaced_top_w_is_rendered`, keeping the first canvas referenced
        for the same reason.
        """
        ovl = urwid.Overlay(
            urwid.SolidFill("X"),
            urwid.SolidFill("."),
            urwid.CENTER,
            4,
            urwid.MIDDLE,
            2,
        )
        cached = ovl.render((8, 4))
        self.assertEqual(("........", "..XXXX..", "..XXXX..", "........"), cached.decoded_text)

        ovl.bottom_w = urwid.SolidFill(",")

        self.assertEqual((",,,,,,,,", ",,XXXX,,", ",,XXXX,,", ",,,,,,,,"), ovl.render((8, 4)).decoded_text)

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

    def test_not_a_widget_warns_on_construction(self) -> None:
        """A top widget missing the Widget API triggers the same warning as `Frame`/`Pile`/`Columns`."""
        with self.assertWarns(DeprecationWarning) as ctx:
            urwid.Overlay(
                NotAWidget(),
                urwid.SolidFill("#"),
                urwid.CENTER,
                (urwid.RELATIVE, 100),
                urwid.MIDDLE,
                (urwid.RELATIVE, 100),
            )
        self.assertIn("is not implementing Widget API", str(ctx.warning))

    def test_sizing_warning_pack_width_without_fixed_support(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, None, urwid.MIDDLE, None)
        with self.assertWarns(overlay_mod.OverlayWarning):
            self.assertEqual(frozenset((urwid.BOX,)), ovl.sizing())

    def test_sizing_warning_pack_height_without_flow_support(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, None)
        with self.assertWarns(overlay_mod.OverlayWarning):
            self.assertEqual(frozenset((urwid.BOX,)), ovl.sizing())

    def test_sizing_pack_height_flow_supported_without_fixed_amount(self) -> None:
        """PACK height with a FLOW-capable top widget adds FLOW, but not FIXED without a width amount."""
        ovl = urwid.Overlay(
            urwid.Text("hi"),
            urwid.SolidFill("#"),
            urwid.CENTER,
            (urwid.RELATIVE, 50),
            urwid.MIDDLE,
            None,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), ovl.sizing())

    def test_sizing_given_height_without_given_or_min_skips_flow(self) -> None:
        """A GIVEN height with no matching GIVEN width and no min_height resolves to BOX only."""
        ovl = urwid.Overlay(
            urwid.SolidFill("*"),
            urwid.SolidFill("#"),
            urwid.CENTER,
            10,
            urwid.MIDDLE,
            (urwid.RELATIVE, 50),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(frozenset((urwid.BOX,)), ovl.sizing())

    def test_sizing_box_height_amount_flow_without_fixed_amount(self) -> None:
        """A BOX-capable top widget with height amount adds FLOW, but not FIXED without a width amount."""
        ovl = urwid.Overlay(
            urwid.SolidFill("*"),
            urwid.SolidFill("#"),
            urwid.CENTER,
            (urwid.RELATIVE, 50),
            urwid.MIDDLE,
            (urwid.RELATIVE, 50),
            min_height=5,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), ovl.sizing())

    def test_sizing_warning_height_amount_without_box_support(self) -> None:
        ovl = urwid.Overlay(
            urwid.Text("hi"),
            urwid.SolidFill("#"),
            urwid.CENTER,
            10,
            urwid.MIDDLE,
            (urwid.RELATIVE, 50),
            min_height=5,
        )
        with self.assertWarns(overlay_mod.OverlayWarning):
            self.assertEqual(frozenset((urwid.BOX,)), ovl.sizing())

    def test_pack_errors(self) -> None:
        top_w = urwid.SolidFill("*")
        bottom_w = urwid.SolidFill("#")
        for description, kwargs in (
            ("width_amount falsy", {"width": 0, "height": 5}),
            ("relative width without min_width", {"width": (urwid.RELATIVE, 50), "height": 5}),
            ("height_amount falsy", {"width": 10, "height": 0}),
            ("relative height without min_height", {"width": 10, "height": (urwid.RELATIVE, 50)}),
        ):
            with self.subTest(description):
                ovl = urwid.Overlay(top_w, bottom_w, urwid.CENTER, kwargs["width"], urwid.MIDDLE, kwargs["height"])
                self.assertRaises(overlay_mod.OverlayError, ovl.pack, ())

    def test_rows_given_width_pack_height(self) -> None:
        top_w = urwid.Text("hi")
        ovl = urwid.Overlay(top_w, urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, None)
        self.assertEqual(top_w.rows((10,)), ovl.rows((999,)))

    def test_rows_error_pack_width_and_height(self) -> None:
        ovl = urwid.Overlay(urwid.Text("hi"), urwid.SolidFill("#"), urwid.CENTER, None, urwid.MIDDLE, None)
        self.assertRaises(overlay_mod.OverlayError, ovl.rows, (10,))

    def test_align_width_valign_height_properties(self) -> None:
        ovl = urwid.Overlay(
            urwid.SolidFill("*"),
            urwid.SolidFill("#"),
            align=urwid.CENTER,
            width=10,
            valign=urwid.MIDDLE,
            height=5,
            min_width=3,
            min_height=2,
        )
        self.assertEqual(urwid.CENTER, ovl.align)
        self.assertEqual(10, ovl.width)
        self.assertEqual(urwid.MIDDLE, ovl.valign)
        self.assertEqual(5, ovl.height)

    def test_options_invalid_align_type(self) -> None:
        with self.assertRaises(ValueError):
            urwid.Overlay.options("bogus", None, "given", 5, "top", None, "given", 5)

    def test_options_invalid_valign_type(self) -> None:
        with self.assertRaises(ValueError):
            urwid.Overlay.options("left", None, "given", 5, "bogus", None, "given", 5)

    def test_set_overlay_parameters_invalid_valign(self) -> None:
        with self.assertRaises(overlay_mod.OverlayError):
            urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, 123, 5)

    def test_selectable_delegates_to_top_w(self) -> None:
        ovl = urwid.Overlay(urwid.Edit(), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 1)
        self.assertTrue(ovl.selectable())

        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 1)
        self.assertFalse(ovl.selectable())

    def test_keypress_delegates_to_top_w(self) -> None:
        edit = urwid.Edit()
        ovl = urwid.Overlay(edit, urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 1)
        self.assertIsNone(ovl.keypress((20, 5), "x"))
        self.assertEqual("x", edit.edit_text)

    def test_focus_position_set_to_one_is_noop(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 5)
        ovl.focus_position = 1
        self.assertEqual(1, ovl.focus_position)

    def test_contents_is_fixed_size(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 5)
        with self.assertRaises(TypeError):
            del ovl.contents[0]
        with self.assertRaises(TypeError):
            ovl.contents.insert(0, (urwid.SolidFill("x"), ovl.contents[1][1]))
        self.assertEqual([ovl.contents[0], ovl.contents[1]], list(ovl.contents))

    def test_contents_setter_replaces_bottom_and_top_options(self) -> None:
        top_w = urwid.SolidFill("1")
        ovl = urwid.Overlay(top_w, urwid.SolidFill("2"), urwid.CENTER, 10, urwid.MIDDLE, 5)
        new_bottom = urwid.SolidFill("4")
        new_top = urwid.SolidFill("5")
        new_options = ovl.options(
            urwid.LEFT, None, urwid.WHSettings.GIVEN, 4, urwid.TOP, None, urwid.WHSettings.GIVEN, 2
        )

        ovl.contents = [(new_bottom, ovl._DEFAULT_BOTTOM_OPTIONS), (new_top, new_options)]

        self.assertIs(ovl.bottom_w, new_bottom)
        self.assertIs(ovl.top_w, new_top)
        self.assertEqual((4, 2), (ovl.width, ovl.height))

        with self.assertRaises(ValueError):
            ovl.contents = [(new_bottom, ovl._DEFAULT_BOTTOM_OPTIONS)]

    def test_contents_getitem_invalid_index(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 5)
        with self.assertRaises(IndexError):
            ovl.contents[2]  # accessing for the side effect of raising

    def test_contents_setitem_errors(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 5)

        with self.subTest("value is not a (widget, options) pair"), self.assertRaises(overlay_mod.OverlayError):
            ovl.contents[0] = "not-a-pair"

        with self.subTest("bottom options mismatch"), self.assertRaises(overlay_mod.OverlayError):
            ovl.contents[0] = (urwid.SolidFill("x"), ovl.contents[1][1])

        with self.subTest("top options malformed"), self.assertRaises(overlay_mod.OverlayError):
            ovl.contents[1] = (urwid.SolidFill("y"), (1, 2, 3))

        with self.subTest("invalid index"), self.assertRaises(IndexError):
            ovl.contents[5] = (urwid.SolidFill("z"), ovl.contents[1][1])

    def test_get_cursor_coords_none_without_support(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 10, urwid.MIDDLE, 5)
        self.assertIsNone(ovl.get_cursor_coords((20, 10)))

    def test_get_cursor_coords_clamped_to_last_row(self) -> None:
        ovl = urwid.Overlay(FixedCursorSolidFill("*"), urwid.SolidFill("#"), urwid.CENTER, 5, urwid.MIDDLE, 5)
        self.assertEqual((0, 4), ovl.get_cursor_coords((5, 5)))

    def test_calculate_padding_filler_raises_for_zero_height_fixed(self) -> None:
        ovl = urwid.Overlay(ZeroHeightFixed(), urwid.SolidFill("#"), urwid.CENTER, None, urwid.MIDDLE, None)
        with self.assertRaises(overlay_mod.OverlayError):
            ovl.calculate_padding_filler((10, 5), False)

    def test_calculate_padding_filler_shrinks_bottom_for_oversized_flow(self) -> None:
        """A PACK-height flow widget taller than maxrow has its bottom filler go negative instead of raising."""
        top_w = urwid.Text("one two three four five six seven eight nine ten")
        ovl = urwid.Overlay(top_w, urwid.SolidFill("#"), urwid.CENTER, 5, urwid.TOP, None)
        height = top_w.rows((5,))
        self.assertGreater(height, 3)
        self.assertEqual((0, 0, 0, 3 - height), ovl.calculate_padding_filler((5, 3), False))

    def test_render_returns_bottom_only_when_bottom_canvas_is_empty(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("X"), urwid.SolidFill("."), urwid.CENTER, 4, urwid.MIDDLE, 2)
        canvas = ovl.render((0, 5))
        self.assertIsInstance(canvas, urwid.CompositeCanvas)
        self.assertEqual(0, canvas.cols())
        self.assertEqual(5, canvas.rows())

    def test_mouse_event_without_support(self) -> None:
        with self.assertWarns(DeprecationWarning):
            ovl = urwid.Overlay(
                NotAWidget(),
                urwid.SolidFill("#"),
                urwid.CENTER,
                (urwid.RELATIVE, 100),
                urwid.MIDDLE,
                (urwid.RELATIVE, 100),
            )
        self.assertFalse(ovl.mouse_event((10, 5), "mouse press", 1, 0, 0, True))

    def test_mouse_event_outside_top_w_area(self) -> None:
        ovl = urwid.Overlay(urwid.SolidFill("X"), urwid.SolidFill("."), urwid.CENTER, 4, urwid.MIDDLE, 2)
        self.assertEqual((2, 2, 1, 1), ovl.calculate_padding_filler((8, 4), True))
        self.assertFalse(ovl.mouse_event((8, 4), "mouse press", 1, 0, 0, True))
