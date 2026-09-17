#!/usr/bin/python

"""Tests covering escape sequences processing"""

from __future__ import annotations

import unittest

import urwid
from urwid import util
from urwid.display import escape


class EscapeModifierTest(unittest.TestCase):
    def test_all_combinations(self):
        expected = {
            "1": "",
            "2": "shift ",
            "3": "meta ",
            "4": "shift meta ",
            "5": "ctrl ",
            "6": "shift ctrl ",
            "7": "meta ctrl ",
            "8": "shift meta ctrl ",
        }
        for digit, prefix in expected.items():
            self.assertEqual(prefix, escape.escape_modifier(digit))


class InputEscapeSequenceParserTest(unittest.TestCase):
    """Tests for parser of input escape sequences"""

    def test_bare_escape(self):
        codes = [27]
        expected = ["esc"]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_meta(self):
        codes = [27, ord("4"), ord("2")]
        expected = ["meta 4"]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([ord("2")], rest)

    def test_shift_arrows(self):
        codes = [27, ord("["), ord("a")]
        expected = ["shift up"]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_ctrl_pgup(self):
        codes = [27, 91, 53, 59, 53, 126]
        expected = ["ctrl page up"]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_esc_meta_1(self):
        codes = [27, 27, 49]
        expected = ["esc", "meta 1"]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_midsequence(self):
        # '[11~' is F1, '[12~' is F2, etc
        codes = [27, ord("["), ord("1")]

        with self.assertRaises(escape.MoreInputRequired):
            escape.process_keyqueue(codes, more_available=True)

        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(["meta ["], actual)
        self.assertListEqual([ord("1")], rest)

    def test_mouse_press(self):
        codes = [27, 91, 77, 32, 41, 48]
        expected = [("mouse press", 1.0, 8, 15)]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_bug_104(self):
        """GH #104: click-Esc & Esc-click crashes urwid apps"""
        codes = [27, 27, 91, 77, 32, 127, 59]
        expected = ["esc", ("mouse press", 1.0, 94, 26)]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

        codes = [27, 27, 91, 77, 35, 120, 59]
        expected = ["esc", ("mouse release", 0, 87, 26)]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(expected, actual)
        self.assertListEqual([], rest)

    def test_functional_keys(self):
        """Test for functional keys F1-F4, F5-F12."""

        def check_key(expected: str, codes: list[int]) -> None:
            actual, rest = escape.process_keyqueue(codes, more_available=False)
            self.assertEqual(
                [expected],
                actual,
                f"Codes {codes!r} ({[chr(code) for code in codes]}) was not decoded to {expected!r}",
            )

        # F1-F4
        for num in range(1, 5):
            codes = [27, ord("O"), 79 + num]
            check_key(f"f{num}", codes)

        # F5-F8
        for num, offset in enumerate((0, 2, 3, 4), start=5):
            codes = [27, ord("["), ord("1"), 53 + offset, ord("~")]
            check_key(f"f{num}", codes)

        # F9-F12
        for num, offset in enumerate((0, 1, 3, 4), start=9):
            codes = [27, ord("["), ord("2"), 48 + offset, ord("~")]
            check_key(f"f{num}", codes)

    def test_functional_keys_mods_f1_f4(self):
        """Test for modifiers handling for functional keys F1-F4."""
        prefixes = ("O", "[1;")
        masks = "12345678"
        letters = "PQRS"

        for prefix in prefixes:
            encoded_prefix = tuple(ord(element) for element in prefix)
            for num, letter in enumerate(letters, start=1):
                for mask in masks:
                    codes = [27, *encoded_prefix, ord(mask), ord(letter)]
                    actual, rest = escape.process_keyqueue(codes, more_available=False)
                    expected = escape.escape_modifier(mask) + f"f{num}"
                    self.assertEqual(
                        [expected],
                        actual,
                        f"Codes {codes!r} ({[chr(code) for code in codes]}) was not decoded to {expected!r}",
                    )

    def test_functional_keys_mods_simple_f1_20(self):
        """Test for modifiers handling for functional keys F1-F20."""
        masks = "12345678"
        numbers = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34)
        for num, number in enumerate(numbers, start=1):
            encoded_number = tuple(ord(element) for element in str(number))
            for mask in masks:
                codes = [27, ord("["), *encoded_number, ord(";"), ord(mask), ord("~")]
                actual, rest = escape.process_keyqueue(codes, more_available=False)
                expected = escape.escape_modifier(mask) + f"f{num}"
                self.assertEqual(
                    [expected],
                    actual,
                    f"Codes {codes!r} ({[chr(code) for code in codes]}) was not decoded to {expected!r}",
                )

    def test_sgrmouse(self):
        prefix = (27, ord("["), ord("<"))
        x = 4
        y = 8
        coord = (ord(f"{x + 1}"), ord(";"), ord(f"{y + 1}"))
        action = ord("M")
        modifiers = ((0, ""), (8, "meta "), (16, "ctrl "), (24, "meta ctrl "))
        for key, code in enumerate((0b0, 0b1, 0b10, 0b1000000, 0b1000001), start=1):
            for mod_code, mod in modifiers:
                key_code = tuple(ord(element) for element in str(code | mod_code))
                codes = [*prefix, *key_code, ord(";"), *coord, action]
                actual, rest = escape.process_keyqueue(codes, more_available=False)
                expected = [(mod + "mouse press", key, x, y)]
                self.assertEqual(
                    expected,
                    actual,
                    f"Codes {codes!r} ({[chr(code) for code in codes]}) was not decoded to {expected!r}",
                )

    def test_sgrmouse_shift_modifier(self):
        prefix = (27, ord("["), ord("<"))
        x = 4
        y = 8
        coord = (ord(f"{x + 1}"), ord(";"), ord(f"{y + 1}"))
        key_code = tuple(ord(element) for element in str(0 | 4))
        codes = [*prefix, *key_code, ord(";"), *coord, ord("M")]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertEqual([("shift mouse press", 1, x, y)], actual)
        self.assertListEqual([], rest)

    def test_sgrmouse_drag(self):
        prefix = (27, ord("["), ord("<"))
        x = 4
        y = 8
        coord = (ord(f"{x + 1}"), ord(";"), ord(f"{y + 1}"))
        key_code = tuple(ord(element) for element in str(0 | escape.MOUSE_DRAG_FLAG))
        codes = [*prefix, *key_code, ord(";"), *coord, ord("M")]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertEqual([("mouse drag", 1, x, y)], actual)
        self.assertListEqual([], rest)

    def test_sgrmouse_release(self):
        prefix = (27, ord("["), ord("<"))
        x = 4
        y = 8
        coord = (ord(f"{x + 1}"), ord(";"), ord(f"{y + 1}"))
        key_code = tuple(ord(element) for element in str(0))
        codes = [*prefix, *key_code, ord(";"), *coord, ord("m")]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertEqual([("mouse release", 1, x, y)], actual)
        self.assertListEqual([], rest)

    def test_sgrmouse_truncated(self):
        codes = [27, ord("["), ord("<")]
        with self.assertRaises(escape.MoreInputRequired):
            escape.process_keyqueue(codes, more_available=True)
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertListEqual(["meta ["], actual)
        self.assertListEqual([ord("<")], rest)

    def test_sgrmouse_missing_terminator(self):
        codes = [ord("0"), ord(";"), ord("5"), ord(";"), ord("8")]
        with self.assertRaises(escape.MoreInputRequired):
            escape.input_trie.read_sgrmouse_info(codes, more_available=True)
        self.assertIsNone(escape.input_trie.read_sgrmouse_info(codes, more_available=False))

    def test_mouse_x10_modifiers(self):
        x, y = 8, 15
        coord = (x + 33, y + 33)
        for bit, prefix in ((4, "shift "), (8, "meta "), (16, "ctrl "), (4 | 8 | 16, "shift meta ctrl ")):
            codes = [27, 91, 77, 32 + bit, *coord]
            actual, rest = escape.process_keyqueue(codes, more_available=False)
            self.assertEqual([(f"{prefix}mouse press", 1, x, y)], actual)
            self.assertListEqual([], rest)

    def test_mouse_x10_drag(self):
        x, y = 8, 15
        codes = [27, 91, 77, 32 + escape.MOUSE_DRAG_FLAG, x + 33, y + 33]
        actual, rest = escape.process_keyqueue(codes, more_available=False)
        self.assertEqual([("mouse drag", 1, x, y)], actual)
        self.assertListEqual([], rest)

    def test_mouse_x10_truncated(self):
        codes = [27, 91, 77, 32]
        with self.assertRaises(escape.MoreInputRequired):
            escape.process_keyqueue(codes, more_available=True)
        self.assertIsNone(escape.input_trie.read_mouse_info([32], more_available=False))

    def test_utf8_multibyte_decoding(self):
        old_encoding = util.get_encoding()
        try:
            urwid.set_encoding("utf-8")

            for text, codes in (
                ("\xe9", list(b"\xc3\xa9")),  # 2-byte
                ("€", list(b"\xe2\x82\xac")),  # 3-byte
                ("\U0001f600", list(b"\xf0\x9f\x98\x80")),  # 4-byte
            ):
                with self.subTest(text=text):
                    actual, rest = escape.process_keyqueue(codes, more_available=False)
                    self.assertEqual([text], actual)
                    self.assertListEqual([], rest)

            # invalid continuation byte falls back to a placeholder
            actual, rest = escape.process_keyqueue([0xC3, ord("A")], more_available=False)
            self.assertEqual(["<195>"], actual)
            self.assertListEqual([ord("A")], rest)

            # a standalone byte that is not a valid utf-8 lead byte (a bare continuation byte)
            actual, rest = escape.process_keyqueue([0x80], more_available=False)
            self.assertEqual(["<128>"], actual)
            self.assertListEqual([], rest)

            # overlong 2-byte encoding of NUL is structurally valid but fails to decode
            actual, rest = escape.process_keyqueue([0xC0, 0x80], more_available=False)
            self.assertEqual(["<192>"], actual)
            self.assertListEqual([0x80], rest)

            # truncated multi-byte sequence
            with self.assertRaises(escape.MoreInputRequired):
                escape.process_keyqueue([0xC3], more_available=True)
            actual, rest = escape.process_keyqueue([0xC3], more_available=False)
            self.assertEqual(["<195>"], actual)
            self.assertListEqual([], rest)
        finally:
            urwid.set_encoding(old_encoding)

    def test_nul_byte_fallback(self):
        old_encoding = util.get_encoding()
        try:
            urwid.set_encoding("utf-8")
            actual, rest = escape.process_keyqueue([0], more_available=False)
            self.assertEqual(["<0>"], actual)
            self.assertListEqual([], rest)
        finally:
            urwid.set_encoding(old_encoding)

    def test_ctrl_lowercase_range(self):
        # codes 8, 9, 10, 13 are intercepted earlier by _keyconv (backspace/tab/enter)
        for code in set(range(1, 27)) - {8, 9, 10, 13}:
            with self.subTest(code=code):
                actual, rest = escape.process_keyqueue([code], more_available=False)
                self.assertEqual([f"ctrl {chr(ord('a') + code - 1)}"], actual)
                self.assertListEqual([], rest)

    def test_ctrl_uppercase_range(self):
        for code in range(28, 32):
            with self.subTest(code=code):
                actual, rest = escape.process_keyqueue([code], more_available=False)
                self.assertEqual([f"ctrl {chr(ord('A') + code - 1)}"], actual)
                self.assertListEqual([], rest)

    def test_keyconv_lookup(self):
        for code, key in ((8, "backspace"), (9, "tab"), (10, "enter"), (13, "enter"), (127, "backspace")):
            with self.subTest(code=code):
                actual, rest = escape.process_keyqueue([code], more_available=False)
                self.assertEqual([key], actual)
                self.assertListEqual([], rest)


