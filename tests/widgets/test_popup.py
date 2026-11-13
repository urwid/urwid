from __future__ import annotations

import pickle
import unittest

import urwid
from urwid.command_map import Command


class ThingWithAPopUp(urwid.PopUpLauncher[urwid.SolidFill]):
    def __init__(self, *, close_on_menu: bool = False, close_on_click_outside: bool = False) -> None:
        super().__init__(
            urwid.SolidFill("x"),
            close_on_menu=close_on_menu,
            close_on_click_outside=close_on_click_outside,
        )
        self.launcher_sizes_seen: list[tuple[int, int] | None] = []

    def create_pop_up(self) -> urwid.Filler[urwid.Edit]:
        return urwid.Filler(urwid.Edit("", "pop up contents"))

    def get_pop_up_parameters(self) -> dict:
        self.launcher_sizes_seen.append(self.launcher_size)
        return {"left": 1, "top": 1, "overlay_width": 10, "overlay_height": 3}


class EmptyListPopUp(urwid.PopUpLauncher[urwid.SolidFill]):
    """Launcher whose pop-up is an empty container, which is false because its length is 0."""

    def __init__(self) -> None:
        super().__init__(urwid.SolidFill("x"))

    def create_pop_up(self) -> urwid.ListBox:
        return urwid.ListBox(urwid.SimpleFocusListWalker([]))

    def get_pop_up_parameters(self) -> dict:
        return {"left": 1, "top": 1, "overlay_width": 10, "overlay_height": 3}


class PopUpLauncherTest(unittest.TestCase):
    def test_open_close(self) -> None:
        launcher = ThingWithAPopUp()
        self.assertIsNone(launcher._pop_up_widget)

        launcher.open_pop_up()
        self.assertIsInstance(launcher._pop_up_widget, urwid.Filler)

        launcher.close_pop_up()
        self.assertIsNone(launcher._pop_up_widget)

    def test_pop_up_widget(self) -> None:
        """The open pop-up widget is readable, and None while the pop-up is closed."""
        launcher = ThingWithAPopUp()
        self.assertIsNone(launcher.pop_up_widget)

        launcher.open_pop_up()
        self.assertIsInstance(launcher.pop_up_widget, urwid.Filler)
        self.assertIs(launcher.pop_up_widget, launcher._pop_up_widget)

        launcher.close_pop_up()
        self.assertIsNone(launcher.pop_up_widget)

    def test_launcher_size(self) -> None:
        """The launcher size is that of the last render, set before the pop-up parameters are read."""
        launcher = ThingWithAPopUp()
        self.assertIsNone(launcher.launcher_size)

        launcher.render((4, 2))
        self.assertEqual((4, 2), launcher.launcher_size)

        # The size of this render is already set when the pop-up parameters are asked for.
        launcher.open_pop_up()
        launcher.render((6, 3))
        self.assertEqual([(6, 3)], launcher.launcher_sizes_seen)

    def test_render_without_pop_up(self) -> None:
        launcher = ThingWithAPopUp()
        canv = launcher.render((4, 2))
        self.assertEqual(canv.get_pop_up(), None)

    def test_render_with_pop_up(self) -> None:
        launcher = ThingWithAPopUp()
        launcher.open_pop_up()
        canv = launcher.render((4, 2))
        pop_up = canv.get_pop_up()
        self.assertIsNotNone(pop_up)
        left, top, (widget, overlay_width, overlay_height) = pop_up
        self.assertEqual((left, top), (1, 1))
        self.assertEqual((overlay_width, overlay_height), (10, 3))
        self.assertIs(widget, launcher._pop_up_widget)

    def test_render_with_empty_container_pop_up(self) -> None:
        """An open pop-up is attached to the canvas even when the widget itself is false."""
        launcher = EmptyListPopUp()
        launcher.open_pop_up()
        self.assertFalse(launcher.pop_up_widget)
        pop_up = launcher.render((4, 2)).get_pop_up()
        self.assertIsNotNone(pop_up)
        self.assertIs(pop_up[2][0], launcher.pop_up_widget)


