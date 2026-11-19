from __future__ import annotations

import copy
import gc
import sys
import typing
import unittest
import weakref

import urwid
from tests.util import SelectableText

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable

    from urwid.widget.attr_map import _AttrMapLike


class CommonContainerTest(unittest.TestCase):
    def test_focus_path(self):
        # big tree of containers
        t = urwid.Text("x")
        e = urwid.Edit("?")
        c = urwid.Columns([t, e, t, t])
        p = urwid.Pile([t, t, c, t])
        a = urwid.AttrMap(p, "gets ignored")
        s = urwid.SolidFill("/")
        o = urwid.Overlay(e, s, "center", "pack", "middle", "pack")
        lb = urwid.ListBox(urwid.SimpleFocusListWalker([t, a, o, t]))
        lb.focus_position = 1
        g = urwid.GridFlow([t, t, t, t, e, t], 10, 0, 0, "left")
        g.focus_position = 4
        f = urwid.Frame(lb, header=t, footer=g)

        self.assertEqual(f.get_focus_path(), ["body", 1, 2, 1])
        f.set_focus_path(["footer"])  # same as f.focus_position = 'footer'
        self.assertEqual(f.get_focus_path(), ["footer", 4])
        f.set_focus_path(["body", 1, 2, 2])
        self.assertEqual(f.get_focus_path(), ["body", 1, 2, 2])
        self.assertRaises(IndexError, lambda: f.set_focus_path([0, 1, 2]))
        self.assertRaises(IndexError, lambda: f.set_focus_path(["body", 2, 2]))
        f.set_focus_path(["body", 2])  # focus the overlay
        self.assertEqual(f.get_focus_path(), ["body", 2, 1])
        # a focus position naming a missing part ends the path there
        self.assertEqual(["header"], urwid.Frame(s, focus_part="header").get_focus_path())


def recording_subclass(cls: type) -> type:
    """Return a subclass of *cls* whose ``focus_position`` setter records each position it is given."""

    class Recording(cls):
        @property
        def focus_position(self):
            return cls.focus_position.fget(self)

        @focus_position.setter
        def focus_position(self, position):
            if (moves := self.__dict__.get("moves")) is not None:
                moves.append(position)
            cls.focus_position.fset(self, position)

    Recording.__name__ = f"Recording{cls.__name__}"
    return Recording


class ContentsLifetimeTest(unittest.TestCase):
    """A container's ``contents`` view does not keep the container alive."""

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing at once")
    def test_container_freed_after_contents_read(self) -> None:
        """A container whose ``contents`` was read is freed by reference counting alone, with no collector run."""
        cases: tuple[tuple[str, Callable[[], typing.Any], object], ...] = (
            ("Overlay", lambda: urwid.Overlay(urwid.Text("x"), urwid.SolidFill(), "center", 5, "middle", "pack"), 1),
            ("Frame", lambda: urwid.Frame(urwid.SolidFill(), header=urwid.Text("x")), "header"),
            ("ListBox", lambda: urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text("x")])), 0),
            ("Pile", lambda: urwid.Pile([urwid.Text("x")]), 0),
            ("Columns", lambda: urwid.Columns([urwid.Text("x")]), 0),
            ("GridFlow", lambda: urwid.GridFlow([urwid.Text("x")], 1, 0, 0, "left"), 0),
            ("Tabs", lambda: urwid.Tabs([("a", urwid.Text("x"))]), 0),
        )
        for label, make_container, key in cases:
            with self.subTest(label):
                container = make_container()
                contents = container.contents
                self.assertEqual("x", contents[key][0].text)
                self.assertEqual(len(contents), len(container.contents))
                repr(contents)
                ref = weakref.ref(container)
                was_enabled = gc.isenabled()
                gc.disable()
                try:
                    del container, contents
                    self.assertIsNone(ref())
                finally:
                    if was_enabled:
                        gc.enable()


# name: (build the container over the selectable cells "a" and "b", the size to render it at, the error a rejected
# contents item raises)
_CONTENTS_CONTAINERS: dict[str, tuple[Callable[[list[urwid.Widget]], typing.Any], tuple[int, ...], type[Exception]]] = {
    "Pile": (urwid.Pile, (3,), urwid.PileError),
    "Columns": (urwid.Columns, (4,), urwid.ColumnsError),
    "GridFlow": (lambda cells: urwid.GridFlow(cells, 1, 1, 0, "left"), (3,), urwid.GridFlowError),
    "Tabs": (lambda cells: urwid.Tabs(zip("ab", cells, strict=True)), (3,), TypeError),
}


