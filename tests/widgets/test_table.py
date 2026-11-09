"""Tests of Table, TableRow and TableLayout."""

from __future__ import annotations

import gc
import math
import sys
import typing
import unittest
import weakref
from unittest import mock

import urwid
from tests.util import SelectableText
from urwid.testing import check_flow_sizing, check_sizing, click, press, render_runs, render_text
from urwid.widget import TableLayout
from urwid.widget import table as table_module

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

PACK = urwid.PACK
WEIGHT = urwid.WEIGHT
Column = urwid.TableColumn


class CountingText(urwid.Text):
    """Text that counts its ``pack()`` calls."""

    def __init__(self, markup: str) -> None:
        """Create the text with a zero call count."""
        super().__init__(markup)
        self.packs = 0

    def pack(self, size=None, focus=False):
        """Count the call and pack as Text does."""
        self.packs += 1
        return super().pack(size, focus)


class TableLayoutTest(unittest.TestCase):
    """Tests of the shared widths, without a Table."""

    def test_validation(self) -> None:
        """An invalid specification is rejected when the layout takes it, naming the column."""
        for columns, kwargs in (
            ([Column(width=-1)], {}),
            ([Column(width=1.5)], {}),
            ([Column(width=True)], {}),
            ([Column(width=(WEIGHT, 0))], {}),
            ([Column(width=(WEIGHT, -1))], {}),
            ([Column(width=(WEIGHT, math.inf))], {}),
            ([Column(width=(WEIGHT, math.nan))], {}),
            ([Column(width=(WEIGHT, "1"))], {}),
            ([Column(width=("given", 1))], {}),
            ([Column(min_width=0)], {}),
            ([Column(width=(WEIGHT, 1), min_width=1.5)], {}),
            ([Column(align="justify")], {}),
            ([Column(wrap="any")], {}),
            ([("a", PACK)], {}),
            ([Column()], {"dividechars": -1}),
            ([Column()], {"dividechars": 1.0}),
        ):
            with self.subTest(columns=columns, kwargs=kwargs), self.assertRaises(urwid.TableError):
                TableLayout(columns, **kwargs)

        for invalid in (Column(width=-1), Column(attr={"a": []})):
            with (
                self.subTest("the index is named", column=invalid),
                self.assertRaisesRegex(urwid.TableError, "column 1"),
            ):
                TableLayout([Column(), invalid])

        with self.subTest("a given width of 0 ignores min_width"):
            self.assertEqual((0, 1), TableLayout([Column(width=0, min_width=0), Column()]).widths(5))

    def test_rows_share_widths(self) -> None:
        """Rows built through one layout line up, and a wider row widens every row."""
        layout = TableLayout([Column(), Column(align=urwid.RIGHT), Column()])
        pile = urwid.Pile([layout.row(["a", "1", "x"]), layout.row(["bbb", "22"])])
        self.assertEqual(["a    1 x", "bbb 22  "], render_text(pile, (8,)))
        pile.contents.append((layout.row(["cccc", "333", "y"]), pile.options()))
        self.assertEqual(["a      1 x", "bbb   22  ", "cccc 333 y"], render_text(pile, (10,)))

    def test_wide_characters(self) -> None:
        """Cells are measured in screen columns, so wide characters line up."""
        layout = TableLayout([Column(), Column()])
        pile = urwid.Pile([layout.row(["中文", "a"]), layout.row(["ab", "b"])])
        self.assertEqual(["中文 a", "ab   b"], render_text(pile, (6,)))

    def test_multi_line_cell(self) -> None:
        """The widest line of a cell is its width."""
        layout = TableLayout([Column(), Column()])
        pile = urwid.Pile([layout.row(["a\nlonger", "x"]), layout.row(["b", "y"])])
        self.assertEqual(["a      x", "longer  ", "b      y"], render_text(pile, (8,)))

    def test_unmeasurable_cell(self) -> None:
        """A FLOW-only cell is not measured: it counts as min_width in a PACK column."""
        edit = urwid.Edit("", "a long value")
        layout = TableLayout([Column(min_width=3), Column()])
        rows = [layout.row([edit, "x"]), layout.row(["ab", "y"])]
        self.assertEqual((3, 1), layout.widths(10))
        self.assertEqual(5, layout.natural_width())
        self.assertEqual([None, 1], list(rows[0]._cell_widths))

    def test_cell_kinds(self) -> None:
        """Buttons, check boxes, decorations and nested Columns are cells; a BOX-only widget is not."""
        layout = TableLayout([Column(), Column(), Column()])
        row = layout.row([urwid.Button("ok"), urwid.CheckBox("c"), urwid.AttrMap(urwid.Text("t"), "x")])
        self.assertEqual(1, row.rows((40,)))
        layout.row([urwid.Padding(urwid.Text("p"), width=3), urwid.Columns([urwid.Text("a"), urwid.Text("b")])])
        layout.row([urwid.Columns([(PACK, urwid.Text("a")), (PACK, urwid.Text("b"))])])
        with self.assertRaises(urwid.TableError):
            layout.row([urwid.SolidFill("x")])

    def test_row_length(self) -> None:
        """A short row is padded with empty text cells; a long row is rejected."""
        layout = TableLayout([Column(), Column()])
        row = layout.row(["a"])
        self.assertEqual(2, len(row.cells))
        self.assertEqual("", typing.cast("urwid.Text", row.cells[1]).text)
        with self.assertRaises(urwid.TableError):
            layout.row(["a", "b", "c"])
        for text in ("ab", b"ab"):
            with self.subTest(text=text), self.assertRaisesRegex(urwid.TableError, "not text"):
                layout.row(text)

    def test_cells_are_copied(self) -> None:
        """Changing the list the row was built from changes nothing."""
        layout = TableLayout([Column(), Column()])
        cells: list[typing.Any] = ["a", "b"]
        row = layout.row(cells)
        cells.append("c")
        self.assertEqual(2, len(row.cells))

    def test_fit(self) -> None:
        """Given and PACK columns keep their width, weighted columns share the rest as Columns shares it."""
        layout = TableLayout(
            [Column(width=3), Column(width=(WEIGHT, 1)), Column(width=(WEIGHT, 2)), Column()],
            dividechars=1,
        )
        row = layout.row(["a", "b", "c", "dd"])
        columns = urwid.Columns(
            [
                (3, urwid.Text("a")),
                (WEIGHT, 1, urwid.Text("b")),
                (WEIGHT, 2, urwid.Text("c")),
                (PACK, urwid.Text("dd")),
            ],
            dividechars=1,
        )
        for maxcol in (10, 17, 40):
            with self.subTest(maxcol=maxcol):
                self.assertEqual(tuple(columns.column_widths((maxcol,))), layout.widths(maxcol))
        self.assertIsNotNone(row)

    def test_rounding_and_minimum(self) -> None:
        """A weighted column pinned at its minimum leaves the others the rest, and the total never exceeds maxcol."""
        layout = TableLayout(
            [Column(width=(WEIGHT, 1), min_width=5), Column(width=(WEIGHT, 1)), Column(width=(WEIGHT, 1))],
            dividechars=0,
        )
        self.assertEqual((5, 3, 2), layout.widths(10))
        for maxcol in range(7, 40):
            with self.subTest(maxcol=maxcol):
                widths = layout.widths(maxcol)
                self.assertEqual(maxcol, sum(widths))
                self.assertGreaterEqual(widths[0], 5)

    def test_minimum_pinned_last(self) -> None:
        """A weighted column pinned at a large minimum after the others took their share takes the room back."""
        layout = TableLayout(
            [Column(width=(WEIGHT, 1)), Column(width=(WEIGHT, 1)), Column(width=(WEIGHT, 1), min_width=5)],
            dividechars=0,
        )
        self.assertEqual((1, 1, 5), layout.widths(7))
        self.assertEqual((2, 2, 5), layout.widths(9))

    def test_huge_weights(self) -> None:
        """Weights whose product with the room could overflow a float keep their ratio."""
        layout = TableLayout([Column(width=(WEIGHT, sys.float_info.max)), Column(width=(WEIGHT, sys.float_info.max))])
        self.assertEqual((5, 4), layout.widths(10))

    def test_overflow(self) -> None:
        """Weighted columns go to their minimum, PACK columns shrink by their slack, given widths are kept."""
        layout = TableLayout(
            [Column(width=4), Column(min_width=2), Column(min_width=4), Column(width=(WEIGHT, 1), min_width=2)],
            dividechars=1,
        )
        row = layout.row(["a", "x" * 10, "y" * 6, "z"])
        # natural 4 + 10 + 6 + 2 + 3 dividers = 25
        self.assertEqual((4, 10, 6, 2), layout.widths(25))
        # 5 short: slack 8 and 2 give up 5 * 8 // 10 = 4 and 5 * 2 // 10 = 1
        self.assertEqual((4, 6, 5, 2), layout.widths(20))
        # 9 short: 7 and 1, then one more from the widest shrunk column
        self.assertEqual((4, 3, 4, 2), layout.widths(16))
        # 10 short: every PACK column at its minimum
        self.assertEqual((4, 2, 4, 2), layout.widths(15))
        # no slack left: the rightmost column is hidden with its divider, and the others shrink again from natural
        self.assertEqual((4, 4, 4, 0), layout.widths(14))
        self.assertEqual((4, 2, 4, 0), layout.widths(12))
        self.assertEqual((4, 6, 0, 0), layout.widths(11))
        self.assertEqual((4, 2, 0, 0), layout.widths(7))
        self.assertEqual((4, 0, 0, 0), layout.widths(5))
        self.assertEqual((4, 0, 0, 0), layout.widths(4))
        self.assertEqual((0, 0, 0, 0), layout.widths(3))
        self.assertEqual((0, 0, 0, 0), layout.widths(0))
        with self.assertRaises(urwid.TableError):
            layout.widths(-1)
        self.assertIsNotNone(row)

    def test_review_example(self) -> None:
        """Given 9 and a weighted minimum of 4 in 10 columns: the weighted column is hidden, the given one kept."""
        layout = TableLayout([Column(width=9), Column(width=(WEIGHT, 1), min_width=4)], dividechars=0)
        self.assertEqual((9, 0), layout.widths(10))

    def test_hidden_column_removes_divider(self) -> None:
        """A column of given width 0 has no divider, and neither has a column hidden for lack of room."""
        layout = TableLayout([Column(), Column(width=0), Column()], dividechars=2)
        pile = urwid.Pile([layout.row(["a", "hidden", "b"])])
        self.assertEqual(["a  b"], render_text(pile, (4,)))
        self.assertEqual(4, layout.natural_width())
        self.assertEqual(["a  "], render_text(pile, (3,)))

    def test_shrunk_space_and_clip(self) -> None:
        """A shrunk SPACE column wraps its row onto more lines; a shrunk CLIP column keeps one line."""
        layout = TableLayout([Column(wrap=urwid.SPACE, min_width=3), Column(min_width=3)], dividechars=1)
        row = layout.row(["aaa bbb", "ccc ddd"])
        self.assertEqual(1, row.rows((15,)))
        self.assertEqual(["aaa ccc", "bbb    "], render_text(row, (7,)))

    def test_natural_width(self) -> None:
        """The natural width counts weighted columns at their minimum and skips hidden given columns."""
        layout = TableLayout(
            [Column("label"), Column(width=0), Column(width=(WEIGHT, 1), min_width=3), Column(width=2)]
        )
        self.assertEqual(5 + 3 + 2 + 2, layout.natural_width())
        row = layout.row(["a longer cell"])
        self.assertEqual(13 + 3 + 2 + 2, layout.natural_width())
        del row
        gc.collect()
        self.assertEqual(5 + 3 + 2 + 2, layout.natural_width())

    def test_focused_edit_does_not_widen(self) -> None:
        """Focusing an Edit cell does not change the width of its column."""
        layout = TableLayout([Column(width=(WEIGHT, 1)), Column()])
        row = layout.row([urwid.Edit("", "abc"), "x"])
        before = render_text(row, (10,))
        self.assertEqual(before, render_text(row, (10,), focus=True))
        self.assertEqual((8, 1), layout.widths(10))

    def test_table_text_measures_itself(self) -> None:
        """set_text on a text cell the layout made re-measures its column, on screen and off."""
        for attr in (None, "col"):
            with self.subTest(attr=attr):
                layout = TableLayout([Column(attr=attr), Column()])
                first = layout.row(["a", "x"])
                second = layout.row(["b", "y"])
                pile = urwid.Pile([first, second])
                self.assertEqual(["a x", "b y"], render_text(pile, (3,)))
                typing.cast("urwid.Text", first.cells[0]).set_text("wide")
                self.assertEqual(["wide x", "b    y"], render_text(pile, (6,)))
                typing.cast("urwid.Text", first.cells[0]).set_text("a")
                self.assertEqual(["a x   ", "b y   "], render_text(pile, (6,)))

                off_screen = layout.row(["c", "z"])
                typing.cast("urwid.Text", off_screen.cells[0]).set_text("offscreen")
                self.assertEqual(["a         x", "b         y"], render_text(pile, (11,)))
                self.assertIsNotNone(off_screen)

    def test_shared_table_text_updates_all_columns(self) -> None:
        """A generated text cell reused in another column keeps both widths current."""
        layout = TableLayout([Column(), Column()])
        first = layout.row(["a", "x"])
        second = layout.row([first.cells[0], first.cells[0]])
        pile = urwid.Pile([first, second])
        self.assertEqual(["a x", "a a"], render_text(pile, (3,)))
        typing.cast("urwid.Text", first.cells[0]).set_text("wide")
        self.assertEqual((4, 4), layout.widths(9))
        self.assertEqual(["wide x   ", "wide wide"], render_text(pile, (9,)))
        typing.cast("urwid.Text", first.cells[0]).set_text("a")
        self.assertEqual((1, 1), layout.widths(3))
        self.assertEqual(["a x", "a a"], render_text(pile, (3,)))

    def test_shared_table_text_survives_removed_row(self) -> None:
        """Removing and collecting a borrowing row does not steal the original cell's updates."""
        table = urwid.Table([Column()], [["a"]], header=False)
        original = table.body[0]
        borrowed = table.layout.row([original.cells[0]])
        table.body.append(borrowed)
        self.assertEqual(["a         ", "a         "], render_text(table, (10, 2)))
        table.body.pop()
        del borrowed
        gc.collect()
        typing.cast("urwid.Text", original.cells[0]).set_text("long text")
        self.assertEqual((9,), table.layout.widths(10))
        self.assertEqual(["long text "], render_text(table, (10, 1)))

    def test_shared_table_text_updates_other_layout(self) -> None:
        """Reusing a generated cell in another layout updates each independent maximum."""
        layout = TableLayout([Column()])
        first = layout.row(["a"])
        other = TableLayout([Column()])
        second = other.row([first.cells[0]])
        typing.cast("urwid.Text", first.cells[0]).set_text("wide")
        self.assertEqual((4,), layout.widths(10))
        self.assertEqual((4,), other.widths(10))
        self.assertEqual(["wide"], render_text(first, (4,)))
        self.assertEqual(["wide"], render_text(second, (4,)))

    def test_caller_widget_needs_invalidate_widths(self) -> None:
        """A caller's text widget changed in place keeps the old width until invalidate_widths()."""
        layout = TableLayout([Column(), Column()])
        cell = urwid.Text("a", wrap=urwid.CLIP)
        pile = urwid.Pile([layout.row([cell, "x"]), layout.row(["b", "y"])])
        self.assertEqual(["a x", "b y"], render_text(pile, (3,)))
        cell.set_text("wide")
        self.assertEqual(["w x", "b y"], render_text(pile, (3,)))
        layout.invalidate_widths()
        self.assertEqual(["wide x", "b    y"], render_text(pile, (6,)))

    def test_canvases_redrawn_after_width_change(self) -> None:
        """Canvases rendered at the old widths are not reused once a wider row arrives."""
        layout = TableLayout([Column(), Column()])
        rows = [layout.row(["a", "x"]), layout.row(["b", "y"])]
        pile = urwid.Pile(rows)
        old = pile.render((8,))
        self.assertEqual([b"a x     ", b"b y     "], old.text)
        wider = layout.row(["ccc", "z"])
        self.assertEqual(["a   x   ", "b   y   "], render_text(pile, (8,)))
        del wider

    def test_allocation_cache_bounded(self) -> None:
        """The layout keeps the widths of the two most recent maxcol values."""
        layout = TableLayout([Column(width=(WEIGHT, 1))])
        for maxcol in range(10):
            layout.widths(maxcol)
        self.assertEqual([8, 9], sorted(layout._allocations))
        layout.widths(8)
        layout.widths(20)
        self.assertEqual([8, 20], sorted(layout._allocations))

    def test_check_flow_sizing(self) -> None:
        """A row renders the rows its rows() reports, a span row as well."""
        layout = TableLayout([Column(), Column(width=(WEIGHT, 1)), Column(width=3)])
        check_flow_sizing(layout.row(["abc", urwid.Edit("", "x"), "d"]))
        check_flow_sizing(layout.row(["whole row"], span=True))

    def test_attribute_redraws(self) -> None:
        """Setting attr or focus_attr on a rendered row redraws it as a row built with the value."""
        layout = TableLayout([Column(), Column()])
        for name, value in (("attr", {None: "a"}), ("focus_attr", {None: "f"})):
            with self.subTest(name):
                row = layout.row(["a", "b"])
                old = render_runs(row, (5,), focus=True)
                setattr(row, name, value)
                self.assertNotEqual(old, render_runs(row, (5,), focus=True))
                self.assertEqual(
                    render_runs(layout.row(["a", "b"], **{name: value}), (5,), focus=True),
                    render_runs(row, (5,), focus=True),
                )
                self.assertEqual(value, getattr(row, name))

    def test_row_attributes(self) -> None:
        """The attr and focus_attr maps apply to the row, and a dict maps the cells' own attributes."""
        layout = TableLayout([Column(), Column()])
        row = layout.row([("cell", "a"), "b"], attr={None: "row", "cell": "row cell"}, focus_attr="focus")
        self.assertEqual([[(urwid.LayeredAttr("row cell", "row"), "a"), ("row", " b")]], render_runs(row, (3,)))
        self.assertEqual(
            [[(urwid.LayeredAttr("cell", "focus"), "a"), ("focus", " b")]], render_runs(row, (3,), focus=True)
        )
        row.attr = None
        self.assertEqual([[("cell", "a"), (None, " b")]], render_runs(row, (3,)))
        self.assertIsNone(row.index)

        with self.subTest("column attr"):
            layout = TableLayout([Column(attr="col"), Column()])
            row = layout.row(["a", "b"])
            self.assertEqual([[("col", "a"), (None, " b")]], render_runs(row, (3,)))
            self.assertNotIsInstance(row.cells[0], urwid.AttrMap)
            self.assertEqual("a", typing.cast("urwid.Text", row.cells[0]).text)
            row.attr = "row"
            row.focus_attr = {None: "focus", "col": "col focus"}
            self.assertEqual([[(urwid.LayeredAttr("col", "row"), "a"), ("row", " b")]], render_runs(row, (3,)))
            self.assertEqual(
                [[(urwid.LayeredAttr("col focus", "focus"), "a"), ("focus", " b")]], render_runs(row, (3,), focus=True)
            )

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting")
    def test_dropped_row_not_measured(self) -> None:
        """A row the caller dropped is not kept alive, and its width stops counting."""
        layout = TableLayout([Column(), Column()])
        layout.row(["a", "x"])
        kept = layout.row(["b", "y"])
        dropped = layout.row(["wide", "z"])
        self.assertEqual((4, 1), layout.widths(10))
        ref = weakref.ref(dropped)
        del dropped
        gc.collect()
        self.assertIsNone(ref())
        self.assertEqual(3, layout.natural_width())
        self.assertIsNotNone(kept)

    def test_measured_once(self) -> None:
        """Cells are packed when their row is built; renders and keys do not pack them again."""
        layout = TableLayout([Column(), Column()])
        cells = [CountingText("a"), CountingText("bb")]
        row = layout.row([cells[0], cells[1]])
        pile = urwid.Pile([row, layout.row(["c", "d"])])
        self.assertEqual([1, 1], [cell.packs for cell in cells])
        for maxcol in range(100):
            urwid.CanvasCache.clear()
            pile.render((5 + maxcol % 3,), focus=True)
            pile.keypress((5,), "down")
        self.assertEqual([1, 1], [cell.packs for cell in cells])
        layout.invalidate_widths()
        self.assertEqual([2, 2], [cell.packs for cell in cells])

    def test_invalidation_reaches_rendered_rows_only(self) -> None:
        """A width change invalidates the row columns laid out since the last change and no other."""
        layout = TableLayout([Column(), Column()])
        rows = [layout.row([str(i), "x"]) for i in range(5)]
        for row in rows[:2]:
            row.render((10,))
        invalidated: list[int] = []
        for i, row in enumerate(rows):
            original = row._w._invalidate
            row._w._invalidate = lambda i=i, original=original: (invalidated.append(i), original())[1]  # type: ignore[method-assign]
        layout.row(["wider", "x"])
        self.assertEqual([0, 1], sorted(invalidated))


