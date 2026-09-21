from __future__ import annotations

import sys
import unittest
import weakref

import urwid
from urwid import canvas
from urwid.util import get_encoding


class CanvasCacheTest(unittest.TestCase):
    def setUp(self):
        # purge the cache
        urwid.CanvasCache._widgets.clear()

    def cct(self, widget, size, focus, expected):
        with self.subTest(widget=widget, size=size, focus=focus, expected=expected):
            got = urwid.CanvasCache.fetch(widget, urwid.Widget, size, focus)
            self.assertEqual(expected, got, f"got: {got} expected: {expected}")

    def test1(self):
        a = urwid.Text("")
        b = urwid.Text("")
        blah = urwid.TextCanvas()
        blah.finalize(a, (10, 1), False)
        blah2 = urwid.TextCanvas()
        blah2.finalize(a, (15, 1), False)
        bloo = urwid.TextCanvas()
        bloo.finalize(b, (20, 2), True)

        urwid.CanvasCache.store(urwid.Widget, blah)
        urwid.CanvasCache.store(urwid.Widget, blah2)
        urwid.CanvasCache.store(urwid.Widget, bloo)

        self.cct(a, (10, 1), False, blah)
        self.cct(a, (15, 1), False, blah2)
        self.cct(a, (15, 1), True, None)
        self.cct(a, (10, 2), False, None)
        self.cct(b, (20, 2), True, bloo)
        self.cct(b, (21, 2), True, None)
        urwid.CanvasCache.invalidate(a)
        self.cct(a, (10, 1), False, None)
        self.cct(a, (15, 1), False, None)
        self.cct(b, (20, 2), True, bloo)

    def test_deps_does_not_grow_unbounded_on_repeated_store(self):
        # A widget that is re-rendered many times (e.g. one screen refresh
        # per store() call) used to add itself to CanvasCache._deps[w] every
        # single time, so the list kept growing for as long as the program
        # ran, even though it only ever depends on `w` once.
        dependency = urwid.Text("")
        dependent = urwid.Text("")

        dependency_canv = urwid.TextCanvas()
        dependency_canv.finalize(dependency, (10, 1), False)
        urwid.CanvasCache.store(urwid.Widget, dependency_canv)

        for _ in range(50):
            canv = urwid.TextCanvas()
            canv.finalize(dependent, (10, 1), False)
            canv.depends_on = [dependency]
            urwid.CanvasCache.store(urwid.Widget, canv)

        self.assertEqual({dependent}, urwid.CanvasCache._deps[dependency])

    def test_store_without_widget_info_raises(self):
        """A canvas has to be finalized (carry widget_info) before it can be cached."""
        unfinalized = urwid.TextCanvas()
        with self.assertRaises(TypeError):
            urwid.CanvasCache.store(urwid.Widget, unfinalized)

    @unittest.skipIf(
        sys.implementation.name in {"pypy", "graalpy"},
        "WeakRef works differently on PyPy/GraalPy's tracing GC",
    )
    def test_fetch_of_a_dead_weakref_returns_none_without_counting_a_hit(self):
        """A cache entry whose canvas is already gone is a miss, not a hit."""
        widget = urwid.Text("")
        key = (urwid.Widget, (10, 1), False)
        # A weakref with no callback: unlike store()'s, it will not clean up
        # after itself, so the dead entry stays in place for fetch() to find.
        placeholder = urwid.TextCanvas()
        urwid.CanvasCache._widgets[widget] = {key: weakref.ref(placeholder)}
        del placeholder

        hits_before = urwid.CanvasCache.hits
        fetches_before = urwid.CanvasCache.fetches
        result = urwid.CanvasCache.fetch(widget, urwid.Widget, (10, 1), False)

        self.assertIsNone(result)
        self.assertEqual(hits_before, urwid.CanvasCache.hits)
        self.assertEqual(fetches_before + 1, urwid.CanvasCache.fetches)

    def test_cleanup_ignores_a_ref_already_removed_by_invalidate(self):
        """invalidate() can drop a ref before its canvas is actually collected; cleanup() must not raise."""
        widget = urwid.Text("")
        canv = urwid.TextCanvas()
        canv.finalize(widget, (10, 1), False)
        urwid.CanvasCache.store(urwid.Widget, canv)
        ref = urwid.CanvasCache._widgets[widget][(urwid.Widget, (10, 1), False)]

        urwid.CanvasCache.invalidate(widget)
        self.assertNotIn(ref, urwid.CanvasCache._refs)

        cleanups_before = urwid.CanvasCache.cleanups
        urwid.CanvasCache.cleanup(ref)  # must be a no-op, not a KeyError

        self.assertEqual(cleanups_before + 1, urwid.CanvasCache.cleanups)

    def test_cleanup_ignores_a_ref_whose_widget_is_already_gone(self):
        """A ref can outlive its widget's entry in _widgets; cleanup() must tolerate that too."""
        widget = urwid.Text("")
        canv = urwid.TextCanvas()
        canv.finalize(widget, (10, 1), False)
        ref = weakref.ref(canv, urwid.CanvasCache.cleanup)
        urwid.CanvasCache._refs[ref] = (widget, urwid.Widget, (10, 1), False)
        # deliberately not registering `widget` in _widgets

        cleanups_before = urwid.CanvasCache.cleanups
        urwid.CanvasCache.cleanup(ref)

        self.assertEqual(cleanups_before + 1, urwid.CanvasCache.cleanups)
        self.assertNotIn(ref, urwid.CanvasCache._refs)

    def test_clear_empties_all_bookkeeping(self):
        widget = urwid.Text("")
        canv = urwid.TextCanvas()
        canv.finalize(widget, (10, 1), False)
        urwid.CanvasCache.store(urwid.Widget, canv)
        self.assertTrue(urwid.CanvasCache._widgets)
        self.assertTrue(urwid.CanvasCache._refs)

        urwid.CanvasCache.clear()

        self.assertEqual({}, urwid.CanvasCache._widgets)
        self.assertEqual({}, urwid.CanvasCache._refs)
        self.assertEqual({}, urwid.CanvasCache._deps)