class ContentsCallbacksTest(unittest.TestCase):
    """The callbacks a container registers on its contents refer to it weakly, and to its deep copy in a copy."""

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing at once")
    def test_freed_after_render_and_focus_move(self) -> None:
        """A container that rendered and moved its focus is freed by reference counting alone."""
        for name, (make, size, _error) in _CONTENTS_CONTAINERS.items():
            with self.subTest(name):
                container = make([SelectableText("a"), SelectableText("b")])
                urwid.connect_signal(container, "focus changed", lambda *_args: None)
                container.render(size)
                container.focus_position = 1
                container.render(size, focus=True)
                ref = weakref.ref(container)
                was_enabled = gc.isenabled()
                gc.disable()
                try:
                    del container
                    self.assertIsNone(ref())
                finally:
                    if was_enabled:
                        gc.enable()

    def test_deep_copy_calls_the_copy(self) -> None:
        """A deep copy's contents report to the copy, and validate after the original is gone."""
        for name, (make, _size, error) in _CONTENTS_CONTAINERS.items():
            with self.subTest(name):
                original = make([SelectableText("a"), SelectableText("b")])
                duplicate = copy.deepcopy(original)
                moved: list[object] = []
                for widget in (original, duplicate):
                    urwid.connect_signal(widget, "focus changed", lambda sender, *_args: moved.append(sender))
                duplicate.focus_position = 1
                self.assertEqual([duplicate], moved)
                del original
                with self.assertRaises(error):
                    duplicate.contents.append("not a widget")


class NoHookWidget(urwid.Widget):
    """Selectable flow widget without ``enter_selectable``, which passes keys back."""

    _selectable = True
    _sizing = frozenset((urwid.FLOW,))

    def rows(self, size, focus=False):
        """Return one row."""
        return 1

    def render(self, size, focus=False):
        """Render a single letter."""
        return urwid.Text("w").render(size, focus)

    def keypress(self, size, key):
        """Return every key unhandled."""
        return key


class SelectNavigationFocusMoveHookTest(unittest.TestCase):
    """Every focus move made by select navigation goes through the ``focus_position`` setter."""

    def test_setter_sees_every_move(self) -> None:
        """Steps, resets and entries are all assignments to ``focus_position``."""
        cases = (
            (urwid.Pile, lambda cls: cls([SelectableText("a"), SelectableText("b")]), (5,), (0, 1)),
            (urwid.Columns, lambda cls: cls([SelectableText("a"), SelectableText("b")]), (10,), (0, 1)),
            (
                urwid.GridFlow,
                lambda cls: cls([SelectableText("a"), SelectableText("b")], 3, 1, 0, "left"),
                (10,),
                (0, 1),
            ),
            (urwid.ListBox, lambda cls: cls([SelectableText("a"), SelectableText("b")]), (5, 3), (0, 1)),
            (
                urwid.Frame,
                lambda cls: cls(urwid.Filler(SelectableText("b")), header=SelectableText("a"), focus_part="header"),
                (5, 3),
                ("header", "body"),
            ),
        )
        for cls, build, size, (first, second) in cases:
            with self.subTest(cls.__name__):
                container = build(recording_subclass(cls))
                container.select_navigation = True
                container.moves = []
                self.assertIsNone(container.keypress(size, "tab"))
                self.assertIsNotNone(container.keypress(size, "tab"))
                container.enter_selectable(reverse=True)
                self.assertTrue(container.focus_first_selectable())
                self.assertEqual([second, first, second, first], container.moves)
                self.assertEqual(first, container.focus_position)


