from __future__ import annotations

import unittest

import urwid
from tests.util import SelectableText


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
