from __future__ import annotations

import typing
import unittest
from typing import Collection

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
        self.assertEqual(
            (
                "- /: root      ",
                "   1: child_1  ",
                "   2: child_2  ",
                "   3: child_3  ",
                "               ",
            ),
            widget.render(size).decoded_text,
        )
        widget.keypress(size, "-")
        self.assertEqual(
            (
                "+ /: root      ",
                "               ",
                "               ",
                "               ",
                "               ",
            ),
            widget.render(size).decoded_text,
        )
        widget.keypress(size, "+")
        self.assertEqual(
            (
                "- /: root      ",
                "   1: child_1  ",
                "   2: child_2  ",
                "   3: child_3  ",
                "               ",
            ),
            widget.render(size).decoded_text,
        )
