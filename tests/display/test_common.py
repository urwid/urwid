from __future__ import annotations

import typing
import unittest

from urwid import LayeredAttr, signals
from urwid.display import common
from urwid.display.common import NO_HYPERLINK, AttrSpec, AttrSpecError, Hyperlink, _browser_href, attr_spec_to_css
from urwid.testing import ScriptedScreen

if typing.TYPE_CHECKING:
    from collections.abc import Hashable


class HyperlinkTest(unittest.TestCase):
    """Tests for the Hyperlink value type and the scheme check of the HTML-producing screens."""

    def test_rejected_values(self) -> None:
        for name, uri, link_id in (
            ("non-ASCII URI", "https://urwid.org/\u00e9", ""),
            ("escape in URI", "https://urwid.org/\x1b]8;;\x1b\\", ""),
            ("DEL in URI", "https://urwid.org/\x7f", ""),
            ("newline in id", "https://urwid.org", "a\nb"),
            ("colon in id", "https://urwid.org", "a:b"),
            ("semicolon in id", "https://urwid.org", "a;b"),
            ("URI too long", "https://urwid.org/" + "a" * 2066, ""),
            ("id too long", "https://urwid.org", "a" * 251),
            ("id without URI", "", "x"),
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                Hyperlink(uri, id=link_id)

    def test_accepted_values(self) -> None:
        self.assertEqual(2083, len(Hyperlink("https://urwid.org/" + "a" * 2065).uri))
        self.assertEqual(250, len(Hyperlink("https://urwid.org", id="a" * 250).id))
        self.assertEqual(NO_HYPERLINK, Hyperlink(""))

    def test_browser_href(self) -> None:
        for uri, expected in (
            (" javascript:alert(1)", None),
            ("JaVaScRiPt:alert(1)", None),
            ("data:text/html,<script>alert(1)</script>", None),
            ("vbscript:msgbox(1)", None),
            ("blob:https://urwid.org/1", None),
            ("ftp://urwid.org/file", None),
            ("urwid.org", None),
            ("", None),
            (" https://urwid.org/?q=javascript:x ", "https://urwid.org/?q=javascript:x"),
            ("MAILTO:a@b", "MAILTO:a@b"),
            ("sftp://urwid.org/file", "sftp://urwid.org/file"),
            ("file:///tmp/a.txt", "file:///tmp/a.txt"),
        ):
            with self.subTest(uri):
                self.assertEqual(expected, _browser_href(Hyperlink(uri)))


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

    def test_hyperlinks_share_the_cache_entry_of_their_style(self) -> None:
        common._style_to_css.cache_clear()
        expected = attr_spec_to_css(AttrSpec("white", "black"))

        for number in range(10):
            self.assertEqual(expected, attr_spec_to_css(AttrSpec("white", "black", hyperlink=f"https://a.b/{number}")))
        self.assertEqual(1, common._style_to_css.cache_info().currsize)


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

    def test_defaults_to_inherit(self) -> None:
        self.assertEqual(AttrSpec("inherit", "inherit"), AttrSpec())

    def test_hyperlink_is_part_of_the_value(self) -> None:
        plain = AttrSpec("dark red", "default")
        linked = AttrSpec("dark red", "default", hyperlink="https://urwid.org")
        same = AttrSpec("dark red", "default", hyperlink=Hyperlink("https://urwid.org"))

        self.assertEqual(Hyperlink("https://urwid.org"), linked.hyperlink)
        self.assertIsNone(plain.hyperlink)
        self.assertEqual(same, linked)
        self.assertEqual(hash(same), hash(linked))
        self.assertNotEqual(plain, linked)
        self.assertNotEqual(hash(plain), hash(linked))
        self.assertNotEqual(linked, AttrSpec("dark red", "default", hyperlink=NO_HYPERLINK))
        self.assertEqual(
            "AttrSpec('dark red', 'default', hyperlink=Hyperlink(uri='https://urwid.org', id='x'))",
            repr(plain.copy_modified(hyperlink=Hyperlink("https://urwid.org", id="x"))),
        )
        self.assertIs(plain, plain.style_only())
        self.assertEqual(plain, linked.style_only())
        with self.assertRaises(ValueError):
            AttrSpec(hyperlink="https://urwid.org/\x1b")

    def test_copy_modified_hyperlink(self) -> None:
        linked = AttrSpec("dark red", "inherit", hyperlink="https://urwid.org")

        for name, changes, expected in (
            ("kept", {"bg": "dark blue"}, AttrSpec("dark red", "dark blue", hyperlink="https://urwid.org")),
            ("replaced", {"hyperlink": "https://a.b"}, AttrSpec("dark red", "inherit", hyperlink="https://a.b")),
            ("explicit off", {"hyperlink": NO_HYPERLINK}, AttrSpec("dark red", "inherit", hyperlink=NO_HYPERLINK)),
            ("inherit", {"hyperlink": None}, AttrSpec("dark red", "inherit")),
        ):
            with self.subTest(name):
                self.assertEqual(expected, linked.copy_modified(**changes))

    def test_subclass_with_three_parameter_constructor(self) -> None:
        class Spec(AttrSpec):
            def __init__(self, fg: str, bg: str, colors: int = 256) -> None:
                super().__init__(fg, bg, colors)

        spec = Spec("dark red", "inherit")
        changed = spec.copy_modified(bg="dark blue")
        layered = spec.layered_over(AttrSpec("inherit", "brown", hyperlink="https://urwid.org"))

        self.assertIsInstance(changed, Spec)
        self.assertEqual(AttrSpec("dark red", "dark blue"), changed)
        self.assertEqual(AttrSpec("dark red", "brown", hyperlink="https://urwid.org"), layered)
        opaque = Spec("dark red", "default").layered_over(AttrSpec("inherit", "brown", hyperlink="https://urwid.org"))
        self.assertEqual(AttrSpec("dark red", "default", hyperlink="https://urwid.org"), opaque)
        with self.assertRaises(TypeError):
            spec.copy_modified(hyperlink="https://urwid.org")

    def test_layered_over_hyperlink(self) -> None:
        inner_link, outer_link = "https://inner.example", "https://outer.example"
        for name, inner, outer, expected in (
            (
                "inner wins",
                AttrSpec("inherit", "inherit", hyperlink=inner_link),
                AttrSpec("dark red", "black", hyperlink=outer_link),
                AttrSpec("dark red", "black", hyperlink=inner_link),
            ),
            (
                "outer taken",
                AttrSpec("inherit,bold", "inherit"),
                AttrSpec("dark red", "black", hyperlink=outer_link),
                AttrSpec("dark red,bold", "black", hyperlink=outer_link),
            ),
            (
                "opaque inner gains only the link",
                AttrSpec("dark red", "default"),
                AttrSpec("yellow,bold", "dark blue", hyperlink=outer_link),
                AttrSpec("dark red", "default", hyperlink=outer_link),
            ),
            (
                "explicit off hides the outer link",
                AttrSpec("inherit", "inherit", hyperlink=NO_HYPERLINK),
                AttrSpec("dark red", "black", hyperlink=outer_link),
                AttrSpec("dark red", "black", hyperlink=NO_HYPERLINK),
            ),
            (
                "true color mode kept by an opaque inner attribute",
                AttrSpec("dark red", "default", 2**24),
                AttrSpec("inherit", "inherit", hyperlink=outer_link),
                AttrSpec("dark red", "default", 2**24, hyperlink=outer_link),
            ),
        ):
            with self.subTest(name):
                self.assertEqual(expected, inner.layered_over(outer))

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
        self.screen = ScriptedScreen()
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

    def test_hyperlink_resolution(self) -> None:
        link = AttrSpec(hyperlink="https://urwid.org")

        self.assertEqual(
            AttrSpec("dark red", "dark blue", hyperlink="https://urwid.org"),
            self.screen.resolve_attr(LayeredAttr("red_fg", link, "blue_bg"), 0),
        )
        self.assertEqual(
            AttrSpec("dark red", "black", hyperlink="https://urwid.org"),
            self.screen.resolve_attr(LayeredAttr(link, "red_fg"), 0),
        )

    def test_palette_changes_are_seen(self) -> None:
        attr = LayeredAttr("red_fg", "blue_bg")
        self.screen.resolve_attr(attr, 0)  # resolved once, so it is cached

        self.screen.register_palette_entry("blue_bg", "inherit", "dark cyan")
        self.assertEqual(AttrSpec("dark red", "dark cyan"), self.screen.resolve_attr(attr, 0))
        self.screen.register_palette_entry(None, "default", "dark magenta")
        self.assertEqual(AttrSpec("dark red", "dark magenta"), self.screen.resolve_attr("red_fg", 0))
        self.screen.register_palette([("alias", "opaque")])
        self.assertEqual(AttrSpec("yellow", "default"), self.screen.resolve_attr("alias", 0))
        self.screen.register_palette([("blue_bg", "inherit", "dark green")], replace=True)
        self.assertEqual(AttrSpec("default", "default"), self.screen.resolve_attr("red_fg", 0))


class PaletteTest(unittest.TestCase):
    """Tests for reading the palette through BaseScreen.palette and replacing it with register_palette()."""

    def setUp(self) -> None:
        """Register a default entry, two plain entries and an alias."""
        self.screen = ScriptedScreen()
        self.screen.register_palette(
            [
                (None, "light gray", "black"),
                ("title", "white", "dark blue"),
                ("body", "black", "light gray"),
                ("alias", "title"),
            ]
        )

    def test_palette_view(self) -> None:
        """Read entries through a view that follows changes and refuses assignment."""
        view = self.screen.palette
        self.assertEqual(AttrSpec("white", "dark blue"), view["title"].basic)
        self.assertEqual(AttrSpec("white", "dark blue", 256), view["title"].high_256)
        self.assertEqual(view["title"].high_256, view["title"][3])
        self.assertEqual(view["title"], view["alias"])
        with self.assertRaises(TypeError):
            view["title"] = view["body"]  # type: ignore[index]
        self.screen.register_palette_entry("footer", "yellow", "black")
        self.assertIn("footer", view)

    def test_replace(self) -> None:
        """Remove the entries the new palette does not name, keeping the None entry unless it is named."""
        cases = (
            ("plain entry", [("body", "white", "black")], [None, "body"], AttrSpec("light gray", "black")),
            ("alias of a removed entry", [("copy", "title")], [None, "copy"], AttrSpec("light gray", "black")),
            ("default entry", [(None, "black", "white")], [None], AttrSpec("black", "white")),
            ("default entry as alias", [(None, "title")], [None], AttrSpec("white", "dark blue")),
            ("nothing", list[tuple[str, str, str]](), [None], AttrSpec("light gray", "black")),
        )
        for name, palette, expected, default in cases:
            with self.subTest(name):
                self.setUp()
                self.screen.register_palette(palette, replace=True)
                self.assertEqual(expected, list(self.screen.palette))
                self.assertEqual(default, self.screen.palette[None][0])

    def test_without_replace_entries_are_kept(self) -> None:
        """Keep the entries the new palette does not name."""
        self.screen.register_palette([("body", "white", "black")])
        self.assertEqual([None, "title", "body", "alias"], list(self.screen.palette))

    def test_replace_reports_removed_entries(self) -> None:
        """Send each removed name with the default colors it is drawn with from then on."""
        sent: dict[Hashable, tuple[AttrSpec, ...]] = {}

        def collect(name: Hashable, *specs: AttrSpec) -> None:
            sent[name] = specs

        signals.connect_signal(self.screen, common.UPDATE_PALETTE_ENTRY, collect)
        self.screen.register_palette([("body", "white", "black")], replace=True)

        self.assertEqual({"body", "title", "alias"}, set(sent))
        self.assertEqual(self.screen.palette["body"], sent["body"])
        default_specs = tuple(AttrSpec("default", "default", colors) for colors in (16, 1, 88, 256, 16777216))
        self.assertEqual(default_specs, sent["title"])
        self.assertEqual(AttrSpec("default", "default"), self.screen.resolve_attr("title", 0))

    def test_raising_handler_leaves_no_stale_colors(self) -> None:
        """Resolve every name by the palette as it is when a signal handler raises during the removals."""
        for name in ("title", "body", "alias"):
            self.screen.resolve_attr(name, 0)  # cached

        def fail_on_alias(name: Hashable, *_specs: AttrSpec) -> None:
            if name == "alias":
                raise RuntimeError(name)

        signals.connect_signal(self.screen, common.UPDATE_PALETTE_ENTRY, fail_on_alias)
        with self.assertRaises(RuntimeError):
            self.screen.register_palette([("body", "white", "black")], replace=True)

        self.assertEqual([None, "body", "alias"], list(self.screen.palette))
        for name, expected in (
            ("title", AttrSpec("default", "default")),
            ("body", AttrSpec("white", "black")),
            ("alias", AttrSpec("white", "dark blue")),
        ):
            with self.subTest(name):
                self.assertEqual(expected, self.screen.resolve_attr(name, 0))

    def test_invalid_entry_removes_nothing(self) -> None:
        """Remove no entry when the new palette has an invalid entry."""
        for name, palette in (
            ("wrong length", [("body", "white", "black"), ("bad", "white", "black", None, None)]),
            ("unknown alias target", [("body", "white", "black"), ("copy", "missing")]),
        ):
            with self.subTest(name):
                self.setUp()
                with self.assertRaises(common.ScreenError):
                    self.screen.register_palette(palette, replace=True)  # type: ignore[arg-type]
                self.assertEqual([None, "title", "body", "alias"], list(self.screen.palette))
                self.assertEqual(AttrSpec("white", "black"), self.screen.palette["body"][0])