class SelectNavigationEntryHookTest(unittest.TestCase):
    """Containers enter the child they move the focus to through ``enter_selectable``."""

    size = (20, 6)

    def test_reset_enters_container_off_the_departing_path(self) -> None:
        """Wrapping past the end starts the header at its first button, although it was left on its second one."""
        header_columns = urwid.Columns([urwid.Button("b1"), urwid.Button("b2")], select_navigation=True)
        header_columns.focus_position = 1
        body = urwid.Pile([urwid.Button("c"), urwid.Button("d")], select_navigation=True)
        frame = urwid.Frame(
            urwid.Filler(body, valign="top"), header=urwid.Padding(header_columns), select_navigation=True
        )
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual("tab", frame.keypress(self.size, "tab"))
        self.assertEqual(["header", 0], frame.get_focus_path())

    def test_reverse_entry_starts_at_last(self) -> None:
        """Moving backwards into a Columns lands on its last item."""
        columns = urwid.Columns([urwid.Button("a"), urwid.Button("b")], select_navigation=True)
        pile = urwid.Pile([columns, urwid.Button("c")], select_navigation=True)
        pile.focus_position = 1
        self.assertIsNone(pile.keypress((20,), "shift tab"))
        self.assertEqual([0, 1], pile.get_focus_path())

    def test_not_opted_in_child_is_one_stop(self) -> None:
        """A child container without the flag keeps its focus and passes the key on."""
        inner = urwid.Pile([urwid.Button("a"), urwid.Button("b")])
        inner.focus_position = 1
        outer = urwid.Pile([urwid.Button("x"), inner, urwid.Button("y")], select_navigation=True)
        self.assertIsNone(outer.keypress((20,), "tab"))
        self.assertEqual([1, 1], outer.get_focus_path())
        self.assertIsNone(outer.keypress((20,), "tab"))
        self.assertEqual(2, outer.focus_position)

    def test_wrappers_forward(self) -> None:
        """Decorations and WidgetWrap forward the hook to the widget they send keys to.

        A disabled WidgetDisable does not.
        """

        def inner() -> urwid.ListBox:
            listbox = urwid.ListBox([SelectableText("a"), SelectableText("b")], select_navigation=True)
            listbox.focus_position = 1
            return listbox

        wrappers = (
            ("WidgetWrap", urwid.WidgetWrap, 0),
            ("AttrMap", lambda w: urwid.AttrMap(w, "x"), 0),
            ("LineBox", urwid.LineBox, 0),
            ("ScrollBar", urwid.ScrollBar, 0),
            ("WidgetPlaceholder", urwid.WidgetPlaceholder, 0),
            ("WidgetDisable", urwid.WidgetDisable, 1),
            ("WidgetDisable enabled", lambda w: urwid.WidgetDisable(w, disabled=False), 0),
        )
        for name, wrap, expected in wrappers:
            with self.subTest(name):
                listbox = inner()
                wrap(listbox).enter_selectable()
                self.assertEqual(expected, listbox.focus_position)

    def test_decorations_resolve_to_widget_decoration_hook(self) -> None:
        """A delegate mixin in the bases does not take over the entry hook from WidgetDecoration."""
        for cls in (urwid.AttrMap, urwid.PopUpLauncher, urwid.WidgetPlaceholder, urwid.LineBox):
            with self.subTest(cls.__name__):
                self.assertIs(urwid.WidgetDecoration.enter_selectable, cls.enter_selectable)

    def test_child_without_hook(self) -> None:
        """A child without the hook is entered without error."""
        pile = urwid.Pile([NoHookWidget(), NoHookWidget()], select_navigation=True)
        self.assertIsNone(pile.keypress((20,), "tab"))
        self.assertEqual("tab", pile.keypress((20,), "tab"))
        self.assertEqual(0, pile.focus_position)


class SelectNavigationNestedTest(unittest.TestCase):
    """Traversal across nested opted-in containers."""

    size = (30, 8)

    def _frame(self) -> urwid.Frame:
        row = urwid.Columns([urwid.Button("a"), urwid.Text("-"), urwid.Button("b")], select_navigation=True)
        records = urwid.ListBox([SelectableText("r1"), SelectableText("r2")])
        body = urwid.Pile([row, urwid.BoxAdapter(records, 2), urwid.Button("c")], select_navigation=True)
        footer = urwid.Columns([urwid.Button("ok"), urwid.Button("cancel")], select_navigation=True)
        return urwid.Frame(urwid.Filler(body, valign="top"), footer=footer, select_navigation=True)

    def test_full_order(self) -> None:
        """Tab visits every stop once in order, and Shift+Tab in the reverse order."""
        stops = [["body", 0, 0], ["body", 0, 2], ["body", 1, 0], ["body", 2], ["footer", 0], ["footer", 1]]
        frame = self._frame()
        frame.focus_first_selectable()
        visited = [frame.get_focus_path()]
        for _ in range(len(stops)):
            frame.keypress(self.size, "tab")
            visited.append(frame.get_focus_path())
        self.assertEqual([*stops, stops[0]], visited)

        frame.focus_last_selectable()
        visited = [frame.get_focus_path()]
        for _ in range(len(stops)):
            frame.keypress(self.size, "shift tab")
            visited.append(frame.get_focus_path())
        self.assertEqual([*reversed(stops), stops[-1]], visited)

    def test_item_appended_to_body(self) -> None:
        """An item appended to the body Pile at its end is reached before the footer."""
        frame = self._frame()
        body = frame.body.base_widget
        body.focus_position = 2
        body.contents.append((urwid.Button("new"), body.options()))
        self.assertIsNone(frame.keypress(self.size, "tab"))
        self.assertEqual(["body", 3], frame.get_focus_path())


