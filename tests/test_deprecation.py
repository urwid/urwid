from __future__ import annotations

import unittest

import urwid
from urwid import _deprecation


class NotAWidget:
    """An object that does not implement the Widget API."""


class WarnTest(unittest.TestCase):
    def test_message_names_the_removal_release(self) -> None:
        with self.assertWarns(DeprecationWarning) as ctx:
            _deprecation.warn("Old is deprecated. Use New instead.", since="1.0", removed_in="3.0")
        self.assertEqual(
            "Old is deprecated. Use New instead. Deprecated since urwid 1.0, will be removed in version 3.0.",
            str(ctx.warning),
        )

    def test_message_without_removal_release(self) -> None:
        with self.assertWarns(DeprecationWarning) as ctx:
            _deprecation.warn("Old is deprecated.", since="1.0", removed_in=None)
        self.assertEqual("Old is deprecated. Deprecated since urwid 1.0.", str(ctx.warning))

    def test_attributed_to_the_caller(self) -> None:
        with self.assertWarns(DeprecationWarning) as ctx:
            _deprecation.warn("Old is deprecated.", since="1.0", removed_in=None)
        self.assertEqual(__file__, ctx.filename)

    def test_attributed_past_nested_urwid_frames(self) -> None:
        # Padding.__init__ passes the object to WidgetDecoration.__init__, which warns two urwid frames deep.
        with self.assertWarns(DeprecationWarning) as ctx:
            urwid.Padding(NotAWidget())  # type: ignore[arg-type]
        self.assertEqual(__file__, ctx.filename)
