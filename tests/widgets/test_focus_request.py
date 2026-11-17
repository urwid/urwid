from __future__ import annotations

import typing
import unittest

import urwid
from urwid.widget.widget import _FOCUS_REQUEST

if typing.TYPE_CHECKING:
    from collections.abc import Callable


class Requester(urwid.Text):
    """A one-row widget that asks for the focus on a press of mouse button 3, after running `on_press`."""

    def __init__(
        self,
        label: str,
        *,
        selectable: bool = True,
        ask: bool = True,
        on_press: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(label)
        self._is_selectable = selectable
        self.ask = ask
        self.on_press = on_press

    def selectable(self) -> bool:
        return self._is_selectable

    def keypress(self, size: tuple[int], key: str) -> str | None:
        return key

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        if self.on_press is not None:
            self.on_press()
        if self.ask and button == 3 and urwid.util.is_mouse_press(event):
            self.request_focus()
        return True


def press(widget: urwid.Widget, size: tuple[int, ...], col: int, row: int, button: int = 3) -> bool | None:
    return widget.mouse_event(size, "mouse press", button, col, row, True)


class ListContainerTest(unittest.TestCase):
    """Pile and Columns: two children, the second one asks for the focus.

    `build` returns the container and the (col, row) of its second child, at the size in `SIZES`.
    """

    BUILDERS: typing.ClassVar[dict[str, Callable[[list[urwid.Widget]], urwid.Widget]]] = {
        "Pile": lambda children: urwid.Pile(children),
        "Columns": lambda children: urwid.Columns(children),
    }
    SIZES: typing.ClassVar[dict[str, tuple[int, ...]]] = {"Pile": (4,), "Columns": (8,)}
    SECOND: typing.ClassVar[dict[str, tuple[int, int]]] = {"Pile": (0, 1), "Columns": (5, 0)}

    def cases(self) -> typing.Iterator[tuple[str, Callable[[list[urwid.Widget]], urwid.Widget]]]:
        for name, build in self.BUILDERS.items():
            with self.subTest(name):
                yield name, build

    def test_request_moves_the_focus(self) -> None:
        """A selectable child that asks gets the focus on button 3; one that does not ask, or cannot take it, not."""
        for description, child, expected in (
            ("asks", Requester("b"), 1),
            ("does not ask", Requester("b", ask=False), 0),
            ("not selectable", Requester("b", selectable=False), 0),
        ):
            for name, build in self.cases():
                with self.subTest(description):
                    container = build([Requester("a"), child])
                    press(container, self.SIZES[name], *self.SECOND[name])
                    self.assertEqual(expected, container.focus_position)

    def test_focus_changed_is_sent_once(self) -> None:
        for name, build in self.cases():
            container = build([Requester("a"), Requester("b")])
            changes: list[tuple[int, int]] = []
            urwid.connect_signal(container, "focus changed", lambda _w, old, new: changes.append((old, new)))
            press(container, self.SIZES[name], *self.SECOND[name])
            self.assertEqual([(0, 1)], changes)

    def test_button_1_is_unchanged(self) -> None:
        for name, build in self.cases():
            container = build([Requester("a"), Requester("b", ask=False)])
            press(container, self.SIZES[name], *self.SECOND[name], button=1)
            self.assertEqual(1, container.focus_position)

    def test_request_goes_up(self) -> None:
        """The container above focuses the container the request came through."""
        for name, build in self.cases():
            inner = build([Requester("a"), Requester("b")])
            outer = urwid.Pile([Requester("x"), inner])
            col, row = self.SECOND[name]
            press(outer, self.SIZES[name], col, row + 1)
            self.assertEqual((1, 1), (outer.focus_position, inner.focus_position))

    def test_changed_container_drops_the_request(self) -> None:
        """A handler that removes its own widget or reorders the contents gets no focus move, here or above."""
        for description, change in (
            ("removes its own widget", lambda container: container.contents.pop(1)),
            ("reorders the contents", lambda container: container.contents.reverse()),
        ):
            for name, build in self.cases():
                with self.subTest(description):
                    child = Requester("b")
                    inner = build([Requester("a"), child])
                    child.on_press = lambda inner=inner, change=change: change(inner)
                    outer = urwid.Pile([Requester("x"), inner])
                    col, row = self.SECOND[name]
                    press(outer, self.SIZES[name], col, row + 1)
                    self.assertEqual(0, outer.focus_position)
                    self.assertIsNot(child, inner.focus)

    def test_explicit_focus_wins(self) -> None:
        """A handler that moved the focus itself keeps it, and the container above still focuses this one."""
        for name, build in self.cases():
            child = Requester("b")
            inner = build([Requester("a"), child, Requester("c")])
            child.on_press = lambda inner=inner: setattr(inner, "focus_position", 2)
            outer = urwid.Pile([Requester("x"), inner])
            col, row = self.SECOND[name]
            press(outer, self.SIZES[name], col, row + 1)
            self.assertEqual((1, 2), (outer.focus_position, inner.focus_position))


class FrameTest(unittest.TestCase):
    def frame(self, footer: urwid.Widget) -> urwid.Frame:
        return urwid.Frame(urwid.ListBox([Requester("body")]), header=Requester("head"), footer=footer)

    def test_request_from_the_footer(self) -> None:
        footer = Requester("foot")
        frame = self.frame(footer)
        changes: list[tuple[str, str]] = []
        urwid.connect_signal(frame, "focus changed", lambda _w, old, new: changes.append((old, new)))
        press(frame, (6, 4), 0, 3)
        self.assertEqual("footer", frame.focus_position)
        self.assertEqual([("body", "footer")], changes)

    def test_replaced_part_drops_the_request(self) -> None:
        footer = Requester("foot")
        frame = self.frame(footer)
        footer.on_press = lambda: setattr(frame, "footer", Requester("new"))
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(frame, 4)])
        press(outer, (6,), 0, 4)
        self.assertEqual(("body", 0), (frame.focus_position, outer.focus_position))


