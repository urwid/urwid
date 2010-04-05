#!/usr/bin/python
#
# Generic TreeWidget/TreeWalker class 
#    Copyright (c) 2010  Rob Lanphier
# Derived from Urwid example lazy directory browser / tree view:
#    Copyright (C) 2004-2009  Ian Ward
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
# Urwid web site: http://excess.org/urwid/

"""
Urwid tree view

Features:
- custom selectable widgets for trees
- custom list walker for displaying widgets in a tree fashion
"""


import urwid

import os


class TreeWidgetError(RuntimeError):
    pass


class TreeWidget(urwid.WidgetWrap):
    """A widget representing something in the file tree."""
    def __init__(self, node):
        self._node = node
        self._innerwidget = None
        self.selected = False

        widget = self.get_indented_widget()

        w = urwid.AttrWrap(widget, None)
        self.__super.__init__(w)
        # Compatibility fix for 0.9.9+
        if not hasattr(self, 'get_w'):
            self.get_w = self._retro_get_w
        self.update_w()
    
    def _retro_get_w(self):
        """
        Implementation of get_w() if the base urwid install doesn't support it.
        """
        return self._w

    def get_indented_widget(self):
        leftmargin = urwid.Text("")
        widgetlist = [self.get_inner_widget()]
        indent_cols = self.get_indent_cols()
        if indent_cols > 0:
            widgetlist.insert(0, ('fixed', indent_cols, leftmargin))
        return urwid.Columns(widgetlist)

    def get_indent_cols(self):
        return 3 * self.get_node().get_depth()

    def get_inner_widget(self):
        if self._innerwidget is None:
            self._innerwidget = self.load_inner_widget()
        return self._innerwidget

    def load_inner_widget(self):
        return urwid.Text(self.get_display_text())
        
    def get_node(self):
        return self._node

    def get_display_text(self):
        return (self.get_node().get_key() + ": " + 
                str(self.get_node().get_value()))

    def selectable(self):
        return True
    
    def is_selected(self):
        return self.selected

    def set_selected(self, value=True):
        self.selected = value

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        w = self.get_w()
        try:
            key = w.keypress(size, key)
        except AttributeError:
            # no biggie...we'll just handle the keypress here
            pass
        key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        """
        Override this method to intercept keystrokes in subclasses.
        Default behavior: Toggle selected on space, ignore other keys.
        """
        if key == " ":
            self.selected = not self.selected
            self.update_w()
        else:
            return key

    def update_w(self):
        """Update the attributes of self.widget based on self.selected.
        """
        if self.selected:
            self.get_w().attr = 'selected'
            self.get_w().focus_attr = 'selected focus'
        else:
            self.get_w().attr = 'body'
            self.get_w().focus_attr = 'focus'

    def next_inorder(self):
        """Return the next TreeWidget depth first from this one."""
        # first check if there's a child widget
        firstchild = self.first_child()
        if firstchild is not None:
            return firstchild

        # now we need to hunt for the next sibling
        thisnode = self.get_node()
        nextnode = thisnode.next_sibling()
        depth = thisnode.get_depth()
        while nextnode is None and depth > 0:
            # keep going up the tree until we find an ancestor next sibling
            thisnode = thisnode.get_parent()
            nextnode = thisnode.next_sibling()
            depth -= 1
            assert depth == thisnode.get_depth()
        if nextnode is None:
            # we're at the end of the tree
            return None
        else:
            return nextnode.get_widget()

    def prev_inorder(self):
        """Return the previous TreeWidget depth first from this one."""
        thisnode = self._node
        prevnode = thisnode.prev_sibling()
        if prevnode is not None:
            # we need to find the last child of the previous widget if its
            # expanded
            prevwidget = prevnode.get_widget()
            lastchild = prevwidget.last_child()
            if lastchild is None:
                return prevwidget
            else:
                return lastchild
        else:
            # need to hunt for the parent
            depth = thisnode.get_depth()
            if prevnode is None and depth == 0:
                return None
            elif prevnode is None:
                prevnode = thisnode.get_parent()
            return prevnode.get_widget()

    def first_child(self):
        """Default to have no children."""
        return None
    
    def last_child(self):
        """Default to have no children."""
        return None

