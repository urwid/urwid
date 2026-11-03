from __future__ import annotations

import sys
import typing
import unittest
import unittest.mock

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


class ComparisonCountingKey(str):
    """String key counting the equality comparisons made against it."""

    __slots__ = ()
    comparisons = 0

    def __eq__(self, other: object) -> bool:
        """Count the comparison, then compare as a string."""
        ComparisonCountingKey.comparisons += 1
        return super().__eq__(other)

    __hash__ = str.__hash__


class ReloadingParent(urwid.ParentNode):
    """Parent whose child keys change on every reload."""

    def __init__(self, value: str, *, child_count: int) -> None:
        """Create a parent with ``child_count`` changing child keys and one key present in every generation."""
        super().__init__(value, key=value)
        self.child_count = child_count
        self.generation = 0

    def load_child_keys(self) -> list[Hashable]:
        """Return the keys of the next generation."""
        self.generation += 1
        return [*(f"{self.generation}-{idx}" for idx in range(self.child_count)), "kept"]

    def load_child_node(self, key: Hashable) -> TreeNode:
        """Create a leaf node for ``key``."""
        return TreeNode(key, parent=self, key=key)


class CyclicParent(urwid.ParentNode):
    """Parent whose only child is ``self.child``, assigned after construction to close a cycle."""

    def __init__(self, value: str, *, parent: CyclicParent | None = None) -> None:
        """Create the node with no child yet and no ``has_children`` calls counted."""
        super().__init__(value, parent=parent, key=value)
        self.child: CyclicParent | None = None
        self.has_children_calls = 0

    def load_child_keys(self) -> list[Hashable]:
        """Return the key of the only child."""
        return [self.child.get_key()]

    def load_child_node(self, key: Hashable) -> TreeNode:
        """Return the only child."""
        return self.child

    def has_children(self) -> bool:
        """Count the call, failing once a descent has clearly stopped making progress."""
        self.has_children_calls += 1
        if self.has_children_calls > 100:
            raise RuntimeError("cycle guard: the descent did not stop")
        return super().has_children()


class CountingParentLink(urwid.TreeNode):
    """Leaf whose parent link counts its reads, failing once a walk has clearly stopped making progress."""

    def __init__(self, value: str) -> None:
        """Create the node with no reads of its parent link counted."""
        self.parent_reads = 0
        self.link: urwid.TreeNode | None = None
        super().__init__(value, key=value)

    @property
    def _parent(self) -> urwid.TreeNode | None:
        """Return the parent link, counting the read."""
        self.parent_reads += 1
        if self.parent_reads > 100:
            raise RuntimeError("cycle guard: the walk did not stop")
        return self.link

    @_parent.setter
    def _parent(self, value: urwid.TreeNode | None) -> None:
        self.link = value


class FixedDepthParent(SelfRegisteringParent):
    """Parent that reports a fixed depth through an overridden ``get_depth``."""

    def get_depth(self) -> int:
        """Return a depth no parent link implies."""
        return 10


class NoDescendantWidget(urwid.TreeWidget):
    """Widget that reports no last descendant through an overridden ``last_child``."""

    def last_child(self) -> None:
        """Hide the children of this widget from a descent."""


class NoDescendantParent(SelfRegisteringParent):
    """Parent rendered with a :class:`NoDescendantWidget`."""

    def load_widget(self) -> NoDescendantWidget:
        """Create the overriding widget."""
        return NoDescendantWidget(self)


class CollapsedBelowRootWidget(urwid.TreeWidget[typing.Any]):
    """Widget that starts collapsed on every node except the root."""

    def is_initially_expanded(self) -> bool:
        """Expand only the root."""
        depth: int = self.get_node().get_depth()
        return depth == 0


class CollapsedBelowRootParent(SelfRegisteringParent):
    """Parent rendered with a :class:`CollapsedBelowRootWidget`."""

    def load_widget(self) -> CollapsedBelowRootWidget:
        """Create the overriding widget."""
        return CollapsedBelowRootWidget(self)


class StyledParent(SelfRegisteringParent):
    """Parent rendered with the widget class given to :func:`build_styled_tree`."""

    widget_class: type[urwid.TreeWidget[typing.Any]] = urwid.TreeWidget

    def load_widget(self) -> urwid.TreeWidget[typing.Any]:
        """Create the widget of the tree's class."""
        return self.widget_class(self)


class StyledChild(SelfRegisteringChild):
    """Leaf rendered with the widget class given to :func:`build_styled_tree`."""

    widget_class: type[urwid.TreeWidget[typing.Any]] = urwid.TreeWidget

    def load_widget(self) -> urwid.TreeWidget[typing.Any]:
        """Create the widget of the tree's class."""
        return self.widget_class(self)


def build_styled_tree(widget_class: type[urwid.TreeWidget[typing.Any]]) -> StyledParent:
    """Build ``/`` holding ``1/`` (leaves ``1`` and ``2``) and ``2/`` (leaf ``1``), all drawn by *widget_class*."""
    nodes: list[StyledParent | StyledChild] = []

    def styled(node: StyledParent | StyledChild) -> StyledParent | StyledChild:
        nodes.append(node)
        return node

    root = styled(
        StyledParent(
            "root",
            key="/",
            children=(
                styled(
                    StyledParent(
                        "nested_1",
                        key="1/",
                        children=(styled(StyledChild(f"child_1{idx}", key=str(idx))) for idx in (1, 2)),
                    )
                ),
                styled(StyledParent("nested_2", key="2/", children=(styled(StyledChild("child_21", key="1")),))),
            ),
        )
    )
    for node in nodes:
        node.widget_class = widget_class
    return typing.cast("StyledParent", root)


