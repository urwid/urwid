from __future__ import annotations

import gc
import sys
import unittest
import weakref

import urwid
import urwid.testing

COLOURS = ("red", "green", "blue")
# A separator after "any", and "large" disabled.
SIZES = ("any", None, "small", "large")


def numbers(count: int) -> list[str]:
    return [f"n{index:02d}" for index in range(count)]


def drop_down_at_row(drop_down: urwid.DropDown, row: int) -> urwid.PopUpTarget:
    """Return a target with `drop_down` on screen row `row`, below `row` rows of filler."""
    pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("."), row), drop_down], focus_item=1) if row else drop_down
    return urwid.PopUpTarget(urwid.Filler(pile, valign="top"))


class DropDownConstructionTest(unittest.TestCase):
    def test_invalid_arguments(self) -> None:
        for description, args, kwargs, error in (
            ("no options", ([],), {}, ValueError),
            ("no visible items", (COLOURS,), {"max_visible_items": 0}, ValueError),
            ("selected past the end", (COLOURS,), {"selected": 3}, IndexError),
            ("negative selected", (COLOURS,), {"selected": -1}, IndexError),
            ("multi-line option with a border", (["a\nb", "c"],), {"border": True}, ValueError),
            ("unknown scroll bar side", (COLOURS,), {"scrollbar_side": "top"}, ValueError),
            ("end markers not a pair", (COLOURS,), {"scrollbar_end_markers": ("^",)}, ValueError),
            ("unknown scroll bar option", (COLOURS,), {"scrollbar_visible": True}, TypeError),
            ("selected separator", (SIZES,), {"selected": 1}, ValueError),
            ("selected disabled option", (SIZES,), {"selected": 3, "disabled": {3}}, ValueError),
            ("disabled separator", (SIZES,), {"disabled": {1}}, ValueError),
            ("disabled past the end", (SIZES,), {"disabled": {4}}, IndexError),
            ("nothing choosable", ([None, "a"],), {"disabled": {1}}, ValueError),
            ("unhashable disabled map", (COLOURS,), {"disabled_map": {"a": []}}, urwid.AttrMapError),
        ):
            with self.subTest(description), self.assertRaises(error):
                urwid.DropDown(*args, **kwargs)

    def test_selected_and_options(self) -> None:
        drop_down = urwid.DropDown(iter(COLOURS), selected=2)
        self.assertEqual(COLOURS, drop_down.options)
        self.assertEqual(2, drop_down.selected)

    def test_fixed_size_is_the_widest_option(self) -> None:
        drop_down = urwid.DropDown(["a", "longest", "b"])
        self.assertEqual((9, 1), drop_down.pack())
        self.assertEqual([b"a       v"], drop_down.render(()).text)

    def test_default_selected_is_the_first_choosable_option(self) -> None:
        drop_down = urwid.DropDown([None, "off", "on"], disabled={1})
        self.assertEqual(2, drop_down.selected)
        self.assertEqual(frozenset({1}), drop_down.disabled)
        self.assertEqual([b"on  v"], drop_down.render(()).text)

    def test_flow_render_clips_the_label(self) -> None:
        drop_down = urwid.DropDown(["a very long option"])
        self.assertEqual((8, 1), drop_down.pack((8,)))
        self.assertEqual(1, len(drop_down.render((8,)).text))
        self.assertTrue(drop_down.render((8,)).text[0].endswith(b" v"))


