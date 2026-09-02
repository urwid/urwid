from __future__ import annotations

import unittest

from urwid.ansi_parser import (
    LOGGER,
    AnsiParser,
    ParsedLine,
    SkippedOp,
    parse_ansi_line,
    parse_ansi_text,
    sgi_params_to_attrspec,
)
from urwid.display import AttrSpec
from urwid.util import rle_len


class LineSplittingTest(unittest.TestCase):
    def test_basic_split(self) -> None:
        lines = parse_ansi_line("one\ntwo\nthree")
        self.assertEqual(["one", "two", "three"], [line.text for line in lines])
        self.assertEqual(3, len(lines))

    def test_crlf_collapses_to_one_split(self) -> None:
        lines = parse_ansi_line("one\r\ntwo\n\rthree")
        self.assertEqual(["one", "two", "three"], [line.text for line in lines])

    def test_lone_cr_and_lf_are_independent_splits(self) -> None:
        # two identical line-end characters in a row are two separate
        # splits, not a collapsed pair (only \r\n / \n\r collapse)
        lines = parse_ansi_line("a\n\nb")
        self.assertEqual(["a", "", "b"], [line.text for line in lines])

    def test_trailing_unterminated_fragment(self) -> None:
        lines = parse_ansi_line("a\nb")
        self.assertEqual(["a", "b"], [line.text for line in lines])

    def test_trailing_line_end_yields_final_empty_fragment(self) -> None:
        # a line end is a structural split point: content after the final
        # split (even if empty) is still a real, returned line
        lines = parse_ansi_line("a\n")
        self.assertEqual(["a", ""], [line.text for line in lines])

    def test_empty_input(self) -> None:
        lines = parse_ansi_line("")
        self.assertEqual(1, len(lines))
        self.assertEqual("", lines[0].text)

    def test_no_content_lost(self) -> None:
        original = "abc\ndef\r\nghi\rjkl"
        lines = parse_ansi_line(original)
        # every printable character from the input appears somewhere in the
        # returned lines (only the line-end bytes themselves are consumed
        # as structural splits, never any other content)
        self.assertEqual("abcdefghijkl", "".join(line.text for line in lines))


class SgrContinuationTest(unittest.TestCase):
    def test_continuation_across_calls(self) -> None:
        first = parse_ansi_line("\x1b[31mred")
        second = parse_ansi_line("still red", previous_attr=first[-1].last_attr)
        self.assertIsNotNone(first[-1].last_attr)
        self.assertEqual(first[-1].last_attr, second[0].attrib[0][0])

    def test_continuation_within_single_call(self) -> None:
        lines = parse_ansi_line("\x1b[31mred\nstill red")
        self.assertEqual(2, len(lines))
        self.assertEqual(lines[0].last_attr, lines[1].last_attr)
        self.assertEqual(lines[0].last_attr, lines[1].attrib[0][0])
        self.assertIsNotNone(lines[0].last_attr)


class StreamingFeedTest(unittest.TestCase):
    def test_chunked_feed_matches_single_call(self) -> None:
        parser = AnsiParser(one_line=True)
        parser.feed("ab")
        parser.feed("c\nd")
        streamed = parser.finalize()

        single = parse_ansi_line("abc\nd")
        self.assertEqual([line.text for line in single], [line.text for line in streamed])
        self.assertEqual([line.attrib for line in single], [line.attrib for line in streamed])

    def test_line_end_split_across_feed_calls(self) -> None:
        parser = AnsiParser(one_line=True)
        parser.feed("one\r")
        parser.feed("\ntwo")
        lines = parser.finalize()
        self.assertEqual(["one", "two"], [line.text for line in lines])

    def test_escape_sequence_split_across_feed_calls(self) -> None:
        parser = AnsiParser(one_line=True)
        parser.feed("\x1b[3")
        parser.feed("1mred")
        lines = parser.finalize()
        self.assertEqual("red", lines[0].text)
        self.assertIsNotNone(lines[0].last_attr)


