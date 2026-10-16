from __future__ import annotations

import functools
import operator
import typing
import unittest

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class Index:
    def __init__(self, value: int) -> None:
        self.value = value

    def __index__(self) -> int:
        return self.value

    def __int__(self) -> int:
        return 1


class CountingIndex:
    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.calls = 0

    def __index__(self) -> int:
        self.calls += 1
        return self.value


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
