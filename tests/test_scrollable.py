from __future__ import annotations

import string
import unittest

import urwid

LGPL_HEADER = """
Copyright (C) <year>  <name of author>

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2.1 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
"""


class TestScrollable(unittest.TestCase):
    def test_basic(self):
        """Test basic init and scroll."""
        long_content = urwid.Text(LGPL_HEADER)
        reduced_size = (80, 5)
        content_size = long_content.pack()

        widget = urwid.Scrollable(long_content)
        self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())

        cropped_content_canvas = urwid.CompositeCanvas(long_content.render((reduced_size[0],)))
        cropped_content_canvas.trim_end(content_size[1] - reduced_size[1])
        top_decoded = cropped_content_canvas.decoded_text

        self.assertEqual(
            top_decoded,
            widget.render(reduced_size).decoded_text,
        )

        for key_1, key_2 in (("down", "up"), ("page down", "page up"), ("end", "home")):
            widget.keypress(reduced_size, key_1)

            self.assertNotEqual(top_decoded, widget.render(reduced_size).decoded_text)

            widget.keypress(reduced_size, key_2)

            self.assertEqual(top_decoded, widget.render(reduced_size).decoded_text)

    def test_negative(self):
        with self.assertRaises(ValueError):
            urwid.Scrollable(urwid.SolidFill(" "))


class TestScrollBarScrollable(unittest.TestCase):
    def test_basic(self):
        """Test basic init and scroll.

        Unlike `Scrollable`, `ScrollBar` can be also scrolled with a mouse wheel.
        """

        long_content = urwid.Text(LGPL_HEADER)
        reduced_size = (40, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(long_content))

        self.assertEqual(frozenset((urwid.BOX,)), widget.sizing())

        top_position_rendered = (
            "                                       █",
            "Copyright (C) <year>  <name of author>  ",
            "                                        ",
            "This library is free software; you can  ",
            "redistribute it and/or                  ",
        )
        pos_1_down_rendered = (
            "Copyright (C) <year>  <name of author>  ",
            "                                       █",
            "This library is free software; you can  ",
            "redistribute it and/or                  ",
            "modify it under the terms of the GNU    ",
        )

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "down")

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "page down")

        self.assertEqual(
            (
                "redistribute it and/or                  ",
                "modify it under the terms of the GNU   █",
                "Lesser General Public                   ",
                "License as published by the Free        ",
                "Software Foundation; either             ",
            ),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "page up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "end")

        self.assertEqual(
            (
                "not, write to the Free Software         ",
                "Foundation, Inc., 51 Franklin Street,   ",
                "Fifth Floor, Boston, MA  02110-1301     ",
                "USA                                     ",
                "                                       █",
            ),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "home")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False)

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False)

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

    def test_alt_symbols(self):
        long_content = urwid.Text(LGPL_HEADER)
        reduced_size = (40, 5)
        widget = urwid.ScrollBar(
            urwid.Scrollable(long_content),
            trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
        )

        self.assertEqual(
            (
                "                                       █",
                "Copyright (C) <year>  <name of author> ░",
                "                                       ░",
                "This library is free software; you can ░",
                "redistribute it and/or                 ░",
            ),
            widget.render(reduced_size).decoded_text,
        )

    def test_fixed(self):
        """Test with fixed wrapped widget."""
        widget = urwid.ScrollBar(
            urwid.Scrollable(urwid.BigText("1", urwid.HalfBlockHeavy6x5Font())),
            trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
            thumb_char=urwid.ScrollBar.Symbols.DARK_SHADE,
        )
        reduced_size = (8, 3)

        self.assertEqual(
            (
                " ▐█▌   ▓",
                " ▀█▌   ▓",
                "  █▌   ░",
            ),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "page down")

        self.assertEqual(
            (
                "  █▌   ░",
                "  █▌   ▓",
                " ███▌  ▓",
            ),
            widget.render(reduced_size).decoded_text,
        )

    def test_negative(self):
        with self.assertRaises(ValueError):
            urwid.ScrollBar(urwid.Text(" "))

        with self.assertRaises(TypeError):
            urwid.ScrollBar(urwid.SolidFill(" "))


class TestScrollBarListBox(unittest.TestCase):
    def test_non_selectable(self):
        widget = urwid.ScrollBar(
            urwid.ListBox(urwid.SimpleListWalker(urwid.Text(line) for line in LGPL_HEADER.splitlines()))
        )

        reduced_size = (40, 5)

        top_position_rendered = (
            "                                       █",
            "Copyright (C) <year>  <name of author>  ",
            "                                        ",
            "This library is free software; you can  ",
            "redistribute it and/or                  ",
        )
        pos_1_down_rendered = (
            "Copyright (C) <year>  <name of author>  ",
            "                                       █",
            "This library is free software; you can  ",
            "redistribute it and/or                  ",
            "modify it under the terms of the GNU    ",
        )

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "down")

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "page down")

        self.assertEqual(
            (
                "modify it under the terms of the GNU    ",
                "Lesser General Public                  █",
                "License as published by the Free        ",
                "Software Foundation; either             ",
                "version 2.1 of the License, or (at your ",
            ),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "page up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "end")

        self.assertEqual(
            (
                "License along with this library; if     ",
                "not, write to the Free Software         ",
                "Foundation, Inc., 51 Franklin Street,   ",
                "Fifth Floor, Boston, MA  02110-1301     ",
                "USA                                    █",
            ),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "home")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False)

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False)

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

    def test_large_non_selectable(self):
        top = urwid.Text("\n".join(string.ascii_letters))
        bottom = urwid.Text("\n".join(string.digits))
        widget = urwid.ScrollBar(urwid.ListBox(urwid.SimpleListWalker((top, bottom))))

        reduced_size = (3, 5)

        top_position_rendered = ("a █", "b  ", "c  ", "d  ", "e  ")
        pos_1_down_rendered = ("b  ", "c █", "d  ", "e  ", "f  ")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "down")

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "page down")

        self.assertEqual(
            ("f  ", "g █", "h  ", "i  ", "j  "),
            widget.render(reduced_size).decoded_text,
        )

        widget.keypress(reduced_size, "page up")

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False)

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False)

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

    def test_large_selectable(self):
        """Input is handled by LineBox and wrapped widgets."""
        top = urwid.Edit("\n".join(string.ascii_letters))
        bottom = urwid.IntEdit("\n".join(string.digits))
        widget = urwid.ScrollBar(urwid.ListBox(urwid.SimpleListWalker((top, bottom))))

        reduced_size = (3, 10)

        top_position_rendered = ("a █", "b █", "c  ", "d  ", "e  ", "f  ", "g  ", "h  ", "i  ", "j  ")
        pos_1_down_rendered = ("0  ", "1  ", "2  ", "3  ", "4  ", "5  ", "6  ", "7  ", "8 █", "9 █")

        self.assertEqual((top_position_rendered), widget.render(reduced_size).decoded_text)

        widget.keypress(reduced_size, "down")

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)