class TableTest(unittest.TestCase):
    """Tests of the Table widget."""

    columns: typing.ClassVar[list[urwid.TableColumn]] = [Column("Name"), Column("N", align=urwid.RIGHT)]

    def make(self, rows: int = 3, **kwargs: typing.Any) -> urwid.Table:
        """Return a two-column table of *rows* rows."""
        return urwid.Table(self.columns, [[f"r{i}", str(i)] for i in range(rows)], **kwargs)

    def test_sizing(self) -> None:
        """A table renders the size it reports in each sizing mode it offers, empty as well."""
        for kwargs in (
            {},
            {"header": False},
            {"max_rows": 2},
            {"scrollbar": True},
            {"scrollbar": None},
            {"footer": ["t"], "header_drop": 2, "footer_drop": 1},
        ):
            with self.subTest(**kwargs):
                table = self.make(**kwargs)
                self.assertEqual(frozenset((urwid.BOX, urwid.FLOW, urwid.FIXED)), table.sizing())
                check_sizing(table, cols=20, rows=4)
        weighted = urwid.Table([Column(width=(WEIGHT, 1))], [["a"]])
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), weighted.sizing())
        check_sizing(weighted, cols=20, rows=4)
        empty = urwid.Table(self.columns)
        check_sizing(empty, cols=20, rows=4)

    def test_header_and_body_aligned(self) -> None:
        """The header and the rows share the column widths in every sizing mode."""
        table = self.make()
        table.body.append(["longer", "123"])
        self.assertEqual(
            ["Name     N", "r0       0", "r1       1", "r2       2", "longer 123"], render_text(table, (10,))
        )
        self.assertEqual(["Name     N", "r0       0", "r1       1"], render_text(table, (10, 3)))
        self.assertEqual((10, 5), table.pack(()))
        self.assertEqual(render_text(table, (10,)), render_text(table, ()))

    def test_no_header(self) -> None:
        """Without a header the rows start at the top."""
        table = self.make(header=False)
        self.assertEqual(["r0 0", "r1 1", "r2 2"], render_text(table, (4,)))

    def test_header_attr_and_label_width(self) -> None:
        """A label widens its column, and header_attr alone maps the header, without the column attr."""
        for attr in (None, "col"):
            with self.subTest(attr=attr):
                table = urwid.Table([Column("Long label", attr=attr), Column("x")], [["a", "b"]], header_attr="head")
                self.assertEqual([("head", "Long label x")], render_runs(table, (12,))[0])

    def test_footer(self) -> None:
        """The footer shares the column widths, widens its column, and stays below the rows in every sizing mode."""
        table = self.make(footer=["Total", "3"])
        self.assertEqual(
            ["Name  N   ", "r0    0   ", "r1    1   ", "r2    2   ", "Total 3   "], render_text(table, (10,))
        )
        self.assertEqual(["Name  N   ", "r0    0   ", "Total 3   "], render_text(table, (10, 3)))
        self.assertEqual((7, 5), table.pack(()))
        self.assertEqual(["Name  N", "r0    0", "r1    1", "r2    2", "Total 3"], render_text(table, ()))
        self.assertEqual(
            ["Name N", "      ", "Sum  0"], render_text(urwid.Table(self.columns, footer=["Sum", "0"]), (6, 3))
        )

    def test_footer_attr_and_text_change(self) -> None:
        """footer_attr alone maps a footer built from cells, and a changed footer text re-measures its column."""
        table = urwid.Table([Column("A", attr="col"), Column("B")], [["a", "b"]], footer=["t", "1"], footer_attr="foot")
        self.assertEqual([("foot", "t 1")], render_runs(table, (3,))[2])
        table.footer.cells[0].set_text("total")
        self.assertEqual(["A     B", "a     b", "total 1"], render_text(table, (7,)))

    def test_footer_row(self) -> None:
        """A row of the layout becomes the footer with its own maps; None removes the footer."""
        table = self.make(header=False)
        footer = table.layout.row(["3 rows"], span=True, attr="note")
        table.footer = footer
        self.assertIs(footer, table.footer)
        self.assertEqual([("note", "3 rows")], render_runs(table, (6,))[3])
        table.footer = None
        self.assertIsNone(table.footer)
        self.assertEqual(["r0 0", "r1 1", "r2 2"], render_text(table, (4,)))

    def test_footer_released_row(self) -> None:
        """A row removed from the body counts in the PACK widths again once it becomes the footer."""
        table = urwid.Table([Column()], [["x"], ["a very long cell"]], header=False)
        row = table.body[1]
        del table.body[1]
        self.assertEqual(1, table.layout.natural_width())
        table.footer = row
        self.assertEqual(16, table.layout.natural_width())
        row.cells[0].set_text("an even longer cell")
        self.assertEqual(["x", "an even longer cell"], [line.rstrip() for line in render_text(table, ())])

    def test_footer_rejected(self) -> None:
        """A footer of another layout, a row of the body, and too many cells are rejected; the body takes no footer."""
        table = self.make(footer=["t"])
        footer = table.footer
        for value in (TableLayout(self.columns).row(["x"]), table.body[0], ["a", "b", "c"], "text"):
            with self.subTest(value=value), self.assertRaises(urwid.TableError):
                table.footer = value
        self.assertIs(footer, table.footer)
        with self.assertRaises(urwid.TableError):
            table.body.append(footer)
        with self.assertRaises(urwid.TableError):
            urwid.Table(self.columns, footer=["a", "b", "c"])

    def test_drop_thresholds(self) -> None:
        """A box size that does not fit drops the part with the larger threshold first, then cuts what is left."""
        header = ["Name  N   "]
        footer = ["Tot  45   "]
        rows = [f"r{i}    {i}   " for i in range(10)]
        for kwargs, size, expected in (
            ({}, (10, 4), [*header, *rows[:2], *footer]),
            ({}, (10, 2), [*header, *footer]),
            ({}, (10, 1), header),
            ({"header_drop": 3, "footer_drop": 1}, (10, 4), [*rows[:3], *footer]),
            ({"header_drop": 3, "footer_drop": 1}, (10, 2), [*rows[:1], *footer]),
            ({"header_drop": 3, "footer_drop": 1}, (10, 1), rows[:1]),
            ({"header_drop": 1, "footer_drop": 3}, (10, 4), [*header, *rows[:3]]),
            ({"header_drop": 2, "footer_drop": 2}, (10, 3), [*header, *rows[:2]]),
            ({"header_drop": 2, "footer_drop": 2}, (10, 2), rows[:2]),
            ({"header_drop": 3}, (10, 2), [*rows[:1], *footer]),
            ({"header_drop": 5, "footer_drop": 5}, (10, 12), [*header, *rows, *footer]),
            ({"header_drop": 5, "footer_drop": 5, "max_rows": 2}, (10,), [*header, *rows[:2], *footer]),
        ):
            with self.subTest(size=size, **kwargs):
                table = self.make(10, footer=["Tot", "45"], **kwargs)
                self.assertEqual(expected, render_text(table, size))

    def test_drop_thresholds_keep_short_body(self) -> None:
        """A body whose rows all fit keeps both parts, whatever the thresholds."""
        table = self.make(2, footer=["Tot", "1"], header_drop=5, footer_drop=5)
        self.assertEqual(["Name N", "r0   0", "r1   1", "Tot  1"], render_text(table, (6, 4)))

    def test_drop_threshold_validation(self) -> None:
        """A threshold is None or an int >= 1."""
        for name in ("header_drop", "footer_drop"):
            for value in (0, -1, True, 1.0, "1"):
                with self.subTest(name=name, value=value), self.assertRaises(urwid.TableError):
                    self.make(**{name: value})

    def test_empty(self) -> None:
        """An empty table shows its header, has no focus, and ignores keys and clicks."""
        table = urwid.Table(self.columns)
        self.assertIsNone(table.focus)
        with self.assertRaises(IndexError):
            _ = table.focus_position
        with self.assertRaises(IndexError):
            table.focus_position = 0
        self.assertEqual(["Name N"], render_text(table, (6,)))
        self.assertEqual(["Name N", "      "], render_text(table, (6, 2)))
        self.assertEqual([], render_text(urwid.Table(self.columns, header=False), (6,)))
        self.assertFalse(table.selectable())
        self.assertEqual(["down"], press(table, (6, 3), "down"))
        self.assertFalse(click(table, (6, 3), 0, 1))

    def test_rejected_row_leaves_body(self) -> None:
        """A change with an invalid row raises and leaves the rows as they were."""
        table = self.make()
        other = TableLayout(self.columns).row(["x", "y"])
        before = list(table.body)
        for change in (
            lambda: table.body.append(["a", "b", "c"]),
            lambda: table.body.append(other),
            lambda: table.body.append([urwid.SolidFill()]),
            lambda: table.body.append(table.body[0]),
            lambda: table.body.extend([["ok"], ["a", "b", "c"]]),
            lambda: table.body.__setitem__(slice(0, 1), [table.body[1]]),
            lambda: table.body.__imul__(2),
        ):
            with self.subTest(change=change), self.assertRaises(urwid.TableError):
                change()
            self.assertEqual(before, list(table.body))

    def test_plain_sequence_becomes_row(self) -> None:
        """A sequence appended to the body becomes a row of the table's layout."""
        table = self.make()
        table.body.append(["new", "9"])
        row = table.body[-1]
        self.assertIsInstance(row, urwid.TableRow)
        self.assertIs(table.layout, row.layout)
        self.assertEqual(3, row.index)

    def test_focus_signal(self) -> None:
        """Every focus move sends one signal with the old and the new position; an in-place replacement sends none."""
        table = self.make()
        events: list[tuple[int | None, int | None]] = []
        urwid.connect_signal(table, "focus changed", lambda _w, old, new: events.append((old, new)))
        self.assertEqual(0, table.focus_position)
        self.assertEqual([], press(table, (10, 4), "down"))
        self.assertEqual([(0, 1)], events)

        events.clear()
        table.focus_position = 2
        self.assertEqual([(1, 2)], events)

        events.clear()
        table.body[2] = ["replaced", "7"]
        self.assertEqual([], events)
        self.assertEqual(2, table.focus_position)
        self.assertEqual("replaced", typing.cast("urwid.Text", table.focus.cells[0]).text)

        events.clear()
        del table.body[:]
        self.assertEqual([(2, None)], events)
        self.assertIsNone(table.focus)

        events.clear()
        table.body.extend([["a"], ["b"]])
        self.assertEqual([(None, 1)], events)

    def test_focus_after_removal(self) -> None:
        """Removing the focused row focuses the next one; replacing every row focuses the last new one."""
        table = self.make(5)
        table.focus_position = 2
        del table.body[2]
        self.assertEqual(2, table.focus_position)
        table.body[:] = [["x"], ["y"]]
        self.assertEqual(1, table.focus_position)

    def test_activate(self) -> None:
        """Enter on a row that leaves it unhandled sends activate with the focus position."""
        table = self.make()
        activated: list[int] = []
        urwid.connect_signal(table, "activate", lambda _w, index: activated.append(index))
        table.focus_position = 1
        self.assertEqual([], press(table, (10, 4), "enter"))
        self.assertEqual([1], activated)
        self.assertEqual(["x"], press(table, (10, 4), "x"))

    def test_click(self) -> None:
        """A click focuses the row under it and reaches the cell, with or without a column attr; no activate."""
        clicked: list[str] = []
        activated: list[int] = []
        for attr in (None, "col"):
            with self.subTest(attr=attr):
                clicked.clear()
                button = urwid.Button("go", on_press=lambda _b: clicked.append("go"))
                table = urwid.Table([Column("A", attr=attr), Column("B")], [["a", "x"], [button, "y"]])
                urwid.connect_signal(table, "activate", lambda _w, index: activated.append(index))
                self.assertTrue(click(table, (12, 4), 0, 2))
                self.assertEqual(1, table.focus_position)
                click(table, (12, 4), 0, 2, event="mouse release")
                self.assertEqual(["go"], clicked)
                self.assertEqual([], activated)
                self.assertFalse(click(table, (12, 4), 0, 0))
                self.assertEqual(1, table.focus_position)

    def test_cell_widgets_keep_their_keys(self) -> None:
        """A check box cell takes space before the table could send activate, with or without a column attr."""
        activated: list[int] = []
        for attr in (None, "col"):
            with self.subTest(attr=attr):
                check = urwid.CheckBox("c")
                table = urwid.Table([Column("A", attr=attr)], [[check]])
                urwid.connect_signal(table, "activate", lambda _w, index: activated.append(index))
                self.assertEqual([], press(table, (10, 3), " "))
                self.assertTrue(check.state)
                self.assertEqual([], activated)

    def test_selectable_rows(self) -> None:
        """Rows of plain text are focusable; rows built not selectable are skipped."""
        table = urwid.Table([Column("A")])
        table.body.extend(
            [table.layout.row(["note"], selectable=False), ["a"], table.layout.row(["sep"], selectable=False), ["b"]]
        )
        table.focus_position = 1
        self.assertEqual([], press(table, (5, 6), "down"))
        self.assertEqual(3, table.focus_position)
        only_notes = urwid.Table([Column("A")], [table.layout.row(["x"], selectable=False)][:0])
        only_notes.body.append(only_notes.layout.row(["x"], selectable=False))
        self.assertEqual(["down"], press(only_notes, (5, 3), "down"))

    def test_max_rows(self) -> None:
        """A flow size shows at most max_rows rows of body, around the focus."""
        table = self.make(10, max_rows=3)
        self.assertEqual(4, table.rows((10,)))
        self.assertEqual(4, len(render_text(table, (10,))))
        table.focus_position = 9
        self.assertEqual(["Name N    ", "r7   7    ", "r8   8    ", "r9   9    "], render_text(table, (10,)))
        short = self.make(2, max_rows=3)
        self.assertEqual(3, short.rows((10,)))

    def test_set_focus_scrolls_as_listbox(self) -> None:
        """``set_focus`` scrolls as :meth:`ListBox.set_focus` does, with and without *coming_from*."""
        size = (3, 5)

        def make_table() -> urwid.Table:
            return urwid.Table([Column("A")], [[f"r{i:02}"] for i in range(22)], header=False)

        listbox = urwid.ListBox([urwid.SelectableIcon(f"r{i:02}", 0) for i in range(22)])
        listbox.render(size, focus=True)

        table = make_table()
        self.assertEqual(["r00", "r01", "r02", "r03", "r04"], render_text(table, size))
        table.set_focus(10, coming_from="above")
        self.assertEqual(["r06", "r07", "r08", "r09", "r10"], render_text(table, size))
        table.set_focus(2, coming_from="below")
        self.assertEqual(["r02", "r03", "r04", "r05", "r06"], render_text(table, size))

        undirected = make_table()
        render_text(undirected, size)
        for position in (10, 2):
            with self.subTest(position=position):
                undirected.focus_position = position
                listbox.set_focus(position)
                self.assertEqual(render_text(listbox, size), render_text(undirected, size))
                self.assertEqual(position, undirected.focus_position)

    def test_set_focus_visible_row_keeps_the_view(self) -> None:
        """A row on screen is focused without scrolling, with and without *coming_from*."""
        for coming_from in (None, "below"):
            with self.subTest(coming_from=coming_from):
                table = urwid.Table([Column("A")], [[f"r{i:02}"] for i in range(22)], header=False)
                table.set_focus(10, coming_from="above")
                render_text(table, (3, 5))
                table.set_focus(7, coming_from)
                self.assertEqual(["r06", "r07", "r08", "r09", "r10"], render_text(table, (3, 5)))
                self.assertEqual(7, table.focus_position)

    def test_set_focus_nested_focus(self) -> None:
        """*coming_from* moves the cursor into a row on screen; every other move keeps the row's focused cell."""
        cases = (
            ("on screen, undirected", 3, None, 1),
            ("on screen, from above", 3, "above", 0),
            ("off screen, undirected", 20, None, 1),
            ("off screen, from above", 20, "above", 1),
        )
        for label, target, coming_from, expected_cell in cases:
            with self.subTest(label):
                table = urwid.Table(
                    [Column("A"), Column("B")],
                    [[urwid.SelectableIcon(f"a{i}", 0), urwid.SelectableIcon(f"b{i}", 0)] for i in range(22)],
                    header=False,
                )
                table.body[target]._w.focus_position = 1
                table.render((10, 5), focus=True)
                table.set_focus(target, coming_from)
                table.render((10, 5), focus=True)
                self.assertEqual(target, table.focus_position)
                self.assertEqual(expected_cell, table.body[target]._w.focus_position)

    def test_set_focus_errors(self) -> None:
        """``set_focus`` rejects a position outside the rows and an unknown *coming_from*."""
        table = self.make()
        with self.assertRaises(IndexError):
            table.set_focus(3)
        with self.assertRaises(urwid.ListBoxError):
            table.set_focus(1, coming_from="left")  # type: ignore[arg-type]

    def test_unfocused_focus_attr_composition(self) -> None:
        """The E12 map is applied over the row's own map, so its keys are the row's mapped attributes."""
        table = urwid.Table(
            [Column("A"), Column("B")],
            [[("cell", "a"), "b"], ["c", "d"]],
            attr={None: "row", "cell": "row cell"},
            unfocused_focus_attr={"row": "row marked", "row cell": "cell marked"},
            header=False,
        )
        self.assertEqual(
            [[(urwid.LayeredAttr("cell marked", "row marked"), "a"), ("row marked", " b")], [("row", "c d")]],
            render_runs(table, (3, 2)),
        )
        table.unfocused_focus_attr = "marked"
        self.assertEqual({None: "marked"}, table.unfocused_focus_attr)

        seen: list[urwid.TableRow] = []

        def by_row(row: urwid.TableRow) -> dict[Hashable, Hashable] | None:
            seen.append(row)
            return None if row.attr is None else {"row": "row by row", "row cell": "cell by row"}

        table.unfocused_focus_attr_func = by_row
        self.assertIs(by_row, table.unfocused_focus_attr_func)
        # a row without its own attr gets None, so the fixed map applies
        self.assertEqual(
            [[(urwid.LayeredAttr("row cell", "row", "marked"), "a"), (urwid.LayeredAttr("row", "marked"), " b")]],
            render_runs(table, (3, 2))[:1],
        )
        self.assertEqual([table.body[0]], seen)
        seen.clear()
        table.body[0] = table.layout.row([("cell", "a"), "b"], attr={None: "row", "cell": "row cell"})
        self.assertEqual(
            [[(urwid.LayeredAttr("cell by row", "row by row"), "a"), ("row by row", " b")], [("row", "c d")]],
            render_runs(table, (3, 2)),
        )
        self.assertEqual([table.body[0]], seen)

    def test_header_never_focused(self) -> None:
        """Up from the first row leaves the key unhandled, and a click on the header changes nothing."""
        table = self.make()
        self.assertEqual(["up"], press(table, (10, 4), "up"))
        self.assertFalse(click(table, (10, 4), 0, 0))
        self.assertEqual(0, table.focus_position)

    def test_footer_never_focused(self) -> None:
        """Down from the last row leaves the key unhandled, and a click on the footer changes nothing."""
        for size in ((10, 5), (10,)):
            with self.subTest(size=size):
                table = self.make(footer=["t"])
                table.focus_position = 2
                self.assertEqual(["down"], press(table, size, "down"))
                self.assertFalse(click(table, size, 0, 4))
                self.assertEqual(2, table.focus_position)
                click(table, size, 0, 2)
                self.assertEqual(1, table.focus_position)

    def test_overlay_pack(self) -> None:
        """An Overlay sizes itself to the table's natural width and rows."""
        table = self.make()
        overlay = urwid.Overlay(table, urwid.SolidFill("."), urwid.CENTER, PACK, urwid.MIDDLE, PACK)
        self.assertEqual(
            ["..........", "..Name N..", "..r0   0..", "..r1   1..", "..r2   2..", ".........."],
            render_text(overlay, (10, 6)),
        )

    def test_row_attr(self) -> None:
        """row_attr runs per render with the row's index, and again for the rows from a change on."""
        calls: list[int] = []

        def stripes(index: int, data: typing.Any) -> Hashable:
            calls.append(index)
            if data == "error":
                return None
            return "even" if index % 2 == 0 else "odd"

        table = urwid.Table([Column("A")], [["a"], ["b"], ["c"]], header=False, row_attr=stripes)
        table.body[1].attr = "error attr"
        table.body[1].data = "error"
        table.focus_position = 0
        table.body[0].focus_attr = "focus"

        # the last canvas is kept, as a screen showing it does, so that rows which did not change reuse theirs
        shown: list[urwid.Canvas] = []

        def attrs() -> list[Hashable]:
            shown[:] = [table.render((1, len(table.body)), focus=True)]
            return [runs[0][0] for runs in render_runs(table, (1, len(table.body)), focus=True)]

        self.assertEqual(["focus", "error attr", "even"], attrs())
        for change, expected, first in (
            (lambda: table.body.insert(0, ["new"]), ["even", "focus", "error attr", "odd"], 0),
            (lambda: table.body.append(["end"]), ["even", "focus", "error attr", "odd", "even"], 4),
            (lambda: table.body.__delitem__(2), ["even", "focus", "even", "odd"], 2),
            (lambda: table.body.__setitem__(3, ["x"]), ["even", "focus", "even", "odd"], 3),
        ):
            with self.subTest(change=change):
                attrs()
                calls.clear()
                change()
                self.assertEqual(expected, attrs())
                self.assertTrue(calls)
                self.assertGreaterEqual(min(calls), first)
                self.assertEqual(list(range(len(table.body))), [row.index for row in table.body])

        calls.clear()
        table.row_attr = lambda index, data: "all"
        self.assertEqual(["all", "focus", "all", "all"], attrs())

    def test_accessors(self) -> None:
        """Replacing the whole body replaces the rows, and the settings read back as given."""
        stripes = typing.cast("typing.Any", lambda index, data: None)
        table = self.make(max_rows=2, row_attr=stripes)
        self.assertEqual(2, table.max_rows)
        self.assertIs(stripes, table.row_attr)
        table.body[:] = [["x", "1"], ["y", "2"]]
        self.assertEqual(["x", "y"], [typing.cast("urwid.Text", row.cells[0]).text for row in table.body])
        self.assertEqual((10, 3), table.pack((10,)))
        self.assertEqual((10, 2), table.pack((10, 2)))
        for max_rows in (-1, 1.5, True):
            with self.subTest(max_rows=max_rows), self.assertRaises(urwid.TableError):
                self.make(max_rows=max_rows)

    def test_set_selectable(self) -> None:
        """A row made not selectable is skipped by the focus moves."""
        table = self.make()
        table.body[1].set_selectable(False)
        self.assertFalse(table.body[1].selectable())
        self.assertEqual([], press(table, (10, 4), "down"))
        self.assertEqual(2, table.focus_position)

    def test_row_assigned_again(self) -> None:
        """Assigning a row to its own place keeps it registered and reruns row_attr for it."""
        table = urwid.Table([Column("A")], [["a"], ["b"]], header=False, row_attr=lambda index, data: data)
        row = table.body[1]
        self.assertEqual([None, None], [runs[0][0] for runs in render_runs(table, (1, 2))])
        row.data = "changed"
        table.body[1] = table.body[1]
        self.assertIs(row, table.body[1])
        self.assertEqual(1, row.index)
        self.assertEqual([None, "changed"], [runs[0][0] for runs in render_runs(table, (1, 2))])
        typing.cast("urwid.Text", row.cells[0]).set_text("wider")
        self.assertEqual((5,), table.layout.widths(9))

    def test_removed_row_has_no_index(self) -> None:
        """A removed row has no index, and the others are numbered again after a removal or a reordering."""
        table = self.make()
        row = table.body.pop(0)
        self.assertIsNone(row.index)
        self.assertEqual([0, 1], [r.index for r in table.body])
        table.body.reverse()
        self.assertEqual([0, 1], [r.index for r in table.body])
        table.body.append(row)
        self.assertEqual(2, row.index)

    def test_removed_row_widths(self) -> None:
        """A removed row stops counting; a removed row that held a column's maximum narrows it."""
        table = self.make()
        table.body.append(["much longer", "1"])
        self.assertEqual((11, 1), table.layout.widths(20))
        cells = [CountingText(str(i)) for i in range(3)]
        for row, cell in zip(list(table.body)[:3], cells, strict=True):
            table.body[row.index] = [cell, "x"]
        packs = [cell.packs for cell in cells]
        del table.body[0]
        self.assertEqual(packs, [cell.packs for cell in cells])
        del table.body[-1]
        self.assertEqual((4, 1), table.layout.widths(20))

    def test_hidden_focused_cell(self) -> None:
        """A cell hidden by a resize keeps the focus and gets it back visible after the resize back."""
        table = urwid.Table(
            [Column("A", width=4), Column("B", min_width=4)],
            [[SelectableText("a"), urwid.Edit("", "bbbb", edit_pos=0)]],
            header=False,
        )
        row = table.body[0]
        row._w.focus_position = 1
        self.assertEqual((5, 0), table.get_cursor_coords((9, 1)))
        self.assertEqual(["a   "], render_text(table, (4, 1), focus=True))
        self.assertIsNone(table.get_cursor_coords((4, 1)))
        self.assertEqual(1, row._w.focus_position)
        self.assertEqual((5, 0), table.get_cursor_coords((9, 1)))
        self.assertEqual(1, row._w.focus_position)

    def test_budget(self) -> None:
        """BOX render and keys walk the visible rows only, and an append measures the new row only."""
        cells = [CountingText(str(i)) for i in range(2000)]
        table = urwid.Table([Column("N")], [[cell] for cell in cells])
        self.assertEqual({1}, {cell.packs for cell in cells})
        table.focus_position = 0
        for _ in range(100):
            urwid.CanvasCache.clear()
            table.render((10, 5), focus=True)
            table.keypress((10, 5), "down")
            table.keypress((10, 5), "up")
        self.assertEqual({1}, {cell.packs for cell in cells})
        new = CountingText("5")
        table.body.append([new])
        self.assertEqual(1, new.packs)
        self.assertEqual({1}, {cell.packs for cell in cells})

        urwid.CanvasCache.clear()
        with mock.patch.object(table_module._TableColumns, "rows", autospec=True, return_value=1) as rows:
            table.render((10, 5), focus=True)
        self.assertLess(rows.call_count, 50)

    def test_bulk_removal_recomputes_once(self) -> None:
        """Replacing or deleting many rows of equal widths scans the rows once per change, not once per row."""
        table = urwid.Table([Column(), Column()], [["aaaa", "bb"] for _ in range(200)])
        with mock.patch.object(
            TableLayout,
            "_iter_rows",
            autospec=True,
            side_effect=TableLayout._iter_rows,
        ) as iter_rows:
            table.body[:] = [["aaaa", "bb"] for _ in range(200)]
            del table.body[:100]
        self.assertLessEqual(iter_rows.call_count, 2)
        self.assertEqual((4, 2), table.layout.widths(20))