class EmptyingWidget(urwid.Edit):
    """Edit that removes every child of *box* when it gets a key, and passes the key back."""

    def __init__(self) -> None:
        """Create the widget with no container to empty yet."""
        super().__init__()
        self.box: urwid.Pile | urwid.Columns | urwid.GridFlow | None = None

    def keypress(self, size, key):
        """Empty the container and return *key* unhandled."""
        del self.box.contents[:]
        return key


class SelectNavigationEdgeCaseTest(unittest.TestCase):
    """Containers and states outside the usual path."""

    def test_overlay_is_one_stop(self) -> None:
        """Overlay does not get the select navigation methods, and an opted-in parent passes over it as one stop."""
        overlay = urwid.Overlay(urwid.Filler(urwid.Edit()), urwid.SolidFill(), "center", 5, "middle", 1)
        for name in ("select_navigation", "enter_selectable", "focus_first_selectable", "focus_last_selectable"):
            with self.subTest(name):
                self.assertFalse(hasattr(overlay, name))
        pile = urwid.Pile([urwid.Button("a"), (3, overlay)], select_navigation=True)
        self.assertIsNone(pile.keypress((10,), "tab"))
        self.assertEqual(1, pile.focus_position)
        self.assertEqual("tab", pile.keypress((10,), "tab"))
        self.assertEqual(0, pile.focus_position)

    def test_child_empties_container(self) -> None:
        """A child that empties its container while handling the key gets the key returned, as without the flag."""
        builds = (
            ("Pile", lambda w: urwid.Pile([w], select_navigation=True)),
            ("Columns", lambda w: urwid.Columns([w], select_navigation=True)),
            ("GridFlow", lambda w: urwid.GridFlow([w], 5, 1, 0, "left", select_navigation=True)),
        )
        for name, build in builds:
            with self.subTest(name):
                child = EmptyingWidget()
                child.box = build(child)
                self.assertEqual("tab", child.box.keypress((20,), "tab"))
                self.assertEqual(0, len(child.box.contents))
        self.assertEqual("tab", urwid.GridFlow([], 5, 1, 0, "left", select_navigation=True).keypress((20,), "tab"))


class CustomListContainer(urwid.Widget, urwid.SelectNavigationListContentsMixin[tuple[urwid.Widget, None]]):
    """Container outside urwid built on the public mixin: a vertical list of flow widgets."""

    _sizing = frozenset((urwid.FLOW,))

    def __init__(self, widgets: list[urwid.Widget]) -> None:
        """Hold *widgets*, focused on the first one; ``select_navigation`` is left at its class default."""
        super().__init__()
        self._contents = urwid.MonitoredFocusList((w, None) for w in widgets)

    @property
    def contents(self):
        """Return the ``(widget, None)`` list."""
        return self._contents

    @property
    def focus(self):
        """Return the widget in focus."""
        return self._contents[self.focus_position][0] if self._contents else None

    @property
    def focus_position(self) -> int:
        """Return the index in focus."""
        return self._contents.focus

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        self._contents.focus = position

    def selectable(self) -> bool:
        """Return whether any child is selectable."""
        return any(w.selectable() for w, _ in self._contents)

    def rows(self, size, focus=False):
        """Return the number of children."""
        return len(self._contents)

    def keypress(self, size, key):
        """Send *key* to the child in focus, then apply select navigation to what it leaves unhandled."""
        if (key := self.focus.keypress(size, key)) is None:
            return None
        if self.select_navigation and self._command_map[key] in {"next selectable", "prev selectable"}:
            return self._select_keypress_unhandled(key)
        return key


