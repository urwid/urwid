from __future__ import annotations

import unittest

import urwid


class EmptyFocusSliceTest(unittest.TestCase):
    slices = (slice(4, 1), slice(-1, 1), slice(4, -3), slice(100, 1), slice(1, -100), slice(1, 1))

    def test_deletion_keeps_focus(self) -> None:
        for selection in self.slices:
            for focus in range(5):
                with self.subTest(selection=selection, focus=focus):
                    items = urwid.MonitoredFocusList(["a", "b", "c", "d", "e"], focus=focus)
                    del items[selection]
                    self.assertEqual(["a", "b", "c", "d", "e"], items)
                    self.assertEqual(focus, items.focus)

    def test_assignment_tracks_the_original_item(self) -> None:
        for selection in self.slices:
            for focus in range(5):
                for replacement in ([], ["x", "y"]):
                    with self.subTest(selection=selection, focus=focus, replacement=replacement):
                        values = ["a", "b", "c", "d", "e"]
                        original = values[focus]
                        items = urwid.MonitoredFocusList(values, focus=focus)
                        values[selection] = replacement
                        items[selection] = replacement
                        self.assertEqual(values, items)
                        self.assertEqual(values.index(original), items.focus)

    def test_callbacks_observe_the_unchanged_focus(self) -> None:
        items = urwid.MonitoredFocusList(["a", "b", "c", "d", "e"], focus=2)
        validated = []
        modified = []
        focus_changes = []
        items.set_validate_contents_modified(lambda indices, new: validated.append((indices, list(new))))
        items.set_modified_callback(lambda: modified.append(items.focus))
        items.set_focus_changed_callback(focus_changes.append)
        del items[4:1]
        self.assertEqual([((4, 1, 1), [])], validated)
        self.assertEqual([2], modified)
        self.assertEqual([], focus_changes)

    def test_validation_can_override_focus(self) -> None:
        items = urwid.MonitoredFocusList(["a", "b", "c", "d", "e"], focus=2)
        items.set_validate_contents_modified(lambda indices, new: 0)
        items[4:1] = ["x"]
        self.assertEqual(0, items.focus)

    def test_walker_keeps_the_focused_widget(self) -> None:
        widgets = [urwid.SelectableIcon(text) for text in "abcde"]
        walker = urwid.SimpleFocusListWalker(widgets)
        walker.set_focus(2)
        walker[4:1] = [urwid.SelectableIcon("x")]
        self.assertEqual(2, walker.focus)
        self.assertIs(widgets[2], walker.get_focus()[0])


if __name__ == "__main__":
    unittest.main()
