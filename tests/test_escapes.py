#!/usr/bin/python

"""Tests covering escape sequences processing"""

from __future__ import annotations

import unittest

from urwid.display import escape


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
