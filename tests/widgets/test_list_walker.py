from __future__ import annotations

import operator
import unittest

import urwid


class ListWalkerBaseTest(unittest.TestCase):
    """Exercise the default get_focus/get_next/get_prev implementations on the base class."""

    class Container(urwid.ListWalker):
        def __init__(self, items: list[str], focus: int = 0) -> None:
            self.items = items
            self.focus = focus

        def __getitem__(self, position: int) -> str:
            return self.items[position]

        def next_position(self, position: int) -> int:
            if position + 1 >= len(self.items):
                raise IndexError
            return position + 1

        def prev_position(self, position: int) -> int:
            if position <= 0:
                raise IndexError
            return position - 1

    def test_get_focus(self) -> None:
        walker = self.Container(["a", "b", "c"], focus=1)
        self.assertEqual(("b", 1), walker.get_focus())

    def test_get_focus_invalid_position(self) -> None:
        walker = self.Container(["a", "b", "c"], focus=99)
        self.assertEqual((None, None), walker.get_focus())

    def test_get_next(self) -> None:
        walker = self.Container(["a", "b", "c"])
        self.assertEqual(("b", 1), walker.get_next(0))

    def test_get_next_out_of_range(self) -> None:
        walker = self.Container(["a", "b", "c"])
        self.assertEqual((None, None), walker.get_next(2))

    def test_get_prev(self) -> None:
        walker = self.Container(["a", "b", "c"])
        self.assertEqual(("a", 0), walker.get_prev(1))

    def test_get_prev_out_of_range(self) -> None:
        walker = self.Container(["a", "b", "c"])
        self.assertEqual((None, None), walker.get_prev(0))


class SimpleListWalkerConstructionTest(unittest.TestCase):
    def test_from_generator(self) -> None:
        walker = urwid.SimpleListWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))
        self.assertEqual(0, walker.focus)

    def test_non_iterable_raises(self) -> None:
        with self.assertRaises(urwid.ListWalkerError):
            urwid.SimpleListWalker(123)

    def test_contents_property_returns_self(self) -> None:
        walker = urwid.SimpleListWalker([1, 2, 3])
        self.assertIs(walker, walker.contents)

    def test_set_modified_callback_not_implemented(self) -> None:
        walker = urwid.SimpleListWalker([1, 2, 3])
        with self.assertRaises(NotImplementedError):
            walker.set_modified_callback(lambda: None)


class SimpleListWalkerMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.walker = urwid.SimpleListWalker([0, 1, 2, 3, 4])
        self.modified_count = 0
        urwid.connect_signal(self.walker, "modified", self._on_modified)

    def _on_modified(self) -> None:
        self.modified_count += 1

    def test_insert_triggers_modified(self) -> None:
        self.walker.insert(0, -1)
        self.assertEqual(1, self.modified_count)
        self.assertEqual([-1, 0, 1, 2, 3, 4], list(self.walker))

    def test_append_triggers_modified(self) -> None:
        self.walker.append(5)
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 1, 2, 3, 4, 5], list(self.walker))

    def test_extend_triggers_modified(self) -> None:
        self.walker.extend([5, 6])
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 1, 2, 3, 4, 5, 6], list(self.walker))

    def test_pop_triggers_modified(self) -> None:
        self.walker.pop()
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 1, 2, 3], list(self.walker))

    def test_remove_triggers_modified(self) -> None:
        self.walker.remove(2)
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 1, 3, 4], list(self.walker))

    def test_sort_triggers_modified(self) -> None:
        self.walker[:] = [3, 1, 2, 0, 4]
        self.modified_count = 0
        self.walker.sort()
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 1, 2, 3, 4], list(self.walker))

    def test_del_slice_triggers_modified(self) -> None:
        del self.walker[1:3]
        self.assertEqual(1, self.modified_count)
        self.assertEqual([0, 3, 4], list(self.walker))

    def test_operators_returning_a_new_list_do_not_trigger_modified(self) -> None:
        """Do not notify for ``+`` and ``n * walker``, which return a new list and leave the walker unchanged."""
        for name, operation, expected in (
            ("add", lambda walker: operator.add(walker, [5]), [0, 1, 2, 3, 4, 5]),
            ("rmul", lambda walker: operator.mul(2, walker), [0, 1, 2, 3, 4] * 2),
        ):
            with self.subTest(name):
                self.modified_count = 0
                self.assertEqual(expected, operation(self.walker))
                self.assertEqual(0, self.modified_count)
                self.assertEqual([0, 1, 2, 3, 4], list(self.walker))

    def test_negative_index_getitem(self) -> None:
        self.assertEqual(4, self.walker[-1])

    def test_negative_index_setitem(self) -> None:
        self.walker[-1] = 40
        self.assertEqual([0, 1, 2, 3, 40], list(self.walker))

    def test_slicing(self) -> None:
        self.assertEqual([1, 2, 3], self.walker[1:4])

    def test_focus_adjusted_when_shrunk_past_focus(self) -> None:
        self.walker.focus = 4
        del self.walker[1:]
        self.assertEqual(0, self.walker.focus)

    def test_focus_not_adjusted_when_still_valid(self) -> None:
        self.walker.focus = 1
        self.walker.append(5)
        self.assertEqual(1, self.walker.focus)

    def test_focus_adjusted_on_empty_list(self) -> None:
        self.walker.focus = 4
        del self.walker[:]
        self.assertEqual(0, self.walker.focus)


class SimpleListWalkerFocusApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.walker = urwid.SimpleListWalker([0, 1, 2])

    def test_set_focus(self) -> None:
        self.walker.set_focus(2)
        self.assertEqual(2, self.walker.focus)

    def test_set_focus_out_of_range(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.set_focus(5)

    def test_set_focus_negative(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.set_focus(-1)

    def test_next_position(self) -> None:
        self.assertEqual(1, self.walker.next_position(0))

    def test_next_position_at_end_no_wrap(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.next_position(2)

    def test_next_position_at_end_wrap_around(self) -> None:
        walker = urwid.SimpleListWalker([0, 1, 2], wrap_around=True)
        self.assertEqual(0, walker.next_position(2))

    def test_prev_position(self) -> None:
        self.assertEqual(0, self.walker.prev_position(1))

    def test_prev_position_at_start_no_wrap(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.prev_position(0)

    def test_prev_position_at_start_wrap_around(self) -> None:
        walker = urwid.SimpleListWalker([0, 1, 2], wrap_around=True)
        self.assertEqual(2, walker.prev_position(0))

    def test_positions(self) -> None:
        self.assertEqual([0, 1, 2], list(self.walker.positions()))

    def test_positions_reverse(self) -> None:
        self.assertEqual([2, 1, 0], list(self.walker.positions(reverse=True)))


class SimpleFocusListWalkerConstructionTest(unittest.TestCase):
    def test_from_generator(self) -> None:
        walker = urwid.SimpleFocusListWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))

    def test_non_iterable_raises(self) -> None:
        with self.assertRaises(urwid.ListWalkerError):
            urwid.SimpleFocusListWalker(123)

    def test_set_modified_callback_not_implemented(self) -> None:
        walker = urwid.SimpleFocusListWalker([1, 2, 3])
        with self.assertRaises(NotImplementedError):
            walker.set_modified_callback(lambda: None)


class SimpleFocusListWalkerFocusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.walker = urwid.SimpleFocusListWalker([0, 1, 2, 3, 4])
        self.modified_count = 0
        urwid.connect_signal(self.walker, "modified", self._on_modified)

    def _on_modified(self) -> None:
        self.modified_count += 1

    def test_set_focus(self) -> None:
        self.walker.set_focus(3)
        self.assertEqual(3, self.walker.focus)
        self.assertEqual(1, self.modified_count)

    def test_focus_tracks_insert_before_focus(self) -> None:
        self.walker.set_focus(2)
        self.walker.insert(0, -1)
        self.assertEqual(3, self.walker.focus)

    def test_focus_tracks_removal_before_focus(self) -> None:
        self.walker.set_focus(3)
        del self.walker[0]
        self.assertEqual(2, self.walker.focus)

    def test_next_position(self) -> None:
        self.assertEqual(1, self.walker.next_position(0))

    def test_next_position_at_end_no_wrap(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.next_position(4)

    def test_next_position_at_end_wrap_around(self) -> None:
        walker = urwid.SimpleFocusListWalker([0, 1, 2], wrap_around=True)
        self.assertEqual(0, walker.next_position(2))

    def test_prev_position(self) -> None:
        self.assertEqual(1, self.walker.prev_position(2))

    def test_prev_position_at_start_no_wrap(self) -> None:
        with self.assertRaises(IndexError):
            self.walker.prev_position(0)

    def test_prev_position_at_start_wrap_around(self) -> None:
        walker = urwid.SimpleFocusListWalker([0, 1, 2], wrap_around=True)
        self.assertEqual(2, walker.prev_position(0))

    def test_positions(self) -> None:
        self.assertEqual([0, 1, 2, 3, 4], list(self.walker.positions()))

    def test_positions_reverse(self) -> None:
        self.assertEqual([4, 3, 2, 1, 0], list(self.walker.positions(reverse=True)))

    def test_next_prev_position_on_empty_list(self) -> None:
        walker = urwid.SimpleFocusListWalker([])
        with self.assertRaises(IndexError):
            walker.next_position(0)
        with self.assertRaises(IndexError):
            walker.prev_position(0)


class MonitoredFocusListModifiedCallbackTest(unittest.TestCase):
    """The modified callback runs once, after both the contents and the focus are updated."""

    def test_callback_sees_final_focus(self) -> None:
        """Every mutating operation notifies once, with the contents and the focus already final."""
        operations = {
            "del item": lambda ml: ml.__delitem__(0),
            "del slice": lambda ml: ml.__delitem__(slice(0, 2)),
            "set item": lambda ml: ml.__setitem__(2, 7),
            "set slice": lambda ml: ml.__setitem__(slice(0, 1), [8, 9]),
            "imul": lambda ml: ml.__imul__(0),
            "append": lambda ml: ml.append(6),
            "extend": lambda ml: ml.extend([6, 7]),
            "insert": lambda ml: ml.insert(0, -1),
            "pop": lambda ml: ml.pop(0),
            "remove": lambda ml: ml.remove(0),
            "reverse": lambda ml: ml.reverse(),
            "sort": lambda ml: ml.sort(reverse=True),
            "clear": lambda ml: ml.clear(),
        }
        for name, operation in operations.items():
            with self.subTest(name):
                ml = urwid.MonitoredFocusList(range(6), focus=2)
                seen = []
                ml.set_modified_callback(lambda ml=ml, seen=seen: seen.append((list(ml), ml.focus)))
                operation(ml)
                self.assertEqual([(list(ml), ml.focus)], seen)

    def test_focus_set_by_callback_is_kept(self) -> None:
        """A focus set by the modified callback is not overwritten afterwards."""
        ml = urwid.MonitoredFocusList(range(6), focus=2)
        ml.set_modified_callback(lambda: setattr(ml, "focus", 0) if ml.focus else None)
        ml.insert(0, -1)
        self.assertEqual(0, ml.focus)

    def test_insert_by_callback_keeps_focus_item(self) -> None:
        """An insertion made by the modified callback keeps the focus on the same item."""
        ml = urwid.MonitoredFocusList(["a", "b", "c", "d"], focus=2)
        ml.set_modified_callback(lambda: ml.insert(0, "x") if len(ml) == 3 else None)
        del ml[0]
        self.assertEqual(["x", "b", "c", "d"], list(ml))
        self.assertEqual("c", ml[ml.focus])

    def test_walker_signal_sees_final_focus(self) -> None:
        """A ListBox rendered from the walker's modified signal shows the new focus item."""
        walker = urwid.SimpleFocusListWalker([urwid.Text(str(num)) for num in range(3)])
        walker.focus = 2
        listbox = urwid.ListBox(walker)
        seen = []

        def on_modified() -> None:
            seen.append((walker.get_focus()[1], listbox.render((5, 1), focus=True).text))

        urwid.connect_signal(walker, "modified", on_modified)
        del walker[2]
        self.assertEqual([(1, [b"1    "])], seen)


if __name__ == "__main__":
    unittest.main()