class PopUpTargetTest(unittest.TestCase):
    def test_render_without_pop_up(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        canv = target.render((10, 5))
        self.assertEqual(b"".join(canv.text), b"x" * 10 * 5)
        self.assertIs(target._current_widget, launcher)
        self.assertEqual(target._pop_up_levels, [])

    def test_render_with_pop_up_creates_overlay(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()

        target.render((10, 5))
        self.assertIsInstance(target._current_widget, urwid.Overlay)
        self.assertEqual([w for w, _overlay in target._pop_up_levels], [launcher._pop_up_widget])

        # Render again with the same pop-up widget open: hits the
        # set_overlay_parameters() branch instead of creating a new Overlay.
        overlay = target._current_widget
        target.render((10, 5))
        self.assertIs(target._current_widget, overlay)

    def test_render_pop_up_closed_reverts_to_original(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        target.render((10, 5))
        self.assertIsInstance(target._current_widget, urwid.Overlay)

        launcher.close_pop_up()
        target.render((10, 5))
        self.assertIs(target._current_widget, launcher)
        self.assertEqual(target._pop_up_levels, [])

    def test_get_cursor_coords_no_support(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        with self.assertRaises(TypeError):
            target.get_cursor_coords((10, 5))

    def test_get_cursor_coords_with_pop_up(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        # Overlay delegates get_cursor_coords to its top widget when it has focus.
        self.assertIsInstance(target.get_cursor_coords((10, 5)), tuple)

    def test_get_pref_col_no_support(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        with self.assertRaises(TypeError):
            target.get_pref_col((10, 5))

    def test_get_pref_col_with_pop_up_still_unsupported(self) -> None:
        # Overlay itself has no get_pref_col method, so opening a pop-up
        # does not change the outcome.
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        with self.assertRaises(TypeError):
            target.get_pref_col((10, 5))

    def test_move_cursor_to_coords_no_support(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        with self.assertRaises(TypeError):
            target.move_cursor_to_coords((10, 5), 0, 0)

    def test_move_cursor_to_coords_with_pop_up_still_unsupported(self) -> None:
        # Overlay itself has no move_cursor_to_coords method, so opening a
        # pop-up does not change the outcome.
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        with self.assertRaises(TypeError):
            target.move_cursor_to_coords((10, 5), 0, 0)

    def test_menu_key_closes_pop_up(self) -> None:
        """With close_on_menu, a menu key the pop-up leaves unhandled closes it."""
        for description, close_on_menu, key, expected, still_open in (
            ("off by default: esc is returned unhandled", False, "esc", "esc", True),
            ("on: esc closes the pop-up", True, "esc", None, False),
            ("on: other unhandled keys are returned", True, "f1", "f1", True),
            ("on: keys the pop-up handles do not close it", True, "x", None, True),
        ):
            with self.subTest(description):
                launcher = ThingWithAPopUp(close_on_menu=close_on_menu)
                target = urwid.PopUpTarget(launcher)
                launcher.open_pop_up()

                self.assertEqual(expected, target.keypress((10, 5), key))
                self.assertEqual(still_open, launcher.pop_up_widget is not None)

    def test_menu_key_follows_the_launcher_command_map(self) -> None:
        """The menu key is looked up in the launcher's command map."""
        launcher = ThingWithAPopUp(close_on_menu=True)
        launcher._command_map = launcher._command_map.copy()
        del launcher._command_map["esc"]
        launcher._command_map["f10"] = Command.MENU
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()

        self.assertEqual("esc", target.keypress((10, 5), "esc"))
        self.assertIsNotNone(launcher.pop_up_widget)
        self.assertIsNone(target.keypress((10, 5), "f10"))
        self.assertIsNone(launcher.pop_up_widget)

    def test_click_outside_closes_pop_up(self) -> None:
        """With close_on_click_outside, a button 1-3 press outside the pop-up closes it and is handled."""
        # The pop-up covers columns 1-10 and rows 1-3 of the 20x6 target.
        for description, close_on_click_outside, event, button, col, row, expected, still_open in (
            ("off by default: the press is not handled", False, "mouse press", 1, 0, 0, False, True),
            ("on: button 1 above the pop-up", True, "mouse press", 1, 0, 0, True, False),
            ("on: button 3 below the pop-up", True, "mouse press", 3, 15, 5, True, False),
            ("on: a press inside goes to the pop-up", True, "mouse press", 1, 2, 2, True, True),
            ("on: the wheel does not close it", True, "mouse press", 4, 0, 0, False, True),
            ("on: a release does not close it", True, "mouse release", 0, 0, 0, False, True),
            ("on: a drag does not close it", True, "mouse drag", 1, 0, 0, False, True),
        ):
            with self.subTest(description):
                launcher = ThingWithAPopUp(close_on_click_outside=close_on_click_outside)
                target = urwid.PopUpTarget(launcher)
                launcher.open_pop_up()

                self.assertEqual(expected, bool(target.mouse_event((20, 6), event, button, col, row, True)))
                self.assertEqual(still_open, launcher.pop_up_widget is not None)

    def test_open_pop_up_pickles(self) -> None:
        """Pickle a target whose open pop-up closes on an outside click."""
        launcher = ThingWithAPopUp(close_on_click_outside=True)
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        target.render((20, 6))

        self.assertIsInstance(pickle.dumps(target), bytes)

    def test_keypress(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        self.assertEqual(target.keypress((10, 5), "q"), "q")

    def test_mouse_event(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        result = target.mouse_event((10, 5), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)

    def test_pack(self) -> None:
        launcher = ThingWithAPopUp()
        target = urwid.PopUpTarget(launcher)
        self.assertEqual(target.pack((10, 5)), (10, 5))


class AnchoredLauncher(urwid.PopUpLauncher[urwid.Text]):
    """A one-row launcher whose pop-up is anchored to it by default, so PopUpTarget keeps the pop-up off its row."""

    def __init__(
        self,
        pop_up_height: int | tuple[str, float] | str,
        *,
        pop_up_width: int | tuple[str, float] | str = 3,
        pop_up: urwid.Widget | None = None,
        anchor_height: int | None = 1,
        left: int | str = 0,
        top: int | str = 1,
        close_on_click_outside: bool = False,
    ) -> None:
        super().__init__(urwid.Text("L"), close_on_click_outside=close_on_click_outside)
        self.pop_up_height = pop_up_height
        self.pop_up_width = pop_up_width
        self.pop_up = pop_up
        self.anchor_height = anchor_height
        self.left = left
        self.top = top

    def create_pop_up(self) -> urwid.Widget:
        return urwid.SolidFill("p") if self.pop_up is None else self.pop_up

    def get_pop_up_parameters(self) -> dict:
        parameters = {
            "left": self.left,
            "top": self.top,
            "overlay_width": self.pop_up_width,
            "overlay_height": self.pop_up_height,
        }
        if self.anchor_height is not None:
            parameters["anchor_height"] = self.anchor_height
        return parameters


class NegativePopUpPositionTest(unittest.TestCase):
    def test_negative_position(self) -> None:
        """A pop-up may open left of and above its launcher; past a screen edge it is moved, or shrunk, to fit."""
        for description, launcher_row, left, top, pop_up_height, expected_col, expected_rows in (
            ("over the launcher", 2, 1, -1, 2, 1, range(1, 3)),
            ("past the top left screen corner", 0, -2, -1, 2, 0, range(2)),
            ("taller than the screen", 2, 0, -1, 9, 0, range(5)),
        ):
            with self.subTest(description):
                launcher = AnchoredLauncher(pop_up_height, anchor_height=None, left=left, top=top)
                pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), launcher_row), launcher])
                target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
                launcher.open_pop_up()
                rows = [line.decode() for line in target.render((6, 5)).text]

                self.assertEqual(
                    [(row, expected_col) for row in expected_rows],
                    [(index, line.index("ppp")) for index, line in enumerate(rows) if "ppp" in line],
                )


class RelativePopUpSizeTest(unittest.TestCase):
    def test_relative_size(self) -> None:
        """A relative size is a percentage of the space from the pop-up's edge to the far edge of the target."""
        for description, left, top, size, expected in (
            ("whole space", 0, 0, ("relative", 100), [" ppppppppppp"] * 5),
            ("fractional percentage", 0, 0, ("relative", 100.0), [" ppppppppppp"] * 5),
            # More than the space: the Overlay moves the pop-up left and up to fit, and shrinks it to the target.
            ("above 100%", 0, 0, ("relative", 250), ["pppppppppppp"] * 5),
            # The product of the space and the percentage is infinite; the result is the same as for 250%.
            ("huge percentage", 0, 0, ("relative", 1e308), ["pppppppppppp"] * 5),
            # 33.4% of 11 columns is 3.67, rounded up to 4; of 5 rows it is 1.67, rounded up to 2.
            ("fractional, rounded", 0, 0, ("relative", 33.4), [*[" pppp       "] * 2, *[" " * 12] * 3]),
            # 50% of the 9 columns right of column 3 rounds up to 5; 50% of the 4 rows below row 1 is 2.
            ("half, offset", 2, 1, ("relative", 50), [" L          ", *["   ppppp    "] * 2, *[" " * 12] * 2]),
        ):
            with self.subTest(description):
                launcher = AnchoredLauncher(size, pop_up_width=size, anchor_height=None, left=left, top=top)
                target = urwid.PopUpTarget(urwid.Filler(urwid.Padding(launcher, left=1), valign="top"))
                launcher.open_pop_up()
                self.assertEqual(expected, [line.decode() for line in target.render((12, 5)).text])

    def test_relative_height_with_no_room_below_is_anchored_above(self) -> None:
        """A relative height is at least one row, so an anchored pop-up with no rows below goes above."""
        launcher = AnchoredLauncher(("relative", 100))
        pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), 4), launcher])
        target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
        launcher.open_pop_up()
        self.assertEqual(["xxx", "xxx", "xxx", "ppp", "L  "], [line.decode() for line in target.render((3, 5)).text])


class PackedPopUpSizeTest(unittest.TestCase):
    @staticmethod
    def render(launcher: AnchoredLauncher, launcher_row: int = 0, size: tuple[int, int] = (6, 5)) -> list[str]:
        pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), launcher_row), launcher])
        target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
        launcher.open_pop_up()
        return [line.decode() for line in target.render(size).text]

    def test_packed_size(self) -> None:
        """A 'pack' width is the fixed size of the widget, a 'pack' height its rows at the pop-up width."""
        for description, width, height, expected in (
            ("pack height", 4, urwid.PACK, ["L     ", "ab    ", "cde   ", *["      "] * 2]),
            ("pack width and height", "pack", "pack", ["L     ", "ab    ", "cde   ", *["      "] * 2]),
            # At 2 columns "cde" wraps to a third row.
            ("pack height at a narrow width", 2, "pack", ["L     ", "ab    ", "cd    ", "e     ", "      "]),
        ):
            with self.subTest(description):
                launcher = AnchoredLauncher(
                    height,
                    pop_up_width=width,
                    pop_up=urwid.Text("ab\ncde"),
                    anchor_height=None,
                )
                self.assertEqual(expected, self.render(launcher))

    def test_packed_height_taller_than_the_space_is_cut_off_the_anchor_rows(self) -> None:
        """A flow pop-up taller than its side loses its last rows rather than covering the launcher."""
        text = urwid.Text("\n".join(f"t{index}" for index in range(6)))
        launcher = AnchoredLauncher("pack", pop_up=text)
        self.assertEqual(["xxxxxx", "xxxxxx", "L     ", "t0    ", "t1    "], self.render(launcher, launcher_row=2))

    def test_packed_list_box_takes_the_box_size(self) -> None:
        """A ListBox(flow=True) is rendered as a box when cut down, so it can scroll to its focus."""
        walker = urwid.SimpleFocusListWalker([urwid.Text(f"l{index}") for index in range(6)])
        walker.set_focus(5)
        launcher = AnchoredLauncher("pack", pop_up=urwid.ListBox(walker, flow=True))
        self.assertEqual(["xxxxxx", "xxxxxx", "L     ", "l4    ", "l5    "], self.render(launcher, launcher_row=2))

    def test_packed_flow_pop_up_takes_keys(self) -> None:
        edit = urwid.Edit()
        launcher = AnchoredLauncher("pack", pop_up_width=4, pop_up=edit, anchor_height=None)
        pile = urwid.Pile([launcher])
        target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
        launcher.open_pop_up()
        target.render((6, 5), focus=True)
        self.assertIsNone(target.keypress((6, 5), "a"))
        self.assertEqual("a", edit.edit_text)

    def test_click_in_a_cut_off_packed_pop_up_hits_the_row_shown(self) -> None:
        """A packed flow pop-up scrolled to its focus takes a click on the row it shows there."""
        pressed: list[int] = []
        buttons = urwid.Pile(
            [urwid.Button(f"b{index}", on_press=lambda _button, i=index: pressed.append(i)) for index in range(6)]
        )
        launcher = AnchoredLauncher("pack", pop_up_width=6, pop_up=buttons, close_on_click_outside=True)
        pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), 2), launcher])
        target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
        launcher.open_pop_up()
        size = (6, 5)
        for _ in range(5):
            target.keypress(size, "down")
        rows = [line.decode() for line in target.render(size, focus=True).text]
        self.assertEqual(["< b4 >", "< b5 >"], rows[3:])

        target.mouse_event(size, "mouse press", 1, 2, 3, True)
        self.assertEqual([4], pressed)
        self.assertIsNotNone(launcher.pop_up_widget)

        # The launcher row is outside the pop-up: the press closes it and does not reach the launcher.
        self.assertTrue(target.mouse_event(size, "mouse press", 1, 0, 2, True))
        self.assertIsNone(launcher.pop_up_widget)

    def test_packed_size_needs_a_matching_widget(self) -> None:
        for description, width, height in (
            ("pack width of a box widget", "pack", 2),
            ("pack height of a box widget", 3, "pack"),
            ("pack width of a fixed only widget", "pack", 2),
        ):
            with self.subTest(description):
                pop_up = (
                    urwid.BigText("A", urwid.Thin3x3Font())
                    if description.endswith("fixed only widget")
                    else urwid.SolidFill("p")
                )
                launcher = AnchoredLauncher(height, pop_up_width=width, pop_up=pop_up, anchor_height=None)
                with self.assertRaises(urwid.WidgetError):
                    self.render(launcher)


