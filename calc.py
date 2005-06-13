#!/usr/bin/python
#
# Urwid advanced example column calculator application
#    Copyright (C) 2004-2005  Ian Ward
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
Urwid advanced example column calculator application

Features:
- multiple separate list boxes within columns
- custom edit widget for editing calculator cells
- custom parent widget for links to other columns
- custom list walker to show and hide cell results as required
- custom wrap and align modes for editing right-1 aligned numbers
- outputs commands that may be used to recreate expression on exit
"""

import urwid
import urwid.curses_display
import urwid.web_display

try: True # old python?
except: False, True = 0, 1

# use appropriate Screen class
if urwid.web_display.is_web_request():
	Screen = urwid.web_display.Screen
else:
	Screen = urwid.curses_display.Screen


def div_or_none(a,b):
	"""Divide a by b.  Return result or None on divide by zero."""
	if b == 0: 
		return None
	return a/b

# operators supported and the functions used to calculate a result
OPERATORS = {
	'+': (lambda a, b: a+b),
	'-': (lambda a, b: a-b),
	'*': (lambda a, b: a*b),
	'/': div_or_none,
	}

# the uppercase versions of keys used to switch columns
COLUMN_KEYS = list( "?ABCDEF" )

# these lists are used to determine when to display errors
EDIT_KEYS = OPERATORS.keys() + COLUMN_KEYS + ['backspace','delete']
MOVEMENT_KEYS = ['up','down','left','right','page up','page down']

# Event text
E_no_such_column = "Column %s does not exist."
E_no_more_columns = "Maxumum number of columns reached."
E_new_col_cell_not_empty = "Column must be started from an empty cell."
E_invalid_key = "Invalid key '%s'."
E_no_parent_column = "There is no parent column to return to."
E_cant_combine = "Cannot combine cells with sub-expressions."
E_invalid_in_parent_cell = "Cannot enter numbers into parent cell."
E_invalid_in_help_col = [
	"Help Column is in focus.  Press ", 
	('key',COLUMN_KEYS[1]),"-",('key',COLUMN_KEYS[-1]), 
	" to select another column."]


class CalcEvent:
	"""Events triggered by user input."""
	
	attr = 'event'
	
	def __init__(self, message):
		self.message = message
	
	def widget(self):
		"""Return a widget containing event information"""
		text = urwid.Text( self.message, 'center' )
		return urwid.AttrWrap( text, self.attr )

class ColumnDeleteEvent(CalcEvent):
	"""Sent when user wants to delete a column"""

	attr = 'confirm'

	def __init__(self, letter, from_parent=0):
		self.message = ["Press ", ('key',"BACKSPACE"),
			" again to confirm column removal."]
		self.letter = letter

class UpdateParentEvent:
	"""Sent when parent columns may need to be updated."""
	pass


class Cell:
	def __init__(self, op ):
		self.op = op
		self.is_top = op is None
		self.child = None
		self.setup_edit()
		self.result = urwid.Text("",'right -1','numeric -1')
	
	def show_result(self, next_cell):
		"""Return whether this widget should display its result.

		next_cell -- the cell following self or None"""
		
		if self.is_top: 
			return False
		if next_cell is None:
			return True
		if self.op == "+" and next_cell.op == "+":
			return False
		return True
		
	
	def setup_edit(self):
		"""Create the standard edit widget for this cell."""
		
		self.edit = urwid.IntEdit()
		if not self.is_top:
			self.edit.set_caption( self.op + " " )
		self.edit.set_align_mode('right -1')
		self.edit.set_wrap_mode('numeric -1')

	def get_value(self):
		"""Return the numeric value of the cell."""
		
		if self.child is not None:
			return self.child.get_result()
		else:
			return long("0"+self.edit.edit_text)
	
	def get_result(self):
		"""Return the numeric result of this cell's operation."""
		
		if self.is_top:
			return self.get_value()
		if self.result.text == "": 
			return None
		return long(self.result.text)

	def set_result(self, result):
		"""Set the numeric result for this cell."""
		
		if result == None:
			self.result.set_text("")
		else:
			self.result.set_text( "%d" %result )
	
	def become_parent(self, column, letter):
		"""Change the edit widget to a parent cell widget."""
		
		self.child = column
		self.edit = ParentEdit( self.op, letter )
	
	def remove_child(self):
		"""Change the edit widget back to a standard edit widget."""
		
		self.child = None
		self.setup_edit()

	def is_empty( self ):
		"""Return True if the cell is "empty"."""

		return self.child is None and self.edit.edit_text == ""