class HorizontalMovementTest(unittest.TestCase):
    def test_right_then_overwrite(self) -> None:
        # move right past "abc", write "Z" at position 5 (padding gap with
        # None-attr spaces), leaving "abc" untouched
        lines = parse_ansi_line("abc\x1b[2CZ")
        self.assertEqual("abc  Z", lines[0].text)

    def test_left_overwrite(self) -> None:
        lines = parse_ansi_line("abc\x1b[2DZY")
        self.assertEqual("aZY", lines[0].text)

    def test_absolute_column_pads_with_none_attr(self) -> None:
        lines = parse_ansi_line("\x1b[31mX\x1b[5GY")
        line = lines[0]
        self.assertEqual("X   Y", line.text)
        # the gap between the written "X" and the absolute-column "Y" was
        # never actually printed to, so it carries a None attr, distinct
        # from a space printed in the current (red) colour -- "Y" itself,
        # having been actually written, carries the current (red) attrspec
        expanded: list = []
        for attr, run in line.attrib:
            expanded.extend([attr] * run)
        self.assertIsNone(expanded[1])  # first gap cell
        self.assertIsNone(expanded[3])  # last gap cell, just before "Y"
        self.assertIsNotNone(expanded[4])  # "Y" itself: written, carries current attrspec

    def test_backspace_is_non_destructive(self) -> None:
        lines = parse_ansi_line("ab\bC")
        self.assertEqual("aC", lines[0].text)

    def test_tab_fills_with_current_attrspec(self) -> None:
        lines = parse_ansi_line("\x1b[31mA\tB")
        line = lines[0]
        self.assertEqual("A       B", line.text)
        expanded: list = []
        for attr, run in line.attrib:
            expanded.extend([attr] * run)
        # every cell up to and including the tab-filled spaces uses the
        # current (red) attrspec, unlike a bare cursor move
        self.assertTrue(all(a is not None for a in expanded[:9]))


class StripAndLogTest(unittest.TestCase):
    def _assert_skip(self, text: str, kind: str, level: str) -> SkippedOp:
        with self.assertLogs(LOGGER, level="INFO") as captured:
            lines = parse_ansi_line(text)
        line = lines[0]
        self.assertTrue(line.skipped, f"expected a SkippedOp for {text!r}")
        op = line.skipped[0]
        self.assertEqual(kind, op.kind)
        self.assertTrue(any(record.levelname == level for record in captured.records))
        return op

    def test_vertical_move_up_down(self) -> None:
        self._assert_skip("\x1b[2A", "vertical-move", "INFO")
        self._assert_skip("\x1b[2B", "vertical-move", "INFO")

    def test_vertical_move_next_prev_line(self) -> None:
        self._assert_skip("\x1b[1E", "vertical-move", "INFO")
        self._assert_skip("\x1b[1F", "vertical-move", "INFO")

    def test_vertical_move_absolute_row(self) -> None:
        self._assert_skip("\x1b[5d", "vertical-move", "INFO")

    def test_vertical_move_row_col(self) -> None:
        self._assert_skip("\x1b[3;4H", "vertical-move", "INFO")
        self._assert_skip("\x1b[3;4f", "vertical-move", "INFO")

    def test_terminal_setting_modes(self) -> None:
        self._assert_skip("\x1b[?25h", "terminal-setting", "INFO")
        self._assert_skip("\x1b[?25l", "terminal-setting", "INFO")

    def test_terminal_setting_scroll_region(self) -> None:
        self._assert_skip("\x1b[1;10r", "terminal-setting", "INFO")

    def test_terminal_setting_erase(self) -> None:
        self._assert_skip("\x1b[2J", "terminal-setting", "INFO")
        self._assert_skip("\x1b[K", "terminal-setting", "INFO")

    def test_terminal_setting_save_restore_cursor(self) -> None:
        self._assert_skip("\x1b[s", "terminal-setting", "INFO")
        self._assert_skip("\x1b[u", "terminal-setting", "INFO")
        self._assert_skip("\x1b7", "terminal-setting", "INFO")
        self._assert_skip("\x1b8", "terminal-setting", "INFO")

    def test_terminal_setting_charset(self) -> None:
        self._assert_skip("\x1b(B", "terminal-setting", "INFO")
        self._assert_skip("\x1b%G", "terminal-setting", "INFO")

    def test_terminal_setting_reset(self) -> None:
        self._assert_skip("\x1bc", "terminal-setting", "INFO")

    def test_terminal_setting_insert_delete(self) -> None:
        for final in "@LMPX":
            self._assert_skip(f"\x1b[1{final}", "terminal-setting", "INFO")

    def test_terminal_setting_device_queries(self) -> None:
        self._assert_skip("\x1b[c", "terminal-setting", "INFO")
        self._assert_skip("\x1b[5n", "terminal-setting", "INFO")

    def test_terminal_setting_tabstops(self) -> None:
        self._assert_skip("\x1bH", "terminal-setting", "INFO")
        self._assert_skip("\x1b[g", "terminal-setting", "INFO")

    def test_terminal_setting_osc_palette(self) -> None:
        self._assert_skip("\x1b]Pnrrggbbx", "terminal-setting", "INFO")
        self._assert_skip("\x1b]R", "terminal-setting", "INFO")

    def test_terminal_setting_unrecognised_osc(self) -> None:
        self._assert_skip("\x1b]666parsed right?\x1b\\", "terminal-setting", "INFO")

    def test_unknown_csi_logs_warning(self) -> None:
        op = self._assert_skip("\x1b[9~", "unknown", "WARNING")
        self.assertEqual("unknown", op.kind)

    def test_unknown_escape_logs_warning(self) -> None:
        self._assert_skip("\x1b|", "unknown", "WARNING")

    def test_never_raises(self) -> None:
        # a grab-bag of recognised and unrecognised sequences must never
        # raise, regardless of classification
        text = "\x1b[2A\x1b[?25h\x1b[31m\x1b[2C\x1b]666bad\x1b\\\x1b[9~\x1b|ok"
        lines = parse_ansi_line(text)
        self.assertEqual("ok", lines[0].text[-2:])