class WideIconWidget(urwid.TreeWidget[typing.Any]):
    """Widget with three-column icons."""

    unexpanded_icon = urwid.SelectableIcon("[+]", 1)
    expanded_icon = urwid.SelectableIcon("[-]", 1)


class LeafIconWidget(urwid.TreeWidget[typing.Any]):
    """Widget giving leaves a blank icon."""

    leaf_icon = urwid.SelectableIcon(urwid.TreeWidget.Symbols.SPACE, 0)


class WideLeafIconWidget(urwid.TreeWidget[typing.Any]):
    """Widget whose leaf icon is wider than the expand and collapse icons."""

    leaf_icon = urwid.Text("( )")


class FlowIconWidget(urwid.TreeWidget[typing.Any]):
    """Widget whose icons have no fixed size."""

    unexpanded_icon = urwid.Divider("+")
    expanded_icon = urwid.Divider("-")


class TextIconEditWidget(urwid.TreeWidget[typing.Any]):
    """Widget with icons that are not selectable beside an editable text, which then has the focus."""

    unexpanded_icon = urwid.Text("+")
    expanded_icon = urwid.Text("-")

    def load_inner_widget(self) -> urwid.Edit:
        """Return an editable text."""
        return urwid.Edit("", "ab")


class OwnLayoutWidget(urwid.TreeWidget[typing.Any]):
    """Widget building its own layout, with the icon first in a plain :class:`urwid.Columns`."""

    def get_indented_widget(self) -> urwid.Padding[urwid.Text | urwid.Columns]:
        """Build the layout without the stock method."""
        widget: urwid.Text | urwid.Columns = self.get_inner_widget()
        if not self.is_leaf:
            icon = [self.unexpanded_icon, self.expanded_icon][self.expanded]
            widget = urwid.Columns([(1, icon), widget], dividechars=1)
        return urwid.Padding(widget, left=self.get_indent_cols())


class SkippedInitWidget(urwid.TreeWidget[typing.Any]):
    """Widget whose ``__init__`` sets the state itself instead of calling :meth:`urwid.TreeWidget.__init__`."""

    def __init__(self, node: urwid.TreeNode[typing.Any]) -> None:  # pylint: disable=super-init-not-called
        """Set the node, the leaf flag and the expanded flag, then build the stock layout."""
        self._node = node
        self._innerwidget = None
        self.is_leaf = not isinstance(node, urwid.ParentNode)
        self.expanded = True
        urwid.WidgetWrap.__init__(self, self.get_indented_widget())  # pylint: disable=non-parent-init-called


class LinesWidget(urwid.TreeWidget[typing.Any]):
    """Widget with connector lines."""

    connector_lines = True


class LinesTipWidget(LinesWidget):
    """Widget with connector lines that end in a tip, with display attributes for both."""

    line_tip = urwid.TreeWidget.Symbols.ARROW_TIP
    line_attr = "line"
    line_tip_attr = "tip"


class LinesLeafIconWidget(LinesWidget):
    """Widget with connector lines and a blank leaf icon."""

    leaf_icon = urwid.SelectableIcon(urwid.TreeWidget.Symbols.SPACE, 0)


class LinesWideIconWidget(WideIconWidget):
    """Widget with connector lines and three-column icons."""

    connector_lines = True


class LinesSkippedInitWidget(SkippedInitWidget):
    """Widget with connector lines whose ``__init__`` does not call :meth:`urwid.TreeWidget.__init__`."""

    connector_lines = True


class LinesOwnLayoutWidget(LinesWidget):
    """Widget placing the lines widget in a layout of its own, with a bracketed text."""

    def get_indented_widget(self) -> urwid.Padding[urwid.Text | urwid.Columns]:
        """Build the layout without the stock method, with the icon of a parent in columns after the lines."""
        widget: urwid.Text | urwid.Columns = urwid.Text(f"[{self.get_display_text()}]")
        if not self.is_leaf:
            icon = [self.unexpanded_icon, self.expanded_icon][self.expanded]
            widget = urwid.Columns([(1, icon), widget], dividechars=1)
        if (lines := self.get_lines_widget()) is not None:
            widget = urwid.Columns([(self.get_indent_cols(), lines), widget], box_columns=(0,))
        return urwid.Padding(widget)


class SpecParent(urwid.ParentNode):
    """Parent whose children are described by *spec*, loaded through :meth:`urwid.ParentNode.get_child_keys`.

    *spec* maps a child key to the spec of a parent child, or to None for a leaf.
    Its key list is one list object, returned by every load, so a test can change it in place.
    """

    widget_class: type[urwid.TreeWidget[typing.Any]] = LinesWidget

    def __init__(
        self,
        value: str,
        spec: dict[str, typing.Any],
        parent: SpecParent | None = None,
        key: Hashable = None,
    ) -> None:
        """Store *spec* and the key list taken from it."""
        super().__init__(value, parent=parent, key=key)
        self.spec = spec
        self.keys = list(spec)

    def load_child_keys(self) -> list[Hashable]:
        """Return the key list itself."""
        return self.keys

    def load_child_node(self, key: Hashable) -> urwid.TreeNode[typing.Any]:
        """Create the child that *spec* describes, with the parent's widget class."""
        if (child_spec := self.spec[key]) is not None:
            child: urwid.TreeNode[typing.Any] = SpecParent(f"node_{key}", child_spec, parent=self, key=key)
        else:
            child = SpecChild(f"leaf_{key}", parent=self, key=key)
        child.widget_class = self.widget_class  # type: ignore[attr-defined]
        return child

    def load_widget(self) -> urwid.TreeWidget[typing.Any]:
        """Create the widget of the tree's class."""
        return self.widget_class(self)


class SpecChild(urwid.TreeNode[typing.Any]):
    """Leaf of a :class:`SpecParent` tree."""

    widget_class: type[urwid.TreeWidget[typing.Any]] = LinesWidget

    def load_widget(self) -> urwid.TreeWidget[typing.Any]:
        """Create the widget of the tree's class."""
        return self.widget_class(self)


