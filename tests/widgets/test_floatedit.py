import unittest
from decimal import Decimal
from itertools import product

from urwid.numedit import FloatEdit


class FloatEditNoPreservePrecicionTest(unittest.TestCase):
    def test(self):
        for v in ("1.01", "2.5", "300", "4.100", "5.001"):
            f = FloatEdit(preserve_significance=False)
            f.set_edit_text(v)
            print(f.value(), Decimal(v))
            self.assertEqual(Decimal(v), f.value())

    def test_int(self):
        corner_value = "1"  # just int
        f = FloatEdit(preserve_significance=False)
        f.set_edit_text(corner_value)
        self.assertEqual(Decimal(corner_value), f.value())

    def test_no_post_dot(self):
        corner_value = "1."  # forced float 1.0 with trimmed end
        f = FloatEdit(preserve_significance=False)
        f.set_edit_text(corner_value)
        self.assertEqual(Decimal(corner_value), f.value())


class FloatEditPreservePrecicionTest(unittest.TestCase):
    def test(self):
        for v, sig, sep in product(("1.010", "2.500", "300.000", "4.100", "5.001"), (0, 1, 2, 3), (".", ",")):
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
