#!/usr/bin/env python
#
# Urwid example lazy directory browser / tree view
#    Copyright (C) 2004-2011  Ian Ward
#    Copyright (C) 2010  Kirk McDonald
#    Copyright (C) 2010  Rob Lanphier
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
- outputs a quoted list of files and directories "selected" on exit
"""

from __future__ import annotations

import itertools
import os
import re
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Hashable


class FlagFileWidget(urwid.TreeWidget):
    # apply an attribute to the expand/unexpand icons
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, "dirmark")
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, "dirmark")

    def __init__(self, node: urwid.TreeNode) -> None:
        super().__init__(node)
        # insert an extra AttrWrap for our own use
        self._w = urwid.AttrMap(self._w, None)
        self.flagged = False
        self.update_w()

    def selectable(self) -> bool:
        return True

    def keypress(self, size, key: str) -> str | None:
        """allow subclasses to intercept keystrokes"""
        key = super().keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key: str) -> str | None:
        """
        Override this method to intercept keystrokes in subclasses.
        Default behavior: Toggle flagged on space, ignore other keys.
        """
        if key == " ":
            self.flagged = not self.flagged
            self.update_w()
            return None

        return key

    def update_w(self) -> None:
        """Update the attributes of self.widget based on self.flagged."""
        if self.flagged:
            self._w.attr_map = {None: "flagged"}
            self._w.focus_map = {None: "flagged focus"}
        else:
            self._w.attr_map = {None: "body"}
            self._w.focus_map = {None: "focus"}


class FileTreeWidget(FlagFileWidget):
    """Widget for individual files."""

    def __init__(self, node: FileNode) -> None:
        super().__init__(node)
        path = node.get_value()
        add_widget(path, self)

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        return self.get_node().get_key()


class EmptyWidget(urwid.TreeWidget):
    """A marker for expanded directories with no contents."""

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        return ("flag", "(empty directory)")


class ErrorWidget(urwid.TreeWidget):
    """A marker for errors reading directories."""

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        return ("error", "(error/permission denied)")


class DirectoryWidget(FlagFileWidget):
    """Widget for a directory."""

    def __init__(self, node: DirectoryNode) -> None:
        super().__init__(node)
        path = node.get_value()
        add_widget(path, self)
        self.expanded = starts_expanded(path)
        self.update_expanded_icon()

    def get_display_text(self) -> str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]:
        node = self.get_node()
        if node.get_depth() == 0:
            return "/"

        return node.get_key()


class FileNode(urwid.TreeNode):
    """Metadata storage for individual files"""

    def __init__(self, path: str, parent: urwid.ParentNode | None = None) -> None:
        depth = path.count(dir_sep())
        key = os.path.basename(path)
        super().__init__(path, key=key, parent=parent, depth=depth)

    def load_parent(self) -> DirectoryNode:
        parentname, _myname = os.path.split(self.get_value())
        parent = DirectoryNode(parentname)
        parent.set_child_node(self.get_key(), self)
        return parent

    def load_widget(self) -> FileTreeWidget:
        return FileTreeWidget(self)


class EmptyNode(urwid.TreeNode):
    def load_widget(self) -> EmptyWidget:
        return EmptyWidget(self)


class ErrorNode(urwid.TreeNode):
    def load_widget(self) -> ErrorWidget:
        return ErrorWidget(self)


class DirectoryNode(urwid.ParentNode):
    """Metadata storage for directories"""

    def __init__(self, path: str, parent: urwid.ParentNode | None = None) -> None:
        if path == dir_sep():
            depth = 0
            key = None
        else:
            depth = path.count(dir_sep())
            key = os.path.basename(path)
        super().__init__(path, key=key, parent=parent, depth=depth)

    def load_parent(self) -> DirectoryNode:
        parentname, _myname = os.path.split(self.get_value())
        parent = DirectoryNode(parentname)
        parent.set_child_node(self.get_key(), self)
        return parent

    def load_child_keys(self):
        dirs = []
        files = []
        try:
            path = self.get_value()
            # separate dirs and files
            for a in os.listdir(path):
                if os.path.isdir(os.path.join(path, a)):
                    dirs.append(a)
                else:
                    files.append(a)
        except OSError:
            depth = self.get_depth() + 1
            self._children[None] = ErrorNode(self, parent=self, key=None, depth=depth)
            return [None]

        # sort dirs and files
        dirs.sort(key=alphabetize)
        files.sort(key=alphabetize)
        # store where the first file starts
        self.dir_count = len(dirs)
        # collect dirs and files together again
        keys = dirs + files
        if len(keys) == 0:
            depth = self.get_depth() + 1
            self._children[None] = EmptyNode(self, parent=self, key=None, depth=depth)
            keys = [None]
        return keys

    def load_child_node(self, key) -> EmptyNode | DirectoryNode | FileNode:
        """Return either a FileNode or DirectoryNode"""
        index = self.get_child_index(key)
        if key is None:
            return EmptyNode(None)

        path = os.path.join(self.get_value(), key)
        if index < self.dir_count:
            return DirectoryNode(path, parent=self)

        path = os.path.join(self.get_value(), key)
        return FileNode(path, parent=self)

    def load_widget(self) -> DirectoryWidget:
        return DirectoryWidget(self)


class DirectoryBrowser:
    palette: typing.ClassVar[list[tuple[str, str, str, ...]]] = [
        ("body", "black", "light gray"),
        ("flagged", "black", "dark green", ("bold", "underline")),
        ("focus", "light gray", "dark blue", "standout"),
        ("flagged focus", "yellow", "dark cyan", ("bold", "standout", "underline")),
        ("head", "yellow", "black", "standout"),
        ("foot", "light gray", "black"),
        ("key", "light cyan", "black", "underline"),
        ("title", "white", "black", "bold"),
        ("dirmark", "black", "dark cyan", "bold"),
        ("flag", "dark gray", "light gray"),
        ("error", "dark red", "light gray"),
    ]

    footer_text: typing.ClassVar[list[tuple[str, str] | str]] = [
        ("title", "Directory Browser"),
        "    ",
        ("key", "UP"),
        ",",
        ("key", "DOWN"),
        ",",
        ("key", "PAGE UP"),
        ",",
        ("key", "PAGE DOWN"),
        "  ",
        ("key", "SPACE"),
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

    def __init__(self) -> None:
        cwd = os.getcwd()
        store_initial_cwd(cwd)
        self.header = urwid.Text("")
        self.listbox = urwid.TreeListBox(urwid.TreeWalker(DirectoryNode(cwd)))
        self.listbox.offset_rows = 1
        self.footer = urwid.AttrMap(urwid.Text(self.footer_text), "foot")
        self.view = urwid.Frame(
            urwid.AttrMap(
                urwid.ScrollBar(
                    self.listbox,
                    thumb_char=urwid.ScrollBar.Symbols.FULL_BLOCK,
                    trough_char=urwid.ScrollBar.Symbols.LITE_SHADE,
                ),
                "body",
            ),
            header=urwid.AttrMap(self.header, "head"),
            footer=self.footer,
        )

    def main(self) -> None:
        """Run the program."""

        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_input)
        self.loop.run()

        # on exit, write the flagged filenames to the console
        names = [escape_filename_sh(x) for x in get_flagged_names()]
        print(" ".join(names))

    def unhandled_input(self, k: str | tuple[str, int, int, int]) -> None:
        # update display of focus directory
        if k in {"q", "Q"}:
            raise urwid.ExitMainLoop()


def main():
    DirectoryBrowser().main()


#######
# global cache of widgets
_widget_cache = {}


def add_widget(path, widget):
    """Add the widget for a given path"""

    _widget_cache[path] = widget


def get_flagged_names() -> list[str]:
    """Return a list of all filenames marked as flagged."""

    names = [w.get_node().get_value() for w in _widget_cache.values() if w.flagged]
    return names


######
# store path components of initial current working directory
_initial_cwd = []


def store_initial_cwd(name: str) -> None:
    """Store the initial current working directory path components."""

    _initial_cwd.clear()
    _initial_cwd.extend(name.split(dir_sep()))


def starts_expanded(name: str) -> bool:
    """Return True if directory is a parent of initial cwd."""

    if name == "/":
        return True

    path_elements = name.split(dir_sep())
    if len(path_elements) > len(_initial_cwd):
        return False

    return path_elements == _initial_cwd[: len(path_elements)]


def escape_filename_sh(name: str) -> str:
    """Return a hopefully safe shell-escaped version of a filename."""

    # check whether we have unprintable characters
    for ch in name:
        if ord(ch) < 32:
            # found one so use the ansi-c escaping
            return escape_filename_sh_ansic(name)

    # all printable characters, so return a double-quoted version
    name = name.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{name}"'


def escape_filename_sh_ansic(name: str) -> str:
    """Return an ansi-c shell-escaped version of a filename."""

    out = []
    # gather the escaped characters into a list
    for ch in name:
        if ord(ch) < 32:
            out.append(f"\\x{ord(ch):02x}")
        elif ch == "\\":
            out.append("\\\\")
        else:
            out.append(ch)

    # slap them back together in an ansi-c quote  $'...'
    return f"$'{''.join(out)}'"


SPLIT_RE = re.compile(r"[a-zA-Z]+|\d+")


def alphabetize(s: str) -> list[str]:
    L = []
    for isdigit, group in itertools.groupby(SPLIT_RE.findall(s), key=str.isdigit):
        if isdigit:
            L.extend(("", int(n)) for n in group)
        else:
            L.append(("".join(group).lower(), 0))
    return L


def dir_sep() -> str:
    """Return the separator used in this os."""
    return getattr(os.path, "sep", "/")


if __name__ == "__main__":
    main()
