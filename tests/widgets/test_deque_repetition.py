from __future__ import annotations

import operator
import unittest
from collections import deque

import urwid


class MonitoredDequeRepetitionTest(unittest.TestCase):
    def test_modified_notification(self) -> None:
        for container in (urwid.MonitoredDeque, urwid.MonitoredFocusDeque):
            for multiplier in (-2, 0, 1, 2, 3):
                with self.subTest(container=container.__name__, multiplier=multiplier):
                    items = container([1, 2, 3])
                    seen = []
                    items.set_modified_callback(lambda: seen.append(list(items)))
                    result = operator.imul(items, multiplier)
                    self.assertIs(items, result)
                    self.assertEqual([1, 2, 3] * multiplier, list(items))
                    self.assertEqual([list(items)], seen)

    def test_bounded_focus_matches_extend(self) -> None:
        for limit in (None, 0, 1, 3, 4, 5, 7):
            for multiplier in (-2, 0, 1, 2, 3):
                with self.subTest(maxlen=limit, multiplier=multiplier):
                    focus = 0 if limit in (0, 1) else 1
                    items = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=limit, focus=focus)
                    expected = urwid.MonitoredFocusDeque(items, maxlen=limit, focus=focus)
                    if multiplier <= 0:
                        expected.clear()
                    elif multiplier > 1:
                        expected.extend(list(expected) * (multiplier - 1))
                    items *= multiplier
                    self.assertEqual(list(expected), list(items))
                    self.assertEqual(expected.focus, items.focus)

    def test_callback_sees_updated_focus(self) -> None:
        items = urwid.MonitoredFocusDeque(["a", "b", "c"], maxlen=5, focus=1)
        seen = []
        items.set_modified_callback(lambda: seen.append((list(items), items.focus)))
        items *= 2
        self.assertEqual([(["b", "c", "a", "b", "c"], 0)], seen)

    def test_focused_item_survives_partial_eviction(self) -> None:
        values = [object(), object(), object()]
        items = urwid.MonitoredFocusDeque(values, maxlen=5, focus=2)
        focused = items[items.focus]
        items *= 2
        self.assertEqual(1, items.focus)
        self.assertIs(focused, items[items.focus])

    def test_invalid_multiplier_does_not_notify(self) -> None:
        for container in (urwid.MonitoredDeque, urwid.MonitoredFocusDeque):
            for multiplier in (1.5, "2"):
                with self.subTest(container=container.__name__, multiplier=multiplier):
                    items = container([1, 2, 3])
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    with self.assertRaises(TypeError):
                        items *= multiplier
                    self.assertEqual([1, 2, 3], list(items))
                    self.assertEqual([], seen)

    def test_index_multiplier(self) -> None:
        class Index:
            calls = 0

            def __index__(self) -> int:
                self.calls += 1
                return 2

            def __int__(self) -> int:
                return 1

        for container in (urwid.MonitoredDeque, urwid.MonitoredFocusDeque):
            with self.subTest(container=container.__name__):
                items = container([1, 2])
                multiplier = Index()
                items *= multiplier
                self.assertEqual([1, 2, 1, 2], list(items))
                self.assertEqual(1, multiplier.calls)

    def test_large_bounded_repetition(self) -> None:
        items = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=5, focus=1)
        expected = deque(items, maxlen=5)
        expected *= 1_000_000
        items *= 1_000_000
        self.assertEqual(list(expected), list(items))
        self.assertEqual(0, items.focus)

    def test_listbox_cache_invalidated(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([urwid.Text("a"), urwid.Text("b")])
        box = urwid.ListBox(walker)
        before = box.render((4, 1), focus=True)
        self.assertEqual([b"a   "], before.text)
        walker *= 0
        after = box.render((4, 1), focus=True)
        self.assertEqual([b"    "], after.text)
        self.assertIsNot(before, after)


if __name__ == "__main__":
    unittest.main()
