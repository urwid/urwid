"""Tests for :class:`urwid.FilteredListWalker`."""

from __future__ import annotations

import gc
import sys
import typing
import unittest
import weakref

import urwid
from tests.util import collect_and_count_alive
from urwid.testing import press, render_text

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable

WORDS = ("apple", "pear", "plum", "peach", "fig", "lime")
WALKER_CLASSES = (
    urwid.SimpleFocusListWalker,
    urwid.SimpleListWalker,
    urwid.SimpleFocusDequeWalker,
    urwid.SimpleDequeWalker,
)
LIST_KEYS = frozenset({"up", "down", "page up", "page down", "home", "end", "enter"})


def texts(words: Iterable[str] = WORDS) -> list[urwid.Text]:
    """Return a new ``Text`` widget for each of *words*."""
    return [urwid.Text(word) for word in words]


def starts(prefix: str) -> Callable[[urwid.Text], bool]:
    """Return a predicate that matches ``Text`` widgets whose text starts with *prefix*."""
    return lambda widget: str(widget.text).startswith(prefix)


def focus_text(view: urwid.FilteredListWalker[urwid.Text]) -> tuple[str | bytes, int] | tuple[None, None]:
    """Return the text and the position of the focus of *view*, or ``(None, None)``."""
    widget, position = view.get_focus()
    if widget is None:
        return None, None
    return widget.text, position


def count_modified(view: urwid.FilteredListWalker[typing.Any]) -> list[None]:
    """Return the list one item is appended to per ``"modified"`` signal of *view*."""
    seen: list[None] = []
    urwid.connect_signal(view, "modified", lambda: seen.append(None))
    return seen


