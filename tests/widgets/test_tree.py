from __future__ import annotations

import typing
import unittest

import urwid
from urwid import TreeNode

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable


class SelfRegisteringParent(urwid.ParentNode):
    def __init__(
        self,
        value: str,
        parent: SelfRegisteringParent | None = None,
        key: Hashable = None,
        depth: int | None = None,
        children: Iterable[SelfRegisteringChild | SelfRegisteringParent] = (),
    ) -> None:
        super().__init__(value, parent, key, depth)
        if parent:
            parent.set_child_node(key, self)

        self._child_keys = []
        for child in children:
            key = child.get_key()
            self._children[key] = child
            self._child_keys.append(key)
            child.set_parent(self)

    def load_child_keys(self) -> list[Hashable]:
        return list(self._children)

    def set_child_node(self, key: Hashable, node: TreeNode) -> None:
        super().set_child_node(key, node)
        self._child_keys = self.load_child_keys()

    def set_parent(self, parent: SelfRegisteringParent) -> None:
        self._parent = parent


class SelfRegisteringChild(urwid.TreeNode):
    def __init__(
        self,
        value: str,
        parent: SelfRegisteringParent | None = None,
        key: Hashable | None = None,
        depth: int | None = None,
    ) -> None:
        super().__init__(value, parent, key, depth)
        if parent:
            parent.set_child_node(key, self)

    def set_parent(self, parent: SelfRegisteringParent) -> None:
        self._parent = parent


