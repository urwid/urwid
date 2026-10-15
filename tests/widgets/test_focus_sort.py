from __future__ import annotations

import unittest

import urwid


class NoEquality:
    def __init__(self, rank: int) -> None:
        self.rank = rank

    def __eq__(self, other: object) -> bool:
        raise AssertionError("Sorting by a key must not compare items for equality")


class FocusSortTest(unittest.TestCase):
    def test_equal_items_keep_the_focused_object(self) -> None:
        for reverse, focus, expected in ((False, 0, 1), (False, 2, 2), (True, 0, 0), (True, 2, 1)):
            with self.subTest(reverse=reverse, focus=focus):
                items = urwid.MonitoredFocusList([[2], [1], [2]], focus=focus)
                original = items[focus]
                items.sort(reverse=reverse)
                self.assertEqual(expected, items.focus)
                self.assertIs(original, items[expected])

    def test_key_sort_does_not_require_equality(self) -> None:
        for reverse, expected in ((False, 1), (True, 0)):
            with self.subTest(reverse=reverse):
                first, second = NoEquality(2), NoEquality(1)
                items = urwid.MonitoredFocusList([first, second])
                seen = []
                items.set_modified_callback(lambda: seen.append((items.focus, items[expected] is first)))
                items.sort(key=lambda item: item.rank, reverse=reverse)
                self.assertEqual(expected, items.focus)
                self.assertEqual([(expected, True)], seen)
                self.assertIs(first, items[expected])

    def test_modified_callback_can_change_focus(self) -> None:
        first, second = [1], [1]
        items = urwid.MonitoredFocusList([first, second], focus=1)
        seen = []

        def modified() -> None:
            seen.append(items.focus)
            items.focus = 0

        items.set_modified_callback(modified)
        items.sort()
        self.assertEqual([1], seen)
        self.assertEqual(0, items.focus)

    def test_key_failure_does_not_notify(self) -> None:
        items = urwid.MonitoredFocusList([2, 1], focus=1)
        seen = []
        items.set_modified_callback(lambda: seen.append(items.focus))

        def bad_key(item: int) -> int:
            raise ValueError("invalid sort key")

        with self.assertRaisesRegex(ValueError, "invalid sort key"):
            items.sort(key=bad_key)
        self.assertEqual([2, 1], items)
        self.assertEqual(1, items.focus)
        self.assertEqual([], seen)

    def test_empty_list_does_not_notify(self) -> None:
        items = urwid.MonitoredFocusList()
        seen = []
        items.set_modified_callback(lambda: seen.append(items.focus))
        items.sort()
        self.assertIsNone(items.focus)
        self.assertEqual([], seen)


if __name__ == "__main__":
    unittest.main()
