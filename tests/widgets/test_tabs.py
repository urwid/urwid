"""Tests for :class:`urwid.Tabs`."""

from __future__ import annotations

import typing
import unittest
import weakref

import urwid
from tests.util import SelectableText, assert_redraws_after_child_change, collect_and_count_alive
from urwid.command_map import Command
from urwid.testing import ScriptedScreen, check_sizing, click, press, render_runs, render_text
from urwid.util import LayeredAttr


def command_map() -> urwid.CommandMap:
    """Return a command map with the tab commands bound to ``]`` and ``[``, and to ``meta right`` and ``meta left``."""
    cm = urwid.CommandMap()
    cm.bind(Command.NEXT_TAB, "]", "meta right")
    cm.bind(Command.PREVIOUS_TAB, "[", "meta left")
    return cm


def make(*labels: str, bodies: list[urwid.Widget] | None = None, **kwargs: typing.Any) -> urwid.Tabs:
    """Return tabs with *labels* over *bodies*, by default a ``Text`` naming the label, with the commands bound."""
    if bodies is None:
        bodies = [urwid.Text(f"{label} body") for label in labels]
    tabs = urwid.Tabs(zip(labels, bodies, strict=True), **kwargs)
    tabs._command_map = command_map()
    return tabs


def record(tabs: urwid.Tabs) -> list[tuple[int | None, int | None]]:
    """Return the list the ``"focus changed"`` signals of *tabs* are appended to, as ``(old, new)``."""
    seen: list[tuple[int | None, int | None]] = []
    urwid.connect_signal(tabs, "focus changed", lambda _w, old, new: seen.append((old, new)))
    return seen


class TabsConstructionTest(unittest.TestCase):
    """Building a ``Tabs`` and its ``contents``."""

    def test_labels_and_contents(self) -> None:
        """Markup labels become clipped ``Text``, widget labels are kept, and contents hold (body, label)."""
        body_a, body_b = urwid.Text("a"), urwid.Text("b")
        label_b = urwid.Text("B")
        tabs = urwid.Tabs([("A", body_a), (label_b, body_b)])
        self.assertIs(body_a, tabs.contents[0][0])
        self.assertIsInstance(tabs.contents[0][1], urwid.Text)
        self.assertEqual(urwid.WrapMode.CLIP, tabs.contents[0][1].wrap)
        self.assertEqual((body_b, label_b), tabs.contents[1])
        self.assertIs(body_a, tabs[0])
        self.assertIs(label_b, urwid.Tabs.options(label_b))
        self.assertEqual("Log", urwid.Tabs.options("Log").text)

    def test_invalid_arguments(self) -> None:
        """Invalid constructor arguments raise the documented exceptions."""
        text = urwid.Text("x")
        for description, args, kwargs, error in (
            ("body not a widget", ([("a", "body")],), {}, TypeError),
            ("label not fixed", ([(urwid.Edit(), text)],), {}, ValueError),
            ("body fixed only", ([("a", urwid.BigText("a", urwid.Thin3x3Font()))],), {}, ValueError),
            ("bar position", ([],), {"bar_position": "middle"}, ValueError),
            ("dividechars", ([],), {"dividechars": -1}, ValueError),
            ("dividechars bool", ([],), {"dividechars": True}, ValueError),
            (
                "selected past the end",
                ([("a", text), ("b", urwid.Text("y")), ("c", urwid.Text("z"))],),
                {"selected": 3},
                IndexError,
            ),
        ):
            with self.subTest(description), self.assertRaises(error):
                urwid.Tabs(*args, **kwargs)

    def test_empty_ignores_selected(self) -> None:
        """An empty ``Tabs`` accepts any ``selected`` and has no focus."""
        tabs = urwid.Tabs([], selected=5)
        self.assertIsNone(tabs.focus)
        with self.assertRaises(IndexError):
            _ = tabs.focus_position
        with self.assertRaises(IndexError):
            tabs.focus_position = 0

    def test_contents_validation(self) -> None:
        """Invalid items are rejected by ``contents`` and leave it unchanged."""
        tabs = make("a")
        for description, item, error in (
            ("not a pair", urwid.Text("x"), TypeError),
            ("label not a widget", (urwid.Text("x"), "label"), TypeError),
            ("label not fixed", (urwid.Text("x"), urwid.Edit()), ValueError),
            ("body fixed only", (urwid.BigText("a", urwid.Thin3x3Font()), urwid.Text("l")), ValueError),
        ):
            with self.subTest(description), self.assertRaises(error):
                tabs.contents.append(item)  # type: ignore[arg-type]
        self.assertEqual(1, len(tabs))

    def test_contents_setter(self) -> None:
        """Assigning ``contents`` replaces the tabs."""
        tabs = make("a", "b")
        body = urwid.Text("new")
        tabs.contents = [(body, urwid.Tabs.options("N"))]
        self.assertIs(body, tabs.focus)
        self.assertEqual(["N   ", "new "], render_text(tabs, (4,)))

    def test_focus_path_through_a_container_body(self) -> None:
        """Focus paths and focus widgets pass through the selected body."""
        edit = urwid.Edit()
        tabs = make("a", "b", bodies=[urwid.Text("x"), urwid.Pile([urwid.Text("t"), edit])], selected=1)
        self.assertEqual([1, 1], tabs.get_focus_path())
        self.assertIs(edit, tabs.get_focus_widgets()[-1])
        tabs.set_focus_path([0])
        self.assertEqual(0, tabs.focus_position)

    def test_repr(self) -> None:
        """The repr lists the tab count and the arguments that differ from their defaults."""
        self.assertEqual("<Tabs box/flow widget (0 tabs)>", repr(urwid.Tabs()))
        self.assertEqual("<Tabs box/flow widget (1 tab)>", repr(urwid.Tabs([("a", urwid.Text("x"))])))
        tabs = make("a", "b", selected=1, bar_position="bottom", bar_selectable=True, dividechars=2)
        tabs.unfocused_focus_attr = "marked"
        self.assertEqual(
            "<Tabs selectable box/flow widget (2 tabs) bar_position=<VAlign.BOTTOM: 'bottom'> bar_selectable=True "
            "dividechars=2 selected=1 unfocused_focus_attr={None: 'marked'}>",
            repr(tabs),
        )