class SideChannelTest(unittest.TestCase):
    def test_bel_counted_and_excluded_from_text(self) -> None:
        lines = parse_ansi_line("a\x07\x07b")
        self.assertEqual("ab", lines[0].text)
        self.assertEqual(2, lines[0].bel)

    def test_bel_resets_per_line(self) -> None:
        lines = parse_ansi_line("a\x07\nb")
        self.assertEqual(1, lines[0].bel)
        self.assertEqual(0, lines[1].bel)

    def test_title_captured_and_excluded_from_text(self) -> None:
        lines = parse_ansi_line("\x1b]0;my title\x07rest")
        self.assertEqual("rest", lines[0].text)
        self.assertEqual("my title", lines[0].title)

    def test_title_prefixes(self) -> None:
        for prefix in (";", "0;", "2;"):
            lines = parse_ansi_line(f"\x1b]{prefix}hello\x07")
            self.assertEqual("hello", lines[0].title)

    def test_title_resets_per_line(self) -> None:
        lines = parse_ansi_line("\x1b]0;t1\x07a\nb")
        self.assertEqual("t1", lines[0].title)
        self.assertIsNone(lines[1].title)

    def test_title_terminated_by_st(self) -> None:
        lines = parse_ansi_line("\x1b];stupid title\x1b\\rest")
        self.assertEqual("stupid title", lines[0].title)
        self.assertEqual("rest", lines[0].text)

    def test_leds_captured_and_excluded_from_text(self) -> None:
        lines = parse_ansi_line("\x1b[3qtest")
        self.assertEqual("test", lines[0].text)
        self.assertEqual("caps_lock", lines[0].leds)

    def test_leds_mode_mapping(self) -> None:
        mapping = {0: "clear", 1: "scroll_lock", 2: "num_lock", 3: "caps_lock"}
        for mode, expected in mapping.items():
            lines = parse_ansi_line(f"\x1b[{mode}q")
            self.assertEqual(expected, lines[0].leds)

    def test_leds_resets_per_line(self) -> None:
        lines = parse_ansi_line("\x1b[3qa\nb")
        self.assertEqual("caps_lock", lines[0].leds)
        self.assertIsNone(lines[1].leds)