class ParentWidget(TreeWidget):
    """Widget for an interior tree node."""

    def __init__(self, node):
        self.__super.__init__(node)
        self.expanded = True
        
        self.update_widget()
    
    def update_widget(self):
        """Update display widget text."""
        
        if self.expanded:
            mark = "-"
        else:
            mark = "+"
        self._innerwidget.set_text([('dirmark', mark), " ", self.get_display_text()] )

    def keypress(self, size, key):
        """Handle expand & collapse requests."""
        
        if key in ("+", "right"):
            self.expanded = True
            self.update_widget()
        elif key == "-":
            self.expanded = False
            self.update_widget()
        else:
            return self.__super.keypress(size, key)
    
    def mouse_event(self, size, event, button, col, row, focus):
        if event != 'mouse press' or button!=1:
            return False

        if row == 0 and col == self.get_indent_cols():
            self.expanded = not self.expanded
            self.update_widget()
            return True
        
        return False
    
    def first_child(self):
        """Return first child if expanded."""
        if not self.expanded: 
            return None
        else:
            if self._node.has_children():
                firstnode = self._node.get_first_child()
                return firstnode.get_widget()
            else:
                return None

    def last_child(self):
        """Return last child if expanded."""
        if not self.expanded:
            return None
        else:
            if self._node.has_children():
                lastchild = self._node.get_last_child().get_widget()
            else:
                return None
            # recursively search down for the last descendant
            lastdescendant = lastchild.last_child()
            if lastdescendant is None:
                return lastchild
            else:
                return lastdescendant