class TabsSelectionTest(unittest.TestCase):
    """The selected tab and the ``"focus changed"`` signal on contents changes."""

    def test_setter(self) -> None:
        """The setter rejects invalid positions and reports a change once."""
        tabs = make("a", "b")
        seen = record(tabs)
        for position in (2, -1, "1", None):
            with self.subTest(position=position), self.assertRaises(IndexError):
                tabs.focus_position = position  # type: ignore[assignment]
        tabs.focus_position = 0  # unchanged: not reported
        tabs.focus_position = 1
        self.assertEqual([(0, 1)], seen)
        self.assertEqual(["a b", "b b", "ody"], render_text(tabs, (3,)))

    def test_removal(self) -> None:
        """Removing or replacing tabs reports index changes only."""
        for description, selected, change, expected_position, expected_signals in (
            ("selected middle tab", 1, lambda c: c.__delitem__(1), 1, []),
            ("selected last tab", 2, lambda c: c.__delitem__(2), 1, [(2, 1)]),
            ("tab before the selection", 2, lambda c: c.__delitem__(0), 1, [(2, 1)]),
            ("replace the selected tab", 1, lambda c: c.__setitem__(1, (urwid.Text("n"), urwid.Text("N"))), 1, []),
            ("emptying", 1, lambda c: c.clear(), None, [(1, None)]),
        ):
            with self.subTest(description):
                tabs = make("a", "b", "c", selected=selected)
                before = tabs.focus
                seen = record(tabs)
                change(tabs.contents)
                self.assertEqual(expected_signals, seen)
                self.assertEqual(expected_position, tabs.focus_position if tabs.contents else None)
                if description == "tab before the selection":
                    self.assertIs(before, tabs.focus)

    def test_empty_widget(self) -> None:
        """An emptied ``Tabs`` renders blank and handles nothing."""
        tabs = make("a")
        del tabs.contents[:]
        self.assertIsNone(tabs.focus)
        self.assertFalse(tabs.selectable())
        self.assertEqual("]", tabs.keypress((5,), "]"))
        self.assertFalse(click(tabs, (5, 3), 0, 0))
        self.assertEqual([], render_text(tabs, (5,)))
        self.assertEqual(["     "] * 2, render_text(tabs, (5, 2)))
        self.assertEqual(0, tabs.rows((5,)))
        self.assertIsNone(tabs.get_cursor_coords((5,)))
        check_sizing(tabs, cols=10, rows=4)