class CanvasTest(unittest.TestCase):
    def test_basic_info(self):
        """Test str and repr methods for debugging purposes."""
        string = "Hello World!"
        rendered = urwid.Text(string).render(())
        self.assertEqual(string, str(rendered))
        self.assertEqual(
            f"<TextCanvas finalized=True cols={len(string)} rows=1 at 0x{id(rendered):X}>",
            repr(rendered),
        )

    def test_composite_basic_info(self):
        """Composite canvas contain info about canvas inside.

        Use canvas caching feature for test.
        """
        string = "Hello World!"
        widget = urwid.Text(string)
        rendered_widget = widget.render(())
        disabled = urwid.WidgetDisable(widget)
        rendered = disabled.render(())
        self.assertEqual(
            f"<CompositeCanvas "
            f"finalized=True cols={rendered_widget.cols()} rows={rendered_widget.rows()} "
            f"children=({rendered_widget!r}) at 0x{id(rendered):X}>",
            repr(rendered),
        )

    def test_set_pop_up_argument_validation(self):
        """Out of contract pop-up parameters are refused instead of mis-placing the pop-up."""
        widget = urwid.SolidFill("*")

        for description, kwargs, message in (
            ("negative left", {"left": -1, "top": 0}, "Pop-up position must not be negative"),
            ("negative top", {"left": 0, "top": -1}, "Pop-up position must not be negative"),
            ("zero width", {"overlay_width": 0}, "Pop-up size must be positive"),
            ("zero height", {"overlay_height": 0}, "Pop-up size must be positive"),
            ("negative width", {"overlay_width": -3}, "Pop-up size must be positive"),
            ("negative height", {"overlay_height": -3}, "Pop-up size must be positive"),
        ):
            with self.subTest(description):
                params = {"left": 0, "top": 0, "overlay_width": 4, "overlay_height": 2, **kwargs}
                canvas = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 10, 5))
                with self.assertRaises(urwid.CanvasError) as ctx:
                    canvas.set_pop_up(widget, **params)
                self.assertIn(message, str(ctx.exception))

        with self.subTest("in contract parameters are accepted"):
            canvas = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 10, 5))
            canvas.set_pop_up(widget, 0, 0, 4, 2)
            self.assertEqual((0, 0, (widget, 4, 2)), canvas.get_pop_up())

    def test_finalize_twice_raises(self):
        widget = urwid.Text("")
        canv = urwid.TextCanvas()
        canv.finalize(widget, (10, 1), False)
        with self.assertRaises(urwid.CanvasError):
            canv.finalize(widget, (10, 1), False)

    def test_set_cursor_on_finalized_cacheable_canvas_raises(self):
        widget = urwid.Text("")
        canv = urwid.TextCanvas()
        canv.finalize(widget, (10, 1), False)
        with self.assertRaises(urwid.CanvasError):
            canv.cursor = (0, 0)

    def test_set_pop_up_on_finalized_cacheable_canvas_raises(self):
        widget = urwid.SolidFill("*")
        canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 10, 5))
        canv.finalize(widget, (10, 5), False)
        with self.assertRaises(urwid.CanvasError):
            canv.set_pop_up(widget, 0, 0, 4, 2)

    def ct(self, text, attr, exp_content):
        with self.subTest(text=text, attr=attr, exp_content=exp_content):
            c = urwid.TextCanvas([t.encode("iso8859-1") for t in text], attr)
            content = list(c.content())
            self.assertEqual(content, exp_content, f"got: {content!r} expected: {exp_content!r}")

    def ct2(self, text, attr, left, top, cols, rows, def_attr, exp_content):
        c = urwid.TextCanvas([t.encode("iso8859-1") for t in text], attr)
        content = list(c.content(left, top, cols, rows, def_attr))
        self.assertEqual(content, exp_content, f"got: {content!r} expected: {exp_content!r}")

    def test1(self):
        self.ct(["Hello world"], None, [[(None, None, b"Hello world")]])
        self.ct(["Hello world"], [[("a", 5)]], [[("a", None, b"Hello"), (None, None, b" world")]])
        self.ct(["Hi", "There"], None, [[(None, None, b"Hi   ")], [(None, None, b"There")]])

    def test2(self):
        self.ct2(
            ["Hello"],
            None,
            0,
            0,
            5,
            1,
            None,
            [[(None, None, b"Hello")]],
        )
        self.ct2(
            ["Hello"],
            None,
            1,
            0,
            4,
            1,
            None,
            [[(None, None, b"ello")]],
        )
        self.ct2(
            ["Hello"],
            None,
            0,
            0,
            4,
            1,
            None,
            [[(None, None, b"Hell")]],
        )
        self.ct2(
            ["Hi", "There"],
            None,
            1,
            0,
            3,
            2,
            None,
            [[(None, None, b"i  ")], [(None, None, b"her")]],
        )
        self.ct2(
            ["Hi", "There"],
            None,
            0,
            0,
            5,
            1,
            None,
            [[(None, None, b"Hi   ")]],
        )
        self.ct2(
            ["Hi", "There"],
            None,
            0,
            1,
            5,
            1,
            None,
            [[(None, None, b"There")]],
        )


