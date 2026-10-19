from __future__ import annotations

import collections
import decimal
import fractions
import math
import sys
import unittest
import warnings

import urwid
from tests.util import CountingIndex, Index

IS_PYPY = sys.implementation.name == "pypy"


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

        md.extend([1, 2])
        md *= 2
        self.assertEqual(10, counter["count"])
        expected = collections.deque([1, 2], maxlen=3)
        expected *= 2
        self.assertEqual(list(expected), list(md))


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

    def test_rotate(self) -> None:
        for rotation, contents, focus in ((1, [4, 0, 1, 2, 3], 1), (-1, [1, 2, 3, 4, 0], 4)):
            with self.subTest(rotation=rotation):
                mfd = urwid.MonitoredFocusDeque([0, 1, 2, 3, 4], focus=0)
                mfd.rotate(rotation)
                self.assertEqual(contents, list(mfd))
                self.assertEqual(focus, mfd.focus)

    def test_clear_focus_is_none(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], focus=1)
        mfd.clear()
        self.assertIsNone(mfd.focus)

    def test_imul(self) -> None:
        mfd = urwid.MonitoredFocusDeque([1, 2, 3], focus=2)
        seen = []
        mfd.set_modified_callback(lambda: seen.append((list(mfd), mfd.focus)))
        mfd *= 2
        self.assertEqual([([1, 2, 3, 1, 2, 3], 2)], seen)
        mfd *= 0
        self.assertEqual([([1, 2, 3, 1, 2, 3], 2), ([], None)], seen)
        mfd.append(1)
        self.assertEqual(0, mfd.focus)

    def test_imul_bounded_by_maxlen(self) -> None:
        """A bounded deque keeps only maxlen items; a huge count is not repeated item by item on any interpreter."""
        for focus, count in ((2, 2), (0, 2), (2, 5)):
            with self.subTest(focus=focus, count=count):
                mfd = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=4, focus=focus)
                expected = collections.deque([1, 2, 3], maxlen=4)
                expected *= count
                mfd *= count
                self.assertEqual(list(expected), list(mfd))
                self.assertEqual(max(0, focus - (3 * count - 4)), mfd.focus)

        mfd = urwid.MonitoredFocusDeque([1, 2, 3], maxlen=4, focus=2)
        mfd *= 2**61
        self.assertEqual([3, 1, 2, 3], list(mfd))
        self.assertEqual(0, mfd.focus)
        md = urwid.MonitoredDeque([1, 2, 3], maxlen=4)
        md *= 2**61
        self.assertEqual([3, 1, 2, 3], list(md))

    def test_focus_out_of_range_rejected(self) -> None:
        for focus in (3, -1):
            with self.subTest(focus=focus), self.assertRaises(IndexError):
                urwid.MonitoredFocusDeque([1, 2, 3], focus=focus)
        with self.assertRaises(IndexError):
            urwid.MonitoredFocusDeque([1, 2, 3], maxlen=2, focus=2)  # only two items are kept
        with self.assertRaises(TypeError):
            urwid.MonitoredFocusDeque([1, 2, 3], focus="1")

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


class _IntOnly:
    """Object that supports only ``__int__``."""

    def __int__(self) -> int:
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
        strict = (1.5, "1", None, "abc", math.inf, b"1", 1j)
        int_only = (decimal.Decimal(1), fractions.Fraction(7, 2), _IntOnly())
        for cls in self.classes:
            for index in (*strict, *int_only):
                with self.subTest(cls=cls.__name__, index=index):
                    deq = cls([0, 1, 2])
                    with self.assertRaises(TypeError):
                        deq.insert(index, 9)
                    self.assertEqual([0, 1, 2], list(deq))
                    if IS_PYPY and any(index is lenient for lenient in int_only):
                        self.skipTest("PyPy deque.insert() converts an index that has only __int__")
                    with self.assertRaises(TypeError):
                        collections.deque([0, 1, 2]).insert(index, 9)


class MonitoredFocusDequeIndexTest(unittest.TestCase):
    def test_base_rotation_uses_index(self) -> None:
        items = urwid.MonitoredDeque(["a", "b", "c"])
        seen = []
        items.set_modified_callback(lambda: seen.append(list(items)))
        index = CountingIndex(1)
        items.rotate(index)
        self.assertEqual(["c", "a", "b"], list(items))
        self.assertEqual([["c", "a", "b"]], seen)
        self.assertEqual(1, index.calls)

    def test_deletion_preserves_focus(self) -> None:
        for value in (0, -1):
            with self.subTest(index=value):
                items = urwid.MonitoredFocusDeque(["a", "b", "c"], focus=1)
                expected = list(items)
                del expected[value]
                del items[Index(value)]
                self.assertEqual(expected, list(items))
                self.assertEqual(expected.index("b"), items.focus)

    def test_deletion_evaluates_index_once(self) -> None:
        items = urwid.MonitoredFocusDeque(["a", "b", "c"], focus=1)
        index = CountingIndex()
        del items[index]
        self.assertEqual(1, index.calls)
        self.assertEqual(0, items.focus)

    def test_rotation_uses_index(self) -> None:
        for value in (0, 1, -1, 4):
            with self.subTest(rotation=value):
                items = urwid.MonitoredFocusDeque(["a", "b", "c"], focus=1)
                items.rotate(Index(value))
                self.assertEqual("b", items[items.focus])
                self.assertEqual((1 + value) % 3, items.focus)


if __name__ == "__main__":
    unittest.main()