class ListBoxTest(unittest.TestCase):
    def list_box(self, rows: int = 3) -> tuple[urwid.ListBox, list[Requester]]:
        children = [Requester(f"r{index}") for index in range(rows)]
        return urwid.ListBox(urwid.SimpleFocusListWalker(children)), children

    def test_request_moves_the_focus(self) -> None:
        list_box, _children = self.list_box()
        press(list_box, (4, 3), 0, 2)
        self.assertEqual(2, list_box.focus_position)

    def test_single_row_passes_the_request_up(self) -> None:
        """A row with no neighbour is still found at its position, so the request reaches the container above."""
        list_box, _children = self.list_box(1)
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 1)])
        press(outer, (4,), 0, 1)
        self.assertEqual(1, outer.focus_position)

    def test_changed_body_drops_the_request(self) -> None:
        for description, change in (
            ("removes its own row", lambda list_box: list_box.body.pop(2)),
            ("inserts a row above it", lambda list_box: list_box.body.insert(0, Requester("new"))),
            ("replaces the body", lambda list_box: setattr(list_box, "body", urwid.SimpleFocusListWalker([]))),
        ):
            with self.subTest(description):
                list_box, children = self.list_box()
                children[2].on_press = lambda list_box=list_box, change=change: change(list_box)
                outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 3)])
                press(outer, (4,), 0, 3)
                self.assertEqual(0, outer.focus_position)
                self.assertIsNot(children[2], list_box.focus)

    def test_walker_that_creates_widgets(self) -> None:
        """A walker that creates a new row widget on every call, at string positions, still takes requests."""
        on_press: list[Callable[[GeneratedWalker], None]] = []
        walker = GeneratedWalker(on_press)
        list_box = urwid.ListBox(walker)
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 3)])
        press(outer, (4,), 0, 3)
        self.assertEqual((1, "c"), (outer.focus_position, list_box.focus_position))

        for description, change in (
            ("the position is gone", lambda walker: walker.keys.remove("b")),
            ("the body is replaced", lambda walker: setattr(list_box, "body", urwid.SimpleFocusListWalker([]))),
        ):
            with self.subTest(description):
                walker = GeneratedWalker([change])
                list_box.body = walker
                outer.focus_position = 0
                press(outer, (4,), 0, 2)
                self.assertEqual(0, outer.focus_position)

    def test_filtered_walker_checks_the_widget(self) -> None:
        """A walker that keeps its widgets, but is not a sequence, drops a request once another row took the index."""
        source = urwid.SimpleFocusListWalker([Requester(f"r{index}") for index in range(3)])
        list_box = urwid.ListBox(urwid.FilteredListWalker(source))
        source[2].on_press = lambda: source.insert(1, Requester("new"))
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 4)])
        press(outer, (4,), 0, 3)
        self.assertEqual((0, 0), (outer.focus_position, list_box.focus_position))

    def test_walker_rejecting_a_removed_position(self) -> None:
        """A walker that raises ValueError for a position it no longer has drops the request without an error."""
        walker = GeneratedWalker([lambda walker: walker.keys.remove("c")])
        walker.strict = True
        list_box = urwid.ListBox(walker)
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 3)])
        press(outer, (4,), 0, 3)
        self.assertEqual(0, outer.focus_position)

    def test_explicit_focus_wins(self) -> None:
        list_box, children = self.list_box()
        children[2].on_press = lambda: setattr(list_box, "focus_position", 1)
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(list_box, 3)])
        press(outer, (4,), 0, 3)
        self.assertEqual((1, 1), (outer.focus_position, list_box.focus_position))