class KeyqueueTrieTest(unittest.TestCase):
    def test_init_rejects_dict_result(self):
        self.assertRaises(TypeError, escape.KeyqueueTrie, [("a", {})])

    def test_add_rejects_empty_sequence(self):
        trie = escape.KeyqueueTrie([])
        self.assertRaises(RuntimeError, trie.add, trie.data, "", "x")

    def test_add_prefix_of_existing_sequence_conflicts(self):
        # "ab" is added first, so "a" collides with the branch node it created
        trie = escape.KeyqueueTrie([("ab", "X")])
        self.assertRaises(RuntimeError, trie.add, trie.data, "a", "Y")

    def test_add_extension_of_existing_sequence_conflicts(self):
        # "a" is added first as a leaf, so "ab" collides with that leaf
        trie = escape.KeyqueueTrie([("a", "X")])
        self.assertRaises(ValueError, trie.add, trie.data, "ab", "Y")

    def test_read_cursor_position_empty_keys(self):
        with self.assertRaises(escape.MoreInputRequired):
            escape.input_trie.read_cursor_position([], more_available=True)
        self.assertIsNone(escape.input_trie.read_cursor_position([], more_available=False))

    def test_read_cursor_position_wrong_prefix(self):
        self.assertIsNone(escape.input_trie.read_cursor_position([ord("x")], more_available=False))

    def test_read_cursor_position_missing_y(self):
        # semicolon before any digit
        codes = [ord("["), ord(";"), ord("5"), ord("R")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_non_digit_y(self):
        codes = [ord("["), ord("x")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_leading_zero_y(self):
        codes = [ord("["), ord("0"), ord("1"), ord(";"), ord("5"), ord("R")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_truncated_after_y(self):
        codes = [ord("["), ord("5"), ord(";")]
        with self.assertRaises(escape.MoreInputRequired):
            escape.input_trie.read_cursor_position(codes, more_available=True)
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_non_digit_x(self):
        codes = [ord("["), ord("5"), ord(";"), ord("y")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_leading_zero_x(self):
        codes = [ord("["), ord("5"), ord(";"), ord("0"), ord("1"), ord("R")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_missing_x(self):
        # 'R' immediately after the semicolon, with no digit for x
        codes = [ord("["), ord("5"), ord(";"), ord("R")]
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_truncated_after_x_digits(self):
        codes = [ord("["), ord("5"), ord(";"), ord("3")]
        with self.assertRaises(escape.MoreInputRequired):
            escape.input_trie.read_cursor_position(codes, more_available=True)
        self.assertIsNone(escape.input_trie.read_cursor_position(codes, more_available=False))

    def test_read_cursor_position_success(self):
        codes = [ord("["), ord("5"), ord(";"), ord("3"), ord("R"), ord("z")]
        result = escape.input_trie.read_cursor_position(codes, more_available=False)
        self.assertEqual((("cursor position", 2, 4), [ord("z")]), result)


class OutputSequenceTest(unittest.TestCase):
    def test_set_cursor_position(self):
        self.assertEqual(f"{escape.ESC}[6;11H", escape.set_cursor_position(10, 5))
        self.assertRaises(TypeError, escape.set_cursor_position, "10", 5)
        self.assertRaises(TypeError, escape.set_cursor_position, 10, "5")

    def test_move_cursor_right(self):
        self.assertEqual("", escape.move_cursor_right(0))
        self.assertEqual(f"{escape.ESC}[3C", escape.move_cursor_right(3))

    def test_move_cursor_up(self):
        self.assertEqual("", escape.move_cursor_up(0))
        self.assertEqual(f"{escape.ESC}[3A", escape.move_cursor_up(3))

    def test_move_cursor_down(self):
        self.assertEqual("", escape.move_cursor_down(0))
        self.assertEqual(f"{escape.ESC}[3B", escape.move_cursor_down(3))
