from __future__ import annotations

import unittest

import urwid


class StubCursorBox(urwid.SolidFill):
    """A box widget with cursor-related methods that record the size passed to them."""

    def get_cursor_coords(self, size: tuple[int, int]) -> tuple[int, int]:
        self.last_size = size
        return 1, 1

    def move_cursor_to_coords(self, size: tuple[int, int], col: int, row: int) -> bool:
        self.last_size = size
        return True

    def get_pref_col(self, size: tuple[int, int]) -> int:
        self.last_size = size
        return 7


class BoxAdapterTest(unittest.TestCase):
    def test_not_a_box_widget(self) -> None:
        with self.assertRaises(urwid.widget.box_adapter.BoxAdapterError):
            urwid.BoxAdapter(urwid.Text("flow widget"), 5)

    def test_repr(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 5)
        self.assertIn("height=5", repr(adapter))

    def test_rows(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 5)
        self.assertEqual(adapter.rows((20,)), 5)

    def test_render(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 3)
        canv = adapter.render((4,))
        self.assertEqual(list(canv.text), [b"xxxx"] * 3)

    def test_get_cursor_coords_supported(self) -> None:
        box = StubCursorBox("x")
        adapter = urwid.BoxAdapter(box, 3)
        self.assertEqual(adapter.get_cursor_coords((10,)), (1, 1))
        self.assertEqual(box.last_size, (10, 3))

    def test_get_cursor_coords_unsupported(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 3)
        self.assertIsNone(adapter.get_cursor_coords((10,)))

    def test_move_cursor_to_coords_supported(self) -> None:
        box = StubCursorBox("x")
        adapter = urwid.BoxAdapter(box, 3)
        self.assertTrue(adapter.move_cursor_to_coords((10,), 0, 0))
        self.assertEqual(box.last_size, (10, 3))

    def test_move_cursor_to_coords_unsupported(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 3)
        self.assertTrue(adapter.move_cursor_to_coords((10,), 0, 0))

    def test_get_pref_col_supported(self) -> None:
        box = StubCursorBox("x")
        adapter = urwid.BoxAdapter(box, 3)
        self.assertEqual(adapter.get_pref_col((10,)), 7)
        self.assertEqual(box.last_size, (10, 3))

    def test_get_pref_col_unsupported(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 3)
        self.assertIsNone(adapter.get_pref_col((10,)))

    def test_keypress(self) -> None:
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Edit("", "hi")]))
        adapter = urwid.BoxAdapter(listbox, 3)
        self.assertIsNone(adapter.keypress((10,), "x"))
        self.assertEqual(listbox.focus.edit_text, "hix")

    def test_mouse_event_supported(self) -> None:
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Edit("", "hi")]))
        adapter = urwid.BoxAdapter(listbox, 3)
        result = adapter.mouse_event((10,), "mouse press", 1, 0, 0, True)
        self.assertTrue(result)

    def test_mouse_event_unhandled(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("x"), 3)
        self.assertFalse(adapter.mouse_event((10,), "mouse press", 1, 0, 0, True))

    def test_getattr_passthrough(self) -> None:
        adapter = urwid.BoxAdapter(urwid.SolidFill("y"), 3)
        self.assertEqual(adapter.fill_char, "y")


if __name__ == "__main__":
    unittest.main()