def build_chain(depth: int) -> SelfRegisteringParent:
    """Build a single-branch tree ``depth`` levels deep bottom-up, so no node knows its depth yet."""
    node: SelfRegisteringParent | SelfRegisteringChild = SelfRegisteringChild("leaf", key="leaf")
    for level in range(depth, 0, -1):
        node = SelfRegisteringParent(f"level_{level}", key=f"{level}/", children=(node,))
    return node


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

    def test_get_depth_deeper_than_recursion_limit(self):
        """A depth computed bottom-up does not recurse once per level."""
        depth = sys.getrecursionlimit() * 2
        node = build_chain(depth)
        while isinstance(node, urwid.ParentNode):
            node = node.get_last_child()

        self.assertEqual(depth, node.get_depth())
        self.assertEqual(depth - 1, node.get_parent().get_depth())

    def test_get_depth_parent_cycle(self):
        """A cycle in the parent links raises instead of walking it forever."""
        first, second = CountingParentLink("first"), CountingParentLink("second")
        first._parent, second._parent = second, first

        with self.assertRaises(urwid.TreeWidgetError):
            first.get_depth()

    def test_get_depth_uses_overriding_ancestor(self):
        """The walk asks an ancestor that overrides get_depth for its depth."""
        parent = FixedDepthParent("parent", key="parent")
        child = SelfRegisteringChild("child", parent=parent, key="child")

        self.assertEqual(11, child.get_depth())

    def test_get_child_index_does_not_scan_keys(self):
        """Walking all siblings looks each key up instead of scanning the key list."""
        count = 2000
        root = SelfRegisteringParent(
            "root",
            key="/",
            children=(SelfRegisteringChild(f"child_{idx}", key=ComparisonCountingKey(idx)) for idx in range(count)),
        )
        ComparisonCountingKey.comparisons = 0
        node = root.get_first_child()
        visited = 1
        while (node := node.next_sibling()) is not None:
            visited += 1

        self.assertEqual(count, visited)
        # Scanning the key list for each sibling makes about count**2 / 2 comparisons.
        self.assertLess(ComparisonCountingKey.comparisons, count * 4)

    def test_get_child_index_after_reload(self):
        """Indexes follow the reloaded key list."""
        parent = ReloadingParent("parent", child_count=3)

        self.assertEqual(1, parent.get_child_index("1-1"))
        parent.get_child_keys(reload=True)
        self.assertEqual(2, parent.get_child_index("2-2"))
        self.assertEqual(3, parent.get_child_index("kept"))
        with self.assertRaises(urwid.TreeWidgetError):
            parent.get_child_index("1-1")

    def test_reload_drops_nodes_of_removed_keys(self):
        """A reload keeps only the cached nodes whose keys are still listed."""
        parent = ReloadingParent("parent", child_count=100)
        kept = parent.get_child_node("kept")
        for _ in range(50):
            for key in parent.get_child_keys(reload=True):
                parent.get_child_node(key)

        self.assertEqual(set(parent.get_child_keys()), set(parent._children))
        self.assertIs(kept, parent.get_child_node("kept"))

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
        self.assertIsNone(widget.leaf_icon)
        self.assertEqual(("      1: child_11   ",), widget.render((20,)).decoded_text)

    def test_leaf_ignores_input(self):
        """A leaf, with or without a leaf icon, passes keys on and ignores clicks."""
        for widget_class in (urwid.TreeWidget, LeafIconWidget):
            with self.subTest(widget_class=widget_class.__name__):
                widget = build_styled_tree(widget_class).get_child_node("1/").get_child_node("1").get_widget()

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

    def test_expand_collapse_and_toggle(self) -> None:
        """Each state change updates both the flag and the icon."""
        widget = self.root.get_child_node("1/").get_widget()
        cases = (
            (widget.collapse, False, "+"),
            (widget.expand, True, "-"),
            (widget.toggle_expanded, False, "+"),
            (widget.toggle_expanded, True, "-"),
        )
        for change, expanded, icon in cases:
            with self.subTest(change=change.__name__, expanded=expanded):
                change()

                self.assertEqual(expanded, widget.expanded)
                self.assertEqual((f"   {icon} 1/: nested_1   ",), widget.render((20,)).decoded_text)

    def test_expand_collapse_and_toggle_ignore_leaf(self) -> None:
        """A leaf keeps its state and its text, as it does for the expand and collapse keys."""
        for widget_class, text in (
            (urwid.TreeWidget, "      1: child_11   "),
            (LeafIconWidget, "        1: child_11 "),
        ):
            widget = build_styled_tree(widget_class).get_child_node("1/").get_child_node("1").get_widget()
            for change in (widget.collapse, widget.expand, widget.toggle_expanded):
                with self.subTest(widget_class=widget_class.__name__, change=change.__name__):
                    change()

                    self.assertTrue(widget.expanded)
                    self.assertEqual((text,), widget.render((20,)).decoded_text)

    def test_is_initially_expanded_override(self) -> None:
        """A subclass decides the starting state of each node."""
        root = CollapsedBelowRootParent(
            "root",
            key="/",
            children=(
                CollapsedBelowRootParent("nested", key="1/", children=(SelfRegisteringChild("child", key="1"),)),
            ),
        )
        size = (20, 3)

        self.assertTrue(root.get_widget().expanded)
        self.assertFalse(root.get_child_node("1/").get_widget().expanded)
        self.assertEqual(
            (
                "- /: root           ",
                "   + 1/: nested     ",
                "                    ",
            ),
            urwid.TreeListBox(urwid.TreeWalker(root)).render(size).decoded_text,
        )

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


