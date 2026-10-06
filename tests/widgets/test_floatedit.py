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
            f = FloatEdit(preserve_significance=True, default=precision_template, decimal_separator=sep)

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