class TabsDispatchTest(unittest.TestCase):
    """A ``Tabs`` with two or more tabs takes the tab commands even when no body is selectable."""

    def test_through_pile(self) -> None:
        """A parent ``Pile`` passes the bound command to the tabs, also over an ``Edit`` body."""
        tabs = make("a", "b", bodies=[urwid.Edit("> "), urwid.Text("text")])
        pile = urwid.Pile([urwid.Text("head"), tabs])
        self.assertIs(tabs, pile.focus)
        self.assertEqual([], press(pile, (10,), "meta right"))
        self.assertEqual(1, tabs.focus_position)
        self.assertEqual([], press(pile, (10,), "meta right"))
        self.assertEqual(0, tabs.focus_position)
        self.assertEqual([], press(pile, (10,), "x"))
        self.assertEqual("x", tabs.focus.edit_text)

    def test_text_bodies(self) -> None:
        """Two tabs of ``Text`` are focused by a parent and switch on the command."""
        tabs = make("a", "b")
        pile = urwid.Pile([urwid.Text("head"), tabs])
        self.assertIs(tabs, pile.focus)
        self.assertEqual([], press(pile, (10,), "]"))
        self.assertEqual(1, tabs.focus_position)
        self.assertEqual(["up"], press(pile, (10,), "up"))

    def test_single_text_tab_is_skipped(self) -> None:
        """A single tab with a ``Text`` body is not selectable for a parent."""
        tabs = make("a")
        pile = urwid.Pile([tabs, urwid.Button("b")])
        self.assertEqual(1, pile.focus_position)

    def test_main_loop(self) -> None:
        """A key bound on the global command map switches tabs through ``MainLoop``."""
        self.addCleanup(urwid.command_map.restore_defaults)
        urwid.command_map.bind(Command.NEXT_TAB, "meta right")
        tabs = urwid.Tabs([("a", urwid.Text("first")), ("b", urwid.Text("second"))])
        screen = ScriptedScreen(size=(8, 3))
        loop = urwid.MainLoop(urwid.Filler(urwid.Pile([urwid.Text("head"), tabs]), valign="top"), screen=screen)
        loop.screen.start()
        self.addCleanup(loop.screen.stop)
        loop.process_input(["meta right"])
        loop.draw_screen()
        self.assertEqual(["head    ", "a b     ", "second  "], screen.last_text)


class TabsRenderTest(unittest.TestCase):
    """Rendering the bar and the selected body."""

    def test_positions_and_sizes(self) -> None:
        """Top and bottom bars render at flow and box sizes, with any divider width."""
        for description, kwargs, size, expected in (
            ("top flow", {}, (8,), ["a bb    ", "a body  "]),
            ("bottom flow", {"bar_position": "bottom"}, (8,), ["a body  ", "a bb    "]),
            ("top box", {}, (8, 3), ["a bb    ", "a body  ", "        "]),
            ("bottom box", {"bar_position": "bottom"}, (8, 3), ["a body  ", "        ", "a bb    "]),
            ("no divider", {"dividechars": 0}, (8,), ["abb     ", "a body  "]),
            ("three dividers", {"dividechars": 3}, (8,), ["a   bb  ", "a body  "]),
            ("bar only", {}, (8, 1), ["a bb    "]),
            ("no rows", {}, (8, 0), []),
            ("trimmed flow body", {}, (3, 2), ["a b", "a b"]),
        ):
            with self.subTest(description):
                tabs = make("a", "bb", **kwargs)
                self.assertEqual(expected, render_text(tabs, size))

    def test_box_bodies(self) -> None:
        """Box bodies keep their box layout and flow-only bodies are padded or trimmed."""
        tabs = make(
            "a",
            "b",
            "c",
            bodies=[urwid.SolidFill("#"), urwid.Filler(urwid.Text("A"), valign="bottom"), urwid.Text("x\ny\nz")],
        )
        self.assertEqual(["a b c", "#####", "#####"], render_text(tabs, (5, 3)))
        tabs.focus_position = 1
        self.assertEqual(["a b c", "     ", "A    "], render_text(tabs, (5, 3)))
        tabs.focus_position = 2
        self.assertEqual(["a b c", "x    ", "y    "], render_text(tabs, (5, 3)))
        self.assertEqual(["a b c", "x    ", "y    ", "z    ", "     "], render_text(tabs, (5, 5)))

    def test_only_the_selected_body_renders(self) -> None:
        """Bodies that are not selected are not rendered."""
        rendered: list[str] = []

        class Counting(urwid.Text):
            """Text that records each render."""

            def render(self, size, focus=False):
                rendered.append(self.text)
                return super().render(size, focus)

        tabs = urwid.Tabs([("a", Counting("one")), ("b", Counting("two"))], selected=1)
        tabs.render((5,))
        self.assertEqual(["two"], rendered)

    def test_label_sizes(self) -> None:
        """A fixed-only label is trimmed to one row and a long label is clipped."""
        big = urwid.BigText("ab", urwid.Thin3x3Font())
        tabs = urwid.Tabs([(big, urwid.Text("x")), ("long label", urwid.Text("y"))], selected=1)
        self.assertEqual(1, tabs.render((20,)).rows() - 1)
        self.assertEqual(["long ", "y    "], render_text(tabs, (5,)))

    def test_redraws_after_child_change(self) -> None:
        """Changes to a body or a label redraw the cached canvas."""
        edit = urwid.Edit("", "ab")
        tabs = urwid.Tabs([("e", edit), ("t", urwid.Text("x"))])
        assert_redraws_after_child_change(self, tabs, (5,), lambda: edit.insert_text("c"), (b"e t  ", b"abc  "))
        label = tabs.contents[1][1]
        assert_redraws_after_child_change(self, tabs, (5,), lambda: label.set_text("T"), (b"e T  ", b"abc  "))

    def test_option_setters_redraw(self) -> None:
        """Each option setter redraws the widget."""

        def make_tabs(**kwargs: typing.Any) -> urwid.Tabs:
            return make("a", "b", **kwargs)

        for name, value in (("bar_position", urwid.VAlign.BOTTOM), ("dividechars", 3)):
            with self.subTest(name):
                urwid.CanvasCache.clear()
                self.addCleanup(urwid.CanvasCache.clear)
                widget = make_tabs()
                old = widget.render((8,))
                setattr(widget, name, value)
                self.assertNotEqual(old.text, widget.render((8,)).text)
                self.assertEqual(make_tabs(**{name: value}).render((8,)).text, widget.render((8,)).text)
        for name in ("attr_map", "selected_map", "focus_map", "unfocused_focus_attr"):
            with self.subTest(name):
                widget = make_tabs(bar_selectable=True)
                press(widget, (8,), "up")
                old = render_runs(widget, (8,), focus=name != "unfocused_focus_attr")
                setattr(widget, name, "x")
                self.assertEqual({None: "x"}, getattr(widget, name))
                self.assertNotEqual(old, render_runs(widget, (8,), focus=name != "unfocused_focus_attr"))
        widget = make_tabs(bar_selectable=True)
        press(widget, (8,), "up")
        widget.bar_selectable = False
        self.assertIsNone(widget.get_cursor_coords((8,)))

    def test_option_errors(self) -> None:
        """Setters reject invalid values."""
        tabs = make("a")
        with self.assertRaises(ValueError):
            tabs.bar_position = "middle"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            tabs.dividechars = -1

    def test_map_getters_return_copies(self) -> None:
        """Changing a returned map does not change the widget."""
        tabs = make("a", attr_map={"a": "b"})
        tabs.attr_map["a"] = "c"  # type: ignore[index]
        self.assertEqual({"a": "b"}, tabs.attr_map)
        self.assertIsNone(tabs.selected_map)


