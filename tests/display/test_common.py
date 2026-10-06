from __future__ import annotations

import unittest

from tests.util import PaletteScreen
from urwid import LayeredAttr
from urwid.display.common import AttrSpec, AttrSpecError, attr_spec_to_css


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


class AttrSpecInheritTest(unittest.TestCase):
    """Tests for the 'inherit' color of AttrSpec and AttrSpec.layered_over."""

    def test_inherit_is_parsed_and_round_trips(self) -> None:
        spec = AttrSpec("inherit,bold", "inherit")

        self.assertTrue(spec.foreground_inherit)
        self.assertTrue(spec.background_inherit)
        self.assertTrue(spec.bold)
        self.assertEqual(1, spec.colors)
        self.assertEqual((None,) * 6, spec.get_rgb_values())
        self.assertEqual("AttrSpec('inherit,bold', 'inherit')", repr(spec))
        self.assertEqual(spec, AttrSpec("inherit", "inherit").copy_modified(fg="inherit,bold"))
        self.assertEqual(spec, spec.copy_modified())

    def test_inherit_differs_from_default(self) -> None:
        inherit, default = AttrSpec("inherit", "inherit"), AttrSpec("default", "default")

        self.assertNotEqual(default, inherit)
        self.assertNotEqual(hash(default), hash(inherit))
        self.assertFalse(default.foreground_inherit)
        self.assertFalse(AttrSpec("bold", "").background_inherit)

    def test_setting_parsing(self) -> None:
        """Keep 'no-' settings in the attribute, as a terminal keeps them, and refuse contradicting settings."""
        for foreground, background, expected in (
            ("inherit,no-underline,bold", "inherit", "inherit,bold,no-underline"),
            ("dark red,no-bold", "dark blue", "dark red,no-bold"),
        ):
            with self.subTest(foreground):
                self.assertEqual(expected, AttrSpec(foreground, background).foreground)
        self.assertNotEqual(AttrSpec("dark red", "dark blue"), AttrSpec("dark red,no-bold", "dark blue"))
        for foreground in ("bold,no-bold", "no-bold,no-bold"):
            with self.subTest(foreground), self.assertRaises(AttrSpecError):
                AttrSpec(foreground, "inherit")

    def test_copy_modified_adds_a_color(self) -> None:
        for name, spec, changes, expected in (
            (
                "default gets a background",
                AttrSpec("default", "default"),
                {"bg": "dark blue"},
                AttrSpec("default", "dark blue"),
            ),
            ("inherit gets a high color", AttrSpec("inherit", "inherit"), {"fg": "#fea"}, AttrSpec("#fea", "inherit")),
            ("88 colors kept", AttrSpec("inherit", "inherit", 88), {"fg": "#fea"}, AttrSpec("#fea", "inherit", 88)),
            (
                "basic colors get a background",
                AttrSpec("dark red", "dark blue", 16),
                {"bg": "brown"},
                AttrSpec("dark red", "brown"),
            ),
        ):
            with self.subTest(name):
                self.assertEqual(expected, spec.copy_modified(**changes))

    def test_opaque_attribute_is_returned_unchanged(self) -> None:
        inner = AttrSpec("dark red", "default")

        self.assertIs(inner, inner.layered_over(AttrSpec("yellow,bold", "dark blue")))

    def test_layered_over(self) -> None:
        """Take inherited colors from the outer attribute; settings from the inner one, else from the outer one."""
        cases = (
            ("fg over bg", ("dark red", "inherit"), ("inherit", "dark blue"), {}, ("dark red", "dark blue")),
            ("bg over fg", ("inherit", "dark blue"), ("dark red", "brown"), {}, ("dark red", "dark blue")),
            (
                "settings are combined",
                ("inherit,bold", "black"),
                ("white,underline", "brown"),
                {},
                ("white,bold,underline", "black"),
            ),
            ("outer inherit stays", ("inherit", "black"), ("inherit", "brown"), {}, ("inherit", "black")),
            (
                "inner no- wins",
                ("inherit,no-bold", "inherit"),
                ("yellow,bold,underline", "dark blue"),
                {},
                ("yellow,underline,no-bold", "dark blue"),
            ),
            (
                "outer no- is kept",
                ("inherit", "dark blue"),
                ("inherit,no-bold", "inherit"),
                {},
                ("inherit,no-bold", "dark blue"),
            ),
            (
                "larger color mode",
                ("#fea", "inherit", 88),
                ("inherit", "#76b900", 2**24),
                {},
                (AttrSpec("#fea", "inherit", 88).foreground, "#76b900", 2**24),
            ),
            (
                "given color mode",
                ("#f0d", "inherit", 256),
                ("inherit", "#ccc", 2**24),
                {"colors": 88},
                ("#f0d", "#ccc", 88),
            ),
        )
        for name, inner, outer, options, expected in cases:
            with self.subTest(name):
                self.assertEqual(AttrSpec(*expected), AttrSpec(*inner).layered_over(AttrSpec(*outer), **options))


