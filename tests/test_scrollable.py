from __future__ import annotations

import string
import typing
import unittest

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

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

        long_content_canvas = long_content.render((reduced_size[0],))
        cropped_content_canvas = urwid.CompositeCanvas(long_content_canvas)
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

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False))

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False))

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

    def test_mouse_left_click_scrollbar(self):
        """Left click on the rendered scrollbar jumps to the clicked position."""
        content = urwid.Text("\n".join(string.ascii_letters))  # 52 single-char lines
        reduced_size = (3, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(content))
        scrollable = widget.original_widget
        scrollbar_col = reduced_size[0] - 1  # right side scrollbar

        self.assertEqual(0, scrollable.get_scrollpos())

        # posmax == 52 - 5 == 47, thumb_height == 1, thumb travel == 5 - 1 == 4.
        # Clicking the bottom row moves past the end and is clamped to posmax.
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, scrollbar_col, 4, False))
        self.assertEqual(47, scrollable.get_scrollpos())

        # Clicking the top row scrolls back to the top.
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, scrollbar_col, 0, False))
        self.assertEqual(0, scrollable.get_scrollpos())

        # Intermediate rows map proportionally: round(row * posmax / travel).
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, scrollbar_col, 1, False))
        self.assertEqual(12, scrollable.get_scrollpos())

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, scrollbar_col, 3, False))
        self.assertEqual(35, scrollable.get_scrollpos())

    def test_mouse_left_click_content_ignored(self):
        """Left click outside of the scrollbar columns does not scroll."""
        content = urwid.Text("\n".join(string.ascii_letters))
        reduced_size = (3, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(content))
        scrollable = widget.original_widget

        self.assertEqual(0, scrollable.get_scrollpos())

        # Column 0 belongs to the wrapped content, not the scrollbar.
        self.assertFalse(widget.mouse_event(reduced_size, "mouse press", 1, 0, 4, False))
        self.assertEqual(0, scrollable.get_scrollpos())

    def test_mouse_left_click_left_side_scrollbar(self):
        """Left click detection honours a left-aligned scrollbar."""
        content = urwid.Text("\n".join(string.ascii_letters))
        reduced_size = (3, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(content), side="left")
        scrollable = widget.original_widget

        self.assertEqual(0, scrollable.get_scrollpos())

        # The scrollbar occupies column 0 when aligned to the left.
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, 0, 4, False))
        self.assertEqual(47, scrollable.get_scrollpos())

        # A click on the content columns is ignored.
        self.assertFalse(widget.mouse_event(reduced_size, "mouse press", 1, 1, 0, False))
        self.assertEqual(47, scrollable.get_scrollpos())

    def test_mouse_left_click_without_scrollbar(self):
        """Without a rendered scrollbar a left click is not handled."""
        content = urwid.Text("a\nb")  # fits into the available height
        reduced_size = (3, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(content))
        scrollable = widget.original_widget

        self.assertFalse(widget.mouse_event(reduced_size, "mouse press", 1, 2, 2, False))
        self.assertEqual(0, scrollable.get_scrollpos())

    def test_mouse_left_click_scrollbar_over_selectable_content(self):
        """The scrollbar keeps its columns even when the wrapped widget consumes every click."""
        clicked: list[int] = []
        buttons = []
        for index in range(20):
            button = urwid.Button(f"b{index}")
            urwid.connect_signal(button, "click", lambda _button, idx=index: clicked.append(idx))
            buttons.append(button)

        reduced_size = (14, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(urwid.Pile(buttons)))
        scrollable = widget.original_widget
        scrollbar_col = reduced_size[0] - 1

        widget.render(reduced_size, True)
        self.assertEqual(0, scrollable.get_scrollpos())

        # Button.mouse_event answers any left press without looking at the column,
        # so delegating first would turn a click on the scrollbar into a button press.
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, scrollbar_col, 4, True))
        self.assertEqual([], clicked)
        self.assertEqual(15, scrollable.get_scrollpos())

        # A click on the content columns still reaches the buttons.
        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, 2, 0, True))
        self.assertEqual([15], clicked)

    def test_mouse_left_click_left_side_scrollbar_over_selectable_content(self):
        """The same protection applies to a left-aligned scrollbar."""
        clicked: list[int] = []
        buttons = []
        for index in range(20):
            button = urwid.Button(f"b{index}")
            urwid.connect_signal(button, "click", lambda _button, idx=index: clicked.append(idx))
            buttons.append(button)

        reduced_size = (14, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(urwid.Pile(buttons)), side="left")
        scrollable = widget.original_widget

        widget.render(reduced_size, True)
        self.assertEqual(0, scrollable.get_scrollpos())

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 1, 0, 4, True))
        self.assertEqual([], clicked)
        self.assertEqual(15, scrollable.get_scrollpos())

    def test_mouse_event_translates_column_for_left_side_scrollbar(self):
        """A left-aligned scrollbar shifts the wrapped widget, so the column has to be shifted back."""

        class ColumnRecorder(urwid.Text):
            def __init__(self, markup) -> None:
                super().__init__(markup)
                self.seen: list[tuple[int, int]] = []

            def selectable(self) -> bool:
                return True

            def mouse_event(self, size, event, button, col, row, focus) -> bool:
                self.seen.append((col, row))
                return False

        content = ColumnRecorder("\n".join(f"line{index}" for index in range(20)))
        reduced_size = (10, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(content), side="left")
        sb_width = widget.scrollbar_width

        widget.render(reduced_size, True)

        # Screen column ``sb_width`` is the first column the wrapped widget draws into.
        widget.mouse_event(reduced_size, "mouse press", 1, sb_width, 0, True)
        self.assertEqual([(0, 0)], content.seen)

        # The last screen column maps to the last column the wrapped widget owns.
        content.seen.clear()
        widget.mouse_event(reduced_size, "mouse press", 1, reduced_size[0] - 1, 0, True)
        self.assertEqual([(reduced_size[0] - 1 - sb_width, 0)], content.seen)

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

    def test_no_scrollbar(self):
        """If widget fit without scroll - no scrollbar needed"""
        widget = urwid.ScrollBar(
            urwid.Scrollable(urwid.BigText("1", urwid.HalfBlockHeavy6x5Font())),
            trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
            thumb_char=urwid.ScrollBar.Symbols.DARK_SHADE,
        )
        reduced_size = (8, 5)
        self.assertEqual(
            (
                " ▐█▌    ",
                " ▀█▌    ",
                "  █▌    ",
                "  █▌    ",
                " ███▌   ",
            ),
            widget.render(reduced_size).decoded_text,
        )


