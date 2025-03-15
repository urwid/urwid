from __future__ import annotations

import typing
import unittest

import urwid
from tests.util import SelectableText

if typing.TYPE_CHECKING:
    from collections.abc import Collection

    from typing_extensions import Literal


class ColumnsTest(unittest.TestCase):
    def test_basic_sizing(self) -> None:
        box_only = urwid.SolidFill("#")
        flow_only = urwid.ProgressBar(None, None)
        fixed_only = urwid.BigText("0", urwid.Thin3x3Font())
        flow_fixed = urwid.Text("text")

        with self.subTest("No sizing calculation possible"), self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
            widget = urwid.Columns(((urwid.PACK, fixed_only), box_only), box_columns=(1,))
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

        for description, kwargs in (
            ("BOX-only widget", {"widget_list": (box_only,)}),
            ('BOX-only widget with "get height from max"', {"widget_list": (box_only,), "box_columns": (0,)}),
            ("No FLOW - BOX only", {"widget_list": (box_only, urwid.SolidFill(" ")), "box_columns": (0, 1)}),
            ("GIVEN BOX only -> BOX only", {"widget_list": ((5, box_only),), "box_columns": (0,)}),
        ):
            with self.subTest(description):
                widget = urwid.Columns(**kwargs)
                self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())

                cols, rows = 2, 2

                self.assertEqual((cols, rows), widget.pack((cols, rows)))
                canvas = widget.render((cols, rows))
                self.assertEqual(cols, canvas.cols())
                self.assertEqual(rows, canvas.rows())

        with self.subTest("FLOW-only"):
            widget = urwid.Columns((flow_only,))
            self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())
            cols, rows = 2, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest('BOX/FLOW by "box_columns": can be rendered as box only as fallback'):
            widget = urwid.Columns((flow_only, box_only), box_columns=(1,))
            self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())
            cols, rows = 2, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            self.assertEqual((cols, rows), widget.pack((cols, rows)))
            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("FLOW/FIXED"):
            widget = urwid.Columns((flow_fixed,))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())
            cols, rows = 4, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            cols, rows = 2, 2
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("FIXED only"):
            widget = urwid.Columns(((urwid.PACK, fixed_only),))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())
            cols, rows = 3, 3
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("FIXED only use FLOW methods - drop & replace by solid"):
            widget = urwid.Columns(((urwid.PACK, fixed_only),))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())
            cols, rows = 2, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual("  ", str(canvas))

        with self.subTest("FIXED only use FLOW methods - add empty space"):
            widget = urwid.Columns(((urwid.PACK, fixed_only),))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())
            cols, rows = 5, 3
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                (
                    "┌─┐  ",
                    "│ │  ",
                    "└─┘  ",
                ),
                canvas.decoded_text,
            )

        with self.subTest("GIVEN BOX + FLOW/FIXED, but other widgets do not support box"):
            widget = urwid.Columns((flow_fixed, (3, box_only)), box_columns=(1,))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())
            cols, rows = 7, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            cols, rows = 4, 4
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual([b"t###", b"e###", b"x###", b"t###"], canvas.text)

            cols, rows = 2, 2
            self.assertEqual((cols, rows), widget.pack((cols, rows)))
            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual([b"te", b"xt"], canvas.text)

        with self.subTest("Wrong sizing -> fallback to historic hardcoded"):
            with self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
                widget = urwid.Columns(((urwid.PACK, box_only),))
                self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())
                self.assertEqual(
                    f"Sizing combination of widget {box_only} (position=0) not supported: PACK box=False",
                    str(ctx.warnings[0].message),
                )

        with self.subTest("Wrong sizing -> fallback to historic hardcoded 2"):
            with self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
                widget = urwid.Columns(((urwid.WEIGHT, 1, fixed_only),))
                self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())
                self.assertEqual(
                    f"Sizing combination of widget {fixed_only} (position=0) not supported: WEIGHT box=False",
                    str(ctx.warnings[0].message),
                )

        with (
            self.subTest('BOX not added to "box_columns" but widget handled as FLOW'),
            self.assertWarns(urwid.widget.ColumnsWarning) as ctx,
        ):
            self.maxDiff = None
            contents = (
                (urwid.WEIGHT, 1, urwid.SolidFill()),
                (urwid.FIXED, 10, urwid.Button("OK", align=urwid.CENTER)),
                (urwid.WEIGHT, 1, urwid.SolidFill()),
                (urwid.FIXED, 10, urwid.Button("Cancel", align=urwid.CENTER)),
                (urwid.WEIGHT, 1, urwid.SolidFill()),
            )
            widget = urwid.Columns(contents)

            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

            self.assertEqual(
                "Columns widget contents flags not allow to determine supported render kind:\n"
                "BOX WEIGHT, FIXED|FLOW GIVEN\n"
                "Using fallback hardcoded BOX|FLOW sizing kind.",
                str(ctx.warnings[0].message),
            )

            cols, rows = 30, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))

            canvas = widget.render((cols,))
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual([b"   <   OK   >    < Cancel >   "], canvas.text)
            self.assertEqual(
                "Widgets in columns [0, 2, 4] "
                f"({[elem[-1] for elem in contents[:6:2]]}) "
                f'are BOX widgets not marked "box_columns" '
                f"while FLOW render is requested (size=(30,))",
                str(ctx.warnings[2].message),
            )

            self.assertEqual("OK", widget.focus.label)
            self.assertIsNone(widget.keypress((cols,), "right"))
            self.assertEqual(
                "Widgets in columns [0, 2, 4] "
                f"({[elem[-1] for elem in contents[:6:2]]}) "
                f'are BOX widgets not marked "box_columns" '
                f"while FLOW render is requested (size=(30,))",
                str(ctx.warnings[3].message),
            )
            self.assertEqual("Cancel", widget.focus.label)

    def test_pack_render_fixed(self) -> None:
        """Cover weighted FIXED/FLOW widgets pack.

        One of the popular use-cases: rows of buttons/radiobuttons/checkboxes in pop-up windows.
        """
        widget = urwid.Columns(
            (urwid.Button(label, align=urwid.CENTER) for label in ("OK", "Cancel", "Help")),
            dividechars=1,
        )
        self.assertEqual((32, 1), widget.pack(()))
        self.assertEqual([b"<   OK   > < Cancel > <  Help  >"], widget.render(()).text)

    def test_render_fixed_consistency(self) -> None:
        """Widgets supporting FIXED should be rendered with PACK side the same way as not FIXED."""
        widget = urwid.Columns(((urwid.PACK, urwid.Text("Prefix:")), (urwid.PACK, urwid.Button("Btn"))), dividechars=1)

        cols, _ = widget.pack(())

        self.assertEqual(((7, 7), (1, 1), ((), ())), widget.get_column_sizes(()))
        self.assertEqual(((7, 7), (1, 1), ((7,), (7,))), widget.get_column_sizes((cols,)))

        self.assertEqual(("Prefix: < Btn >",), widget.render(()).decoded_text)
        self.assertEqual(("Prefix: < Btn >",), widget.render((cols,)).decoded_text)

    def test_render_pack_item_not_fit(self):
        items = urwid.Text("123"), urwid.Text("456")
        widget = urwid.Columns((urwid.PACK, item) for item in items)
        # Make width < widget fixed pack
        width = items[0].pack(())[0] - 1
        height = items[0].rows((width,))
        self.assertEqual((width, height), widget.pack((width,)))

        canvas = widget.render((width,))
        # Rendered should be not empty
        self.assertEqual(items[0].render((width,)).decoded_text, canvas.decoded_text)
        self.assertEqual(width, canvas.cols())

    def test_pack_render_broken_sizing(self) -> None:
        use_sizing = frozenset((urwid.BOX,))

        class BrokenSizing(urwid.Text):
            def sizing(self) -> frozenset[urwid.Sizing]:
                return use_sizing

        with self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
            element = BrokenSizing("Test")
            widget = urwid.Columns(((urwid.PACK, element),))
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())
            self.assertEqual(
                f"Sizing combination of widget {element} (position=0) not supported: PACK box=False",
                str(ctx.warnings[0].message),
            )

        with self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
            canvas = widget.render((10,))
            self.assertEqual([b"Test      "], canvas.text)
            self.assertEqual(
                f"Unusual widget {element} sizing for {urwid.PACK} (box=False). "
                f"Assuming wrong sizing and using FLOW for width calculation",
                str(ctx.warnings[0].message),
            )

    def test_pack_render_skip_widget(self):
        widget = urwid.Columns(((0, urwid.Text("Ignore\nme")), (urwid.Text("Count"))))
        cols, rows = 5, 1
        self.assertEqual((cols, rows), widget.pack(()))
        self.assertEqual((cols, rows), widget.pack((cols,)))
        self.assertEqual("Count", str(widget.render(())))
        self.assertEqual("Count", str(widget.render((cols,))))

    def test_pack_flow_with_fixed_item(self):
        widget = urwid.Columns(
            (
                (urwid.PACK, urwid.BigText("3", urwid.Thin3x3Font())),
                (urwid.Text("Multi\nline\ntext\n???")),
            ),
            dividechars=1,
        )
        with self.subTest("Skip"):
            self.assertEqual(3, widget.rows((3,)))
            self.assertEqual((3, 3), widget.pack((3,)))
            self.assertEqual(
                (
                    "┌─┐",
                    " ─┤",
                    "└─┘",
                ),
                widget.render((3,)).decoded_text,
            )
        with self.subTest("Fit all"):
            self.assertEqual(4, widget.rows((9,)))
            self.assertEqual((9, 4), widget.pack((9,)))
            self.assertEqual(
                (
                    "┌─┐ Multi",
                    " ─┤ line ",
                    "└─┘ text ",
                    "    ???  ",
                ),
                widget.render((9,)).decoded_text,
            )
        with self.subTest("Use SolidCanvas instead"):
            self.assertEqual(1, widget.rows((2,)))
            self.assertEqual((2, 1), widget.pack((2,)))
            self.assertEqual(("  ",), widget.render((2,)).decoded_text)

    def test_pack_render_empty_widget(self):
        widget = urwid.Columns(())
        self.assertEqual(frozenset((urwid.FLOW, urwid.BOX)), widget.sizing())
        cols, rows = 10, 1
        self.assertEqual((cols, rows), widget.pack((cols,)))
        canvas = widget.render((cols,))
        self.assertEqual(rows, canvas.rows())
        self.assertEqual(("          ",), canvas.decoded_text)

    def test_not_a_widget(self):
        class NotAWidget:
            __slots__ = ("name", "symbol")

            def __init__(self, name: str, symbol: bytes) -> None:
                self.name = name
                self.symbol = symbol

            def __repr__(self) -> str:
                return f"{self.__class__.__name__}(name={self.name!r}, symbol={self.symbol!r})"

            def selectable(self) -> bool:
                return False

            def rows(self, max_col_row: tuple[int], focus: bool = False) -> int:
                return 1

            def render(self, max_col_row: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.Canvas:
                maxcol = max_col_row[0]
                line = self.symbol * maxcol
                if len(max_col_row) == 1:
                    return urwid.TextCanvas((line,), maxcol=maxcol)
                return urwid.TextCanvas((line,) * max_col_row[1], maxcol=maxcol)

        with self.subTest("Box"), self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
            items = (NotAWidget("First", b"*"), NotAWidget("Second", b"^"))
            widget = urwid.Columns(items)

            self.assertEqual(("**^^", "**^^"), widget.render((4, 2)).decoded_text)
            self.assertEqual(f"{items[0]!r} is not a Widget", str(ctx.warnings[0].message))
            self.assertEqual(f"{items[1]!r} is not a Widget", str(ctx.warnings[1].message))

        with self.subTest("Flow"), self.assertWarns(urwid.widget.ColumnsWarning) as ctx:
            items = (NotAWidget("First", b"*"), NotAWidget("Second", b"^"))
            widget = urwid.Columns(items)

            self.assertEqual(("***^^^",), widget.render((6,)).decoded_text)
            self.assertEqual(f"{items[0]!r} is not a Widget", str(ctx.warnings[0].message))
            self.assertEqual(f"{items[1]!r} is not a Widget", str(ctx.warnings[1].message))

    def test_zero_width_column(self):
        elem_1 = urwid.BoxAdapter(urwid.SolidFill("#"), 2)
        elem_2 = urwid.BoxAdapter(urwid.SolidFill("*"), 4)

        widget = urwid.Columns((elem_1, (0, elem_2)))
        self.assertEqual((3, 2), widget.pack((3,)))

        canvas = widget.render((3,))
        self.assertEqual(2, canvas.rows())
        self.assertEqual(3, canvas.cols())
        self.assertEqual([b"###", b"###"], canvas.text)

    def test_focus_column(self):
        button_1 = urwid.Button("Selectable")
        button_2 = urwid.Button("Other selectable")
        widget_list = [
            (urwid.PACK, urwid.Text("Non selectable")),
            (urwid.PACK, button_1),
            (urwid.PACK, button_2),
            (urwid.PACK, urwid.Text("The end")),
        ]
        with self.subTest("Not provided -> select first selectable"):
            widget = urwid.Columns(widget_list)
            self.assertEqual(1, widget.focus_position)
            widget.keypress((), "left")
            self.assertEqual(1, widget.focus_position)

        with self.subTest("Exact index"):
            widget = urwid.Columns(widget_list, focus_column=2)
            self.assertEqual(2, widget.focus_position)
            widget.keypress((), "left")
            self.assertEqual(1, widget.focus_position)

        with self.subTest("Exact widget"):
            widget = urwid.Columns(widget_list, focus_column=button_2)
            self.assertEqual(2, widget.focus_position)
            self.assertEqual(button_2, widget.focus)
            widget.keypress((), "left")
            self.assertEqual(1, widget.focus_position)

    def test_pack_not_enough_info(self):
        """Test special case for not official fixed pack and render support."""
        widget = urwid.Columns(
            (
                (urwid.WEIGHT, 16, urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE)),
                (10, urwid.Button("First")),
                urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE),
                (10, urwid.Button("Second")),
                (urwid.WEIGHT, 16, urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE)),
            ),
            box_columns=(0, 2, 4),
        )
        cols, rows = 53, 1
        self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())
        self.assertEqual((cols, rows), widget.pack(()))
        self.assertEqual(
            ("░░░░░░░░░░░░░░░░< First  >░< Second >░░░░░░░░░░░░░░░░",),
            widget.render(()).decoded_text,
        )

    def test_no_height(self):
        widget = urwid.Columns(
            (
                (urwid.WEIGHT, 16, urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE)),
                urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE),
                (urwid.WEIGHT, 16, urwid.SolidFill(urwid.SolidFill.Symbols.LITE_SHADE)),
            ),
            box_columns=(0, 1, 2),
        )
        self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())
        with self.assertRaises(urwid.widget.ColumnsError):
            widget.pack(())

    def assert_column_widths(
        self,
        expected: Collection[int],
        widget: urwid.Columns,
        size: tuple[int, int] | tuple[int] | tuple[()],
        description: str,
    ) -> None:
        column_widths, _, _ = widget.get_column_sizes(size)
        self.assertEqual(expected, column_widths, f"{description} expected {expected}, got {column_widths}")

    def test_widths(self):
        x = urwid.Text("")  # sample "column"

        self.assert_column_widths((20,), urwid.Columns([x]), (20,), "simple 1")
        self.assert_column_widths((10, 10), urwid.Columns([x, x]), (20,), "simple 2")

        self.assert_column_widths((10, 9), urwid.Columns([x, x], 1), (20,), "simple 2+1")

        self.assert_column_widths((6, 6, 6), urwid.Columns([x, x, x], 1), (20,), "simple 3+1")
        self.assert_column_widths((5, 6, 5), urwid.Columns([x, x, x], 2), (20,), "simple 3+2")
        self.assert_column_widths((6, 6, 5), urwid.Columns([x, x, x], 2), (21,), "simple 3+2")

        simple_4 = urwid.Columns([x, x, x, x], 1)
        for expected, cols, description in (
            ((6, 5, 6, 5), 25, "simple 4+1"),
            ((1, 1, 1, 1), 7, "squish 4+1"),
            ((1, 2, 1), 6, "squish 4+1"),
            ((2, 1), 4, "squish 4+1"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, simple_4, (cols,), description)

        fixed = urwid.Columns([("fixed", 4, x), ("fixed", 6, x), ("fixed", 2, x)], 1)
        for expected, size, description in (
            ((4, 6, 2), (), "FIXED"),
            ((4, 6, 2), (25,), "fixed 3"),
            ((4, 6), (13,), "fixed 3 cut"),
            ((4,), (10,), "fixed 3 cut2"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, fixed, size, description)

        mixed = urwid.Columns([("weight", 2, x), ("fixed", 5, x), x, ("weight", 3, x)], 1)
        for expected, cols, description in (
            ((2, 5, 1, 3), 14, "mixed 4"),
            ((1, 5, 1, 2), 12, "mixed 4 a"),
            ((2, 5, 1), 10, "mixed 4 b"),
            ((4, 5, 2, 6), 20, "mixed 4 c"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, mixed, (cols,), description)

    def test_widths_focus_end(self):
        x = urwid.Text("")  # sample "column"
        self.assert_column_widths(
            (10, 10),
            urwid.Columns([x, x], focus_column=1),
            (20,),
            "end simple 2",
        )
        self.assert_column_widths(
            (10, 9),
            urwid.Columns([x, x], 1, 1),
            (20,),
            "end simple 2+1",
        )
        self.assert_column_widths(
            (6, 6, 6),
            urwid.Columns([x, x, x], 1, 2),
            (20,),
            "end simple 3+1",
        )
        self.assert_column_widths(
            (5, 6, 5),
            urwid.Columns([x, x, x], 2, 2),
            (20,),
            "end simple 3+2",
        )
        self.assert_column_widths(
            (6, 6, 5),
            urwid.Columns([x, x, x], 2, 2),
            (21,),
            "end simple 3+2",
        )

        simple_4 = urwid.Columns([x, x, x, x], 1, 3)
        for expected, cols, description in (
            ((6, 5, 6, 5), 25, "end simple 4+1"),
            ((1, 1, 1, 1), 7, "end squish 4+1"),
            ((0, 1, 2, 1), 6, "end squish 4+1"),
            ((0, 0, 2, 1), 4, "end squish 4+1"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, simple_4, (cols,), description)

        fixed = urwid.Columns([("fixed", 4, x), ("fixed", 6, x), ("fixed", 2, x)], 1, 2)
        for expected, size, description in (
            ((4, 6, 2), (), "FIXED"),
            ((4, 6, 2), (25,), "end fixed 3"),
            ((0, 6, 2), (13,), "end fixed 3 cut"),
            ((0, 0, 2), (8,), "end fixed 3 cut2"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, fixed, size, description)

        mixed = urwid.Columns([("weight", 2, x), ("fixed", 5, x), x, ("weight", 3, x)], 1, 3)
        for expected, cols, description in (
            ((2, 5, 1, 3), 14, "end mixed 4"),
            ((1, 5, 1, 2), 12, "end mixed 4 a"),
            ((0, 5, 1, 2), 10, "end mixed 4 b"),
            ((4, 5, 2, 6), 20, "end mixed 4 c"),
        ):
            with self.subTest(description):
                self.assert_column_widths(expected, mixed, (cols,), description)

    def check_move_cursor(
        self,
        expected: bool,
        widget: urwid.Columns,
        size: tuple[int, int] | tuple[int] | tuple[()],
        col: int | Literal["left", "right"],
        row: int,
        focus_position: int,
        pref_col: int | Literal["left", "right"] | None,
        description: str,
    ) -> None:
        moved = widget.move_cursor_to_coords(size, col, row)
        self.assertEqual(expected, moved, f"{description} expected {expected!r}, got {moved!r}")
        self.assertEqual(
            focus_position,
            widget.focus_position,
            f"{description} expected focus_position {focus_position!r}, got {widget.focus_position!r}",
        )
        w_pref_col = widget.get_pref_col(size)
        self.assertEqual(
            pref_col,
            w_pref_col,
            f"{description} expected pref_col {pref_col!r}, got {w_pref_col!r}",
        )

    def test_move_cursor(self):
        e, s, x = urwid.Edit("", ""), SelectableText(""), urwid.Text("")

        self.check_move_cursor(
            False,
            urwid.Columns([x, x, x], 1),
            (20,),
            9,
            0,
            0,
            None,
            "nothing selectable",
        )

        mid = urwid.Columns([x, s, x], 1)
        self.check_move_cursor(
            True,
            mid,
            (20,),
            9,
            0,
            1,
            9,
            "dead on",
        )
        self.check_move_cursor(
            True,
            mid,
            (20,),
            6,
            0,
            1,
            6,
            "l edge",
        )
        self.check_move_cursor(
            True,
            mid,
            (20,),
            13,
            0,
            1,
            13,
            "r edge",
        )
        self.check_move_cursor(
            True,
            mid,
            (20,),
            2,
            0,
            1,
            2,
            "l off",
        )
        self.check_move_cursor(
            True,
            mid,
            (20,),
            17,
            0,
            1,
            17,
            "r off",
        )

        self.check_move_cursor(
            True,
            urwid.Columns([x, x, s], 1),
            (20,),
            2,
            0,
            2,
            2,
            "l off 2",
        )
        self.check_move_cursor(
            True,
            urwid.Columns([s, x, x], 1),
            (20,),
            17,
            0,
            0,
            17,
            "r off 2",
        )

        self.check_move_cursor(
            True,
            urwid.Columns([s, s, x], 1),
            (20,),
            6,
            0,
            0,
            6,
            "l between",
        )
        self.check_move_cursor(
            True,
            urwid.Columns([x, s, s], 1),
            (20,),
            13,
            0,
            1,
            13,
            "r between",
        )

        l_2 = urwid.Columns([s, s, x], 2)
        self.check_move_cursor(
            True,
            l_2,
            (22,),
            6,
            0,
            0,
            6,
            "l between 2l",
        )
        self.check_move_cursor(
            True,
            l_2,
            (22,),
            7,
            0,
            1,
            7,
            "l between 2r",
        )

        r_2 = urwid.Columns([x, s, s], 2)
        self.check_move_cursor(
            True,
            r_2,
            (22,),
            14,
            0,
            1,
            14,
            "r between 2l",
        )
        self.check_move_cursor(
            True,
            r_2,
            (22,),
            15,
            0,
            2,
            15,
            "r between 2r",
        )

        # unfortunate pref_col shifting
        edge = urwid.Columns([x, e, x], 1)
        self.check_move_cursor(
            True,
            edge,
            (20,),
            6,
            0,
            1,
            7,
            "l e edge",
        )
        self.check_move_cursor(
            True,
            edge,
            (20,),
            13,
            0,
            1,
            12,
            "r e edge",
        )

        # 'left'/'right' special cases
        full = urwid.Columns([e, e, e])
        self.check_move_cursor(
            True,
            full,
            (12,),
            "right",
            0,
            2,
            "right",
            "l e edge",
        )
        self.check_move_cursor(
            True,
            full,
            (12,),
            "left",
            0,
            0,
            "left",
            "r e edge",
        )

    def test_init_with_a_generator(self):
        urwid.Columns(urwid.Text(c) for c in "ABC")

    def test_old_attributes(self):
        c = urwid.Columns([urwid.Text("a"), urwid.SolidFill("x")], box_columns=[1])
        with self.assertWarns(DeprecationWarning):
            self.assertEqual(c.box_columns, [1])
        with self.assertWarns(DeprecationWarning):
            c.box_columns = []

        self.assertEqual(c.box_columns, [])

    def test_box_column(self):
        c = urwid.Columns([urwid.Filler(urwid.Edit()), urwid.Text("")], box_columns=[0])
        c.keypress((10,), "x")
        c.get_cursor_coords((10,))
        c.move_cursor_to_coords((10,), 0, 0)
        c.mouse_event((10,), "foo", 1, 0, 0, True)
        c.get_pref_col((10,))

    def test_length(self):
        columns = urwid.Columns(urwid.Text(c) for c in "ABC")
        self.assertEqual(3, len(columns))
        self.assertEqual(3, len(columns.contents))

    def test_common(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        t3 = urwid.Text("three")
        sf = urwid.SolidFill("x")
        c = urwid.Columns([])

        with self.subTest("Focus"):
            self.assertEqual(c.focus, None)
            self.assertRaises(IndexError, lambda: getattr(c, "focus_position"))
            self.assertRaises(IndexError, lambda: setattr(c, "focus_position", None))
            self.assertRaises(IndexError, lambda: setattr(c, "focus_position", 0))

        with self.subTest("Contents change"):
            c.contents = [
                (t1, ("pack", None, False)),
                (t2, ("weight", 1, False)),
                (sf, ("weight", 2, True)),
                (t3, ("given", 10, False)),
            ]
            c.focus_position = 1
            del c.contents[0]
            self.assertEqual(c.focus_position, 0)
            c.contents[0:0] = [(t3, ("given", 10, False)), (t2, ("weight", 1, False))]
            c.contents.insert(3, (t1, ("pack", None, False)))
            self.assertEqual(c.focus_position, 2)

        with self.subTest("Contents change validation"):
            c.contents.clear()

            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append(t1))
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, None)))
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, "given")))
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, ("given", None))))
            # Incorrect kind
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, ("what", 1, False))))
            # Incorrect box field
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, ("given", 1, None))))
            # Incorrect size type
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, ("given", (), False))))
            # Incorrect size
            self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, ("given", -1, False))))
            # Float and int weight accepted
            c.contents.append((t1, ("weight", 1, False)))
            c.contents.append((t2, ("weight", 0.5, False)))
            self.assertEqual(("one   two",), c.render(()).decoded_text)

    def test_focus_position(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        c = urwid.Columns([t1, t2])
        self.assertEqual(c.focus, t1)
        self.assertEqual(c.focus_position, 0)
        c.focus_position = 1
        self.assertEqual(c.focus, t2)
        self.assertEqual(c.focus_position, 1)
        c.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(c, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(c, "focus_position", 2))

    def test_deprecated(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        sf = urwid.SolidFill("x")
        # old methods:
        c = urwid.Columns([t1, ("weight", 3, t2), sf], box_columns=[2])
        with self.subTest("Focus"):
            c.set_focus(0)
            self.assertRaises(IndexError, lambda: c.set_focus(-1))
            self.assertRaises(IndexError, lambda: c.set_focus(3))
            c.set_focus(t2)
            self.assertEqual(c.focus_position, 1)
            self.assertRaises(ValueError, lambda: c.set_focus("nonexistant"))

        with self.subTest("Contents"):
            self.assertEqual(c.widget_list, [t1, t2, sf])
            self.assertEqual(c.column_types, [("weight", 1), ("weight", 3), ("weight", 1)])
            self.assertEqual(c.box_columns, [2])

        with self.subTest("Contents change"):
            c.widget_list = [t2, t1, sf]
            self.assertEqual(c.widget_list, [t2, t1, sf])
            self.assertEqual(c.box_columns, [2])

            self.assertEqual(
                c.contents,
                [(t2, ("weight", 1, False)), (t1, ("weight", 3, False)), (sf, ("weight", 1, True))],
            )
            self.assertEqual(c.focus_position, 1)  # focus unchanged
            c.column_types = [("flow", None), ("weight", 2), ("fixed", 5)]  # use the old name
            self.assertEqual(c.column_types, [("flow", None), ("weight", 2), ("fixed", 5)])
            self.assertEqual(
                c.contents,
                [(t2, ("pack", None, False)), (t1, ("weight", 2, False)), (sf, ("given", 5, True))],
            )
            self.assertEqual(c.focus_position, 1)  # focus unchanged

        with self.subTest("Contents change 2"):
            c.widget_list = [t1]
            self.assertEqual(len(c.contents), 1)
            self.assertEqual(c.focus_position, 0)
            c.widget_list.extend([t2, t1])
            self.assertEqual(len(c.contents), 3)
            self.assertEqual(c.column_types, [("flow", None), ("weight", 1), ("weight", 1)])
            c.column_types[:] = [("weight", 2)]
            self.assertEqual(len(c.contents), 1)

    def test_regression_columns_different_height(self):
        size = (20, 5)
        box_w = urwid.SolidFill("#")
        f_f_widget = urwid.Text("Fixed/Flow")
        box_flow = urwid.LineBox(urwid.Filler(f_f_widget, valign=urwid.TOP))
        self.assertIn(urwid.BOX, box_w.sizing())
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), box_flow.sizing())

        with self.subTest("BoxFlow weight"):
            widget = urwid.Columns(((1, box_w), box_flow))

            self.assertEqual(
                (
                    "#┌─────────────────┐",
                    "#│Fixed/Flow       │",
                    "#│                 │",
                    "#│                 │",
                    "#└─────────────────┘",
                ),
                widget.render(size, False).decoded_text,
            )

        with self.subTest("BoxFlow GIVEN"):
            widget = urwid.Columns((box_w, (12, box_flow)))

            self.assertEqual(
                (
                    "########┌──────────┐",
                    "########│Fixed/Flow│",
                    "########│          │",
                    "########│          │",
                    "########└──────────┘",
                ),
                widget.render(size, False).decoded_text,
            )