class NamedPartsContainer(urwid.Widget, urwid.SelectNavigationMixin[str]):
    """Container keyed by name with its own ``set_focus`` and no ``focus_position``, as some applications write."""

    _selectable = True
    _sizing = frozenset((urwid.FLOW,))

    def __init__(self) -> None:
        """Hold two named parts, focused on the first one, with select navigation switched on."""
        super().__init__()
        self.parts = {"main": SelectableText("m"), "mini": SelectableText("n")}
        self.focus_name = "main"
        self.select_navigation = True

    @property
    def focus(self):
        """Return the part in focus."""
        return self.parts[self.focus_name]

    def set_focus(self, name: str) -> None:
        """Focus the part called *name*."""
        self.focus_name = name

    def _select_candidates(self, *, reverse, from_edge):
        names = list(self.parts)
        yield from reversed(names) if reverse else names

    def _select_enter_focus(self, *, reverse):
        pass

    def rows(self, size, focus=False):
        """Return one row."""
        return 1

    def render(self, size, focus=False):
        """Render the part in focus."""
        return self.focus.render(size, focus)

    def keypress(self, size, key):
        """Send *key* to the part in focus, then apply select navigation to what it leaves unhandled."""
        if (key := self.focus.keypress(size, key)) is None:
            return None
        if self.select_navigation and self._command_map[key] in {"next selectable", "prev selectable"}:
            return self._select_keypress_unhandled(key)
        return key


class SelectNavigationPublicMixinTest(unittest.TestCase):
    """The public mixins work for a container defined outside urwid."""

    def _container(self) -> CustomListContainer:
        return CustomListContainer([SelectableText("a"), urwid.Text("-"), SelectableText("b")])

    def test_defaults_without_init_assignment(self) -> None:
        """A container that never sets ``select_navigation`` reads ``False`` and keeps its focus on entry."""
        container = self._container()
        self.assertFalse(container.select_navigation)
        container.focus_position = 2
        container.enter_selectable()
        self.assertEqual(2, container.focus_position)
        self.assertEqual("tab", container.keypress((5,), "tab"))

    def test_traversal_and_entry(self) -> None:
        """Steps, the reset at the edge, the public methods and entry from an urwid parent all work."""
        container = self._container()
        container.select_navigation = True
        self.assertIsNone(container.keypress((5,), "tab"))
        self.assertEqual(2, container.focus_position)
        self.assertEqual("tab", container.keypress((5,), "tab"))
        self.assertEqual(0, container.focus_position)
        self.assertTrue(container.focus_last_selectable())
        self.assertEqual(2, container.focus_position)
        pile = urwid.Pile([urwid.Button("x"), container], select_navigation=True)
        pile.focus_position = 0
        self.assertIsNone(pile.keypress((5,), "tab"))
        self.assertEqual([1, 0], pile.get_focus_path())

    def test_missing_methods_fail_at_creation(self) -> None:
        """A container that does not implement the required members cannot be created."""

        class Incomplete(urwid.Widget, urwid.SelectNavigationMixin[int]):
            @property
            def focus(self):
                return None

        with self.assertRaises(TypeError):
            Incomplete()

    def test_container_without_focus_position_is_one_stop(self) -> None:
        """A container that relies on Widget.focus_position gets a warning instead of an exception."""
        container = NamedPartsContainer()
        with self.assertWarns(urwid.widget.WidgetWarning):
            self.assertEqual("tab", container.keypress((5,), "tab"))
        self.assertEqual("main", container.focus_name)
        with self.assertWarns(urwid.widget.WidgetWarning):
            self.assertFalse(container.focus_first_selectable())
        pile = urwid.Pile([urwid.Button("x"), container], select_navigation=True)
        pile.focus_position = 0
        with self.assertWarns(urwid.widget.WidgetWarning):
            self.assertIsNone(pile.keypress((5,), "tab"))
        self.assertEqual(1, pile.focus_position)
        with self.assertWarns(urwid.widget.WidgetWarning):
            self.assertEqual("tab", pile.keypress((5,), "tab"))
        self.assertEqual(0, pile.focus_position)

    def test_containers_keep_their_base_classes(self) -> None:
        """The urwid containers are still instances of the container mixins they were before."""
        for widget in (
            urwid.Pile([]),
            urwid.Columns([]),
            urwid.GridFlow([], 5, 1, 0, "left"),
        ):
            with self.subTest(type(widget).__name__):
                self.assertIsInstance(widget, urwid.WidgetContainerMixin)
                self.assertIsInstance(widget, urwid.widget.WidgetContainerListContentsMixin)
                self.assertIsInstance(widget, urwid.SelectNavigationListContentsMixin)
        for widget in (urwid.Frame(urwid.SolidFill()), urwid.ListBox([])):
            with self.subTest(type(widget).__name__):
                self.assertIsInstance(widget, urwid.WidgetContainerMixin)
                self.assertIsInstance(widget, urwid.SelectNavigationMixin)
        self.assertNotIsInstance(
            urwid.Overlay(urwid.SolidFill(), urwid.SolidFill(), "center", 1, "middle", 1), urwid.SelectNavigationMixin
        )


