from __future__ import annotations

import collections
import decimal
import math
import unittest
import warnings

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


class MonitoredFocusDequeModifiedCallbackTest(unittest.TestCase):
    """The modified callback runs once, after both the contents and the focus are updated."""

    def test_callback_sees_final_focus(self) -> None:
        """Every mutating operation notifies once, with the contents and the focus already final."""
        operations = {
            "del item": lambda md: md.__delitem__(0),
            "set item": lambda md: md.__setitem__(2, 7),
            "append": lambda md: md.append(6),
            "appendleft": lambda md: md.appendleft(-1),
            "extend": lambda md: md.extend([6, 7]),
            "iadd": lambda md: md.__iadd__([6, 7]),
            "extendleft": lambda md: md.extendleft([-1, -2]),
            "insert": lambda md: md.insert(0, -1),
            "pop": lambda md: md.pop(),
            "popleft": lambda md: md.popleft(),
            "remove": lambda md: md.remove(0),
            "reverse": lambda md: md.reverse(),
            "rotate": lambda md: md.rotate(2),
            "clear": lambda md: md.clear(),
        }
        for maxlen in (None, 6):
            for name, operation in operations.items():
                if maxlen is not None and name == "insert":
                    continue  # deque.insert raises on a full bounded deque
                with self.subTest(name, maxlen=maxlen):
                    md = urwid.MonitoredFocusDeque(range(6), maxlen, focus=2)
                    seen = []
                    md.set_modified_callback(lambda md=md, seen=seen: seen.append((list(md), md.focus)))
                    operation(md)
                    self.assertEqual([(list(md), md.focus)], seen)

    def test_iadd_keeps_focused_item_like_extend(self) -> None:
        """In-place addition evicts from a bounded deque and keeps the focused item, the same as extend."""
        for maxlen in (None, 4):
            with self.subTest(maxlen=maxlen):
                extended = urwid.MonitoredFocusDeque("abc", maxlen, focus=2)
                extended.extend("xyz")
                added = urwid.MonitoredFocusDeque("abc", maxlen, focus=2)
                added += "xyz"
                self.assertIsInstance(added, urwid.MonitoredFocusDeque)
                self.assertEqual((list(extended), extended.focus), (list(added), added.focus))
                self.assertEqual("c", added[added.focus])

    def test_focus_set_by_callback_is_kept(self) -> None:
        """A focus set by the modified callback is not overwritten afterwards."""
        md = urwid.MonitoredFocusDeque(range(6), focus=2)
        md.set_modified_callback(lambda: setattr(md, "focus", 0) if md.focus else None)
        md.appendleft(-1)
        self.assertEqual(0, md.focus)

    def test_insert_by_callback_keeps_focus_item(self) -> None:
        """An insertion made by the modified callback keeps the focus on the same item."""
        md = urwid.MonitoredFocusDeque(["a", "b", "c", "d"], focus=2)
        md.set_modified_callback(lambda: md.appendleft("x") if len(md) == 3 else None)
        md.popleft()
        self.assertEqual(["x", "b", "c", "d"], list(md))
        self.assertEqual("c", md[md.focus])

    def test_walker_signal_sees_final_focus(self) -> None:
        """A ListBox rendered from the walker's modified signal shows the new focus item."""
        walker = urwid.SimpleFocusDequeWalker([urwid.Text(str(num)) for num in range(3)])
        walker.focus = 2
        listbox = urwid.ListBox(walker)
        seen = []

        def on_modified() -> None:
            seen.append((walker.get_focus()[1], listbox.render((5, 1), focus=True).text))

        urwid.connect_signal(walker, "modified", on_modified)
        walker.pop()
        self.assertEqual([(1, [b"1    "])], seen)


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


class _Index:
    """Integer-like object that supports only ``__index__``, as ``deque.insert()`` requires."""

    def __index__(self) -> int:
        return 1


class MonitoredDequeInsertIndexTest(unittest.TestCase):
    """Check ``insert()`` index conversion against ``collections.deque.insert()``."""

    classes = (urwid.MonitoredDeque, urwid.MonitoredFocusDeque)

    def test_integer_index_does_not_warn(self) -> None:
        """Insert at an ``int``, a ``bool`` and an ``__index__`` object like ``deque`` does, with no warning."""
        for cls in self.classes:
            for index in (1, True, _Index()):
                with self.subTest(cls=cls.__name__, index=index), warnings.catch_warnings():
                    warnings.simplefilter("error")
                    reference = collections.deque([0, 1, 2])
                    reference.insert(index, 9)
                    deq = cls([0, 1, 2])
                    deq.insert(index, 9)
                    self.assertEqual(list(reference), list(deq))

    def test_non_integer_index_raises(self) -> None:
        """Raise ``TypeError`` for an index without ``__index__`` like ``deque`` does, with no change."""
        for cls in self.classes:
            for index in (1.5, decimal.Decimal(1), "1", None, "abc", math.inf):
                with self.subTest(cls=cls.__name__, index=index):
                    with self.assertRaises(TypeError):
                        collections.deque([0, 1, 2]).insert(index, 9)
                    deq = cls([0, 1, 2])
                    with self.assertRaises(TypeError):
                        deq.insert(index, 9)
                    self.assertEqual([0, 1, 2], list(deq))


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


class SimpleDequeWalkerFocusTest(unittest.TestCase):
    def test_contents_returns_self(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        self.assertIs(walker, walker.contents)

    def test_set_focus(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        walker.set_focus(2)
        self.assertEqual(2, walker.focus)

    def test_set_focus_out_of_range_raises(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        with self.assertRaises(IndexError):
            walker.set_focus(3)
        with self.assertRaises(IndexError):
            walker.set_focus(-1)

    def test_modified_clamps_focus_on_shrink(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        walker.focus = 2
        walker.pop()
        walker.pop()
        self.assertEqual(0, walker.focus)

    def test_next_prev_position(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        self.assertEqual(1, walker.next_position(0))
        self.assertEqual(0, walker.prev_position(1))

    def test_positions(self) -> None:
        walker = urwid.SimpleDequeWalker([1, 2, 3])
        self.assertEqual([0, 1, 2], list(walker.positions()))
        self.assertEqual([2, 1, 0], list(walker.positions(reverse=True)))


class SimpleFocusDequeWalkerFocusTest(unittest.TestCase):
    def test_set_focus(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([1, 2, 3])
        walker.set_focus(2)
        self.assertEqual(2, walker.focus)

    def test_next_prev_position(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([1, 2, 3])
        self.assertEqual(1, walker.next_position(0))
        self.assertEqual(0, walker.prev_position(1))

    def test_positions(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([1, 2, 3])
        self.assertEqual([0, 1, 2], list(walker.positions()))
        self.assertEqual([2, 1, 0], list(walker.positions(reverse=True)))


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
            urwid.ListBox._invalidate,
            "outdated canvas cache reuse after ListWalker's contents modified",
        )

    def test_signal_connected_focus(self) -> None:
        lb = urwid.ListBox([])
        lb.body = urwid.SimpleFocusDequeWalker([])
        self.assertEqual(
            lb.body._urwid_signals["modified"][0][1],
            urwid.ListBox._invalidate,
            "outdated canvas cache reuse after ListWalker's contents modified",
        )


if __name__ == "__main__":
    unittest.main()