class TableSelectNavigationTest(unittest.TestCase):
    """Tests of Tab and Shift+Tab across the cells and rows."""

    def make(self) -> urwid.Table:
        """Return a table of two rows of Edit cells with select navigation."""
        return urwid.Table(
            [Column("A"), Column("B"), Column("C")],
            [
                [urwid.Edit("", "a0"), urwid.Edit("", "b0"), "c0"],
                [urwid.Edit("", "a1"), urwid.Edit("", "b1", allow_tab=False), urwid.Edit("", "c1")],
            ],
            select_navigation=True,
        )

    def test_tab_across_cells_then_rows(self) -> None:
        """Tab moves across the cells, then to the next row, and returns the key past the last cell."""
        table = self.make()
        events: list[tuple[int | None, int | None]] = []
        urwid.connect_signal(table, "focus changed", lambda _w, old, new: events.append((old, new)))
        size = (20, 4)
        positions = []
        for _ in range(4):
            self.assertEqual([], press(table, size, "tab"))
            positions.append((table.focus_position, table.focus._w.focus_position))
        self.assertEqual([(0, 1), (1, 0), (1, 1), (1, 2)], positions)
        self.assertEqual([(0, 1)], events)
        # past the last cell of the last row: the key is returned and the focus wraps to the first cell
        self.assertEqual(["tab"], press(table, size, "tab"))
        self.assertEqual((0, 0), (table.focus_position, table.focus._w.focus_position))
        table.focus_position = 1
        table.focus._w.focus_position = 0
        self.assertEqual([], press(table, size, "shift tab"))
        self.assertEqual((0, 1), (table.focus_position, table.focus._w.focus_position))

    def test_edit_with_allow_tab_keeps_tab(self) -> None:
        """An Edit that takes Tab keeps it."""
        table = urwid.Table([Column("A")], [[urwid.Edit("", "x", allow_tab=True)], ["b"]], select_navigation=True)
        self.assertEqual([], press(table, (10, 4), "tab"))
        self.assertEqual(0, table.focus_position)

    def test_without_select_navigation(self) -> None:
        """Without select navigation Tab is left unhandled."""
        table = urwid.Table([Column("A"), Column("B")], [[urwid.Edit("", "a"), urwid.Edit("", "b")]])
        self.assertEqual(["tab"], press(table, (10, 3), "tab"))
        self.assertEqual(0, table.focus._w.focus_position)

    def test_cell_focus_map_under_column_attr(self) -> None:
        """A cell's own focus map highlights only the focused cell when its column has an attr."""
        table = urwid.Table(
            [Column("A", attr="col"), Column("B", attr="col")],
            [[urwid.AttrMap(SelectableText("x"), "c", "cf"), urwid.AttrMap(SelectableText("y"), "c", "cf")]],
            header=False,
            select_navigation=True,
        )
        cf, c = urwid.LayeredAttr("cf", "col"), urwid.LayeredAttr("c", "col")
        self.assertEqual([[(cf, "x"), (None, " "), (c, "y")]], render_runs(table, (3, 1), focus=True))
        self.assertEqual([], press(table, (3, 1), "tab"))
        self.assertEqual([[(c, "x"), (None, " "), (cf, "y")]], render_runs(table, (3, 1), focus=True))

    def test_hidden_cells_skipped(self) -> None:
        """Tab skips a cell of a hidden column."""
        table = urwid.Table(
            [Column("A"), Column("B", width=0), Column("C")],
            [[urwid.Edit("", "a"), urwid.Edit("", "b"), urwid.Edit("", "c")]],
            select_navigation=True,
        )
        table.render((10, 3), focus=True)
        self.assertEqual([], press(table, (10, 3), "tab"))
        self.assertEqual(2, table.focus._w.focus_position)