class TestTree(unittest.TestCase):
    def test_basic(self):
        root = SelfRegisteringParent(
            "root",
            key="/",
            children=(SelfRegisteringChild(f"child_{idx}", key=str(idx)) for idx in range(1, 4)),
        )

        widget = urwid.TreeListBox(urwid.TreeWalker(root))
        size = (15, 5)
        expanded = (
            "- /: root      ",
            "   1: child_1  ",
            "   2: child_2  ",
            "   3: child_3  ",
            "               ",
        )
        collapsed = (
            "+ /: root      ",
            *(" " * size[0] for _ in range(size[1] - 1)),
        )
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "-")
        self.assertEqual(collapsed, widget.render(size).decoded_text)
        widget.keypress(size, "+")
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "down")
        self.assertIs(root, widget.focus_position)
        widget.keypress(size, "-")
        self.assertEqual(collapsed, widget.render(size).decoded_text)
        widget.keypress(size, "right")
        self.assertEqual(expanded, widget.render(size).decoded_text)

    def test_nested_behavior(self):
        root = SelfRegisteringParent(
            "root",
            key="/",
            children=(
                SelfRegisteringParent(
                    f"nested_{idx}",
                    key=f"{idx}/",
                    children=(SelfRegisteringChild(f"child_{idx}{cidx}", key=str(cidx)) for cidx in range(1, 4)),
                )
                for idx in range(1, 4)
            ),
        )
        widget = urwid.TreeListBox(urwid.TreeWalker(root))
        size = (18, 13)
        expanded = (
            "- /: root         ",
            "   - 1/: nested_1 ",
            "      1: child_11 ",
            "      2: child_12 ",
            "      3: child_13 ",
            "   - 2/: nested_2 ",
            "      1: child_21 ",
            "      2: child_22 ",
            "      3: child_23 ",
            "   - 3/: nested_3 ",
            "      1: child_31 ",
            "      2: child_32 ",
            "      3: child_33 ",
        )
        collapsed = (
            "+ /: root         ",
            *(" " * size[0] for _ in range(size[1] - 1)),
        )
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "-")
        self.assertEqual(collapsed, widget.render(size).decoded_text)
        widget.keypress(size, "+")
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "down")
        widget.keypress(size, "-")
        self.assertEqual(
            (
                "- /: root         ",
                "   + 1/: nested_1 ",
                "   - 2/: nested_2 ",
                "      1: child_21 ",
                "      2: child_22 ",
                "      3: child_23 ",
                "   - 3/: nested_3 ",
                "      1: child_31 ",
                "      2: child_32 ",
                "      3: child_33 ",
                "                  ",
                "                  ",
                "                  ",
            ),
            widget.render(size).decoded_text,
        )
        widget.keypress(size, "right")
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "left")
        widget.keypress(size, "-")
        self.assertEqual(collapsed, widget.render(size).decoded_text)
        widget.keypress(size, "+")
        widget.keypress(size, "page down")
        widget.keypress(size, "-")
        self.assertEqual(
            (
                "- /: root         ",
                "   - 1/: nested_1 ",
                "      1: child_11 ",
                "      2: child_12 ",
                "      3: child_13 ",
                "   - 2/: nested_2 ",
                "      1: child_21 ",
                "      2: child_22 ",
                "      3: child_23 ",
                "   + 3/: nested_3 ",
                "                  ",
                "                  ",
                "                  ",
            ),
            widget.render(size).decoded_text,
        )

    def test_deep_nested_collapse_expand(self):
        root = SelfRegisteringParent(
            "root",
            key="/",
            children=(
                SelfRegisteringParent(
                    f"nested_{top_idx}",
                    key=f"{top_idx}/",
                    children=(
                        SelfRegisteringParent(
                            f"nested_{top_idx}{first_idx}",
                            key=f"{first_idx}/",
                            children=(
                                SelfRegisteringChild(f"child_{top_idx}{first_idx}{last_idx}", key=str(last_idx))
                                for last_idx in range(1, 3)
                            ),
                        )
                        for first_idx in range(1, 3)
                    ),
                )
                for top_idx in range(1, 3)
            ),
        )
        widget = urwid.TreeListBox(urwid.TreeWalker(root))
        size = (21, 15)
        expanded = (
            "- /: root            ",
            "   - 1/: nested_1    ",
            "      - 1/: nested_11",
            "         1: child_111",
            "         2: child_112",
            "      - 2/: nested_12",
            "         1: child_121",
            "         2: child_122",
            "   - 2/: nested_2    ",
            "      - 1/: nested_21",
            "         1: child_211",
            "         2: child_212",
            "      - 2/: nested_22",
            "         1: child_221",
            "         2: child_222",
        )
        collapsed = (
            "+ /: root            ",
            *(" " * size[0] for _ in range(size[1] - 1)),
        )
        collapsed_last = (
            "- /: root            ",
            "   - 1/: nested_1    ",
            "      - 1/: nested_11",
            "         1: child_111",
            "         2: child_112",
            "      - 2/: nested_12",
            "         1: child_121",
            "         2: child_122",
            "   - 2/: nested_2    ",
            "      - 1/: nested_21",
            "         1: child_211",
            "         2: child_212",
            "      + 2/: nested_22",
            "                     ",
            "                     ",
        )
        self.assertEqual(expanded, widget.render(size).decoded_text)
        widget.keypress(size, "page down")
        widget.keypress(size, "-")
        self.assertEqual(collapsed_last, widget.render(size).decoded_text)
        widget.keypress(size, "left")
        widget.keypress(size, "-")
        self.assertEqual(
            (
                "- /: root            ",
                "   - 1/: nested_1    ",
                "      - 1/: nested_11",
                "         1: child_111",
                "         2: child_112",
                "      - 2/: nested_12",
                "         1: child_121",
                "         2: child_122",
                "   + 2/: nested_2    ",
                "                     ",
                "                     ",
                "                     ",
                "                     ",
                "                     ",
                "                     ",
            ),
            widget.render(size).decoded_text,
        )
        widget.keypress(size, "right")
        self.assertEqual(collapsed_last, widget.render(size).decoded_text)
        widget.keypress(size, "home")
        widget.keypress(size, "-")
        self.assertEqual(collapsed, widget.render(size).decoded_text)