class TestTreeWidgetIcons(unittest.TestCase):
    """Icon symbols, icons wider than one column, and where a click on the icon lands."""

    def test_symbols(self) -> None:
        """The symbols are reachable from the widget class, and the default icons use them."""
        self.assertIs(urwid.widget.treetools.TreeSymbols, urwid.TreeWidget.Symbols)
        self.assertEqual("+", urwid.TreeWidget.unexpanded_icon.text)
        self.assertEqual("-", urwid.TreeWidget.expanded_icon.text)

    def test_default_layout_renders_as_plain_columns(self) -> None:
        """The stock icon columns draw a one-column icon exactly as :class:`urwid.Columns` does, at every width."""
        widget = build_styled_tree(urwid.TreeWidget).get_child_node("1/").get_widget()
        plain = urwid.Padding(
            urwid.Columns([(1, urwid.TreeWidget.expanded_icon), urwid.Text("1/: nested_1")], dividechars=1),
            left=3,
        )
        for maxcol in range(1, 10):
            with self.subTest(maxcol=maxcol):
                self.assertEqual(
                    plain.render((maxcol,), focus=True).decoded_text,
                    widget.render((maxcol,), focus=True).decoded_text,
                )
                self.assertEqual(plain.rows((maxcol,), True), widget.rows((maxcol,), True))
                self.assertEqual(plain.get_cursor_coords((maxcol,)), widget.get_cursor_coords((maxcol,)))

    def test_icon_columns_width_policy(self) -> None:
        """The text is dropped before the icon, and the icon only when it does not fit on its own."""
        columns = urwid.widget.treetools._IconColumns(  # pylint: disable=protected-access
            [(3, urwid.SelectableIcon("[+]", 1)), urwid.Text("text")],
            dividechars=1,
        )
        cases = ((1, [0, 1]), (2, [0, 2]), (3, [3, 0]), (4, [3, 0]), (5, [3, 1]), (8, [3, 4]))
        for maxcol, widths in cases:
            with self.subTest(maxcol=maxcol):
                self.assertEqual(widths, columns.column_widths((maxcol,)))

    def test_wide_icon(self) -> None:
        """A three-column icon shifts the text, and a click on any of its columns toggles."""
        widget = build_styled_tree(WideIconWidget).get_child_node("1/").get_widget()

        self.assertEqual(("   [-] 1/: nested_1 ",), widget.render((20,)).decoded_text)
        widget.collapse()
        self.assertEqual(("   [+] 1/: nested_1 ",), widget.render((20,)).decoded_text)
        for col in (3, 4, 5):
            with self.subTest(col=col):
                self.assertTrue(widget.mouse_event((20,), "mouse press", 1, col, 0, True))
        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 6, 0, True))
        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 2, 0, True))
        self.assertTrue(widget.expanded)

    def test_wide_icon_on_narrow_row(self) -> None:
        """A row narrower than the icon shows the text, and a click there is not on the icon."""
        widget = build_styled_tree(WideIconWidget).get_child_node("1/").get_widget()

        self.assertEqual(("   [-]",), widget.render((6,)).decoded_text)
        self.assertEqual(("   [-] ",), widget.render((7,)).decoded_text)
        self.assertEqual(tuple(f"   {char}" for char in "1/:nested_1"), widget.render((4,)).decoded_text)
        self.assertFalse(widget.mouse_event((4,), "mouse press", 1, 3, 0, True))
        self.assertTrue(widget.mouse_event((6,), "mouse press", 1, 5, 0, True))
        self.assertFalse(widget.expanded)

    def test_icons_without_fixed_size(self) -> None:
        """Icons that cannot be packed to a fixed size get a one-column icon column."""
        widget = build_styled_tree(FlowIconWidget).get_child_node("1/").get_widget()

        self.assertEqual(("   - 1/: nested_1   ",), widget.render((20,)).decoded_text)
        widget.collapse()
        self.assertEqual(("   + 1/: nested_1   ",), widget.render((20,)).decoded_text)

    def test_text_in_focus_on_narrow_row(self) -> None:
        """A focused text beside icons that are not selectable keeps the row, the cursor and the keys."""
        widget = build_styled_tree(TextIconEditWidget).get_child_node("1/").get_widget()

        self.assertEqual(("   ab",), widget.render((5,), focus=True).decoded_text)
        self.assertEqual((4, 0), widget.get_cursor_coords((5,)))
        self.assertIsNone(widget.keypress((5,), "z"))

    def test_mouse_on_decorated_layout(self) -> None:
        """A click toggles after the layout is wrapped in an :class:`urwid.AttrMap`, as ``examples/browse.py`` does."""
        widget = build_styled_tree(urwid.TreeWidget).get_child_node("1/").get_widget()
        widget._w = urwid.AttrMap(widget._w, None, "focus")  # pylint: disable=protected-access

        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertFalse(widget.expanded)
        self.assertEqual(("   + 1/: nested_1   ",), widget.render((20,)).decoded_text)

    def test_own_layout(self) -> None:
        """A layout built without the stock method keeps the one-column icon right after the indent."""
        widget = build_styled_tree(OwnLayoutWidget).get_child_node("1/").get_widget()

        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 4, 0, True))
        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertFalse(widget.expanded)
        self.assertEqual(("   + 1/: nested_1   ",), widget.render((20,)).decoded_text)

    def test_skipped_init(self) -> None:
        """A widget that sets its state itself and calls the stock layout method renders and toggles."""
        widget = build_styled_tree(SkippedInitWidget).get_child_node("1/").get_widget()

        self.assertEqual(("   - 1/: nested_1   ",), widget.render((20,)).decoded_text)
        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertEqual(("   + 1/: nested_1   ",), widget.render((20,)).decoded_text)


