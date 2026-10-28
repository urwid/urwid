from __future__ import annotations

import copy
import functools
import operator
import pickle
import typing
import unittest

import urwid
from tests.util import CountingIndex, Index

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class MonitoredFocusListIndexTest(unittest.TestCase):
    def test_repetition_rejects_non_indices(self) -> None:
        for multiplier in (1.5, "2"):
            with self.subTest(multiplier=multiplier):
                items = urwid.MonitoredFocusList(["a", "b", "c"], focus=1)
                validated = []
                modified = []
                items.set_validate_contents_modified(lambda *args: validated.append(args))
                items.set_modified_callback(lambda: modified.append(True))
                with self.assertRaises(TypeError):
                    items *= multiplier
                self.assertEqual(["a", "b", "c"], items)
                self.assertEqual(1, items.focus)
                self.assertEqual([], validated)
                self.assertEqual([], modified)

    def test_mutation_rejects_non_indices_before_validation(self) -> None:
        operations = {
            "delete": operator.delitem,
            "pop": lambda items, index: items.pop(index),
            "set": lambda items, index: operator.setitem(items, index, "replacement"),
        }
        for name, operation in operations.items():
            for value in (1.5, "1"):
                with self.subTest(operation=name, index=value):
                    items = urwid.MonitoredFocusList(["a", "b", "c"], focus=1)
                    validated = []
                    modified = []
                    items.set_validate_contents_modified(lambda *args: validated.append(args))
                    items.set_modified_callback(lambda: modified.append(True))
                    with self.assertRaises(TypeError):
                        operation(items, value)
                    self.assertEqual(["a", "b", "c"], items)
                    self.assertEqual(1, items.focus)
                    self.assertEqual([], validated)
                    self.assertEqual([], modified)

    def test_repetition_uses_index(self) -> None:
        for multiplier in (0, 1, 2):
            with self.subTest(multiplier=multiplier):
                items = urwid.MonitoredFocusList(["a", "b"])
                items *= Index(multiplier)
                self.assertEqual(["a", "b"] * multiplier, items)
                self.assertEqual(0 if multiplier else None, items.focus)

    def test_mutation_uses_index_for_validation_and_focus(self) -> None:
        operations = {
            "delete": operator.delitem,
            "pop": lambda items, index: items.pop(index),
            "set": lambda items, index: operator.setitem(items, index, "replacement"),
        }
        for name, operation in operations.items():
            for index in (0, -1):
                with self.subTest(operation=name, index=index):
                    items = urwid.MonitoredFocusList(["a", "b", "c"], focus=1)
                    expected = list(items)
                    operation(expected, index)
                    seen = []
                    items.set_validate_contents_modified(lambda indices, new: seen.append(indices))
                    operation(items, Index(index))
                    normalized = index % 3
                    self.assertEqual([(normalized, normalized + 1, 1)], seen)
                    self.assertEqual(expected, items)
                    self.assertEqual(expected.index("b"), items.focus)

    def test_index_is_evaluated_once(self) -> None:
        operations = {
            "delete": operator.delitem,
            "pop": lambda items, index: items.pop(index),
            "set": lambda items, index: operator.setitem(items, index, "replacement"),
        }
        for name, operation in operations.items():
            with self.subTest(operation=name):
                items = urwid.MonitoredFocusList(["a", "b", "c"], focus=1)
                index = CountingIndex()
                operation(items, index)
                self.assertEqual(1, index.calls)


class MonitoredFocusListConstructionTest(unittest.TestCase):
    def test_focus_out_of_range_rejected(self) -> None:
        for focus in (3, -1):
            with self.subTest(focus=focus), self.assertRaises(IndexError):
                urwid.MonitoredFocusList([1, 2, 3], focus=focus)
        with self.assertRaises(TypeError):
            urwid.MonitoredFocusList([1, 2, 3], focus="1")

    def test_focus_ignored_when_empty(self) -> None:
        ml = urwid.MonitoredFocusList([], focus=5)
        ml.append(1)
        self.assertEqual(0, ml.focus)