class ParentEdit(urwid.Edit):
	"""Edit widget modified to link to a child column"""
	
	def __init__(self, op, letter):
		"""Use the operator and letter of the child column as caption
		
		op -- operator or None
		letter -- letter of child column
		remove_fn -- function to call when user wants to remove child
		             function takes no parameters
		"""
		
		urwid.Edit.__init__(self)
		self.op = op
		self.set_letter( letter )
		self.set_align_mode('right -1')
		self.set_wrap_mode('numeric -1')
	
	def set_letter(self, letter):
		"""Set the letter of the child column for display."""
		
		self.letter = letter
		caption = "("+letter+")"
		if self.op is not None:
			caption = self.op+" "+caption
		self.set_caption(caption)
		
	def keypress(self, size, key):
		"""Disable usual editing, allow only removing of child""" 
		
		if key == "backspace":
			raise ColumnDeleteEvent(self.letter, from_parent=True)
		elif key in list("0123456789"):
			raise CalcEvent, E_invalid_in_parent_cell
		else:
			return key
		

class CellWalker:
	def __init__(self, content ):
		self.content = content
		self.focus = (0,0)
		# everyone can share the same divider widget
		self.div = urwid.Divider("-")

	def get_cell(self, i):
		if i < 0 or i >= len(self.content):
			return None
		else:
			return self.content[i]

	def _get_at_pos(self, pos):
		i, sub = pos
		assert sub in (0,1,2)
		if i < 0 or i >= len(self.content):
			return None, None
		if sub == 0:
			edit = self.content[i].edit
			return urwid.AttrWrap(edit, 'edit', 'editfocus'), pos
		elif sub == 1:
			return self.div, pos
		else:
			return self.content[i].result, pos
	
	def get_focus(self):
		return self._get_at_pos(self.focus)
	
	def set_focus(self, focus):
		self.focus = focus
	
	def get_next(self, start_from):
		i, sub = start_from
		assert sub in (0,1,2)
		if sub == 0:
			show_result = self.content[i].show_result(
				self.get_cell(i+1))
			if show_result:
				return self._get_at_pos( (i, 1) )
			else:
				return self._get_at_pos( (i+1, 0) )
		elif sub == 1:
			return self._get_at_pos( (i, 2) )
		else:
			return self._get_at_pos( (i+1, 0) )
	
	def get_prev(self, start_from):
		i, sub = start_from
		assert sub in (0,1,2)
		if sub == 0:
			if i == 0: return None, None
			show_result = self.content[i-1].show_result(
				self.content[i])
			if show_result:
				return self._get_at_pos( (i-1, 2) )
			else:
				return self._get_at_pos( (i-1, 0) )
		elif sub == 1:
			return self._get_at_pos( (i, 0) )
		else:
			return self._get_at_pos( (i, 1) )
	
			
