from __future__ import annotations

import string
import typing
import unittest

import urwid
from urwid.widget.scrollable import ScrollableError

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

    def test_selectable(self):
        widget = urwid.Scrollable(urwid.Text("hi"))
        self.assertTrue(widget.selectable())

    def test_render_pads_height_and_trims_width(self):
        """A fixed widget wider than the viewport but short enough to fit vertically is padded to the full height,
        has its scroll position reset, and is trimmed horizontally.
        """
        widget = urwid.Scrollable(urwid.BigText("12", urwid.HalfBlockHeavy6x5Font()))
        widget.set_scrollpos(3)
        size = (8, 10)
        canv = widget.render(size)

        self.assertEqual(0, widget.get_scrollpos())
        self.assertEqual(10, canv.rows())
        self.assertEqual(8, canv.cols())

    def test_set_scrollpos_negative_counts_from_bottom(self):
        content = urwid.Text("\n".join(string.ascii_letters))
        size = (5, 5)

        widget = urwid.Scrollable(content)
        widget.set_scrollpos(-3)
        canv = widget.render(size)

        reference = urwid.Scrollable(urwid.Text("\n".join(string.ascii_letters)))
        reference.set_scrollpos(45)
        reference_canv = reference.render(size)

        self.assertEqual(45, widget.get_scrollpos())
        self.assertEqual(reference_canv.decoded_text, canv.decoded_text)

    def test_cursor_hidden_when_scrolled_out_of_view(self):
        """Scrolling the cursor's row out of the visible canvas hides it (unrelated to automove_cursor)."""
        edit = urwid.Edit("", "\n".join(f"line{index}" for index in range(10)), multiline=True)
        edit.set_edit_pos(0)
        widget = urwid.Scrollable(edit)
        size = (10, 3)

        canv = widget.render(size, True)
        self.assertIsNotNone(canv.cursor)

        widget.set_scrollpos(5)
        canv = widget.render(size, True)
        self.assertIsNone(canv.cursor)

    def test_keypress_unhandled_returns_key(self):
        widget = urwid.Scrollable(urwid.Text("hello"))
        size = (10, 3)
        widget.render(size)

        self.assertEqual("x", widget.keypress(size, "x"))

    def test_keypress_forwarded_follows_cursor_out_of_view(self):
        """Keys are forwarded to a widget whose cursor is visible;
        the cursor-position-preservation logic in render()/keypress() (separate from automove_cursor)
        then scrolls to keep it in view.
        """
        edit = urwid.Edit("", "\n".join(f"line{index}" for index in range(20)), multiline=True)
        edit.set_edit_pos(0)
        widget = urwid.Scrollable(edit)
        size = (10, 3)

        canv = widget.render(size, True)
        self.assertEqual((0, 0), canv.cursor)

        for _ in range(3):
            self.assertIsNone(widget.keypress(size, "down"))
            widget.render(size, True)

        self.assertGreater(widget.get_scrollpos(), 0)
        self.assertEqual((0, 3), edit.get_cursor_coords((10,)))

        # Now move the cursor back up past the top of the current viewport: trim_top follows it up too.
        for _ in range(3):
            self.assertIsNone(widget.keypress(size, "up"))
            widget.render(size, True)

        self.assertEqual(0, widget.get_scrollpos())
        self.assertEqual((0, 0), edit.get_cursor_coords((10,)))

    def test_keypress_forwarded_without_get_cursor_coords(self):
        """force_forward_keypress works with a widget that has no get_cursor_coords method,
        and an unhandled forwarded key falls through to Scrollable's own scroll handling.
        """

        class NoCursorCoordsWidget:
            def sizing(self):
                return frozenset((urwid.FLOW,))

            def selectable(self):
                return True

            def rows(self, size, focus=False):
                return 20

            def render(self, size, focus=False):
                return urwid.SolidCanvas(" ", size[0], 20)

            def keypress(self, size, key):
                return key  # never handles anything

        widget = urwid.Scrollable(NoCursorCoordsWidget(), force_forward_keypress=True)
        size = (10, 3)

        widget.render(size, True)
        self.assertEqual(0, widget.get_scrollpos())

        widget.keypress(size, "down")
        widget.render(size, True)

        self.assertGreater(widget.get_scrollpos(), 0)

    def test_mouse_event_without_ow_support(self):
        class NoMouseWidget:
            def sizing(self):
                return frozenset((urwid.FLOW,))

            def selectable(self):
                return False

            def render(self, size, focus=False):
                return urwid.SolidCanvas(" ", size[0], 1)

            def keypress(self, size, key):
                return key

        widget = urwid.Scrollable(NoMouseWidget())

        self.assertFalse(widget.mouse_event((10, 3), "mouse press", 1, 0, 0, False))

    def test_get_original_widget_size_raises_for_unsupported_sizing(self):
        class MutableSizingText(urwid.Text):
            forced_sizing: frozenset | None = None

            def sizing(self):
                if self.forced_sizing is not None:
                    return self.forced_sizing
                return super().sizing()

        inner = MutableSizingText("hi")
        widget = urwid.Scrollable(inner)
        inner.forced_sizing = frozenset()

        with self.assertRaises(ScrollableError):
            widget.render((10, 3))

    def test_rows_max_raises_for_unsupported_sizing(self):
        # sizing() is queried twice inside rows_max(): once (indirectly, via _get_original_widget_size())
        # to compute ow_size, and again to pick the FIXED/FLOW branch. Reporting FLOW for the first two
        # calls (construction, then the ow_size lookup) and nothing for the third exercises the `else`
        # branch inside rows_max() itself, rather than the one in _get_original_widget_size().
        class TwoStageSizingText(urwid.Text):
            def __init__(self, markup):
                super().__init__(markup)
                self.calls = 0

            def sizing(self):
                self.calls += 1
                if self.calls <= 2:
                    return frozenset((urwid.FLOW,))
                return frozenset()

        inner = TwoStageSizingText("hi")
        widget = urwid.Scrollable(inner)

        with self.assertRaises(ScrollableError):
            widget.rows_max((10, 3))

    def test_rows_max_flow_widget(self):
        # Edit is FLOW-only (unlike Text, which is also FIXED), so this exercises the
        # `Sizing.FLOW in sizing` branch of rows_max() rather than the `Sizing.FIXED` one.
        widget = urwid.Scrollable(urwid.Edit("", "a\nb\nc", multiline=True))

        self.assertEqual(3, widget.rows_max((10, 2)))
        self.assertEqual(3, widget.rows_max())  # cached value, no size given


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

    def test_selectable(self):
        widget = urwid.ScrollBar(urwid.Scrollable(urwid.Text("hi")))
        self.assertTrue(widget.selectable())

    def test_scrollbar_side_property(self):
        widget = urwid.ScrollBar(urwid.Scrollable(urwid.Text("hi")))
        self.assertEqual("right", widget.scrollbar_side)

        widget.scrollbar_side = "left"
        self.assertEqual("left", widget.scrollbar_side)

        with self.assertRaises(ValueError):
            widget.scrollbar_side = "top"

    def test_scrolling_base_widget_missing(self):
        widget = urwid.ScrollBar(urwid.Scrollable(urwid.Text("hi")))
        widget.original_widget = urwid.Text("hi")  # no longer wraps anything SupportsScroll-compatible

        with self.assertRaises(ScrollableError):
            _ = widget.scrolling_base_widget

    def test_mouse_click_scrollbar_zero_thumb_travel(self):
        """When the thumb fills the whole trough, any click maps to position 0."""
        content = urwid.Text("a\nb\nc")
        widget = urwid.ScrollBar(urwid.Scrollable(content))
        scrollable = widget.original_widget
        size = (5, 1)

        scrollable.set_scrollpos(1)
        widget.render(size)
        layout = widget._scrollbar_layout(size, False)
        self.assertEqual(0, size[1] - layout.thumb_height)

        self.assertTrue(widget.mouse_event(size, "mouse press", 1, size[0] - 1, 0, False))
        self.assertEqual(0, scrollable.get_scrollpos())

    def test_mouse_wheel_on_scrollbar_column_still_scrolls(self):
        """A wheel event landing on the scrollbar's own column still scrolls the content."""
        content = urwid.Text("\n".join(string.ascii_letters))
        widget = urwid.ScrollBar(urwid.Scrollable(content))
        scrollable = widget.original_widget
        size = (5, 5)
        scrollbar_col = size[0] - 1

        scrollable.set_scrollpos(5)
        widget.render(size)

        self.assertTrue(widget.mouse_event(size, "mouse press", 4, scrollbar_col, 0, False))
        self.assertEqual(4, scrollable.get_scrollpos())

        self.assertTrue(widget.mouse_event(size, "mouse press", 5, scrollbar_col, 0, False))
        self.assertEqual(5, scrollable.get_scrollpos())

    def test_scrollbar_layout_relative_scroll_all_visible_falls_back_to_absolute(self):
        """When relative scrolling reports every row visible, the absolute geometry is still computed."""

        class RelativeScrollFake(urwid.Widget):
            _sizing = frozenset((urwid.BOX,))

            def __init__(self, length, visible_amount, pos, rows_max_value):
                self._length = length
                self._visible_amount = visible_amount
                self._pos = pos
                self._rows_max_value = rows_max_value

            def sizing(self):
                return self._sizing

            def selectable(self):
                return False

            def render(self, size, focus=False):
                return urwid.SolidCanvas(" ", size[0], size[1])

            def __len__(self):
                return self._length

            def require_relative_scroll(self, size, focus=False):
                return True

            def get_first_visible_pos(self, size, focus=False):
                return self._pos

            def get_visible_amount(self, size, focus=False):
                return self._visible_amount

            def get_scrollpos(self, size=None, focus=False):
                return self._pos

            def set_scrollpos(self, position):
                self._pos = position

            def rows_max(self, size=None, focus=False):
                return self._rows_max_value

        fake = RelativeScrollFake(length=5, visible_amount=5, pos=0, rows_max_value=10)
        widget = urwid.ScrollBar(fake)

        layout = widget._scrollbar_layout((10, 5), False)

        self.assertIsNotNone(layout)
        self.assertEqual(5, layout.posmax)
        self.assertEqual(2, layout.thumb_height)


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

    def test_shade_symbols_around_listbox(self) -> None:
        """Thumb/trough characters used by list windows."""
        widget = urwid.ScrollBar(
            urwid.ListBox(urwid.SimpleListWalker([urwid.Text(f"item {idx}") for idx in range(6)])),
            thumb_char=urwid.ScrollBar.Symbols.DARK_SHADE,
            trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
        )

        self.assertEqual("▓", urwid.ScrollBar.Symbols.DARK_SHADE)
        self.assertEqual("░", urwid.ScrollBar.Symbols.LITE_SHADE)
        self.assertEqual(
            (
                "item 0 ▓",
                "item 1 ▓",
                "item 2 ░",
            ),
            widget.render((8, 3)).decoded_text,
        )


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