class TabsSizingTest(unittest.TestCase):
    """Sizing modes and their checks."""

    def test_sizing_follows_the_bodies(self) -> None:
        """Flow sizing is offered only while every body is a flow widget."""
        tabs = make("a", "b")
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), tabs.sizing())
        check_sizing(tabs, cols=10, rows=4)
        tabs.contents.append((urwid.SolidFill("#"), urwid.Tabs.options("c")))
        self.assertEqual(frozenset((urwid.BOX,)), tabs.sizing())
        check_sizing(tabs, cols=10, rows=4)
        tabs.focus_position = 2
        with self.assertRaises(urwid.TabsError):
            tabs.rows((10,))
        with self.assertRaises(urwid.TabsError):
            tabs.render((10,))
        del tabs.contents[2]
        self.assertEqual(frozenset((urwid.BOX, urwid.FLOW)), tabs.sizing())

    def test_check_sizing_with_cursor(self) -> None:
        """The sizing checks pass with a body cursor and with the bar cursor."""
        for bar_position in ("top", "bottom"):
            with self.subTest(bar_position):
                tabs = make("a", "b", bodies=[urwid.Edit("> ", "x"), urwid.Text("y")], bar_position=bar_position)
                check_sizing(tabs, cols=10, rows=4)
                tabs.bar_selectable = True
                tabs.enter_selectable()
                press(tabs, (10,), "up" if bar_position == "top" else "down")
                check_sizing(tabs, cols=10, rows=4)

    def test_inside_list_box(self) -> None:
        """Tabs of flow bodies work as a ``ListBox`` row."""
        tabs = make("a", "b")
        list_box = urwid.ListBox([tabs, urwid.Text("after")])
        self.assertEqual(["a b   ", "a body", "after "], render_text(list_box, (6, 3)))
        self.assertIsNone(list_box.keypress((6, 3), "]"))
        self.assertEqual(["a b   ", "b body", "after "], render_text(list_box, (6, 3)))