class MonitoredFocusListValidationTest(unittest.TestCase):
    def test_iadd_is_validated(self) -> None:
        pile = urwid.Pile([urwid.Text("a")])
        contents = pile.contents
        with self.assertRaises(urwid.PileError):
            contents += ["bad"]
        self.assertEqual(1, len(pile.contents))

    def test_clear_reports_removed_range(self) -> None:
        ml = urwid.MonitoredFocusList([1, 2, 3])
        seen = []
        ml.set_validate_contents_modified(lambda indices, new_items: seen.append(indices))
        ml.clear()
        self.assertEqual([(0, 3, 1)], seen)


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
            "iadd": lambda ml: ml.__iadd__([6, 7]),
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


class MonitoredFocusListFocusMovedCallbackTest(unittest.TestCase):
    """The focus moved callback runs after the focus changed, once per operation."""

    def test_operations_report_once_with_final_state(self) -> None:
        """A change of the contents reports the old and the final focus once, with the contents already final."""
        operations: dict[str, tuple[Callable[[urwid.MonitoredFocusList[int]], object], int | None]] = {
            "del before focus": (lambda ml: ml.__delitem__(0), 1),
            "del after focus": (lambda ml: ml.__delitem__(4), 2),
            "set item": (lambda ml: ml.__setitem__(2, 7), 2),
            "insert before focus": (lambda ml: ml.insert(0, -1), 3),
            "append": (lambda ml: ml.append(6), 2),
            "reverse": (lambda ml: ml.reverse(), 3),
            "clear": (lambda ml: ml.clear(), None),
            "focus": (lambda ml: setattr(ml, "focus", 4), 4),
            "same focus": (lambda ml: setattr(ml, "focus", 2), 2),
        }
        for name, (operation, new_focus) in operations.items():
            with self.subTest(name):
                ml = urwid.MonitoredFocusList(range(6), focus=2)
                seen: list[tuple[int | None, int | None, list[int], int | None]] = []
                ml.set_focus_moved_callback(lambda old, new, ml=ml, seen=seen: seen.append((old, new, list(ml), ml.focus)))
                operation(ml)
                self.assertEqual(new_focus, ml.focus)
                self.assertEqual([] if new_focus == 2 else [(2, new_focus, list(ml), new_focus)], seen)

    def test_empty_list(self) -> None:
        """Emptying the list reports ``None`` as the new focus, and filling it reports ``None`` as the old one."""
        ml = urwid.MonitoredFocusList([1, 2], focus=1)
        seen: list[tuple[int | None, int | None]] = []
        ml.set_focus_moved_callback(lambda old, new: seen.append((old, new)))
        del ml[:]
        ml.extend([3, 4, 5])
        self.assertEqual([(1, None), (None, 2)], seen)

    def test_focus_set_by_modified_callback(self) -> None:
        """A focus the modified callback sets is reported once, together with the change."""
        ml = urwid.MonitoredFocusList(range(6), focus=2)
        ml.set_modified_callback(lambda: setattr(ml, "focus", 5) if ml.focus != 5 else None)
        seen: list[tuple[int | None, int | None]] = []
        ml.set_focus_moved_callback(lambda old, new: seen.append((old, new)))
        ml.insert(0, -1)
        self.assertEqual([(2, 5)], seen)

    def test_independent_of_focus_changed_callback(self) -> None:
        """Replacing the focus changed callback keeps the focus moved callback, which runs after it."""
        ml = urwid.MonitoredFocusList(range(3), focus=0)
        order: list[str] = []
        ml.set_focus_moved_callback(lambda old, new: order.append(f"moved {old} {new} {ml.focus}"))
        ml.set_focus_changed_callback(lambda new: order.append(f"changed {new} {ml.focus}"))
        ml.focus = 1
        self.assertEqual(["changed 1 0", "moved 0 1 1"], order)

    def test_applied_change_reported_when_a_callback_raises(self) -> None:
        """A change whose modified callback raises is still reported, once."""
        ml = urwid.MonitoredFocusList(range(6), focus=3)
        seen: list[tuple[int | None, int | None]] = []
        ml.set_focus_moved_callback(lambda old, new: seen.append((old, new)))

        def fail() -> None:
            raise RuntimeError

        ml.set_modified_callback(fail)
        with self.assertRaises(RuntimeError):
            del ml[0]
        self.assertEqual([(3, 2)], seen)

    def test_callback_set_during_a_change_is_kept(self) -> None:
        """A focus moved callback set by the modified callback replaces the one in use, and reports the change."""
        ml = urwid.MonitoredFocusList(range(3), focus=1)
        first: list[tuple[int | None, int | None]] = []
        second: list[tuple[int | None, int | None]] = []
        ml.set_focus_moved_callback(lambda old, new: first.append((old, new)))
        ml.set_modified_callback(lambda: ml.set_focus_moved_callback(lambda old, new: second.append((old, new))))
        ml.insert(0, -1)
        self.assertEqual(([], [(1, 2)]), (first, second))

    def test_failed_change_reports_nothing(self) -> None:
        """A change that raises reports nothing, and the next change is reported again."""
        ml = urwid.MonitoredFocusList(range(6), focus=2)
        seen: list[tuple[int | None, int | None]] = []
        ml.set_focus_moved_callback(lambda old, new: seen.append((old, new)))
        with self.assertRaises(ValueError):
            ml[0:4:2] = [1, 2, 3]
        self.assertEqual([], seen)
        ml.focus = 3
        self.assertEqual([(2, 3)], seen)