class TextCanvasErrorTest(unittest.TestCase):
    def test_text_must_be_bytes(self):
        with self.assertRaises(urwid.CanvasError):
            urwid.TextCanvas(["not bytes"])

    def test_check_width_false_requires_int_maxcol(self):
        with self.assertRaises(TypeError):
            urwid.TextCanvas([b"hi"], check_width=False, maxcol=None)

    def test_text_wider_than_maxcol_raises(self):
        with self.assertRaises(urwid.CanvasError):
            urwid.TextCanvas([b"hello"], maxcol=3)

    def test_attribute_extending_beyond_text_raises(self):
        with self.assertRaises(urwid.CanvasError):
            urwid.TextCanvas([b"hi"], attr=[[(None, 5)]])

    def test_character_set_extending_beyond_text_raises(self):
        with self.assertRaises(urwid.CanvasError):
            urwid.TextCanvas([b"hi"], cs=[[(None, 5)]])

    def test_translated_coords_with_and_without_cursor(self):
        with_cursor = urwid.TextCanvas([b"hi"], cursor=(1, 0))
        self.assertEqual((4, 3), with_cursor.translated_coords(3, 3))

        without_cursor = urwid.TextCanvas([b"hi"])
        self.assertIsNone(without_cursor.translated_coords(3, 3))

    def test_content_trim_top_out_of_range_raises(self):
        canv = urwid.TextCanvas([b"a", b"b"])
        with self.assertRaises(ValueError):
            list(canv.content(trim_top=5))


class BlankCanvasTest(unittest.TestCase):
    def test_cols_and_rows_are_unknown(self):
        blank = urwid.BlankCanvas()
        with self.assertRaises(NotImplementedError):
            blank.cols()
        with self.assertRaises(NotImplementedError):
            blank.rows()

    def test_content_uses_the_default_attribute_when_given(self):
        blank = urwid.BlankCanvas()
        self.assertEqual([[(None, None, b"   ")]], list(blank.content(cols=3, rows=1)))
        self.assertEqual([[("a", None, b"   ")]], list(blank.content(cols=3, rows=1, attr={None: "a"})))

    def test_content_with_zero_rows_yields_nothing(self):
        blank = urwid.BlankCanvas()
        self.assertEqual([], list(blank.content(cols=3, rows=0)))


class SolidCanvasErrorTest(unittest.TestCase):
    def test_fill_char_not_exactly_one_column_wide_raises(self):
        with self.subTest("empty"):
            with self.assertRaises(ValueError):
                urwid.SolidCanvas("", 3, 1)

        with self.subTest("double-width"):
            with self.assertRaises(ValueError):
                urwid.SolidCanvas("\N{HIRAGANA LETTER A}", 3, 1)


class ShardBodyTest(unittest.TestCase):
    def sbt(self, shards, shard_tail, expected):
        result = canvas.shard_body(shards, shard_tail, False)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def sbttail(self, num_rows, sbody, expected):
        result = canvas.shard_body_tail(num_rows, sbody)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def sbtrow(self, sbody, expected):
        result = list(canvas.shard_body_row(sbody))
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def test1(self):
        cviews = [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 5, None, "bar")]
        self.sbt(
            cviews,
            [],
            [(0, None, (0, 0, 10, 5, None, "foo")), (0, None, (0, 0, 5, 5, None, "bar"))],
        )
        self.sbt(
            cviews,
            [(0, 3, None, (0, 0, 5, 8, None, "baz"))],
            [
                (3, None, (0, 0, 5, 8, None, "baz")),
                (0, None, (0, 0, 10, 5, None, "foo")),
                (0, None, (0, 0, 5, 5, None, "bar")),
            ],
        )
        self.sbt(
            cviews,
            [(10, 3, None, (0, 0, 5, 8, None, "baz"))],
            [
                (0, None, (0, 0, 10, 5, None, "foo")),
                (3, None, (0, 0, 5, 8, None, "baz")),
                (0, None, (0, 0, 5, 5, None, "bar")),
            ],
        )
        self.sbt(
            cviews,
            [(15, 3, None, (0, 0, 5, 8, None, "baz"))],
            [
                (0, None, (0, 0, 10, 5, None, "foo")),
                (0, None, (0, 0, 5, 5, None, "bar")),
                (3, None, (0, 0, 5, 8, None, "baz")),
            ],
        )

    def test_underfilled_gap_is_padded(self):
        # cviews are short 4 columns of what the shard tail's gap expects: rather than
        # raising or silently truncating the row, the missing width is padded with a
        # blank filler cview so the resulting shard stays rectangular.
        # Regression test for https://github.com/urwid/urwid/issues/340
        cviews = [(0, 0, 6, 5, None, "foo")]
        result = canvas.shard_body(
            cviews,
            [(10, 3, None, (0, 0, 5, 8, None, "baz"))],
            False,
            num_rows=5,
        )
        assert result == [
            (0, None, (0, 0, 6, 5, None, "foo")),
            (0, None, (0, 0, 4, 5, None, canvas.blank_canvas)),
            (3, None, (0, 0, 5, 8, None, "baz")),
        ]

    def test2(self):
        sbody = [
            (0, None, (0, 0, 10, 5, None, "foo")),
            (0, None, (0, 0, 5, 5, None, "bar")),
            (3, None, (0, 0, 5, 8, None, "baz")),
        ]
        self.sbttail(5, sbody, [])
        self.sbttail(
            3,
            sbody,
            [
                (0, 3, None, (0, 0, 10, 5, None, "foo")),
                (0, 3, None, (0, 0, 5, 5, None, "bar")),
                (0, 6, None, (0, 0, 5, 8, None, "baz")),
            ],
        )

        sbody = [
            (0, None, (0, 0, 10, 3, None, "foo")),
            (0, None, (0, 0, 5, 5, None, "bar")),
            (3, None, (0, 0, 5, 9, None, "baz")),
        ]
        self.sbttail(
            3,
            sbody,
            [(10, 3, None, (0, 0, 5, 5, None, "bar")), (0, 6, None, (0, 0, 5, 9, None, "baz"))],
        )

    def test3(self):
        self.sbtrow(
            [
                (0, iter("foo"), (0, 0, 10, 5, None, "foo")),
                (0, iter("bar"), (0, 0, 5, 5, None, "bar")),
                (3, iter("zzz"), (0, 0, 5, 8, None, "baz")),
            ],
            ["f", "b", "z"],
        )

    def test_row_without_a_content_iterator_raises(self):
        with self.assertRaises(ValueError):
            list(canvas.shard_body_row([(0, None, (0, 0, 5, 5, None, "foo"))]))

    def test_cviews_wider_than_the_shard_tail_gap_raises(self):
        # the cview is 10 columns wide but the shard tail only leaves a 5 column gap for it
        cviews = [(0, 0, 10, 5, None, "foo")]
        shard_tail = [(5, 0, None, (0, 0, 5, 5, None, "bar"))]
        with self.assertRaises(canvas.CanvasError):
            canvas.shard_body(cviews, shard_tail, False)