class FilterFrame(urwid.Frame[urwid.ListBox[int], urwid.Edit, urwid.Text]):
    """The type-ahead routing of the filter example: list keys to the body, every other key to the header."""

    def __init__(self, listbox: urwid.ListBox[int], query: urwid.Edit, footer: urwid.Text) -> None:
        """Show *query* above *listbox* and *footer* below it, with the focus in *query*."""
        super().__init__(listbox, header=query, footer=footer, focus_part="header")
        self._query = query

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Send a list key to the list, sized as it is drawn, and every other key to the query."""
        if key not in LIST_KEYS:
            return self._query.keypress((size[0],), key)
        maxcol, maxrow = size
        (hrows, frows), _ = self.frame_top_bottom(size, True)
        remaining = maxrow - hrows - frows
        if remaining <= 0 or not self.body.selectable():
            return key
        return self.body.keypress((maxcol, remaining), key)


def type_ahead(labels: Iterable[str]) -> tuple[FilterFrame, urwid.FilteredListWalker[urwid.Button], urwid.Edit]:
    """Return a type-ahead frame over buttons labelled *labels*, its view and its query."""
    view = urwid.FilteredListWalker([urwid.Button(label) for label in labels])
    edit = urwid.Edit("Filter: ")
    footer = urwid.Text("")
    frame = FilterFrame(urwid.ListBox(view), edit, footer)

    def refilter(_edit: urwid.Edit, _old: str) -> None:
        query = edit.edit_text.lower()
        view.set_predicate((lambda button: query in button.label.lower()) if query else None)

    urwid.connect_signal(edit, "postchange", refilter)
    for button in view.source:
        urwid.connect_signal(button, "click", lambda button: footer.set_text(button.label))
    return frame, view, edit


class ProtocolTest(unittest.TestCase):
    """Positions, items and moves of the list walker protocol."""

    def test_positions_items_and_len(self) -> None:
        """Only the positions passing the predicate are visible, and hidden ones raise."""
        for walker_class in WALKER_CLASSES:
            with self.subTest(walker_class=walker_class.__name__):
                view = urwid.FilteredListWalker(walker_class(texts()), predicate=starts("p"))
                self.assertEqual([1, 2, 3], list(view.positions()))
                self.assertEqual([3, 2, 1], list(view.positions(reverse=True)))
                self.assertEqual(3, len(view))
                self.assertIs(view.source[2], view[2])
                for position in (0, 4, 6, -1):
                    with self.subTest(position=position):
                        self.assertRaises(IndexError, view.__getitem__, position)
                        self.assertRaises(IndexError, view.set_focus, position)

    def test_next_and_prev_position(self) -> None:
        """Moves skip hidden positions and stop or wrap at the ends."""
        for wrap_around in (False, True):
            with self.subTest(wrap_around=wrap_around):
                view = urwid.FilteredListWalker(texts(), predicate=starts("p"), wrap_around=wrap_around)
                self.assertEqual(2, view.next_position(1))
                self.assertEqual(2, view.prev_position(3))
                self.assertEqual(1, view.next_position(0))
                self.assertEqual(3, view.prev_position(4))
                if wrap_around:
                    self.assertEqual(1, view.next_position(3))
                    self.assertEqual(3, view.prev_position(1))
                else:
                    self.assertRaises(IndexError, view.next_position, 3)
                    self.assertRaises(IndexError, view.prev_position, 1)
                    self.assertEqual((None, None), view.get_next(3))
                view.set_predicate(lambda _widget: False)
                self.assertRaises(IndexError, view.next_position, 0)
                self.assertRaises(IndexError, view.prev_position, 0)


class PredicateFocusTest(unittest.TestCase):
    """The focus after a change of the predicate."""

    def test_focus_after_predicate_change(self) -> None:
        """The focus stays while visible, else goes to the first visible item."""
        cases = (
            ("kept while visible", 2, starts("p"), ("plum", 2)),
            ("first visible when hidden", 4, starts("p"), ("pear", 1)),
            ("none when nothing matches", 2, lambda _widget: False, (None, None)),
        )
        for label, focus, predicate, expected in cases:
            with self.subTest(label):
                view = urwid.FilteredListWalker(texts())
                view.set_focus(focus)
                view.predicate = predicate
                self.assertEqual(expected, focus_text(view))
                self.assertIs(predicate, view.predicate)

    def test_predicate_that_raises_leaves_the_view_unchanged(self) -> None:
        """A predicate that raises is not kept, and the view keeps its items and focus."""
        source = urwid.SimpleFocusListWalker(texts())
        view = urwid.FilteredListWalker(source, predicate=starts("p"))
        view.set_focus(2)

        def broken(widget: urwid.Text) -> bool:
            if widget.text == "fig":
                raise ValueError("broken predicate")
            return True

        with self.assertRaises(ValueError):
            view.set_predicate(broken)
        self.assertIsNot(broken, view.predicate)
        self.assertEqual([1, 2, 3], list(view.positions()))
        self.assertEqual(("plum", 2), focus_text(view))
        del source[0]
        self.assertEqual(("plum", 1), focus_text(view))

    def test_widget_listed_twice_keeps_the_nearest_occurrence(self) -> None:
        """A widget listed twice keeps the focused occurrence."""
        for focus in (0, 4):
            with self.subTest(focus=focus):
                twice, other = urwid.Text("pear"), urwid.Text("fig")
                view = urwid.FilteredListWalker([twice, urwid.Text("apple"), other, urwid.Text("plum"), twice])
                view.set_focus(focus)
                view.set_predicate(lambda widget, other=other: widget is not other)
                self.assertEqual(focus, view.get_focus()[1])


class EmptyViewRecoveryTest(unittest.TestCase):
    """The focus once an empty view gets visible items again."""

    def test_first_row_appended_to_an_empty_source(self) -> None:
        """The first matching row of an empty source takes the focus."""
        for walker_class in WALKER_CLASSES:
            with self.subTest(walker_class=walker_class.__name__):
                source = walker_class([])
                view = urwid.FilteredListWalker(source, predicate=starts("p"))
                self.assertEqual((None, None), view.get_focus())
                source.append(urwid.Text("pear"))
                self.assertEqual(("pear", 0), focus_text(view))

    def test_matching_row_inserted_under_a_filter_without_matches(self) -> None:
        """A matching row inserted later takes the focus."""
        for walker_class in WALKER_CLASSES:
            with self.subTest(walker_class=walker_class.__name__):
                source = walker_class(texts())
                view = urwid.FilteredListWalker(source, predicate=starts("z"))
                source.insert(3, urwid.Text("zebra"))
                self.assertEqual(("zebra", 3), focus_text(view))

    def test_filter_without_matches_cleared(self) -> None:
        """Clearing the filter focuses the widget focused last, at the occurrence nearest its last position."""
        twice = urwid.Text("pear")
        for label, widgets, focus in (
            ("listed once", texts(), 4),
            ("listed twice, first", [twice, *texts(("apple", "fig", "plum")), twice], 0),
            ("listed twice, last", [twice, *texts(("apple", "fig", "plum")), twice], 4),
        ):
            with self.subTest(label):
                view = urwid.FilteredListWalker(widgets)
                view.set_focus(focus)
                view.set_predicate(lambda _widget: False)
                self.assertEqual((None, None), view.get_focus())
                view.set_predicate(None)
                self.assertEqual((widgets[focus], focus), view.get_focus())

    def test_source_cleared_then_repopulated(self) -> None:
        """Repopulating a cleared source focuses the item at the old position."""
        for walker_class in WALKER_CLASSES:
            with self.subTest(walker_class=walker_class.__name__):
                source = walker_class(texts())
                view = urwid.FilteredListWalker(source)
                view.set_focus(2)
                source.clear()
                self.assertEqual((None, None), view.get_focus())
                source.extend(texts(("kiwi", "date", "lemon", "melon")))
                self.assertEqual(("lemon", 2), focus_text(view))


class SourceChangeTest(unittest.TestCase):
    """The focus and the signal after a change of the source."""

    def test_source_changes_while_filtered(self) -> None:
        """The focus follows its widget, and the view emits once per change."""
        cases: tuple[tuple[str, Callable[[typing.Any], object], tuple[str | None, int | None], bool], ...] = (
            ("insert before the focus", lambda source: source.insert(0, urwid.Text("pecan")), ("plum", 3), False),
            ("insert after the focus", lambda source: source.insert(5, urwid.Text("pecan")), ("plum", 2), False),
            ("delete the focus", lambda source: source.__delitem__(2), ("peach", 2), False),
            ("delete after the focus", lambda source: source.__delitem__(3), ("plum", 2), False),
            ("clear", lambda source: source.clear(), (None, None), False),
            ("appendleft", lambda source: source.appendleft(urwid.Text("papaya")), ("plum", 3), True),
            ("slice assignment", lambda source: source.__setitem__(slice(0, 2), texts(["pumpkin"])), ("plum", 1), None),
            ("sort", lambda source: source.sort(key=lambda widget: widget.text), ("plum", 5), None),
        )
        for walker_class in WALKER_CLASSES:
            is_deque = issubclass(walker_class, urwid.MonitoredDeque)
            for label, change, expected, deque_only in cases:
                if deque_only is not None and deque_only != is_deque:
                    continue
                if deque_only is None and is_deque:
                    continue
                with self.subTest(label, walker_class=walker_class.__name__):
                    source = walker_class(texts())
                    view = urwid.FilteredListWalker(source, predicate=starts("p"))
                    view.set_focus(2)
                    seen = count_modified(view)
                    change(source)
                    self.assertEqual(expected, focus_text(view))
                    self.assertEqual(1, len(seen))

    def test_delete_the_last_visible_focus(self) -> None:
        """Deleting the last visible item in focus focuses the new last one."""
        for walker_class in WALKER_CLASSES:
            with self.subTest(walker_class=walker_class.__name__):
                source = walker_class(texts())
                view = urwid.FilteredListWalker(source, predicate=starts("p"))
                view.set_focus(3)
                del source[3]
                self.assertEqual(("plum", 2), focus_text(view))

    def test_maxlen_eviction(self) -> None:
        """An eviction from a bounded deque shifts the positions and keeps the focus."""
        for walker_class in (urwid.SimpleFocusDequeWalker, urwid.SimpleDequeWalker):
            with self.subTest(walker_class=walker_class.__name__):
                source = walker_class(texts(), maxlen=len(WORDS))
                view = urwid.FilteredListWalker(source, predicate=starts("p"))
                view.set_focus(2)
                seen = count_modified(view)
                source.append(urwid.Text("pine"))
                self.assertEqual([0, 1, 2, 5], list(view.positions()))
                self.assertEqual(("plum", 1), focus_text(view))
                self.assertEqual(1, len(seen))

    def test_refilter_after_an_in_place_change(self) -> None:
        """A widget changed in place is hidden by refilter()."""
        source = urwid.SimpleFocusListWalker(texts())
        view = urwid.FilteredListWalker(source, predicate=starts("p"))
        view.set_focus(2)
        source[2].set_text("grape")
        self.assertEqual(("grape", 2), focus_text(view))
        seen = count_modified(view)
        view.refilter()
        self.assertEqual(("peach", 3), focus_text(view))
        self.assertEqual(1, len(seen))

    def test_source_focus_does_not_move_the_view(self) -> None:
        """The focus of the source is independent of the view's."""
        source = urwid.SimpleFocusListWalker(texts())
        view = urwid.FilteredListWalker(source, predicate=starts("p"))
        view.set_focus(2)
        seen = count_modified(view)
        source.set_focus(0)
        self.assertEqual(("plum", 2), focus_text(view))
        self.assertEqual(0, source.focus)
        self.assertEqual(1, len(seen))