class TreeNode(object):
    """
    Store tree contents and cache TreeWidget objects.  
    A TreeNode consists of the following elements:
    *  key: accessor token for parent nodes
    *  value: subclass-specific data
    *  parent: a TreeNode which contains a pointer back to this object
    *  widget: The widget used to render the object
    """
    def __init__(self, value, parent=None, key=None, depth=None):
        self._key = key
        self._parent = parent
        self._value = value
        self._depth = depth
        self._widget = None

    def get_widget(self, reload=False):
        """ Return the widget for this node."""
        if self._widget is None or reload == True:
            self._widget = self.load_widget()
        return self._widget

    def load_widget(self):
        return TreeWidget(self)
        
    def get_depth(self):
        if self._depth is None and self._parent is None:
            self._depth = 0
        elif self._depth is None:
            self._depth = self._parent.get_depth() + 1
        return self._depth
            
    def get_index(self):
        if self.get_depth() == 0:
            return None
        else:
            key = self.get_key()
            parent = self.get_parent()
            return parent.get_child_index(key)

    def get_key(self):
        return self._key

    def set_key(self, key):
        self._key = key

    def change_key(self, key):
        self.get_parent().change_child_key(self._key, key)

    def get_parent(self):
        if self._parent == None and self.get_depth() > 0:
            self._parent = self.load_parent()
        return self._parent
        
    def load_parent(self):
        """Provide TreeNode with a parent for the current node.  This function
        is only required if the tree was instantiated from a child node
        (virtual function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")
        
    def get_value(self):
        return self._value

    def is_root(self):
        return self.get_depth() == 0
        
    def next_sibling(self):
        if self.get_depth() > 0:
            return self.get_parent().next_child(self.get_key())
        else:
            return None

    def prev_sibling(self):
        if self.get_depth() > 0:
            return self.get_parent().prev_child(self.get_key())
        else:
            return None

    def get_root(self):
        root = self
        while root.get_parent() is not None:
            root = root.get_parent()
        return root

    def get_selected_nodes(self):
        if self.get_widget().is_selected():
            return [self]
        else:
            return []
        
        
class ParentNode(TreeNode):
    """Maintain sort order for TreeNodes."""
    def __init__(self, value, parent=None, key=None, depth=None):
        TreeNode.__init__(self, value, parent=parent, key=key, depth=depth)

        self._child_keys = None
        self._children = {}

    def load_widget(self):
        return ParentWidget(self)

    def get_child_keys(self, reload=False):
        """Return a possibly ordered list of child keys"""
        if self._child_keys is None or reload == True:
            self._child_keys = self.load_child_keys()
        return self._child_keys

    def load_child_keys(self):
        """Provide ParentNode with an ordered list of child keys (virtual
        function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")

    def get_child_widget(self, key):
        """Return the widget for a given key.  Create if necessary."""
        
        child = self.get_child_node(key)
        return child.get_widget()

    def get_child_node(self, key, reload=False):
        """Return the child node for a given key.  Create if necessary."""
        if key not in self._children or reload == True:
            self._children[key] = self.load_child_node(key)
        return self._children[key]

    def load_child_node(self, key):
        """Load the child node for a given key (virtual function)"""
        raise TreeWidgetError("virtual function.  Implement in subclass")

    def set_child_node(self, key, node):
        """Set the child node for a given key.  Useful for bottom-up, lazy 
        population of a tree.."""
        self._children[key]=node
    
    def change_child_key(self, oldkey, newkey):
        if newkey in self._children:
            raise TreeWidgetError("%s is already in use" % newkey)
        self._children[newkey] = self._children.pop(oldkey)
        self._children[newkey].set_key(newkey)

    def get_child_index(self, key):
        try:
            return self.get_child_keys().index(key)
        except ValueError:
            errorstring = ("Can't find key %s in ParentNode %s\n" +
                           "ParentNode items: %s")
            raise TreeWidgetError(errorstring % (key, self.get_key(), 
                                  str(self.get_child_keys())))

    def next_child(self, key):
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
        else:
            return None

    def prev_child(self, key):
        """Return the previous child node in index order from the given key."""
        index = self.get_child_index(key)
        if index is None:
            return None

        child_keys = self.get_child_keys()
        index -= 1
        
        if index >= 0:
            # get the previous item at same level
            return self.get_child_node(child_keys[index])
        else:
            return None

    def get_first_child(self):
        """Return the first TreeNode in the directory."""
        child_keys = self.get_child_keys()
        return self.get_child_node(child_keys[0])
    
    def get_last_child(self):
        """Return the last TreeNode in the directory."""
        child_keys = self.get_child_keys()
        return self.get_child_node(child_keys[-1])
        
    def has_children(self):
        """Does this node have any children?"""
        return len(self.get_child_keys())>0

    def get_selected_nodes(self):
        retval = []
        if self.get_widget().is_selected():
            retval.append(self)
        for key in self.get_child_keys():
            child = self.get_child_node(key)
            retval += child.get_selected_nodes()
        return retval


class TreeWalker(urwid.ListWalker):
    """ListWalker-compatible class for browsing directories.
    
    positions are TreeNodes."""
    
    def __init__(self, start_from):
        """start_from: TreeNode with the initial focus."""
        self.focus = start_from

    def get_focus(self):
        widget = self.focus.get_widget()
        return widget, self.focus
        
    def set_focus(self, focus):
        self.focus = focus
        self._modified()

    def get_next(self, start_from):
        widget = start_from.get_widget()
        target = widget.next_inorder()
        if target is None:
            return None, None
        else:
            return target, target.get_node()

    def get_prev(self, start_from):
        widget = start_from.get_widget()
        target = widget.prev_inorder()
        if target is None:
            return None, None
        else:
            return target, target.get_node()


class TreeListBox(urwid.ListBox):
    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        return self.unhandled_input(size, key)

    def unhandled_input(self, size, input):
        """Handle macro-navigation keys"""
        if input == 'left':
            self.move_focus_to_parent(size)
        elif input == '-':
            self.collapse_focus_parent(size)
        elif input == 'home':
            self.focus_home(size)
        elif input == 'end':
            self.focus_end(size)
        else:
            return input
                                        
    def collapse_focus_parent(self, size):
        """Collapse parent directory."""

        widget, pos = self.body.get_focus()
        self.move_focus_to_parent(size)
        
        pwidget, ppos = self.body.get_focus()
        if pos != ppos:
            self.keypress(size, "-")

    def move_focus_to_parent(self, size):
        """Move focus to parent of widget in focus."""

        widget, pos = self.body.get_focus()
        
        parentpos = pos.get_parent()
        
        if parentpos is None:
            return
        
        middle, top, bottom = self.calculate_visible( size )

        row_offset, focus_widget, focus_pos, focus_rows, cursor = middle
        trim_top, fill_above = top

        for widget, pos, rows in fill_above:
            row_offset -= rows
            if pos == parentpos:
                self.change_focus(size, pos, row_offset)
                return

        self.change_focus(size, pos.get_parent())
        
    def focus_home(self, size):
        """Move focus to very top."""

        widget, pos = self.body.get_focus()
        rootnode = pos.get_root()
        self.change_focus(size, rootnode)

    def focus_end( self, size ):
        """Move focus to far bottom."""

        maxrow, maxcol = size
        widget, pos = self.body.get_focus()
        rootnode = pos.get_root()
        rootwidget = rootnode.get_widget()
        lastwidget = rootwidget.last_child()
        lastnode = lastwidget.get_node()

        self.change_focus(size, lastnode, maxrow-1)