class AlignedPopUpTest(unittest.TestCase):
    def test_alignment_inside_the_target(self) -> None:
        """An aligned axis is placed inside the whole target after the size is known, wherever the launcher is."""
        blank = " " * 12
        for description, left, top, width, height, expected in (
            (
                "packed and centred",
                "center",
                "middle",
                "pack",
                "pack",
                ["xxxxxxxxxxxx", "xxxxab xxxxx", "xxxxcdexxxxx", "  L         ", blank],
            ),
            (
                "right and bottom",
                urwid.RIGHT,
                urwid.BOTTOM,
                3,
                "pack",
                ["xxxxxxxxxxxx", "xxxxxxxxxxxx", "xxxxxxxxxxxx", "  L      ab ", "         cde"],
            ),
            # Relative to all 12 columns, not to the 10 right of the launcher.
            (
                "relative and centred",
                "center",
                -3,
                ("relative", 50),
                "pack",
                ["xxxab    xxx", "xxxcde   xxx", "xxxxxxxxxxxx", "  L         ", blank],
            ),
        ):
            with self.subTest(description):
                launcher = AnchoredLauncher(
                    height,
                    pop_up_width=width,
                    pop_up=urwid.Text("ab\ncde"),
                    anchor_height=None,
                    left=left,
                    top=top,
                )
                pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), 3), urwid.Padding(launcher, left=2)])
                target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
                launcher.open_pop_up()
                self.assertEqual(expected, [line.decode() for line in target.render((12, 5)).text])

    def test_nested_aligned_pop_up_is_centred_in_the_target(self) -> None:
        """An aligned nested pop-up ignores the position of the pop-up that opened it."""
        inner = AnchoredLauncher(1, anchor_height=None, left="center", top="middle")
        outer = DialogWithLauncher(inner)
        target = urwid.PopUpTarget(urwid.Filler(outer, valign="top"))
        outer.open_pop_up()
        inner.open_pop_up()
        rows = [line.decode() for line in target.render((12, 10)).text]
        self.assertEqual([(4, 4)], [(index, line.index("ppp")) for index, line in enumerate(rows) if "ppp" in line])