class MonitoredFocusListClearValidationTest(unittest.TestCase):
    def test_clear_reports_removed_contents(self) -> None:
        for contents in ([], [1, 2, 3]):
            with self.subTest(contents=contents):
                items = urwid.MonitoredFocusList(contents)
                seen = []

                def validate(indices, new_items):
                    seen.append((indices, list(new_items), list(items)))

                items.set_validate_contents_modified(validate)
                items.clear()
                self.assertEqual([((0, len(contents), 1), [], contents)], seen)
                self.assertEqual([], items)
                self.assertIsNone(items.focus)

    def test_clear_respects_removal_rejection(self) -> None:
        items = urwid.MonitoredFocusList([1, 2, 3], focus=1)
        modified = []
        items.set_modified_callback(lambda: modified.append(True))

        def validate(indices, new_items):
            if indices[0] < indices[1]:
                raise ValueError("cannot remove items")

        items.set_validate_contents_modified(validate)
        with self.assertRaisesRegex(ValueError, "cannot remove items"):
            items.clear()
        self.assertEqual([1, 2, 3], items)
        self.assertEqual(1, items.focus)
        self.assertEqual([], modified)


FILL_OPERATIONS: typing.Final[Mapping[str, Callable[[list[typing.Any], list[typing.Any]], object]]] = {
    "slice all": lambda items, new: operator.setitem(items, slice(None), new),
    "slice 0:0": lambda items, new: operator.setitem(items, slice(0, 0), new),
    "extend": lambda items, new: items.extend(new),
    "+=": operator.iadd,
    "insert": lambda items, new: items.insert(0, new[0]),
    "append": lambda items, new: items.append(new[0]),
}


