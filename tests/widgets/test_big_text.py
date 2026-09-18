from __future__ import annotations

import unittest

import urwid


class BigTextTest(unittest.TestCase):
    def test_get_text(self) -> None:
        widget = urwid.BigText("AB", urwid.HalfBlock5x4Font())
        text, attrib = widget.get_text()
        self.assertEqual(text, "AB")
        self.assertEqual(attrib, [])

    def test_get_text_with_attributes(self) -> None:
        widget = urwid.BigText([("bold", "AB")], urwid.HalfBlock5x4Font())
        text, attrib = widget.get_text()
        self.assertEqual(text, "AB")
        self.assertEqual(attrib, [("bold", 2)])

    def test_set_font(self) -> None:
        font_a = urwid.HalfBlock5x4Font()
        font_b = urwid.HalfBlock6x5Font()
        widget = urwid.BigText("A", font_a)
        self.assertIs(widget.font, font_a)
        widget.set_font(font_b)
        self.assertIs(widget.font, font_b)

    def test_render_attributes_applied(self) -> None:
        widget = urwid.BigText([("bold", "A")], urwid.HalfBlock5x4Font())
        canv = widget.render(())
        self.assertEqual(canv.rows(), 4)
        # The single attribute run should be applied across the glyph's width.
        for row in canv.content():
            for attr, _cs, _text in row:
                self.assertEqual(attr, "bold")

    def test_render_char_width_zero_is_skipped(self) -> None:
        # '\n' has zero width in HalfBlock5x4Font, so the render loop skips it
        # while still consuming the character's attribute run.
        widget = urwid.BigText([("bold", "A"), (None, "\n"), ("bold", "B")], urwid.HalfBlock5x4Font())
        canv_with_newline = widget.render(())
        canv_without = urwid.BigText([("bold", "AB")], urwid.HalfBlock5x4Font()).render(())
        self.assertEqual(list(canv_with_newline.text), list(canv_without.text))

    def test_pack(self) -> None:
        widget = urwid.BigText("AB", urwid.HalfBlock5x4Font())
        font = widget.font
        expected_cols = font.char_width("A") + font.char_width("B")
        self.assertEqual(widget.pack(), (expected_cols, font.height))

    def test_render_without_attributes(self) -> None:
        widget = urwid.BigText("A", urwid.HalfBlock5x4Font())
        canv = widget.render(())
        for row in canv.content():
            for attr, _cs, _text in row:
                self.assertIsNone(attr)

    def test_render_empty_text(self) -> None:
        widget = urwid.BigText("", urwid.HalfBlock5x4Font())
        canv = widget.render(())
        self.assertEqual(canv.rows(), 4)
        self.assertEqual(canv.cols(), 0)


if __name__ == "__main__":
    unittest.main()
