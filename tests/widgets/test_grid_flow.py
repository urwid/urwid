from __future__ import annotations

import typing
import unittest
from unittest import mock

import urwid
from tests.util import SelectableText, assert_attribute_redraws


class GridFlowTest(unittest.TestCase):
    def test_layout_attributes_invalidate(self) -> None:
        """Setting a layout attribute of a rendered ``GridFlow`` redraws it and updates its rows."""

        def make(**kwargs: typing.Any) -> urwid.GridFlow:
            options = {"cell_width": 1, "h_sep": 1, "v_sep": 0, "align": "left", **kwargs}
            return urwid.GridFlow([urwid.Text(char) for char in "abc"], **options)

        for name, value in (("h_sep", 2), ("v_sep", 1), ("align", "right")):
            with self.subTest(name):
                assert_attribute_redraws(self, make, (4,), name, value)

    def test_fixed(self):
        grid = urwid.GridFlow(
            (urwid.Button(tag, align=urwid.CENTER) for tag in ("OK", "Cancel", "Help")),
            cell_width=10,
            h_sep=1,
            v_sep=1,
            align=urwid.CENTER,
        )
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), grid.sizing())

        cols, rows = 32, 1
        self.assertEqual((cols, rows), grid.pack(()))
        canvas = grid.render(())
        self.assertEqual(cols, canvas.cols())
        self.assertEqual(rows, canvas.rows())
        self.assertEqual([b"<   OK   > < Cancel > <  Help  >"], canvas.text)

    def test_fixed_own_cell_widths(self) -> None:
        """A fixed size fits cells whose widths differ from ``cell_width`` on one row."""
        grid = urwid.GridFlow([], cell_width=1, h_sep=1, v_sep=0, align=urwid.LEFT)
        grid.contents.extend(
            (urwid.Text(label), grid.options(urwid.GIVEN, len(label))) for label in ("Open", "Quit program", "Up")
        )

        self.assertEqual((20, 1), grid.pack(()))
        self.assertEqual([b"Open Quit program Up"], grid.render(()).text)

    def test_display_widget_cached(self) -> None:
        """The display widget is reused at the same width, and rebuilt for another width or a change.

        The width 7 differs from the fixed width the constructor lays the cells out in.
        """
        grid = urwid.GridFlow(
            [SelectableText(char) for char in "abc"],
            cell_width=1,
            h_sep=1,
            v_sep=0,
            align="left",
        )
        display = grid.get_display_widget((7,))

        with self.subTest("same width"):
            grid.rows((7,))
            self.assertIs(display, grid.get_display_widget((7,)))

        with self.subTest("other width"):
            self.assertIsNot(display, grid.get_display_widget((3,)))

        with self.subTest("focus change"):
            display = grid.get_display_widget((3,))
            grid.focus_position = 2
            self.assertIsNot(display, grid.get_display_widget((3,)))
            self.assertEqual(1, grid.get_display_widget((3,)).focus_position)

    def test_display_widget_follows_cell_selectable(self) -> None:
        """A row without the focus focuses its first selectable cell, also after that cell becomes selectable."""
        cell = urwid.Text("d")
        grid = urwid.GridFlow(
            [SelectableText("a"), SelectableText("b"), urwid.Text("c"), cell],
            cell_width=1,
            h_sep=1,
            v_sep=0,
            align="left",
        )
        self.assertEqual(0, grid.get_display_widget((3,)).contents[1][0].base_widget.focus_position)

        with mock.patch.object(cell, "selectable", return_value=True):
            self.assertEqual(1, grid.get_display_widget((3,)).contents[1][0].base_widget.focus_position)

    def test_pref_col_kept_inside_cell(self) -> None:
        """A column given to ``move_cursor_to_coords`` stays the preferred column, limited to the focus cell.

        The cells are 5 wide at columns 0-4, 6-10 and 12-16, and have no ``get_pref_col`` of their own.
        Width 17 is the natural width, where the display widget built by the constructor is reused.
        """
        cases = (
            # name, width, align, focus before, column, keys after, expected preferred column
            ("on the focus cell", 20, "left", 1, 10, (), 10),
            ("focus moved to the cell", 20, "left", 0, 10, (), 10),
            ("unhandled down", 20, "left", 1, 10, ("down",), 10),
            ("natural width", 17, "left", 1, 10, ("down",), 10),
            ("cell on the right", 20, "left", 1, 13, (), 13),
            ("gap, nearest cell on the left", 20, "left", 1, 11, (), 10),
            ("centred rows", 30, "center", 1, 15, (), 15),
            ("'left' is the first column of the cell", 20, "left", 1, "left", (), 0),
            ("'right' is the last column of the cell", 20, "left", 1, "right", (), 16),
            ("left key: centre of the new cell", 20, "left", 1, 10, ("left",), 2),
            ("back to the cell: its centre", 20, "left", 1, 10, ("right", "left"), 8),
        )
        for name, maxcol, align, focus, col, keys, expected in cases:
            with self.subTest(name):
                grid = urwid.GridFlow(
                    [SelectableText(char) for char in "abc"],
                    cell_width=5,
                    h_sep=1,
                    v_sep=0,
                    align=align,
                    focus=focus,
                )
                self.assertTrue(grid.move_cursor_to_coords((maxcol,), col, 0))
                for key in keys:
                    grid.keypress((maxcol,), key)

                self.assertEqual(expected, grid.get_pref_col((maxcol,)))

    def test_pref_col_kept_across_rows(self) -> None:
        """Up and down between the rows of the grid keep the column, as in a :class:`Pile` of :class:`Columns`."""
        grid = urwid.GridFlow(
            [SelectableText(char) for char in "abcdef"],
            cell_width=5,
            h_sep=1,
            v_sep=0,
            align="left",
            focus=1,
        )
        self.assertTrue(grid.move_cursor_to_coords((11,), 9, 0))

        self.assertIsNone(grid.keypress((11,), "down"))

        self.assertEqual(3, grid.focus_position)
        self.assertEqual(9, grid.get_pref_col((11,)))

    def test_pref_col_dropped(self) -> None:
        """A focus or contents change drops the kept column, so the focus cell gives its centre.

        The cells are 5 wide at columns 0-4, 6-10 and 12-16; the column 10 is kept for the cell at 6-10.
        """

        def click(grid: urwid.GridFlow) -> None:
            self.assertTrue(grid.mouse_event((20,), "mouse press", 1, 13, 0, True))

        def focus_away_and_back(grid: urwid.GridFlow) -> None:
            grid.focus_position = 2
            grid.focus_position = 1

        def replace_focus_cell(grid: urwid.GridFlow) -> None:
            # the focus index stays the same, so only the contents change drops the column
            grid.contents[1] = (SelectableText("x"), grid.options())

        cases = (
            # name, action, expected focus position, expected preferred column
            ("click on another cell", click, 2, 14),
            ("focus set away and back", focus_away_and_back, 1, 8),
            ("focus cell replaced", replace_focus_cell, 1, 8),
        )
        for name, action, focus, expected in cases:
            with self.subTest(name):
                grid = urwid.GridFlow(
                    [SelectableText(char) for char in "abc"],
                    cell_width=5,
                    h_sep=1,
                    v_sep=0,
                    align="left",
                    focus=1,
                )
                self.assertTrue(grid.move_cursor_to_coords((20,), 10, 0))

                action(grid)

                self.assertEqual(focus, grid.focus_position)
                self.assertEqual(expected, grid.get_pref_col((20,)))

    def test_pref_col_not_kept_after_contents_change_by_cell(self) -> None:
        """A cell that changes the contents while it moves its cursor leaves no column kept."""

        class InsertingText(SelectableText):
            def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
                grid.contents.insert(0, (urwid.Text("z"), grid.options()))
                return True

        grid = urwid.GridFlow(
            [SelectableText("a"), SelectableText("b"), InsertingText("c")],
            cell_width=5,
            h_sep=1,
            v_sep=0,
            align="left",
            focus=1,
        )

        self.assertTrue(grid.move_cursor_to_coords((30,), 13, 0))

        self.assertEqual(6 * grid.focus_position + 2, grid.get_pref_col((30,)))

    def test_pref_col_not_kept_after_focus_changed_handler(self) -> None:
        """A "focus changed" handler that moves the focus again or empties the grid leaves no column kept.

        Three 5 wide cells fit in a row, at columns 0-4, 6-10 and 12-16.
        """

        def redirect(grid: urwid.GridFlow, _old: int | None, new: int | None) -> None:
            if new == 2:
                grid.focus_position = 1

        def empty(grid: urwid.GridFlow, _old: int | None, new: int | None) -> None:
            if new == 4:
                del grid.contents[:]

        def enter_last_cell(grid: urwid.GridFlow) -> None:
            grid.move_cursor_to_coords((17,), 16, 0)

        def down_from_middle_cell(grid: urwid.GridFlow) -> None:
            grid.move_cursor_to_coords((17,), 9, 0)
            grid.keypress((17,), "down")

        cases = (
            # name, handler, action, expected preferred column (None: empty grid)
            ("focus moved again", redirect, enter_last_cell, 8),
            ("grid emptied", empty, down_from_middle_cell, None),
        )
        for name, handler, action, expected in cases:
            with self.subTest(name):
                grid = urwid.GridFlow(
                    [SelectableText(char) for char in "abcdef"],
                    cell_width=5,
                    h_sep=1,
                    v_sep=0,
                    align="left",
                    focus=0,
                )
                urwid.connect_signal(grid, "focus changed", handler)

                action(grid)

                if expected is None:
                    self.assertEqual(0, len(grid))
                    self.assertEqual(1, grid.render((17,)).rows())
                else:
                    self.assertEqual(expected, grid.get_pref_col((17,)))

    def test_pref_col_through_pile(self) -> None:
        """Down through a grid of cells without their own column keeps the cursor column of the widget above."""
        top = urwid.Edit("", "x" * 16)
        top.edit_pos = 10
        bottom = urwid.Edit("", "y" * 16)
        grid = urwid.GridFlow(
            [SelectableText(char) for char in "abc"],
            cell_width=5,
            h_sep=1,
            v_sep=0,
            align="left",
            focus=1,
        )
        pile = urwid.Pile([top, grid, bottom])

        for _ in range(2):
            self.assertIsNone(pile.keypress((17,), "down"))

        self.assertEqual(10, bottom.edit_pos)

    def test_pack_cells(self) -> None:
        """A ``'pack'`` cell is as wide as its widget packs to, and at most as wide as the grid."""
        grid = urwid.GridFlow([], cell_width=1, h_sep=1, v_sep=0, align=urwid.LEFT)
        grid.contents.extend(
            (urwid.Text(label), grid.options(urwid.PACK)) for label in ("a", "bbbb", "cc", "dddddd", "e", "f" * 12)
        )

        with self.subTest("fixed"):
            self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), grid.sizing())
            self.assertEqual((31, 1), grid.pack(()))
            self.assertEqual(("a bbbb cc dddddd e ffffffffffff",), grid.render(()).decoded_text)

        with self.subTest("flow"):
            self.assertEqual(
                ("a bbbb cc ", "dddddd e  ", "ffffffffff", "ff        "),
                grid.render((10,)).decoded_text,
            )

    def test_pack_cell_uses_fixed_width_first(self) -> None:
        """A widget that fills any flow width, such as a ``Button``, takes its fixed width in a ``'pack'`` cell."""
        grid = urwid.GridFlow(
            [urwid.Button("OK"), urwid.Button("Cancel")],
            cell_width=10,
            h_sep=1,
            v_sep=0,
            align="left",
        )
        grid.contents[:] = [(widget, grid.options("pack")) for widget, _options in grid.contents]

        self.assertEqual(("< OK > < Cancel >   ",), grid.render((20,)).decoded_text)

    def test_pack_cell_follows_its_widget(self) -> None:
        """A ``'pack'`` cell is measured again when its widget changes width, with no contents change."""
        text = urwid.Text("ab")
        grid = urwid.GridFlow([], cell_width=1, h_sep=1, v_sep=0, align=urwid.LEFT)
        grid.contents.extend(((text, grid.options("pack")), (urwid.Text("cd"), grid.options("pack"))))
        self.assertEqual(("ab cd ",), grid.render((6,)).decoded_text)

        text.set_text("abcd")

        self.assertEqual(("abcd  ", "cd    "), grid.render((6,)).decoded_text)

    def test_pack_cell_flow_only(self) -> None:
        """A ``'pack'`` cell holding a FLOW-only widget limits the grid to FLOW sizing."""
        grid = urwid.GridFlow([urwid.Edit("x: ")], cell_width=10, h_sep=1, v_sep=0, align=urwid.LEFT)
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), grid.sizing())

        grid.contents[0] = (grid.contents[0][0], grid.options("pack"))

        self.assertEqual(frozenset((urwid.FLOW,)), grid.sizing())

    def test_default_focus(self):
        with self.subTest("Simple"):
            grid = urwid.GridFlow(
                (urwid.Button("btn"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertTrue(grid.selectable())
            self.assertEqual(0, grid.focus_position)

        with self.subTest("Simple not selectable"):
            grid = urwid.GridFlow(
                (urwid.Text("btn"), urwid.Text("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertFalse(grid.selectable())
            self.assertEqual(0, grid.focus_position)

        with self.subTest("Explicit index"):
            grid = urwid.GridFlow(
                (urwid.Button("btn"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
                focus=1,
            )
            self.assertEqual(1, grid.focus_position)

        with self.subTest("Explicit widget"):
            btn2 = urwid.Button("btn 2")
            grid = urwid.GridFlow(
                (urwid.Button("btn"), btn2),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
                focus=btn2,
            )
            self.assertEqual(1, grid.focus_position)

        with self.subTest("Selectable not first"):
            grid = urwid.GridFlow(
                (urwid.Text("text"), urwid.Button("btn")),
                cell_width=10,
                h_sep=1,
                v_sep=1,
                align=urwid.CENTER,
            )
            self.assertEqual(1, grid.focus_position)

    def test_cell_width(self):
        gf = urwid.GridFlow([], 5, 0, 0, "left")
        self.assertEqual(gf.cell_width, 5)

    def test_not_fit(self):
        """Test scenario with maxcol < cell_width (special case, warning will be produced)."""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second")],
            5,
            0,
            0,
            "left",
        )
        size = (3,)
        with self.assertWarns(urwid.widget.GridFlowWarning):
            canvas = widget.render(size)

        self.assertEqual(
            ("< f", "  i", "  r", "  s", "  t", "< s", "  e", "  c", "  o", "  n", "  d"),
            canvas.decoded_text,
        )

    def test_not_fit_widest_cell(self) -> None:
        """The warning compares the size with the widest cell, not with ``cell_width``."""
        grid = urwid.GridFlow([], cell_width=1, h_sep=0, v_sep=0, align=urwid.LEFT)
        grid.contents.append((urwid.Text("hidden files"), grid.options(urwid.GIVEN, 12)))

        with self.assertWarns(urwid.widget.GridFlowWarning):
            canvas = grid.render((6,))

        self.assertEqual(("hidden", "files "), canvas.decoded_text)

    def test_multiline(self):
        """Test widgets fit only with multiple lines"""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second")],
            10,
            0,
            0,
            "left",
        )
        size = (10,)
        canvas = widget.render(size)
        self.assertEqual(
            ("< first  >", "< second >"),
            canvas.decoded_text,
        )

    def test_multiline_2(self):
        """Test widgets fit only with multiple lines"""
        widget = urwid.GridFlow(
            [urwid.Button("first"), urwid.Button("second"), urwid.Button("third"), urwid.Button("forth")],
            10,
            0,
            0,
            "left",
        )
        size = (20,)
        canvas = widget.render(size)
        self.assertEqual(
            (
                "< first  >< second >",
                "< third  >< forth  >",
            ),
            canvas.decoded_text,
        )

    def test_basics(self):
        repr(urwid.GridFlow([], 5, 0, 0, "left"))  # should not fail

    def test_v_sep(self):
        gf = urwid.GridFlow([urwid.Text("test")], 10, 3, 1, "center")
        self.assertEqual(gf.rows((40,), False), 1)

    def test_keypress_v_sep_0(self):
        """
        Ensure proper keypress handling when v_sep is 0.
        https://github.com/urwid/urwid/issues/387
        """
        call_back = mock.Mock()
        button = urwid.Button("test", call_back)
        gf = urwid.GridFlow([button], 10, 3, v_sep=0, align="center")
        self.assertEqual(gf.keypress((20,), "enter"), None)
        call_back.assert_called_with(button)

    def test_keypress_callback_can_set_focus_position(self):
        """
        A callback fired by the keypress may set the focus itself.
        https://github.com/urwid/urwid/issues/194
        """
        gf = urwid.GridFlow(
            [urwid.Button(f"b{idx}", lambda _btn: setattr(gf, "focus_position", 1)) for idx in range(4)],
            10,
            1,
            0,
            "left",
        )
        gf.focus_position = 2

        self.assertEqual(gf.keypress((80,), "enter"), None)
        self.assertEqual(1, gf.focus_position)

    def test_keypress_without_callback_still_follows_the_display_widget(self):
        gf = urwid.GridFlow([urwid.Button(f"b{idx}") for idx in range(4)], 10, 1, 0, "left")
        gf.focus_position = 0

        self.assertEqual(gf.keypress((80,), "right"), None)
        self.assertEqual(1, gf.focus_position)

    def test_mouse_event_callback_can_set_focus_position(self):
        """
        Same as the keypress case, for a callback fired by a click.
        """
        gf = urwid.GridFlow(
            [urwid.Button(f"b{idx}", lambda _btn: setattr(gf, "focus_position", 1)) for idx in range(4)],
            10,
            1,
            0,
            "left",
        )
        gf.focus_position = 0
        gf.render((80,))

        # column 35 is inside the fourth cell
        self.assertTrue(gf.mouse_event((80,), "mouse press", 1, 35, 0, True))
        self.assertEqual(1, gf.focus_position)

    def test_mouse_event_without_callback_still_follows_the_display_widget(self):
        gf = urwid.GridFlow([urwid.Button(f"b{idx}") for idx in range(4)], 10, 1, 0, "left")
        gf.focus_position = 0
        gf.render((80,))

        self.assertTrue(gf.mouse_event((80,), "mouse press", 1, 35, 0, True))
        self.assertEqual(3, gf.focus_position)

    def test_mouse_event_not_handled_by_a_cell(self) -> None:
        """An event no cell handles and that moves no focus is unhandled, so a parent ListBox scrolls on the wheel."""
        for name, button, col in (("wheel", 5, 2), ("click beside the cells", 1, 30)):
            with self.subTest(name):
                gf = urwid.GridFlow([urwid.Button("b")], 10, 1, 0, "left")
                self.assertFalse(gf.mouse_event((40,), "mouse press", button, col, 0, True))

        with self.subTest("click that only moves the focus"):
            gf = urwid.GridFlow([SelectableText("a"), SelectableText("b")], 4, 1, 0, "left")
            self.assertTrue(gf.mouse_event((20,), "mouse press", 1, 6, 0, True))
            self.assertEqual(1, gf.focus_position)

        rows = [urwid.Text(str(idx)) for idx in range(10)]
        listbox = urwid.ListBox([*rows, urwid.GridFlow([urwid.Button("b")], 10, 1, 0, "left"), *rows])
        listbox.focus_position = 10
        listbox.render((20, 5), focus=True)
        offset, _inset = listbox.get_focus_offset_inset((20, 5))
        self.assertTrue(listbox.mouse_event((20, 5), "mouse press", 5, 2, offset, True))
        listbox.render((20, 5), focus=True)
        self.assertEqual(offset - 1, listbox.get_focus_offset_inset((20, 5))[0])

    def test_mouse_event_callback_can_shrink_contents(self):
        """A click whose callback replaces the contents with fewer cells keeps the new focus."""
        new_cells = [urwid.Button(f"n{idx}") for idx in range(3)]
        gf = urwid.GridFlow(
            [urwid.Button(f"b{idx}", lambda _btn: gf.contents.__setitem__(slice(None), new_items)) for idx in range(6)],
            10,
            1,
            0,
            "left",
        )
        new_items = [(cell, gf.options()) for cell in new_cells]
        gf.focus_position = 0
        gf.render((80,))

        # column 60 is inside the sixth cell
        self.assertTrue(gf.mouse_event((80,), "mouse press", 1, 60, 0, True))
        self.assertEqual(new_items, list(gf.contents))
        self.assertEqual(0, gf.focus_position)

    def test_mouse_event_callback_can_replace_contents_same_length(self):
        """A click whose callback replaces the contents does not move the focus to the clicked index."""
        new_cells = [urwid.Button(f"n{idx}") for idx in range(6)]
        gf = urwid.GridFlow(
            [urwid.Button(f"b{idx}", lambda _btn: gf.contents.__setitem__(slice(None), new_items)) for idx in range(6)],
            10,
            1,
            0,
            "left",
        )
        new_items = [(cell, gf.options()) for cell in new_cells]
        gf.focus_position = 0
        gf.render((80,))

        self.assertTrue(gf.mouse_event((80,), "mouse press", 1, 60, 0, True))
        self.assertEqual(new_items, list(gf.contents))
        self.assertEqual(0, gf.focus_position)

    def _replacing_grid(self, new_count: int) -> tuple[urwid.GridFlow, list[tuple[urwid.Widget, tuple]]]:
        """Build a GridFlow whose first cell replaces the contents and leaves the key unhandled."""

        class Replacer(urwid.SelectableIcon):
            """Selectable cell that replaces the GridFlow contents on any key."""

            def keypress(self, size: tuple[int], key: str) -> str:
                gf.contents[:] = new_items
                return key

        gf = urwid.GridFlow([Replacer("r"), *(urwid.Button(f"b{idx}") for idx in range(5))], 10, 1, 0, "left")
        new_items = [(urwid.Button(f"n{idx}"), gf.options()) for idx in range(new_count)]
        gf.focus_position = 0
        return gf, new_items

    def test_keypress_handler_can_shrink_contents(self):
        """A key whose handler replaces the contents with fewer cells keeps the new focus."""
        gf, new_items = self._replacing_grid(1)

        self.assertEqual(gf.keypress((80,), "right"), None)
        self.assertEqual(new_items, list(gf.contents))
        self.assertEqual(0, gf.focus_position)

    def test_keypress_handler_can_replace_contents_same_length(self):
        """A key whose handler replaces the contents does not move the focus by the stale display widget."""
        gf, new_items = self._replacing_grid(6)

        self.assertEqual(gf.keypress((80,), "right"), None)
        self.assertEqual(new_items, list(gf.contents))
        self.assertEqual(0, gf.focus_position)

    def test_length(self):
        grid = urwid.GridFlow((urwid.Text(c) for c in "ABC"), 1, 0, 0, "left")
        self.assertEqual(3, len(grid))
        self.assertEqual(3, len(grid.contents))

    def test_common(self):
        gf = urwid.GridFlow([], 5, 1, 0, "left")

        with self.subTest("Focus"):
            self.assertEqual(gf.focus, None)
            self.assertEqual(gf.contents, [])
            self.assertRaises(IndexError, lambda: gf.focus_position)
            self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", None))
            self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", 0))

        with self.subTest("Contents options"):
            self.assertEqual(gf.options(), ("given", 5))
            self.assertEqual(gf.options(width_amount=9), ("given", 9))
            self.assertEqual(gf.options("pack"), ("pack", None))
            self.assertRaises(urwid.GridFlowError, lambda: gf.options("weight", None))
            self.assertRaises(urwid.GridFlowError, lambda: gf.options("pack", 3))

    def test_focus_position(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, "left")
        self.assertEqual(gf.focus, t1)
        self.assertEqual(gf.focus_position, 0)
        self.assertEqual(gf.contents, [(t1, ("given", 5)), (t2, ("given", 5))])
        gf.focus_position = 1
        self.assertEqual(gf.focus, t2)
        self.assertEqual(gf.focus_position, 1)
        gf.contents.insert(0, (t2, ("given", 5)))
        self.assertEqual(gf.focus_position, 2)
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.append(()))
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.insert(1, (t1, ("weight", 1))))
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.insert(1, (t1, ("pack", 3))))
        gf.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(gf, "focus_position", 3))

    def test_empty(self):
        """Test behaviour of empty widget."""
        grid = urwid.GridFlow(
            (),
            cell_width=10,
            h_sep=1,
            v_sep=1,
            align=urwid.CENTER,
        )
        self.assertEqual(frozenset((urwid.FLOW,)), grid.sizing(), "Empty grid can not be handled as FIXED")
        rows = 1
        with self.subTest("Flow"):
            maxcol = 1
            self.assertEqual((maxcol, rows), grid.pack((maxcol,)))
            rendered = grid.render((maxcol,))
            self.assertEqual(maxcol, rendered.cols())
            self.assertEqual(rows, rendered.rows())

        with self.subTest("Fixed"):
            maxcol = 0
            self.assertEqual((maxcol, rows), grid.pack(()))
            with self.assertRaises(ValueError):
                grid.render(())

    def test_cell_width_setter(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, "left")
        gf.focus_position = 1
        gf.cell_width = 8
        self.assertEqual(gf.cell_width, 8)
        self.assertEqual(gf.contents, [(t1, ("given", 8)), (t2, ("given", 8))])
        self.assertEqual(gf.focus_position, 1)

    def test_contents_setter(self):
        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, "left")
        gf.contents = [(t2, gf.options())]
        self.assertEqual(gf.contents, [(t2, ("given", 5))])
        self.assertEqual(len(gf), 1)

    def test_v_sep_gt_1(self):
        """Divider height grows with v_sep when wrapping to multiple rows."""
        widget = urwid.GridFlow([urwid.Text("first"), urwid.Text("second")], 10, 0, 2, "left")
        canvas = widget.render((10,))
        self.assertEqual(4, canvas.rows())
        self.assertEqual(
            ("first     ", "          ", "          ", "second    "),
            canvas.decoded_text,
        )

    def test_keypress_unhandled_key_passed_through(self):
        gf = urwid.GridFlow([urwid.Text("a"), urwid.Text("b")], 10, 0, 0, "left")
        self.assertEqual("x", gf.keypress((10,), "x"))

    def test_get_cursor_coords_and_pref_col(self):
        e1 = urwid.Edit("", "hello")
        e2 = urwid.Edit("", "world")
        gf = urwid.GridFlow([e1, e2], 10, 1, 0, "left")
        gf.focus_position = 0
        e1.set_edit_pos(3)
        self.assertEqual((3, 0), gf.get_cursor_coords((30,)))
        self.assertEqual(3, gf.get_pref_col((30,)))

    def test_move_cursor_to_coords(self):
        e1 = urwid.Edit("", "hello")
        e2 = urwid.Edit("", "world")
        gf = urwid.GridFlow([e1, e2], 10, 1, 0, "left")
        gf.focus_position = 0
        self.assertTrue(gf.move_cursor_to_coords((30,), 15, 0))
        self.assertEqual(1, gf.focus_position)

    def test_set_focus_from_display_widget_no_pile_focus(self):
        """When the Pile display widget has no focus, the helper is a no-op."""
        gf = urwid.GridFlow([urwid.Button("a")], 10, 0, 0, "left")
        gf._w = mock.Mock(focus=None)
        gf._set_focus_from_display_widget()
        self.assertEqual(0, gf.focus_position)

    def test_set_focus_from_display_widget_column_no_focus(self):
        """When the focused column's widget itself is falsy, column focus position defaults to 0."""
        inner = urwid.GridFlow([], 5, 0, 0, "left")  # empty GridFlow is falsy (len 0)
        gf = urwid.GridFlow([inner], 10, 0, 0, "left")
        gf.render((10,))
        gf._set_focus_from_display_widget()
        self.assertEqual(0, gf.focus_position)

    def test_focus_changed_callback_replacement(self) -> None:
        """Replace the contents focus callback and read the new index before it is applied."""
        first = urwid.Button("first")
        second = urwid.Button("second")
        grid = urwid.GridFlow((first, second), cell_width=10, h_sep=1, v_sep=0, align=urwid.LEFT)
        seen: list[tuple[int, int, urwid.Widget]] = []

        def on_focus_change(new_focus: int) -> None:
            seen.append((new_focus, grid.focus_position, grid.contents[new_focus][0]))
            grid._invalidate()

        grid.contents.set_focus_changed_callback(on_focus_change)
        grid.focus_position = 1

        self.assertEqual([(1, 0, second)], seen)
        self.assertIs(second, grid.focus)
        self.assertEqual(1, grid.focus_position)


class FramedGridFlow(urwid.GridFlow):
    """GridFlow whose display widget is wrapped in a LineBox."""

    def generate_display_widget(self, size):
        """Return the standard display widget inside a LineBox."""
        return urwid.LineBox(super().generate_display_widget(size))


class TabBarLikeGridFlow(urwid.GridFlow):
    """GridFlow whose iteration yields widgets and whose ``focus`` is an index, as some applications do."""

    def __iter__(self):
        """Iterate over the cell widgets."""
        return iter(widget for widget, _ in self.contents)

    @property
    def focus(self):
        """Return the index of the focused cell."""
        return self.focus_position


class GridFlowSelectNavigationTest(unittest.TestCase):
    """``select_navigation`` moves the focus over the cells in their contents order."""

    size = (8,)

    def _cells(self) -> list[urwid.Widget]:
        return [urwid.Button("a"), urwid.Text("-"), urwid.Button("b"), urwid.Button("c")]

    def _grid(self, cls: type[urwid.GridFlow] = urwid.GridFlow, *, select_navigation: bool = True) -> urwid.GridFlow:
        return cls(self._cells(), 5, 1, 0, "left", select_navigation=select_navigation)

    def test_off_by_default(self) -> None:
        """Without the flag the key is returned and the entry hook keeps the focus."""
        grid = self._grid(select_navigation=False)
        self.assertEqual("tab", grid.keypress(self.size, "tab"))
        self.assertEqual(0, grid.focus_position)
        grid.focus_position = 2
        grid.enter_selectable()
        self.assertEqual(2, grid.focus_position)

    def test_generate_display_widget_override(self) -> None:
        """A subclass that overrides ``generate_display_widget`` is drawn with the widget it returns."""
        grid = FramedGridFlow([urwid.Text("ab")], cell_width=4, h_sep=1, v_sep=0, align="left")

        self.assertEqual(("┌────────┐", "│ab      │", "└────────┘"), grid.render((10,)).decoded_text)

    def test_traversal(self) -> None:
        """Steps follow the contents order across rows, and past the edge the key is returned after a reset."""
        for cls in (urwid.GridFlow, FramedGridFlow, TabBarLikeGridFlow):
            with self.subTest(cls=cls.__name__):
                grid = self._grid(cls)
                self.assertIsNone(grid.keypress(self.size, "tab"))
                self.assertEqual(2, grid.focus_position)
                self.assertIsNone(grid.keypress(self.size, "tab"))
                self.assertEqual(3, grid.focus_position)
                self.assertEqual("tab", grid.keypress(self.size, "tab"))
                self.assertEqual(0, grid.focus_position)
                self.assertEqual("shift tab", grid.keypress(self.size, "shift tab"))
                self.assertEqual(3, grid.focus_position)
                self.assertIsNone(grid.keypress(self.size, "shift tab"))
                self.assertEqual(2, grid.focus_position)

    def test_entered_from_parent(self) -> None:
        """A parent entering the GridFlow moves the GridFlow's own focus, and the rendered focus follows."""
        grid = self._grid()
        grid.focus_position = 2
        pile = urwid.Pile([urwid.Button("x"), grid], select_navigation=True)
        self.assertIsNone(pile.keypress(self.size, "tab"))
        self.assertEqual(0, grid.focus_position)
        canvas = pile.render(self.size, focus=True)
        self.assertEqual((2, 1), canvas.cursor)  # the label of "a", on the first row of the GridFlow
        self.assertIsNone(pile.keypress(self.size, "shift tab"))
        self.assertEqual(0, pile.focus_position)
        grid.focus_position = 0
        self.assertEqual("shift tab", pile.keypress(self.size, "shift tab"))
        self.assertEqual(1, pile.focus_position)
        self.assertEqual(3, grid.focus_position)

    def test_not_opted_in_kept_when_entered(self) -> None:
        """A GridFlow without the flag is one stop and keeps its focus."""
        grid = self._grid(select_navigation=False)
        grid.focus_position = 2
        pile = urwid.Pile([urwid.Button("x"), grid], select_navigation=True)
        self.assertIsNone(pile.keypress(self.size, "tab"))
        self.assertEqual(2, grid.focus_position)
        self.assertEqual("tab", pile.keypress(self.size, "tab"))
        self.assertEqual(0, pile.focus_position)
