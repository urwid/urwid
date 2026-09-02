from __future__ import annotations

import unittest

import urwid
from urwid.ansi_parser import AnsiParser
from urwid.util import get_encoding, rle_len


class ANSITextTest(unittest.TestCase):
    """Tests covering the default, multi-line (``one_line=False``) behaviour of :class:`~urwid.ANSIText`."""

    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_sizing(self) -> None:
        widget = urwid.ANSIText("hello")
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

    def test_pack_and_render_fixed(self) -> None:
        ansi = urwid.ANSIText("\x1b[31mhello\nworld\x1b[0m")
        plain = urwid.Text("hello\nworld")
        self.assertEqual(plain.pack(), ansi.pack())
        self.assertEqual(plain.render(()).text, ansi.render(()).text)

    def test_pack_and_render_flow(self) -> None:
        ansi = urwid.ANSIText("\x1b[32mimportant\nthings\x1b[0m")
        plain = urwid.Text("important\nthings")
        self.assertEqual(plain.pack((11,)), ansi.pack((11,)))
        self.assertEqual(plain.render((11,)).text, ansi.render((11,)).text)
        self.assertEqual(plain.rows((11,)), ansi.rows((11,)))

    def test_multirow_canvas_matches_plain_text(self) -> None:
        ansi = urwid.ANSIText("row one\nrow two\nrow three")
        plain = urwid.Text("row one\nrow two\nrow three")
        self.assertEqual(plain.render((20,)).text, ansi.render((20,)).text)
        self.assertEqual(3, len(ansi.render((20,)).text))

    def test_difference_from_one_line_multiline_input(self) -> None:
        # the key behavioural difference between the two modes: one_line=True
        # only ever surfaces the first physical line, while the default
        # (one_line=False) resolves the whole block into real multi-row output
        raw = "first\nsecond\nthird"
        line_widget = urwid.ANSIText(raw, one_line=True)
        text_widget = urwid.ANSIText(raw)
        self.assertEqual("first", line_widget.text)
        self.assertEqual("first\nsecond\nthird", text_widget.text)

    def test_progress_bar_redraw_produces_single_row(self) -> None:
        widget = urwid.ANSIText("progress: 10%\rprogress: 20%\rprogress: 100%")
        self.assertEqual("progress: 100%", widget.text)
        self.assertNotIn("\n", widget.text)
        self.assertEqual(1, len(widget.render((30,)).text))

    def test_vertical_cursor_movement_resolves_across_rows(self) -> None:
        widget = urwid.ANSIText("AB\n12\x1b[1EX")
        # CSI 1E: cursor next line + column reset -- so "X" lands on a new
        # row at column 0, not overwriting "12"
        self.assertEqual("AB\n12\nX", widget.text)

    def test_bel_title_leds_properties(self) -> None:
        widget = urwid.ANSIText("\x1b]0;my title\x07a\n\x1b[3qb\x07c")
        self.assertEqual("a\nbc", widget.text)
        self.assertEqual("my title", widget.title)
        self.assertEqual("caps_lock", widget.leds)
        self.assertEqual(1, widget.bel)

    def test_last_attr_property(self) -> None:
        widget = urwid.ANSIText("\x1b[31mred\nstill red")
        self.assertIsNotNone(widget.last_attr)
        continued = urwid.ANSIText("more red", previous_attr=widget.last_attr)
        self.assertEqual(widget.last_attr, continued.attrib[0][0])

    def test_attrib_rle_contract(self) -> None:
        widget = urwid.ANSIText("\x1b[31mred\x1b[0m and \n\x1b[32mgreen\x1b[0m")
        self.assertEqual(len(widget.text), rle_len(widget.attrib))

    def test_plain_text_regression_against_text(self) -> None:
        for sample in ("", "hello world", "line one\nline two", "trailing space \nnext"):
            ansi = urwid.ANSIText(sample)
            plain = urwid.Text(sample)
            self.assertEqual(plain.get_text(), ansi.get_text())
            self.assertEqual(plain.pack(), ansi.pack())
            self.assertEqual(plain.render((10,)).text, ansi.render((10,)).text)

    def test_set_ansi_text_reparses_and_invalidates(self) -> None:
        widget = urwid.ANSIText("first\nline")
        self.assertEqual("first\nline", widget.text)
        widget.set_ansi_text("\x1b[31msecond\nblock")
        self.assertEqual("second\nblock", widget.text)
        self.assertIsNotNone(widget.last_attr)

    def test_align_and_wrap_forwarded(self) -> None:
        widget = urwid.ANSIText("hi", align=urwid.RIGHT, wrap=urwid.CLIP)
        self.assertEqual([b"        hi"], widget.render((10,)).text)

    def test_from_lines_multiline_yields_single_widget(self) -> None:
        # the "normal multiline" from_lines path: several chunks (including
        # one containing an internal newline, and a chunk boundary that
        # splits a line) are fed in, and since one_line defaults to False,
        # exactly one ANSIText is yielded, representing the fully
        # reassembled multi-line block
        chunks = ["\x1b[31mred\nsti", "ll red\n\x1b[0mpla", "in\nlast li", "ne"]
        widgets = list(urwid.ANSIText.from_lines(chunks))
        self.assertEqual(1, len(widgets))
        self.assertEqual("red\nstill red\nplain\nlast line", widgets[0].text)

    def test_from_lines_multiline_matches_single_call(self) -> None:
        raw = "one\ntwo\nthree\x1b[31m\nfour"
        whole = list(urwid.ANSIText.from_lines([raw]))
        chunks = [raw[:3], raw[3:10], raw[10:15], raw[15:]]
        self.assertEqual("".join(chunks), raw)
        chunked = list(urwid.ANSIText.from_lines(chunks))
        self.assertEqual(1, len(whole))
        self.assertEqual(1, len(chunked))
        self.assertEqual(whole[0].text, chunked[0].text)
        self.assertEqual(whole[0].attrib, chunked[0].attrib)
        self.assertEqual(whole[0].last_attr, chunked[0].last_attr)

    def test_from_lines_multiline_preserves_mode_on_set_ansi_text(self) -> None:
        # a widget produced by from_lines(one_line=False) must remember its
        # mode, so a later set_ansi_text() call re-parses in the same mode
        (widget,) = list(urwid.ANSIText.from_lines(["a\nb"]))
        self.assertEqual("a\nb", widget.text)
        widget.set_ansi_text("c\nd")
        self.assertEqual("c\nd", widget.text)