class TabsAttributeTest(unittest.TestCase):
    """Display attributes of the labels."""

    def test_widget_level_maps(self) -> None:
        """``attr_map``, ``selected_map`` and ``focus_map`` apply to their labels."""
        tabs = make("a", "b", "c", attr_map="tab", selected_map="sel", focus_map="cur", bar_selectable=True)
        self.assertEqual(
            [("sel", "a"), (None, " "), ("tab", "b"), (None, " "), ("tab", "c")], render_runs(tabs, (5,))[0]
        )
        self.assertEqual(render_runs(tabs, (5,))[0], render_runs(tabs, (5,), focus=True)[0])
        press(tabs, (5,), "up", "right")
        self.assertEqual(
            [("sel", "a"), (None, " "), ("cur", "b"), (None, " "), ("tab", "c")],
            render_runs(tabs, (5,), focus=True)[0],
        )

    def test_label_own_focus_map(self) -> None:
        """The selected label gets the focus flag, and ``unfocused_focus_attr`` marks it otherwise."""

        def label() -> urwid.AttrMap:
            return urwid.AttrMap(urwid.Text("L"), "a", focus_map="a sel")

        tabs = urwid.Tabs([(label(), urwid.Text("x")), (label(), urwid.Text("y"))])
        self.assertEqual([("a sel", "L"), (None, " "), ("a", "L")], render_runs(tabs, (3,), focus=True)[0])
        self.assertEqual([("a", "L"), (None, " "), ("a", "L")], render_runs(tabs, (3,))[0])
        tabs.unfocused_focus_attr = {"a": "a marked"}
        self.assertEqual([("a marked", "L"), (None, " "), ("a", "L")], render_runs(tabs, (3,))[0])
        self.assertEqual([("a sel", "L"), (None, " "), ("a", "L")], render_runs(tabs, (3,), focus=True)[0])
        self.assertEqual(
            [("a", "x  ")],
            render_runs(
                urwid.Tabs([(label(), urwid.AttrMap(urwid.Text("x"), "a"))], unfocused_focus_attr={"a": "a marked"}),
                (3,),
            )[1],
        )

    def test_layering(self) -> None:
        """A single-attribute map layers under the label's own attribute, a named one replaces it."""
        label = urwid.AttrMap(urwid.Text("L"), "a")
        tabs = urwid.Tabs([(label, urwid.Text("x")), ("M", urwid.Text("y"))], selected=1, attr_map="tab")
        self.assertEqual(LayeredAttr("a", "tab"), render_runs(tabs, (3,))[0][0][0])
        tabs.attr_map = {"a": "tab a"}
        self.assertEqual("tab a", render_runs(tabs, (3,))[0][0][0])
        tabs = urwid.Tabs([(label, urwid.Text("x")), ("M", urwid.Text("y"))], focus_map="cur", bar_selectable=True)
        tabs.enter_selectable()
        self.assertEqual(LayeredAttr("a", "cur"), render_runs(tabs, (3,), focus=True)[0][0][0])


class TabsCursorTest(unittest.TestCase):
    """The canvas cursor and ``get_cursor_coords``."""

    def test_label_cursor_never_replaces_the_body_cursor(self) -> None:
        """A selectable label's cursor never replaces the body's cursor."""
        for bar_position, bar_row, body_row in (("top", 0, 1), ("bottom", 1, 0)):
            with self.subTest(bar_position):
                tabs = urwid.Tabs(
                    [(urwid.Button("b"), urwid.Edit("> ", "x")), ("c", urwid.Text("y"))],
                    bar_position=bar_position,
                    bar_selectable=True,
                )
                canvas = tabs.render((12,), focus=True)
                self.assertEqual((3, body_row), canvas.cursor)
                self.assertEqual((3, body_row), tabs.get_cursor_coords((12,)))
                self.assertIsNone(tabs.render((12,)).cursor)
                press(tabs, (12,), "up" if bar_position == "top" else "down")
                self.assertEqual((0, bar_row), tabs.render((12,), focus=True).cursor)
                self.assertEqual((0, bar_row), tabs.get_cursor_coords((12,)))

    def test_body_cursor_below_the_crop(self) -> None:
        """A body cursor on a row cut away is not reported."""
        edit = urwid.Edit("", "1\n2\n3", multiline=True)
        tabs = urwid.Tabs([("e", edit), ("t", urwid.Text("x"))])
        self.assertIsNone(tabs.render((4, 3), focus=True).cursor)
        self.assertIsNone(tabs.get_cursor_coords((4, 3)))
        edit.edit_pos = 0
        self.assertEqual((0, 1), tabs.render((4, 3), focus=True).cursor)
        self.assertEqual((0, 1), tabs.get_cursor_coords((4, 3)))
        self.assertIsNone(tabs.get_cursor_coords((4, 1)))


