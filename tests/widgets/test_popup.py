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


if __name__ == "__main__":
    unittest.main()
