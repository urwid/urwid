from __future__ import annotations

import typing
import unittest

import urwid
from urwid import TreeNode

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Hashable, Iterable


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

    def load_child_keys(self) -> Collection[Hashable]:
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