class TabsTest(unittest.TestCase):
    def test_request_from_the_body_takes_the_focus_from_the_bar(self) -> None:
        tabs = urwid.Tabs(
            [("one", urwid.Filler(Requester("body"), valign="top")), ("two", urwid.SolidFill("."))],
            bar_selectable=True,
        )
        # A button 1 press on the label focuses the selectable bar; the body is on row 1.
        press(tabs, (10, 4), 0, 0, button=1)
        self.assertTrue(tabs._bar_focused)
        press(tabs, (10, 4), 0, 1)
        self.assertFalse(tabs._bar_focused)

    def test_bar_focus_set_by_the_handler_is_kept(self) -> None:
        body = Requester("body")
        tabs = urwid.Tabs(
            [("one", urwid.Filler(body, valign="top")), ("two", urwid.SolidFill("."))],
            bar_selectable=True,
        )
        body.on_press = lambda: setattr(tabs, "_bar_focused", True)
        press(tabs, (10, 4), 0, 1)
        self.assertTrue(tabs._bar_focused)

    def test_switched_tab_drops_the_request(self) -> None:
        body = Requester("body")
        tabs = urwid.Tabs(
            [("one", urwid.Filler(body, valign="top")), ("two", urwid.Filler(Requester("2"), valign="top"))],
        )
        body.on_press = lambda: setattr(tabs, "focus_position", 1)
        outer = urwid.Pile([Requester("x"), urwid.BoxAdapter(tabs, 4)])
        press(outer, (10,), 0, 2)
        self.assertEqual((0, 1), (outer.focus_position, tabs.focus_position))


