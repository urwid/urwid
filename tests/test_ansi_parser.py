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
        with self.assertLogs(LOGGER, level="DEBUG") as captured:
            lines = parse_ansi_line(text)
        line = lines[0]
        self.assertTrue(line.skipped, f"expected a SkippedOp for {text!r}")
        op = line.skipped[0]
        self.assertEqual(kind, op.kind)
        self.assertEqual({level}, {record.levelname for record in captured.records})
        return op

    def test_vertical_move_up_down(self) -> None:
        self._assert_skip("\x1b[2A", "vertical-move", "DEBUG")
        self._assert_skip("\x1b[2B", "vertical-move", "DEBUG")

    def test_vertical_move_next_prev_line(self) -> None:
        self._assert_skip("\x1b[1E", "vertical-move", "DEBUG")
        self._assert_skip("\x1b[1F", "vertical-move", "DEBUG")

    def test_vertical_move_absolute_row(self) -> None:
        self._assert_skip("\x1b[5d", "vertical-move", "DEBUG")

    def test_vertical_move_row_col(self) -> None:
        self._assert_skip("\x1b[3;4H", "vertical-move", "DEBUG")
        self._assert_skip("\x1b[3;4f", "vertical-move", "DEBUG")

    def test_terminal_setting_modes(self) -> None:
        self._assert_skip("\x1b[?25h", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b[?25l", "terminal-setting", "DEBUG")

    def test_terminal_setting_scroll_region(self) -> None:
        self._assert_skip("\x1b[1;10r", "terminal-setting", "DEBUG")

    def test_terminal_setting_erase(self) -> None:
        self._assert_skip("\x1b[2J", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b[K", "terminal-setting", "DEBUG")

    def test_terminal_setting_save_restore_cursor(self) -> None:
        self._assert_skip("\x1b[s", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b[u", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b7", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b8", "terminal-setting", "DEBUG")

    def test_terminal_setting_charset(self) -> None:
        self._assert_skip("\x1b(B", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b%G", "terminal-setting", "DEBUG")

    def test_terminal_setting_reset(self) -> None:
        self._assert_skip("\x1bc", "terminal-setting", "DEBUG")

    def test_terminal_setting_insert_delete(self) -> None:
        for final in "@LMPX":
            self._assert_skip(f"\x1b[1{final}", "terminal-setting", "DEBUG")

    def test_terminal_setting_device_queries(self) -> None:
        self._assert_skip("\x1b[c", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b[5n", "terminal-setting", "DEBUG")

    def test_terminal_setting_tabstops(self) -> None:
        self._assert_skip("\x1bH", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b[g", "terminal-setting", "DEBUG")

    def test_terminal_setting_osc_palette(self) -> None:
        self._assert_skip("\x1b]Pnrrggbbx", "terminal-setting", "DEBUG")
        self._assert_skip("\x1b]R", "terminal-setting", "DEBUG")

    def test_terminal_setting_unrecognised_osc(self) -> None:
        self._assert_skip("\x1b]666parsed right?\x1b\\", "terminal-setting", "DEBUG")

    def test_unknown_csi_logs_debug(self) -> None:
        op = self._assert_skip("\x1b[9~", "unknown", "DEBUG")
        self.assertEqual("unknown", op.kind)

    def test_unknown_escape_logs_debug(self) -> None:
        self._assert_skip("\x1b|", "unknown", "DEBUG")

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

    def test_applied_on_top_of_previous(self) -> None:
        """Keep each colour's own depth and brightness when other parameters change."""
        for label, previous, params, expected in (
            (
                "256-colour foreground beside a true-colour background",
                None,
                [38, 5, 100, 48, 2, 1, 2, 3],
                AttrSpec("#878700", "#010203", colors=2**24),
            ),
            (
                "basic foreground beside a true-colour background",
                None,
                [48, 2, 1, 2, 3, 31],
                AttrSpec("dark red", "#010203", colors=2**24),
            ),
            (
                "basic foreground after a true-colour background",
                [48, 2, 1, 2, 3],
                [31],
                AttrSpec("dark red", "#010203", colors=2**24),
            ),
            (
                "256-colour foreground after a true-colour background",
                [48, 2, 1, 2, 3],
                [38, 5, 100],
                AttrSpec("#878700", "#010203", colors=2**24),
            ),
            ("bright foreground keeps its brightness", [91], [4], AttrSpec("light red,underline", "default")),
            ("bright background keeps its brightness", [101], [4], AttrSpec("default,underline", "light red")),
            ("bold brightening stays while bold", [1, 31], [4], AttrSpec("light red,bold,underline", "default")),
            ("bold brightening goes with bold", [1, 31], [22], AttrSpec("dark red", "default")),
        ):
            with self.subTest(label):
                base = None if previous is None else sgi_params_to_attrspec(previous, None)
                self.assertEqual(expected, sgi_params_to_attrspec(params, base))


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
        with self.assertLogs(LOGGER, level="DEBUG"):
            result = parse_ansi_text("a\x1b[2Jb")
        self.assertTrue(result.skipped)
        self.assertEqual("terminal-setting", result.skipped[0].kind)
        self.assertEqual("ab", result.text)

    def test_terminal_setting_save_restore_cursor_still_stripped(self) -> None:
        with self.assertLogs(LOGGER, level="DEBUG"):
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


class UntrustedInputBoundsTest(unittest.TestCase):
    """Escape sequences from untrusted input cannot make the parser allocate without bound or raise.

    Each input is large enough to exceed the parser's limits, yet small enough to stay cheap if a limit regresses.
    """

    def test_cursor_right_and_absolute_column_are_bounded(self) -> None:
        """Cap the CSI C step and the CSI G column."""
        for text in ("\x1b[100000Cx", "\x1b[100000Gx", "ab\x1b[100000Gx"):
            with self.subTest(text=text):
                line = parse_ansi_line(text)[0]
                self.assertLessEqual(len(line.text), 1025)
                self.assertTrue(line.text.endswith(" x"))

    def test_cursor_right_step_is_capped_on_long_lines(self) -> None:
        """Advance a cursor past a long line by the full step, capped per sequence."""
        line = parse_ansi_line("a" * 1500 + "\x1b[3Cy")[0]
        self.assertTrue(line.text.endswith("a   y"))
        line = parse_ansi_line("a" * 1500 + "\x1b[100000Cy")[0]
        self.assertEqual(1500 + 1024 + 1, len(line.text))

    def test_cursor_down_and_absolute_row_are_bounded(self) -> None:
        """Cap the CSI B and E steps and the CSI d and H rows and columns."""
        for text in ("\x1b[100000Bx", "\x1b[100000Ex", "\x1b[100000dx", "\x1b[100000;100000Hx"):
            with self.subTest(text=text):
                rows = parse_ansi_text(text).text.split("\n")
                self.assertLessEqual(len(rows), 1025)
                self.assertLessEqual(len(rows[-1]), 1024)
                self.assertTrue(rows[-1].endswith("x"))

    def test_cursor_down_step_is_capped_below_many_rows(self) -> None:
        """Advance a cursor below many newline rows by the full step, capped per sequence."""
        result = parse_ansi_text("\n" * 2000 + "\x1b[5Bx")
        self.assertEqual(2006, len(result.text.split("\n")))
        result = parse_ansi_text("\n" * 2000 + "\x1b[100000Bx")
        self.assertEqual(2000 + 1024 + 1, len(result.text.split("\n")))

    def test_overlong_csi_parameter_is_skipped(self) -> None:
        """Skip a CSI parameter longer than the default 4300-digit limit of int()."""
        result = parse_ansi_text("a\x1b[" + "9" * 5000 + "mb")
        self.assertEqual("ab", result.text)
        self.assertIsNone(result.last_attr)
        self.assertEqual(["unknown"], [op.kind for op in result.skipped])

    def test_unterminated_csi_buffer_is_bounded(self) -> None:
        """Stop buffering CSI parameters at the length bound."""
        parser = AnsiParser()
        parser.feed("\x1b[" + "1;" * 10000)
        self.assertLessEqual(len(parser._escbuf), 640)

    def test_unterminated_osc_buffer_is_bounded(self) -> None:
        """Stop buffering an OSC string at the length bound."""
        parser = AnsiParser()
        parser.feed("\x1b]0;" + "A" * 100000)
        self.assertLessEqual(len(parser._escbuf), 10000)

    def test_overlong_osc_is_skipped_up_to_its_terminator(self) -> None:
        """Skip an over-long OSC string, discarding it up to either terminator."""
        for terminator in ("\x07", "\x1b\\"):
            with self.subTest(terminator=terminator):
                result = parse_ansi_text("a\x1b]0;" + "A" * 10000 + terminator + "b")
                self.assertEqual(["unknown"], [op.kind for op in result.skipped])
                self.assertEqual("ab", result.text)
                self.assertIsNone(result.title)

    def test_out_of_range_extended_colours_are_ignored(self) -> None:
        """Ignore a 256-colour index or truecolour component outside 0..255."""
        for params in ([38, 5, 99999999], [48, 5, 256], [38, 2, 999, 999, 999], [48, 2, 0, 0, 256]):
            with self.subTest(params=params):
                self.assertIsNone(sgi_params_to_attrspec(params, None))
                # the colour's own parameters are consumed, the rest still applies
                self.assertEqual(AttrSpec("dark red", "default"), sgi_params_to_attrspec([*params, 31], None))

    def test_out_of_range_colour_through_parser(self) -> None:
        """Ignore out-of-range extended colours in parsed text."""
        result = parse_ansi_line("\x1b[38;5;99999999mX\x1b[38;2;999;999;999mY")[0]
        self.assertEqual("XY", result.text)
        self.assertIsNone(result.last_attr)

    def test_skipped_list_is_capped(self) -> None:
        """Record only the first 65536 skipped sequences, in both modes."""
        text = "\x1b[2J" + "\x1b[K" * 70000
        for one_line in (True, False):
            with self.subTest(one_line=one_line):
                parser = AnsiParser(one_line=one_line)
                parser.feed(text)
                skipped = parser.finalize()[0].skipped
                self.assertEqual(65536, len(skipped))
                self.assertEqual(["\x1b[2J", "\x1b[K"], [op.raw for op in skipped[:2]])

    def test_skipped_cap_is_per_line_in_one_line_mode(self) -> None:
        """Start each line with an empty skipped list, so a full line does not cap the next one."""
        parser = AnsiParser(one_line=True)
        parser.feed("\x1b[K" * 70000 + "\n\x1b[K")
        lines = parser.finalize()
        self.assertEqual([65536, 1], [len(line.skipped) for line in lines])

    def test_column_padding_is_bounded(self) -> None:
        """Limit the cells padded to reach moved columns to 1024 * 1024 plus 8 per input character."""
        for unit in ("\n\x1b[1024Gx", "\x1b[1024Cx"):
            text = unit * 3000
            for one_line in (True, False):
                with self.subTest(unit=unit, one_line=one_line):
                    parser = AnsiParser(one_line=one_line)
                    parser.feed(text)
                    lines = parser.finalize()
                    cells = sum(len(line.text) - line.text.count("\n") for line in lines)
                    self.assertLessEqual(cells, 1024 * 1024 + 8 * len(text) + 3000)
                    skipped = [op for line in lines for op in line.skipped if op.raw == unit[-8:-1]]
                    self.assertTrue(skipped)

    def test_row_padding_is_bounded(self) -> None:
        """Limit the empty rows vertical moves insert, each counted as 8 cells."""
        text = "\x1b[1024Bx" * 500
        result = parse_ansi_text(text)
        rows = result.text.split("\n")
        self.assertLessEqual(8 * len(rows) + sum(map(len, rows)), 1024 * 1024 + 8 * len(text) + 500)
        self.assertEqual(500, "".join(rows).count("x"))
        self.assertIn("\x1b[1024B", [op.raw for op in result.skipped])

    def test_padding_cut_is_recorded_against_the_column_move(self) -> None:
        """Record a cut against the column move, not a vertical move one_line mode skips."""
        line = parse_ansi_line("\x1b[1024C" * 1100 + "\x1b[5Ax")[0]
        cut = [op.raw for op in line.skipped if op.reason.startswith("padding limit")]
        self.assertEqual(["\x1b[1024C"], cut)

    def test_padding_budget_spans_feed_calls(self) -> None:
        """Grow the padding budget with every feed call, up to the same limit as one call with all the text."""
        text = "\n\x1b[1024Gx" * 3000
        parser = AnsiParser()
        for start in range(0, len(text), 7):
            parser.feed(text[start : start + 7])
        result = parser.finalize()[0].text
        cells = len(result) - result.count("\n")
        self.assertLessEqual(cells, 1024 * 1024 + 8 * len(text) + 3000)
        self.assertGreater(cells, 1024 * 1024 + 3000)

    def test_sparse_full_screen_drawing_is_kept(self) -> None:
        """Keep the padding of a sparse drawing far below the padding limit."""
        result = parse_ansi_text("\x1b[1;1Htop\x1b[60;200Hmid\x1b[1000;1000Hend")
        expected = ["top"] + [""] * 58 + [" " * 199 + "mid"] + [""] * 939 + [" " * 999 + "end"]
        self.assertEqual(expected, result.text.split("\n"))
        self.assertEqual([], result.skipped)


class OscTerminationTest(unittest.TestCase):
    """An ESC inside an OSC string either starts the ST terminator or ends the string and starts a new sequence."""

    def _parse_chunked(self, chunks: list[str], one_line: bool) -> ParsedLine:
        parser = AnsiParser(one_line=one_line)
        for chunk in chunks:
            parser.feed(chunk)
        return parser.finalize()[0]

    def test_unterminated_osc_ends_at_escape(self) -> None:
        """End an OSC string at an ESC not followed by a backslash, unapplied, and parse what follows."""
        text = "a\x1b]0;title\x1b[31mred text\x07b"
        red = sgi_params_to_attrspec([31], None)
        for one_line in (True, False):
            for split in range(len(text) + 1):
                with self.subTest(one_line=one_line, split=split):
                    line = self._parse_chunked([text[:split], text[split:]], one_line)
                    self.assertEqual("ared textb", line.text)
                    self.assertEqual([(None, 1), (red, 9)], line.attrib)
                    self.assertIsNone(line.title)
                    self.assertEqual(1, line.bel)
                    self.assertEqual([("unknown", "\x1b]0;title")], [(op.kind, op.raw) for op in line.skipped])

    def test_osc_terminated_by_st_across_feed_calls(self) -> None:
        """Apply an OSC title whose ESC backslash terminator is split across two feed calls."""
        for one_line in (True, False):
            with self.subTest(one_line=one_line):
                line = self._parse_chunked(["\x1b]0;title\x1b", "\\rest"], one_line)
                self.assertEqual("title", line.title)
                self.assertEqual("rest", line.text)

    def test_title_never_contains_escape(self) -> None:
        """Take the title from the OSC string an ESC starts, not from the unterminated one before it."""
        for one_line in (True, False):
            with self.subTest(one_line=one_line):
                line = self._parse_chunked(["\x1b]0;ti\x1b", "]0;tle\x07x"], one_line)
                self.assertEqual("tle", line.title)
                self.assertEqual("x", line.text)

    def test_overlong_osc_discard_ends_at_escape(self) -> None:
        """End the discarded remainder of an over-long OSC string at an ESC not followed by a backslash."""
        red = sgi_params_to_attrspec([31], None)
        for one_line in (True, False):
            with self.subTest(one_line=one_line):
                line = self._parse_chunked(["a\x1b]0;" + "A" * 5000 + "\x1b", "[31mb"], one_line)
                self.assertEqual("ab", line.text)
                self.assertEqual([(None, 1), (red, 1)], line.attrib)
                self.assertIsNone(line.title)


if __name__ == "__main__":
    unittest.main()
