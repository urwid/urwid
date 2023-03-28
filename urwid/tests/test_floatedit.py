import unittest
from urwid.numedit import FloatEdit
from decimal import Decimal, getcontext
from itertools import product
class FloatEditNoPreservePrecicionTest(unittest.TestCase):
    def test(self):
        for v in ('1.01', '2.5', '300', '4.100', '5.001'):
            f = FloatEdit(preserveSignificance=False)
            f.set_edit_text(v)
            print(f.value(), Decimal(v))
            assert f.value() == Decimal(v), f'{f.value()} != {Decimal(v)}'

class FloatEditPreservePrecicionTest(unittest.TestCase):

    def test(self):
        for v, sig, sep in product(('1.010', '2.500', '300.000', '4.100', '5.001'), (1, 2, 3), ('.', ',')):
            f = FloatEdit(preserveSignificance=True, default='0.' + '0'*sig, decimalSeparator=sep)
            f.set_edit_text(v.replace('.', sep))
            getcontext().prec = sig+1
            print(f.value(), Decimal(v))
            assert str(f.value()) == str(Decimal(v) * 1), f'{str(f.value())} != {str(Decimal(v)*1)} (significance={sig})'
