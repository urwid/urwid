from __future__ import annotations

import string
import unittest

import urwid
from urwid.util import get_encoding


class TestFontRender(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_001_basic(self):
        font = urwid.Thin3x3Font()
        rendered = b"\n".join(font.render("1").text).decode()
        expected = " ┐ \n │ \n ┴ "
        self.assertEqual(expected, rendered)

    def test_002_non_rect(self):
        """Test non rect symbol, which causes spaces based padding.

        Lines as bytes should be not equal length.
        """
        font = urwid.Thin3x3Font()
        rendered = b"\n".join(font.render("2").text).decode()
        expected = "┌─┐\n┌─┘\n└─ "
        self.assertEqual(expected, rendered)

    def test_003_distinct_glyphs(self):
        """No registered font draws two characters the same, such as ``0`` and ``O``."""
        for name, font_cls in urwid.get_all_fonts():
            with self.subTest(font=name):
                font = font_cls()
                seen: dict[tuple[str, ...], str] = {}
                for character in font.characters():
                    glyph = tuple(row.rstrip() for row in font.char_data(character))
                    self.assertNotIn(glyph, seen, f"{character!r} is drawn as {seen.get(glyph)!r}")
                    seen[glyph] = character

    def test_004_thin_5x4(self):
        """Thin 5x4 glyphs keep their trailing gap column."""
        font = urwid.Thin5x4Font()
        rendered = b"\n".join(font.render("R").text).decode()
        expected = "┬──┐ \n├─┬┘ \n│ └┐ \n┴  ┴ "
        self.assertEqual(expected, rendered)

    def test_005_character_sets(self):
        """Fonts render every character of the sets they cover, at the font's height."""
        letters = frozenset(string.ascii_letters)
        all_fonts = [font_cls() for _, font_cls in urwid.get_all_fonts()]
        cases = (
            (
                "letters and digits",
                frozenset(string.ascii_letters + string.digits),
                [
                    font_cls()
                    for font_cls in (
                        urwid.Thin5x4Font,
                        urwid.HalfBlock5x4Font,
                        urwid.HalfBlock6x5Font,
                        urwid.HalfBlockHeavy6x5Font,
                        urwid.Thin6x6Font,
                        urwid.HalfBlock7x7Font,
                    )
                ],
            ),
            (
                "punctuation",
                frozenset(string.punctuation + " "),
                [font for font in all_fonts if letters & frozenset(font.characters())],
            ),
        )
        for case, expected, fonts in cases:
            for font in fonts:
                with self.subTest(case=case, font=font.name):
                    self.assertEqual(frozenset(), expected - frozenset(font.characters()))
                    for character in sorted(expected):
                        with self.subTest(character=character):
                            self.assertEqual(font.height, font.render(character).rows())
