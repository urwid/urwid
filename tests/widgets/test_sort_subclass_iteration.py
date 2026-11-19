from __future__ import annotations

import unittest

import urwid

from .test_sort_partial_failure import SortFailure, SortItem


class SortSubclassIterationTest(unittest.TestCase):
    def subclass(self, base, mode):
        class CustomIteration(base):
            def __iter__(self):
                if mode == "raise":
                    raise RuntimeError("custom iteration unavailable")
                if mode == "empty":
                    return iter(())
                return reversed(self)

        return CustomIteration

    def test_successful_monitored_sort_uses_list_storage(self):
        # list.sort never needs the subclass's public iteration protocol.
        for mode in ["raise", "empty", "reverse"]:
            with self.subTest(mode=mode):
                items = self.subclass(urwid.MonitoredList, mode)([3, 1, 2])
                seen = []
                items.set_modified_callback(lambda: seen.append(True))
                items.sort()
                self.assertEqual([1, 2, 3], [item for item in list.__iter__(items)])
                self.assertEqual([True], seen)

    def test_partial_failure_uses_storage_for_detection_and_focus(self):
        for base in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            for mode in ["raise", "empty", "reverse"]:
                with self.subTest(base=base, mode=mode):
                    failure = SortFailure("sort failed")
                    counter = [0]
                    original = [SortItem(n, counter, failure) for n in [5, 1, 4, 2, 3, 0]]
                    items = self.subclass(base, mode)(original)
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    with self.assertRaises(SortFailure) as caught:
                        items.sort()
                    self.assertIs(caught.exception, failure)
                    actual = [item for item in list.__iter__(items)]
                    self.assertTrue(any(item is not old for item, old in zip(actual, original)))
                    self.assertEqual([True], seen)
                    if base is urwid.MonitoredFocusList:
                        self.assertIs(items[items.focus], original[0])

    def test_unchanged_failure_keeps_original_exception(self):
        for base in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            for mode in ["raise", "empty", "reverse"]:
                with self.subTest(base=base, mode=mode):
                    items = self.subclass(base, mode)([3, 1, 2])
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    failure = SortFailure("key failed")

                    def key(item):
                        raise failure

                    with self.assertRaises(SortFailure) as caught:
                        items.sort(key=key)
                    self.assertIs(caught.exception, failure)
                    self.assertEqual([3, 1, 2], [item for item in list.__iter__(items)])
                    self.assertEqual([], seen)


class SortSubclassLengthTest(unittest.TestCase):
    def subclass(self, mode):
        class CustomLength(urwid.MonitoredList):
            def __len__(self):
                if mode == "raise":
                    raise RuntimeError("custom length unavailable")
                return 0 if mode == "zero" else 999

        return CustomLength

    def test_failed_sort_uses_storage_length(self):
        for mode in ["raise", "zero", "large"]:
            for limit in [1, 4]:
                with self.subTest(mode=mode, limit=limit):
                    failure = SortFailure("original comparison failure")
                    counter = [0]
                    original = [SortItem(n, counter, failure, limit) for n in [5, 1, 4, 2, 3, 0]]
                    items = self.subclass(mode)(original)
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    with self.assertRaises(SortFailure) as caught:
                        items.sort()
                    self.assertIs(caught.exception, failure)
                    actual = [item for item in list.__iter__(items)]
                    changed = any(item is not old for item, old in zip(actual, original))
                    self.assertEqual([True] if changed else [], seen)

    def test_successful_sort_uses_storage_length(self):
        for mode in ["raise", "zero", "large"]:
            with self.subTest(mode=mode):
                items = self.subclass(mode)([3, 1, 2])
                seen = []
                items.set_modified_callback(lambda: seen.append(True))
                items.sort()
                self.assertEqual([1, 2, 3], [item for item in list.__iter__(items)])
                self.assertEqual([True], seen)