class LinearRebuildTest(unittest.TestCase):
    """The cost of a rebuild over a deque source."""

    def test_rebuild_indexes_a_deque_at_most_once(self) -> None:
        """A rebuild indexes a deque source at most once, however long the source is."""
        reads: list[object] = []

        class CountingDeque(urwid.SimpleFocusDequeWalker[urwid.Text]):
            def __getitem__(self, position: typing.Any) -> typing.Any:
                reads.append(position)
                return super().__getitem__(position)

        source = CountingDeque(urwid.Text(str(number)) for number in range(2000))
        view = urwid.FilteredListWalker(source)
        view.set_focus(1001)
        changes: tuple[tuple[str, Callable[[], None]], ...] = (
            ("focus stays visible", lambda: view.set_predicate(lambda widget: int(str(widget.text)) % 2 == 1)),
            ("refilter", view.refilter),
            ("focus hidden", lambda: view.set_predicate(lambda widget: int(str(widget.text)) % 2 == 0)),
        )
        for label, change in changes:
            with self.subTest(label):
                reads.clear()
                change()
                self.assertLessEqual(len(reads), 1)


class TypeAheadTest(unittest.TestCase):
    """Type-ahead key routing over the view, with the cursor kept in the query."""

    def test_typing_and_list_keys(self) -> None:
        """Letters edit the query and the list keys move the list."""
        frame, view, edit = type_ahead(("apple", "banana", "cherry", "pear", "plum", "peach", "fig", "lime"))
        size = (20, 10)
        self.assertEqual([], press(frame, size, "p"))
        self.assertEqual([0, 3, 4, 5], list(view.positions()))
        self.assertEqual(0, view.get_focus()[1])
        press(frame, size, "down", "down")
        self.assertEqual(4, view.get_focus()[1])
        self.assertEqual(1, edit.edit_pos)
        press(frame, size, "l")
        self.assertEqual([0, 4], list(view.positions()))
        self.assertEqual(4, view.get_focus()[1])
        press(frame, size, "home")
        self.assertEqual(0, view.get_focus()[1])
        self.assertEqual(2, edit.edit_pos)
        press(frame, size, "end")
        self.assertEqual(4, view.get_focus()[1])
        self.assertEqual(2, edit.edit_pos)
        press(frame, size, "enter")
        self.assertEqual("plum", frame.footer.text)
        press(frame, size, "backspace", "backspace")
        self.assertEqual(8, len(view))
        self.assertEqual(4, view.get_focus()[1])
        self.assertEqual("header", frame.focus_position)
        self.assertEqual(["esc"], press(frame, size, "esc"))

    def test_wrapped_query_keeps_list_keys_on_the_list(self) -> None:
        """Up, down and page down move the list under a wrapped query."""
        labels = [f"pea{number:02d}" for number in range(30)]
        frame, view, edit = type_ahead(labels)
        size = (10, 8)
        press(frame, size, "p", "e", "a")
        self.assertEqual(2, edit.rows((size[0],), True))
        press(frame, size, "down", "down", "up")
        self.assertEqual(1, view.get_focus()[1])
        self.assertEqual(3, edit.edit_pos)

        reference = urwid.ListBox(urwid.FilteredListWalker([urwid.Button(label) for label in labels]))
        reference.focus_position = 1
        body_rows = size[1] - 2 - 1
        press(reference, (size[0], body_rows), "page down")
        press(frame, size, "page down")
        position = view.get_focus()[1]
        self.assertEqual(reference.focus_position, position)
        self.assertGreater(position, 1)
        body = render_text(frame, size)[2 : 2 + body_rows]
        self.assertTrue(any(labels[position] in row for row in body), body)

    def test_no_body_rows(self) -> None:
        """A list key is returned unhandled when the list has no rows."""
        frame, view, _edit = type_ahead(("pear", "plum"))
        press(frame, (10, 8), "p", "e", "a")
        self.assertEqual(["down"], press(frame, (10, 3), "down"))
        self.assertEqual(0, view.get_focus()[1])