class TestTreeWidgetLeafIcon(unittest.TestCase):
    """An icon column for leaves, so their text lines up with the text of a parent."""

    def test_leaf_text_lines_up_with_parent_text(self) -> None:
        """A leaf and a parent at the same depth start their text in the same column."""
        root = StyledParent(
            "root",
            key="/",
            children=(
                StyledParent("nested", key="1/", children=(StyledChild("child", key="1"),)),
                StyledChild("leaf", key="2"),
            ),
        )
        for node in (root, root.get_child_node("1/"), root.get_child_node("1/").get_child_node("1")):
            node.widget_class = LeafIconWidget
        root.get_child_node("2").widget_class = LeafIconWidget

        self.assertEqual(
            (
                "- /: root        ",
                "   - 1/: nested  ",
                "        1: child ",
                "     2: leaf     ",
            ),
            urwid.TreeListBox(urwid.TreeWalker(root)).render((17, 4)).decoded_text,
        )

    def test_leaf_layout_renders_as_plain_columns(self) -> None:
        """A one-column leaf icon draws as :class:`urwid.Columns` would draw it, at every width."""
        widget = build_styled_tree(LeafIconWidget).get_child_node("1/").get_child_node("1").get_widget()
        plain = urwid.Padding(
            urwid.Columns([(1, LeafIconWidget.leaf_icon), urwid.Text("1: child_11")], dividechars=1),
            left=6,
        )
        for maxcol in range(1, 12):
            with self.subTest(maxcol=maxcol):
                self.assertEqual(
                    plain.render((maxcol,), focus=True).decoded_text,
                    widget.render((maxcol,), focus=True).decoded_text,
                )
                self.assertEqual(plain.rows((maxcol,), True), widget.rows((maxcol,), True))
                self.assertEqual(plain.get_cursor_coords((maxcol,)), widget.get_cursor_coords((maxcol,)))

    def test_leaf_icon_widens_icon_column(self) -> None:
        """A leaf icon wider than the other icons widens the icon column of every node."""
        root = build_styled_tree(WideLeafIconWidget)

        self.assertEqual(("   -   1/: nested_1  ",), root.get_child_node("1/").get_widget().render((21,)).decoded_text)
        self.assertEqual(
            ("      ( ) 1: child_11",),
            root.get_child_node("1/").get_child_node("1").get_widget().render((21,)).decoded_text,
        )

    def test_leaf_icon_is_decoration(self) -> None:
        """A leaf with an icon is not selectable, and updating the icon keeps the leaf icon."""
        widget = build_styled_tree(LeafIconWidget).get_child_node("1/").get_child_node("1").get_widget()
        widget.update_expanded_icon()

        self.assertFalse(widget.selectable())
        self.assertEqual(("        1: child_11 ",), widget.render((20,)).decoded_text)

    def test_wide_leaf_icon_on_narrow_row(self) -> None:
        """A row with room for the leaf icon alone shows the icon, and a row with less room shows the text."""
        widget = build_styled_tree(WideLeafIconWidget).get_child_node("1/").get_child_node("1").get_widget()

        self.assertEqual(("      ( )",), widget.render((9,)).decoded_text)
        self.assertEqual(("      1:", "      ch", "      il", "      d_", "      11"), widget.render((8,)).decoded_text)