class ShardsTrimTest(unittest.TestCase):
    def sttop(self, shards, top, expected):
        result = canvas.shards_trim_top(shards, top)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def strows(self, shards, rows, expected):
        result = canvas.shards_trim_rows(shards, rows)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def stsides(self, shards, left, cols, expected):
        result = canvas.shards_trim_sides(shards, left, cols)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def test1(self):
        shards = [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 5, None, "bar")])]
        self.sttop(shards, 2, [(3, [(0, 2, 10, 3, None, "foo"), (0, 2, 5, 3, None, "bar")])])
        self.strows(shards, 2, [(2, [(0, 0, 10, 2, None, "foo"), (0, 0, 5, 2, None, "bar")])])

        shards = [(5, [(0, 0, 10, 5, None, "foo")]), (3, [(0, 0, 10, 3, None, "bar")])]
        self.sttop(shards, 2, [(3, [(0, 2, 10, 3, None, "foo")]), (3, [(0, 0, 10, 3, None, "bar")])])
        self.sttop(shards, 5, [(3, [(0, 0, 10, 3, None, "bar")])])
        self.sttop(shards, 7, [(1, [(0, 2, 10, 1, None, "bar")])])
        self.strows(shards, 7, [(5, [(0, 0, 10, 5, None, "foo")]), (2, [(0, 0, 10, 2, None, "bar")])])
        self.strows(shards, 5, [(5, [(0, 0, 10, 5, None, "foo")])])
        self.strows(shards, 4, [(4, [(0, 0, 10, 4, None, "foo")])])

        shards = [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz")]), (3, [(0, 0, 10, 3, None, "bar")])]
        self.sttop(
            shards,
            2,
            [
                (3, [(0, 2, 10, 3, None, "foo"), (0, 2, 5, 6, None, "baz")]),
                (3, [(0, 0, 10, 3, None, "bar")]),
            ],
        )
        self.sttop(shards, 5, [(3, [(0, 0, 10, 3, None, "bar"), (0, 5, 5, 3, None, "baz")])])
        self.sttop(shards, 7, [(1, [(0, 2, 10, 1, None, "bar"), (0, 7, 5, 1, None, "baz")])])
        self.strows(
            shards,
            7,
            [
                (5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 7, None, "baz")]),
                (2, [(0, 0, 10, 2, None, "bar")]),
            ],
        )
        self.strows(shards, 5, [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 5, None, "baz")])])
        self.strows(shards, 4, [(4, [(0, 0, 10, 4, None, "foo"), (0, 0, 5, 4, None, "baz")])])

    def test2(self):
        shards = [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 5, None, "bar")])]
        self.stsides(shards, 0, 15, [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 5, None, "bar")])])
        self.stsides(shards, 6, 9, [(5, [(6, 0, 4, 5, None, "foo"), (0, 0, 5, 5, None, "bar")])])
        self.stsides(shards, 6, 6, [(5, [(6, 0, 4, 5, None, "foo"), (0, 0, 2, 5, None, "bar")])])
        self.stsides(shards, 0, 10, [(5, [(0, 0, 10, 5, None, "foo")])])
        self.stsides(shards, 10, 5, [(5, [(0, 0, 5, 5, None, "bar")])])
        self.stsides(shards, 1, 7, [(5, [(1, 0, 7, 5, None, "foo")])])

        shards = [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz")]), (3, [(0, 0, 10, 3, None, "bar")])]
        self.stsides(
            shards,
            0,
            15,
            [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz")]), (3, [(0, 0, 10, 3, None, "bar")])],
        )
        self.stsides(
            shards,
            2,
            13,
            [(5, [(2, 0, 8, 5, None, "foo"), (0, 0, 5, 8, None, "baz")]), (3, [(2, 0, 8, 3, None, "bar")])],
        )
        self.stsides(
            shards,
            2,
            10,
            [(5, [(2, 0, 8, 5, None, "foo"), (0, 0, 2, 8, None, "baz")]), (3, [(2, 0, 8, 3, None, "bar")])],
        )
        self.stsides(
            shards,
            2,
            8,
            [(5, [(2, 0, 8, 5, None, "foo")]), (3, [(2, 0, 8, 3, None, "bar")])],
        )
        self.stsides(
            shards,
            2,
            6,
            [(5, [(2, 0, 6, 5, None, "foo")]), (3, [(2, 0, 6, 3, None, "bar")])],
        )
        self.stsides(shards, 10, 5, [(8, [(0, 0, 5, 8, None, "baz")])])
        self.stsides(shards, 11, 3, [(8, [(1, 0, 3, 8, None, "baz")])])

    def test_argument_validation(self):
        shards = [(5, [(0, 0, 10, 5, None, "foo")])]

        with self.subTest("trim_top requires a positive amount"):
            with self.assertRaises(ValueError):
                canvas.shards_trim_top(shards, 0)

        with self.subTest("trim_top cannot remove every shard"):
            with self.assertRaises(canvas.CanvasError):
                canvas.shards_trim_top(shards, 5)

        with self.subTest("trim_rows rejects a negative row count"):
            with self.assertRaises(ValueError):
                canvas.shards_trim_rows(shards, -1)

        with self.subTest("trim_sides rejects a negative left"):
            with self.assertRaises(ValueError):
                canvas.shards_trim_sides(shards, -1, 5)

        with self.subTest("trim_sides rejects a non-positive width"):
            with self.assertRaises(ValueError):
                canvas.shards_trim_sides(shards, 0, 0)


class ShardsJoinTest(unittest.TestCase):
    def sjt(self, shard_lists, expected):
        result = canvas.shards_join(shard_lists)
        assert result == expected, f"got: {result!r} expected: {expected!r}"

    def test(self):
        shards1 = [(5, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz")]), (3, [(0, 0, 10, 3, None, "bar")])]
        shards2 = [(3, [(0, 0, 10, 3, None, "aaa")]), (5, [(0, 0, 10, 5, None, "bbb")])]
        shards3 = [
            (3, [(0, 0, 10, 3, None, "111")]),
            (2, [(0, 0, 10, 3, None, "222")]),
            (3, [(0, 0, 10, 3, None, "333")]),
        ]

        self.sjt([shards1], shards1)
        self.sjt(
            [shards1, shards2],
            [
                (3, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz"), (0, 0, 10, 3, None, "aaa")]),
                (2, [(0, 0, 10, 5, None, "bbb")]),
                (3, [(0, 0, 10, 3, None, "bar")]),
            ],
        )
        self.sjt(
            [shards1, shards3],
            [
                (3, [(0, 0, 10, 5, None, "foo"), (0, 0, 5, 8, None, "baz"), (0, 0, 10, 3, None, "111")]),
                (2, [(0, 0, 10, 3, None, "222")]),
                (3, [(0, 0, 10, 3, None, "bar"), (0, 0, 10, 3, None, "333")]),
            ],
        )
        self.sjt(
            [shards1, shards2, shards3],
            [
                (
                    3,
                    [
                        (0, 0, 10, 5, None, "foo"),
                        (0, 0, 5, 8, None, "baz"),
                        (0, 0, 10, 3, None, "aaa"),
                        (0, 0, 10, 3, None, "111"),
                    ],
                ),
                (2, [(0, 0, 10, 5, None, "bbb"), (0, 0, 10, 3, None, "222")]),
                (3, [(0, 0, 10, 3, None, "bar"), (0, 0, 10, 3, None, "333")]),
            ],
        )


class CanvasJoinTest(unittest.TestCase):
    def cjtest(self, desc, l, expected):
        l = [(c, None, False, n) for c, n in l]
        result = list(urwid.CanvasJoin(l).content())

        assert result == expected, f"{desc} expected {expected!r}, got {result!r}"

    def test(self):
        C = urwid.TextCanvas
        hello = C([b"hello"])
        there = C([b"there"], [[("a", 5)]])
        a = C([b"a"])
        hi = C([b"hi"])
        how = C([b"how"], [[("a", 1)]])
        dy = C([b"dy"])
        how_you = C([b"how", b"you"])

        self.cjtest("one", [(hello, 5)], [[(None, None, b"hello")]])
        self.cjtest(
            "two",
            [(hello, 5), (there, 5)],
            [[(None, None, b"hello"), ("a", None, b"there")]],
        )
        self.cjtest(
            "two space",
            [(hello, 7), (there, 5)],
            [[(None, None, b"hello"), (None, None, b"  "), ("a", None, b"there")]],
        )
        self.cjtest(
            "three space",
            [(hi, 4), (how, 3), (dy, 2)],
            [
                [(None, None, b"hi"), (None, None, b"  "), ("a", None, b"h"), (None, None, b"ow"), (None, None, b"dy")],
            ],
        )
        self.cjtest(
            "four space",
            [(a, 2), (hi, 3), (dy, 3), (a, 1)],
            [
                [
                    (None, None, b"a"),
                    (None, None, b" "),
                    (None, None, b"hi"),
                    (None, None, b" "),
                    (None, None, b"dy"),
                    (None, None, b" "),
                    (None, None, b"a"),
                ]
            ],
        )
        self.cjtest(
            "pile 2",
            [(how_you, 4), (hi, 2)],
            [
                [(None, None, b"how"), (None, None, b" "), (None, None, b"hi")],
                [(None, None, b"you"), (None, None, b" "), (None, None, b"  ")],
            ],
        )
        self.cjtest(
            "pile 2r",
            [(hi, 4), (how_you, 3)],
            [
                [(None, None, b"hi"), (None, None, b"  "), (None, None, b"how")],
                [(None, None, b"    "), (None, None, b"you")],
            ],
        )

    def test_shortcuts_are_attributed_to_the_joined_canvas_position(self) -> None:
        left = urwid.TextCanvas([b"hi"])
        left.shortcuts["k"] = "original"
        right = urwid.TextCanvas([b"there"])

        joined = urwid.CanvasJoin([(left, "left-pos", False, 2), (right, None, False, 5)])

        self.assertEqual({"k": "left-pos"}, joined.shortcuts)


class CanvasOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def cotest(self, desc, bgt, bga, fgt, fga, l, r, et):
        with self.subTest(desc):
            bgt = bgt.encode("iso8859-1")
            fgt = fgt.encode("iso8859-1")
            bg = urwid.CompositeCanvas(urwid.TextCanvas([bgt], [bga]))
            fg = urwid.CompositeCanvas(urwid.TextCanvas([fgt], [fga]))
            bg.overlay(fg, l, 0)
            result = list(bg.content())
            assert result == et, f"{desc} expected {et!r}, got {result!r}"

    def test1(self):
        self.cotest(
            "left",
            "qxqxqxqx",
            [],
            "HI",
            [],
            0,
            6,
            [[(None, None, b"HI"), (None, None, b"qxqxqx")]],
        )
        self.cotest(
            "right",
            "qxqxqxqx",
            [],
            "HI",
            [],
            6,
            0,
            [[(None, None, b"qxqxqx"), (None, None, b"HI")]],
        )
        self.cotest(
            "center",
            "qxqxqxqx",
            [],
            "HI",
            [],
            3,
            3,
            [[(None, None, b"qxq"), (None, None, b"HI"), (None, None, b"xqx")]],
        )
        self.cotest(
            "center2",
            "qxqxqxqx",
            [],
            "HI  ",
            [],
            2,
            2,
            [[(None, None, b"qx"), (None, None, b"HI  "), (None, None, b"qx")]],
        )
        self.cotest(
            "full",
            "rz",
            [],
            "HI",
            [],
            0,
            0,
            [[(None, None, b"HI")]],
        )

    def test2(self):
        self.cotest(
            "same",
            "asdfghjkl",
            [("a", 9)],
            "HI",
            [("a", 2)],
            4,
            3,
            [[("a", None, b"asdf"), ("a", None, b"HI"), ("a", None, b"jkl")]],
        )
        self.cotest(
            "diff",
            "asdfghjkl",
            [("a", 9)],
            "HI",
            [("b", 2)],
            4,
            3,
            [[("a", None, b"asdf"), ("b", None, b"HI"), ("a", None, b"jkl")]],
        )
        self.cotest(
            "None end",
            "asdfghjkl",
            [("a", 9)],
            "HI  ",
            [("a", 2)],
            2,
            3,
            [[("a", None, b"as"), ("a", None, b"HI"), (None, None, b"  "), ("a", None, b"jkl")]],
        )
        self.cotest(
            "float end",
            "asdfghjkl",
            [("a", 3)],
            "HI",
            [("a", 2)],
            4,
            3,
            [[("a", None, b"asd"), (None, None, b"f"), ("a", None, b"HI"), (None, None, b"jkl")]],
        )
        self.cotest(
            "cover 2",
            "asdfghjkl",
            [("a", 5), ("c", 4)],
            "HI",
            [("b", 2)],
            4,
            3,
            [[("a", None, b"asdf"), ("b", None, b"HI"), ("c", None, b"jkl")]],
        )
        self.cotest(
            "cover 2-2",
            "asdfghjkl",
            [("a", 4), ("d", 1), ("e", 1), ("c", 3)],
            "HI",
            [("b", 2)],
            4,
            3,
            [[("a", None, b"asdf"), ("b", None, b"HI"), ("c", None, b"jkl")]],
        )

    def test3(self):
        urwid.set_encoding("euc-jp")
        self.cotest(
            "db0",
            "\xa1\xa1\xa1\xa1\xa1\xa1",
            [],
            "HI",
            [],
            2,
            2,
            [[(None, None, b"\xa1\xa1"), (None, None, b"HI"), (None, None, b"\xa1\xa1")]],
        )
        self.cotest(
            "db1",
            "\xa1\xa1\xa1\xa1\xa1\xa1",
            [],
            "OHI",
            [],
            1,
            2,
            [[(None, None, b" "), (None, None, b"OHI"), (None, None, b"\xa1\xa1")]],
        )
        self.cotest(
            "db2",
            "\xa1\xa1\xa1\xa1\xa1\xa1",
            [],
            "OHI",
            [],
            2,
            1,
            [[(None, None, b"\xa1\xa1"), (None, None, b"OHI"), (None, None, b" ")]],
        )
        self.cotest(
            "db3",
            "\xa1\xa1\xa1\xa1\xa1\xa1",
            [],
            "OHIO",
            [],
            1,
            1,
            [[(None, None, b" "), (None, None, b"OHIO"), (None, None, b" ")]],
        )


class CompositeCanvasWrapTest(unittest.TestCase):
    def test_wrap_preserves_dimensions_text_and_cursor(self) -> None:
        """Wrapping a rendered canvas keeps its size and allows cursor updates."""
        base = urwid.Edit("x").render((10,), focus=True)
        wrapped = urwid.CompositeCanvas(canv=base)

        self.assertEqual((10, 1), (wrapped.cols(), wrapped.rows()))
        self.assertEqual([b"x         "], wrapped.text)
        self.assertEqual((1, 0), wrapped.cursor)

        wrapped.cursor = (3, 0)
        self.assertEqual((3, 0), wrapped.cursor)

    def test_wrap_accepts_pop_up_metadata(self) -> None:
        """Pop-up placement is recorded on a wrapped canvas."""
        inner = urwid.SolidFill(" ").render((20, 10))
        popup = urwid.Text("hi")
        wrapped = urwid.CompositeCanvas(canv=inner)
        wrapped.set_pop_up(popup, 5, 3, 8, 4)

        self.assertEqual((20, 10), (wrapped.cols(), wrapped.rows()))
        self.assertEqual((5, 3, (popup, 8, 4)), wrapped.get_pop_up())

    def test_wrap_inherits_shortcuts_as_wrap(self) -> None:
        inner = urwid.SolidCanvas(" ", 3, 1)
        inner.shortcuts["x"] = "original"
        wrapped = urwid.CompositeCanvas(canv=inner)
        self.assertEqual({"x": "wrap"}, wrapped.shortcuts)


class CompositeCanvasDimensionsTest(unittest.TestCase):
    def test_rows_rejects_a_non_integer_row_count(self) -> None:
        canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 1))
        canv.shards = [(1.5, canv.shards[0][1])]
        with self.assertRaises(TypeError):
            canv.rows()

    def test_cols_rejects_a_non_integer_column_count(self) -> None:
        canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 1))
        num_rows, cviews = canv.shards[0]
        (trim_left, trim_top, _cols, rows, attr_map, cv) = cviews[0]
        canv.shards = [(num_rows, [(trim_left, trim_top, 1.5, rows, attr_map, cv)])]
        with self.assertRaises(TypeError):
            canv.cols()


class CompositeCanvasTrimTest(unittest.TestCase):
    def test_trim_argument_validation(self) -> None:
        canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 5))

        with self.subTest("negative top"):
            with self.assertRaises(ValueError):
                canv.trim(-1)

        with self.subTest("top at or beyond the row count"):
            with self.assertRaises(ValueError):
                canv.trim(5)

    def test_trim_end_argument_validation(self) -> None:
        canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 5))

        with self.subTest("non-positive end"):
            with self.assertRaises(ValueError):
                canv.trim_end(0)

        with self.subTest("end beyond the row count"):
            with self.assertRaises(ValueError):
                canv.trim_end(6)

    def test_mutation_on_finalized_canvas_raises(self) -> None:
        widget = urwid.SolidFill(" ")
        for description, mutate in (
            ("trim", lambda c: c.trim(1)),
            ("trim_end", lambda c: c.trim_end(1)),
            ("pad_trim_left_right", lambda c: c.pad_trim_left_right(1, 0)),
            ("pad_trim_top_bottom", lambda c: c.pad_trim_top_bottom(1, 0)),
            ("overlay", lambda c: c.overlay(urwid.CompositeCanvas(urwid.SolidCanvas(" ", 1, 1)), 0, 0)),
            ("fill_attr_apply", lambda c: c.fill_attr_apply({})),
            ("set_depends", lambda c: c.set_depends([])),
        ):
            with self.subTest(description):
                canv = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 5))
                canv.finalize(widget, (3, 5), False)
                with self.assertRaises(urwid.CanvasError):
                    mutate(canv)