class SgiParamsToAttrspecTest(unittest.TestCase):
    def test_basic_foreground(self) -> None:
        self.assertEqual(AttrSpec("dark red", "default"), sgi_params_to_attrspec([31], None))

    def test_basic_background(self) -> None:
        self.assertEqual(AttrSpec("default", "dark blue"), sgi_params_to_attrspec([44], None))

    def test_bright_aixterm_foreground(self) -> None:
        result = sgi_params_to_attrspec([91], None)
        self.assertEqual(AttrSpec("light red", "default", colors=16), result)

    def test_256_colour(self) -> None:
        result = sgi_params_to_attrspec([38, 5, 200], None)
        self.assertEqual(AttrSpec("#f0d", "default", colors=256), result)

    def test_truecolour(self) -> None:
        result = sgi_params_to_attrspec([38, 2, 10, 20, 30], None)
        expected = AttrSpec("#0a141e", "default", colors=2**24)
        self.assertEqual(expected, result)

    def test_bold_set_and_unset(self) -> None:
        bold = sgi_params_to_attrspec([1], None)
        self.assertTrue(bold.bold)
        unbold = sgi_params_to_attrspec([22], bold)
        self.assertFalse(unbold.bold if unbold else False)

    def test_underline_blink_standout(self) -> None:
        result = sgi_params_to_attrspec([4, 5, 7], None)
        self.assertTrue(result.underline)
        self.assertTrue(result.blink)
        self.assertTrue(result.standout)
        unset = sgi_params_to_attrspec([24, 25, 27], result)
        self.assertFalse(unset.underline if unset else False)
        self.assertFalse(unset.blink if unset else False)
        self.assertFalse(unset.standout if unset else False)

    def test_reset(self) -> None:
        coloured = sgi_params_to_attrspec([31, 1], None)
        self.assertIsNotNone(coloured)
        reset = sgi_params_to_attrspec([0], coloured)
        self.assertIsNone(reset)

    def test_default_default_is_none(self) -> None:
        self.assertIsNone(sgi_params_to_attrspec([39, 49], None))

    def test_never_raises_on_charset_codes(self) -> None:
        # SGR 10/11/12 toggle vterm-only charset/display-control state;
        # sgi_params_to_attrspec must not raise and must simply ignore them
        result = sgi_params_to_attrspec([10], None)
        self.assertIsNone(result)
        result = sgi_params_to_attrspec([31, 11], None)
        self.assertEqual(AttrSpec("dark red", "default"), result)


class ParsedLineDataclassTest(unittest.TestCase):
    def test_fields_have_expected_defaults(self) -> None:
        line = ParsedLine(text="", attrib=[], last_attr=None)
        self.assertEqual(0, line.bel)
        self.assertIsNone(line.title)
        self.assertIsNone(line.leds)
        self.assertEqual([], line.skipped)

    def test_rle_len_matches_text_length(self) -> None:
        lines = parse_ansi_line("\x1b[31mred\x1b[0m and plain")
        for line in lines:
            self.assertEqual(len(line.text), rle_len(line.attrib))