class CellColumn( urwid.BoxWidget ):
	def __init__(self, letter):
		self.content = [ Cell( None ) ]
		self.walker = CellWalker( self.content )
		self.listbox = urwid.ListBox( self.walker )
		self.set_letter( letter )
	
	def set_letter(self, letter):
		"""Set the column header with letter."""
		
		self.letter = letter
		header = urwid.AttrWrap(
			urwid.Text( ["Column ",('key',letter)],
			'right -1','numeric -1'), 'colhead' )
		self.frame = urwid.Frame( self.listbox, header )
			
	def render(self, (maxcol, maxrow), **args):
		return self.frame.render( (maxcol, maxrow), **args )

	def keypress(self, size, key):
		key = self.frame.keypress( size, key)
		if key is None: 
			changed = self.update_results()
			if changed:
				raise UpdateParentEvent()
			return
		
		f, (i, sub) = self.walker.get_focus()
		if sub != 0: 
			# f is not an edit widget
			return key
		if OPERATORS.has_key(key):
			# move trailing text to new cell below
			edit = self.walker.get_cell(i).edit
			cursor_pos = edit.edit_pos
			tail = edit.edit_text[cursor_pos:]
			edit.set_edit_text( edit.edit_text[:cursor_pos] )
			
			new_cell = Cell( key )
			new_cell.edit.set_edit_text( tail )
			self.content[i+1:i+1] = [new_cell]
			
			changed = self.update_results()
			self.move_focus_next( size )
			self.content[i+1].edit.set_edit_pos(0)
			if changed:
				raise UpdateParentEvent()
			return
			
		elif key == 'backspace':
			# unhandled backspace, we're at beginning of number
			# append current number to cell above, removing operator
			above = self.walker.get_cell(i-1)
			if above is None:
				# we're the first cell
				raise ColumnDeleteEvent( self.letter, 
					from_parent=False )
			
			edit = self.walker.get_cell(i).edit
			# check that we can combine
			if above.child is not None:
				# cell above is parent
				if edit.edit_text:
					# ..and current not empty, no good
					raise CalcEvent, E_cant_combine
				above_pos = 0
			else:	
				# above is normal number cell
				above_pos = len(above.edit.edit_text)
				above.edit.set_edit_text( above.edit.edit_text +
					edit.edit_text )

			self.move_focus_prev( size )
			self.content[i-1].edit.set_edit_pos(above_pos)
			del self.content[i]
			changed = self.update_results()
			if changed:
				raise UpdateParentEvent()
			return
		
		elif key == 'delete':
			# pull text from next cell into current
			cell = self.walker.get_cell(i)
			below = self.walker.get_cell(i+1)
			if cell.child is not None:
				# this cell is a parent
				raise CalcEvent, E_cant_combine
			if below is None:
				# nothing below
				return key
			if below.child is not None:
				# cell below is a parent
				raise CalcEvent, E_cant_combine
			
			edit = self.walker.get_cell(i).edit
			edit.set_edit_text( edit.edit_text +
				below.edit.edit_text )

			del self.content[i+1]
			changed = self.update_results()
			if changed:
				raise UpdateParentEvent()
			return
		return key

	
	def move_focus_next(self, size):
		f, (i, sub) = self.walker.get_focus()
		assert i<len(self.content)-1
		
		ni = i
		while ni == i:
			self.frame.keypress(size, 'down')
			nf, (ni, nsub) = self.walker.get_focus()
	
	def move_focus_prev(self, size):
		f, (i, sub) = self.walker.get_focus()
		assert i>0
		
		ni = i
		while ni == i:
			self.frame.keypress(size, 'up')
			nf, (ni, nsub) = self.walker.get_focus()
			
			
	def update_results( self, start_from=None ):
		"""Update column.  Return True if final result changed.
		
		start_from -- Cell to start updating from or None to start from
		              the current focus (default None)
		"""
		
		if start_from is None:
			f, (i, sub) = self.walker.get_focus()
		else:
			i = self.content.index(start_from)
			if i == None: return False
		
		focus_cell = self.walker.get_cell(i)
		
		if focus_cell.is_top:
			x = focus_cell.get_value()
			last_op = None
		else:	
			last_cell = self.walker.get_cell(i-1)
			x = last_cell.get_result()
			
			if x is not None and focus_cell.op is not None:
				x = OPERATORS[focus_cell.op]( x, 
					focus_cell.get_value() )
			focus_cell.set_result(x)
		
		for cell in self.content[i+1:]:
			if cell.op is None:
				x = None
			if x is not None:
				x = OPERATORS[cell.op]( x, cell.get_value() )
			if cell.get_result() == x:
				return False
			cell.set_result(x)

		return True

	
	def create_child( self, letter ):
		"""Return (parent cell,child column) or None,None on failure."""
		f, (i, sub) = self.walker.get_focus()
		if sub != 0: 
			# f is not an edit widget
			return None, None

		cell = self.walker.get_cell(i)
		if cell.child is not None:
			raise CalcEvent, E_new_col_cell_not_empty
		if cell.edit.edit_text:
			raise CalcEvent, E_new_col_cell_not_empty

		child = CellColumn( letter )
		cell.become_parent( child, letter )

		return cell, child

	def is_empty( self ):
		"""Return True if this column is empty."""

		return len(self.content)==1 and self.content[0].is_empty()

	
	def get_expression(self):
		"""Return the expression as a printable string."""
		
		l = []
		for c in self.content:
			if c.op is not None: # only applies to first cell
				l.append(c.op)
			if c.child is not None:
				l.append("("+c.child.get_expression()+")")
			else:
				l.append("%d"%c.get_value())
				
		return "".join(l)

	def get_result(self):
		"""Return the result of the last cell in the column."""
		
		return self.content[-1].get_result()
		

		

