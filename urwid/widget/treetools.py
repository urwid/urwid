# Generic TreeWidget/TreeWalker class
#    Copyright (c) 2010  Rob Lanphier
#    Copyright (C) 2004-2010  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/


"""
Urwid tree view

Features:
- custom selectable widgets for trees
- custom list walker for displaying widgets in a tree fashion
"""


from __future__ import annotations

import typing

from .columns import Columns
from .constants import WHSettings
from .listbox import ListBox, ListWalker
from .padding import Padding
from .text import Text
from .widget import WidgetWrap
from .wimp import SelectableIcon

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Sequence

__all__ = ("ParentNode", "TreeListBox", "TreeNode", "TreeWalker", "TreeWidget", "TreeWidgetError")


class TreeWidgetError(RuntimeError):
    pass


class TreeWidget(WidgetWrap[Padding[typing.Union[Text, Columns]]]):
    """A widget representing something in a nested tree display."""

    indent_cols = 3
    unexpanded_icon = SelectableIcon("+", 0)
    expanded_icon = SelectableIcon("-", 0)

    def __init__(self, node: TreeNode) -> None:
        self._node = node
        self._innerwidget: Text | None = None
        self.is_leaf = not hasattr(node, "get_first_child")
        self.expanded = True
        widget = self.get_indented_widget()
        super().__init__(widget)

    def selectable(self) -> bool:
        """
        Allow selection of non-leaf nodes so children may be (un)expanded
        """
        return not self.is_leaf

    def get_indented_widget(self) -> Padding[Text | Columns]:
        widget = self.get_inner_widget()
        if not self.is_leaf:
            widget = Columns(
                [(1, [self.unexpanded_icon, self.expanded_icon][self.expanded]), widget],
                dividechars=1,
            )
        indent_cols = self.get_indent_cols()
        return Padding(widget, width=(WHSettings.RELATIVE, 100), left=indent_cols)

    def update_expanded_icon(self) -> None:
        """Update display widget text for parent widgets"""
        # icon is first element in columns indented widget
        icon = [self.unexpanded_icon, self.expanded_icon][self.expanded]
        self._w.base_widget.contents[0] = (icon, (WHSettings.GIVEN, 1, False))

    def get_indent_cols(self) -> int:
        return self.indent_cols * self.get_node().get_depth()

    def get_inner_widget(self) -> Text:
        if self._innerwidget is None:
            self._innerwidget = self.load_inner_widget()
        return self._innerwidget

    def load_inner_widget(self) -> Text:
        return Text(self.get_display_text())

    def get_node(self) -> TreeNode:
        return self._node

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        return f"{self.get_node().get_key()}: {self.get_node().get_value()!s}"

    def next_inorder(self) -> TreeWidget | None:
        """Return the next TreeWidget depth first from this one."""
        # first check if there's a child widget
        first_child = self.first_child()
        if first_child is not None:
            return first_child

        # now we need to hunt for the next sibling
        this_node = self.get_node()
        next_node = this_node.next_sibling()
        depth = this_node.get_depth()
        while next_node is None and depth > 0:
            # keep going up the tree until we find an ancestor next sibling
            this_node = this_node.get_parent()
            next_node = this_node.next_sibling()
            depth -= 1
            if depth != this_node.get_depth():
                raise ValueError(depth)
        if next_node is None:
            # we're at the end of the tree
            return None

        return next_node.get_widget()

    def prev_inorder(self) -> TreeWidget | None:
        """Return the previous TreeWidget depth first from this one."""
        this_node = self._node
        prev_node = this_node.prev_sibling()
        if prev_node is not None:
            # we need to find the last child of the previous widget if its
            # expanded
            prev_widget = prev_node.get_widget()
            last_child = prev_widget.last_child()
            if last_child is None:
                return prev_widget

            return last_child

        # need to hunt for the parent
        depth = this_node.get_depth()
        if prev_node is None and depth == 0:
            return None
        if prev_node is None:
            prev_node = this_node.get_parent()
        return prev_node.get_widget()

    def keypress(
        self,
        size: tuple[int] | tuple[()],
        key: str,
    ) -> str | None:
        """Handle expand & collapse requests (non-leaf nodes)"""
        if self.is_leaf:
            return key

        if key in {"+", "right"}:
            self.expanded = True
            self.update_expanded_icon()
            return None
        if key == "-":
            self.expanded = False
            self.update_expanded_icon()
            return None
        if self._w.selectable():
            return super().keypress(size, key)

        return key

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        if self.is_leaf or event != "mouse press" or button != 1:
            return False

        if row == 0 and col == self.get_indent_cols():
            self.expanded = not self.expanded
            self.update_expanded_icon()
            return True

        return False

    def first_child(self) -> TreeWidget | None:
        """Return first child if expanded."""
        if self.is_leaf or not self.expanded:
            return None

        if self._node.has_children():
            first_node = self._node.get_first_child()
            return first_node.get_widget()

        return None

    def last_child(self) -> TreeWidget | None:
        """Return last child if expanded."""
        if self.is_leaf or not self.expanded:
            return None

        if self._node.has_children():
            last_child = self._node.get_last_child().get_widget()
        else:
            return None
        # recursively search down for the last descendant
        last_descendant = last_child.last_child()
        if last_descendant is None:
            return last_child

        return last_descendant