class AnsiParserScreenModeTest(unittest.TestCase):
    def test_plain_multiline_roundtrips(self) -> None:
        result = parse_ansi_text("one\ntwo\nthree")
        self.assertEqual("one\ntwo\nthree", result.text)

    def test_empty_input(self) -> None:
        result = parse_ansi_text("")
        self.assertEqual("", result.text)

    def test_bare_cr_overwrites_current_row(self) -> None:
        # progress-bar-style in-place redraw: a bare \r (not part of a
        # \r\n / \n\r pair) resolves onto a single row, not two
        result = parse_ansi_text("progress: 10%\rprogress: 20%")
        self.assertEqual("progress: 20%", result.text)
        self.assertNotIn("\n", result.text)

    def test_crlf_and_lfcr_are_genuine_newlines(self) -> None:
        result = parse_ansi_text("one\r\ntwo\n\rthree")
        self.assertEqual("one\ntwo\nthree", result.text)

    def test_cr_split_across_feed_calls_stays_bare(self) -> None:
        parser = AnsiParser(one_line=False)
        parser.feed("progress: 10%\r")
        parser.feed("progress: 20%")
        result = parser.finalize()[0]
        self.assertEqual("progress: 20%", result.text)

    def test_crlf_split_across_feed_calls_is_still_one_newline(self) -> None:
        parser = AnsiParser(one_line=False)
        parser.feed("one\r")
        parser.feed("\ntwo")
        result = parser.finalize()[0]
        self.assertEqual("one\ntwo", result.text)

    def test_lfcr_split_across_feed_calls_is_still_one_newline(self) -> None:
        parser = AnsiParser(one_line=False)
        parser.feed("one\n")
        parser.feed("\rtwo")
        result = parser.finalize()[0]
        self.assertEqual("one\ntwo", result.text)

    def test_cursor_up_and_down(self) -> None:
        # write "AB" on row 0, drop to row 1, move back up onto row 0 -- the
        # column is untouched by CSI A/B, so the write lands right after "AB"
        result = parse_ansi_text("AB\n12\x1b[1AX")
        self.assertEqual("ABX\n12", result.text)

    def test_cursor_up_clamps_at_row_zero(self) -> None:
        result = parse_ansi_text("\x1b[5AX")
        self.assertEqual("X", result.text)

    def test_cursor_down_extends_with_blank_rows(self) -> None:
        # column untouched by CSI B: "A" leaves the column at 1, so the "B"
        # lands at column 1 on the extended row, padded with one space
        result = parse_ansi_text("A\x1b[3BB")
        self.assertEqual("A\n\n\n B", result.text)

    def test_cursor_next_line(self) -> None:
        result = parse_ansi_text("AB\x1b[1EX")
        self.assertEqual("AB\nX", result.text)

    def test_cursor_prev_line(self) -> None:
        result = parse_ansi_text("AB\nCD\x1b[1FX")
        self.assertEqual("XB\nCD", result.text)

    def test_cursor_absolute_row(self) -> None:
        # column untouched by CSI d, same padding reasoning as CSI B above
        result = parse_ansi_text("A\x1b[3dB")
        self.assertEqual("A\n\n B", result.text)

    def test_cursor_position_row_and_column(self) -> None:
        result = parse_ansi_text("\x1b[2;3HX")
        self.assertEqual("\n  X", result.text)

    def test_sgr_continuation_across_rows(self) -> None:
        result = parse_ansi_text("\x1b[31mred\nstill red")
        self.assertIsNotNone(result.last_attr)
        expanded: list = []
        for attr, run in result.attrib:
            expanded.extend([attr] * run)
        # "red" (positions 0-2) and "still red" (after the \n separator)
        # both carry the same non-None SGR attrspec
        self.assertEqual(result.last_attr, expanded[0])
        self.assertEqual(result.last_attr, expanded[-1])

    def test_bel_title_leds_aggregate_across_rows(self) -> None:
        # the leading \x07 and the one straight after "c" are real BEL
        # characters; the two used to terminate the OSC title sequences are
        # not counted as BEL
        result = parse_ansi_text("\x07a\n\x1b]0;first\x07b\n\x1b[3qc\x07\x1b]0;second\x07d")
        self.assertEqual(2, result.bel)
        self.assertEqual("second", result.title)
        self.assertEqual("caps_lock", result.leds)

    def test_terminal_setting_still_stripped_and_logged(self) -> None:
        with self.assertLogs(LOGGER, level="INFO"):
            result = parse_ansi_text("a\x1b[2Jb")
        self.assertTrue(result.skipped)
        self.assertEqual("terminal-setting", result.skipped[0].kind)
        self.assertEqual("ab", result.text)

    def test_terminal_setting_save_restore_cursor_still_stripped(self) -> None:
        with self.assertLogs(LOGGER, level="INFO"):
            result = parse_ansi_text("a\x1b[sb")
        self.assertTrue(result.skipped)
        self.assertEqual("terminal-setting", result.skipped[0].kind)

    def test_never_raises(self) -> None:
        text = "\x1b[2A\x1b[?25h\x1b[31m\x1b[2C\x1b]666bad\x1b\\\x1b[9~\x1b|ok"
        result = parse_ansi_text(text)
        self.assertTrue(result.text.endswith("ok"))

    def test_rle_len_matches_text_length(self) -> None:
        from urwid.util import rle_len

        result = parse_ansi_text("\x1b[31mred\nplain\rover\x1b[1Bnext")
        self.assertEqual(len(result.text), rle_len(result.attrib))


if __name__ == "__main__":
    unittest.main()