class HelpColumn(urwid.BoxWidget):
	help_text = [
		('title', "Column Calculator"),
		"",
		[ "Numbers: ", ('key', "0"), "-", ('key', "9") ],
		"" ,
		[ "Operators: ",('key', "+"), ", ", ('key', "-"), ", ",
			('key', "*"), " and ", ('key', "/")],
		"",
		[ "Editing: ", ('key', "BACKSPACE"), " and ",('key', "DELETE")],
		"",
		[ "Movement: ", ('key', "UP"), ", ", ('key', "DOWN"), ", ",
			('key', "LEFT"), ", ", ('key', "RIGHT"), ", ",
			('key', "PAGE UP"), " and ", ('key', "PAGE DOWN") ],
		"",
		[ "Sub-expressions: ", ('key', "("), " and ", ('key', ")") ],
		"",
		[ "Columns: ", ('key', COLUMN_KEYS[0]), " and ", 
			('key',COLUMN_KEYS[1]), "-", 
			('key',COLUMN_KEYS[-1]) ],
		"",
		[ "Exit: ", ('key', "Q") ],
		"",
		"",
		["Column Calculator does operations in the order they are ",
			"typed, not by following usual precedence rules.  ",
			"If you want to calculate ", ('key', "12 - 2 * 3"), 
			" with the multiplication happening before the ",
			"subtraction you must type ", 
			('key', "12 - (2 * 3)"), " instead."],
		]
		
	def __init__(self):
		self.head = urwid.AttrWrap(
			urwid.Text(["Help Column ", ('key',"?")],
				'right -1','numeric -1'),
			'help')
		self.foot = urwid.AttrWrap( 
			urwid.Text(["[text continues.. press ",
			('key',"?"), " then scroll]"]), 'helpnote' )
		self.items = [urwid.Text(x) for x in self.help_text]
		self.listbox = urwid.ListBox( self.items )
		self.body = urwid.AttrWrap( self.listbox, 'help' )
		self.frame = urwid.Frame( self.body, header=self.head)
	
	def render( self, (maxcol, maxrow), **opts ):
		head_rows = self.head.rows( (maxcol,) )
		if "bottom" in self.listbox.ends_visible( 
			(maxcol, maxrow-head_rows) ):
			self.frame.footer = None
		else:
			self.frame.footer = self.foot

		return self.frame.render( (maxcol, maxrow), ** opts )
	
	def keypress( self, size, key ):
		return self.frame.keypress( size, key )
		

