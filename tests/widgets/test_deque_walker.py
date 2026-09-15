from __future__ import annotations

import collections
import unittest

import urwid


class MonitoredDequeConstructionTest(unittest.TestCase):
    def test_from_generator(self) -> None:
        walker = urwid.SimpleDequeWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))

    def test_from_generator_focus(self) -> None:
        walker = urwid.SimpleFocusDequeWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))

    def test_non_iterable_raises(self) -> None:
        with self.assertRaises(urwid.ListWalkerError):
            urwid.SimpleDequeWalker(123)
        with self.assertRaises(urwid.ListWalkerError):
            urwid.SimpleFocusDequeWalker(123)


class MonitoredDequeMaxlenParityTest(unittest.TestCase):
    """Verify a bounded MonitoredDeque matches a plain collections.deque with the same maxlen.

    Runs the same operation sequence against both, asserting equal contents after each step.
    """

    def test_parity(self) -> None:
        maxlen = 4
        monitored = urwid.MonitoredDeque(maxlen=maxlen)
        reference: collections.deque = collections.deque(maxlen=maxlen)

        operations = [
            ("append", 1),
            ("append", 2),
            ("append", 3),
            ("appendleft", 0),
            ("append", 4),  # triggers eviction of head
            ("appendleft", -1),  # triggers eviction of tail
            ("extend", [10, 11, 12]),
            ("extendleft", [20, 21]),
            ("rotate", 1),
            ("rotate", -2),
            ("reverse", None),
            ("pop", None),
            ("popleft", None),
        ]
        for name, arg in operations:
            with self.subTest(name=name, arg=arg):
                if arg is None:
                    # pylint incorrectly infers a fixed signature for these dynamically-dispatched
                    # calls, treating `name` as though it always resolved to an argument-taking
                    # method such as ``append``.
                    getattr(monitored, name)()  # pylint: disable=no-value-for-parameter
                    getattr(reference, name)()  # pylint: disable=no-value-for-parameter
                else:
                    getattr(monitored, name)(arg)
                    getattr(reference, name)(arg)
                self.assertEqual(list(reference), list(monitored))


class MonitoredDequeModifiedCallbackTest(unittest.TestCase):
    def test_modified_fires_once(self) -> None:
        counter = {"count": 0}

        def bump() -> None:
            counter["count"] += 1

        md = urwid.MonitoredDeque([1, 2, 3], maxlen=3)
        md.set_modified_callback(bump)

        md.append(4)  # evicts head
        self.assertEqual(1, counter["count"])

        md.appendleft(0)  # evicts tail
        self.assertEqual(2, counter["count"])

        md.extend([5, 6])  # evicts multiple
        self.assertEqual(3, counter["count"])

        md.extendleft([7, 8])
        self.assertEqual(4, counter["count"])

        md.pop()
        self.assertEqual(5, counter["count"])

        md.popleft()
        self.assertEqual(6, counter["count"])

        md.rotate(1)
        self.assertEqual(7, counter["count"])

        md.clear()
        self.assertEqual(8, counter["count"])


class MonitoredFocusDequeFocusAdjustmentTest(unittest.TestCase):
    def test_focus_evicted_by_append(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=3, focus=0)
        mfd.append(4)  # evicts head (the focus item)
        self.assertEqual([2, 3, 4], list(mfd))
        self.assertEqual(0, mfd.focus)

    def test_focus_evicted_by_appendleft(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=3, focus=2)
        mfd.appendleft(0)  # evicts tail (the focus item)
        self.assertEqual([0, 1, 2], list(mfd))
        self.assertEqual(2, mfd.focus)

    def test_focus_shift_without_eviction(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], focus=1)
        mfd.appendleft(0)
        self.assertEqual([0, 1, 2, 3], list(mfd))
        self.assertEqual(2, mfd.focus)

    def test_rotate_positive(self) -> None:
        mfd = urwid.MonitoredFocusDeque([0, 1, 2, 3, 4], focus=0)
        mfd.rotate(1)
        self.assertEqual([4, 0, 1, 2, 3], list(mfd))
        self.assertEqual(1, mfd.focus)

    def test_rotate_negative(self) -> None:
        mfd = urwid.MonitoredFocusDeque([0, 1, 2, 3, 4], focus=0)
        mfd.rotate(-1)
        self.assertEqual([1, 2, 3, 4, 0], list(mfd))
        self.assertEqual(4, mfd.focus)

    def test_clear_focus_is_none(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], focus=1)
        mfd.clear()
        self.assertIsNone(mfd.focus)

    def test_maxlen_zero(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=0)
        self.assertIsNone(mfd.focus)
        mfd.append(1)
        self.assertEqual(0, len(mfd))
        self.assertIsNone(mfd.focus)


class WrapAroundTest(unittest.TestCase):
    def test_simple_deque_walker_wrap_true(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3], wrap_around=True)
        self.assertEqual(0, walker.next_position(2))
        self.assertEqual(2, walker.prev_position(0))

    def test_simple_deque_walker_wrap_false(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3], wrap_around=False)
        with self.assertRaises(IndexError):
            walker.next_position(2)
        with self.assertRaises(IndexError):
            walker.prev_position(0)

    def test_simple_focus_deque_walker_wrap_true(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([1, 2, 3], wrap_around=True)
        self.assertEqual(0, walker.next_position(2))
        self.assertEqual(2, walker.prev_position(0))

    def test_simple_focus_deque_walker_wrap_false(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([1, 2, 3], wrap_around=False)
        with self.assertRaises(IndexError):
            walker.next_position(2)
        with self.assertRaises(IndexError):
            walker.prev_position(0)


class ListBoxIntegrationTest(unittest.TestCase):
    def test_listbox_with_simple_focus_deque_walker(self) -> None:
        texts = [urwid.Text(str(num)) for num in range(5)]
        walker = urwid.SimpleFocusDequeWalker(texts, maxlen=3)
        lb = urwid.ListBox(walker)

        # Only the last 3 items should have survived construction eviction.
        self.assertEqual(3, len(lb.body))

        lb.body.append(urwid.Text("new"))
        self.assertEqual(3, len(lb.body))
        self.assertTrue(0 <= lb.focus_position < len(lb.body))

    def test_signal_connected(self) -> None:
        lb = urwid.ListBox([])
        lb.body = urwid.SimpleDequeWalker([])
        self.assertEqual(
            lb.body._urwid_signals["modified"][0][1],
            lb._invalidate,
            "outdated canvas cache reuse after ListWalker's contents modified",
        )

    def test_signal_connected_focus(self) -> None:
        lb = urwid.ListBox([])
        lb.body = urwid.SimpleFocusDequeWalker([])
        self.assertEqual(
            lb.body._urwid_signals["modified"][0][1],
            lb._invalidate,
            "outdated canvas cache reuse after ListWalker's contents modified",
        )


if __name__ == "__main__":
    unittest.main()
