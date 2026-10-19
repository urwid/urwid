from __future__ import annotations

import unittest

import urwid
from tests.util import wstest


class SolidFillTest(unittest.TestCase):
    def test_squish(self):
        wstest(urwid.SolidFill())


if __name__ == "__main__":
    unittest.main()
