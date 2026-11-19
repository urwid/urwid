from __future__ import annotations

import typing
import unittest

import urwid
import urwid.testing
from tests.util import assert_attribute_redraws


class SolidFillTest(unittest.TestCase):
    def test_layout_attributes_invalidate(self) -> None:
        """Setting a layout attribute of a rendered ``SolidFill`` redraws it."""

        def make(**kwargs: typing.Any) -> urwid.SolidFill:
            return urwid.SolidFill(**{"fill_char": "x", **kwargs})

        assert_attribute_redraws(self, make, (2, 2), "fill_char", "y")

    def test_squish(self):
        urwid.testing.check_box_sizing(urwid.SolidFill())


if __name__ == "__main__":
    unittest.main()
