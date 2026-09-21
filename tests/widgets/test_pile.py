from __future__ import annotations

import unittest
import warnings

import urwid
from tests.util import SelectableText


class NotAWidget:
    __slots__ = ("name", "symbol")

    def __init__(self, name: str, symbol: bytes) -> None:
        self.name = name
        self.symbol = symbol

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, symbol={self.symbol!r})"

    def selectable(self) -> bool:
        return False

    def pack(self, max_col_row: tuple[int, int] | tuple[int], focus: bool = False) -> int:
        if len(max_col_row) == 2:
            return max_col_row
        return max_col_row[0], self.rows(max_col_row)

    def rows(self, max_col_row: tuple[int], focus=False) -> int:
        return 1

    def render(self, max_col_row: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.Canvas:
        maxcol = max_col_row[0]
        line = self.symbol * maxcol
        if len(max_col_row) == 1:
            return urwid.TextCanvas((line,), maxcol=maxcol)
        return urwid.TextCanvas((line,) * max_col_row[1], maxcol=maxcol)


class ImplementWidget:
    __slots__ = ("name", "symbol")

    def sizing(self) -> frozenset[urwid.Sizing]:
        return frozenset((urwid.BOX, urwid.FLOW))

    @property
    def base_widget(self) -> urwid.AbstractWidget:
        return self

    def __init__(self, name: str, symbol: bytes) -> None:
        self.name = name
        self.symbol = symbol

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, symbol={self.symbol!r})"

    def selectable(self) -> bool:
        return False

    @property
    def focus(self) -> None:
        return None

    def _invalidate(self) -> None:
        pass

    def rows(self, max_col_row: tuple[int], focus: bool = False) -> int:
        return 1

    def pack(self, size: typing.Any, focus: bool = False) -> tuple[int, int]:
        return self.rows(size, focus)

    def render(self, max_col_row: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.Canvas:
        maxcol = max_col_row[0]
        line = self.symbol * maxcol
        if len(max_col_row) == 1:
            return urwid.TextCanvas((line,), maxcol=maxcol)
        return urwid.TextCanvas((line,) * max_col_row[1], maxcol=maxcol)

    def keypress(self, size: tuple[int, int] | tuple[int], key: str) -> str | None:
        return key

    def mouse_event(
        self,
        size: tuple[int, int] | tuple[int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        return False


class BoxWithRows(urwid.Widget):
    """A proper Widget that only supports BOX sizing but still has a rows() method."""

    _sizing = frozenset((urwid.BOX,))

    def selectable(self) -> bool:
        return False

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 2

    def pack(self, size: tuple[int, int] | tuple[int] | tuple[()], focus: bool = False) -> tuple[int, int]:
        return (size[0] if size else 3, 2)

    def render(self, size: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.Canvas:
        maxcol = size[0]
        rows = size[1] if len(size) > 1 else 2
        return urwid.SolidFill("#").render((maxcol, rows))


class FixedBox(urwid.Widget):
    """A proper Widget supporting both FIXED and BOX sizing."""

    _sizing = frozenset((urwid.FIXED, urwid.BOX))

    def __init__(self, width: int, height: int, symbol: str) -> None:
        super().__init__()
        self.width = width
        self.height = height
        self.symbol = symbol

    def selectable(self) -> bool:
        return False

    def pack(self, size: tuple[int, int] | tuple[int] | tuple[()], focus: bool = False) -> tuple[int, int]:
        return (self.width, self.height)

    def render(self, size: tuple[int, int] | tuple[int], focus: bool = False) -> urwid.Canvas:
        maxcol = size[0]
        rows = size[1] if len(size) > 1 else self.height
        return urwid.SolidFill(self.symbol).render((maxcol, rows))


class NoPrefColText(SelectableText):
    def get_pref_col(self, size: tuple[int]) -> None:
        return None


class RejectCursorText(SelectableText):
    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
        return False


class NoCoordsText(SelectableText):
    def get_cursor_coords(self, size: tuple[int]) -> None:
        return None


class ZeroRowsText(SelectableText):
    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 0

    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
        return True


class MultiRowCursorText(SelectableText):
    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 3

    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
        return row == 1


class PileTest(unittest.TestCase):
    def test_basic_sizing(self) -> None:
        box_only = urwid.SolidFill("#")
        flow_only = urwid.ProgressBar(None, None)
        fixed_only = urwid.BigText("0", urwid.Thin3x3Font())
        flow_fixed = urwid.Text("text")

        with self.subTest("BOX-only widget"):
            widget = urwid.Pile((box_only,))
            self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())

            cols, rows = 2, 2

            self.assertEqual((cols, rows), widget.pack((cols, rows)))
            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("GIVEN BOX -> BOX/FLOW"):
            widget = urwid.Pile(((2, box_only),))
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), widget.sizing())

            cols, rows = 2, 5
            self.assertEqual((cols, rows), widget.pack((cols, rows)))
            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

            cols, rows = 5, 2
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("FLOW-only"):
            widget = urwid.Pile((flow_only,))
            self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())

            cols, rows = 5, 1
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())

        with self.subTest("FIXED -> FIXED"):
            widget = urwid.Pile(((urwid.PACK, fixed_only),))
            self.assertEqual(frozenset((urwid.FIXED,)), widget.sizing())

            cols, rows = 3, 3
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "┌─┐",
                    "│ │",
                    "└─┘",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("FLOW/FIXED -> FLOW/FIXED"):
            widget = urwid.Pile(((urwid.PACK, flow_fixed),))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols, rows = 4, 1
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                ["text"],
                [line.decode("utf-8") for line in widget.render(()).text],
            )

            cols, rows = 2, 2
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "te",
                    "xt",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("FLOW + FLOW/FIXED -> FLOW/FIXED"):
            widget = urwid.Pile((flow_only, (urwid.PACK, flow_fixed)))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols, rows = 4, 2
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    " 0 %",
                    "text",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

            cols, rows = 2, 3
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "0 ",
                    "te",
                    "xt",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("FLOW + FIXED widgets -> FLOW/FIXED"):
            widget = urwid.Pile((flow_only, (urwid.PACK, fixed_only)))
            self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols, rows = 3, 4
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "0 %",
                    "┌─┐",
                    "│ │",
                    "└─┘",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

            cols, rows = 10, 4
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "    0 %   ",
                    "┌─┐",
                    "│ │",
                    "└─┘",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

        with self.subTest("GIVEN BOX + FIXED widgets -> BOX/FLOW/FIXED"):
            widget = urwid.Pile(((1, box_only), (urwid.PACK, fixed_only), (1, box_only)))
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), widget.sizing())

            cols, rows = 3, 5
            self.assertEqual((cols, rows), widget.pack(()))
            canvas = widget.render(())
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "###",
                    "┌─┐",
                    "│ │",
                    "└─┘",
                    "###",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

            cols, rows = 5, 5
            self.assertEqual((cols, rows), widget.pack((cols,)))
            canvas = widget.render((cols,))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "#####",
                    "┌─┐",
                    "│ │",
                    "└─┘",
                    "#####",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

            cols, rows = 5, 6
            self.assertEqual((cols, rows), widget.pack((cols, rows)))
            canvas = widget.render((cols, rows))
            self.assertEqual(cols, canvas.cols())
            self.assertEqual(rows, canvas.rows())
            self.assertEqual(
                [
                    "#####",
                    "┌─┐",
                    "│ │",
                    "└─┘",
                    "#####",
                    "     ",
                ],
                [line.decode("utf-8") for line in canvas.text],
            )

    def test_pack_render_fixed(self) -> None:
        """Potential real world case"""
        widget = urwid.LineBox(
            urwid.Pile(
                (
                    urwid.Text("Modal window", align=urwid.CENTER),
                    urwid.Divider("─"),
                    urwid.Columns(
                        (urwid.Button(label, align=urwid.CENTER) for label in ("OK", "Cancel", "Help")),
                        dividechars=1,
                    ),
                )
            )
        )
        cols, rows = 34, 5
        self.assertEqual((cols, rows), widget.pack(()))
        canvas = widget.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())
        self.assertEqual(
            [
                "┌────────────────────────────────┐",
                "│          Modal window          │",
                "│────────────────────────────────│",
                "│<   OK   > < Cancel > <  Help  >│",
                "└────────────────────────────────┘",
            ],
            [line.decode("utf-8") for line in canvas.text],
        )
        self.assertEqual("OK", widget.focus.focus.label)
        widget.keypress((), "right")
        self.assertEqual("Cancel", widget.focus.focus.label)

    def test_not_a_widget(self):
        with self.subTest("Box"), self.assertWarns(urwid.widget.PileWarning) as ctx:
            items = (NotAWidget("First", b"*"), NotAWidget("Second", b"^"))
            widget = urwid.Pile(items)

            self.assertEqual(("****", "^^^^"), widget.render((4, 2)).decoded_text)
            self.assertEqual(f"{items[0]!r} is not a Widget", str(ctx.warnings[0].message))
            self.assertEqual(f"{items[1]!r} is not a Widget", str(ctx.warnings[1].message))

        with self.subTest("Flow"), self.assertWarns(urwid.widget.PileWarning) as ctx:
            items = (NotAWidget("First", b"*"), NotAWidget("Second", b"^"))
            widget = urwid.Pile(items)

            self.assertEqual(("******", "^^^^^^"), widget.render((6,)).decoded_text)
            self.assertEqual(f"{items[0]!r} is not a Widget", str(ctx.warnings[0].message))
            self.assertEqual(f"{items[1]!r} is not a Widget", str(ctx.warnings[1].message))

    def test_implement_widget_interface(self):
        with (
            warnings.catch_warnings(record=True) as collected_w,
            self.subTest("Box"),
        ):
            items = (ImplementWidget("First", b"*"), ImplementWidget("Second", b"^"))
            widget = urwid.Pile(items)

            self.assertEqual(("****", "^^^^"), widget.render((4, 2)).decoded_text)

            pile_warnings = tuple(
                warning.message for warning in collected_w if warning.category == urwid.widget.PileWarning
            )
            self.assertTrue(len(pile_warnings) == 0, "No warnings expected")

        with (
            warnings.catch_warnings(record=True) as collected_w,
            self.subTest("Flow"),
        ):
            items = (ImplementWidget("First", b"*"), ImplementWidget("Second", b"^"))
            widget = urwid.Pile(items)

            self.assertEqual(("******", "^^^^^^"), widget.render((6,)).decoded_text)

            pile_warnings = tuple(
                warning.message for warning in collected_w if warning.category == urwid.widget.PileWarning
            )
            self.assertTrue(len(pile_warnings) == 0, "No warnings expected")

    def ktest(self, desc, contents, focus_item, key, rkey, rfocus, rpref_col):
        p = urwid.Pile(contents, focus_item)
        rval = p.keypress((20,), key)
        assert rkey == rval, f"{desc} key expected {rkey!r} but got {rval!r}"
        new_focus = contents.index(p.focus)
        assert new_focus == rfocus, f"{desc} focus expected {rfocus!r} but got {new_focus!r}"
        new_pref = p.get_pref_col((20,))
        assert new_pref == rpref_col, f"{desc} pref_col expected {rpref_col!r} but got {new_pref!r}"

    def test_select_change(self):
        self.ktest("simple up", [SelectableText("")], 0, "up", "up", 0, 0)
        self.ktest("simple down", [SelectableText("")], 0, "down", "down", 0, 0)
        self.ktest("ignore up", [urwid.Text(""), SelectableText("")], 1, "up", "up", 1, 0)
        self.ktest("ignore down", [SelectableText(""), urwid.Text("")], 0, "down", "down", 0, 0)
        self.ktest("step up", [SelectableText(""), SelectableText("")], 1, "up", None, 0, 0)
        self.ktest("step down", [SelectableText(""), SelectableText("")], 0, "down", None, 1, 0)
        self.ktest("skip step up", [SelectableText(""), urwid.Text(""), SelectableText("")], 2, "up", None, 0, 0)
        self.ktest("skip step down", [SelectableText(""), urwid.Text(""), SelectableText("")], 0, "down", None, 2, 0)
        self.ktest(
            "pad skip step up",
            [urwid.Text(""), SelectableText(""), urwid.Text(""), SelectableText("")],
            3,
            "up",
            None,
            1,
            0,
        )
        self.ktest(
            "pad skip step down",
            [SelectableText(""), urwid.Text(""), SelectableText(""), urwid.Text("")],
            0,
            "down",
            None,
            2,
            0,
        )
        self.ktest(
            "padi skip step up",
            [SelectableText(""), urwid.Text(""), SelectableText(""), urwid.Text(""), SelectableText("")],
            4,
            "up",
            None,
            2,
            0,
        )
        self.ktest(
            "padi skip step down",
            [SelectableText(""), urwid.Text(""), SelectableText(""), urwid.Text(""), SelectableText("")],
            0,
            "down",
            None,
            2,
            0,
        )
        e = urwid.Edit("", "abcd", edit_pos=1)
        e.keypress((20,), "right")  # set a pref_col
        self.ktest("pref step up", [SelectableText(""), urwid.Text(""), e], 2, "up", None, 0, 2)
        self.ktest("pref step down", [e, urwid.Text(""), SelectableText("")], 0, "down", None, 2, 2)
        z = urwid.Edit("", "1234")
        self.ktest("prefx step up", [z, urwid.Text(""), e], 2, "up", None, 0, 2)
        assert z.get_pref_col((20,)) == 2
        z = urwid.Edit("", "1234")
        self.ktest("prefx step down", [e, urwid.Text(""), z], 0, "down", None, 2, 2)
        assert z.get_pref_col((20,)) == 2

    def test_init_with_a_generator(self):
        urwid.Pile(urwid.Text(c) for c in "ABC")

    def test_change_focus_with_mouse(self):
        p = urwid.Pile([urwid.Edit(), urwid.Edit()])
        self.assertEqual(p.focus_position, 0)
        p.mouse_event((10,), "button press", 1, 1, 1, True)
        self.assertEqual(p.focus_position, 1)

    def test_zero_weight(self):
        p = urwid.Pile(
            [
                urwid.SolidFill("a"),
                ("weight", 0, urwid.SolidFill("d")),
            ]
        )
        p.render((5, 4))

    def test_mouse_event_in_empty_pile(self):
        p = urwid.Pile([])
        p.mouse_event((5,), "button press", 1, 1, 1, False)
        p.mouse_event((5,), "button press", 1, 1, 1, True)

    def test_length(self):
        pile = urwid.Pile(urwid.Text(c) for c in "ABC")
        self.assertEqual(3, len(pile))
        self.assertEqual(3, len(pile.contents))

    def test_common(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        t3 = urwid.Text("three")
        sf = urwid.SolidFill("x")
        p = urwid.Pile([])

        with self.subTest("Focus"):
            self.assertEqual(p.focus, None)
            self.assertRaises(IndexError, lambda: getattr(p, "focus_position"))
            self.assertRaises(IndexError, lambda: setattr(p, "focus_position", None))
            self.assertRaises(IndexError, lambda: setattr(p, "focus_position", 0))

        with self.subTest("Contents change"):
            p.contents = [(t1, ("pack", None)), (t2, ("pack", None)), (sf, ("given", 3)), (t3, ("pack", None))]
            p.focus_position = 1
            del p.contents[0]
            self.assertEqual(p.focus_position, 0)
            p.contents[0:0] = [(t3, ("pack", None)), (t2, ("pack", None))]
            p.contents.insert(3, (t1, ("pack", None)))
            self.assertEqual(p.focus_position, 2)

        with self.subTest("Contents change validation"):
            p.contents.clear()
            self.assertRaises(urwid.PileError, lambda: p.contents.append(t1))
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, None)))
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, "given")))
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, ("given",))))
            # Incorrect kind
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, ("what", 0))))
            # incorrect size type
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, ("given", ()))))
            # incorrect size
            self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, ("given", -1))))
            # Float and int weight accepted
            p.contents.append((t1, ("weight", 1)))
            p.contents.append((t2, ("weight", 0.5)))
            self.assertEqual(("one", "two"), p.render((3,)).decoded_text)

    def test_delete_contents_with_negative_step(self) -> None:
        widgets = [urwid.Text(str(index)) for index in range(5)]
        for focus, expected_focus in enumerate((1, 1, 3, 3, 3)):
            with self.subTest(focus=focus):
                pile = urwid.Pile(widgets, focus_item=focus)
                del pile.contents[::-2]
                self.assertEqual([widgets[1], widgets[3]], [item[0] for item in pile.contents])
                self.assertIs(widgets[expected_focus], pile.focus)

    def test_focus_position(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        p = urwid.Pile([t1, t2])
        self.assertEqual(p.focus, t1)
        self.assertEqual(p.focus_position, 0)
        p.focus_position = 1
        self.assertEqual(p.focus, t2)
        self.assertEqual(p.focus_position, 1)
        p.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(p, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(p, "focus_position", 2))

    def test_deprecated(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        p = urwid.Pile([t1, t2])
        # old methods:
        with self.subTest("Focus"):
            p.set_focus(0)
            self.assertRaises(IndexError, lambda: p.set_focus(-1))
            self.assertRaises(IndexError, lambda: p.set_focus(2))
            p.set_focus(t2)
            self.assertEqual(p.focus_position, 1)
            self.assertRaises(ValueError, lambda: p.set_focus("nonexistant"))

        with self.subTest("Contents"):
            self.assertEqual(p.widget_list, [t1, t2])
            self.assertEqual(p.item_types, [("weight", 1), ("weight", 1)])

        with self.subTest("Contents change"):
            p.widget_list = [t2, t1]
            self.assertEqual(p.widget_list, [t2, t1])
            self.assertEqual(p.contents, [(t2, ("weight", 1)), (t1, ("weight", 1))])
            self.assertEqual(p.focus_position, 1)  # focus unchanged
            p.item_types = [("flow", None), ("weight", 2)]
            self.assertEqual(p.item_types, [("flow", None), ("weight", 2)])
            self.assertEqual(p.contents, [(t2, ("pack", None)), (t1, ("weight", 2))])
            self.assertEqual(p.focus_position, 1)  # focus unchanged

        with self.subTest("Contents change 2"):
            p.widget_list = [t1]
            self.assertEqual(len(p.contents), 1)
            self.assertEqual(p.focus_position, 0)
            p.widget_list.extend([t2, t1])
            self.assertEqual(len(p.contents), 3)
            self.assertEqual(p.item_types, [("flow", None), ("weight", 1), ("weight", 1)])
            p.item_types[:] = [("weight", 2)]
            self.assertEqual(len(p.contents), 1)

    def test_focused_not_fit(self):
        """Pile not fit in size and focused widget is out of default display window"""
        widget = urwid.Pile(
            (
                (urwid.PACK, urwid.Text("top 0")),
                (urwid.PACK, urwid.Text("top 1")),
                urwid.ListBox((urwid.CheckBox("cb 0"),)),
                (urwid.PACK, urwid.Text("btm -2")),
                (urwid.PACK, urwid.Text("btm -1")),
            )
        )

        with self.subTest("Fit selectable only"):
            canvas = widget.render((8, 1), True)
            self.assertEqual(("[ ] cb 0",), canvas.decoded_text)

        with self.subTest("Fit selectable and some items"):
            canvas = widget.render((8, 2), True)
            self.assertEqual(
                (
                    "top 1   ",
                    "[ ] cb 0",
                ),
                canvas.decoded_text,
            )

        with self.subTest("Fit selectable and symmetric items"):
            canvas = widget.render((8, 3), True)
            self.assertEqual(
                (
                    "top 1   ",
                    "[ ] cb 0",
                    "btm -2  ",
                ),
                canvas.decoded_text,
            )

        with self.subTest("Not symmetric top"):
            canvas = urwid.Pile(
                (
                    (urwid.PACK, urwid.Text("top 0")),
                    (urwid.PACK, urwid.Text("top 1")),
                    urwid.ListBox((urwid.CheckBox("cb 0"),)),
                    (urwid.PACK, urwid.Text("btm -1")),
                )
            ).render((8, 3), True)
            self.assertEqual(
                (
                    "top 1   ",
                    "[ ] cb 0",
                    "btm -1  ",
                ),
                canvas.decoded_text,
            )

        with self.subTest("Not symmetric bottom"):
            canvas = urwid.Pile(
                (
                    (urwid.PACK, urwid.Text("top 0")),
                    urwid.ListBox((urwid.CheckBox("cb 0"),)),
                    (urwid.PACK, urwid.Text("btm -2")),
                    (urwid.PACK, urwid.Text("btm -1")),
                )
            ).render((8, 3), True)
            self.assertEqual(
                (
                    "top 0   ",
                    "[ ] cb 0",
                    "btm -2  ",
                ),
                canvas.decoded_text,
            )

        with self.subTest("Non-linear sizes should not break rendering"):
            canvas = urwid.Pile(
                (
                    (urwid.PACK, urwid.Text("multi\nline")),
                    (urwid.PACK, urwid.Text("top 1")),
                    urwid.ListBox((urwid.CheckBox("cb 0"),)),
                    (urwid.PACK, urwid.Text("also\nlines")),
                )
            ).render((8, 3), True)
            self.assertEqual(
                (
                    "top 1   ",
                    "[ ] cb 0",
                    "        ",
                ),
                canvas.decoded_text,
            )

        with self.subTest("In multiple weighted need to choose correct to show"):
            canvas = urwid.Pile(
                (
                    (urwid.PACK, urwid.Text("top 0")),
                    urwid.ListBox((urwid.CheckBox("cb 0"),)),
                    (urwid.PACK, urwid.Text("top 1")),
                    urwid.ListBox((urwid.CheckBox("cb 1"),)),
                    (urwid.PACK, urwid.Text("btm -2")),
                    urwid.ListBox((urwid.CheckBox("cb 1"),)),
                    (urwid.PACK, urwid.Text("btm -1")),
                ),
                focus_item=3,
            ).render((8, 3), True)
            self.assertEqual(
                (
                    "top 1   ",
                    "[ ] cb 1",
                    "btm -2  ",
                ),
                canvas.decoded_text,
            )

    def test_focus_changed_callback_replacement(self) -> None:
        """Replace the contents focus callback and read the new index before it is applied."""
        first = urwid.Button("first")
        second = urwid.Button("second")
        pile = urwid.Pile((first, second))
        seen: list[tuple[int, int, urwid.Widget]] = []

        def on_focus_change(new_focus: int) -> None:
            seen.append((new_focus, pile.focus_position, pile.contents[new_focus][0]))
            pile._invalidate()

        pile.contents.set_focus_changed_callback(on_focus_change)
        pile.focus_position = 1

        self.assertEqual([(1, 0, second)], seen)
        self.assertIs(second, pile.focus)
        self.assertEqual(1, pile.focus_position)

    def test_pack_rows_with_weight_body(self) -> None:
        """Dialog-style pile: PACK description, weighted body, PACK footer."""
        pile = urwid.Pile(
            (
                (urwid.WHSettings.PACK, urwid.Text("Describe")),
                urwid.SolidFill("."),
                (urwid.WHSettings.PACK, urwid.Button("OK")),
            )
        )

        self.assertEqual((8, 5), pile.pack((8, 5)))
        self.assertEqual(
            (
                "Describe",
                "........",
                "........",
                "........",
                "< OK   >",
            ),
            pile.render((8, 5)).decoded_text,
        )

    def test_sizing_empty(self) -> None:
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), urwid.Pile([]).sizing())

    def test_sizing_given_non_box_widget_falls_back(self) -> None:
        pile = urwid.Pile(((5, urwid.ProgressBar(None, None)),))
        with self.assertWarns(urwid.widget.PileWarning) as ctx:
            self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), pile.sizing())
        self.assertIn("not supported", str(ctx.warnings[0].message))

    def test_sizing_pack_flow_only_widget(self) -> None:
        pile = urwid.Pile(((urwid.PACK, urwid.ProgressBar(None, None)),))
        self.assertEqual(frozenset((urwid.FLOW,)), pile.sizing())

    def test_init_invalid_items(self) -> None:
        with self.assertRaises(urwid.PileError):
            urwid.Pile([("bogus", 1, urwid.Text("x"))])
        with self.assertRaises(urwid.PileError):
            urwid.Pile([(1, 2, 3, 4)])

    def test_options(self) -> None:
        self.assertEqual((urwid.PACK, None), urwid.Pile.options(urwid.PACK))
        self.assertEqual((urwid.GIVEN, 5), urwid.Pile.options(urwid.GIVEN, 5))
        self.assertEqual((urwid.WEIGHT, 2), urwid.Pile.options(urwid.WEIGHT, 2))
        with self.assertRaises(urwid.PileError):
            urwid.Pile.options(urwid.GIVEN, None)

    def test_focus_setter_widget_not_found(self) -> None:
        pile = urwid.Pile([urwid.Text("one")])
        with self.assertRaises(ValueError):
            pile.focus = urwid.Text("other")

    def test_get_pref_col_not_selectable(self) -> None:
        pile = urwid.Pile([urwid.Text("one")])
        self.assertIsNone(pile.get_pref_col((10,)))

    def test_get_pref_col_empty_contents_but_selectable(self) -> None:
        """Defensive branch: contents is empty even though `_selectable` was left True."""
        pile = urwid.Pile([])
        pile._selectable = True
        self.assertIsNone(pile.get_pref_col((10,)))

    def test_get_rows_sizes_empty_contents(self) -> None:
        pile = urwid.Pile([])
        self.assertEqual(((), (), ()), pile.get_rows_sizes(()))
        self.assertEqual(((5,), (3,), ()), pile.get_rows_sizes((5, 3)))

    def test_fixed_rows_sizes_errors(self) -> None:
        with self.subTest("PACK with BOX-only widget"), self.assertRaises(urwid.PileError):
            urwid.Pile(((urwid.PACK, urwid.SolidFill("#")),)).get_rows_sizes(())

        with self.subTest("GIVEN with non-BOX widget"), self.assertRaises(urwid.PileError):
            urwid.Pile(((5, urwid.ProgressBar(None, None)),)).get_rows_sizes(())

        with self.subTest("WEIGHT with BOX-only widget"), self.assertRaises(urwid.PileError):
            urwid.Pile((urwid.SolidFill("#"),)).get_rows_sizes(())

        with self.subTest("Only GIVEN BOX items: no width information"), self.assertRaises(urwid.PileError):
            urwid.Pile(((5, urwid.SolidFill("#")),)).get_rows_sizes(())

    def test_fixed_rows_sizes_weighted_fixed_box_widgets(self) -> None:
        """FIXED+BOX widgets used with the default WEIGHT option get scaled to a common height."""
        pile = urwid.Pile((FixedBox(4, 2, "a"), FixedBox(6, 4, "b")))
        self.assertEqual(frozenset((urwid.FIXED, urwid.BOX)), pile.sizing())
        self.assertEqual((6, 8), pile.pack(()))
        self.assertEqual(
            (
                "aaaaaa",
                "aaaaaa",
                "aaaaaa",
                "aaaaaa",
                "bbbbbb",
                "bbbbbb",
                "bbbbbb",
                "bbbbbb",
            ),
            pile.render(()).decoded_text,
        )

    def test_flow_rows_sizes_unusual_sizing_warning(self) -> None:
        pile = urwid.Pile((BoxWithRows(),))
        with self.assertWarns(urwid.widget.PileWarning) as ctx:
            canvas = pile.render((5,))
        self.assertEqual(("#####", "#####"), canvas.decoded_text)
        self.assertIn("Unusual widget", str(ctx.warnings[0].message))

    def test_get_rows_sizes_box_unusual_sizing_warning(self) -> None:
        pile = urwid.Pile(((urwid.PACK, BoxWithRows()),))
        with self.assertWarns(urwid.widget.PileWarning) as ctx:
            canvas = pile.render((5, 4))
        self.assertIn("Unusual widget", str(ctx.warnings[0].message))
        self.assertEqual(4, canvas.rows())

    def test_get_rows_sizes_hide_loop_exhausted(self) -> None:
        """When there is zero available space, every hideable item stays hidden (no break taken)."""
        pile = urwid.Pile(
            (
                (urwid.PACK, urwid.Text("a")),
                (urwid.PACK, urwid.Text("b")),
                urwid.ListBox((urwid.CheckBox("cb0"),)),
                (urwid.PACK, urwid.Text("c")),
                (urwid.PACK, urwid.Text("d")),
            )
        )
        _widths, heights, _args = pile.get_rows_sizes((8, 0), focus=True)
        self.assertEqual((0, 0, 0, 0, 0), heights)

    def test_get_rows_sizes_zero_weight_ignored_by_hide_logic(self) -> None:
        pile = urwid.Pile(
            (
                (urwid.PACK, urwid.Text("top 0")),
                ("weight", 0, urwid.SolidFill("z")),
                urwid.ListBox((urwid.CheckBox("cb 0"),)),
                (urwid.PACK, urwid.Text("btm -1")),
            )
        )
        self.assertEqual(("top 0   ", "[ ] cb 0"), pile.render((8, 2), True).decoded_text)

    def test_get_item_rows(self) -> None:
        pile = urwid.Pile([urwid.Text("a"), urwid.Text("b")])
        self.assertEqual([1, 1], pile.get_item_rows((5, 2), False))

    def test_render_empty_pile(self) -> None:
        pile = urwid.Pile([])
        self.assertEqual(("     ", "     "), pile.render((5, 2)).decoded_text)
        with self.assertRaises(ValueError):
            pile.render(())

    def test_keypress_empty_contents(self) -> None:
        pile = urwid.Pile([])
        self.assertEqual("up", pile.keypress((5,), "up"))

    def test_keypress_unhandled_non_updown_key(self) -> None:
        """When the focused widget leaves a non-up/down key unhandled, Pile returns it as-is."""
        pile = urwid.Pile([SelectableText("x")])
        self.assertEqual("left", pile.keypress((10,), "left"))

    def test_keypress_pref_col_none_and_no_move_cursor(self) -> None:
        a = NoPrefColText("a")
        b = SelectableText("b")
        pile = urwid.Pile([a, b])
        pile.focus_position = 0
        self.assertIsNone(pile.keypress((10,), "down"))
        self.assertEqual(1, pile.focus_position)

    def test_get_cursor_coords(self) -> None:
        with self.subTest("Not selectable"):
            pile = urwid.Pile([urwid.Text("one")])
            self.assertIsNone(pile.get_cursor_coords((10,)))

        with self.subTest("Focus widget without get_cursor_coords"):
            pile = urwid.Pile([SelectableText("x")])
            self.assertIsNone(pile.get_cursor_coords((10,)))

        with self.subTest("Focus at position 0"):
            pile = urwid.Pile([urwid.Edit("", "abc", edit_pos=1)])
            self.assertEqual((1, 0), pile.get_cursor_coords((10,)))

        with self.subTest("Focus below other items"):
            pile = urwid.Pile([urwid.Text("one"), urwid.Edit("", "abc", edit_pos=1)])
            pile.focus_position = 1
            self.assertEqual((1, 1), pile.get_cursor_coords((10,)))

        with self.subTest("Focus widget's get_cursor_coords returns None"):
            pile = urwid.Pile([NoCoordsText("x")])
            self.assertIsNone(pile.get_cursor_coords((10,)))

    def test_keypress_not_selectable_falls_through_to_candidates(self) -> None:
        """When no child is selectable, up/down still scans candidates before returning the key unchanged."""
        pile = urwid.Pile([urwid.Text("a"), urwid.Text("b")])
        self.assertFalse(pile.selectable())
        self.assertEqual("down", pile.keypress((10,), "down"))

    def test_keypress_zero_row_candidate_skips_move_loop(self) -> None:
        pile = urwid.Pile([SelectableText("above"), ZeroRowsText("below")])
        self.assertIsNone(pile.keypress((10,), "down"))
        self.assertEqual(1, pile.focus_position)

    def test_keypress_move_cursor_retries_rows(self) -> None:
        """The row-by-row cursor placement loop retries until move_cursor_to_coords succeeds."""
        pile = urwid.Pile([SelectableText("above"), urwid.Text("mid"), MultiRowCursorText("below")])
        self.assertIsNone(pile.keypress((10,), "down"))
        self.assertEqual(2, pile.focus_position)

    def test_move_cursor_to_coords(self) -> None:
        with self.subTest("Success"):
            pile = urwid.Pile([urwid.Edit("", "abc"), urwid.Edit("", "def")])
            self.assertTrue(pile.move_cursor_to_coords((10,), 1, 1))
            self.assertEqual(1, pile.focus_position)

        with self.subTest("Row beyond all items"):
            pile = urwid.Pile([urwid.Edit("", "abc"), urwid.Edit("", "def")])
            self.assertFalse(pile.move_cursor_to_coords((10,), 1, 100))

        with self.subTest("Widget at row not selectable"):
            pile = urwid.Pile([urwid.Text("a"), urwid.Edit("", "b")])
            self.assertFalse(pile.move_cursor_to_coords((10,), 0, 0))

        with self.subTest("Widget rejects cursor move"):
            pile = urwid.Pile([RejectCursorText("x")])
            self.assertFalse(pile.move_cursor_to_coords((10,), 0, 0))
            self.assertEqual(0, pile.focus_position)

        with self.subTest("Selectable widget without move_cursor_to_coords"):
            pile = urwid.Pile([SelectableText("y")])
            self.assertTrue(pile.move_cursor_to_coords((10,), 0, 0))

    def test_mouse_event_row_beyond_items(self) -> None:
        pile = urwid.Pile([urwid.Text("a")])
        self.assertFalse(pile.mouse_event((10,), "mouse press", 1, 0, 50, True))

    def test_mouse_event_child_without_mouse_event(self) -> None:
        """A child widget missing mouse_event() triggers the same "not implementing Widget API" warning.

        See :meth:`Frame._check_widget_subclass` for the same pattern elsewhere in the codebase.
        """
        item = NotAWidget("n", b"*")
        with self.assertWarns(urwid.widget.PileWarning):
            pile = urwid.Pile([item])
        with self.assertWarns(DeprecationWarning) as ctx:
            result = pile.mouse_event((4,), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)
        self.assertIn("is not implementing Widget API", str(ctx.warning))