class CompositeCanvasOverlayValidationTest(unittest.TestCase):
    def test_overlay_rejects_a_mismatched_size(self) -> None:
        base = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 5, 5))

        with self.subTest("too wide"):
            with self.assertRaises(ValueError):
                base.overlay(urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 2)), 3, 0)

        with self.subTest("too tall"):
            with self.assertRaises(ValueError):
                base.overlay(urwid.CompositeCanvas(urwid.SolidCanvas(" ", 2, 3)), 0, 3)

    def test_overlay_on_a_rowless_canvas_yields_no_middle_shards(self) -> None:
        base = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 5, 5))
        base.trim(0, 0)  # empties the canvas: no rows left to overlay onto
        self.assertEqual(0, base.rows())
        self.assertEqual(0, base.cols())  # trimming to no rows also leaves no shards to measure columns from

        base.overlay(urwid.CompositeCanvas(), 0, 0)  # equally empty, so sizes still match
        self.assertEqual([], base.shards)


class CompositeCanvasFillAttrTest(unittest.TestCase):
    def test_fill_attr_sets_the_default_attribute(self) -> None:
        canv = urwid.CompositeCanvas(urwid.TextCanvas([b"hi"]))
        canv.fill_attr("a")
        self.assertEqual([[("a", None, b"hi")]], list(canv.content()))

    def test_fill_attr_apply_combines_with_an_existing_mapping(self) -> None:
        canv = urwid.CompositeCanvas(urwid.TextCanvas([b"hi"], [[("a", 2)]]))
        canv.fill_attr_apply({"a": "b"})
        canv.fill_attr_apply({"b": "c", "z": "z"})
        self.assertEqual([[("c", None, b"hi")]], list(canv.content()))