class ListBoxTest(unittest.TestCase):
    """A ``ListBox`` over the view."""

    @staticmethod
    def even_buttons(count: int = 20) -> urwid.FilteredListWalker[urwid.Button]:
        """Return a view of *count* buttons that shows the even ones."""
        source = urwid.SimpleFocusListWalker([urwid.Button(f"b{number:02d}") for number in range(count)])
        return urwid.FilteredListWalker(source, predicate=lambda button: int(button.label[1:]) % 2 == 0)

    def test_keys_move_among_visible_rows(self) -> None:
        """Moving keys focus visible rows only."""
        view = self.even_buttons()
        listbox = urwid.ListBox(view)
        size = (12, 4)
        for key, expected in (("down", 2), ("down", 4), ("up", 2), ("end", 18), ("home", 0), ("page down", 8)):
            with self.subTest(key=key):
                press(listbox, size, key)
                self.assertEqual(expected, listbox.focus_position)
        press(listbox, size, "page up")
        self.assertEqual(0, listbox.focus_position)

    def test_edge_stop(self) -> None:
        """The edge setting applies at the first visible row."""
        for edge, unhandled in (("return", ["up"]), ("stop", [])):
            with self.subTest(edge=edge):
                listbox = urwid.ListBox(self.even_buttons(), edge=edge)
                self.assertEqual(unhandled, press(listbox, (12, 4), "up"))
                self.assertEqual(0, listbox.focus_position)

    def test_focus_next_match(self) -> None:
        """A search does not find a hidden widget."""
        listbox = urwid.ListBox(self.even_buttons())
        self.assertIsNone(listbox.focus_next_match(lambda button: button.label == "b07"))
        self.assertEqual(8, listbox.focus_next_match(lambda button: button.label == "b08"))

    def test_focus_position_indexes_the_source(self) -> None:
        """Focus positions are source indices."""
        view = self.even_buttons()
        listbox = urwid.ListBox(view)
        listbox.focus_position = 8
        self.assertIs(view.source[8], listbox.focus)
        with self.assertRaises(IndexError):
            listbox.focus_position = 7

    def test_scrollbar_over_a_large_source(self) -> None:
        """A scroll bar renders over a filtered large source."""
        view = self.even_buttons(1000)
        bar = urwid.ScrollBar(urwid.ListBox(view))
        size = (12, 5)
        self.assertEqual(5, len(render_text(bar, size)))
        press(bar, size, "end")
        self.assertEqual(5, len(render_text(bar, size)))

    def test_empty_view(self) -> None:
        """An empty view renders blank and returns the keys."""
        view = self.even_buttons()
        view.set_predicate(lambda _button: False)
        listbox = urwid.ListBox(view)
        self.assertEqual(["", "", ""], render_text(listbox, (12, 3), strip=True))
        self.assertEqual(["down"], press(listbox, (12, 3), "down"))

        unfocusable = urwid.ListBox(view, focus_when_empty=False)
        self.assertFalse(unfocusable.selectable())
        view.set_predicate(None)
        self.assertTrue(unfocusable.selectable())