class ResolveAttrTest(unittest.TestCase):
    """Tests for BaseScreen.resolve_attr, which turns a canvas run attribute into the AttrSpec to draw."""

    def setUp(self) -> None:
        """Register a palette with partial and opaque entries."""
        self.screen = PaletteScreen()
        self.screen.register_palette(
            [
                (None, "light gray", "black"),
                ("red_fg", "dark red", "inherit", "bold"),
                ("blue_bg", "inherit", "dark blue", "underline"),
                ("opaque", "yellow", "default"),
            ]
        )

    def test_resolve_attr(self) -> None:
        """Place each layer, outermost first, over the result so far, starting from the entry of None."""
        self.screen.register_palette(
            [
                ("panel", "inherit", "dark blue", None, "inherit", "#ccc"),
                ("parent", "inherit,bold", "inherit", "bold"),
                ("plain", "inherit,no-bold", "inherit", "no-bold"),
            ]
        )
        cases = (
            ("name over the None entry", "red_fg", 0, AttrSpec("dark red", "black")),
            ("opaque name", "opaque", 0, AttrSpec("yellow", "default")),
            ("two layers", LayeredAttr("red_fg", "blue_bg"), 0, AttrSpec("dark red", "dark blue")),
            (
                "AttrSpec layer",
                LayeredAttr(AttrSpec("inherit", "inherit"), "blue_bg"),
                0,
                AttrSpec("light gray", "dark blue"),
            ),
            ("opaque inner layer", LayeredAttr("opaque", "blue_bg"), 0, AttrSpec("yellow", "default")),
            (
                "88-color screen",
                LayeredAttr(AttrSpec("#f0d", "inherit", 256), "panel"),
                2,
                AttrSpec("#f0d", "#ccc", 88),
            ),
            (
                "256-color screen",
                LayeredAttr(AttrSpec("#f0d", "inherit", 256), "panel"),
                3,
                AttrSpec("#f0d", "#ccc", 256),
            ),
            (
                "enclosing settings kept",
                LayeredAttr("red_fg", "blue_bg", "parent"),
                0,
                AttrSpec("dark red,bold", "dark blue"),
            ),
            (
                "monochrome enclosing settings kept",
                LayeredAttr("red_fg", "blue_bg", "parent"),
                1,
                AttrSpec("default,bold,underline", "default", 1),
            ),
            (
                "monochrome settings combined",
                LayeredAttr("red_fg", "blue_bg"),
                1,
                AttrSpec("default,bold,underline", "default", 1),
            ),
            ("monochrome no- kept", LayeredAttr("plain", "parent"), 1, AttrSpec("default,no-bold", "default", 1)),
            ("unknown name hides layers", LayeredAttr("red_fg", "missing"), 0, AttrSpec("dark red", "default")),
            ("unknown name", "missing", 0, AttrSpec("default", "default")),
        )
        for name, attr, index, expected in cases:
            with self.subTest(name):
                self.assertEqual(expected, self.screen.resolve_attr(attr, index))

    def test_palette_changes_are_seen(self) -> None:
        attr = LayeredAttr("red_fg", "blue_bg")
        self.screen.resolve_attr(attr, 0)  # resolved once, so it is cached

        self.screen.register_palette_entry("blue_bg", "inherit", "dark cyan")
        self.assertEqual(AttrSpec("dark red", "dark cyan"), self.screen.resolve_attr(attr, 0))
        self.screen.register_palette_entry(None, "default", "dark magenta")
        self.assertEqual(AttrSpec("dark red", "dark magenta"), self.screen.resolve_attr("red_fg", 0))
        self.screen.register_palette([("alias", "opaque")])
        self.assertEqual(AttrSpec("yellow", "default"), self.screen.resolve_attr("alias", 0))
