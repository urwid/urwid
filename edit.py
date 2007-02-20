#!/usr/bin/python
#
# Urwid example lazy text editor suitable for tabbed and format=flowed text
#    Copyright (C) 2004-2007  Ian Ward
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
Urwid example lazy text editor suitable for tabbed and format=flowed text

Features:
- custom list walker for lazily loading text file

Usage:
edit.py <filename>

"""

import sys

import urwid
import urwid.raw_display


class LineWalker:
	"""ListWalker-compatible class for lazily reading file contents."""
	
	def __init__(self, name):
		self.file = open(name)
		self.lines = []
		self.focus = 0
	
	def get_focus(self): 
		return self._get_at_pos( self.focus )
	
	def set_focus(self, focus):
		self.focus = focus
	
	def get_next(self, start_from):
		return self._get_at_pos( start_from + 1 )
	
	def get_prev(self, start_from):
		return self._get_at_pos( start_from - 1 )

	def read_next_line(self):
		"""Read another line from the file."""
		
		next_line = self.file.readline()
		
		if not next_line or next_line[-1:] != '\n':
			# no newline on last line of file
			self.file = None
		else:
			# trim newline characters
			next_line = next_line[:-1]

		expanded = next_line.expandtabs()
		
		edit = urwid.Edit( "", expanded, allow_tab=True )
		edit.set_edit_pos(0)
		edit.original_text = next_line
		self.lines.append( edit )

		return next_line
		
	
	def _get_at_pos(self, pos):
		"""Return a widget for the line number passed."""
		
		if pos < 0:
			# line 0 is the start of the file, no more above
			return None, None
			
		if len(self.lines) > pos:
			# we have that line so return it
			return self.lines[pos], pos

		if self.file is None:
			# file is closed, so there are no more lines
			return None, None

		assert pos == len(self.lines), "out of order request?"

		self.read_next_line()
		
		return self.lines[-1], pos
	
	def split_focus(self):
		"""Divide the focus edit widget at the cursor location."""
		
		focus = self.lines[self.focus]
		pos = focus.edit_pos
		edit = urwid.Edit("",focus.edit_text[pos:], allow_tab=True )
		edit.original_text = ""
		focus.set_edit_text( focus.edit_text[:pos] )
		edit.set_edit_pos(0)
		self.lines.insert( self.focus+1, edit )

	def combine_focus_with_prev(self):
		"""Combine the focus edit widget with the one above."""

		above, ignore = self.get_prev(self.focus)
		if above is None:
			# already at the top
			return
		
		focus = self.lines[self.focus]
		above.set_edit_pos(len(above.edit_text))
		above.set_edit_text( above.edit_text + focus.edit_text )
		del self.lines[self.focus]
		self.focus -= 1

	def combine_focus_with_next(self):
		"""Combine the focus edit widget with the one below."""

		below, ignore = self.get_next(self.focus)
		if below is None:
			# already at bottom
			return
		
		focus = self.lines[self.focus]
		focus.set_edit_text( focus.edit_text + below.edit_text )
		del self.lines[self.focus+1]


class EditDisplay:
	palette = [
		('body','default', 'default'),
		('foot','dark cyan', 'dark blue', 'bold'),
		('key','light cyan', 'dark blue', 'underline'),
		]
		
	footer_text = ('foot', [
		"Text Editor    ",
		('key', "F5"), " save  ",
		('key', "F8"), " quit",
		])
	
	def __init__(self, name):
		self.save_name = name
		self.walker = LineWalker( name ) 
		self.listbox = urwid.ListBox( self.walker )
		self.footer = urwid.AttrWrap( urwid.Text( self.footer_text ),
			"foot")
		self.view = urwid.Frame( urwid.AttrWrap( self.listbox, 'body'),
			footer=self.footer )

	def main(self):
		self.ui = urwid.raw_display.Screen()
		self.ui.register_palette( self.palette )
		self.ui.run_wrapper( self.run )

	def run(self):
		self.ui.set_mouse_tracking()
		size = self.ui.get_cols_rows()
		while 1:
			canvas = self.view.render( size, focus=1 )
			self.ui.draw_screen( size, canvas )
			keys = None
			while not keys: 
				keys = self.ui.get_input()
			for k in keys:
				if urwid.is_mouse_event(k):
					event, button, col, row = k
					self.view.mouse_event( size, event,
						button, col, row, focus=True )
					continue
				if k == 'window resize':
					size = self.ui.get_cols_rows()
					continue
				elif k == "f5":
					self.save_file()
					continue
				elif k == "f8":
					return
				
				k = self.view.keypress( size, k )
				if k is not None:
					self.unhandled_keypress( size, k )
	
	def unhandled_keypress(self, size, k):
		"""Last resort for keypresses."""

		if k == "delete":
			# delete at end of line
			self.walker.combine_focus_with_next()
		elif k == "backspace":
			# backspace at beginning of line
			self.walker.combine_focus_with_prev()
		elif k == "enter":
			# start new line
			self.walker.split_focus()
			# move the cursor to the new line and reset pref_col
			self.view.keypress(size, "down")
			self.view.keypress(size, "home")


	def save_file(self):
		"""Write the file out to disk."""
		
		l = []
		walk = self.walker
		for edit in walk.lines:
			# collect the text already stored in edit widgets
			if edit.original_text.expandtabs() == edit.edit_text:
				l.append( edit.original_text )
			else:
				l.append( re_tab( edit.edit_text ) )
		
		# then the rest
		while walk.file is not None:
			l.append( walk.read_next_line() )
			
		# write back to disk
		outfile = open(self.save_name, "w")
		
		prefix = ""
		for line in l:
			outfile.write( prefix + line )
			prefix = "\n"

def re_tab( s ):
	"""Return a tabbed string from an expanded one."""
	l = []
	p = 0
	for i in range(8, len(s), 8):
		if s[i-2:i] == "  ":
			# collapse two or more spaces into a tab
			l.append( s[p:i].rstrip() + "\t" )
			p = i

	if p == 0:
		return s
	else:
		l.append(s[p:])
		return "".join(l)



def main():
	try:
		name = sys.argv[1]
		assert open( name, "a" )
	except:
		sys.stderr.write( __doc__ )
		return
	EditDisplay( name ).main()
	

if __name__=="__main__": 
	main()