class MonitoredFocusListFillEmptyTest(unittest.TestCase):
    """Filling an empty focus list gives the focus to the last new item, which applications rely on."""

    @staticmethod
    def widgets() -> list[urwid.Widget]:
        """Return new widgets whose first one is not selectable."""
        return [urwid.Text("t"), urwid.Button("b"), urwid.Text("t2")]

    def test_list_gives_focus_to_last_new_item(self) -> None:
        """Check the focus of a focus list and a walker after each way of filling them."""
        lists: dict[str, Callable[[], urwid.MonitoredFocusList[urwid.Widget]]] = {
            "MonitoredFocusList": urwid.MonitoredFocusList,
            "SimpleFocusListWalker": lambda: urwid.SimpleFocusListWalker([]),
        }
        for target, make in lists.items():
            for name, operation in FILL_OPERATIONS.items():
                with self.subTest(target=target, operation=name):
                    items = make()
                    operation(items, self.widgets())
                    self.assertEqual(len(items) - 1, items.focus)

    def test_container_gives_focus_to_last_new_item(self) -> None:
        """Check the focus position of a container after each way of filling its contents."""
        containers: dict[str, Callable[[], urwid.Pile | urwid.Columns | urwid.GridFlow]] = {
            "Pile": lambda: urwid.Pile([]),
            "Columns": lambda: urwid.Columns([]),
            "GridFlow": lambda: urwid.GridFlow([], 5, 1, 0, urwid.LEFT),
        }
        for target, make in containers.items():
            for name, operation in FILL_OPERATIONS.items():
                with self.subTest(target=target, operation=name):
                    widget = make()
                    operation(widget.contents, [(w, widget.options()) for w in self.widgets()])
                    self.assertEqual(len(widget.contents) - 1, widget.focus_position)

    def test_fill_notifies_once_with_the_new_focus(self) -> None:
        """Check that a fill sends one modified notification, which already sees the new focus.

        A fill with several items also reports one focus change; whether a one-item fill reports one is left open.
        """

        def record_focus(items: urwid.MonitoredFocusList[str], modified: list[int | None]) -> None:
            modified.append(items.focus)

        for name, operation in FILL_OPERATIONS.items():
            with self.subTest(operation=name):
                items: urwid.MonitoredFocusList[str] = urwid.MonitoredFocusList()
                modified: list[int | None] = []
                focus_changes: list[int] = []
                items.set_modified_callback(functools.partial(record_focus, items, modified))
                items.set_focus_changed_callback(focus_changes.append)
                operation(items, ["a", "b", "c"])
                last = len(items) - 1
                self.assertEqual([last], modified)
                if last:
                    self.assertEqual([last], focus_changes)

    def test_validation_can_override_focus(self) -> None:
        """Check that a focus returned by the validation callback wins over the last new item."""
        items: urwid.MonitoredFocusList[str] = urwid.MonitoredFocusList()
        items.set_validate_contents_modified(lambda indices, new: 0)
        items[:] = ["a", "b", "c"]
        self.assertEqual(0, items.focus)


APPEND_OPERATIONS: Mapping[str, Callable[[urwid.MonitoredFocusList[str], list[str]], typing.Any]] = {
    "append": lambda items, new: [items.append(item) for item in new],
    "extend": urwid.MonitoredFocusList.extend,
    "iadd": operator.iadd,
    "insert at the end": lambda items, new: [items.insert(len(items) + 5, item) for item in new],
    "slice at the end": lambda items, new: operator.setitem(items, slice(len(items), None), new),
}


class MonitoredFocusListFollowEndTest(unittest.TestCase):
    """With ``follow_end``, items added after a focused last item take the focus."""

    def test_focus_follows_added_items(self) -> None:
        """Check every way of adding items at the end, with the focus on the last item and elsewhere."""
        for name, operation in APPEND_OPERATIONS.items():
            for follow_end, focus, expected in ((True, 2, 4), (True, 1, 1), (False, 2, 2)):
                with self.subTest(operation=name, follow_end=follow_end, focus=focus):
                    items = urwid.MonitoredFocusList(["a", "b", "c"], focus=focus, follow_end=follow_end)
                    operation(items, ["d", "e"])
                    self.assertEqual(["a", "b", "c", "d", "e"], items)
                    self.assertEqual(expected, items.focus)

    def test_other_changes_keep_the_focused_item(self) -> None:
        """Check that changes which add nothing after the last item move the focus as without ``follow_end``."""
        items = urwid.MonitoredFocusList(["a", "b"], focus=1, follow_end=True)
        items.insert(1, "c")
        self.assertEqual(2, items.focus)
        items[-1:] = ["d", "e"]
        self.assertEqual(2, items.focus)
        items.focus = 3
        items *= 1
        self.assertEqual(3, items.focus)

    def test_repetition(self) -> None:
        """Check that repeating the contents moves a focused last item to the new last item, and only that one."""
        for focus, expected in ((2, 5), (1, 1)):
            with self.subTest(focus=focus):
                items = urwid.MonitoredFocusList(["a", "b", "c"], focus=focus, follow_end=True)
                items *= 2
                self.assertEqual(expected, items.focus)

    def test_setting_after_construction(self) -> None:
        """Check that the attribute can be switched on and off."""
        items = urwid.MonitoredFocusList(["a"])
        self.assertFalse(items.follow_end)
        items.follow_end = True
        items.append("b")
        self.assertEqual(1, items.focus)
        items.follow_end = False
        items.append("c")
        self.assertEqual(1, items.focus)

    def test_notifies_once_with_the_new_focus(self) -> None:
        """Check the focus-changed and modified callbacks see the new last item."""
        items = urwid.MonitoredFocusList(["a"], follow_end=True)
        modified: list[int | None] = []
        focus_changes: list[int] = []
        items.set_modified_callback(lambda: modified.append(items.focus))
        items.set_focus_changed_callback(focus_changes.append)
        items.extend(["b", "c"])
        self.assertEqual([2], modified)
        self.assertEqual([2], focus_changes)

    def test_validation_can_override_focus(self) -> None:
        """Check that a focus returned by the validation callback wins over the new last item."""
        items = urwid.MonitoredFocusList(["a"], follow_end=True)
        items.set_validate_contents_modified(lambda indices, new: 0)
        items.append("b")
        self.assertEqual(0, items.focus)


