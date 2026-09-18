from __future__ import annotations

import unittest

import urwid
from urwid.util import get_encoding
from urwid.widget import bar_graph


class SegmentAttributesTest(unittest.TestCase):
    def test_requires_at_least_two_entries(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            urwid.BarGraph(["only-bg"])

    def test_plain_attributes_default_to_space_char(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        self.assertEqual(g.attr, ["bg", "fg"])
        self.assertEqual(g.char, [" ", " "])

    def test_tuple_attributes_use_given_char(self) -> None:
        g = urwid.BarGraph(["bg", ("fg", "#")])
        self.assertEqual(g.attr, ["bg", "fg"])
        self.assertEqual(g.char, [" ", "#"])

    def test_hatt_defaults_to_background_attribute(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        self.assertEqual(g.hatt, ["bg"])

    def test_hatt_accepts_a_list(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        self.assertEqual(g.hatt, ["hbg", "hfg"])

    def test_hatt_accepts_a_single_value(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt="honly")  # type: ignore[arg-type]
        self.assertEqual(g.hatt, ["honly"])

    def test_satt_invalid_key_shape_raises(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            urwid.BarGraph(["bg", "fg", "fg2"], satt={(1, 2, 3): "attr"})  # type: ignore[dict-item]

    def test_satt_fg_not_int_raises(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            urwid.BarGraph(["bg", "fg"], satt={("x", 0): "attr"})  # type: ignore[dict-item]

    def test_satt_bg_not_int_raises(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            urwid.BarGraph(["bg", "fg"], satt={(1, "x"): "attr"})  # type: ignore[dict-item]

    def test_satt_fg_not_greater_than_bg_raises(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            urwid.BarGraph(["bg", "fg"], satt={(0, 1): "attr"})

    def test_satt_valid(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], satt={(1, 0): "attr"})
        self.assertEqual(g.satt, {(1, 0): "attr"})


class SetDataTest(unittest.TestCase):
    def test_hlines_are_sorted_descending(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        g.set_data([[1]], 10, [2, 8, 5])
        _bardata, _top, hlines = g.data
        self.assertEqual(hlines, [8, 5, 2])

    def test_hlines_none_kept_as_none(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        g.set_data([[1]], 10)
        _bardata, _top, hlines = g.data
        self.assertIsNone(hlines)


class BarWidthTest(unittest.TestCase):
    def test_set_bar_width_rejects_non_positive(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        with self.assertRaises(ValueError):
            g.set_bar_width(0)

    def test_set_bar_width_accepts_positive(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        g.set_bar_width(3)
        self.assertEqual(g.bar_width, 3)

    def test_calculate_bar_widths_fixed_width(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        g.set_bar_width(3)
        self.assertEqual(g.calculate_bar_widths((10, 5), [[1], [2], [3]]), [3, 3, 3])

    def test_calculate_bar_widths_more_bars_than_columns(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        self.assertEqual(g.calculate_bar_widths((2, 5), [[1], [2], [3]]), [1, 1])

    def test_get_data_truncates_bars_that_do_not_fit(self) -> None:
        g = urwid.BarGraph(["bg", "fg"])
        g.set_bar_width(5)
        g.set_data([[1], [2], [3]], 5)
        # Only floor(10 / 5) == 2 bars fit into 10 columns.
        bardata, _top, _hlines = g._get_data((10, 3))
        self.assertEqual(bardata, [[1], [2]])


class SelectableTest(unittest.TestCase):
    def test_bar_graph_not_selectable(self) -> None:
        self.assertFalse(urwid.BarGraph(["bg", "fg"]).selectable())

    def test_graph_vscale_not_selectable(self) -> None:
        self.assertFalse(urwid.GraphVScale([(1, "1")], 2).selectable())


class HLinesDisplayTest(unittest.TestCase):
    def test_inserts_hline_row_at_correct_position(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        disp = [(5, [(1, 3)])]
        # top=5, hline=2, maxrow=5 -> row index 2 (of 5), non-smoothed underscore (chnum 0).
        result = g.hlines_display(disp, top=5, hlines=[2], maxrow=5)
        self.assertEqual(
            result,
            [(2, [(1, 3)]), (1, [((1, 0), 3)]), (2, [(1, 3)])],
        )

    def test_out_of_range_hline_is_dropped(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        disp = [(5, [(1, 3)])]
        # hline above top: rh comes out negative and is filtered.
        result = g.hlines_display(disp, top=5, hlines=[6], maxrow=5)
        self.assertEqual(result, disp)

    def test_hline_on_segment_without_hatt_entry_is_left_unstyled(self) -> None:
        # hatt has only one entry (index 0), so bar_type 1 has no matching hatt: fill_row leaves it as-is.
        g = urwid.BarGraph(["bg", "fg"])
        disp = [(5, [(1, 3)])]
        result = g.hlines_display(disp, top=5, hlines=[2], maxrow=5)
        self.assertEqual(result, [(2, [(1, 3)]), (1, [(1, 3)]), (2, [(1, 3)])])

    def test_smoothed_hline_uses_fractional_character(self) -> None:
        old_encoding = get_encoding()
        urwid.set_encoding("utf-8")
        try:
            g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"], satt={(1, 0): "smooth"})
            disp = [(5, [(1, 3)])]
            # top=10, hline=6.9, maxrow=5: rh = (10-6.9)*5/10 - 0.0 = 1.55 -> row 1, f=0.55 -> chnum 3.
            result = g.hlines_display(disp, top=10, hlines=[6.9], maxrow=5)
            self.assertEqual(
                result,
                [(1, [(1, 3)]), (1, [((1, 3), 3)]), (3, [(1, 3)])],
            )
        finally:
            urwid.set_encoding(old_encoding)

    def test_calculate_display_applies_hlines(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        g.set_data([[3]], 5, [2])
        result = g.calculate_display((1, 5))
        self.assertTrue(any(isinstance(bar_type, tuple) for _y, row in result for bar_type, _w in row))

    def test_two_hlines_landing_on_the_same_row_are_deduplicated(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        disp = [(5, [(1, 3)])]
        result = g.hlines_display(disp, top=10, hlines=[5, 5.05], maxrow=10)
        self.assertEqual(result, [(4, [(1, 3)]), (1, [((1, 0), 3)])])

    def test_hline_on_the_last_row_of_a_block_needs_no_trailing_row(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], hatt=["hbg", "hfg"])
        disp = [(5, [(1, 3)])]
        result = g.hlines_display(disp, top=5, hlines=[0.5], maxrow=5)
        self.assertEqual(result, [(4, [(1, 3)]), (1, [((1, 0), 3)])])


class CalculateBargraphDisplayTest(unittest.TestCase):
    def test_mismatched_lengths_raise(self) -> None:
        with self.assertRaises(bar_graph.BarGraphError):
            bar_graph.calculate_bargraph_display([[1], [2]], 5, [1], 5)

    def test_zero_maxrow_returns_no_rows(self) -> None:
        self.assertEqual(bar_graph.calculate_bargraph_display([[1]], 5, [1], 0), [])

    def test_zero_width_bar_does_not_desync_following_bars(self) -> None:
        # Regression test: a zero-width bar must not shift which bar_widths entry later,
        # non-zero-width bars read.
        result = bar_graph.calculate_bargraph_display([[1], [2], [3]], 5, [0, 1, 1], 5)
        self.assertEqual(
            result,
            [(2, [(0, 2)]), (1, [(0, 1), (1, 1)]), (2, [(1, 2)])],
        )

    def test_row_realignment_across_several_bars(self) -> None:
        # A row whose segment boundaries do not line up with the previous row's run
        # boundaries: the rowsets builder has to skip over several old runs to catch up.
        result = bar_graph.calculate_bargraph_display(
            [[7, 1, 2], [7, 8, 8], [8, 8, 0], [4, 2, 3]],
            6,
            [3, 2, 0, 3],
            3,
        )
        self.assertEqual(
            result,
            [(1, [(1, 3), (3, 2), (0, 3)]), (1, [(1, 3), (3, 5)]), (1, [(3, 8)])],
        )

    def test_row_realignment_reaching_the_last_run(self) -> None:
        # Same as above, but the skip lands exactly on the final run of "last".
        result = bar_graph.calculate_bargraph_display(
            [[3, 7, 1], [6, 4, 8], [7, 0, 5], [6, 4, 0]],
            3,
            [1, 2, 1, 2],
            4,
        )
        self.assertEqual(
            result,
            [(3, [(2, 1), (3, 3), (2, 2)]), (1, [(3, 4), (2, 2)])],
        )


class SmoothDisplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_row_shorter_than_merge_target_raises(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], satt={(1, 0): "smooth"})
        with self.assertRaises(bar_graph.BarGraphError):
            # 2 columns merged into a row describing only 1: the merge cannot consume it all.
            g.smooth_display([(4, [(0, 2)]), (4, [(0, 1)])])

    def test_large_block_is_grouped_without_remainder(self) -> None:
        g = urwid.BarGraph(["bg", "fg"], satt={(1, 0): "smooth"})
        # 16 disp-rows (2 actual rows) with no partial remainder exercises the "copy whole blocks" path.
        result = g.smooth_display([(16, [(0, 2)])])
        self.assertEqual(result, [(2, [(0, 2)])])

    def test_merging_two_already_smoothed_segments(self) -> None:
        # Three adjacent bars whose eighth-row boundaries fall close enough together that the
        # merge combines two segments that are themselves already a smoothed (fg, bg, k) tuple.
        g = urwid.BarGraph(["a", "b", "c"], satt={(1, 0): "x", (2, 1): "y"})
        g.set_data([[3], [6], [4]], 10)
        result = g.calculate_display((6, 1))
        self.assertEqual(
            result,
            [(1, [((1, 0, 2), 2), ((1, 0, 5), 2), ((1, 0, 3), 2)])],
        )

    def test_merge_falls_back_to_plain_attribute_when_pair_has_no_satt_entry(self) -> None:
        # The transition landed on by this bar's boundary has no (fg, bg) entry in satt, so the
        # merge falls back to whichever plain attribute dominates instead of a smoothed character.
        g = urwid.BarGraph(["a", "b", "c"], satt={(2, 0): "z"})
        g.set_data([[8, 2, 5]], 10)
        result = g.calculate_display((2, 1))
        self.assertEqual(result, [(1, [(1, 2)])])

    def test_merge_combines_consecutive_runs_of_the_same_type(self) -> None:
        g = urwid.BarGraph(["a", "b", "c"], satt={(2, 0): "z"})
        g.set_data([[9, 4], [5, 4], [3, 5]], 7)
        result = g.calculate_display((5, 1))
        self.assertEqual(result, [(1, [(2, 4), ((2, 0, 6), 1)])])


class RenderTest(unittest.TestCase):
    def test_render_plain_bars(self) -> None:
        g = urwid.BarGraph(["bg", ("fg", "#")])
        g.set_data([[3]], 5)
        canv = g.render((1, 5))
        self.assertEqual(list(canv.text), [b" ", b" ", b"#", b"#", b"#"])

    def test_render_raises_on_multirow_character(self) -> None:
        g = urwid.BarGraph(["bg", ("fg", "\n")])
        g.set_data([[1]], 1)
        with self.assertRaises(bar_graph.BarGraphError):
            g.render((1, 1))

    def test_render_horizontal_line_segment(self) -> None:
        g = urwid.BarGraph(["bg", ("fg", "#")], hatt=["hbg", "hfg"])
        g.set_data([[3]], 5, [2])
        canv = g.render((1, 5))
        # Row 2 (0-indexed) carries the hline character instead of the plain fill.
        self.assertEqual(canv.text[2], g.hlines[0].encode())

    def test_render_smoothed_vertical_eighth(self) -> None:
        old_encoding = get_encoding()
        urwid.set_encoding("utf-8")
        try:
            g = urwid.BarGraph(["black", "red"], satt={(1, 0): "red/black"})
            # A value that does not land on an eighth-row boundary forces a smoothed character.
            g.set_data([[1]], 3)
            canv = g.render((1, 5))
            rendered = b"".join(canv.text).decode()
            self.assertTrue(any(ch in g.eighths for ch in rendered))
        finally:
            urwid.set_encoding(old_encoding)


class GraphVScaleTest(unittest.TestCase):
    def test_set_scale_sorts_labels_descending(self) -> None:
        scale = urwid.GraphVScale([(1, "one"), (5, "five"), (3, "three")], 10)
        self.assertEqual(scale.pos, [5, 3, 1])

    def test_render_empty_scale_returns_solid_canvas(self) -> None:
        scale = urwid.GraphVScale([], 10)
        canv = scale.render((5, 3))
        self.assertIsInstance(canv, urwid.SolidCanvas)

    def test_render_places_labels_by_position(self) -> None:
        scale = urwid.GraphVScale([(8, "top"), (2, "bot")], 10)
        canv = scale.render((5, 10))
        text = b"\n".join(canv.text).decode()
        self.assertIn("top", text)
        self.assertIn("bot", text)

    def test_render_skips_overlapping_labels(self) -> None:
        # Two labels landing on the same row: sorted descending puts "zzz" first (p < rows branch
        # then skips "aaa").
        scale = urwid.GraphVScale([(5, "aaa"), (5, "zzz")], 10)
        canv = scale.render((5, 10))
        text = b"\n".join(canv.text).decode()
        self.assertIn("zzz", text)
        self.assertNotIn("aaa", text)

    def test_render_stops_at_labels_beyond_maxrow(self) -> None:
        # A position far below the scale's own range (outside the documented 0 < position < top)
        # maps to a row past maxrow, so rendering stops before placing it.
        scale = urwid.GraphVScale([(1, "b"), (-5, "a")], 10)
        canv = scale.render((5, 3))
        text = b"\n".join(canv.text).decode()
        self.assertNotIn("a", text)
        self.assertIn("b", text)

    def test_render_exact_fit_needs_no_trailing_padding(self) -> None:
        scale = urwid.GraphVScale([(1, "x")], 10)
        canv = scale.render((5, 1))
        self.assertEqual(list(canv.text), [b"x    "])


if __name__ == "__main__":
    unittest.main()
