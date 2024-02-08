#!/usr/bin/env python
#
# Trivial data browser
#    This version:
#      Copyright (C) 2010  Rob Lanphier
#    Derived from browse.py in urwid distribution
#      Copyright (C) 2004-2007  Ian Ward
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
Urwid example lazy directory browser / tree view

Features:
- custom selectable widgets for files and directories
- custom message widgets to identify access errors and empty directories
- custom list walker for displaying widgets in a tree fashion
"""

from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable


class ExampleTreeWidget(urwid.TreeWidget):
    """Display widget for leaf nodes"""

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        return self.get_node().get_value()["name"]


class ExampleNode(urwid.TreeNode):
    """Data storage object for leaf nodes"""

    def load_widget(self) -> ExampleTreeWidget:
        return ExampleTreeWidget(self)


class ExampleParentNode(urwid.ParentNode):
    """Data storage object for interior/parent nodes"""

    def load_widget(self) -> ExampleTreeWidget:
        return ExampleTreeWidget(self)

    def load_child_keys(self) -> Iterable[int]:
        data = self.get_value()
        return range(len(data["children"]))

    def load_child_node(self, key) -> ExampleParentNode | ExampleNode:
        """Return either an ExampleNode or ExampleParentNode"""
        childdata = self.get_value()["children"][key]
        childdepth = self.get_depth() + 1
        if "children" in childdata:
            childclass = ExampleParentNode
        else:
            childclass = ExampleNode
        return childclass(childdata, parent=self, key=key, depth=childdepth)


class ExampleTreeBrowser:
    palette: typing.ClassVar[tuple[str, str, str, ...]] = [
        ("body", "black", "light gray"),
        ("focus", "light gray", "dark blue", "standout"),
        ("head", "yellow", "black", "standout"),
        ("foot", "light gray", "black"),
        ("key", "light cyan", "black", "underline"),
        ("title", "white", "black", "bold"),
        ("flag", "dark gray", "light gray"),
        ("error", "dark red", "light gray"),
    ]

    footer_text: typing.ClassVar[list[tuple[str, str] | str]] = [
        ("title", "Example Data Browser"),
        "    ",
        ("key", "UP"),
        ",",
        ("key", "DOWN"),
        ",",
        ("key", "PAGE UP"),
        ",",
        ("key", "PAGE DOWN"),
        "  ",
        ("key", "+"),
        ",",
        ("key", "-"),
        "  ",
        ("key", "LEFT"),
        "  ",
        ("key", "HOME"),
        "  ",
        ("key", "END"),
        "  ",
        ("key", "Q"),
    ]

    def __init__(self, data=None) -> None:
        self.topnode = ExampleParentNode(data)
        self.listbox = urwid.TreeListBox(urwid.TreeWalker(self.topnode))
        self.listbox.offset_rows = 1
        self.header = urwid.Text("")
        self.footer = urwid.AttrMap(urwid.Text(self.footer_text), "foot")
        self.view = urwid.Frame(
            urwid.AttrMap(self.listbox, "body"),
            header=urwid.AttrMap(self.header, "head"),
            footer=self.footer,
        )

    def main(self) -> None:
        """Run the program."""

        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, k: str | tuple[str, int, int, int]) -> None:
        if k in {"q", "Q"}:
            raise urwid.ExitMainLoop()


def get_example_tree():
    """generate a quick 100 leaf tree for demo purposes"""
    retval = {"name": "parent", "children": []}
    for i in range(10):
        retval["children"].append({"name": f"child {i!s}"})
        retval["children"][i]["children"] = []
        for j in range(10):
            retval["children"][i]["children"].append({"name": "grandchild " + str(i) + "." + str(j)})
    return retval


def main() -> None:
    sample = get_example_tree()
    ExampleTreeBrowser(sample).main()


if __name__ == "__main__":
    main()
