from __future__ import annotations

import unittest
from decimal import Decimal
from itertools import product

from urwid.numedit import FloatEdit, IntegerEdit, NumEdit


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


class FloatEditNoPreservePrecicionTest(unittest.TestCase):
    def test(self):
        # "1" is just an int, and "1." a forced float 1.0 with a trimmed end
        for v in ("1.01", "2.5", "300", "4.100", "5.001", "1", "1."):
            with self.subTest(v):
                f = FloatEdit(preserve_significance=False)
                f.set_edit_text(v)
                print(f.value(), Decimal(v))
                self.assertEqual(Decimal(v), f.value())


class FloatEditPreservePrecicionTest(unittest.TestCase):
    def test(self):
        for v, sig, sep in product(("1.010", "2.500", "300.000", "4.100", "5.001"), (0, 1, 2, 3), (".", ",")):
            with self.subTest(v, significance=sig, separator=sep):
                precision_template = "0." + "0" * sig
                expected = Decimal(v).quantize(Decimal(precision_template))
                f = FloatEdit(
                    preserve_significance=True, default=precision_template.replace(".", sep), decimal_separator=sep
                )

                f.set_edit_text(v.replace(".", sep))
                self.assertEqual(expected, f.value(), f"{f.value()} != {expected} (significance={sig!r})")


class FloatEditDeprecatedArgumentsTest(unittest.TestCase):
    def test_camel_case_arguments_warn_and_keep_working(self):
        with self.assertWarns(DeprecationWarning):
            f = FloatEdit(default="0.00", preserveSignificance=True)
        f.set_edit_text("1.5")
        self.assertEqual(Decimal("1.50"), f.value())
        with self.assertWarns(DeprecationWarning):
            f = FloatEdit(decimalSeparator=",")
        f.set_edit_text("1,5")
        self.assertEqual(Decimal("1.5"), f.value())


class FloatEditDefaultSeparatorTest(unittest.TestCase):
    def test_defaults_use_the_configured_separator(self):
        for default in ("1,250", Decimal("1.250")):
            for preserve_significance in (False, True):
                with self.subTest(default=default, preserve_significance=preserve_significance):
                    edit = FloatEdit(
                        default=default, decimal_separator=",", preserve_significance=preserve_significance
                    )
                    self.assertEqual("1,250", edit.edit_text)
                    self.assertEqual(Decimal("1.250"), edit.value())
                    self.assertEqual(1.25, float(edit))
                    edit.set_edit_text("2,5")
                    self.assertEqual(
                        Decimal("2.500" if preserve_significance else "2.5").as_tuple(), edit.value().as_tuple()
                    )

    def test_string_defaults_reject_the_wrong_separator(self):
        for separator, default in ((",", "1.250"), (".", "1,250"), (",", "1.2,50")):
            for preserve_significance in (False, True):
                with (
                    self.subTest(separator=separator, default=default, preserve_significance=preserve_significance),
                    self.assertRaises(ValueError),
                ):
                    FloatEdit(default=default, decimal_separator=separator, preserve_significance=preserve_significance)

    def test_deprecated_separator_applies_to_default(self):
        with self.assertWarns(DeprecationWarning):
            edit = FloatEdit(default="1,25", decimalSeparator=",")
        self.assertEqual("1,25", edit.edit_text)
        self.assertEqual(Decimal("1.25"), edit.value())


class FloatEditDefaultValidationTest(unittest.TestCase):
    def test_exponent_string_default_uses_editable_characters(self):
        for default in ("1e5", Decimal("1E+5")):
            with self.subTest(default=default):
                edit = FloatEdit(default=default)

                self.assertEqual("100000", edit.edit_text)
                self.assertEqual(Decimal("100000"), edit.value())

    def test_non_finite_defaults_are_rejected(self):
        for default in ("inf", "-inf", "nan", Decimal("Infinity"), Decimal("NaN")):
            with self.subTest(default=default), self.assertRaises(ValueError):
                FloatEdit(default=default)

    def test_long_value_preserves_significance(self):
        edit = FloatEdit(default="1.0000", preserve_significance=True)
        edit.set_edit_text("123456789012345678901234567890")

        self.assertEqual(
            Decimal("123456789012345678901234567890.0000").as_tuple(),
            edit.value().as_tuple(),
        )


class NumEditLeadingZerosTest(unittest.TestCase):
    def test_lone_zero_is_kept(self):
        for edit in (IntegerEdit(), FloatEdit()):
            with self.subTest(widget=type(edit).__name__):
                edit.keypress((10,), "0")
                edit.keypress((10,), "0")
                self.assertEqual("0", edit.edit_text)
                self.assertEqual(Decimal(0), edit.value())

    def test_zero_default_is_kept(self):
        for edit in (IntegerEdit(default=0), FloatEdit(default="0")):
            with self.subTest(widget=type(edit).__name__):
                edit.keypress((10,), "end")
                self.assertEqual("0", edit.edit_text)
                self.assertEqual(Decimal(0), edit.value())

    def test_zero_before_decimal_separator_is_kept(self):
        for separator in (".", ","):
            with self.subTest(separator=separator):
                edit = FloatEdit(decimal_separator=separator)
                edit.keypress((10,), "0")
                edit.keypress((10,), separator)
                self.assertEqual(f"0{separator}", edit.edit_text)
                self.assertEqual(Decimal(0), edit.value())
                edit.keypress((10,), "5")
                self.assertEqual(f"0{separator}5", edit.edit_text)
                self.assertEqual(Decimal("0.5"), edit.value())

    def test_zeros_before_digits_are_trimmed(self):
        for edit, keys, expected in (
            (IntegerEdit(), "007", "7"),
            (FloatEdit(), "007", "7"),
            (NumEdit("0123456789ABCDEF", "", ""), "0f", "f"),
            (IntegerEdit(allow_negative=True), "-007", "-7"),
            (IntegerEdit(allow_negative=True), "-00", "-0"),
            (FloatEdit(allow_negative=True), "-00.5", "-0.5"),
        ):
            with self.subTest(widget=type(edit).__name__, keys=keys):
                for key in keys:
                    edit.keypress((10,), key)
                self.assertEqual(expected, edit.edit_text)

    def test_zeros_after_sign_are_trimmed_behind_the_cursor(self):
        edit = IntegerEdit(allow_negative=True)
        for key in "-007":
            edit.keypress((10,), key)
        self.assertEqual(("-7", 2), (edit.edit_text, edit.edit_pos))

        edit = IntegerEdit(default="-007", allow_negative=True)
        for key, expected in (("home", ("-007", 0)), ("right", ("-007", 1)), ("right", ("-07", 1))):
            with self.subTest(key=key, expected=expected):
                edit.keypress((10,), key)
                self.assertEqual(expected, (edit.edit_text, edit.edit_pos))


class FloatEditDecimalSeparatorInputTest(unittest.TestCase):
    def test_second_separator_is_refused(self):
        for separator in (".", ","):
            with self.subTest(separator=separator):
                edit = FloatEdit(decimal_separator=separator)
                for key in ("1", separator, "2"):
                    edit.keypress((10,), key)
                self.assertEqual(separator, edit.keypress((10,), separator))
                edit.keypress((10,), "home")
                self.assertEqual(separator, edit.keypress((10,), separator))
                self.assertEqual(f"1{separator}2", edit.edit_text)
                self.assertEqual(Decimal("1.2"), edit.value())


if __name__ == "__main__":
    unittest.main()
