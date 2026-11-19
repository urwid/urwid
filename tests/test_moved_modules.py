from __future__ import annotations

import sys
import unittest
import warnings

import urwid


class MovedModuleTest(unittest.TestCase):
    def test_attribute_access_warns(self) -> None:
        with self.assertWarns(DeprecationWarning):
            self.assertIs(urwid.display.escape.SHOW_CURSOR, urwid.escape.SHOW_CURSOR)

    def test_dunder_lookup_neither_warns_nor_resolves_the_alias(self) -> None:
        alias = urwid._MovedModuleWarn("urwid.test_alias", "urwid.display.raw")
        sys.modules["urwid.test_alias"] = alias
        self.addCleanup(sys.modules.pop, "urwid.test_alias", None)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertIsNone(getattr(alias, "__warningregistry__", None))

        self.assertIs(alias, sys.modules["urwid.test_alias"])