class AnchoredPopUpTest(unittest.TestCase):
    def test_placement(self) -> None:
        """Below if it fits, else above if it fits, else the larger side clipped; never over the launcher."""
        maxrow = 11
        for description, launcher_row, pop_up_height, expected_rows in (
            ("fits below", 2, 4, range(3, 7)),
            ("fits above only", 8, 4, range(4, 8)),
            ("clipped below, more rows below", 4, 10, range(5, 11)),
            ("clipped above, more rows above", 6, 10, range(6)),
            ("clipped below on equal sides", 5, 10, range(6, 11)),
        ):
            with self.subTest(description):
                launcher = AnchoredLauncher(pop_up_height)
                pile = urwid.Pile([urwid.BoxAdapter(urwid.SolidFill("x"), launcher_row), launcher])
                target = urwid.PopUpTarget(urwid.Filler(pile, valign="top"))
                launcher.open_pop_up()
                rows = [line.decode() for line in target.render((3, maxrow)).text]

                self.assertEqual("L  ", rows[launcher_row])
                self.assertEqual(list(expected_rows), [index for index, line in enumerate(rows) if line == "ppp"])

    def test_no_room_on_either_side_falls_back_to_overlay_placement(self) -> None:
        launcher = AnchoredLauncher(2)
        target = urwid.PopUpTarget(urwid.Filler(launcher, valign="top"))
        launcher.open_pop_up()
        self.assertEqual([b"ppp"], target.render((3, 1)).text)