class TestTreeNode(unittest.TestCase):
    def setUp(self) -> None:
        self.root = SelfRegisteringParent(
            "root",
            key="/",
            children=(SelfRegisteringChild(f"child_{idx}", key=str(idx)) for idx in range(1, 4)),
        )

    def test_root_properties(self):
        self.assertTrue(self.root.is_root())
        self.assertEqual(0, self.root.get_depth())
        self.assertEqual("/", self.root.get_key())
        self.assertEqual("root", self.root.get_value())
        self.assertIsNone(self.root.get_index())
        self.assertIsNone(self.root.get_parent())
        self.assertIs(self.root, self.root.get_root())
        self.assertIsNone(self.root.next_sibling())
        self.assertIsNone(self.root.prev_sibling())

    def test_child_properties(self):
        child = self.root.get_child_node("2")
        self.assertFalse(child.is_root())
        self.assertEqual(1, child.get_depth())
        self.assertEqual(1, child.get_index())
        self.assertIs(self.root, child.get_parent())
        self.assertIs(self.root, child.get_root())

    def test_siblings(self):
        first, second, last = (self.root.get_child_node(key) for key in ("1", "2", "3"))
        self.assertIs(second, first.next_sibling())
        self.assertIs(last, second.next_sibling())
        self.assertIsNone(last.next_sibling())
        self.assertIs(second, last.prev_sibling())
        self.assertIs(first, second.prev_sibling())
        self.assertIsNone(first.prev_sibling())

    def test_set_key(self):
        child = self.root.get_child_node("2")
        child.set_key("two")
        self.assertEqual("two", child.get_key())

    def test_change_key(self):
        child = self.root.get_child_node("2")
        child.change_key("two")

        self.assertEqual("two", child.get_key())
        self.assertIs(child, self.root.get_child_node("two"))
        self.assertEqual(["1", "3", "two"], list(self.root.get_child_keys(reload=True)))

    def test_change_key_in_use(self):
        child = self.root.get_child_node("2")
        with self.assertRaises(urwid.TreeWidgetError) as ctx:
            child.change_key("3")

        self.assertEqual("3 is already in use", str(ctx.exception))
        self.assertEqual("2", child.get_key())

    def test_get_child_index_unknown_key(self):
        with self.assertRaises(urwid.TreeWidgetError) as ctx:
            self.root.get_child_index("no_such_key")

        self.assertIn("Can't find key no_such_key in ParentNode /", str(ctx.exception))

    def test_get_child_widget(self):
        child = self.root.get_child_node("1")
        widget = self.root.get_child_widget("1")
        self.assertIs(child.get_widget(), widget)
        self.assertIs(child, widget.get_node())

    def test_get_widget_reload(self):
        child = self.root.get_child_node("1")
        widget = child.get_widget()
        self.assertIs(widget, child.get_widget())
        self.assertIsNot(widget, child.get_widget(reload=True))

    def test_set_child_node(self):
        extra = SelfRegisteringChild("child_4", key="4")
        self.root.set_child_node("4", extra)

        self.assertIs(extra, self.root.get_child_node("4"))
        self.assertIs(self.root.get_last_child(), extra)

    def test_first_and_last_child(self):
        self.assertIs(self.root.get_child_node("1"), self.root.get_first_child())
        self.assertIs(self.root.get_child_node("3"), self.root.get_last_child())
        self.assertTrue(self.root.has_children())

    def test_no_children(self):
        empty = SelfRegisteringParent("empty", key="empty")
        self.assertFalse(empty.has_children())
        self.assertEqual([], list(empty.get_child_keys()))

    def test_load_parent_not_implemented(self):
        orphan = TreeNode("orphan", key="orphan", depth=1)
        with self.assertRaises(urwid.TreeWidgetError) as ctx:
            orphan.get_parent()

        self.assertEqual("virtual function.  Implement in subclass", str(ctx.exception))

    def test_load_child_keys_not_implemented(self):
        node = urwid.ParentNode("node", key="node")
        with self.assertRaises(urwid.TreeWidgetError) as ctx:
            node.get_child_keys()

        self.assertEqual("virtual function.  Implement in subclass", str(ctx.exception))

    def test_load_child_node_not_implemented(self):
        node = urwid.ParentNode("node", key="node")
        with self.assertRaises(urwid.TreeWidgetError) as ctx:
            node.get_child_node("child")

        self.assertEqual("virtual function.  Implement in subclass", str(ctx.exception))


