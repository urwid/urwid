from __future__ import annotations

import gc
import sys
import unittest
import weakref

import urwid

COLOURS = ("red", "green", "blue")


def numbers(count: int) -> list[str]:
    return [f"n{index:02d}" for index in range(count)]


def screen(target: urwid.PopUpTarget, size: tuple[int, int]) -> list[str]:
    return [line.decode() for line in target.render(size, focus=True).text]


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

    def test_selected_out_of_range(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        with self.assertRaises(IndexError):
            drop_down.selected = 3
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
        rows = screen(target, (7, 6))

        self.assertEqual(["green v", "red    ", "green  ", "blue   "], rows[:4])
        self.assertEqual((0, 2), target.render((7, 6), focus=True).cursor)

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
        self.assertEqual("blue  v", screen(target, (7, 6))[0])

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

    def test_other_mouse_buttons_do_not_open(self) -> None:
        drop_down = urwid.DropDown(COLOURS)
        self.assertFalse(drop_down.mouse_event((7,), "mouse press", 3, 0, 0, True))
        self.assertIsNone(drop_down._pop_up_widget)

    def test_long_list_scrolls_with_the_selected_option_visible(self) -> None:
        drop_down = urwid.DropDown(numbers(20), selected=15, max_visible_items=5)
        target = drop_down_at_row(drop_down, 0)
        target.keypress((6, 10), "enter")

        rows = screen(target, (6, 10))
        list_rows = rows[1:6]

        self.assertEqual("", rows[6].strip())
        self.assertIn("n15  ", [row[:5] for row in list_rows])
        # The scroll bar takes the last column of the list.
        self.assertNotEqual({" "}, {row[-1] for row in list_rows})

    def test_list_opens_above_when_it_does_not_fit_below(self) -> None:
        drop_down = urwid.DropDown(numbers(4))
        target = drop_down_at_row(drop_down, 7)
        target.keypress((5, 9), "enter")

        rows = screen(target, (5, 9))

        self.assertEqual(["n00  ", "n01  ", "n02  ", "n03  "], rows[3:7])
        self.assertEqual("n00 v", rows[7])

    def test_list_takes_the_larger_side_when_it_fits_on_neither(self) -> None:
        drop_down = urwid.DropDown(numbers(10))
        target = drop_down_at_row(drop_down, 3)
        target.keypress((5, 8), "enter")

        rows = screen(target, (5, 8))

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
