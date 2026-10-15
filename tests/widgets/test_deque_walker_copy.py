from __future__ import annotations

import copy
import operator
import pickle
import unittest
from collections import deque

import urwid


class ContentsOnlyWalker(urwid.SimpleDequeWalker):
    def __init__(self, contents=()) -> None:
        super().__init__(contents, wrap_around=True)


class ContentsOnlyFocusWalker(urwid.SimpleFocusDequeWalker):
    def __init__(self, contents=()) -> None:
        super().__init__(contents, wrap_around=True)


class DequeWalkerCopyTest(unittest.TestCase):
    def test_capacity_and_wrapping(self) -> None:
        operations = {
            "copy": lambda items: items.copy(),
            "shallow": copy.copy,
            "deep": copy.deepcopy,
            "repeat": lambda items: items * 2,
            "reverse_repeat": lambda items: 2 * items,
            "concatenate": lambda items: items + deque([4, 5]),
        }
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            for limit in (None, 0, 2, 4):
                for wrap in (False, True):
                    for name, operation in operations.items():
                        with self.subTest(container=container.__name__, maxlen=limit, wrap=wrap, operation=name):
                            original = container([1, 2, 3], wrap_around=wrap, maxlen=limit)
                            expected = operation(deque(original, maxlen=limit))
                            result = operation(original)
                            self.assertIsInstance(result, container)
                            self.assertIsNot(original, result)
                            self.assertEqual(list(expected), list(result))
                            self.assertEqual(limit, result.maxlen)
                            self.assertIs(wrap, result.wrap_around)
                            self.assertEqual(list(deque([1, 2, 3], maxlen=limit)), list(original))

    def test_copy_depth(self) -> None:
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                item = [1]
                original = container([item], maxlen=2)
                for result in (original.copy(), copy.copy(original), original * 2, original + deque([item])):
                    self.assertIs(item, result[0])
                result = copy.deepcopy(original)
                self.assertIsNot(item, result[0])
                self.assertEqual(item, result[0])

    def test_pickle_retains_configuration(self) -> None:
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            for limit in (None, 0, 2, 4):
                for wrap in (False, True):
                    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
                        with self.subTest(container=container.__name__, maxlen=limit, wrap=wrap, protocol=protocol):
                            original = container([1, 2, 3], wrap_around=wrap, maxlen=limit)
                            if len(original) > 1:
                                original.set_focus(1)
                            result = pickle.loads(pickle.dumps(original, protocol=protocol))
                            self.assertIsInstance(result, container)
                            self.assertEqual(list(original), list(result))
                            self.assertEqual(limit, result.maxlen)
                            self.assertIs(wrap, result.wrap_around)
                            self.assertEqual(original.focus, result.focus)

    def test_copy_stays_bounded(self) -> None:
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2], maxlen=2)
                for result in (original.copy(), copy.copy(original), copy.deepcopy(original)):
                    result.append(3)
                    self.assertEqual([2, 3], list(result))
                    self.assertEqual([1, 2], list(original))

    def test_arithmetic_does_not_notify_original(self) -> None:
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3], maxlen=4)
                original.set_focus(1)
                seen = []
                urwid.connect_signal(original, "modified", lambda: seen.append(True))
                original * 2
                2 * original
                original + deque([4, 5])
                self.assertEqual([], seen)
                self.assertEqual([1, 2, 3], list(original))
                self.assertEqual(1, original.focus)

    def test_invalid_operands(self) -> None:
        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            for operation, operand in ((operator.add, [4]), (operator.mul, 1.5), (operator.mul, "2")):
                with self.subTest(container=container.__name__, operation=operation, operand=operand):
                    original = container([1, 2, 3], maxlen=4)
                    with self.assertRaises(TypeError):
                        operation(original, operand)
                    self.assertEqual([1, 2, 3], list(original))

    def test_index_multiplier_is_evaluated_once(self) -> None:
        class Index:
            calls = 0

            def __index__(self) -> int:
                self.calls += 1
                return 2

        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3], maxlen=4)
                multiplier = Index()
                result = original * multiplier
                self.assertEqual([3, 1, 2, 3], list(result))
                self.assertEqual(1, multiplier.calls)

    def test_reflected_operand(self) -> None:
        class Scale:
            def __rmul__(self, other):
                return other

        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3], maxlen=4)
                self.assertIs(original, original * Scale())

    def test_left_operand_defers_to_repetition(self) -> None:
        class Index:
            def __mul__(self, other):
                return NotImplemented

            def __index__(self) -> int:
                return 2

        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                result = Index() * container([1, 2, 3], maxlen=4, wrap_around=True)
                self.assertEqual([3, 1, 2, 3], list(result))
                self.assertEqual(4, result.maxlen)
                self.assertIs(True, result.wrap_around)

    def test_invalid_index_is_evaluated_once(self) -> None:
        class Index:
            calls = 0

            def __index__(self) -> int:
                self.calls += 1
                raise TypeError("invalid index")

        for container in (urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3], maxlen=4)
                multiplier = Index()
                with self.assertRaises(TypeError):
                    original * multiplier
                self.assertEqual(1, multiplier.calls)
                self.assertEqual([1, 2, 3], list(original))

    def test_subclass_is_retained(self) -> None:
        class Walker(urwid.SimpleDequeWalker):
            pass

        class FocusWalker(urwid.SimpleFocusDequeWalker):
            pass

        for container in (Walker, FocusWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3], maxlen=4, wrap_around=True)
                for result in (original.copy(), original * 2, 2 * original, original + deque([4])):
                    self.assertIs(type(result), container)
                    self.assertEqual(4, result.maxlen)
                    self.assertIs(True, result.wrap_around)

    def test_unbounded_subclass_with_contents_only_constructor(self) -> None:
        class Walker(urwid.SimpleDequeWalker):
            def __init__(self, contents) -> None:
                super().__init__(contents, wrap_around=True)

        class FocusWalker(urwid.SimpleFocusDequeWalker):
            def __init__(self, contents) -> None:
                super().__init__(contents, wrap_around=True)

        for container in (Walker, FocusWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3])
                for result in (original.copy(), copy.copy(original), original * 2, 2 * original):
                    self.assertIs(type(result), container)
                    self.assertIsNone(result.maxlen)
                    self.assertIs(True, result.wrap_around)

    def test_unbounded_subclass_reconstruction(self) -> None:
        for container in (ContentsOnlyWalker, ContentsOnlyFocusWalker):
            with self.subTest(container=container.__name__):
                original = container([1, 2, 3])
                for result in (copy.deepcopy(original), pickle.loads(pickle.dumps(original))):
                    self.assertIs(type(result), container)
                    self.assertEqual([1, 2, 3], list(result))
                    self.assertIsNone(result.maxlen)
                    self.assertIs(True, result.wrap_around)


if __name__ == "__main__":
    unittest.main()