class ConstructionTest(unittest.TestCase):
    """The sources the constructor accepts."""

    def test_plain_list_is_copied(self) -> None:
        """A plain list is copied into a new focus list walker."""
        widgets = texts()
        view = urwid.FilteredListWalker(widgets)
        self.assertIsInstance(view.source, urwid.SimpleFocusListWalker)
        self.assertIsNot(widgets, view.source)
        self.assertEqual(widgets, list(view.source))

    def test_rejected_sources(self) -> None:
        """A list walker that is not a sequence, and a non-iterable, raise."""
        with self.assertRaises(TypeError) as context:
            urwid.FilteredListWalker(urwid.TreeWalker(urwid.TreeNode("root")))
        self.assertIn("TreeWalker", str(context.exception))
        with self.assertRaises(urwid.ListWalkerError):
            urwid.FilteredListWalker(123)  # type: ignore[arg-type]


class LeakTest(unittest.TestCase):
    """The source does not keep the view alive."""

    def test_view_is_freed_while_the_source_lives(self) -> None:
        """A dropped view is collected, and the source keeps working."""
        source = urwid.SimpleFocusListWalker(texts())
        view = urwid.FilteredListWalker(source, predicate=starts("p"))
        ref = weakref.ref(view)
        del view
        self.assertEqual(0, collect_and_count_alive([ref]))
        source.append(urwid.Text("pine"))

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing at once")
    def test_view_is_freed_without_a_collector_run(self) -> None:
        """A dropped view is freed by reference counting alone."""
        source = urwid.SimpleFocusListWalker(texts())
        view = urwid.FilteredListWalker(source)
        ref = weakref.ref(view)
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            del view
            self.assertIsNone(ref())
        finally:
            if was_enabled:
                gc.enable()