def _pickle_round_trip(obj: object, protocol: int) -> typing.Any:
    return pickle.loads(pickle.dumps(obj, protocol=protocol))


COPY_OPERATIONS: Mapping[str, Callable[[typing.Any], typing.Any]] = {
    **{
        f"pickle{protocol}": functools.partial(_pickle_round_trip, protocol=protocol)
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
    },
    "copy": copy.copy,
    "deepcopy": copy.deepcopy,
}


class SlottedFocusList(urwid.MonitoredFocusList[str]):
    """Focus list with a slot, whose default pickle state carries the slot values separately."""

    __slots__ = ("extra",)
    extra: str


class OwnStateList(urwid.MonitoredList[str]):
    """Monitored list that restores its own attributes from the default pickle state."""

    extra: str

    def __setstate__(self, state: dict[str, typing.Any]) -> None:
        """Restore the attributes from the instance dictionary."""
        vars(self).update(state)


class PlainReduceList(urwid.MonitoredList[str]):
    """Monitored list that pickles and copies as a plain list through its own ``__reduce__``."""

    def __reduce__(self) -> tuple[typing.Any, ...]:
        """Rebuild as a plain list, appending the items."""
        return list, (), None, iter(self)


class MonitoredListPickleTest(unittest.TestCase):
    """Pickling and copying restore a monitored list without calling its monitoring methods on a partial object."""

    def test_pickle_and_copy_restore_items_and_focus(self) -> None:
        """Check every pickle protocol and both copies, which restore items and attributes in different orders."""
        lists: dict[str, Callable[[list[urwid.Text]], urwid.MonitoredList[urwid.Text]]] = {
            "MonitoredList": urwid.MonitoredList,
            "MonitoredFocusList": lambda items: urwid.MonitoredFocusList(items, follow_end=True),
            "SimpleListWalker": lambda items: urwid.SimpleListWalker(items, wrap_around=True),
            "SimpleFocusListWalker": lambda items: urwid.SimpleFocusListWalker(
                items, wrap_around=True, follow_end=True
            ),
        }
        for target, make in lists.items():
            for name, operation in COPY_OPERATIONS.items():
                with self.subTest(target=target, operation=name):
                    original = make([urwid.Text("a"), urwid.Text("b"), urwid.Text("c")])
                    if isinstance(original, (urwid.MonitoredFocusList, urwid.SimpleListWalker)):
                        original.focus = 1
                    result = operation(original)
                    self.assertIs(type(original), type(result))
                    self.assertEqual(["a", "b", "c"], [widget.text for widget in result])
                    self.assertEqual(vars(original).keys(), vars(result).keys())
                    if isinstance(original, (urwid.MonitoredFocusList, urwid.SimpleListWalker)):
                        self.assertEqual(1, result.focus)
                    if isinstance(original, (urwid.SimpleListWalker, urwid.SimpleFocusListWalker)):
                        self.assertTrue(result.wrap_around)
                    if isinstance(original, urwid.MonitoredFocusList):
                        self.assertTrue(result.follow_end)

    def test_unpickling_does_not_notify(self) -> None:
        """Check that restoring the items calls neither callback, and that a list containing itself survives.

        Protocols 0 and 1 pass a list subclass's items to its constructor, which cannot hold the list itself.
        """
        for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                calls: list[object] = []
                items: urwid.MonitoredFocusList[object] = urwid.MonitoredFocusList(["a", "b"], focus=1)
                items.append(items)
                items.set_modified_callback(functools.partial(calls.append, "modified"))
                items.set_focus_changed_callback(calls.append)
                result, result_calls = pickle.loads(pickle.dumps((items, calls), protocol=protocol))
                self.assertEqual([], result_calls)
                self.assertIs(result, result[2])
                self.assertEqual(1, result.focus)
                result.append("c")
                self.assertEqual(["modified"], result_calls)

    def test_subclass_state(self) -> None:
        """Check a subclass with slots, and ones whose own ``__setstate__`` or ``__reduce__`` gets the default state.

        Protocols 0 and 1 cannot pickle a class with slots.
        """
        for name, operation in COPY_OPERATIONS.items():
            with self.subTest(operation=name):
                own_state = OwnStateList(["a", "b"])
                own_state.extra = "x"
                result = operation(own_state)
                self.assertIs(OwnStateList, type(result))
                self.assertEqual(["a", "b"], list(result))
                self.assertEqual("x", result.extra)
                result = operation(PlainReduceList(["a", "b"]))
                self.assertIs(list, type(result))
                self.assertEqual(["a", "b"], result)
                if name in {"pickle0", "pickle1"}:
                    continue
                slotted = SlottedFocusList(["a", "b"], focus=1)
                slotted.extra = "x"
                result = operation(slotted)
                self.assertIs(SlottedFocusList, type(result))
                self.assertEqual(["a", "b"], list(result))
                self.assertEqual("x", result.extra)
                self.assertEqual(1, result.focus)


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


