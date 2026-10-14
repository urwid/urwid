import unittest
from decimal import Decimal

from urwid.numedit import IntegerEdit


class IntegerEditNegativeDefaultTest(unittest.TestCase):
    def test_negative_string_defaults(self):
        for default, base, expected in (("-42", 10, -42), ("-101", 2, -5), ("-ff", 16, -255), ("-Z", 36, -35)):
            with self.subTest(default=default, base=base):
                edit = IntegerEdit(default=default, base=base, allow_negative=True)
                self.assertEqual(default, edit.edit_text)
                self.assertEqual(Decimal(expected), edit.value())
                self.assertEqual(expected, int(edit))
                edit.keypress((10,), "home")
                edit.keypress((10,), "delete")
                self.assertEqual(-expected, int(edit))

    def test_negative_string_defaults_require_opt_in(self):
        for default, base in (("-42", 10), ("-101", 2), ("-ff", 16)):
            with self.subTest(default=default, base=base), self.assertRaises(ValueError):
                IntegerEdit(default=default, base=base)

    def test_invalid_negative_defaults(self):
        for default, base in (("-", 10), ("--42", 10), ("4-2", 10), ("-102", 2), ("-FG", 16), ("+42", 10)):
            with self.subTest(default=default, base=base), self.assertRaises(ValueError):
                IntegerEdit(default=default, base=base, allow_negative=True)

    def test_nonnegative_defaults(self):
        for default, base, expected in (("42", 10, 42), ("101", 2, 5), ("ff", 16, 255), ("", 10, None)):
            with self.subTest(default=default, base=base):
                edit = IntegerEdit(default=default, base=base, allow_negative=True)
                self.assertEqual(default, edit.edit_text)
                self.assertEqual(expected, edit.value())
