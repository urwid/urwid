#!/usr/bin/python
#
# Urwid example lazy directory browser / tree view
#    Copyright (C) 2004  Ian Ward
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
Urwid example lazy directory browser / tree view

Features:
- custom selectable widgets for files and directories
- custom message widgets to identify access errors and empty directories
- custom list walker for displaying widgets in a tree fashion
- outputs a quoted list of files and directories "selected" on exit
"""


import urwid
import urwid.curses_display

import os

try: True # old python?
except: False, True = 0, 1
		

class TreeWidget(urwid.FlowWidget):
	"""A widget representing something in the file tree."""
	
	def __init__(self, dir, name, index):
		self.dir = dir
		self.name = name
		self.index = index
		self.widget = None # subclass will set this
		self.selected = False
		
		parent, _ign = os.path.split(dir)
		# we're at the top if parent is same as dir
		if dir == parent:
			self.depth = 0
		else:
		 	self.depth = dir.count(dir_sep())
	
	def rows(self, (maxcol,), **args):
		"""Return rows from display widget."""
		return self.widget.rows((maxcol,), **args)
	
	def selectable(self):
		"""Default to selectable."""
		return True

	def keypress(self, (maxcol,), key):
		"""Toggle selected on space, ignore other keys."""

		if key == " ":
			self.selected = not self.selected
		else:
			return key

	def render(self, (maxcol,), **args ):
		"""Wrap display widget with appropriate attribute."""

		if self.selected:
			wrap = urwid.AttrWrap( self.widget, 'selected', 
				'selected focus')
		else:
			wrap = urwid.AttrWrap( self.widget, 'body', 'focus')
	
		return wrap.render( (maxcol,), ** args )
		
	def first_child(self):
		"""Default to have no children."""
		return None
	
	def last_child(self):
		"""Default to have no children."""
		return None
	
	def next_inorder(self):
		"""Return the next TreeWidget depth first from this one."""
		
		child = self.first_child()
		if child: 
			return child
		else:
			dir = get_directory(self.dir)
			return dir.next_inorder_from(self.index)
	
	def prev_inorder(self):
		"""Return the previous TreeWidget depth first from this one."""
		
		dir = get_directory(self.dir)
		return dir.prev_inorder_from(self.index)


class EmptyWidget(TreeWidget):
	"""A marker for expanded directories with no contents."""
	
	def __init__(self, dir, name, index):
		TreeWidget.__init__(self, dir, name, index)
		self.widget = urwid.Text( [ "  "*self.depth,
			('flag',"(empty directory)")])

	def selectable(self): 
		return False

class ErrorWidget(TreeWidget):
	"""A marker for errors reading directories."""

	def __init__(self, dir, name, index):
		TreeWidget.__init__(self, dir, name, index)
		self.widget = urwid.Text( [ "  "*self.depth,
			('error',"(error/permission denied)")])

	def selectable(self): 
		return False


class FileWidget(TreeWidget):
	"""Widget for a simple file (or link, device node, etc)."""
	
	def __init__(self, dir, name, index):
		TreeWidget.__init__(self, dir, name, index)
		self.widget = urwid.Text("  "*self.depth + name)


class DirectoryWidget(TreeWidget):
	"""Widget for a directory."""
	
	def __init__(self, dir, name, index ):
		TreeWidget.__init__(self, dir, name, index)
		
		# check if this directory starts expanded
		self.expanded = starts_expanded( os.path.join(dir,name) )
		
		self.widget = urwid.Text("")
		self.update_widget()
	
	def update_widget(self):
		"""Update display widget text."""
		
		if self.expanded:
			mark = "+"
		else:
			mark = "-"
		self.widget.set_text( ["  "*(self.depth),
			('dirmark', mark), " ", self.name] )

	def keypress(self, (maxcol,), key ):
		"""Handle expand & collapse requests."""
		
		if key == "+":
			self.expanded = True
			self.update_widget()
		elif key == "-":
			self.expanded = False
			self.update_widget()
		else:
			return TreeWidget.keypress(self, (maxcol,), key)
	
	def first_child(self):
		"""Return first child if expanded."""
		
		if not self.expanded: 
			return None
		full_dir = os.path.join(self.dir, self.name)
		dir = get_directory( full_dir )
		return dir.get_first()
	
	def last_child(self):
		"""Return last child if expanded."""
		
		if not self.expanded:
			return None
		full_dir = os.path.join(self.dir, self.name)
		dir = get_directory( full_dir )
		widget = dir.get_last()
		sub = widget.last_child()
		if sub is not None:
			return sub
		return widget
		
		

class Directory:
	"""Store sorted directory contents and cache TreeWidget objects."""
	
	def __init__(self, path):
		self.path = path
		self.widgets = {}

		dirs = []
		files = []
		try:
			# separate dirs and files
			for a in os.listdir(path):
				if os.path.isdir(os.path.join(path,a)):
					dirs.append( a )
				else:
					files.append( a )
		except OSError, e:
			self.widgets[None] = ErrorWidget( self.path, None, 0 )

		# sort dirs and files
		dirs.sort(sensible_cmp)
		files.sort(sensible_cmp)
		# store where the first file starts
		self.dir_count = len(dirs)
		# collect dirs and files together again
		self.items = dirs + files

		# if no items, put a dummy None item in the list
		if not self.items:
			self.items = [None]

	def get_widget(self, name):
		"""Return the widget for a given file.  Create if necessary."""
		
		if self.widgets.has_key( name ):
			return self.widgets[name]
		
		# determine the correct TreeWidget type (constructor)
		index = self.items.index( name )
		if name is None:
			constructor = EmptyWidget
		elif index < self.dir_count:
			constructor = DirectoryWidget
		else:
			constructor = FileWidget

		widget = constructor( self.path, name, index )
		
		self.widgets[name] = widget
		return widget

		
	def next_inorder_from(self, index):
		"""Return the TreeWidget following index depth first."""
	
		index += 1
		# try to get the next item at same level
		if index < len(self.items):
			return self.get_widget(self.items[index])
			
		# need to go up a level
		parent, myname = os.path.split(self.path)
		# give up if we can't go higher
		if parent == self.path: return None

		# find my location in parent, and return next inorder
		pdir = get_directory( parent )
		mywidget = pdir.get_widget( myname )
		return pdir.next_inorder_from( mywidget.index )
		
	def prev_inorder_from(self, index):
		"""Return the TreeWidget preceeding index depth first."""
		
		index -= 1
		if index >= 0:
			widget = self.get_widget(self.items[index])
			widget_child = widget.last_child()
			if widget_child: 
				return widget_child
			else:
				return widget

		# need to go up a level
		parent, myname = os.path.split(self.path)
		# give up if we can't go higher
		if parent == self.path: return None

		# find myself in parent, and return
		pdir = get_directory( parent )
		return pdir.get_widget( myname )

	def get_first(self):
		"""Return the first TreeWidget in the directory."""
		
		return self.get_widget(self.items[0])
	
	def get_last(self):
		"""Return the last TreeWIdget in the directory."""
		
		return self.get_widget(self.items[-1])
		


class DirectoryWalker:
	"""ListWalker-compatible class for browsing directories.
	
	positions used are directory,filename tuples."""
	
	def __init__(self, start_from ):
		parent = start_from
		dir = get_directory(parent)
		widget = dir.get_first()
		self.focus = parent, widget.name

	def get_focus(self):
		parent, name = self.focus
		dir = get_directory( parent )
		widget = dir.get_widget( name )
		return widget, self.focus
		
	def set_focus(self, focus):
		parent, name = focus
		self.focus = parent, name
	
	def get_next(self, start_from):
		parent, name = start_from
		dir = get_directory( parent )
		widget = dir.get_widget(name)
		target = widget.next_inorder()
		if target is None:
			return None, None
		return target, (target.dir, target.name)

	def get_prev(self, start_from):
		parent, name = start_from
		dir = get_directory( parent )
		widget = dir.get_widget(name)
		target = widget.prev_inorder()
		if target is None:
			return None, None
		return target, (target.dir, target.name)
				

		
class DirectoryBrowser:
	palette = [
		('body', 'black', 'light gray'),
		('selected', 'black', 'dark green', ('bold','underline')),
		('focus', 'light gray', 'dark blue', 'standout'),
		('selected focus', 'yellow', 'dark cyan', 
				('bold','standout','underline')),
		('head', 'yellow', 'black', 'standout'),
		('foot', 'light gray', 'black'),
		('key', 'light cyan', 'black','underline'),
		('title', 'white', 'black', 'bold'),
		('dirmark', 'black', 'dark cyan', 'bold'),
		('flag', 'dark gray', 'light gray'),
		('error', 'dark red', 'light gray'),
		]
	
	footer_text = [
		('title', "Directory Browser"), "    ",
		('key', "UP"), ",", ('key', "DOWN"), ",",
		('key', "PAGE UP"), ",", ('key', "PAGE DOWN"),
		"  ",
		('key', "SPACE" ), "  ",
		('key', "+"), ",",
		('key', "-"), "  ",
		('key', "LEFT"), "  ",
		('key', "HOME"), "  ", 
		('key', "END"), "  ",
		('key', "Q"),
		]
	
	
	def __init__(self):
		cwd = os.getcwd()
		store_initial_cwd( cwd )
		self.listbox = urwid.ListBox( DirectoryWalker( cwd ) )
		self.listbox.offset_rows = 1
		self.header = urwid.Text( "" )
		self.footer = urwid.AttrWrap( urwid.Text( self.footer_text ),
			'foot')
		self.view = urwid.Frame( 
			urwid.AttrWrap( self.listbox, 'body' ), 
			header=urwid.AttrWrap(self.header, 'head' ), 
			footer=self.footer )

	def main(self):
		"""Run the program."""
		
		self.ui = urwid.curses_display.Screen()
		self.ui.register_palette( self.palette )
		self.ui.run_wrapper( self.run )
	
		# on exit, write the selected filenames to the console
		names = [escape_filename_sh(x) for x in get_selected_names()]
		print " ".join(names)

	def run(self):
		"""Handle user input and display updating."""
		
		size = self.ui.get_cols_rows()
		while 1:
			focus, _ign = self.listbox.body.get_focus()
			# update display of focus directory
			self.header.set_text( focus.dir )
			canvas = self.view.render( size, focus=1 )
			self.ui.draw_screen( size, canvas )
			keys = None
			while not keys: 
				keys = self.ui.get_input()
			for k in keys:
				if k == 'window resize':
					size = self.ui.get_cols_rows()
				elif k in ('q','Q'):
					return
				elif k == 'right':
					# right can behave like +
					k = "+"
				k = self.view.keypress( size, k )
				# k = unhandled key or None
				if k == 'left':
					self.move_focus_to_parent( size )
				elif k == '-':
					self.collapse_focus_parent( size )
				elif k == 'home':
					self.focus_home( size )
				elif k == 'end':
					self.focus_end( size )
					
	def collapse_focus_parent(self, size):
		"""Collapse parent directory."""
		
		widget, pos = self.listbox.body.get_focus()
		self.move_focus_to_parent( size )
		
		pwidget, ppos = self.listbox.body.get_focus()
		if widget.dir != pwidget.dir:
			self.view.keypress( size, "-")

	def move_focus_to_parent(self, size):
		"""Move focus to parent of widget in focus."""
		
		middle,top,bottom = self.listbox.calculate_visible( size )
		
		row_offset, focus_widget, focus_pos, focus_rows, cursor = middle
		trim_top, fill_above = top

		parent,name = os.path.split(focus_widget.dir)
		
		if parent == focus_widget.dir:
			# no root dir, choose first element instead
			self.focus_home( size )
			return
		
		for widget, pos, rows in fill_above:
			row_offset -= rows
			if pos == (parent,name):
				self.listbox.change_focus(size, pos, row_offset)
				return
		
		self.listbox.change_focus( size, (parent, name) )
		return 
		
	def focus_home(	self, size ):
		"""Move focus to very top."""
		
		dir = get_directory("/")
		widget = dir.get_first()
		parent, name = widget.dir, widget.name
		self.listbox.change_focus( size, (parent, name) )

	def focus_end( self, size ):
		"""Move focus to far bottom."""
		
		maxrow, maxcol = size
		dir = get_directory("/")
		widget = dir.get_last()
		parent, name = widget.dir, widget.name
		self.listbox.change_focus( size, (parent, name), maxrow-1 )






def main():
	DirectoryBrowser().main()




#######
# global cache of directory information
_dir_cache = {}

def get_directory(name):
	"""Return the Directory object for a given path.  Create if necessary."""
	
	if not _dir_cache.has_key(name):
		_dir_cache[name] = Directory(name)
	return _dir_cache[name]

def directory_cached(name):
	"""Return whether the directory is in the cache."""
	
	return _dir_cache.has_key(name)

def get_selected_names():
	"""Return a list of all filenames marked as selected."""
	
	l = []
	for d in _dir_cache.values():
		for w in d.widgets.values():
			if w.selected:
				l.append( os.path.join( w.dir, w.name ) )
	return l
			


######
# store path components of initial current working directory
_initial_cwd = []

def store_initial_cwd( name ):
	"""Store the initial current working directory path components."""
	
	global _initial_cwd
	_initial_cwd = name.split( dir_sep() )

def starts_expanded( name ):
	"""Return True if directory is a parent of initial cwd."""
	
	l = name.split( dir_sep() )
	if len(l) > len( _initial_cwd ):
		return False
	
	if l != _initial_cwd[:len(l)]:
		return False
	
	return True


def escape_filename_sh( name ):
	"""Return a hopefully safe shell-escaped version of a filename."""

	# check whether we have unprintable characters
	for ch in name: 
		if ord(ch) < 32: 
			# found one so use the ansi-c escaping
			return escape_filename_sh_ansic( name )
			
	# all printable characters, so return a double-quoted version
	name.replace('\\','\\\\')
	name.replace('"','\\"')
	name.replace('`','\\`')
	name.replace('$','\\$')
	return '"'+name+'"'


def escape_filename_sh_ansic( name ):
	"""Return an ansi-c shell-escaped version of a filename."""
	
	out =[]
	# gather the escaped characters into a list
	for ch in name:
		if ord(ch) < 32:
			out.append("\\x%02x"% ord(ch))
		elif ch == '\\':
			out.append('\\\\')
		else:
			out.append( ch )
			
	# slap them back together in an ansi-c quote  $'...'
	return "$'" + "".join(out) + "'"


def sensible_cmp( name_a, name_b ):
	"""Case insensitive compare with sensible numeric ordering.
	
	"blah7" < "BLAH08" < "blah9" < "blah10" """
	
	# ai, bi are indexes into name_a, name_b
	ai = bi = 0
	
	def next_atom( name, i ):
		"""Return the next 'atom' and the next index.
		
		An 'atom' is either a nonnegative integer or an uppercased 
		character used for defining sort order."""
		
		a = name[i].upper()
		i += 1
		if a.isdigit():
			while i < len(name) and name[i].isdigit():
				a += name[i]
				i += 1
			a = int(a)
		return a, i
		
	# compare one atom at a time
	while ai < len(name_a) and bi < len(name_b):
		a, ai = next_atom( name_a, ai )
		b, bi = next_atom( name_b, bi )
		if a < b: return -1
		if a > b: return 1
	
	# if all out of atoms to compare, do a regular cmp
	if ai == len(name_a) and bi == len(name_b): 
		return cmp(name_a,name_b)
	
	# the shorter one comes first
	if ai == len(name_a): return -1
	return 1


def dir_sep():
	"""Return the separator used in this os."""
	return getattr(os.path,'sep','/')


if __name__=="__main__": 
	main()
		
