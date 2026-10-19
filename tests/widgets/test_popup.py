from __future__ import annotations

import unittest

import urwid


class ThingWithAPopUp(urwid.PopUpLauncher[urwid.SolidFill]):
    def __init__(self) -> None:
        super().__init__(urwid.SolidFill("x"))

    def create_pop_up(self) -> urwid.Filler[urwid.Edit]:
        return urwid.Filler(urwid.Edit("", "pop up contents"))

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

    def __init__(self, pop_up_height: int, *, anchor_height: int | None = 1, left: int = 0, top: int = 1) -> None:
        super().__init__(urwid.Text("L"))
        self.pop_up_height = pop_up_height
        self.anchor_height = anchor_height
        self.left = left
        self.top = top

    def create_pop_up(self) -> urwid.SolidFill:
        return urwid.SolidFill("p")

    def get_pop_up_parameters(self) -> dict:
        parameters = {"left": self.left, "top": self.top, "overlay_width": 3, "overlay_height": self.pop_up_height}
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

    def __init__(self, level: int) -> None:
        self.level = level
        super().__init__(urwid.Filler(urwid.Edit("", f"level {level}")))

    def create_pop_up(self) -> NestedDialog:
        return NestedDialog(self.level + 1)

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