class TabsScrollTest(unittest.TestCase):
    """The bar offset when the labels do not fit."""

    labels = ("one", "two", "three", "four", "five")

    def test_selected_label_is_centred(self) -> None:
        """The selected label is centred and the ends clamp."""
        tabs = make(*self.labels)
        for selected, expected in ((0, "one two "), (2, "o three "), (4, "our five")):
            with self.subTest(selected=selected):
                tabs.focus_position = selected
                self.assertEqual(expected, render_text(tabs, (8,))[0])

    def test_offsets_are_stable(self) -> None:
        """Repeated renders and hit tests give the same offset."""
        tabs = make(*self.labels, selected=2)
        first = render_text(tabs, (8,))
        self.assertEqual(first, render_text(tabs, (8,)))
        self.assertEqual([tabs._label_at(8, 2, False)] * 3, [tabs._label_at(8, 2, False) for _ in range(3)])

    def test_click_matches_a_kept_canvas(self) -> None:
        """A click at one width hits the label a kept canvas of that width shows."""
        tabs = make(*self.labels, selected=2)
        kept = [tabs.render((width,)) for width in (8, 12, 30)]
        row = kept[0].decoded_text[0]
        col = row.index("three")
        self.assertTrue(click(tabs, (8,), col, 0))
        self.assertEqual(2, tabs.focus_position)
        self.assertTrue(click(tabs, (8,), 0, 0))
        self.assertEqual(1, tabs.focus_position)

    def test_gaps_and_degenerate_sizes(self) -> None:
        """Gaps, zero columns and zero rows handle no click and show no cursor."""
        tabs = make("a", "b")
        self.assertFalse(click(tabs, (5,), 1, 0))
        self.assertFalse(click(tabs, (5,), 4, 0))
        self.assertFalse(click(tabs, (0,), 0, 0))
        self.assertFalse(click(tabs, (5, 0), 0, 0))
        self.assertEqual([""] * 2, render_text(tabs, (0,)))
        self.assertIsNone(tabs.render((0,), focus=True).cursor)
        self.assertEqual([], render_text(tabs, (5, 0)))

    def test_oversized_label(self) -> None:
        """A label wider than the bar shows its first column, with the bar cursor on it."""
        tabs = make("a", "a very long label", "b", selected=1, bar_selectable=True)
        self.assertEqual("a very", render_text(tabs, (6,))[0])
        press(tabs, (6,), "up")
        self.assertEqual((0, 0), tabs.render((6,), focus=True).cursor)

    def test_empty_label(self) -> None:
        """An empty label takes no column and shows no cursor outside the bar."""
        tabs = make("abc", "", bar_selectable=True)
        press(tabs, (3,), "up", "right")
        self.assertEqual(1, tabs._bar_cursor)
        self.assertIsNone(tabs.render((3,), focus=True).cursor)
        self.assertEqual([0, 0, None], [tabs._label_at(3, col, True) for col in range(3)])

    def test_bar_cursor_scrolls_without_selecting(self) -> None:
        """Moving the bar cursor scrolls the bar without selecting."""
        tabs = make(*self.labels, bar_selectable=True)
        press(tabs, (8,), "up", "right", "right", "right", "right")
        self.assertEqual(0, tabs.focus_position)
        self.assertEqual("our five", render_text(tabs, (8,), focus=True)[0])
        self.assertEqual("one two", render_text(tabs, (8,))[0].rstrip())


class TabsKeyTest(unittest.TestCase):
    """Keys for the body, the bar and the tab commands."""

    def test_keys_reach_the_body(self) -> None:
        """Keys go to the selected body."""
        tabs = make("e", "t", bodies=[urwid.Edit(), urwid.Text("x")])
        self.assertEqual(["up"], press(tabs, (5,), "a", "up"))
        self.assertEqual("a", tabs.focus.edit_text)

    def test_commands(self) -> None:
        """The commands step through the tabs with wrap-around and report each change."""
        tabs = make("a", "b", "c")
        seen = record(tabs)
        self.assertEqual(["x"], press(tabs, (5,), "]", "]", "]", "[", "x"))
        self.assertEqual(2, tabs.focus_position)
        self.assertEqual([(0, 1), (1, 2), (2, 0), (0, 2)], seen)

    def test_body_handles_the_command_key_first(self) -> None:
        """A body that handles the command key keeps it."""

        class Eating(SelectableText):
            """Selectable text that handles every key."""

            def keypress(self, size, key):
                return None

        tabs = make("a", "b", bodies=[Eating("x"), urwid.Text("y")])
        self.assertEqual([], press(tabs, (5,), "]"))
        self.assertEqual(0, tabs.focus_position)

    def test_bar_navigation(self) -> None:
        """Entering the bar, moving its cursor, selecting and returning, for both bar positions."""
        for bar_position, to_bar, to_body in (("top", "up", "down"), ("bottom", "down", "up")):
            with self.subTest(bar_position):
                tabs = make(
                    "a", "b", "c", bodies=[urwid.Edit(), urwid.Edit(), urwid.Text("t")], bar_position=bar_position
                )
                self.assertEqual([to_bar], press(tabs, (5,), to_bar))
                tabs.bar_selectable = True
                seen = record(tabs)
                self.assertEqual(["left"], press(tabs, (5,), to_bar, "left"))
                self.assertEqual(["right"], press(tabs, (5,), "right", "right", "right"))
                self.assertEqual([], seen)
                self.assertEqual([], press(tabs, (5,), "left", "enter"))
                self.assertEqual([(0, 1)], seen)
                self.assertEqual([], press(tabs, (5,), to_body, "x"))
                self.assertEqual("x", tabs.focus.edit_text)
                press(tabs, (5,), to_bar, "right", "enter")
                self.assertEqual(2, tabs.focus_position)
                # a Text body does not take the focus back
                self.assertEqual([to_body], press(tabs, (5,), to_body))
                self.assertIsNotNone(tabs.render((5,), focus=True).cursor)

    def test_bar_focus_cleared(self) -> None:
        """Turning the bar off or shrinking to one tab returns the focus to the body."""
        tabs = make("a", "b", "c", bodies=[urwid.Edit(), urwid.Edit(), urwid.Edit()], bar_selectable=True)
        press(tabs, (5,), "up")
        tabs.bar_selectable = False
        self.assertEqual((0, 1), tabs.get_cursor_coords((5,)))
        tabs.bar_selectable = True
        press(tabs, (5,), "up", "right", "right")
        del tabs.contents[1:]
        self.assertEqual(0, tabs._bar_cursor)
        self.assertEqual((0, 1), tabs.get_cursor_coords((5,)))

    def test_hidden_body_gets_no_keys(self) -> None:
        """A body with no visible rows gets no keys."""
        tabs = make("a", "b", bodies=[urwid.Edit(), urwid.Text("t")])
        self.assertEqual(["x"], press(tabs, (5, 1), "x"))
        self.assertEqual("", tabs.focus.edit_text)