class CanvasPadTrimTopBottomTest(unittest.TestCase):
    def test_pad_top_and_bottom(self) -> None:
        canvas = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 3, 1))

        canvas.pad_trim_top_bottom(1, 2)

        self.assertEqual(4, canvas.rows())
        self.assertEqual(3, canvas.cols())
        self.assertEqual([b"   ", b"   ", b"   ", b"   "], canvas.text)

    def test_trim_bottom(self) -> None:
        canvas = urwid.CompositeCanvas(urwid.TextCanvas([b"a", b"b", b"c", b"d", b"e"]))

        canvas.pad_trim_top_bottom(0, -2)

        self.assertEqual(3, canvas.rows())
        self.assertEqual([b"a", b"b", b"c"], canvas.text)

    def test_trim_top(self) -> None:
        canvas = urwid.CompositeCanvas(urwid.TextCanvas([b"a", b"b", b"c"]))

        canvas.pad_trim_top_bottom(-1, 0)

        self.assertEqual(2, canvas.rows())
        self.assertEqual([b"b", b"c"], canvas.text)


class CanvasCombineTest(unittest.TestCase):
    def test_stacks_canvases_vertically(self) -> None:
        top = urwid.Text("top").render(())
        middle = urwid.Text("mid").render(())
        bottom = urwid.Text("bot").render(())

        combined = urwid.CanvasCombine(
            [
                (top, None, False),
                (middle, None, True),
                (bottom, None, False),
            ]
        )

        self.assertEqual(3, combined.rows())
        self.assertEqual(3, combined.cols())
        self.assertEqual([b"top", b"mid", b"bot"], combined.text)

    def test_shortcuts_are_attributed_to_the_stacked_canvas_position(self) -> None:
        top = urwid.Text("top").render(())
        top.shortcuts["k"] = "original"
        bottom = urwid.Text("bot").render(())

        combined = urwid.CanvasCombine([(top, "top-pos", False), (bottom, None, False)])

        self.assertEqual({"k": "top-pos"}, combined.shortcuts)


