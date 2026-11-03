"""Type checker fixture for subclassing the tree node and widget classes.

mypy, Pyrefly and Pyright check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    class NameNode(urwid.TreeNode[str]):
        """Load a widget typed with this node class rather than with the base one."""

        def load_widget(self) -> NameWidget:
            """Return the widget for this node."""
            return NameWidget(self)

    class NameWidget(urwid.TreeWidget[NameNode]):
        """Show the name a node holds."""

        def get_display_text(self) -> str:
            """Return the node value as the widget text."""
            return self.get_node().get_value()

    def widget_of_subclass_is_base_widget(widget: NameWidget) -> urwid.TreeWidget[urwid.TreeNode[str]]:
        """Accept the widget of a node subclass where a widget of the base node is expected."""
        return widget

    class TriangleWidget(urwid.TreeWidget[NameNode]):
        """Draw the expand and collapse icons with symbols of the widget class."""

        unexpanded_icon = urwid.SelectableIcon(urwid.TreeWidget.Symbols.TRIANGLE_RIGHT, 0)
        expanded_icon = urwid.SelectableIcon(urwid.TreeWidget.Symbols.TRIANGLE_DOWN, 0)

    def symbols() -> None:
        """Type the symbols as members of their enumeration, usable wherever text is."""
        assert_type(urwid.TreeWidget.Symbols.PLUS, typing.Literal[urwid.widget.treetools.TreeSymbols.PLUS])