class NestedDialog(urwid.PopUpLauncher[urwid.Filler[urwid.Edit]]):
    """A pop-up launcher whose own pop-up is another :class:`NestedDialog`.

    Used to reproduce https://github.com/urwid/urwid/issues/469: a pop-up
    launcher opened from inside an already-open pop-up.
    """

    def __init__(
        self,
        level: int,
        *,
        close_on_menu_levels: frozenset[int] = frozenset(),
        close_on_click_outside_levels: frozenset[int] = frozenset(),
    ) -> None:
        self.level = level
        self.close_on_menu_levels = close_on_menu_levels
        self.close_on_click_outside_levels = close_on_click_outside_levels
        super().__init__(
            urwid.Filler(urwid.Edit("", f"level {level}")),
            close_on_menu=level in close_on_menu_levels,
            close_on_click_outside=level in close_on_click_outside_levels,
        )

    def create_pop_up(self) -> NestedDialog:
        return NestedDialog(
            self.level + 1,
            close_on_menu_levels=self.close_on_menu_levels,
            close_on_click_outside_levels=self.close_on_click_outside_levels,
        )

    def get_pop_up_parameters(self) -> dict:
        return {"left": self.level * 12, "top": 0, "overlay_width": 10, "overlay_height": 3}


class NestedPopUpTest(unittest.TestCase):
    def test_nested_pop_up_is_rendered(self) -> None:
        outer = NestedDialog(0)
        target = urwid.PopUpTarget(outer)
        outer.open_pop_up()
        inner = outer._pop_up_widget

        inner.open_pop_up()  # nest a second pop-up inside the first one

        canv = target.render((25, 10))
        text = b"\n".join(canv.text).decode()
        self.assertIn("level 1", text)
        self.assertIn("level 2", text)
        self.assertEqual(len(target._pop_up_levels), 2)

    def test_click_outside_closes_only_the_topmost_pop_up(self) -> None:
        """Close only the topmost pop-up on an outside click.

        The click closes it only when its own launcher asked for that.
        """
        outer = NestedDialog(0, close_on_click_outside_levels=frozenset({1}))
        target = urwid.PopUpTarget(outer)
        outer.open_pop_up()
        inner = outer.pop_up_widget
        inner.open_pop_up()

        # Column 5 is inside the level 1 pop-up (columns 0-9) and outside the level 2 one (columns 12-21).
        self.assertTrue(target.mouse_event((40, 10), "mouse press", 1, 5, 5, True))
        self.assertIsNone(inner.pop_up_widget)
        self.assertIsNotNone(outer.pop_up_widget)

        # The level 0 launcher did not ask for it, so its pop-up stays open.
        self.assertFalse(target.mouse_event((40, 10), "mouse press", 1, 5, 5, True))
        self.assertIsNotNone(outer.pop_up_widget)

    def test_closing_inner_pop_up_reverts_to_outer(self) -> None:
        outer = NestedDialog(0)
        target = urwid.PopUpTarget(outer)
        outer.open_pop_up()
        inner = outer._pop_up_widget
        inner.open_pop_up()
        target.render((25, 10))

        inner.close_pop_up()
        canv = target.render((25, 10))
        text = b"\n".join(canv.text).decode()
        self.assertIn("level 1", text)
        self.assertNotIn("level 2", text)
        self.assertEqual(len(target._pop_up_levels), 1)

    def test_closing_outer_pop_up_closes_everything(self) -> None:
        outer = NestedDialog(0)
        target = urwid.PopUpTarget(outer)
        outer.open_pop_up()
        inner = outer._pop_up_widget
        inner.open_pop_up()
        target.render((25, 10))

        outer.close_pop_up()
        canv = target.render((25, 10))
        text = b"\n".join(canv.text).decode()
        self.assertNotIn("level 1", text)
        self.assertNotIn("level 2", text)
        self.assertEqual(target._pop_up_levels, [])

    def test_keypress_reaches_innermost_pop_up(self) -> None:
        outer = NestedDialog(0)
        target = urwid.PopUpTarget(outer)
        outer.open_pop_up()
        inner = outer._pop_up_widget
        inner.open_pop_up()
        innermost = inner._pop_up_widget

        target.keypress((20, 10), "x")
        self.assertEqual(innermost.original_widget.original_widget.edit_text, "level 2x")

    def test_menu_key_closes_only_the_topmost_pop_up(self) -> None:
        """Only the topmost pop-up's launcher decides what a menu key does."""
        for description, close_on_menu_levels, expected, outer_open, inner_open in (
            ("both launchers close on menu", frozenset({0, 1}), None, True, False),
            ("only the outer launcher closes on menu", frozenset({0}), "esc", True, True),
        ):
            with self.subTest(description):
                outer = NestedDialog(0, close_on_menu_levels=close_on_menu_levels)
                target = urwid.PopUpTarget(outer)
                outer.open_pop_up()
                inner = outer.pop_up_widget
                inner.open_pop_up()

                self.assertEqual(expected, target.keypress((25, 10), "esc"))
                self.assertEqual(outer_open, outer.pop_up_widget is not None)
                self.assertEqual(inner_open, inner.pop_up_widget is not None)