class TestScrollBarListBox(unittest.TestCase):
    def test_relative_non_selectable(self):
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

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False))

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False))

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)

    def test_empty(self):
        """Empty widget should be correctly rendered."""
        widget = urwid.ScrollBar(urwid.ListBox(urwid.SimpleListWalker(())))
        reduced_size = (10, 5)
        self.assertEqual(
            (
                "          ",
                "          ",
                "          ",
                "          ",
                "          ",
            ),
            widget.render(reduced_size).decoded_text,
        )

    def test_minimal_height(self):
        """If we have only 1 line render height and thumb position in the middle - do not render top."""
        widget = urwid.ScrollBar(
            urwid.ListBox(
                (
                    urwid.CheckBox("A"),
                    urwid.CheckBox("B"),
                    urwid.CheckBox("C"),
                )
            )
        )
        reduced_size = (7, 1)
        self.assertEqual(("[ ] A █",), widget.render(reduced_size).decoded_text)
        widget.keypress(reduced_size, "down")
        self.assertEqual(("[ ] B █",), widget.render(reduced_size).decoded_text)
        widget.keypress(reduced_size, "down")
        self.assertEqual(("[ ] C █",), widget.render(reduced_size).decoded_text)


def trivial_AttrMap(widget):
    return urwid.AttrMap(widget, {})


class TestScrollableAttrMap(unittest.TestCase):
    def test_basic(self):
        """Test basic init and scroll."""
        long_content = urwid.Text(LGPL_HEADER)
        reduced_size = (80, 5)
        content_size = long_content.pack()

        widget = urwid.Scrollable(trivial_AttrMap(long_content))
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
            urwid.Scrollable(trivial_AttrMap(urwid.SolidFill(" ")))


class TestScrollBarAttrMap(unittest.TestCase):
    def test_basic(self):
        """Test basic init and scroll.

        Unlike `Scrollable`, `ScrollBar` can be also scrolled with a mouse wheel.
        """

        long_content = urwid.Text(LGPL_HEADER)
        reduced_size = (40, 5)
        widget = urwid.ScrollBar(urwid.Scrollable(trivial_AttrMap(long_content)))

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

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False))

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False))

        self.assertEqual(top_position_rendered, widget.render(reduced_size).decoded_text)


class TestScrollBarListBoxAttrMap(unittest.TestCase):
    def test_relative_non_selectable(self):
        widget = urwid.ScrollBar(
            trivial_AttrMap(
                urwid.ListBox(urwid.SimpleListWalker(urwid.Text(line) for line in LGPL_HEADER.splitlines()))
            )
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

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False))

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False))

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

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 5, 1, 1, False))

        self.assertEqual(pos_1_down_rendered, widget.render(reduced_size).decoded_text)

        self.assertTrue(widget.mouse_event(reduced_size, "mouse press", 4, 1, 1, False))

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

    def test_hinted_len(self):
        class HintedWalker(urwid.ListWalker):
            def __init__(self, items: Iterable[str]) -> None:
                self.items: tuple[str] = tuple(items)
                self.focus = 0
                self.requested_numbers: set[int] = set()

            def __length_hint__(self) -> int:
                return len(self.items)

            def __getitem__(self, item: int) -> urwid.Text:
                self.requested_numbers.add(item)
                return urwid.Text(self.items[item])

            def set_focus(self, item: int) -> None:
                self.focus = item

            def next_position(self, position: int) -> int:
                if position + 1 < len(self.items):
                    return position + 1
                raise IndexError

            def prev_position(self, position: int) -> int:
                if position - 1 >= 0:
                    return position - 1
                raise IndexError

        widget = urwid.ScrollBar(urwid.ListBox(HintedWalker((f"Line {idx:02}") for idx in range(1, 51))))
        size = (10, 10)
        widget.original_widget.focus_position = 19
        self.assertEqual(
            (
                "Line 16   ",
                "Line 17   ",
                "Line 18   ",
                "Line 19  █",
                "Line 20  █",
                "Line 21   ",
                "Line 22   ",
                "Line 23   ",
                "Line 24   ",
                "Line 25   ",
            ),
            widget.render(size).decoded_text,
        )
        self.assertNotIn(
            30,
            widget.original_widget.body.requested_numbers,
            "Requested index out of range [0, last shown]. This means not relative scroll bar built.",
        )