class CalcDisplay:
	palette = [
		('body','white', 'dark blue'),
		('edit','yellow', 'dark blue'),
		('editfocus','yellow','dark cyan', 'bold'),
		('key','dark cyan', 'light gray', ('standout','underline')),
		('title', 'white', 'light gray', ('bold','standout')),
		('help', 'black', 'light gray', 'standout'),
		('helpnote', 'dark green', 'light gray'),
		('colhead', 'black', 'light gray', 'standout'),
		('event', 'light red', 'black', 'standout'),
		('confirm', 'yellow', 'black', 'bold'),
		]
	
	def __init__(self):
		self.col_list = [ HelpColumn(), CellColumn("A") ]
		self.columns = urwid.Columns( self.col_list, 1 )
		self.columns.set_focus_column( 1 )
		self.view = urwid.AttrWrap( self.columns, 'body' )
		self.col_link = {}

	def main(self):
		self.ui = Screen()
		self.ui.register_palette( self.palette )
		self.ui.run_wrapper( self.run )

		# on exit write the formula and the result to the console
		expression, result = self.get_expression_result()
		print "Paste this expression into a new Column Calculator session to continue editing:"
		print expression
		print "Result:", result

	def run(self):
		"""Update screen and accept user input."""
		size = self.ui.get_cols_rows()
		self.event = None
		while 1:
			# draw the screen
			view = self.view
			if self.event is not None:
				# show the event too
				view = urwid.Frame( view, 
					footer=self.event.widget() )
			canvas = view.render( size, focus=1 )
			self.ui.draw_screen( size, canvas )
			
			# wait until we get some input
			keys = None
			while not keys: 
				# this call returns None when it times out
				keys = self.ui.get_input()
				
			# handle each key one at a time
			for k in keys:
				if k == 'window resize':
					# read the new screen size
					size = self.ui.get_cols_rows()
					continue
					
				elif k in ('q','Q'):
					# exit main loop
					return
				
				# handle other keystrokes
				try:
					self.wrap_keypress( size, k )
					self.event = None
				except CalcEvent, e:
					self.event = e
			
	def wrap_keypress(self, size, key):
		"""Handle confirmation and throw event on bad input."""
		
		try:
			key = self.keypress(size, key)
			
		except ColumnDeleteEvent, e:
			if e.letter == COLUMN_KEYS[1]:
				# cannot delete the first column, ignore key
				return
			
			if not self.column_empty( e.letter ):
				# need to get two in a row, so check last event
				if not isinstance(self.event,ColumnDeleteEvent):
					# ask for confirmation
					raise e
			self.delete_column(e.letter)
			
		except UpdateParentEvent, e:
			self.update_parent_columns()
			return
		
		if key is None:
			return

		if self.columns.get_focus_column() == 0:
			if key not in ('up','down','page up','page down'):
				raise CalcEvent, E_invalid_in_help_col
		
		if key not in EDIT_KEYS and key not in MOVEMENT_KEYS:
			raise CalcEvent, E_invalid_key % key.upper()
		
	def keypress(self, size, key):
		"""Handle a keystroke."""
		
		# let the view try to handle it first
		key = self.view.keypress( size, key )
		if key is None: 
			return
	
		if key.upper() in COLUMN_KEYS:
			# column switch
			i = COLUMN_KEYS.index(key.upper())
			if i >= len( self.col_list ): 
				raise CalcEvent, E_no_such_column % key.upper()
			self.columns.set_focus_column( i )
			return
		elif key == "(":
			# open a new column
			if len( self.col_list ) >= len(COLUMN_KEYS):
				raise CalcEvent, E_no_more_columns
			i = self.columns.get_focus_column()
			if i == 0: 
				# makes no sense in help column
				return key
			col = self.col_list[i]
			new_letter = COLUMN_KEYS[len(self.col_list)]
			parent, child = col.create_child( new_letter )
			if child is None:
				# something invalid in focus
				return key
			self.col_list.append(child)
			self.set_link( parent, col, child )
			self.columns.set_focus_column(len(self.col_list)-1)
		
		elif key == ")":
			i = self.columns.get_focus_column()
			if i == 0:
				# makes no sense in help column
				return key
			col = self.col_list[i]
			parent, pcol = self.get_parent( col )
			if parent is None: 
				# column has no parent
				raise CalcEvent, E_no_parent_column
			
			new_i = self.col_list.index( pcol )
			self.columns.set_focus_column( new_i )
		else:
			return key
	
	def set_link( self, parent, pcol, child ):
		"""Store the link between a parent cell and child column.
		
		parent -- parent Cell object
		pcol -- CellColumn where parent resides
		child -- child CellColumn object"""

		self.col_link[ child ] = parent, pcol
	
	def get_parent( self, child ):
		"""Return the parent and parent column for a given column."""

		return self.col_link.get( child, (None,None) )
	
	def column_empty(self, letter):
		"""Return True if the column passed is empty."""
		
		i = COLUMN_KEYS.index(letter)
		col = self.col_list[i]
		return col.is_empty()
		
	
	def delete_column(self, letter):
		"""Delete the column with the given letter."""
		
		i = COLUMN_KEYS.index(letter)
		col = self.col_list[i]
		
		parent, pcol = self.get_parent( col )

		f = self.columns.get_focus_column()
		if f == i:
			# move focus to the parent column
			f = self.col_list.index(pcol)
			self.columns.set_focus_column(f)
		
		parent.remove_child()
		pcol.update_results(parent)
		del self.col_list[i]
		
		# delete children of this column
		keep_right_cols = []
		remove_cols = [col]
		for rcol in self.col_list[i:]:
			parent, pcol = self.get_parent( rcol )
			if pcol in remove_cols:
				remove_cols.append( rcol )
			else:
				keep_right_cols.append( rcol )
		for rc in remove_cols:
			# remove the links
			del self.col_link[rc]
		# keep only the non-children
		self.col_list[i:] = keep_right_cols		

		# fix the letter assigmnents
		for j in range(i, len(self.col_list)):
			col = self.col_list[j]
			# fix the column heading
			col.set_letter( COLUMN_KEYS[j] )
			parent, pcol = self.get_parent( col )
			# fix the parent cell
			parent.edit.set_letter( COLUMN_KEYS[j] )

	def update_parent_columns(self):
		"Update the parent columns of the current focus column."

		f = self.columns.get_focus_column()
		col = self.col_list[f]
		while 1:
			parent, pcol = self.get_parent(col)
			if pcol is None: 
				return

			changed = pcol.update_results( start_from = parent )
			if not changed: 
				return
			col = pcol
			
			
	def get_expression_result(self):
		"""Return (expression, result) as strings."""
		
		col = self.col_list[1]
		return col.get_expression(), "%d"%col.get_result()
			

def wrap_numeric_less1( text, width, wrap_mode ):
	"""Return line breaks suitable for right justified number editing.
	
	choose line breaks so that wrapped numbers leave space on the first
	line instead of the last line with one extra space on the last line
	to leave room for a cursor at the end"""
	
	lt = len(text)
	return range( lt%width +1, lt, width )

def align_right_less1( text, width, b, wrap_mode, align_mode ):
	"""Return alignment suitable for right justified number editing.

	leave room for a cursor at the end, only works as intended when used
	with wrap_numeric_less1
	"""
	
	return urwid.util.calculate_alignment(text+" ",width,b,'clip','right')
	
	
		
		
def main():
	"""Launch Column Calculator."""
	urwid.web_display.set_preferences("Column Calculator")
	# try to handle short web requests quickly
	if urwid.web_display.handle_short_request():
		return
	
	urwid.util.register_wrap_mode('numeric -1', wrap_numeric_less1 )
	urwid.util.register_align_mode('right -1', align_right_less1 )
	CalcDisplay().main()

if '__main__'==__name__ or urwid.web_display.is_web_request():
	main()