class TreeNode:
    """
    Store tree contents and cache TreeWidget objects.
    A TreeNode consists of the following elements:
    *  key: accessor token for parent nodes
    *  value: subclass-specific data
    *  parent: a TreeNode which contains a pointer back to this object
    *  widget: The widget used to render the object
    """

    def __init__(
        self,
        value: typing.Any,
        parent: ParentNode | None = None,
        key: Hashable | None = None,
        depth: int | None = None,
    ) -> None:
        self._key = key
        self._parent = parent
        self._value = value
        self._depth = depth
        self._widget: TreeWidget | None = None

    def get_widget(self, reload: bool = False) -> TreeWidget:
        """Return the widget for this node."""
        if self._widget is None or reload:
            self._widget = self.load_widget()
        return self._widget

    def load_widget(self) -> TreeWidget:
        return TreeWidget(self)

    def get_depth(self) -> int:
        if self._depth is self._parent is None:
            self._depth = 0
        elif self._depth is None:
            self._depth = self._parent.get_depth() + 1
        return self._depth

    def get_index(self) -> int | None:
        if self.get_depth() == 0:
            return None

        return self.get_parent().get_child_index(self.get_key())

    def get_key(self) -> Hashable | None:
        return self._key

    def set_key(self, key: Hashable | None) -> None:
        self._key = key

    def change_key(self, key: Hashable | None) -> None:
        self.get_parent().change_child_key(self._key, key)

    def get_parent(self) -> ParentNode:
        if self._parent is None and self.get_depth() > 0:
            self._parent = self.load_parent()
        return self._parent

    def load_parent(self):
        """Provide TreeNode with a parent for the current node.  This function
        is only required if the tree was instantiated from a child node
        (virtual function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")

    def get_value(self):
        return self._value

    def is_root(self) -> bool:
        return self.get_depth() == 0

    def next_sibling(self) -> TreeNode | None:
        if self.get_depth() > 0:
            return self.get_parent().next_child(self.get_key())

        return None

    def prev_sibling(self) -> TreeNode | None:
        if self.get_depth() > 0:
            return self.get_parent().prev_child(self.get_key())

        return None

    def get_root(self) -> ParentNode:
        root = self
        while root.get_parent() is not None:
            root = root.get_parent()
        return root


class ParentNode(TreeNode):
    """Maintain sort order for TreeNodes."""

    def __init__(
        self,
        value: typing.Any,
        parent: ParentNode | None = None,
        key: Hashable = None,
        depth: int | None = None,
    ) -> None:
        super().__init__(value, parent=parent, key=key, depth=depth)

        self._child_keys: Sequence[Hashable] | None = None
        self._children: dict[Hashable, TreeNode] = {}

    def get_child_keys(self, reload: bool = False) -> Sequence[Hashable]:
        """Return a possibly ordered list of child keys"""
        if self._child_keys is None or reload:
            self._child_keys = self.load_child_keys()
        return self._child_keys

    def load_child_keys(self) -> Sequence[Hashable]:
        """Provide ParentNode with an ordered list of child keys (virtual function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")

    def get_child_widget(self, key) -> TreeWidget:
        """Return the widget for a given key.  Create if necessary."""

        return self.get_child_node(key).get_widget()

    def get_child_node(self, key, reload: bool = False) -> TreeNode:
        """Return the child node for a given key. Create if necessary."""
        if key not in self._children or reload:
            self._children[key] = self.load_child_node(key)
        return self._children[key]

    def load_child_node(self, key: Hashable) -> TreeNode:
        """Load the child node for a given key (virtual function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")

    def set_child_node(self, key: Hashable, node: TreeNode) -> None:
        """Set the child node for a given key.

        Useful for bottom-up, lazy population of a tree.
        """
        self._children[key] = node

    def change_child_key(self, oldkey: Hashable, newkey: Hashable) -> None:
        if newkey in self._children:
            raise TreeWidgetError(f"{newkey} is already in use")
        self._children[newkey] = self._children.pop(oldkey)
        self._children[newkey].set_key(newkey)

    def get_child_index(self, key: Hashable) -> int:
        try:
            return self.get_child_keys().index(key)
        except ValueError as exc:
            raise TreeWidgetError(
                f"Can't find key {key} in ParentNode {self.get_key()}\nParentNode items: {self.get_child_keys()!s}"
            ).with_traceback(exc.__traceback__) from exc

    def next_child(self, key: Hashable) -> TreeNode | None:
        """Return the next child node in index order from the given key."""

        index = self.get_child_index(key)
        # the given node may have just been deleted
        if index is None:
            return None
        index += 1

        child_keys = self.get_child_keys()
        if index < len(child_keys):
            # get the next item at same level
            return self.get_child_node(child_keys[index])

        return None

    def prev_child(self, key: Hashable) -> TreeNode | None:
        """Return the previous child node in index order from the given key."""
        index = self.get_child_index(key)
        if index is None:
            return None

        child_keys = self.get_child_keys()
        index -= 1

        if index >= 0:
            # get the previous item at same level
            return self.get_child_node(child_keys[index])

        return None

    def get_first_child(self) -> TreeNode:
        """Return the first TreeNode in the directory."""
        child_keys = self.get_child_keys()
        return self.get_child_node(child_keys[0])

    def get_last_child(self) -> TreeNode:
        """Return the last TreeNode in the directory."""
        child_keys = self.get_child_keys()
        return self.get_child_node(child_keys[-1])

    def has_children(self) -> bool:
        """Does this node have any children?"""
        return len(self.get_child_keys()) > 0


class TreeWalker(ListWalker):
    """ListWalker-compatible class for displaying TreeWidgets

    positions are TreeNodes."""

    def __init__(self, start_from) -> None:
        """start_from: TreeNode with the initial focus."""
        self.focus = start_from

    def get_focus(self):
        widget = self.focus.get_widget()
        return widget, self.focus

    def set_focus(self, focus) -> None:
        self.focus = focus
        self._modified()

    # pylint: disable=arguments-renamed  # its bad, but we should not change API
    def get_next(self, start_from) -> tuple[TreeWidget, TreeNode] | tuple[None, None]:
        target = start_from.get_widget().next_inorder()
        if target is None:
            return None, None

        return target, target.get_node()

    def get_prev(self, start_from) -> tuple[TreeWidget, TreeNode] | tuple[None, None]:
        target = start_from.get_widget().prev_inorder()
        if target is None:
            return None, None

        return target, target.get_node()

    # pylint: enable=arguments-renamed


class TreeListBox(ListBox):
    """A ListBox with special handling for navigation and
    collapsing of TreeWidgets"""

    def keypress(
        self,
        size: tuple[int, int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        key: str | None = super().keypress(size, key)
        return self.unhandled_input(size, key)

    def unhandled_input(self, size: tuple[int, int], data: str) -> str | None:
        """Handle macro-navigation keys"""
        if data == "left":
            self.move_focus_to_parent(size)
            return None
        if data == "-":
            self.collapse_focus_parent(size)
            return None

        return data

    def collapse_focus_parent(self, size: tuple[int, int]) -> None:
        """Collapse parent directory."""

        _widget, pos = self.body.get_focus()
        self.move_focus_to_parent(size)

        _pwidget, ppos = self.body.get_focus()
        if pos != ppos:
            self.keypress(size, "-")

    def move_focus_to_parent(self, size: tuple[int, int]) -> None:
        """Move focus to parent of widget in focus."""

        _widget, pos = self.body.get_focus()

        parentpos = pos.get_parent()

        if parentpos is None:
            return

        middle, top, _bottom = self.calculate_visible(size)

        row_offset, _focus_widget, _focus_pos, _focus_rows, _cursor = middle  # pylint: disable=unpacking-non-sequence
        _trim_top, fill_above = top  # pylint: disable=unpacking-non-sequence

        for _widget, pos, rows in fill_above:
            row_offset -= rows
            if pos == parentpos:
                self.change_focus(size, pos, row_offset)
                return

        self.change_focus(size, pos.get_parent())

    def _keypress_max_left(self, size: tuple[int, int]) -> None:
        self.focus_home(size)

    def _keypress_max_right(self, size: tuple[int, int]) -> None:
        self.focus_end(size)

    def focus_home(self, size: tuple[int, int]) -> None:
        """Move focus to very top."""

        _widget, pos = self.body.get_focus()
        rootnode = pos.get_root()
        self.change_focus(size, rootnode)

    def focus_end(self, size: tuple[int, int]) -> None:
        """Move focus to far bottom."""

        maxrow, _maxcol = size
        _widget, pos = self.body.get_focus()
        lastwidget = pos.get_root().get_widget().last_child()
        if lastwidget:
            lastnode = lastwidget.get_node()

            self.change_focus(size, lastnode, maxrow - 1)
