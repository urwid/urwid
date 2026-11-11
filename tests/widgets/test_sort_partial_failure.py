from __future__ import annotations

import unittest

import urwid


class SortFailure(RuntimeError):
    pass


class SortItem(urwid.Text):
    __hash__ = object.__hash__

    def __init__(self, rank, counter, failure, limit=4):
        super().__init__(str(rank))
        self.rank = rank
        self.counter = counter
        self.failure = failure
        self.limit = limit

    def selectable(self):
        return True

    def __eq__(self, other):
        raise AssertionError("identity checks must not call equality")

    def __lt__(self, other):
        self.counter[0] += 1
        if self.counter[0] == self.limit:
            raise self.failure
        return self.rank < other.rank


class PartialSortTest(unittest.TestCase):
    def make_items(self, cls, limit=4):
        failure = SortFailure("sort failed")
        counter = [0]
        original = [SortItem(n, counter, failure, limit) for n in [5, 1, 4, 2, 3, 0]]
        return cls(original), original, failure

    def test_partial_permutation_notifies_once_after_focus(self):
        for cls in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            with self.subTest(cls=cls):
                items, original, failure = self.make_items(cls)
                seen = []
                items.set_modified_callback(lambda: seen.append((list(items), getattr(items, "focus", None))))
                with self.assertRaises(SortFailure) as caught:
                    items.sort()
                self.assertIs(caught.exception, failure)
                self.assertEqual([1, 5, 4, 2, 3, 0], [item.rank for item in items])
                self.assertEqual(1, len(seen))
                if cls is urwid.MonitoredFocusList:
                    self.assertIs(items[items.focus], original[0])
                    self.assertEqual(1, seen[0][1])

    def test_unchanged_failure_notifies_nothing(self):
        for cls in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            for key_failure in [True, False]:
                with self.subTest(cls=cls, key_failure=key_failure):
                    items, original, failure = self.make_items(cls, limit=1)
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))

                    def key(item):
                        raise failure

                    with self.assertRaises(SortFailure) as caught:
                        items.sort(**({"key": key} if key_failure else {}))
                    self.assertIs(caught.exception, failure)
                    self.assertTrue(all(a is b for a, b in zip(items, original)))
                    self.assertEqual([], seen)

    def test_listbox_cached_render_is_invalidated(self):
        for cls in [urwid.SimpleListWalker, urwid.SimpleFocusListWalker]:
            with self.subTest(cls=cls):
                walker, original, failure = self.make_items(cls)
                box = urwid.ListBox(walker)
                before = box.render((8, 6), True)
                seen = []
                urwid.connect_signal(walker, "modified", lambda: seen.append(True))
                with self.assertRaises(SortFailure) as caught:
                    walker.sort()
                self.assertIs(caught.exception, failure)
                after = box.render((8, 6), True)
                self.assertIsNot(after, before)
                # Focus tracking can scroll the viewport, so compare to a fresh consumer.
                fresh = urwid.ListBox(walker).render((8, 6), True)
                self.assertEqual(fresh.text, after.text)
                self.assertEqual([True], seen)
                if cls is urwid.SimpleFocusListWalker:
                    self.assertIs(walker[walker.focus], original[0])

    def test_partial_failure_preserves_original_when_callbacks_raise(self):
        for cls in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            callbacks = ["modified"] if cls is urwid.MonitoredList else ["modified", "focus_changed", "focus_moved"]
            for callback in callbacks:
                with self.subTest(cls=cls, callback=callback):
                    items, _, failure = self.make_items(cls)
                    seen = []

                    def fail(*args):
                        seen.append(callback)
                        raise RuntimeError("callback failed")

                    getattr(items, f"set_{callback}_callback")(fail)
                    with self.assertRaises(SortFailure) as caught:
                        items.sort()
                    self.assertIs(caught.exception, failure)
                    self.assertEqual([callback], seen)

    def test_interruption_notifies_partial_order(self):
        for cls in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            for failure_type in [KeyboardInterrupt, SystemExit, GeneratorExit]:
                with self.subTest(cls=cls, failure_type=failure_type):
                    failure = failure_type()
                    counter = [0]
                    original = [SortItem(n, counter, failure) for n in [5, 1, 4, 2, 3, 0]]
                    items = cls(original)
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    with self.assertRaises(failure_type) as caught:
                        items.sort()
                    self.assertIs(caught.exception, failure)
                    self.assertEqual([True], seen)
                    if cls is urwid.MonitoredFocusList:
                        self.assertIs(items[items.focus], original[0])

    def test_key_comparison_failure_and_reverse_sort(self):
        for cls in [urwid.MonitoredList, urwid.MonitoredFocusList]:
            for reverse in [False, True]:
                with self.subTest(cls=cls, reverse=reverse):
                    items, original, failure = self.make_items(cls)
                    seen = []
                    items.set_modified_callback(lambda: seen.append(True))
                    # A key object can fail during comparison after every key was computed.
                    with self.assertRaises(SortFailure) as caught:
                        items.sort(key=lambda item: item, reverse=reverse)
                    self.assertIs(caught.exception, failure)
                    changed = any(a is not b for a, b in zip(items, original))
                    self.assertEqual([True] if changed else [], seen)
                    if cls is urwid.MonitoredFocusList:
                        self.assertIs(items[items.focus], original[0])

    def test_failed_focus_callback_still_invalidates_consumer(self):
        walker, original, failure = self.make_items(urwid.SimpleFocusListWalker)
        box = urwid.ListBox(walker)
        before = box.render((8, 6), True)

        def fail(index):
            raise RuntimeError("focus callback veto")

        walker.set_focus_changed_callback(fail)
        with self.assertRaises(SortFailure) as caught:
            walker.sort()
        self.assertIs(caught.exception, failure)
        self.assertEqual(0, walker.focus)
        self.assertIsNot(walker[walker.focus], original[0])
        self.assertIsNot(before, box.render((8, 6), True))

    def test_modified_callback_focus_override_is_kept(self):
        items, _, failure = self.make_items(urwid.MonitoredFocusList)
        items.set_modified_callback(lambda: setattr(items, "focus", 3))
        moved = []
        items.set_focus_moved_callback(lambda old, new: moved.append((old, new)))
        with self.assertRaises(SortFailure) as caught:
            items.sort()
        self.assertIs(caught.exception, failure)
        self.assertEqual(3, items.focus)
        self.assertEqual([(0, 3)], moved)