class ContainerFocusChangedSignalTest(unittest.TestCase):
    """``Pile``, ``Columns`` and ``GridFlow`` send ``"focus changed"`` after their focus position changed."""

    containers: typing.ClassVar[dict[str, tuple[Callable[[list[urwid.Widget]], urwid.Widget], str, tuple[int]]]] = {
        "Pile": (urwid.Pile, "down", (10,)),
        "Columns": (urwid.Columns, "right", (30,)),
        "GridFlow": (lambda cells: urwid.GridFlow(cells, 5, 1, 0, "left"), "right", (30,)),
    }

    def test_signal(self) -> None:
        """Keys, the focus setter and contents changes are reported, also after the legacy callback is replaced."""
        for name, (make, key, size) in self.containers.items():
            with self.subTest(name):
                widget = make([SelectableText("a"), SelectableText("b"), SelectableText("c")])
                seen: list[tuple[str, urwid.Widget, int | None, int | None, int | None]] = []

                def record(tag: str, sender: urwid.Widget, old: int | None, new: int | None) -> None:
                    seen.append((tag, sender, old, new, sender.focus_position if sender.contents else None))

                urwid.connect_signal(widget, "focus changed", record, user_args=["tag"])
                self.assertIsNone(widget.keypress(size, key))
                widget.focus_position = 1  # unchanged: not reported
                widget.contents.set_focus_changed_callback(lambda new: None)
                widget.focus_position = 2
                del widget.contents[:]
                self.assertEqual(
                    [("tag", widget, 0, 1, 1), ("tag", widget, 1, 2, 2), ("tag", widget, 2, None, None)],
                    seen,
                )

    def test_contents_change_reported_once(self) -> None:
        """Inserting several items before the focus is reported once, with the final position."""
        for name, (make, _key, _size) in self.containers.items():
            with self.subTest(name):
                widget = make([SelectableText("a"), SelectableText("b")])
                seen: list[tuple[int | None, int | None]] = []
                urwid.connect_signal(widget, "focus changed", lambda _w, old, new: seen.append((old, new)))
                widget.contents[0:0] = [(SelectableText(str(i)), widget.options()) for i in range(3)]
                self.assertEqual([(0, 3)], seen)

    def test_grid_flow_mouse(self) -> None:
        """A click on another cell of a ``GridFlow`` is reported."""
        grid = urwid.GridFlow([SelectableText("a"), SelectableText("b")], 4, 1, 0, "left")
        seen: list[tuple[int | None, int | None]] = []
        urwid.connect_signal(grid, "focus changed", lambda _w, old, new: seen.append((old, new)))
        grid.mouse_event((20,), "mouse press", 1, 6, 0, True)
        self.assertEqual([(0, 1)], seen)

    def test_subclass(self) -> None:
        """A subclass with its own signals list connects the signal, and construction sends none."""

        class Labelled(urwid.Pile):
            signals: typing.ClassVar[list[str]] = ["labelled"]

            def __init__(self, widget_list: list[urwid.Widget]) -> None:
                super().__init__(widget_list, focus_item=1)
                self.label = "set after the base"

            def __getattr__(self, name: str) -> object:
                # forwards unknown names to an attribute set only after the base __init__
                return getattr(self.label, name)

        pile = Labelled([SelectableText("a"), SelectableText("b")])
        seen: list[tuple[int | None, int | None]] = []
        urwid.connect_signal(pile, "focus changed", lambda _w, old, new: seen.append((old, new)))
        pile.focus_position = 0
        self.assertEqual(["labelled", "focus changed"], Labelled.signals)
        self.assertEqual([(1, 0)], seen)


