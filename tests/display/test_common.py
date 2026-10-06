from __future__ import annotations

import unittest

from urwid.display.common import AttrSpec, attr_spec_to_css


class AttrSpecToCssTest(unittest.TestCase):
    """Tests for common.attr_spec_to_css, which translates an AttrSpec into the inline CSS
    shared by the web and html_fragment display modules -- their equivalent of raw_display's
    _attrspec_to_escape.
    """

    def test_default_colours_fall_back_to_black_on_light_gray(self) -> None:
        fg, bg, extra = attr_spec_to_css(AttrSpec("default", "default"))

        self.assertEqual("#000000", fg)
        self.assertEqual("#e5e5e5", bg)
        self.assertEqual("", extra)

    def test_named_colours_render_as_hex(self) -> None:
        fg, bg, extra = attr_spec_to_css(AttrSpec("white", "black"))

        self.assertEqual("#ffffff", fg)
        self.assertEqual("#000000", bg)
        self.assertEqual("", extra)

    def test_high_colour_renders_exact_rgb(self) -> None:
        fg, bg, _extra = attr_spec_to_css(AttrSpec("#76b900", "#000000", colors=16777216))

        self.assertEqual("#76b900", fg)
        self.assertEqual("#000000", bg)

    def test_basic_colour_beside_true_colour_renders_its_palette_rgb(self) -> None:
        for aspec, expected in (
            (AttrSpec("dark red", "#010203", colors=16777216), ("#cd0000", "#010203")),
            (AttrSpec("#010203", "dark blue", colors=16777216), ("#010203", "#0000ee")),
        ):
            with self.subTest(aspec=aspec):
                fg, bg, _extra = attr_spec_to_css(aspec)

                self.assertEqual(expected, (fg, bg))

    def test_standout_swaps_foreground_and_background(self) -> None:
        fg, bg, _extra = attr_spec_to_css(AttrSpec("white,standout", "black"))

        self.assertEqual("#000000", fg)
        self.assertEqual("#ffffff", bg)

    def test_all_attributes_combine_into_one_style(self) -> None:
        aspec = AttrSpec("white,bold,italics,underline,blink,strikethrough,faint", "black")
        _fg, _bg, extra = attr_spec_to_css(aspec)

        self.assertIn(";text-decoration:underline line-through", extra)
        self.assertIn(";font-weight:bold", extra)
        self.assertIn(";font-style:italic", extra)
        self.assertIn(";animation:urwid-blink 1s step-start infinite", extra)
        self.assertIn(";opacity:0.5", extra)

    def test_underline_alone_has_no_line_through(self) -> None:
        _fg, _bg, extra = attr_spec_to_css(AttrSpec("white,underline", "black"))

        self.assertEqual(";text-decoration:underline", extra)

    def test_no_attributes_gives_empty_extra(self) -> None:
        _fg, _bg, extra = attr_spec_to_css(AttrSpec("white", "black"))

        self.assertEqual("", extra)