class PartialExtendTest(unittest.TestCase):
    def test_failed_iterator_reports_the_retained_prefix(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for prefix in ([], [2], [2, 3, 4]):
                with self.subTest(operation=operation, prefix=prefix):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))
                    failure = ValueError("Input failed")

                    def incoming():
                        yield from prefix
                        raise failure

                    with self.assertRaises(ValueError) as caught:
                        operation(items, incoming())

                    self.assertIs(caught.exception, failure)
                    self.assertEqual(items, [1, *prefix])
                    self.assertEqual(changes, [[1, *prefix]] if prefix else [])

    def test_interruption_reports_partial_changes(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for error_type in (KeyboardInterrupt, SystemExit, GeneratorExit):
                with self.subTest(operation=operation, error_type=error_type):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))
                    failure = error_type()

                    def incoming():
                        yield 2
                        raise failure

                    with self.assertRaises(error_type) as caught:
                        operation(items, incoming())

                    self.assertIs(caught.exception, failure)
                    self.assertEqual(changes, [[1, 2]])

    def test_successful_extension_notifies_once(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for values in ([], [2, 3]):
                with self.subTest(operation=operation, values=values):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))

                    result = operation(items, iter(values))

                    if operation is operator.iadd:
                        self.assertIs(result, items)
                    else:
                        self.assertIsNone(result)
                    self.assertEqual(changes, [[1, *values]])

    def test_failure_to_start_iteration_does_not_notify(self):
        class BrokenIterable:
            def __iter__(self):
                raise ValueError("Cannot iterate")

        items = urwid.MonitoredList([1])
        changes = []
        items.set_modified_callback(lambda: changes.append(list(items)))

        with self.assertRaisesRegex(ValueError, "Cannot iterate"):
            items.extend(BrokenIterable())

        self.assertEqual(items, [1])
        self.assertEqual(changes, [])

    def test_focus_list_still_validates_input_before_changing_contents(self):
        for operation in (urwid.MonitoredFocusList.extend, operator.iadd):
            with self.subTest(operation=operation):
                items = urwid.MonitoredFocusList([1], focus=0)
                changes = []
                items.set_modified_callback(lambda: changes.append(list(items)))

                def incoming():
                    yield 2
                    raise ValueError("Input failed")

                with self.assertRaisesRegex(ValueError, "Input failed"):
                    operation(items, incoming())

                self.assertEqual(items, [1])
                self.assertEqual(items.focus, 0)
                self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