class TestTreeWidget(unittest.TestCase):
    def setUp(self) -> None:
        self.root = SelfRegisteringParent(
            "root",
            key="/",
            children=(
                SelfRegisteringParent(
                    f"nested_{idx}",
                    key=f"{idx}/",
                    children=(SelfRegisteringChild(f"child_{idx}{cidx}", key=str(cidx)) for cidx in range(1, 3)),
                )
                for idx in range(1, 3)
            ),
        )

    def test_leaf_widget(self):
        widget = self.root.get_child_node("1/").get_child_node("1").get_widget()

        self.assertTrue(widget.is_leaf)
        self.assertFalse(widget.selectable())
        self.assertIsNone(widget.first_child())
        self.assertIsNone(widget.last_child())
        self.assertEqual(6, widget.get_indent_cols())
        self.assertEqual(("      1: child_11   ",), widget.render((20,)).decoded_text)

    def test_leaf_ignores_input(self):
        widget = self.root.get_child_node("1/").get_child_node("1").get_widget()

        self.assertEqual("+", widget.keypress((20,), "+"))
        self.assertEqual("-", widget.keypress((20,), "-"))
        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 6, 0, True))

    def test_parent_widget(self):
        widget = self.root.get_widget()

        self.assertFalse(widget.is_leaf)
        self.assertTrue(widget.selectable())
        self.assertTrue(widget.expanded)
        self.assertEqual(0, widget.get_indent_cols())
        self.assertEqual("/: root", widget.get_display_text())

    def test_inner_widget_is_cached(self):
        widget = self.root.get_widget()
        inner = widget.get_inner_widget()

        self.assertIs(inner, widget.get_inner_widget())
        self.assertEqual("/: root", inner.text)

    def test_parent_without_children(self):
        widget = SelfRegisteringParent("empty", key="empty").get_widget()

        self.assertFalse(widget.is_leaf)
        self.assertTrue(widget.expanded)
        self.assertIsNone(widget.first_child())
        self.assertIsNone(widget.last_child())

    def test_children_of_collapsed_widget(self):
        widget = self.root.get_widget()
        widget.expanded = False
        widget.update_expanded_icon()

        self.assertIsNone(widget.first_child())
        self.assertIsNone(widget.last_child())
        self.assertEqual(("+ /: root           ",), widget.render((20,)).decoded_text)

    def test_first_and_last_child(self):
        widget = self.root.get_widget()
        nested_1 = self.root.get_child_node("1/")
        deepest = self.root.get_child_node("2/").get_child_node("2")

        self.assertIs(nested_1.get_widget(), widget.first_child())
        self.assertIs(deepest.get_widget(), widget.last_child())

    def test_mouse_event_toggles_expanded(self):
        widget = self.root.get_child_node("1/").get_widget()

        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertFalse(widget.expanded)
        self.assertEqual(("   + 1/: nested_1   ",), widget.render((20,)).decoded_text)

        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertTrue(widget.expanded)
        self.assertEqual(("   - 1/: nested_1   ",), widget.render((20,)).decoded_text)

    def test_mouse_event_ignored(self):
        widget = self.root.get_child_node("1/").get_widget()

        self.assertFalse(widget.mouse_event((20,), "mouse release", 1, 3, 0, True))
        self.assertFalse(widget.mouse_event((20,), "mouse press", 3, 3, 0, True))
        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 10, 0, True))
        self.assertTrue(widget.expanded)

    def test_inorder_traversal(self):
        keys = []
        widget = self.root.get_widget()
        while widget is not None:
            keys.append(widget.get_node().get_key())
            widget = widget.next_inorder()

        self.assertEqual(["/", "1/", "1", "2", "2/", "1", "2"], keys)

        backwards = []
        widget = self.root.get_child_node("2/").get_child_node("2").get_widget()
        while widget is not None:
            backwards.append(widget.get_node().get_key())
            widget = widget.prev_inorder()

        self.assertEqual(["2", "1", "2/", "2", "1", "1/", "/"], backwards)

    def test_next_inorder_skips_collapsed_children(self):
        widget = self.root.get_child_node("1/").get_widget()
        widget.expanded = False

        next_widget = widget.next_inorder()
        self.assertIsNotNone(next_widget)
        self.assertEqual("2/", next_widget.get_node().get_key())

    def test_next_inorder_inconsistent_depth(self):
        broken = SelfRegisteringChild("broken", parent=self.root, key="broken", depth=5)

        with self.assertRaises(ValueError):
            broken.get_widget().next_inorder()


