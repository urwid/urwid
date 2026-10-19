from __future__ import annotations

import unittest

import urwid
import urwid.testing


class SolidFillTest(unittest.TestCase):
    def test_squish(self):
        urwid.testing.check_box_sizing(urwid.SolidFill())


if __name__ == "__main__":
    unittest.main()
