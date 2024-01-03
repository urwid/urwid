from __future__ import annotations

import unittest


class TestMovedImports(unittest.TestCase):
    def test_moved_imports_direct(self) -> None:
        with self.assertWarns(DeprecationWarning):
            from urwid import web_display

        from urwid.display import web

        self.assertIs(web, web_display)

    def test_moved_imports_nested(self) -> None:
        from urwid.display import html_fragment
        from urwid.html_fragment import HtmlGenerator

        self.assertIs(html_fragment.HtmlGenerator, HtmlGenerator)
