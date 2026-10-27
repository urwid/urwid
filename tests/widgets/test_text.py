from __future__ import annotations

import unittest
import warnings

import urwid
import urwid.testing
from urwid.util import set_temporary_encoding


class TextTest(unittest.TestCase):
    def setUp(self):
        self.t = urwid.Text("I walk the\ncity in the night")

    def test1_wrap(self):
        expected = [t.encode("iso8859-1") for t in ("I walk the", "city in   ", "the night ")]
        got = self.t.render((10,))._text
        assert got == expected, f"got: {got!r} expected: {expected!r}"

    def test2_align(self):
        for align, lines in (
            ("left", ("I walk the        ", "city in the night ")),
            ("right", ("        I walk the", " city in the night")),
            ("center", ("    I walk the    ", " city in the night")),
        ):
            with self.subTest(align):
                self.t.set_align_mode(align)
                expected = [t.encode("iso8859-1") for t in lines]
                got = self.t.render((18,))._text
                assert got == expected, f"got: {got!r} expected: {expected!r}"

    def test_selectable(self) -> None:
        plain = urwid.Text("plain")
        row = urwid.Text("row", selectable=True)

        self.assertFalse(plain.selectable())
        self.assertTrue(row.selectable())
        self.assertEqual("enter", row.keypress((5,), "enter"))
        self.assertIsNone(row.render((5,), focus=True).cursor)

        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([plain, row]))
        listbox.render((5, 2), focus=True)
        self.assertEqual(1, listbox.focus_position)

    def test_selectable_false_keeps_class_attribute(self) -> None:
        """The default does not shadow a subclass's class-level ``_selectable``."""

        class AlwaysSelectable(urwid.Text):
            _selectable = True

            def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:
                return key

        self.assertTrue(AlwaysSelectable("x").selectable())
        self.assertTrue(urwid.SelectableIcon("x").selectable())
        self.assertNotIn("_selectable", vars(urwid.Text("x")))

    def test5_encode_error(self):
        with set_temporary_encoding("ascii"):
            expected = [b"?  "]
            got = urwid.Text("û").render((3,))._text
            assert got == expected, f"got: {got!r} expected: {expected!r}"

    def test_empty_markup_segments(self) -> None:
        """An empty markup segment must not truncate the rendered row or drop the content that follows it."""
        for name, markup, expected_text, expected_attrs in (
            ("middle", [("a", "X" * 10), ("b", ""), ("c", " END")], "XXXXXXXXXX END", [("a", 10), ("b", 0), ("c", 4)]),
            ("start", [("b", ""), ("a", "X" * 10), ("c", " END")], "XXXXXXXXXX END", [("b", 0), ("a", 10), ("c", 4)]),
            ("end", [("a", "X" * 10), ("c", " END"), ("b", "")], "XXXXXXXXXX END", [("a", 10), ("c", 4), ("b", 0)]),
            (
                "multiple",
                [("a", "AB"), ("b", ""), ("c", ""), ("d", "CD")],
                "ABCD",
                [("a", 2), ("b", 0), ("c", 0), ("d", 2)],
            ),
        ):
            with self.subTest(name):
                widget = urwid.Text(markup)

                self.assertEqual((expected_text, expected_attrs), widget.get_text())

                canvas = widget.render(())
                self.assertEqual([expected_text.encode()], canvas.text)
                self.assertEqual((expected_text,), canvas.decoded_text)

    def test_empty_markup_segment_render_content(self) -> None:
        """The canvas content rows must expose the display attribute of each segment."""
        widget = urwid.Text([("a", "X" * 10), ("b", ""), ("c", " END")])

        content = list(widget.render(()).content())
        attrs = [attr for row in content for attr, _cs, _text in row]
        rendered = b"".join(text for row in content for _attr, _cs, text in row)

        self.assertEqual(b"XXXXXXXXXX END", rendered)
        self.assertIn("a", attrs)
        self.assertIn("c", attrs)

    def test_nested_markup_with_a_hyperlink(self) -> None:
        """A hyperlink attribute nested in markup layers over the enclosing palette entry."""
        palette = [(None, "default", "default"), ("bold", "dark red,bold", "inherit")]
        link = urwid.AttrSpec(hyperlink="https://urwid.org")

        (row,) = urwid.Text(["a", ("bold", (link, "x"))]).render(()).content()
        attr, _cs, text = row[-1]

        self.assertEqual(b"x", text)
        self.assertIsInstance(attr, urwid.LayeredAttr)
        self.assertEqual(
            urwid.AttrSpec("dark red,bold", "default", hyperlink="https://urwid.org"),
            urwid.testing.resolve_attr(attr, palette, colors=16),
        )

    def test_markup_tuple_and_set_text(self) -> None:
        widget = urwid.Text(("title", "Hello"))

        self.assertEqual(("Hello", [("title", 5)]), widget.get_text())
        self.assertEqual("Hello", widget.text)
        self.assertEqual((5, 1), widget.pack(()))

        widget.set_text([("a", "AB"), ("b", "CD")])
        self.assertEqual(("ABCD", [("a", 2), ("b", 2)]), widget.get_text())

    def test_pack_does_not_wrap_after_tab(self) -> None:
        """A line holding a tab packs to its unwrapped width, not to a layout wrapped after the tab stop."""
        for widget, expected in (
            (urwid.Text("Tab\there:"), (13, 1)),
            (urwid.Text(b"Tab\there:"), (13, 1)),
            (urwid.Text("a\tb\tcccccccc"), (24, 1)),
            (urwid.Text("abcdef\t中中", wrap="any"), (12, 1)),
            (urwid.Text("a\tbbbbbbbbbbbb", layout=urwid.StandardTextLayout(tab_stops=(12,))), (24, 1)),
        ):
            with self.subTest(text=widget.text, wrap=widget.wrap):
                self.assertEqual(expected, widget.pack(()))

    def test_control_characters_are_drawn_in_the_columns_they_are_measured_as(self) -> None:
        """A control character or escape sequence measured as zero columns is left out of the canvas.

        The raw display then draws the text as wide as the layout measured it, and the neighbour stays in place.
        """
        for encoding in ("utf-8", "latin-1"):
            for text, drawn in (
                ("\x1b[31mred", "red"),
                ("a\rb", "ab"),
                ("a\x07b", "ab"),
                ("\x9b31m", "31m"),
                ("a\x1b]0;title\x07b", "ab"),
                ("a\x7fb", "ab"),
            ):
                with self.subTest(encoding=encoding, text=text), set_temporary_encoding(encoding):
                    widget = urwid.Text(text)
                    columns = urwid.Columns([(urwid.PACK, widget), urwid.Text("XYZ")])
                    screen = urwid.display.raw.Screen()
                    written: list[str] = []
                    screen.write = written.append
                    screen.flush = lambda: None
                    screen._started = True

                    canvas = columns.render((20,))
                    screen.draw_screen((20, canvas.rows()), canvas)

                    self.assertEqual((len(drawn), 1), widget.pack())
                    self.assertEqual([f"{drawn}XYZ".ljust(20).encode()], canvas.text)
                    self.assertIn(f"{drawn}XYZ\x1b[K", "".join(written))
                    self.assertEqual(text, widget.text)

    def test_utf8_bytes_leave_out_control_characters(self) -> None:
        """Bytes in UTF-8 are measured as decoded text, so an escape sequence in them takes no column either."""
        self.assertEqual([b"ab"], urwid.Text(b"a\x1b[1mb").render(()).text)

    def test_narrow_bytes_keep_control_characters(self) -> None:
        """Bytes in a narrow encoding measure one column per byte, which the display's ``?`` takes as well."""
        with set_temporary_encoding("latin-1"):
            self.assertEqual([b"a\x1b[1mb"], urwid.Text(b"a\x1b[1mb").render(()).text)

    def test_line_cut_inside_escape_sequence_draws_its_measured_columns(self) -> None:
        """A line cut by screen column counts ESC as zero columns and the rest of the sequence as text, and draws so."""
        self.assertEqual([b"ab[31", b"mcd  ", b"ef   "], urwid.Text("ab\x1b[31mcd ef").render((5,)).text)

    def test_control_characters_keep_attributes_aligned(self) -> None:
        """Each attribute run covers the characters drawn for it, without the control characters left out."""
        canvas = urwid.Text([("x", "a\x1b[1m"), ("y", "bc\x07"), "d"]).render((6,))
        self.assertEqual([[("x", None, b"a"), ("y", None, b"bc"), (None, None, b"d  ")]], list(canvas.content()))

        # the text OSC 66 displays ends the sequence, and its parameters may hold the same characters
        canvas = urwid.Text([("A", "\x1b]66;s=2;"), ("B", "2\x07x")]).render(())
        self.assertEqual([[("B", None, b"2x")]], list(canvas.content()))

    def test_segment_neither_measure_fits_is_drawn_unchanged(self) -> None:
        """A segment no drop makes as wide as laid out is drawn as given, rather than raising or overflowing."""
        for widget, width, expected in (
            (urwid.Text(b"a\xc2\x9bb\xff"), 3, [b"a\xc2\x9bb\xff"]),  # bytes that are not valid UTF-8
            (urwid.Text("\u200da\x07\u4e2d", wrap="clip"), 1, [b"\xe2\x80\x8da\x07 "]),
        ):
            with self.subTest(text=widget.text), warnings.catch_warnings():
                warnings.simplefilter("ignore", UnicodeWarning)
                canvas = widget.render((width,))
                layout_widths = [
                    urwid.text_layout.line_width(urwid.text_layout.trim_line(line, widget.text, 0, width))
                    for line in widget.get_line_translation(width)
                ]

                self.assertEqual(expected, canvas.text)
                self.assertEqual([width], layout_widths)
                self.assertEqual(width, canvas.cols())

    def test_layout_and_line_drawing_controls_unchanged(self) -> None:
        """LF and TAB are laid out, and SO and SI select the DEC line-drawing set, rather than being left out."""
        self.assertEqual([b"a        ", b"b       c"], urwid.Text("a\nb\tc").render(()).text)
        with set_temporary_encoding("latin-1"):
            canvas = urwid.Text("a\x0eq\x0fb").render(())

            self.assertEqual([b"aqb"], canvas.text)
            self.assertEqual([[None, "0", None]], [[cs for _, cs, _ in row] for row in canvas.content()])


class TestEmptyMarkup(unittest.TestCase):
    def test_001_empty(self):
        text = urwid.Text("")
        text.set_text(text.get_text())
        self.assertEqual("", text.text)


if __name__ == "__main__":
    unittest.main()