class TestTreeWalker(unittest.TestCase):
    def setUp(self) -> None:
        self.root = SelfRegisteringParent(
            "root",
            key="/",
            children=(SelfRegisteringChild(f"child_{idx}", key=str(idx)) for idx in range(1, 4)),
        )
        self.walker = urwid.TreeWalker(self.root)

    def test_get_focus(self):
        widget, position = self.walker.get_focus()

        self.assertIs(self.root, position)
        self.assertIs(self.root.get_widget(), widget)

    def test_set_focus(self):
        modified = []
        urwid.connect_signal(self.walker, "modified", lambda: modified.append(True))

        child = self.root.get_child_node("2")
        self.walker.set_focus(child)

        self.assertIs(child, self.walker.focus)
        self.assertEqual([True], modified)

    def test_get_next(self):
        widget, position = self.walker.get_next(self.root)

        self.assertIs(self.root.get_child_node("1"), position)
        self.assertIs(position.get_widget(), widget)

    def test_get_next_at_end(self):
        self.assertEqual((None, None), self.walker.get_next(self.root.get_child_node("3")))

    def test_get_prev(self):
        widget, position = self.walker.get_prev(self.root.get_child_node("2"))

        self.assertIs(self.root.get_child_node("1"), position)
        self.assertIs(position.get_widget(), widget)

    def test_get_prev_at_start(self):
        self.assertEqual((None, None), self.walker.get_prev(self.root))


class TestTreeListBox(unittest.TestCase):
    def setUp(self) -> None:
        self.root = SelfRegisteringParent(
            "root",
            key="/",
            children=(
                SelfRegisteringParent(
                    f"nested_{idx}",
                    key=f"{idx}/",
                    children=(SelfRegisteringChild(f"child_{idx}{cidx}", key=str(cidx)) for cidx in range(1, 3)),
                )
                for idx in range(1, 3)
            ),
        )
        self.widget = urwid.TreeListBox(urwid.TreeWalker(self.root))
        self.size = (21, 7)

    def test_collapse_focus_parent_from_leaf(self):
        self.widget.set_focus(self.root.get_child_node("1/").get_child_node("1"))

        self.widget.keypress(self.size, "-")

        self.assertIs(self.root.get_child_node("1/"), self.widget.focus_position)
        self.assertEqual(
            (
                "- /: root            ",
                "   + 1/: nested_1    ",
                "   - 2/: nested_2    ",
                "      1: child_21    ",
                "      2: child_22    ",
                "                     ",
                "                     ",
            ),
            self.widget.render(self.size).decoded_text,
        )

    def test_collapse_focus_parent_keeps_root(self):
        self.widget.collapse_focus_parent(self.size)

        self.assertIs(self.root, self.widget.focus_position)
        self.assertTrue(self.root.get_widget().expanded)

    def test_left_on_root_keeps_focus(self):
        self.assertIsNone(self.widget.keypress(self.size, "left"))
        self.assertIs(self.root, self.widget.focus_position)

    def test_unhandled_input_passes_other_keys_through(self):
        self.assertEqual("f1", self.widget.unhandled_input(self.size, "f1"))

    def test_focus_end(self):
        self.widget.keypress(self.size, "end")

        self.assertIs(self.root.get_child_node("2/").get_child_node("2"), self.widget.focus_position)

    def test_focus_home(self):
        self.widget.keypress(self.size, "end")
        self.widget.keypress(self.size, "home")

        self.assertIs(self.root, self.widget.focus_position)

    def test_focus_end_without_children(self):
        widget = urwid.TreeListBox(urwid.TreeWalker(SelfRegisteringParent("empty", key="empty")))
        widget.keypress(self.size, "end")

        self.assertEqual("empty", widget.focus_position.get_key())

    def test_move_focus_to_parent_from_offscreen_child(self):
        size = (21, 3)
        self.widget.keypress(size, "end")
        self.assertEqual("2", self.widget.focus_position.get_key())

        self.widget.keypress(size, "left")

        self.assertIs(self.root.get_child_node("2/"), self.widget.focus_position)
