#!/usr/bin/python
#
# Urwid example fibonacci sequence viewer / unbounded data demo
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
Urwid example fibonacci sequence viewer / unbounded data demo

Features:
- custom list walker class for browsing infinite set
- custom wrap mode "numeric" for wrapping numbers to right and bottom
"""

import urwid
import urwid.curses_display

class FibonacciWalker:
	"""ListWalker-compatible class for browsing fibonacci set.
	
	positions returned are (value at position-1, value at poistion) tuples.
	"""
	
	def __init__(self):
		self.focus = (0,1)
	
	def _get_at_pos(self, pos):
		"""Return a widget and the position passed."""
		
		# Generating widgets this way does not allow the line
		# translations to be cached and would be inefficient if the 
		# 'numeric' align mode wasn't so simple (no searching in the 
		# text the way the other modes do)  
		return urwid.Text("%d"%pos[1], 'right', 'numeric'), pos
	
	def get_focus(self): 
		return self._get_at_pos( self.focus )
	
	def set_focus(self, focus):
		self.focus = focus
	
	def get_next(self, start_from):
		a, b = start_from
		focus = b, a+b
		return self._get_at_pos( focus )
	
	def get_prev(self, start_from):
		a, b = start_from
		focus = b-a, a
		return self._get_at_pos( focus )

class FibonacciDisplay:
	palette = [
		('body','black','dark cyan', 'standout'),
		('foot','light gray', 'black'),
		('key','light cyan', 'black', 'underline'),
		('title', 'white', 'black',),
		]
		
	footer_text = [
		('title', "Fibonacci Set Viewer"), "    ",
		('key', "UP"), ", ", ('key', "DOWN"), ", ",
		('key', "PAGE UP"), " and ", ('key', "PAGE DOWN"),
		" move view  ",
		('key', "Q"), " exits",
		]
	
	def __init__(self):
		self.listbox = urwid.ListBox( FibonacciWalker() )
		self.footer = urwid.AttrWrap( urwid.Text( self.footer_text ),
			'foot')
		self.view = urwid.Frame( urwid.AttrWrap( self.listbox, 'body'),
			footer=self.footer )

	def main(self):
		self.ui = urwid.curses_display.Screen()
		self.ui.register_palette( self.palette )
		self.ui.run_wrapper( self.run )

	def run(self):
		size = self.ui.get_cols_rows()
		while 1:
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
				self.view.keypress( size, k )




def main():
	urwid.util.register_wrap_mode('numeric', wrap_numeric)
	FibonacciDisplay().main()
	


def wrap_numeric( text, width, wrap_mode ):
	"""Return line breaks suitable for right justified numbers."""
	
	lt = len(text)
	if lt % width:
		return range( lt%width, lt, width )
	else:
		return range( width, lt, width )
		

if __name__=="__main__": 
	main()