class TabsEnterSelectableTest(unittest.TestCase):
    """The ``enter_selectable`` entry hook."""

    def test_enter(self) -> None:
        """Entry puts the keys on a selectable body, else on a selectable bar, else changes nothing."""
        tabs = make("a", "b", bodies=[urwid.Edit(), urwid.Text("t")], bar_selectable=True)
        press(tabs, (5,), "up")
        tabs.enter_selectable()
        self.assertEqual([], press(tabs, (5,), "x"))
        self.assertEqual("x", tabs.focus.edit_text)

        tabs.focus_position = 1
        tabs.enter_selectable()
        self.assertEqual((2, 0), tabs.get_cursor_coords((5,)))

        tabs = make("a", "b", selected=1)
        tabs.enter_selectable()
        self.assertIsNone(tabs.get_cursor_coords((5,)))
        self.assertFalse(tabs._bar_focused)

    def test_enter_reaches_the_body(self) -> None:
        """Entry calls the body's own entry hook."""
        pile = urwid.Pile([urwid.Button("a"), urwid.Button("b")], select_navigation=True)
        tabs = make("p", "q", bodies=[pile, urwid.Text("t")])
        tabs.enter_selectable(reverse=True)
        self.assertEqual(1, pile.focus_position)


class TabsSingleTabTest(unittest.TestCase):
    """A single tab has nothing to switch to."""

    def test_single_tab(self) -> None:
        """One tab follows its body, keeps the bar unfocused and returns the commands."""
        tabs = make("a", bodies=[urwid.Edit()], bar_selectable=True)
        seen = record(tabs)
        self.assertTrue(tabs.selectable())
        self.assertFalse(make("a").selectable())
        self.assertEqual(["up", "meta right", "meta left"], press(tabs, (5,), "up", "meta right", "meta left"))
        self.assertTrue(click(tabs, (5,), 0, 0))
        self.assertEqual(0, tabs.focus_position)
        self.assertEqual([], seen)
        self.assertEqual((0, 1), tabs.get_cursor_coords((5,)))

        tabs.contents.append((urwid.Text("b"), urwid.Tabs.options("b")))
        self.assertEqual([], press(tabs, (5,), "up"))
        self.assertEqual((0, 0), tabs.get_cursor_coords((5,)))
        del tabs.contents[1]
        self.assertEqual((0, 1), tabs.get_cursor_coords((5,)))