class CanvasOverlayFunctionTest(unittest.TestCase):
    def test_shortcuts_from_the_top_canvas_are_marked_fg(self) -> None:
        top = urwid.CompositeCanvas(urwid.SolidCanvas(" ", 2, 2))
        top.shortcuts["k"] = "original"
        bottom = urwid.SolidCanvas(" ", 5, 5)

        overlayed = canvas.CanvasOverlay(top, bottom, 1, 1)

        self.assertEqual({"k": "fg"}, overlayed.shortcuts)
        self.assertEqual((5, 5), (overlayed.cols(), overlayed.rows()))


class CanvasPadTrimTest(unittest.TestCase):
    def cptest(self, desc, ct, ca, l, r, et):
        with self.subTest(desc):
            ct = ct.encode("iso8859-1")
            c = urwid.CompositeCanvas(urwid.TextCanvas([ct], [ca]))
            c.pad_trim_left_right(l, r)
            result = list(c.content())
            self.assertEqual(result, et, f"{desc} expected {et!r}, got {result!r}")

    def test1(self):
        self.cptest("none", "asdf", [], 0, 0, [[(None, None, b"asdf")]])
        self.cptest("left pad", "asdf", [], 2, 0, [[(None, None, b"  "), (None, None, b"asdf")]])
        self.cptest("right pad", "asdf", [], 0, 2, [[(None, None, b"asdf"), (None, None, b"  ")]])

    def test2(self):
        self.cptest("left trim", "asdf", [], -2, 0, [[(None, None, b"df")]])
        self.cptest("right trim", "asdf", [], 0, -2, [[(None, None, b"as")]])


class ApplyTextLayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_repeated_offsets_reset_the_attribute_walk(self) -> None:
        # Two lines that both cover text offsets 0-4: the first line leaves
        # the attribute walk sitting at offset 2 (the start of the "b" run),
        # so the second line's request for offset 0 is behind it and arange()
        # has to rewind instead of assuming offsets only increase.
        text = b"abcdefgh"
        attr = [("a", 2), ("b", 2), ("c", 4)]
        ls = [[(4, 0, 4)], [(4, 0, 4)]]

        result = list(canvas.apply_text_layout(text, attr, ls, 4).content())

        expected_line = [("a", None, b"ab"), ("b", None, b"cd")]
        self.assertEqual([expected_line, expected_line], result)

    def test_attribute_change_within_a_double_width_segment(self) -> None:
        # A single word-wrap segment can still contain more than one markup
        # attribute; when the encoding also changes the segment's byte width
        # (double-width euc-jp characters here), each attribute chunk has to
        # be re-encoded on its own to work out how many columns it used.
        urwid.set_encoding("euc-jp")
        text = "ああ"  # two double-width hiragana characters
        attr = [("a", 1), ("b", 1)]
        ls = [[(4, 0, 2)]]

        result = list(canvas.apply_text_layout(text, attr, ls, 4).content())

        self.assertEqual([[("a", None, b"\xa4\xa2"), ("b", None, b"\xa4\xa2")]], result)