class TableOptionsTest(unittest.TestCase):
    """Tests of the scrollbar and the rows spanning every column."""

    def test_scrollbar_natural_width(self) -> None:
        """The scrollbar column counts in the natural width, and the header is padded over it."""
        table = urwid.Table([Column("A"), Column("B")], [["a", "b"]] * 5, scrollbar=True)
        self.assertEqual(4, table.pack(())[0])
        lines = render_text(table, (6, 3))
        self.assertEqual("A B   ", lines[0])
        self.assertTrue(all(len(line) == 6 for line in lines))

    def test_scrollbar_only_when_needed(self) -> None:
        """With scrollbar=None the bar is drawn only once the rows do not fit."""
        table = urwid.Table([Column("A"), Column("B")], [["a", "b"]] * 2, scrollbar=None)
        self.assertEqual(["A B ", "a b ", "a b "], render_text(table, (4, 3)))
        table.body.extend([["c", "d"]] * 3)
        lines = render_text(table, (4, 3))
        self.assertIn("\u2588", "".join(line[-1] for line in lines[1:]))
        self.assertEqual("A B ", lines[0])

    def test_scrollbar_options(self) -> None:
        """The scrollbar options reach the scrollbar: its characters, width, end markers and attributes."""
        table = urwid.Table(
            [Column("A")],
            [["a"]] * 10,
            scrollbar=True,
            scrollbar_thumb_char="#",
            scrollbar_trough_char=".",
            scrollbar_width=2,
            scrollbar_end_markers=("^", "v"),
            scrollbar_attr="trough",
            scrollbar_thumb_attr="thumb",
        )
        self.assertEqual(3, table.pack(())[0])
        runs = render_runs(table, (4, 6))
        self.assertEqual([(None, "A   ")], runs[0])
        self.assertEqual([(None, "a "), ("trough", "^^")], runs[1])
        self.assertEqual([(None, "a "), ("thumb", "##")], runs[2])
        self.assertEqual([(None, "a "), ("trough", "vv")], runs[5])

    def test_scrollbar_options_left(self) -> None:
        """With the scrollbar on the left the header and the footer are padded on the left, over the scrollbar."""
        table = urwid.Table(
            [Column("A"), Column("B")],
            [["a", "b"]] * 5,
            scrollbar=True,
            scrollbar_side="left",
            scrollbar_thumb_char="#",
            scrollbar_trough_char=".",
        )
        self.assertEqual([" A B", "#a b", "#a b", ".a b"], render_text(table, (4, 4)))
        table.footer = ["t", "5"]
        self.assertEqual([" A B", "#a b", ".a b", " t 5"], render_text(table, (4, 4)))

    def test_scrollbar_options_ignored_without_scrollbar(self) -> None:
        """With scrollbar=False the options are not used and no column is kept for a scrollbar."""
        table = urwid.Table([Column("A")], [["a"]] * 5, scrollbar_width=3)
        self.assertEqual(1, table.pack(())[0])

    def test_scrollbar_options_invalid(self) -> None:
        """A keyword that is no option, an option the scrollbar rejects, or ``visible`` raises at construction."""
        options: dict[str, typing.Any]
        for scrollbar, options, error in (
            (True, {"thumb_char": "#"}, TypeError),
            (True, {"scrollbar_visible": None}, TypeError),
            (True, {"scrollbar_delegate_selectable": True}, TypeError),
            (False, {"scrollbar_unknown": 1}, TypeError),
            (True, {"scrollbar_end_markers": ("^",)}, ValueError),
        ):
            with self.subTest(scrollbar=scrollbar, options=options), self.assertRaises(error):
                urwid.Table([Column("A")], scrollbar=scrollbar, **options)

    def test_scrollbar_mouse_offsets(self) -> None:
        """A click on the last column beside the scrollbar reaches the row under it, on either side of it."""
        sides: tuple[tuple[typing.Literal["left", "right"], int], ...] = (("right", 6), ("left", 7))
        clicked: list[str] = []

        def on_press(button: urwid.Button) -> None:
            clicked.append(button.label)

        for side, col in sides:
            with self.subTest(side=side):
                clicked.clear()
                table = urwid.Table(
                    [Column("A", width=(urwid.WEIGHT, 1))],
                    [[urwid.Button(str(i), on_press=on_press)] for i in range(10)],
                    scrollbar=True,
                    scrollbar_side=side,
                )
                size = (8, 4)
                table.focus_position = 0
                # the scrollbar finds where its columns are from the last render, as on a screen
                table.render(size, focus=True)
                click(table, size, col, 2)
                click(table, size, col, 2, event="mouse release")
                self.assertEqual(1, table.focus_position)
                self.assertEqual(["1"], clicked)

    def test_span_row(self) -> None:
        """A span row takes the whole width at any size, is not measured, and takes no column attr."""
        table = urwid.Table([Column("A", attr="col"), Column("B")], [["a", "b"]])
        table.body.append(table.layout.row(["a row spanning both columns"], span=True))
        for maxcol in (3, 10, 40):
            with self.subTest(maxcol=maxcol):
                lines = render_text(table, (maxcol,))
                self.assertTrue(all(len(line) == maxcol for line in lines))
        self.assertEqual(["A B", "a b", "a r"], render_text(table, (3,)))
        self.assertEqual([("col", "a"), (None, " b")], render_runs(table, (3,))[1])
        self.assertEqual([(None, "a r")], render_runs(table, (3,))[2])
        self.assertEqual(3, table.pack(())[0])
        with self.assertRaises(urwid.TableError):
            table.layout.row(["a", "b"], span=True)

    def test_span_row_under_row_attr(self) -> None:
        """row_attr colours a span row like any other."""
        table = urwid.Table([Column("A")], [["a"]], header=False, row_attr=lambda index, data: f"r{index}")
        table.body.append(table.layout.row(["span"], span=True))
        self.assertEqual(["r0", "r1"], [runs[0][0] for runs in render_runs(table, (4, 2))])


if __name__ == "__main__":
    unittest.main()