class TabsMouseTest(unittest.TestCase):
    """Mouse events on the bar and on the body."""

    def test_label_press(self) -> None:
        """A press on a label selects it, and with a selectable bar focuses the bar."""
        for bar_selectable in (False, True):
            with self.subTest(bar_selectable=bar_selectable):
                tabs = make("a", "b", bodies=[urwid.Edit(), urwid.Edit()], bar_selectable=bar_selectable)
                seen = record(tabs)
                self.assertTrue(click(tabs, (5,), 2, 0))
                self.assertEqual([(0, 1)], seen)
                self.assertEqual(bar_selectable, tabs.get_cursor_coords((5,)) == (2, 0))

    def test_body_rows(self) -> None:
        """Body events are shifted by the bar row, and rows cut away are not handled."""
        for bar_position, body_row in (("top", 1), ("bottom", 0)):
            with self.subTest(bar_position):
                pile = urwid.Pile([urwid.Button("x"), urwid.Button("y")])
                tabs = make("a", "b", bodies=[pile, urwid.Text("t")], bar_position=bar_position)
                self.assertTrue(click(tabs, (8, 3), 0, body_row + 1))
                self.assertEqual(1, pile.focus_position)
                # the second button is cropped away at two rows
                self.assertFalse(click(tabs, (8, 2), 0, 2))

    def test_press_on_body_returns_the_focus(self) -> None:
        """A press on the body while the bar has the focus returns it to the body."""
        tabs = make("a", "b", bodies=[urwid.Button("x"), urwid.Text("t")], bar_selectable=True)
        press(tabs, (8,), "up")
        self.assertTrue(click(tabs, (8,), 0, 1))
        self.assertEqual((2, 1), tabs.get_cursor_coords((8,)))

    def test_unhandled_events_on_the_bar(self) -> None:
        """Other buttons, releases and the wheel are not handled on the bar."""
        tabs = make("a", "b")
        for description, kwargs in (
            ("button 3", {"button": 3}),
            ("release", {"event": "mouse release"}),
            ("wheel", {"button": 4}),
        ):
            with self.subTest(description):
                self.assertFalse(click(tabs, (5,), 2, 0, **kwargs))
        self.assertEqual(0, tabs.focus_position)


class TabsSignalTest(unittest.TestCase):
    """The ``"focus changed"`` signal."""

    def test_handler_removing_tabs_keeps_the_bar_cursor_valid(self) -> None:
        """A handler that removes tabs leaves the bar cursor on a tab, for the commands and for clicks."""
        for description, switch in (
            ("command", lambda tabs: press(tabs, (10, 3), "meta right")),
            ("click", lambda tabs: click(tabs, (10, 3), 4, 0)),
        ):
            with self.subTest(description):
                tabs = make("a", "b", "c", bar_selectable=True, selected=1)
                press(tabs, (10, 3), "up")

                def drop_last(sender: urwid.Tabs, _old: int | None, new: int | None) -> None:
                    if new == 2:
                        del sender.contents[2]

                urwid.connect_signal(tabs, "focus changed", drop_last)
                switch(tabs)
                self.assertEqual(2, len(tabs))
                self.assertLess(tabs._bar_cursor, len(tabs))
                tabs.render((10, 3), focus=True)

    def test_signal_sources(self) -> None:
        """Commands, clicks and the setter send it, also after the legacy callback is replaced."""
        tabs = make("a", "b", "c")
        seen = record(tabs)
        press(tabs, (5,), "]")
        click(tabs, (5,), 4, 0)
        tabs.focus_position = 2  # unchanged: not reported
        # pylint infers `contents` as the list test_contents_setter assigns to it
        tabs.contents.set_focus_changed_callback(lambda _new: None)  # pylint: disable=no-member
        tabs.focus_position = 0
        self.assertEqual([(0, 1), (1, 2), (2, 0)], seen)

    def test_construction_sends_nothing(self) -> None:
        """Construction sends nothing, and a subclass with its own signals keeps this one."""

        class Labelled(urwid.Tabs):
            """Tabs with a signal of its own."""

            signals: typing.ClassVar[list[str]] = ["labelled"]

        seen: list[int] = []
        original = Labelled._emit

        def emit(self: urwid.Tabs, name: str, *args: object) -> None:
            seen.append(1)
            original(self, name, *args)

        Labelled._emit = emit  # type: ignore[method-assign]
        tabs = Labelled([("a", urwid.Text("x")), ("b", urwid.Text("y"))], selected=1)
        self.assertEqual([], seen)
        self.assertEqual(["labelled", "focus changed"], Labelled.signals)
        changes = record(tabs)
        tabs.focus_position = 0
        self.assertEqual([(1, 0)], changes)


class TabsLifetimeTest(unittest.TestCase):
    """References held by ``Tabs``."""

    def test_widget_and_bodies_are_freed(self) -> None:
        """Removed bodies and a dropped widget are freed."""
        bodies = [urwid.Edit(), urwid.Text("t")]
        refs: list[weakref.ReferenceType[typing.Any]] = [weakref.ref(body) for body in bodies]
        tabs = urwid.Tabs(zip(("a", "b"), bodies, strict=True))
        tabs.render((5,), focus=True)
        del bodies
        del tabs.contents[:]
        self.assertEqual(0, collect_and_count_alive(refs))
        tabs_ref = weakref.ref(tabs)
        del tabs
        self.assertEqual(0, collect_and_count_alive([tabs_ref]))