class DialogWithLauncher(urwid.PopUpLauncher[urwid.Text]):
    """A launcher whose pop-up is a dialog at (6, 4) holding `inner` under a title row."""

    def __init__(self, inner: urwid.Widget, *, dialog_height: int = 4, valign: str = "top") -> None:
        super().__init__(urwid.Text("O"))
        self.inner = inner
        self.dialog_height = dialog_height
        self.valign = valign

    def create_pop_up(self) -> urwid.Filler[urwid.Pile]:
        return urwid.Filler(urwid.Pile([urwid.Text("dlg"), self.inner]), valign=self.valign)

    def get_pop_up_parameters(self) -> dict:
        return {"left": 6, "top": 4, "overlay_width": 5, "overlay_height": self.dialog_height}


class NestedPopUpOffsetTest(unittest.TestCase):
    def test_nested_pop_up_is_placed_relative_to_its_launcher(self) -> None:
        """A nested pop-up's position is relative to the pop-up containing its launcher, not to the screen."""
        for description, dialog, pop_up_height, anchor_height, expected_rows in (
            ("plain, below", {}, 3, None, range(6, 9)),
            ("anchored, below", {}, 4, 1, range(6, 10)),
            ("anchored, flipped above", {}, 5, 1, range(5)),
            # Relative to the space below the pop-up's top on the screen, not inside the 4-row dialog.
            ("relative height", {}, ("relative", 100), None, range(6, 10)),
            # The dialog is too tall for the screen, so the Overlay shrinks it to the 10 screen rows and the
            # Filler centres its 2 rows there: the launcher is on screen row 5, not where a 14-row dialog has it.
            ("dialog shrunk to the screen", {"dialog_height": 14, "valign": "middle"}, 2, None, range(6, 8)),
        ):
            with self.subTest(description):
                inner = AnchoredLauncher(pop_up_height, anchor_height=anchor_height)
                outer = DialogWithLauncher(inner, **dialog)
                target = urwid.PopUpTarget(urwid.Filler(outer, valign="top"))
                outer.open_pop_up()
                inner.open_pop_up()

                rows = [line.decode() for line in target.render((12, 10)).text]

                self.assertEqual("L", rows[5][6])
                self.assertEqual(
                    list(expected_rows),
                    [index for index, line in enumerate(rows) if line[6:9] == "ppp"],
                )