class DropDownSelectionTest(unittest.TestCase):
    def test_change_signal_sees_the_previous_value(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        seen = []
        urwid.connect_signal(drop_down, "change", lambda widget, index: seen.append((widget.selected, index)))

        drop_down.selected = 2
        drop_down.selected = 2  # no change, no signal

        self.assertEqual([(0, 2)], seen)
        self.assertEqual([b"blue  v"], drop_down.render(()).text)

    def test_postchange_signal_sees_the_new_value(self) -> None:
        """ "postchange" follows a change, with the previous index, once the label shows the new option."""
        drop_down = urwid.DropDown(COLOURS)
        seen = []
        urwid.connect_signal(
            drop_down,
            "postchange",
            lambda widget, previous: seen.append((widget.selected, previous, widget.render(()).text)),
        )

        drop_down.selected = 2
        drop_down.selected = 2  # no change, no signal
        drop_down.selected = 1

        self.assertEqual([(2, 0, [b"blue  v"]), (1, 2, [b"green v"])], seen)

    def test_selected_out_of_range(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        with self.assertRaises(IndexError):
            drop_down.selected = 3
        self.assertEqual(0, drop_down.selected)

    def test_selected_separator_or_disabled(self) -> None:
        drop_down = urwid.DropDown(SIZES, disabled={3})
        for index in (1, 3):
            with self.subTest(index=index), self.assertRaises(ValueError):
                drop_down.selected = index
        self.assertEqual(0, drop_down.selected)

    def test_other_keys_are_not_handled(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        self.assertEqual("down", drop_down.keypress((7,), "down"))
        self.assertIsNone(drop_down._pop_up_widget)


class DropDownListTest(unittest.TestCase):
    def test_open_shows_all_options_below_with_the_selected_focused(self) -> None:
        drop_down = urwid.DropDown(COLOURS, selected=1)
        target = drop_down_at_row(drop_down, 0)

        self.assertIsNone(target.keypress((7, 6), "enter"))
        rows = urwid.testing.render_text(target, (7, 6), focus=True)

        self.assertEqual(["green v", "red    ", "green  ", "blue   "], rows[:4])
        self.assertEqual((0, 2), target.render((7, 6), focus=True).cursor)

    def test_border(self) -> None:
        """A bordered list is boxed, and a list that scrolls has its scroll bar outside the box."""
        for description, options, expected in (
            # As without a border, the list is at least as wide as the drop-down.
            ("fits", COLOURS, ["red     v", "┌───────┐", "│red    │", "│green  │", "│blue   │", "└───────┘"]),
            (
                "scrolls",
                numbers(4),
                ["n00     v", "┌──────┐ ", "│n00   │█", "│n01   │█", "│n02   │ ", "└──────┘ "],
            ),
        ):
            with self.subTest(description):
                drop_down = urwid.DropDown(options, border=True, max_visible_items=3, attr_map="option")
                target = drop_down_at_row(drop_down, 0)
                target.keypress((9, 7), "enter")
                self.assertEqual(expected, urwid.testing.render_text(target, (9, 7), focus=True)[:6])
                # The box is drawn in the attribute of the options.
                corner = next(iter(list(target.render((9, 7), focus=True).content())[1]))
                self.assertEqual("option", corner[0])
                target.keypress((9, 7), "down")
                target.keypress((9, 7), "enter")
                self.assertEqual(1, drop_down.selected)

    def test_scroll_bar_options(self) -> None:
        """A wide bar on the left, outside the box when there is one."""
        for border, expected in (
            (True, ["n00      v", "  ┌──────┐", "##│n00   │", "##│n01   │", "..│n02   │", "  └──────┘"]),
            (False, ["n00      v", "##n00     ", "##n01     ", "..n02     ", "          ", "          "]),
        ):
            with self.subTest(border=border):
                drop_down = urwid.DropDown(
                    numbers(4),
                    border=border,
                    max_visible_items=3,
                    scrollbar_side="left",
                    scrollbar_width=2,
                    scrollbar_thumb_char="#",
                    scrollbar_trough_char=".",
                )
                target = drop_down_at_row(drop_down, 0)
                target.keypress((10, 7), "enter")
                self.assertEqual(expected, urwid.testing.render_text(target, (10, 7), focus=True)[:6])

    def test_scroll_bar_end_markers(self) -> None:
        """End markers take the first and last bar rows; the one whose end is visible is drawn dim."""
        drop_down = urwid.DropDown(
            numbers(6),
            border=True,
            max_visible_items=4,
            scrollbar_end_markers=("^", "v"),
            scrollbar_marker_dim_attr="dim",
        )
        target = drop_down_at_row(drop_down, 0)
        target.keypress((10, 8), "enter")
        self.assertEqual(
            ["┌───────┐ ", "│n00    │^", "│n01    │█", "│n02    │ ", "│n03    │v", "└───────┘ "],
            urwid.testing.render_text(target, (10, 8), focus=True)[1:7],
        )
        rows = list(target.render((10, 8), focus=True).content())
        self.assertEqual("dim", rows[2][-1][0])
        self.assertIsNone(rows[5][-1][0])

    def test_scroll_bar_click_scrolls_by_focus(self) -> None:
        """With scrollbar_scroll_by_focus, a click low on the bar scrolls the list; without it, it does nothing."""
        for scroll_by_focus, expected, handled in (
            (False, ["n00    █", "n01    █", "n02     ", "n03     ", "n04     "], False),
            (True, ["n05     ", "n06     ", "n07     ", "n08    █", "n09    █"], True),
        ):
            with self.subTest(scroll_by_focus=scroll_by_focus):
                drop_down = urwid.DropDown(numbers(10), max_visible_items=5, scrollbar_scroll_by_focus=scroll_by_focus)
                target = drop_down_at_row(drop_down, 0)
                target.keypress((8, 8), "enter")
                target.render((8, 8), focus=True)
                self.assertEqual(handled, target.mouse_event((8, 8), "mouse press", 1, 7, 5, True))
                self.assertEqual(expected, urwid.testing.render_text(target, (8, 8), focus=True)[1:6])

    def test_border_cursor_reaches_the_target(self) -> None:
        drop_down = urwid.DropDown(COLOURS, border=True, selected=1)
        target = drop_down_at_row(drop_down, 0)
        target.keypress((9, 7), "enter")
        self.assertEqual((1, 3), target.get_cursor_coords((9, 7)))
        self.assertEqual((1, 3), target.render((9, 7), focus=True).cursor)

    def test_border_list_cut_short_by_the_screen_gets_a_scroll_bar(self) -> None:
        drop_down = urwid.DropDown(numbers(8), border=True)
        target = drop_down_at_row(drop_down, 0)
        target.keypress((10, 5), "enter")
        self.assertEqual(
            ["n00      v", "┌───────┐ ", "│n00    │█", "│n01    │ ", "└───────┘ "],
            urwid.testing.render_text(target, (10, 5), focus=True),
        )

    def test_choose_with_keys(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        target = drop_down_at_row(drop_down, 0)
        seen = []
        urwid.connect_signal(drop_down, "change", lambda _widget, index: seen.append(index))

        target.keypress((7, 6), " ")
        target.keypress((7, 6), "down")
        target.keypress((7, 6), "down")
        target.keypress((7, 6), "enter")

        self.assertEqual([2], seen)
        self.assertIsNone(drop_down._pop_up_widget)
        self.assertEqual("blue  v", urwid.testing.render_text(target, (7, 6), focus=True)[0])

    def test_escape_closes_without_a_change(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        target = drop_down_at_row(drop_down, 0)

        target.keypress((7, 6), "enter")
        target.keypress((7, 6), "down")
        self.assertIsNone(target.keypress((7, 6), "esc"))

        self.assertIsNone(drop_down._pop_up_widget)
        self.assertEqual(0, drop_down.selected)

    def test_choose_with_the_mouse(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        target = drop_down_at_row(drop_down, 0)

        self.assertTrue(target.mouse_event((7, 6), "mouse press", 1, 0, 0, True))
        self.assertIsNotNone(drop_down._pop_up_widget)
        self.assertTrue(target.mouse_event((7, 6), "mouse press", 1, 1, 3, True))

        self.assertEqual(2, drop_down.selected)
        self.assertIsNone(drop_down._pop_up_widget)

    def test_click_outside_closes_without_a_change(self) -> None:
        """A click outside the open list closes it without a change, and does not reach the widget under it."""
        for description, col, row in (
            ("below the list", 0, 5),
            ("on the drop-down itself", 0, 0),
        ):
            with self.subTest(description):
                drop_down = urwid.DropDown(COLOURS)
                target = drop_down_at_row(drop_down, 0)
                target.mouse_event((7, 6), "mouse press", 1, 0, 0, True)
                self.assertIsNotNone(drop_down.pop_up_widget)

                self.assertTrue(target.mouse_event((7, 6), "mouse press", 1, col, row, True))

                self.assertIsNone(drop_down.pop_up_widget)
                self.assertEqual(0, drop_down.selected)

    def test_single_option_is_read_only(self) -> None:
        """A drop-down with one option is not selectable, opens no list and leaves the event unhandled."""
        drop_down = urwid.DropDown(["only"])
        target = drop_down_at_row(drop_down, 0)

        self.assertFalse(drop_down.selectable())
        self.assertTrue(urwid.DropDown(["one", "two"]).selectable())
        self.assertEqual("enter", target.keypress((6, 6), "enter"))
        self.assertFalse(target.mouse_event((6, 6), "mouse press", 1, 0, 0, True))

        self.assertIsNone(drop_down._pop_up_widget)

    def test_single_choosable_option_is_read_only(self) -> None:
        """A read-only drop-down is drawn with ``disabled_map``, and one with a choice is not."""
        read_only = urwid.DropDown(["only", None, "off"], disabled={2}, disabled_map="disabled")
        choice = urwid.DropDown(SIZES, disabled={3}, disabled_map="disabled")

        self.assertFalse(read_only.selectable())
        self.assertTrue(choice.selectable())
        for drop_down, expected in ((read_only, {"disabled"}), (choice, {None})):
            with self.subTest(selectable=drop_down.selectable()):
                content = drop_down.render(()).content()
                self.assertEqual(expected, {attr for row in content for attr, _cs, _text in row})

    def test_launcher_attributes(self) -> None:
        """The widget takes the list's maps unless the ``launcher_*`` maps override them."""
        for name, kwargs, focus, expected in (
            ("attr_map", {"attr_map": "option", "focus_map": "focus"}, False, {"option"}),
            ("focus_map", {"attr_map": "option", "focus_map": "focus"}, True, {"focus"}),
            ("focused without focus_map", {"attr_map": "option"}, True, {"option"}),
            ("override", {"attr_map": "option", "launcher_attr_map": "own"}, False, {"own"}),
            ("focused takes launcher_attr_map", {"launcher_attr_map": "own"}, True, {"own"}),
            ("focus override", {"focus_map": "focus", "launcher_focus_map": "own focus"}, True, {"own focus"}),
        ):
            with self.subTest(name):
                content = urwid.DropDown(SIZES, **kwargs).render((), focus=focus).content()
                self.assertEqual(expected, {attr for row in content for attr, _cs, _text in row})

        read_only = urwid.DropDown(
            ["only", None, "off"],
            disabled={2},
            disabled_map="disabled",
            launcher_disabled_map={None: "own disabled"},
        )
        content = read_only.render((), focus=True).content()
        self.assertEqual({"own disabled"}, {attr for row in content for attr, _cs, _text in row})

    def test_separator_and_disabled_option(self) -> None:
        """A separator and a disabled option are drawn in the list, and up and down skip them."""
        for description, border, expected in (
            ("plain", False, ["any    v", "any     ", "────────", "small   ", "large   "]),
            ("border", True, ["any    v", "┌──────┐", "│any   │", "├──────┤", "│small │", "│large │", "└──────┘"]),
        ):
            with self.subTest(description):
                drop_down = urwid.DropDown(SIZES, disabled={3}, border=border)
                target = drop_down_at_row(drop_down, 0)
                target.keypress((8, 7), "enter")
                self.assertEqual(expected, urwid.testing.render_text(target, (8, 7), focus=True)[: len(expected)])

                # Down passes the separator to "small", and stops there, before the disabled "large".
                target.keypress((8, 7), "down")
                target.keypress((8, 7), "down")
                target.keypress((8, 7), "enter")
                self.assertEqual(2, drop_down.selected)

    def test_home_and_end_skip_separators_and_disabled_options(self) -> None:
        """Home and End focus the first or last option that can be chosen, with the rows beyond it in view."""
        for border, top, bottom in (
            (False, ["───────█", "a      █", "b       "], ["b       ", "c      █", "───────█"]),
            (True, ["├─────┤█", "│a    │█", "│b    │ "], ["│b    │ ", "│c    │█", "├─────┤█"]),
        ):
            with self.subTest(border=border):
                drop_down = urwid.DropDown(
                    [None, "a", "b", "c", None], disabled={3}, border=border, max_visible_items=3
                )
                target = drop_down_at_row(drop_down, 0)
                target.keypress((8, 9), "enter")
                # The list starts below the drop-down row, after the top edge of the box when there is one.
                first = 2 if border else 1

                target.keypress((8, 9), "end")
                self.assertEqual(bottom, urwid.testing.render_text(target, (8, 9), focus=True)[first : first + 3])
                target.keypress((8, 9), "home")
                self.assertEqual(top, urwid.testing.render_text(target, (8, 9), focus=True)[first : first + 3])

                target.keypress((8, 9), "end")
                target.keypress((8, 9), "enter")
                self.assertEqual(2, drop_down.selected)

    def test_click_on_separator_or_disabled_option_does_nothing(self) -> None:
        # Rows of the separator and of the disabled option, without and with a border.
        for border, row in ((False, 2), (False, 4), (True, 3), (True, 5)):
            with self.subTest(border=border, row=row):
                drop_down = urwid.DropDown(SIZES, disabled={3}, border=border)
                target = drop_down_at_row(drop_down, 0)
                target.keypress((7, 6), "enter")

                target.mouse_event((7, 6), "mouse press", 1, 1, row, True)

                self.assertIsNotNone(drop_down.pop_up_widget)
                self.assertEqual(0, drop_down.selected)

    def test_disabled_option_attribute(self) -> None:
        drop_down = urwid.DropDown(SIZES, disabled={3}, attr_map="option", disabled_map="disabled")
        target = drop_down_at_row(drop_down, 0)
        target.keypress((7, 6), "enter")

        content = list(target.render((7, 6), focus=True).content())

        # The disabled attribute is layered over the attribute of the options, as for an AttrMap inside another.
        self.assertEqual(
            [["option"], [urwid.LayeredAttr("disabled", "option")]],
            [[attr for attr, _cs, _text in row] for row in content[3:5]],
        )

    def test_other_mouse_buttons_do_not_open(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        self.assertFalse(drop_down.mouse_event((7,), "mouse press", 3, 0, 0, True))
        self.assertIsNone(drop_down._pop_up_widget)

    def test_long_list_scrolls_with_the_selected_option_visible(self) -> None:
        """The list opens on the selected option, below the options before it when they fit and centred otherwise."""
        for selected, first in ((3, 0), (15, 13)):
            with self.subTest(selected=selected):
                drop_down = urwid.DropDown(numbers(20), selected=selected, max_visible_items=5)
                target = drop_down_at_row(drop_down, 0)
                target.keypress((6, 10), "enter")

                rows = urwid.testing.render_text(target, (6, 10), focus=True)
                list_rows = rows[1:6]

                self.assertEqual("", rows[6].strip())
                expected = [f"n{number:02}  " for number in range(first, first + 5)]
                self.assertEqual(expected, [row[:5] for row in list_rows])
                # The scroll bar takes the last column of the list.
                self.assertNotEqual({" "}, {row[-1] for row in list_rows})

    def test_list_opens_above_when_it_does_not_fit_below(self) -> None:
        drop_down = urwid.DropDown(numbers(4))
        target = drop_down_at_row(drop_down, 7)
        target.keypress((5, 9), "enter")

        rows = urwid.testing.render_text(target, (5, 9), focus=True)

        self.assertEqual(["n00  ", "n01  ", "n02  ", "n03  "], rows[3:7])
        self.assertEqual("n00 v", rows[7])

    def test_list_takes_the_larger_side_when_it_fits_on_neither(self) -> None:
        drop_down = urwid.DropDown(numbers(10))
        target = drop_down_at_row(drop_down, 3)
        target.keypress((5, 8), "enter")

        rows = urwid.testing.render_text(target, (5, 8), focus=True)

        self.assertEqual("n00 v", rows[3])
        self.assertEqual(["n00", "n01", "n02", "n03"], [row[:3] for row in rows[4:]])
        self.assertEqual("...", rows[0][:3])

    def test_option_attributes(self) -> None:
        drop_down = urwid.DropDown(COLOURS, selected=1, attr_map="option", focus_map="focused")
        target = drop_down_at_row(drop_down, 0)
        target.keypress((7, 6), "enter")

        content = list(target.render((7, 6), focus=True).content())

        self.assertEqual(
            [["option"], ["focused"], ["option"]], [[attr for attr, _cs, _text in row] for row in content[1:4]]
        )

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing the widget")
    def test_open_list_does_not_keep_the_drop_down_alive(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        drop_down.open_pop_up()
        ref = weakref.ref(drop_down)

        gc.disable()
        try:
            del drop_down
            self.assertIsNone(ref())
        finally:
            gc.enable()


if __name__ == "__main__":
    unittest.main()