class ANSITextOneLineTest(unittest.TestCase):
    """Tests covering ``ANSIText`` constructed with ``one_line=True``."""

    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_sizing(self) -> None:
        widget = urwid.ANSIText("hello", one_line=True)
        self.assertEqual(frozenset((urwid.FIXED, urwid.FLOW)), widget.sizing())

    def test_pack_and_render_fixed(self) -> None:
        ansi = urwid.ANSIText("\x1b[31mhello\x1b[0m", one_line=True)
        plain = urwid.Text("hello")
        self.assertEqual(plain.pack(), ansi.pack())
        self.assertEqual(plain.render(()).text, ansi.render(()).text)

    def test_pack_and_render_flow(self) -> None:
        ansi = urwid.ANSIText("\x1b[32mimportant things\x1b[0m", one_line=True)
        plain = urwid.Text("important things")
        self.assertEqual(plain.pack((11,)), ansi.pack((11,)))
        self.assertEqual(plain.render((11,)).text, ansi.render((11,)).text)
        self.assertEqual(plain.rows((11,)), ansi.rows((11,)))

    def test_embedded_line_end_uses_first_line_only(self) -> None:
        widget = urwid.ANSIText("a\nb", one_line=True)
        self.assertEqual("a", widget.text)

    def test_from_lines_pre_split(self) -> None:
        lines = list(
            urwid.ANSIText.from_lines(
                [
                    "\x1b[31mred line\n",
                    "still red (no new colour)\n",
                    "\x1b[0mplain again\n",
                ],
                one_line=True,
            )
        )
        # each trailing "\n" is a structural split point, so the final one
        # also flushes a trailing empty fragment as its own ANSIText
        self.assertEqual(4, len(lines))
        self.assertEqual("red line", lines[0].text)
        self.assertEqual("still red (no new colour)", lines[1].text)
        self.assertEqual("plain again", lines[2].text)
        self.assertEqual("", lines[3].text)
        # colour set on line 1 persists (via last_attr chaining) into the
        # unstyled line 2
        self.assertIsNotNone(lines[0].last_attr)
        self.assertEqual(lines[0].last_attr, lines[1].attrib[0][0])
        # explicit reset on line 3 clears it
        self.assertIsNone(lines[2].last_attr)

    def test_from_lines_unsplit_single_chunk_vs_chunked(self) -> None:
        raw = "\x1b[31mred\nstill red\n\x1b[0mplain\n"

        whole = list(urwid.ANSIText.from_lines([raw], one_line=True))

        # split at arbitrary offsets, including mid-escape-sequence and
        # mid-line splits
        chunks = [raw[:4], raw[4:9], raw[9:15], raw[15:22], raw[22:]]
        self.assertEqual("".join(chunks), raw)
        chunked = list(urwid.ANSIText.from_lines(chunks, one_line=True))

        self.assertEqual(len(whole), len(chunked))
        for a, b in zip(whole, chunked):
            self.assertEqual(a.text, b.text)
            self.assertEqual(a.attrib, b.attrib)
            self.assertEqual(a.last_attr, b.last_attr)

    def test_from_lines_flushes_final_unterminated_fragment(self) -> None:
        lines = list(urwid.ANSIText.from_lines(["no trailing newline"], one_line=True))
        self.assertEqual(1, len(lines))
        self.assertEqual("no trailing newline", lines[0].text)

    def test_from_lines_accumulates_single_parser_across_chunks(self) -> None:
        # confirm the underlying AnsiParser sees the same result whether
        # driven directly or through from_lines
        parser = AnsiParser(one_line=True)
        chunks = ["\x1b[3", "1mred\n", "plain"]
        for chunk in chunks:
            parser.feed(chunk)
        expected = parser.finalize()

        widgets = list(urwid.ANSIText.from_lines(chunks, one_line=True))
        self.assertEqual(len(expected), len(widgets))
        for parsed, widget in zip(expected, widgets):
            self.assertEqual(parsed.text, widget.text)

    def test_attrib_rle_contract(self) -> None:
        widget = urwid.ANSIText("\x1b[31mred\x1b[0m and \x1b[32mgreen\x1b[0m", one_line=True)
        self.assertEqual(len(widget.text), rle_len(widget.attrib))

    def test_bel_title_leds_properties_excluded_from_text(self) -> None:
        widget = urwid.ANSIText("\x1b]0;my title\x07\x1b[3q\x07hello", one_line=True)
        self.assertEqual("hello", widget.text)
        self.assertEqual("my title", widget.title)
        self.assertEqual("caps_lock", widget.leds)
        self.assertEqual(1, widget.bel)

    def test_last_attr_property(self) -> None:
        widget = urwid.ANSIText("\x1b[31mred", one_line=True)
        self.assertIsNotNone(widget.last_attr)
        continued = urwid.ANSIText("still red", previous_attr=widget.last_attr, one_line=True)
        self.assertEqual(widget.last_attr, continued.attrib[0][0])

    def test_plain_text_regression_against_text(self) -> None:
        for sample in ("", "hello world", "a  b   c", "line with trailing space "):
            ansi = urwid.ANSIText(sample, one_line=True)
            plain = urwid.Text(sample)
            self.assertEqual(plain.get_text(), ansi.get_text())
            self.assertEqual(plain.pack(), ansi.pack())
            self.assertEqual(plain.render((10,)).text, ansi.render((10,)).text)

    def test_set_ansi_text_reparses_and_invalidates(self) -> None:
        widget = urwid.ANSIText("first", one_line=True)
        self.assertEqual("first", widget.text)
        widget.set_ansi_text("\x1b[31msecond")
        self.assertEqual("second", widget.text)
        self.assertIsNotNone(widget.last_attr)

    def test_set_ansi_text_preserves_mode_from_from_lines(self) -> None:
        # a widget produced by from_lines(one_line=True) must remember its
        # mode, so a later set_ansi_text() call splits on the first line
        # again rather than switching to multi-row behaviour
        (widget,) = list(urwid.ANSIText.from_lines(["only line"], one_line=True))
        widget.set_ansi_text("a\nb")
        self.assertEqual("a", widget.text)

    def test_align_and_wrap_forwarded(self) -> None:
        widget = urwid.ANSIText("hi", align=urwid.RIGHT, wrap=urwid.CLIP, one_line=True)
        self.assertEqual([b"        hi"], widget.render((10,)).text)


if __name__ == "__main__":
    unittest.main()