class GeneratedWalker(urwid.ListWalker):
    """Walker over the positions "a", "b", "c" that creates a new row widget each time it is asked for one.

    Each row runs the callbacks in `on_press` with the walker when it is pressed, before asking for the focus.
    """

    def __init__(self, on_press: list[Callable[[GeneratedWalker], None]]) -> None:
        super().__init__()
        self.keys = ["a", "b", "c"]
        self.focus = "a"
        self.on_press = on_press
        # Look positions up with list.index(), which raises ValueError for a position the walker no longer has.
        self.strict = False

    def _row(self, key: str | None) -> tuple[Requester | None, str | None]:
        if key not in self.keys:
            return None, None
        row = Requester(key)
        row.on_press = lambda: [callback(self) for callback in self.on_press]
        return row, key

    def get_focus(self) -> tuple[Requester | None, str | None]:
        return self._row(self.focus)

    def set_focus(self, position: str) -> None:
        self.focus = position
        self._modified()

    def get_next(self, position: str) -> tuple[Requester | None, str | None]:
        index = self.keys.index(position) + 1 if self.strict or position in self.keys else len(self.keys)
        return self._row(self.keys[index] if index < len(self.keys) else None)

    def get_prev(self, position: str) -> tuple[Requester | None, str | None]:
        index = self.keys.index(position) - 1 if self.strict or position in self.keys else -1
        return self._row(self.keys[index] if index >= 0 else None)


class LeafNode(urwid.TreeNode):
    def load_widget(self) -> urwid.TreeWidget:
        return LeafWidget(self)


class LeafWidget(urwid.TreeWidget):
    def selectable(self) -> bool:
        return True

    def mouse_event(self, size, event, button, col, row, focus) -> bool:  # noqa: ANN001
        if button == 3:
            self.request_focus()
            return True
        return super().mouse_event(size, event, button, col, row, focus)


class TreeRoot(urwid.ParentNode):
    def load_child_keys(self) -> list[int]:
        return [0, 1, 2]

    def load_child_node(self, key: int) -> LeafNode:
        return LeafNode(f"leaf {key}", parent=self, key=key, depth=1)


class PassThroughTest(unittest.TestCase):
    """The request reaches the outer Pile through containers and decorations that do not handle it themselves."""

    def assert_reaches_outer(self, widget: urwid.Widget, size: tuple[int, ...], col: int, row: int) -> None:
        outer = urwid.Pile([Requester("x"), (urwid.GIVEN, size[-1], widget) if len(size) == 2 else widget])
        # Rendered first, as a main loop does: ScrollBar places the event by the layout of its last render.
        outer.render(size[:1], focus=True)
        press(outer, size[:1], col, row + 1)
        self.assertEqual(1, outer.focus_position)

    def test_decorations(self) -> None:
        for description, build, row in (
            ("Padding", lambda w: urwid.Padding(w, left=1), 1),
            ("AttrMap", lambda w: urwid.AttrMap(w, "a"), 1),
            ("LineBox", urwid.LineBox, 2),
        ):
            with self.subTest(description):
                pile = urwid.Pile([Requester("a"), Requester("b")])
                self.assert_reaches_outer(build(pile), (8,), 1, row)
                self.assertEqual(1, pile.focus_position)

    def test_filler_and_box_containers(self) -> None:
        pile = urwid.Pile([Requester("a"), Requester("b")])
        self.assert_reaches_outer(urwid.Filler(pile, valign="top"), (8, 3), 0, 1)
        self.assertEqual(1, pile.focus_position)

    def test_grid_flow(self) -> None:
        cells = [Requester(str(index)) for index in range(4)]
        grid = urwid.GridFlow(cells, cell_width=2, h_sep=0, v_sep=0, align="left")
        self.assert_reaches_outer(grid, (4,), 2, 1)
        self.assertEqual(3, grid.focus_position)

    def test_table(self) -> None:
        cells = [[Requester(f"a{index}"), Requester(f"b{index}")] for index in range(3)]
        table = urwid.Table([urwid.TableColumn(), urwid.TableColumn()], cells, header=False)
        self.assert_reaches_outer(table, (8, 3), 4, 2)
        self.assertEqual((2, 1), (table.focus_position, table.focus.focus_position))

    def test_scroll_bar_list_box(self) -> None:
        list_box = urwid.ListBox(urwid.SimpleFocusListWalker([Requester(f"r{index}") for index in range(6)]))
        self.assert_reaches_outer(urwid.ScrollBar(list_box), (6, 3), 0, 2)
        self.assertEqual(2, list_box.focus_position)

    def test_tree_list_box(self) -> None:
        tree = urwid.TreeListBox(urwid.TreeWalker(TreeRoot("root")))
        self.assert_reaches_outer(tree, (12, 4), 3, 3)
        self.assertEqual("leaf 2", tree.focus.get_node().get_value())

    def test_nested_list_box(self) -> None:
        list_box = urwid.ListBox(urwid.SimpleFocusListWalker([Requester(f"r{index}") for index in range(3)]))
        pile = urwid.Pile([Requester("p"), urwid.BoxAdapter(list_box, 3)])
        columns = urwid.Columns([Requester("c"), pile])
        press(columns, (8,), 5, 3)
        self.assertEqual((1, 1, 2), (columns.focus_position, pile.focus_position, list_box.focus_position))

    def test_overlay_and_pop_up_target(self) -> None:
        pile = urwid.Pile([Requester("a"), Requester("b")])
        self.assert_reaches_outer(urwid.PopUpTarget(urwid.Filler(pile, valign="top")), (8, 3), 0, 1)
        self.assertEqual(1, pile.focus_position)

        top = urwid.Pile([Requester("o"), Requester("p")])
        overlay = urwid.Overlay(top, urwid.SolidFill("."), "left", 2, "top", None, left=6, top=0)
        self.assert_reaches_outer(overlay, (8, 3), 6, 1)
        self.assertEqual(1, top.focus_position)