class TestTreeWidgetLines(unittest.TestCase):
    """Connector lines in the indentation, drawn with the glyphs and attributes of the widget class."""

    def test_lines(self) -> None:
        """A tee joins a node with a next sibling, a corner the last child, and a bar passes a sibling below."""
        listbox = urwid.TreeListBox(urwid.TreeWalker(build_styled_tree(LinesWidget)))

        self.assertEqual(
            (
                "- /: root           ",
                "├──- 1/: nested_1   ",
                "│  ├──1: child_11   ",
                "│  └──2: child_12   ",
                "└──- 2/: nested_2   ",
                "   └──1: child_21   ",
            ),
            listbox.render((20, 6)).decoded_text,
        )

    def test_indent_cols(self) -> None:
        """The connector fills its level of the indentation, and an indentation of 0 has no lines."""
        cases = (
            (1, ("- /: root   ", "├- 1/: neste", "│├1: child_1", "│└2: child_1", "└- 2/: neste", " └1: child_2")),
            (2, ("- /: root   ", "├─- 1/: nest", "│ ├─1: child", "│ └─2: child", "└─- 2/: nest", "  └─1: child")),
            (0, ("- /: root   ", "- 1/: nested", "1: child_11 ", "2: child_12 ", "- 2/: nested", "1: child_21 ")),
        )
        for indent_cols, rows in cases:
            with self.subTest(indent_cols=indent_cols):
                widget_class = type("IndentWidget", (LinesWidget,), {"indent_cols": indent_cols})
                listbox = urwid.TreeListBox(urwid.TreeWalker(build_styled_tree(widget_class)))
                self.assertEqual(
                    rows,
                    tuple(row[:12] for row in listbox.render((20, 6)).decoded_text),
                )

    def test_leaf_icon(self) -> None:
        """The connector of a leaf ends at its icon."""
        listbox = urwid.TreeListBox(urwid.TreeWalker(build_styled_tree(LinesLeafIconWidget)))

        self.assertEqual(
            ("│  ├──  1: child_11 ", "│  └──  2: child_12 "),
            listbox.render((20, 6)).decoded_text[2:4],
        )

    def test_tip_and_attributes(self) -> None:
        """The tip ends the connector, with its own display attribute."""
        widget = build_styled_tree(LinesTipWidget).get_child_node("1/").get_widget()
        canvas = widget.render((20,))

        self.assertEqual(("├─➤- 1/: nested_1   ",), canvas.decoded_text)
        self.assertEqual(
            [("line", "├─"), ("tip", "➤")],
            [(attr, text.decode()) for attr, _cs, text in next(iter(canvas.content()))[:2]],
        )

    def test_rows_below_the_first(self) -> None:
        """A node drawn on several rows continues the bars of its level, and of the levels above it."""
        root = build_styled_tree(LinesWidget)

        self.assertEqual(
            ("├──- 1/:", "│    nes", "│    ted", "│    _1 "),
            root.get_child_node("1/").get_widget().render((8,)).decoded_text,
        )
        self.assertEqual(
            ("   └──1:", "      ch"),
            root.get_child_node("2/").get_child_node("1").get_widget().render((8,)).decoded_text[:2],
        )

    def test_wide_glyph_raises(self) -> None:
        """A glyph wider than one column raises, naming the attribute."""
        for name in ("line_vertical", "line_tee", "line_corner", "line_horizontal", "line_tip"):
            with self.subTest(name=name):
                widget_class = type("WideGlyphWidget", (LinesWidget,), {name: "\N{CJK UNIFIED IDEOGRAPH-4E00}"})
                with self.assertRaisesRegex(urwid.widget.treetools.TreeWidgetError, name):
                    build_styled_tree(widget_class).get_child_node("1/").get_widget()

    def test_toggle_keeps_lines(self) -> None:
        """Keys and a click on every cell of a wide icon switch the icon and leave the lines as they are."""
        widget = build_styled_tree(LinesWideIconWidget).get_child_node("1/").get_widget()

        self.assertIsNone(widget.keypress((20,), "-"))
        self.assertEqual(("├──[+] 1/: nested_1 ",), widget.render((20,)).decoded_text)
        self.assertIsNone(widget.keypress((20,), "+"))
        self.assertEqual(("├──[-] 1/: nested_1 ",), widget.render((20,)).decoded_text)
        for col, icon in ((3, "+"), (4, "-"), (5, "+")):
            with self.subTest(col=col):
                self.assertTrue(widget.mouse_event((20,), "mouse press", 1, col, 0, True))
                self.assertEqual((f"├──[{icon}] 1/: nested_1 ",), widget.render((20,)).decoded_text)
        self.assertFalse(widget.mouse_event((20,), "mouse press", 1, 0, 0, True))

    def test_narrow_row(self) -> None:
        """A row without room for the indentation and one more column drops the lines, and the icon moves left."""
        widget = build_styled_tree(LinesWideIconWidget).get_child_node("1/").get_widget()

        self.assertEqual(("├──[-]",), widget.render((6,)).decoded_text)
        self.assertEqual(("├──1/", "│  : ", "│  ne"), widget.render((5,)).decoded_text[:3])
        self.assertEqual(("[-]",), widget.render((3,)).decoded_text)
        self.assertFalse(widget.mouse_event((5,), "mouse press", 1, 3, 0, True))
        self.assertTrue(widget.mouse_event((3,), "mouse press", 1, 0, 0, True))
        self.assertEqual(("[+]",), widget.render((3,)).decoded_text)

        leaf = build_styled_tree(LinesLeafIconWidget).get_child_node("1/").get_child_node("1").get_widget()
        self.assertEqual(("  1: c", "  hild", "  _11 "), leaf.render((6,)).decoded_text)

    def test_non_utf8_terminal(self) -> None:
        """The light glyphs are drawn with DEC special graphics, the others with the ASCII fallbacks or ``?``."""
        heavy = type("HeavyWidget", (LinesWidget,), {"line_tee": urwid.TreeWidget.Symbols.HEAVY_TEE})
        old_fallbacks = urwid.get_ascii_fallbacks()
        self.addCleanup(urwid.set_ascii_fallbacks, old_fallbacks)
        rows = {}
        with urwid.util.set_temporary_encoding("ascii"):
            for label, widget_class in (("light", LinesWidget), ("heavy", heavy), ("fallback", heavy)):
                if label == "fallback":
                    urwid.set_ascii_fallbacks({urwid.TreeWidget.Symbols.HEAVY_TEE: "+"})
                canvas = build_styled_tree(widget_class).get_child_node("1/").get_widget().render((20,))
                rows[label] = [(cs, text) for _attr, cs, text in next(iter(canvas.content()))[:2]]

        self.assertEqual([("0", b"tqq"), (None, b"-")], rows["light"])
        self.assertEqual([(None, b"?"), ("0", b"qq")], rows["heavy"])
        self.assertEqual([(None, b"+"), ("0", b"qq")], rows["fallback"])

    def test_reload_redraws_lines(self) -> None:
        """A change of the last child redraws the lines of the old and the new last child, under a kept canvas."""

        def append_in_place(root: SpecParent) -> None:
            root.spec["c"] = None
            root.keys.append("c")
            root.get_child_keys(reload=True)

        def pop_in_place(root: SpecParent) -> None:
            root.keys.pop()
            root.get_child_keys(reload=True)

        def append_and_clear(root: SpecParent) -> None:
            root.spec["c"] = None
            root.keys.append("c")
            root._child_keys = None  # pylint: disable=protected-access
            root.get_child_keys()

        cases = (
            (append_in_place, ("├──- a: node_a  ", "│  ├──x: leaf_x ", "│  └──y: leaf_y ", "├──b: leaf_b    ")),
            (pop_in_place, ("└──- a: node_a  ", "   ├──x: leaf_x ", "   └──y: leaf_y ", "                ")),
            (append_and_clear, ("├──- a: node_a  ", "│  ├──x: leaf_x ", "│  └──y: leaf_y ", "├──b: leaf_b    ")),
        )
        for change, rows in cases:
            with self.subTest(change=change.__name__):
                root = SpecParent("root", {"a": {"x": None, "y": None}, "b": None}, key="/")
                listbox = urwid.TreeListBox(urwid.TreeWalker(root))
                kept = listbox.render((16, 5))
                change(root)

                self.assertEqual("└──b: leaf_b    ", kept.decoded_text[4])
                self.assertEqual(rows, listbox.render((16, 5)).decoded_text[1:])

    def test_default_does_no_walk(self) -> None:
        """Without connector lines, a reload looks at no child for lines to redraw."""
        root = SpecParent("root", {"a": {"x": None}, "b": None}, key="/")
        root.widget_class = urwid.TreeWidget
        urwid.TreeListBox(urwid.TreeWalker(root)).render((16, 4))
        with unittest.mock.patch.object(urwid.ParentNode, "_invalidate_lines") as invalidate:
            root.spec["c"] = None
            root.keys.append("c")
            root.get_child_keys(reload=True)

        invalidate.assert_not_called()

    def test_get_lines_widget(self) -> None:
        """The lines widget is created once, and a layout of a subclass's own places it and sees it redrawn."""
        root = SpecParent("root", {"a": None, "b": None}, key="/")
        root.widget_class = LinesOwnLayoutWidget
        listbox = urwid.TreeListBox(urwid.TreeWalker(root))
        widget = root.get_child_node("a").get_widget()
        kept = listbox.render((16, 3))

        self.assertIs(widget.get_lines_widget(), widget.get_lines_widget())
        self.assertIsNone(root.get_widget().get_lines_widget())
        self.assertIsNone(build_styled_tree(urwid.TreeWidget).get_child_node("1/").get_widget().get_lines_widget())
        self.assertEqual(("- [/: root]     ", "├──[a: leaf_a]  ", "└──[b: leaf_b]  "), kept.decoded_text)
        root.keys.pop()
        root.get_child_keys(reload=True)
        self.assertEqual("└──[a: leaf_a]  ", listbox.render((16, 3)).decoded_text[1])

        parent = build_styled_tree(LinesOwnLayoutWidget).get_child_node("1/").get_widget()
        parent.collapse()
        self.assertEqual(("├──+ [1/: nested_1]   ",), parent.render((22,)).decoded_text)

    def test_skipped_init(self) -> None:
        """A widget that sets its state itself and calls the stock layout method draws lines and toggles."""
        root = build_styled_tree(LinesSkippedInitWidget)
        widget = root.get_child_node("1/").get_widget()

        self.assertEqual(("├──- 1/: nested_1   ",), widget.render((20,)).decoded_text)
        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertEqual(("├──+ 1/: nested_1   ",), widget.render((20,)).decoded_text)
        self.assertEqual(
            ("│  └──2: child_12   ",),
            root.get_child_node("1/").get_child_node("2").get_widget().render((20,)).decoded_text,
        )

    def test_decorated_layout_mouse(self) -> None:
        """A click toggles after the layout is wrapped in an :class:`urwid.AttrMap`, as ``examples/browse.py`` does."""
        widget = build_styled_tree(LinesWidget).get_child_node("1/").get_widget()
        widget._w = urwid.AttrMap(widget._w, None, "focus")

        self.assertTrue(widget.mouse_event((20,), "mouse press", 1, 3, 0, True))
        self.assertEqual(("├──+ 1/: nested_1   ",), widget.render((20,)).decoded_text)


