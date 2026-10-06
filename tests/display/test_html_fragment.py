from __future__ import annotations

import unittest

import urwid
from urwid.canvas import TextCanvas
from urwid.display import html_fragment, raw
from urwid.display.common import AttrSpec
from urwid.display.html_fragment import HtmlGenerator, HtmlGeneratorSimulationError, html_span
from urwid.event_loop import ExitMainLoop

try:
    from urwid.display import curses
except ImportError:  # no stdlib curses on this platform, e.g. Windows and GraalPy
    curses = None  # type: ignore[assignment]


class HtmlSpanTest(unittest.TestCase):
    """Tests for html_span, the html_fragment equivalent of web.code_span: both wrap
    common.attr_spec_to_css's inline CSS around the run of text, html_span into a ``<span>``
    rather than the wire format web.code_span produces. The colour/attribute-to-CSS logic
    itself is covered by tests/display/test_common.py, since the two modules share it.
    """

    def test_wraps_text_in_a_styled_span(self) -> None:
        self.assertEqual(
            '<span style="color:#ffffff;background:#000000">hi</span>',
            html_span("hi", AttrSpec("white", "black")),
        )

    def test_escapes_html_special_characters(self) -> None:
        self.assertEqual(
            '<span style="color:#ffffff;background:#000000">a &lt;b&gt; &amp; c</span>',
            html_span("a <b> & c", AttrSpec("white", "black")),
        )

    def test_empty_string_produces_no_span(self) -> None:
        self.assertEqual("", html_span("", AttrSpec("white", "black")))

    def test_combined_attributes_render_in_one_style(self) -> None:
        aspec = AttrSpec("white,bold,italics,underline,blink,strikethrough,faint", "black")

        span = html_span("hi", aspec)

        self.assertEqual(
            '<span style="color:#ffffff;background:#000000'
            ";text-decoration:underline line-through;font-weight:bold;font-style:italic"
            ';animation:urwid-blink 1s step-start infinite;opacity:0.5">hi</span>',
            span,
        )

    def test_cursor_splits_into_three_pieces_with_swapped_colours(self) -> None:
        span = html_span("abc", AttrSpec("white", "black"), cursor=1)

        self.assertEqual(
            '<span style="color:#ffffff;background:#000000">a</span>'
            '<span style="color:#000000;background:#ffffff">b</span>'
            '<span style="color:#ffffff;background:#000000">c</span>',
            span,
        )

    def test_cursor_at_last_column_leaves_a_trailing_empty_span(self) -> None:
        span = html_span("ab", AttrSpec("white", "black"), cursor=1)

        self.assertEqual(
            '<span style="color:#ffffff;background:#000000">a</span>'
            '<span style="color:#000000;background:#ffffff">b</span>'
            '<span style="color:#ffffff;background:#000000"></span>',
            span,
        )


class HtmlGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.screen = HtmlGenerator()
        # HtmlGenerator keeps its lists as class variables, shared across instances;
        # reset them so one test cannot see fixtures left behind by another.
        HtmlGenerator.fragments = []
        HtmlGenerator.sizes = []
        HtmlGenerator.keys = []

    def test_default_palette_entry_is_registered_on_construction(self) -> None:
        self.assertIn(None, self.screen._palette)

    def test_set_terminal_properties_keeps_unset_values(self) -> None:
        self.screen.set_terminal_properties(colors=256, has_underline=False)

        self.assertEqual(256, self.screen.colors)
        self.assertFalse(self.screen.bright_is_bold)
        self.assertFalse(self.screen.has_underline)

    def test_get_cols_rows_pops_the_next_size(self) -> None:
        HtmlGenerator.sizes = [(80, 25), (20, 10)]

        self.assertEqual((80, 25), self.screen.get_cols_rows())
        self.assertEqual((20, 10), self.screen.get_cols_rows())

    def test_get_cols_rows_raises_once_sizes_are_exhausted(self) -> None:
        HtmlGenerator.sizes = []

        with self.assertRaises(HtmlGeneratorSimulationError):
            self.screen.get_cols_rows()

    def test_get_input_pops_the_next_keys(self) -> None:
        HtmlGenerator.keys = [["down"], ["a", "b"]]

        self.assertEqual(["down"], self.screen.get_input())
        self.assertEqual(["a", "b"], self.screen.get_input())

    def test_get_input_raises_exit_main_loop_once_keys_are_exhausted(self) -> None:
        HtmlGenerator.keys = []

        with self.assertRaises(ExitMainLoop):
            self.screen.get_input()

    def test_get_input_raw_keys_returns_empty_raw_list(self) -> None:
        HtmlGenerator.keys = [["Q"]]

        self.assertEqual((["Q"], []), self.screen.get_input(raw_keys=True))

    def test_draw_screen_appends_one_pre_fragment(self) -> None:
        self.screen.register_palette_entry("focus", "light red,bold,underline,standout", "dark blue")
        canvas = urwid.AttrMap(urwid.Text("hi"), "focus").render((5,))

        self.screen.draw_screen((5, canvas.rows()), canvas)

        self.assertEqual(
            [
                '<pre><span style="color:#0000ee;background:#ff0000'
                ';text-decoration:underline;font-weight:bold">hi   </span>\n</pre>'
            ],
            HtmlGenerator.fragments,
        )

    def test_draw_screen_rejects_a_canvas_with_a_different_row_count(self) -> None:
        canvas = urwid.Text("hi").render((5,))

        with self.assertRaises(ValueError):
            self.screen.draw_screen((5, canvas.rows() + 1), canvas)

    def test_draw_screen_highlights_the_cursor_column(self) -> None:
        self.screen.register_palette_entry("focus", "white", "black")
        canvas = TextCanvas(text=[b"hi"], attr=[[("focus", 2)]], cs=[[(None, 2)]], cursor=(1, 0))

        self.screen.draw_screen((2, canvas.rows()), canvas)

        self.assertEqual(
            [
                "<pre>"
                '<span style="color:#ffffff;background:#000000">h</span>'
                '<span style="color:#000000;background:#ffffff">i</span>'
                '<span style="color:#ffffff;background:#000000"></span>'
                "\n</pre>"
            ],
            HtmlGenerator.fragments,
        )


class ScreenshotInitTest(unittest.TestCase):
    def setUp(self) -> None:
        if curses is not None:
            self._orig_curses_screen = curses.Screen
        self._orig_raw_screen = raw.Screen

    def tearDown(self) -> None:
        HtmlGenerator.sizes = []
        HtmlGenerator.keys = []
        if curses is not None:
            curses.Screen = self._orig_curses_screen
        raw.Screen = self._orig_raw_screen

    def test_rejects_a_non_positive_size(self) -> None:
        with self.assertWarns(DeprecationWarning), self.assertRaises(ValueError):
            html_fragment.screenshot_init([(80, 0)], [])

    def test_rejects_a_non_integer_size(self) -> None:
        with self.assertWarns(DeprecationWarning), self.assertRaises(TypeError):
            html_fragment.screenshot_init([(80.0, 25)], [])

    def test_rejects_keys_that_are_not_a_list_of_lists(self) -> None:
        with self.assertWarns(DeprecationWarning), self.assertRaises(TypeError):
            html_fragment.screenshot_init([(80, 25)], ["down"])

    def test_rejects_a_non_string_key(self) -> None:
        with self.assertWarns(DeprecationWarning), self.assertRaises(TypeError):
            html_fragment.screenshot_init([(80, 25)], [["down", 1]])

    def test_replaces_curses_and_raw_screen_with_html_generator(self) -> None:
        with self.assertWarns(DeprecationWarning):
            html_fragment.screenshot_init([(80, 25)], [["Q"]])

        if curses is not None:
            self.assertIs(curses.Screen, HtmlGenerator)
        self.assertIs(raw.Screen, HtmlGenerator)
        self.assertEqual([(80, 25)], HtmlGenerator.sizes)
        self.assertEqual([["Q"]], HtmlGenerator.keys)


class ScreenshotCollectTest(unittest.TestCase):
    def test_drains_the_fragments_list(self) -> None:
        HtmlGenerator.fragments = ["<pre>one</pre>", "<pre>two</pre>"]

        collected = html_fragment.screenshot_collect()

        self.assertEqual(["<pre>one</pre>", "<pre>two</pre>"], collected)
        self.assertEqual([], HtmlGenerator.fragments)