def _cells(text: str) -> list[urwid.AttrMap]:
    """Return one selectable cell per character of *text*, each with the attribute ``"plain"``."""
    return [urwid.AttrMap(SelectableText(char), "plain") for char in text]


# name: (build the container with the focus on "c", the size to render it at)
_MARKING_CONTAINERS: dict[str, Callable[..., tuple[urwid.Widget, tuple[int] | tuple[int, int]]]] = {
    "Pile": lambda **kwargs: (urwid.Pile(_cells("abcd"), focus_item=2, **kwargs), (1,)),
    "Columns": lambda **kwargs: (urwid.Columns(_cells("abcd"), focus_column=2, **kwargs), (4,)),
    "ListBox": lambda **kwargs: (_focused_list_box(**kwargs), (1, 4)),
    # two rows, "a b" and "c d": the first row's own focus cell, "a", stays plain
    "GridFlow": lambda **kwargs: (urwid.GridFlow(_cells("abcd"), 1, 1, 0, "left", focus=2, **kwargs), (3,)),
}


def _focused_list_box(**kwargs: typing.Any) -> urwid.ListBox:
    """Return a ListBox over the cells "abcd" with the focus on "c"."""
    list_box = urwid.ListBox(urwid.SimpleFocusListWalker(_cells("abcd")), **kwargs)
    list_box.focus_position = 2
    return list_box


def _attributes(canvas: urwid.Canvas) -> dict[str, typing.Any]:
    """Return the display attribute of every non-blank character of *canvas*."""
    return {
        char: attr
        for row in canvas.content()
        for attr, _charset, text in row
        for char in text.decode("utf-8")
        if char != " "
    }