class DispatchScopeTest(unittest.TestCase):
    def test_request_outside_an_event_is_ignored(self) -> None:
        child = Requester("b")
        pile = urwid.Pile([Requester("a"), child])
        child.request_focus()
        press(pile, (4,), 0, 0, button=1)
        self.assertEqual(0, pile.focus_position)
        self.assertIsNone(_FOCUS_REQUEST.get())

    def test_exception_from_the_child(self) -> None:
        """A child that raises takes its request with it, and the context variable is restored."""

        def fail() -> None:
            raise RuntimeError("handler failed")

        child = Requester("b")
        inner = urwid.Pile([Requester("a"), child])
        outer = urwid.Pile([Requester("x"), inner])

        class Catcher(Requester):
            def mouse_event(self, *args: typing.Any) -> bool:
                child.request_focus()
                child.on_press = fail
                try:
                    press(outer, (4,), 0, 2)
                except RuntimeError:
                    pass
                return True

        catcher = Catcher("c")
        top = urwid.Pile([Requester("t"), catcher])
        press(top, (4,), 0, 1, button=1)
        # The request made before the failed nested dispatch belongs to the catcher, which keeps it.
        self.assertEqual(1, top.focus_position)
        self.assertEqual((0, 0), (outer.focus_position, inner.focus_position))
        self.assertIsNone(_FOCUS_REQUEST.get())

    def test_nested_dispatch(self) -> None:
        """A second dispatch starts fresh; a request made inside it travels up through the widget that started it."""
        for description, ask_before, nested_asks, expected in (
            # The forwarding widget asks, then forwards a button 3 press to a row that does not ask:
            # the other tree keeps its focus.
            ("request before a nested dispatch", True, False, (1, 0)),
            # The forwarding widget does not ask, the row in the other tree does: both move.
            ("request inside the nested dispatch", False, True, (1, 1)),
        ):
            with self.subTest(description):
                other = urwid.Pile([Requester("p"), Requester("o", ask=nested_asks)])

                class Forwarder(Requester):
                    def mouse_event(
                        self,
                        *args: typing.Any,
                        ask_before: bool = ask_before,
                        other: urwid.Pile = other,
                    ) -> bool:
                        if ask_before:
                            self.request_focus()
                        press(other, (4,), 0, 1)
                        return True

                outer = urwid.Pile([Requester("x"), Forwarder("f")])
                press(outer, (4,), 0, 1)
                self.assertEqual(expected, (outer.focus_position, other.focus_position))


if __name__ == "__main__":
    unittest.main()