class TestLastChild(unittest.TestCase):
    """Descent to the last visible descendant."""

    def test_cycle(self):
        """A node that is its own descendant raises instead of descending forever."""
        first = CyclicParent("first")
        second = CyclicParent("second", parent=first)
        first.child, second.child = second, first

        with self.assertRaises(urwid.TreeWidgetError):
            first.get_widget().last_child()

    def test_overriding_descendant_widget(self):
        """A descendant widget that overrides last_child decides its own last descendant."""
        hiding = NoDescendantParent("hiding", key="h/", children=(SelfRegisteringChild("hidden", key="x"),))
        root = SelfRegisteringParent("root", key="/", children=(hiding,))

        self.assertIs(hiding.get_widget(), root.get_widget().last_child())


class TestDeepTree(unittest.TestCase):
    """A subtree deeper than the recursion limit, built bottom-up."""

    def setUp(self) -> None:
        """Put the deep subtree before a leaf under the root."""
        self.depth = sys.getrecursionlimit() * 2
        self.deep = build_chain(self.depth)
        self.root = SelfRegisteringParent("root", key="/", children=(self.deep, SelfRegisteringChild("tail", key="t")))
        self.widget = urwid.TreeListBox(urwid.TreeWalker(self.root))
        self.size = (20, 3)

    def test_last_child_deeper_than_recursion_limit(self):
        """The last descendant is found without recursing once per level."""
        last = self.deep.get_widget().last_child()

        self.assertEqual("leaf", last.get_node().get_key())
        self.assertEqual(self.depth + 1, last.get_node().get_depth())

    def test_render_below_deep_subtree(self):
        """Rendering with the deep subtree above the focus fills the rows above it."""
        tail = self.root.get_child_node("t")
        self.widget.change_focus(self.size, tail, 2)
        self.widget.render(self.size, focus=True)

        self.assertIs(tail, self.widget.focus_position)
        self.assertEqual("leaf", self.widget.body.get_prev(tail)[1].get_key())

    def test_focus_end_inside_deep_subtree(self):
        """The End key moves the focus to the deepest last node."""
        deep = build_chain(self.depth)
        root = SelfRegisteringParent("root", key="/", children=(SelfRegisteringChild("head", key="h"), deep))
        widget = urwid.TreeListBox(urwid.TreeWalker(root))
        widget.keypress(self.size, "end")

        self.assertEqual("leaf", widget.focus_position.get_key())


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
        # the last node is placed on the bottom row before the next render, not on a row counted from the width
        self.assertEqual((self.size[1] - 1, 0), self.widget.get_focus_offset_inset(self.size))

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

    def test_navigation_to_offscreen_parent_above_nested_siblings(self):
        for key in ("left", "-"):
            with self.subTest(key=key):
                inner = SelfRegisteringParent(
                    "inner", key="inner", children=(SelfRegisteringChild(str(idx), key=str(idx)) for idx in range(2))
                )
                target = SelfRegisteringChild("target", key="target")
                outer = SelfRegisteringParent("outer", key="outer", children=(inner, target))
                root = SelfRegisteringParent("root", key="root", children=(outer,))
                widget = urwid.TreeListBox(urwid.TreeWalker(root))
                size = (30, 3)
                widget.change_focus(size, target, offset_inset=2, snap_rows=0)
                widget.render(size)
                visible = widget.calculate_visible(size)
                self.assertEqual(
                    [inner.get_child_node("1"), inner.get_child_node("0")],
                    [node for _widget, node, _rows in visible.top.fill],
                )

                widget.keypress(size, key)

                self.assertIs(outer, widget.focus_position)
                self.assertEqual(key == "left", outer.get_widget().expanded)
                self.assertTrue(inner.get_widget().expanded)

    def test_positions(self) -> None:
        """Positions follow the display order and skip the children of a collapsed node."""
        self.root.get_child_node("1/").get_widget().collapse()
        nested_2 = typing.cast("SelfRegisteringParent", self.root.get_child_node("2/"))
        expected = [
            self.root,
            self.root.get_child_node("1/"),
            nested_2,
            nested_2.get_child_node("1"),
            nested_2.get_child_node("2"),
        ]

        walker = urwid.TreeWalker(nested_2)
        self.assertEqual(expected, list(walker.positions()))
        self.assertEqual(expected[::-1], list(walker.positions(reverse=True)))
        with self.assertRaises(TypeError):
            walker.positions(True)  # type: ignore[call-arg]  # pylint: disable=too-many-function-args

    def test_positions_of_collapsed_root(self) -> None:
        """A collapsed root is the only visible node, whatever node is in focus."""
        self.root.get_widget().collapse()
        walker = urwid.TreeWalker(self.root.get_child_node("2/"))

        self.assertEqual([self.root], list(walker.positions()))
        self.assertEqual([self.root], list(walker.positions(reverse=True)))

    def test_plain_listbox_home_and_end(self) -> None:
        """A plain ListBox over a TreeWalker moves to the first and last visible node."""
        listbox = urwid.ListBox(urwid.TreeWalker(self.root))

        listbox.keypress(self.size, "end")
        self.assertIs(self.root.get_child_node("2/").get_child_node("2"), listbox.focus_position)

        listbox.keypress(self.size, "home")
        self.assertIs(self.root, listbox.focus_position)

    def test_iteration_follows_display_order_from_any_focus(self) -> None:
        """Iterating the ListBox starts at the root whatever node is in focus."""
        self.widget.set_focus(self.root.get_child_node("2/"))
        expected = ["/", "1/", "1", "2", "2/", "1", "2"]

        self.assertEqual(expected, [node.get_key() for node in self.widget])
        self.assertEqual(expected[::-1], [node.get_key() for node in reversed(self.widget)])

    def test_focus_tree_navigation(self) -> None:
        """Each focus method moves to its target, or keeps the focus when there is none."""
        nested_1 = typing.cast("SelfRegisteringParent", self.root.get_child_node("1/"))
        nested_2 = typing.cast("SelfRegisteringParent", self.root.get_child_node("2/"))
        cases = (
            ("focus_first_child", self.root, nested_1),
            ("focus_last_child", self.root, nested_2),
            ("focus_next_sibling", nested_1, nested_2),
            ("focus_prev_sibling", nested_2, nested_1),
            ("focus_first_child", nested_1.get_child_node("1"), nested_1.get_child_node("1")),
            ("focus_last_child", nested_2.get_child_node("2"), nested_2.get_child_node("2")),
            ("focus_next_sibling", nested_2, nested_2),
            ("focus_next_sibling", self.root, self.root),
            ("focus_prev_sibling", nested_1, nested_1),
            ("focus_prev_sibling", self.root, self.root),
        )
        for method, start, expected in cases:
            with self.subTest(method=method, start=start.get_value()):
                self.widget.set_focus(start)
                self.widget.render(self.size)

                getattr(self.widget, method)()

                self.assertIs(expected, self.widget.focus_position)

    def test_focus_child_of_collapsed_node_keeps_focus(self) -> None:
        """The hidden children of a collapsed node cannot take the focus."""
        nested_1 = self.root.get_child_node("1/")
        nested_1.get_widget().collapse()
        for method in ("focus_first_child", "focus_last_child"):
            with self.subTest(method=method):
                self.widget.set_focus(nested_1)

                getattr(self.widget, method)()

                self.assertIs(nested_1, self.widget.focus_position)

    def test_focus_prev_sibling_keeps_visible_target_on_its_row(self) -> None:
        """A visible target is focused where it is drawn, without scrolling."""
        self.widget.set_focus(self.root.get_child_node("2/"))
        self.widget.render(self.size)

        self.widget.focus_prev_sibling()
        self.widget.render(self.size)

        self.assertIs(self.root.get_child_node("1/"), self.widget.focus_position)
        self.assertEqual((1, 0), self.widget.get_focus_offset_inset(self.size))

    def test_focus_last_child_scrolls_offscreen_target_into_view(self) -> None:
        """A target below the view is scrolled up to the bottom row."""
        size = (21, 3)
        self.widget.render(size)

        self.widget.focus_last_child()

        self.assertEqual(
            (
                "      1: child_11    ",
                "      2: child_12    ",
                "   - 2/: nested_2    ",
            ),
            self.widget.render(size).decoded_text,
        )