class UnfocusedFocusAttrTest(unittest.TestCase):
    def test_marks_the_focus_child_while_unfocused(self) -> None:
        """``unfocused_focus_attr`` recolours only the focus child, as :class:`AttrMap` would, while unfocused."""
        cases = (
            # label, unfocused_focus_attr, render with focus, whether the focus child "c" is marked
            ("single attribute", "mark", False, True),
            ("attribute map", {"plain": "mark"}, False, True),
            ("map missing the attribute", {"other": "mark"}, False, True),
            ("not set", None, False, False),
            ("rendered with focus", "mark", True, False),
        )
        for name, make in _MARKING_CONTAINERS.items():
            for label, attr, focus, marked in cases:
                with self.subTest(name, case=label):
                    container, size = make(unfocused_focus_attr=attr)
                    expected = dict.fromkeys("abcd", "plain")
                    if marked:
                        expected["c"] = _attributes(urwid.AttrMap(_cells("c")[0], attr).render((1,)))["c"]
                    self.assertEqual(expected, _attributes(container.render(size, focus=focus)))

    def test_setting_redraws(self) -> None:
        """Setting ``unfocused_focus_attr`` on a rendered container redraws it, and ``None`` turns the marking off."""
        for name, make in _MARKING_CONTAINERS.items():
            with self.subTest(name):
                container, size = make()
                # the canvas cache holds canvases weakly: keep the old one alive, as a screen showing it does
                old_canvas = container.render(size)
                container.unfocused_focus_attr = "mark"
                marked = _attributes(urwid.AttrMap(_cells("c")[0], "mark").render((1,)))["c"]
                self.assertEqual(marked, _attributes(container.render(size))["c"])
                self.assertEqual({None: "mark"}, container.unfocused_focus_attr)
                container.unfocused_focus_attr = None
                self.assertEqual("plain", _attributes(container.render(size))["c"])
                self.assertEqual("plain", _attributes(old_canvas)["c"])

                def func(_child: urwid.AbstractWidget) -> str:
                    return "mark"

                container.unfocused_focus_attr_func = func
                self.assertEqual(marked, _attributes(container.render(size))["c"])
                self.assertIs(func, container.unfocused_focus_attr_func)
                if name != "ListBox":
                    self.assertIn("unfocused_focus_attr_func=", repr(container))
                    self.assertIn(("unfocused_focus_attr_func", func, None), list(container.__rich_repr__()))
                container.unfocused_focus_attr_func = None
                self.assertEqual("plain", _attributes(container.render(size))["c"])

    def test_func_marks_the_focus_child(self) -> None:
        """``unfocused_focus_attr_func`` gives the map for the focus child; on ``None`` the fixed map applies."""
        cases: tuple[tuple[str, _AttrMapLike | None, _AttrMapLike | None, _AttrMapLike | None], ...] = (
            # label, the function's result, unfocused_focus_attr, the map "c" is marked with
            ("single attribute", "mark", None, "mark"),
            ("attribute map", {"plain": "mark"}, None, {"plain": "mark"}),
            ("None without a fixed map", None, None, None),
            ("None with a fixed map", None, "mark", "mark"),
            ("result over the fixed map", "mark", "other", "mark"),
        )
        for name, make in _MARKING_CONTAINERS.items():
            for label, result, fixed, marked_with in cases:
                with self.subTest(name, case=label):
                    seen: list[object] = []

                    def func(child: urwid.AbstractWidget, result: _AttrMapLike | None = result) -> _AttrMapLike | None:
                        seen.append(child)
                        return result

                    container, size = make(unfocused_focus_attr=fixed, unfocused_focus_attr_func=func)
                    expected = dict.fromkeys("abcd", "plain")
                    if marked_with is not None:
                        expected["c"] = _attributes(urwid.AttrMap(_cells("c")[0], marked_with).render((1,)))["c"]
                    self.assertEqual(expected, _attributes(container.render(size)))
                    self.assertTrue(seen)
                    self.assertTrue(all(child is container.focus for child in seen))

                    seen.clear()
                    self.assertEqual(dict.fromkeys("abcd", "plain"), _attributes(container.render(size, focus=True)))
                    self.assertEqual([], seen)

    def test_func_called_when_drawn_afresh(self) -> None:
        """The function runs when the canvas is drawn afresh, and not for a canvas the cache returns."""
        for name, make in _MARKING_CONTAINERS.items():
            with self.subTest(name):
                calls: list[object] = []
                container, size = make(unfocused_focus_attr_func=lambda child: (calls.append(child), "mark")[1])
                # the canvas cache holds canvases weakly: keep the first one alive, as a screen showing it does
                first = container.render(size)
                self.assertEqual(1, len(calls))
                self.assertIs(first, container.render(size))
                self.assertEqual(1, len(calls))
                typing.cast("urwid.Widget", container.focus)._invalidate()
                container.render(size)
                self.assertEqual(2, len(calls))

    def test_func_limit_of_the_focus_map_example(self) -> None:
        """The manual's example cannot tell apart attributes the normal map has already merged."""

        def own_focus_map(child: urwid.AbstractWidget) -> dict[Hashable, Hashable] | None:
            if not isinstance(child, urwid.AttrMap) or child.focus_map is None:
                return None
            return {child.attr_map.get(key, key): value for key, value in child.focus_map.items()}

        markup = [("a", "x"), ("b", "y")]
        distinct = urwid.AttrMap(SelectableText(markup), {"a": "pa", "b": "pb"}, {"a": "one", "b": "two"})
        merged = urwid.AttrMap(SelectableText(markup), {"a": "plain", "b": "plain"}, {"a": "one", "b": "two"})
        for child, expected in ((distinct, {"x": "one", "y": "two"}), (merged, {"x": "two", "y": "two"})):
            with self.subTest(attr_map=child.attr_map):
                pile = urwid.Pile([child], unfocused_focus_attr_func=own_focus_map)
                self.assertEqual({"x": "one", "y": "two"}, _attributes(child.render((2,), focus=True)))
                self.assertEqual(expected, _attributes(pile.render((2,))))

    def test_mark_follows_the_focus(self) -> None:
        """After the focus moves, the new focus child is marked and the old one is plain again."""
        for name, make in _MARKING_CONTAINERS.items():
            with self.subTest(name):
                container, size = make(unfocused_focus_attr="mark")
                container.render(size)
                container.focus_position = 0
                attributes = _attributes(container.render(size))
                self.assertNotEqual("plain", attributes["a"])
                self.assertEqual("plain", attributes["c"])

    def test_rejects_unhashable_attributes(self) -> None:
        """An attribute map with an unhashable value is rejected, as :class:`AttrMap` rejects it."""
        with self.assertRaises(urwid.AttrMapError):
            urwid.Pile(_cells("a"), unfocused_focus_attr={"plain": ["mark"]})