if __name__ == "__main__":
    unittest.main()


class PilePopUpLauncher(urwid.PopUpLauncher[urwid.Filler[urwid.Pile]]):
    """Launcher over an opted-in Pile, whose pop-up is another opted-in Pile."""

    def __init__(self) -> None:
        """Create both Piles and wrap the background one."""
        self.background = urwid.Pile([urwid.Button("a"), urwid.Button("b")], select_navigation=True)
        self.pop_up = urwid.Pile([urwid.Button("p"), urwid.Button("q")], select_navigation=True)
        super().__init__(urwid.Filler(self.background, valign="top"))

    def create_pop_up(self) -> urwid.Filler[urwid.Pile]:
        """Return the pop-up Pile, aligned to the top."""
        return urwid.Filler(self.pop_up, valign="top")

    def get_pop_up_parameters(self) -> dict:
        """Place the pop-up below the background buttons."""
        return {"left": 0, "top": 2, "overlay_width": 8, "overlay_height": 2}


class PopUpTargetSelectNavigationTest(unittest.TestCase):
    """PopUpTarget is one stop: entering it keeps every focus under it."""

    size = (8, 5)

    def test_entry_keeps_focus(self) -> None:
        """No focus under the target changes on entry, whatever state the pop-up is in."""
        launcher = PilePopUpLauncher()
        target = urwid.PopUpTarget(launcher)
        launcher.background.focus_position = 1
        launcher.pop_up.focus_position = 1

        steps = (
            ("no pop-up", lambda: None),
            ("opened, not rendered", launcher.open_pop_up),
            ("open and rendered", lambda: target.render(self.size, focus=True)),
            ("closed, not rendered", launcher.close_pop_up),
        )
        for description, step in steps:
            with self.subTest(description):
                step()
                target.enter_selectable()
                target.enter_selectable(reverse=True)
                self.assertEqual(1, launcher.background.focus_position)
                self.assertEqual(1, launcher.pop_up.focus_position)

    def test_keys_traverse_open_pop_up(self) -> None:
        """Keys still reach the opted-in Pile of the open pop-up."""
        launcher = PilePopUpLauncher()
        target = urwid.PopUpTarget(launcher)
        launcher.open_pop_up()
        target.render(self.size, focus=True)
        self.assertIsNone(target.keypress(self.size, "tab"))
        self.assertEqual(1, launcher.pop_up.focus_position)
        self.assertEqual("tab", target.keypress(self.size, "tab"))
        self.assertEqual(0, launcher.pop_up.focus_position)
        self.assertEqual(0, launcher.background.focus_position)
