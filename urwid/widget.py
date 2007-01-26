#!/usr/bin/python
#
# Urwid basic widget classes
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

import string

from util import *
from canvas import *

try: sum # old python?
except: sum = lambda l: reduce(lambda a,b: a+b, l, 0)

class FlowWidget(object):
	"""
	base class of widgets
	"""
	def selectable(self):
		"""Return False.  Not selectable by default."""
		return False
	
	def rows(self, (maxcol,), focus=False):
		"""
		All flow widgets must implement this function.
		"""
		raise NotImplementedError()

	def render(self, (maxcol,), focus=False):
		"""
		All widgets must implement this function.
		"""
		raise NotImplementedError()


class BoxWidget(object):
	"""
	base class of width and height constrained widgets such as
	the top level widget attached to the display object
	"""
	def selectable(self):
		"""Return True.  Selectable by default."""
		return True
	
	def render(self, size, focus=False):
		"""
		All widgets must implement this function.
		"""
		raise NotImplementedError()
	

def fixed_size(size):
	"""
	raise ValueError if size != ().
	
	Used by FixedWidgets to test size parameter.
	"""
	if size != ():
		raise ValueError("FixedWidget takes only () for size." \
			"passed: %s" % `size`)

class FixedWidget(object):
	def selectable(self):
		"""Return False.  Not selectable by default."""
		return False

	def render(self, size, focus=False):
		"""
		All widgets must implement this function.
		"""
		raise NotImplementedError()
	
	def pack(self, size=None, focus=False):
		"""
		All fixed widgets must implement this function.
		"""
		raise NotImplementedError()

class Divider(FlowWidget):
	"""
	Horizontal divider widget
	"""
	def __init__(self,div_char=" ",top=0,bottom=0):
		"""
		div_char -- character to repeat across line
		top -- number of blank lines above
		bottom -- number of blank lines below
		"""
		self.div_char = div_char
		self.top = top
		self.bottom = bottom
		
	
	def rows(self,(maxcol,), focus=False ):
		"""Return the number of lines that will be rendered."""
		return self.top + 1 + self.bottom
	
	def render(self,(maxcol,), focus=False ):
		"""Render the divider as a canvas and return it."""
		canv = CanvasCache.fetch(self, (maxcol,), False)
		if canv:
			return canv

		canv = SolidCanvas(self.div_char, maxcol, 1)
		if self.top or self.bottom:
			old_canv = canv
			canv = CompositeCanvas(canv)
			# HACK to keep a reference to the CompositeCanvas
			old_canv.keep_alive_link = canv 
			canv.pad_trim_top_bottom(self.top, self.bottom)

		CanvasCache.store(self, (maxcol,), False, canv)
		return canv
	

class SolidFill(BoxWidget):
	def __init__(self,fill_char=" "):
		"""
		fill_char -- character to fill area with
		"""
		self.fill_char = fill_char
	
	def render(self,(maxcol,maxrow), focus=False ):
		"""Render the Fill as a canvas and return it."""
		canv = CanvasCache.fetch(self, (maxcol,maxrow), False)
		if canv:
			return canv

		canv = SolidCanvas(self.fill_char, maxcol, maxrow)

		CanvasCache.store(self, (maxcol,maxrow), False, canv)
		return canv
	
	def selectable(self):
		"""Not selectable."""
		return False
	
class TextError(Exception):
	pass

class Text(FlowWidget):
	"""
	a horizontally resizeable text widget
	"""
	def __init__(self,markup, align='left', wrap='space', layout=None):
		"""
		markup -- content of text widget, one of:
			plain string -- string is displayed
			( attr, markup2 ) -- markup2 is given attribute attr
			[ markupA, markupB, ... ] -- list items joined together
		align -- align mode for text layout
		wrap -- wrap mode for text layout
		layout -- layout object to use, defaults to StandardTextLayout
		"""
		self._cache_maxcol = None
		self.set_text(markup)
		self.set_layout(align, wrap, layout)
	
	def invalidate(self):
		self._cache_maxcol = None
		CanvasCache.invalidate(self)

	def set_text(self,markup):
		"""Set content of text widget."""
		self.text, self.attrib = decompose_tagmarkup(markup)
		self.invalidate()

	def get_text(self):
		"""
		Returns (text, attributes).
		
		text -- complete string content of text widget
		attributes -- run length encoded attributes for text
		"""
		return self.text, self.attrib

	def set_align_mode(self, mode):
		"""
		Set text alignment / justification.  
		
		Valid modes for StandardTextLayout are: 
			'left', 'center' and 'right'
		"""
		if not self.layout.supports_align_mode(mode):
			raise TextError("Alignment mode %s not supported."%
				`mode`)
		self.align_mode = mode
		self.invalidate()

	def set_wrap_mode(self, mode):
		"""
		Set wrap mode.  
		
		Valid modes for StandardTextLayout are :
			'any'	: wrap at any character
			'space'	: wrap on space character
			'clip'	: truncate lines instead of wrapping
		"""
		if not self.layout.supports_wrap_mode(mode):
			raise TextError("Wrap mode %s not supported"%`mode`)
		self.wrap_mode = mode
		self.invalidate()

	def set_layout(self, align, wrap, layout=None):
		"""
		Set layout object, align and wrap modes.
		
		align -- align mode for text layout
		wrap -- wrap mode for text layout
		layout -- layout object to use, defaults to StandardTextLayout
		"""
		if layout is None:
			layout = default_layout
		self.layout = layout
		self.set_align_mode( align )
		self.set_wrap_mode( wrap )

	def render(self,(maxcol,), focus=False):
		"""
		Render contents with wrapping and alignment.  Return canvas.
		"""
		canv = CanvasCache.fetch(self, (maxcol,), False)
		if canv:
			return canv

		text, attr = self.get_text()
		trans = self.get_line_translation( maxcol, (text,attr) )
		canv = apply_text_layout( text, attr, trans, maxcol )
		
		CanvasCache.store(self, (maxcol,), False, canv)
		return canv

	def rows(self,(maxcol,), focus=False):
		"""Return the number of rows the rendered text spans."""
		return len(self.get_line_translation(maxcol))

	def get_line_translation(self, maxcol, ta=None):
		"""Return layout structure for mapping self.text to a canvas.
		"""
		# uses cached translation if available.  If set_text is not
		# used (eg. in subclass) set self._cache_maxcol to None
		# before calling this method.
		
		if not self._cache_maxcol or self._cache_maxcol != maxcol:
			self._update_cache_translation(maxcol, ta)
		return self._cache_translation

	def _update_cache_translation(self,maxcol, ta):
		if ta:
			text, attr = ta
		else:
			text, attr = self.get_text()
		self._cache_maxcol = maxcol
		self._cache_translation = self._calc_line_translation(
			text, maxcol )
	
	def _calc_line_translation(self, text, maxcol ):
		return self.layout.layout(
			text, self._cache_maxcol, 
			self.align_mode, self.wrap_mode )
	
	def pack(self, size=None, focus=False):
		"""
		Return the number of screen columns required for this Text
		widget to be displayed without wrapping or clipping, as a 
		single element tuple.

		size -- None for unlimited screen columns or (maxcol,) to
		        specify a maximum column size
		"""
		text, attr = self.get_text()
		
		if size is not None:
			(maxcol,) = size
			if not hasattr(self.layout, "pack"):
				return size
			trans = self.get_line_translation( maxcol, (text,attr))
			cols = self.layout.pack( maxcol, trans )
			return (cols,)
	
		i = 0
		cols = 0
		while i < len(text):
			j = text.find('\n', i)
			if j == -1:
				j = len(text)
			c = calc_width(text, i, j)
			if c>cols:
				cols = c
			i = j+1
		return (cols,)
		

class Edit(Text):
	"""Text edit widget"""
	
	def valid_char(self, ch):
		"""Return true for printable characters."""
		return is_wide_char(ch,0) or (len(ch)==1 and ord(ch) >= 32)
	
	def selectable(self): return True

	def __init__(self, caption = "", edit_text = "", multiline = False,
			align = 'left', wrap = 'space', allow_tab = False,
			edit_pos = None, layout=None):
		"""
		caption -- markup for caption preceeding edit_text
		edit_text -- text string for editing
		multiline -- True: 'enter' inserts newline  False: return it
		align -- align mode
		wrap -- wrap mode
		allow_tab -- True: 'tab' inserts 1-8 spaces  False: return it
		edit_pos -- initial position for cursor, None:at end
		layout -- layout object
		"""
		
		Text.__init__(self,"", align, wrap, layout)
		assert type(edit_text)==type("") or type(edit_text)==type(u"")
		self.multiline = multiline
		self.allow_tab = allow_tab
		self.edit_pos = 0
		self.set_caption(caption)
		self.set_edit_text(edit_text)
		if edit_pos is None:
			edit_pos = len(edit_text)
		self.set_edit_pos(edit_pos)
		self._shift_view_to_cursor = False
	
	def get_text(self):
		"""get_text() -> text, attributes
		
		text -- complete text of caption and edit_text
		attributes -- run length encoded attributes for text
		"""
		return self.caption + self.edit_text, self.attrib
	
	def get_pref_col(self, (maxcol,)):
		"""Return the preferred column for the cursor, or the
		current cursor x value."""
		pref_col, then_maxcol = self.pref_col_maxcol
		if then_maxcol != maxcol:
			return self.get_cursor_coords((maxcol,))[0]
		else:
			return pref_col
	
	def update_text(self):
		"""Deprecated.  Use set_caption and/or set_edit_text instead.
		
		Make sure any cached line translation is not reused."""
		self.invalidate()

	def set_caption(self, caption):
		"""Set the caption markup for this widget."""
		self.caption, self.attrib = decompose_tagmarkup(caption)
		self.invalidate()
	
	def set_edit_pos(self, pos):
		"""Set the cursor position with a self.edit_text offset."""
		assert pos >= 0 and pos <= len(self.edit_text), "out of range"
		self.highlight = None
		self.pref_col_maxcol = None, None
		self.edit_pos = pos
	
	def set_edit_text(self, text):
		"""Set the edit text for this widget."""
		self.highlight = None
		self.edit_text = text
		if self.edit_pos > len(text):
			self.edit_pos = len(text)
		self.invalidate()

	def get_edit_text(self):
		"""Return the edit text for this widget."""
		return self.edit_text

	def insert_text(self, text):
		"""Insert text at the cursor position and update cursor."""
		p = self.edit_pos
		self.set_edit_text( self.edit_text[:p] + text + 
			self.edit_text[p:] )
		self.set_edit_pos( self.edit_pos + len(text))
	
	def keypress(self,(maxcol,),key):
		"""Handle editing keystrokes, return others."""

		p = self.edit_pos
		if self.valid_char(key):
			self._delete_highlighted()
			if type(key) == type(u""):
				key = key.encode("utf-8")
			self.insert_text( key )
			
		elif key=="tab" and self.allow_tab:
			self._delete_highlighted() 
			key = " "*(8-(self.edit_pos%8))
			self.insert_text( key )

		elif key=="enter" and self.multiline:
			self._delete_highlighted() 
			key = "\n"
			self.insert_text( key )

		elif key=="left":
			if p==0: return key
			p = move_prev_char(self.edit_text,0,p)
			self.set_edit_pos(p)
		
		elif key=="right":
			if p >= len(self.edit_text): return key
			p = move_next_char(self.edit_text,p,len(self.edit_text))
			self.set_edit_pos(p)
		
		elif key in ("up","down"):
			self.highlight = None
			
			x,y = self.get_cursor_coords((maxcol,))
			pref_col = self.get_pref_col((maxcol,))
			assert pref_col is not None
			#if pref_col is None: 
			#	pref_col = x

			if key == "up": y -= 1
			else:		y += 1

			if not self.move_cursor_to_coords((maxcol,),pref_col,y):
				return key
		
		elif key=="backspace":
			self._delete_highlighted()
			self.pref_col_maxcol = None, None
			if p == 0: return key
			p = move_prev_char(self.edit_text,0,p)
			self.set_edit_text( self.edit_text[:p] + 
				self.edit_text[self.edit_pos:] )
			self.set_edit_pos( p )

		elif key=="delete":
			self._delete_highlighted()
			self.pref_col_maxcol = None, None
			if p >= len(self.edit_text):
				return key
			p = move_next_char(self.edit_text,p,len(self.edit_text))
			self.set_edit_text( self.edit_text[:self.edit_pos] + 
				self.edit_text[p:] )
		
		elif key in ("home", "end"):
			self.highlight = None
			self.pref_col_maxcol = None, None
			
			x,y = self.get_cursor_coords((maxcol,))
			
			if key == "home":
				self.move_cursor_to_coords((maxcol,),'left',y)
			else:
				self.move_cursor_to_coords((maxcol,),'right',y)
			return
			
			
		else:
			# key wasn't handled
			return key

	def move_cursor_to_coords(self, (maxcol,), x, y):
		"""Set the cursor position with (x,y) coordinates.

		Returns True if move succeeded, False otherwise.
		"""
		trans = self.get_line_translation(maxcol)
		top_x, top_y = self.position_coords(maxcol, 0)
		if y < top_y or y >= len(trans):
			return False

		pos = calc_pos( self.get_text()[0], trans, x, y )
		e_pos = pos - len(self.caption)
		if e_pos < 0: e_pos = 0
		if e_pos > len(self.edit_text): e_pos = len(self.edit_text)
		self.edit_pos = e_pos
		self.pref_col_maxcol = x, maxcol
		return True

	def mouse_event(self, (maxcol,), event, button, x, y, focus):
		"""
		Move the cursor to the location clicked for button 1.
		"""
		if button==1:
			return self.move_cursor_to_coords( (maxcol,), x, y )


	def _delete_highlighted(self):
		"""
		Delete all highlighted text and update cursor position, if any
		text is highlighted.
		"""
		if not self.highlight: return
		start, stop = self.highlight
		btext, etext = self.edit_text[:start], self.edit_text[stop:]
		self.set_edit_text( btext + etext )
		self.edit_pos = start
		self.highlight = None
		
		
	def render(self,(maxcol,), focus=False):
		""" 
		Render edit widget and return canvas.  Include cursor when in
		focus.
		"""
		
		self._shift_view_to_cursor = not not focus # force bool
		
		canv = Text.render(self,(maxcol,))
		if focus:
			canv.cursor = self.get_cursor_coords((maxcol,))
		else:
			canv.cursor = None
		# .. will need to FIXME if I want highlight to work again
		#if self.highlight:
		#	hstart, hstop = self.highlight_coords()
		#	d.coords['highlight'] = [ hstart, hstop ]
		return canv
	
	def get_line_translation(self, maxcol, ta=None ):
		trans = Text.get_line_translation(self, maxcol, ta)
		if not self._shift_view_to_cursor: 
			return trans
		
		text, ignore = self.get_text()
		x,y = calc_coords( text, trans, 
			self.edit_pos + len(self.caption) )
		if x < 0:
			return ( trans[:y]
				+ [shift_line(trans[y],-x)]
				+ trans[y+1:] )
		elif x >= maxcol:
			return ( trans[:y] 
				+ [shift_line(trans[y],-(x-maxcol+1))]
				+ trans[y+1:] )
		return trans
			

	def get_cursor_coords(self,(maxcol,)):
		"""Return the (x,y) coordinates of cursor within widget."""

		self._shift_view_to_cursor = True
		return self.position_coords(maxcol,self.edit_pos)
	
	
	def position_coords(self,maxcol,pos):
		"""
		Return (x,y) coordinates for an offset into self.edit_text.
		"""
		
		p = pos + len(self.caption)
		trans = self.get_line_translation(maxcol)
		x,y = calc_coords(self.get_text()[0], trans,p)
		return x,y

		




class IntEdit(Edit):
	"""Edit widget for integer values"""

	def valid_char(self, ch):
		"""Return true for decimal digits."""
		return len(ch)==1 and ord(ch)>=ord('0') and ord(ch)<=ord('9')
	
	def __init__(self,caption="",default=None):
		"""
		caption -- caption markup
		default -- default edit value
		"""
		if default is not None: val = str(default)
		else: val = ""
		Edit.__init__(self,caption,val)

	def keypress(self,(maxcol,),key):
		"""Handle editing keystrokes.  Return others."""
	        if key in list("0123456789"):
			# trim leading zeros
	                while self.edit_pos > 0 and self.edit_text[:1] == "0":
	                        self.set_edit_pos( self.edit_pos - 1)
	                        self.set_edit_text(self.edit_text[1:])

	        unhandled = Edit.keypress(self,(maxcol,),key)

		return unhandled

	def value(self):
		"""Return the numeric value of self.edit_text."""
		if self.edit_text:
			return long(self.edit_text)
		else:
			return 0


class SelectableIcon(Text):
	def selectable(self):
		return True
	
	def render(self, (maxcol,), focus=False):
		c = Text.render(self, (maxcol,), focus )
		if focus:
			c = CompositeCanvas(c)
			c.cursor = self.get_cursor_coords((maxcol,))
		return c
	
	def get_cursor_coords(self, (maxcol,)):
		if maxcol>1:
			return (1,0)

	def keypress(self, (maxcol,), key):
		return key

class CheckBox(FlowWidget):
	states = { 
		True: SelectableIcon("[X]"),
		False: SelectableIcon("[ ]"),
		'mixed': SelectableIcon("[#]") }
	reserve_columns = 4

	def selectable(self): return True
	
	def __init__(self, label, state=False, has_mixed=False,
		     on_state_change=None):
		"""
		label -- markup for check box label
		state -- False, True or "mixed"
		has_mixed -- True if "mixed" is a state to cycle through
		on_state_change -- callback function for state changes
		                   on_state_change( check box, new state )
		"""
		self.label = Text("")
		self.has_mixed = has_mixed
		self.state = None
		self.on_state_change = on_state_change
		self.set_label(label)
		self.set_state(state)
	
	def set_label(self, label):
		"""Change the check box label."""
		self.label.set_text(label)
	
	def get_label(self):
		"""Return label text."""
		text, attr = self.label.get_text()
		return text
	
	def set_state(self, state, do_callback=True):
		"""
		Call on_state_change if do_callback is True,
		then change the check box state.
		"""
		if (do_callback and self.state is not None and 
			self.on_state_change):
			self.on_state_change( self, state )
		self.state = state
		self.display_widget = Columns( [
			('fixed', self.reserve_columns, self.states[state] ),
			self.label ] )
		self.display_widget.focus_col = 0
		
	def get_state(self):
		"""Return the state of the checkbox."""
		return self.state
		
	def keypress(self, (maxcol,), key):
		"""Toggle state on space or enter."""
		if key not in (' ','enter'):
			return key
		
		self.toggle_state()
		
	def toggle_state(self):
		"""Cycle to the next valid state."""
		if self.state == False:
			self.set_state(True)
		elif self.state == True:
			if self.has_mixed:
				self.set_state('mixed')
			else:
				self.set_state(False)
		elif self.state == 'mixed':
			self.set_state(False)

	def mouse_event(self, (maxcol,), event, button, x, y, focus):
		"""Toggle state on button 1 press."""
		if button != 1 or not is_mouse_press(event):
			return False
		self.toggle_state()
		return True
	
	def get_cursor_coords(self, (maxcol,)):
		"""Return cursor coords from display widget."""
		return self.display_widget.get_cursor_coords( (maxcol,))
	
	def render(self, (maxcol,), focus=False):
		"""Render check box."""
		return self.display_widget.render( (maxcol,), focus=focus)
	
	def rows(self, (maxcol,), focus=False):
		"""Return rows required for check box."""
		return self.display_widget.rows( (maxcol,), focus=focus)
		

class RadioButton(FlowWidget):
	states = { 
		True: SelectableIcon("(X)"),
		False: SelectableIcon("( )"),
		'mixed': SelectableIcon("(#)") }
	reserve_columns = 4

	def selectable(self): return True
	
	def __init__(self, group, label, state="first True",
		     on_state_change=None):
		"""
		group -- list for radio buttons in same group
		label -- markup for radio button label
		state -- False, True, "mixed" or "first True"
		on_state_change -- callback function for state changes
		                   on_state_change( radio_button, new_state )

		This function will append the new radio button to group.
		"first True" will set to True if group is empty.
		"""

		if state=="first True":
			state = not group
		self.group = group

		self.label = Text("")
		self.state = None
		self.on_state_change = on_state_change
		self.set_label(label)
		self.set_state(state)
	
		group.append(self)
	
	def set_label(self, label):
		"""Change the check box label."""
		self.label.set_text(label)
	
	def get_label(self):
		"""Return label text."""
		text, attr = self.label.get_text()
		return text
	
	def set_state(self, state, do_callback=True):
		"""
		Call on_state_change if do_callback is True,
		then change the radio button state.
		if state is True set all other radio buttons in group to False.
		"""
		if (do_callback and self.state is not None and 
			self.on_state_change):
			self.on_state_change( self, state )
		self.state = state
		self.display_widget = Columns( [
			('fixed', self.reserve_columns, self.states[state] ),
			self.label ] )
		self.display_widget.focus_col = 0
		
		if state is not True:
			return

		for cb in self.group:
			if cb is self: continue
			if cb.state:
				cb.set_state(False)
	
	def get_state(self):
		"""Return the state of the radio button."""
		return self.state

	def keypress(self, (maxcol,), key):
		"""Set state to True on space or enter."""
		if key not in (' ','enter'):
			return key
		
		if self.state is not True:
			self.set_state(True)
		else:
			return key
	
	def mouse_event(self, (maxcol,), event, button, x, y, focus):
		"""Set state to True on button 1 press."""
		if button != 1 or not is_mouse_press(event):
			return False
		if self.state is not True:
			self.set_state(True)
		return True
			
	def get_cursor_coords(self, (maxcol,)):
		"""Return cursor coords from display widget."""
		return self.display_widget.get_cursor_coords( (maxcol,))
	
	def render(self, (maxcol,), focus=False):
		"""Render radio button."""
		return self.display_widget.render( (maxcol,), focus=focus)
	
	def rows(self, (maxcol,), focus=False):
		"""Return rows required for radio button."""
		return self.display_widget.rows( (maxcol,), focus=focus)

class Button(FlowWidget):
	button_left = Text("<")
	button_right = Text(">")

	def selectable(self):
		return True
	
	def __init__(self, label, on_press):
		"""
		label -- markup for button label
		on_press -- callback function for button "press"
		           on_press( button object )
		"""
			
		self.set_label( label )
		self.on_press = on_press
	
	def set_label(self, label):
		self.label = label
		self.display_widget = Columns([
			('fixed', 1, self.button_left),
			Text( label ),
			('fixed', 1, self.button_right)],
			dividechars=1)
	
	def get_label(self):
		return self.label
	
	def render(self, (maxcol,), focus=False):
		"""Display button. Show a cursor when in focus."""
		c = self.display_widget.render( (maxcol,), focus=focus)
		if focus and maxcol >2:
			c.cursor = (2,0)
		return c

	def get_cursor_coords(self, (maxcol,)):
		"""Return the location of the cursor."""
		if maxcol >2:
			return (2,0)
		return None

	def rows(self, (maxcol,), focus=False):
		"""Return rows required for button."""
		return self.display_widget.rows( (maxcol,), focus=focus)
		
	def keypress(self, (maxcol,), key):
		"""Call on_press on spage or enter."""
		if key not in (' ','enter'):
			return key
		
		self.on_press( self )
	
	def mouse_event(self, (maxcol,), event, button, x, y, focus):
		"""Call on_press on button 1 press."""
		if button != 1 or not is_mouse_press(event):
			return False
			
		self.on_press( self )
		return True
	


class GridFlow(FlowWidget):

	def selectable(self): 
		"""Return True if the cell in focus is selectable."""
		return self.focus_cell and self.focus_cell.selectable()
		
	def __init__(self, cells, cell_width, h_sep, v_sep, align):
		"""
		cells -- list of flow widgets to display
		cell_width -- column width for each cell
		h_sep -- blank columns between each cell horizontally
		v_sep -- blank rows between cells vertically (if more than
		         one row is required to display all the cells)
		align -- horizontal alignment of cells, see "align" parameter
		         of Padding widget for available options
		"""
		self.cells = cells
		self.cell_width = cell_width
		self.h_sep = h_sep
		self.v_sep = v_sep
		self.align = align
		self.focus_cell = None
		if cells:
			self.focus_cell = cells[0]
		self._cache_maxcol = None

	def set_focus(self, cell):
		"""Set the cell in focus.  
		
		cell -- widget or integer index into self.cells"""
		if type(cell) == type(0):
			assert cell>=0 and cell<len(self.cells)
			self.focus_cell = self.cells[cell]
		else:
			assert cell in self.cells
			self.focus_cell = cell
		self._cache_maxcol = None
		

	def get_display_widget(self, (maxcol,)):
		"""
		Arrange the cells into columns (and possibly a pile) for 
		display, input or to calculate rows. 
		"""
		# use cache if possible
		if self._cache_maxcol == maxcol:
			return self._cache_display_widget

		self._cache_maxcol = maxcol
		self._cache_display_widget = self.generate_display_widget(
			(maxcol,))

		return self._cache_display_widget

	def generate_display_widget(self, (maxcol,)):
		"""
		Actually generate display widget (ignoring cache)
		"""
		d = Divider()
		if len(self.cells) == 0: # how dull
			return d
		
		if self.v_sep > 1:
			# increase size of divider
			d.top = self.v_sep-1
		
		# cells per row
		bpr = (maxcol+self.h_sep) / (self.cell_width+self.h_sep)
		
		if bpr == 0: # too narrow, pile them on top of eachother
			l = [self.cells[0]]
			f = 0
			for b in self.cells[1:]:
				if b is self.focus_cell:
					f = len(l)
				if self.v_sep:
					l.append(d)
				l.append(b)
			return Pile(l, f)
		
		if bpr >= len(self.cells): # all fit on one row
			k = len(self.cells)
			f = self.cells.index(self.focus_cell)
			cols = Columns(self.cells, self.h_sep, f)
			rwidth = (self.cell_width+self.h_sep)*k - self.h_sep
			row = Padding(cols, self.align, rwidth)
			return row

		
		out = []
		s = 0
		f = 0
		while s < len(self.cells):
			if out and self.v_sep:
				out.append(d)
			k = min( len(self.cells), s+bpr )
			cells = self.cells[s:k]
			if self.focus_cell in cells:
				f = len(out)
				fcol = cells.index(self.focus_cell)
				cols = Columns(cells, self.h_sep, fcol)
			else:
				cols = Columns(cells, self.h_sep)
			rwidth = (self.cell_width+self.h_sep)*(k-s)-self.h_sep
			row = Padding(cols, self.align, rwidth)
			out.append(row)
			s += bpr
		return Pile(out, f)	
	
	def _set_focus_from_display_widget(self, w):
		"""Set the focus to the item in focus in the display widget."""
		if isinstance(w, Padding):
			# unwrap padding
			w = w.w
		w = w.get_focus()
		if w in self.cells:
			self.set_focus(w)
			return
		if isinstance(w, Padding):
			# unwrap padding
			w = w.w
		w = w.get_focus()
		#assert w == self.cells[0], `w, self.cells`
		self.set_focus(w)

	def keypress(self, (maxcol,), key):
		"""
		Pass keypress to display widget for handling.  
		Capture	focus changes."""
		
		d = self.get_display_widget((maxcol,))
		if not d.selectable():
			return key
		key = d.keypress( (maxcol,), key)
		if key is None:
			self._set_focus_from_display_widget(d)
		return key

	def rows(self, (maxcol,), focus=False):
		"""Return rows used by this widget."""
		d = self.get_display_widget((maxcol,))
		return d.rows( (maxcol,), focus=focus )
	
	def render(self, (maxcol,), focus=False ):
		"""Use display widget to render."""
		d = self.get_display_widget((maxcol,))
		return d.render( (maxcol,), focus=focus )

	def get_cursor_coords(self, (maxcol,)):
		"""Get cursor from display widget."""
		d = self.get_display_widget((maxcol,))
		if not d.selectable():
			return None
		return d.get_cursor_coords((maxcol,))
	
	def move_cursor_to_coords(self, (maxcol,), col, row ):
		"""Set the widget in focus based on the col + row."""
		d = self.get_display_widget((maxcol,))
		if not d.selectable():
			# happy is the default
			return True
		
		r =  d.move_cursor_to_coords((maxcol,), col, row)
		if not r:
			return False
		
		self._set_focus_from_display_widget(d)
		return True
	
	def mouse_event(self, (maxcol,), event, button, col, row, focus):
		"""Send mouse event to contained widget."""
		d = self.get_display_widget((maxcol,))
		
		r = d.mouse_event( (maxcol,), event, button, col, row, focus )
		if not r:
			return False
		
		self._set_focus_from_display_widget(d)
		return True
		
	
	def get_pref_col(self, (maxcol,)):
		"""Return pref col from display widget."""
		d = self.get_display_widget((maxcol,))
		if not d.selectable():
			return None
		return d.get_pref_col((maxcol,))
	


class PaddingError(Exception):
	pass

class Padding(object):
	def __init__(self, w, align, width, min_width=None):
		"""
		w -- a box, flow or fixed widget to pad on the left and/or right
		align -- one of:
		    'left', 'center', 'right'
		    ('fixed left', columns)
		    ('fixed right', columns)
		    ('relative', percentage 0=left 100=right)
		width -- one of:
		    number of columns wide 
		    ('fixed right', columns)  Only if align is 'fixed left'
		    ('fixed left', columns)  Only if align is 'fixed right'
		    ('relative', percentage of total width)
		    None   to enable clipping mode
		min_width -- the minimum number of columns for w or None
			
		Padding widgets will try to satisfy width argument first by
		reducing the align amount when necessary.  If width still 
		cannot be satisfied it will also be reduced.

		Clipping Mode:
		In clipping mode w is treated as a fixed widget and this 
		widget expects to be treated as a flow widget.  w will
		be clipped to fit within the space given.  For example,
		if align is 'left' then w may be clipped on the right.
		"""

		at,aa,wt,wa=decompose_align_width(align, width, PaddingError)
		
		self.w = w
		self.align_type, self.align_amount = at, aa
		self.width_type, self.width_amount = wt, wa
		self.min_width = min_width
		
	def render(self, size, focus=False):	
		left, right = self.padding_values(size, focus)
		
		maxcol = size[0]
		maxcol -= left+right

		if self.width_type is None:
			c = self.w.render((), focus)
		else:
			c = self.w.render((maxcol,)+size[1:], focus)
		if left != 0 or right != 0:
			c = CompositeCanvas(c)
			c.pad_trim_left_right(left, right)
		return c

	def padding_values(self, size, focus):
		"""Return the number of columns to pad on the left and right.
		
		Override this method to define custom padding behaviour."""
		maxcol = size[0]
		if self.width_type is None:
			width, ignore = self.w.pack(focus=focus)
			return calculate_padding(self.align_type,
				self.align_amount, 'fixed', width, 
				None, maxcol, clip=True )

		return calculate_padding( self.align_type, self.align_amount,
			self.width_type, self.width_amount,
			self.min_width, maxcol )

	def selectable(self):
		"""Return the selectable value of self.w."""
		return self.w.selectable()

	def rows(self, (maxcol,), focus=False ):
		"""Return the rows needed for self.w."""
		if self.width_type is None:
			ignore, height = self.w.pack(focus)
			return height
		left, right = self.padding_values((maxcol,), focus)
		return self.w.rows( (maxcol-left-right,), focus=focus )
	
	def keypress(self, size, key):
		"""Pass keypress to self.w."""
		maxcol = size[0]
		left, right = self.padding_values(size, True)
		maxvals = (maxcol-left-right,)+size[1:] 
		return self.w.keypress(maxvals, key)

	def get_cursor_coords(self,size):
		"""Return the (x,y) coordinates of cursor within self.w."""
		if not hasattr(self.w,'get_cursor_coords'):
			return None
		left, right = self.padding_values(size, True)
		maxcol = size[0]
		maxvals = (maxcol-left-right,)+size[1:] 
		coords = self.w.get_cursor_coords(maxvals)
		if coords is None: 
			return None
		x, y = coords
		return x+left, y

	def move_cursor_to_coords(self, size, x, y):
		"""Set the cursor position with (x,y) coordinates of self.w.

		Returns True if move succeeded, False otherwise.
		"""
		if not hasattr(self.w,'move_cursor_to_coords'):
			return True
		left, right = self.padding_values(size, True)
		maxcol = size[0]
		maxvals = (maxcol-left-right,)+size[1:] 
		if type(x)==type(0):
			if x < left: 
				x = left
			elif x >= maxcol-right: 
				x = maxcol-right-1
			x -= left
		return self.w.move_cursor_to_coords(maxvals, x, y)
	
	def mouse_event(self, size, event, button, x, y, focus):
		"""Send mouse event if position is within self.w."""
		if not hasattr(self.w,'mouse_event'):
			return False
		left, right = self.padding_values(size, focus)
		maxcol = size[0]
		if x < left or x >= maxcol-right: 
			return False
		maxvals = (maxcol-left-right,)+size[1:] 
		return self.w.mouse_event(maxvals, event, button, x-left, y,
			focus)
		

	def get_pref_col(self, size):
		"""Return the preferred column from self.w, or None."""
		if not hasattr(self.w,'get_pref_col'):
			return None
		left, right = self.padding_values(size, True)
		maxcol = size[0]
		maxvals = (maxcol-left-right,)+size[1:] 
		x = self.w.get_pref_col(maxvals)
		if type(x) == type(0):
			return x+left
		return x
		

class FillerError(Exception):
	pass

class Filler(BoxWidget):
	def __init__(self, body, valign="middle", height=None, min_height=None):
		"""
		body -- a flow widget or box widget to be filled around
		valign -- one of:
		    'top', 'middle', 'bottom'
		    ('fixed top', rows)
		    ('fixed bottom', rows)
		    ('relative', percentage 0=top 100=bottom)
		height -- one of:
		    None if body is a flow widget
		    number of rows high 
		    ('fixed bottom', rows)  Only if valign is 'fixed top'
		    ('fixed top', rows)  Only if valign is 'fixed bottom'
		    ('relative', percentage of total height)
		min_height -- one of:
		    None if no minimum or if body is a flow widget
		    minimum number of rows for the widget when height not fixed
		
		If body is a flow widget then height and min_height must be set
		to None.
		
		Filler widgets will try to satisfy height argument first by
		reducing the valign amount when necessary.  If height still 
		cannot be satisfied it will also be reduced.
		"""
		vt,va,ht,ha=decompose_valign_height(valign,height,FillerError)
		
		self.body = body
		self.valign_type, self.valign_amount = vt, va
		self.height_type, self.height_amount = ht, ha
		if self.height_type not in ('fixed', None):
			self.min_height = min_height
		else:
			self.min_height = None
	
	def selectable(self):
		"""Return selectable from body."""
		return self.body.selectable()
	
	def filler_values(self, (maxcol, maxrow), focus):
		"""Return the number of rows to pad on the top and bottom.
		
		Override this method to define custom padding behaviour."""

		if self.height_type is None:
			height = self.body.rows((maxcol,),focus=focus)
			return calculate_filler( self.valign_type,
				self.valign_amount, 'fixed', height, 
				None, maxrow )
			
		return calculate_filler( self.valign_type, self.valign_amount,
			self.height_type, self.height_amount,
			self.min_height, maxrow)

	
	def render(self, (maxcol,maxrow), focus=False):
		"""Render self.body with space above and/or below."""
		top, bottom = self.filler_values((maxcol,maxrow), focus)
		
		if self.height_type is None:
			c = self.body.render( (maxcol,), focus)
		else:
			c = self.body.render( (maxcol,maxrow-top-bottom),focus)
		c = CompositeCanvas(c)
		
		if c.rows() > maxrow and c.cursor is not None:
			cx, cy = c.cursor
			if cy >= maxrow:
				c.trim(cy-maxrow+1,maxrow-top-bottom)
			
		#c.trim(0, maxrow-top-bottom)
		c.pad_trim_top_bottom(top, bottom)
		return c


	def keypress(self, (maxcol,maxrow), key):
		"""Pass keypress to self.body."""
		if self.height_type is None:
			return self.body.keypress( (maxcol,), key )

		top, bottom = self.filler_values((maxcol,maxrow), True)
		return self.body.keypress( (maxcol,maxrow-top-bottom), key )

	def get_cursor_coords(self, (maxcol,maxrow)):
		"""Return cursor coords from self.body if any."""
		if not hasattr(self.body, 'get_cursor_coords'):
			return None
			
		top, bottom = self.filler_values((maxcol,maxrow), True)
		if self.height_type is None:
			coords = self.body.get_cursor_coords((maxcol,))
		else:
			coords = self.body.get_cursor_coords(
				(maxcol,maxrow-top-bottom))
		if not coords:
			return None
		x, y = coords
		if y >= maxrow:
			y = maxrow-1
		return x, y+top

	def get_pref_col(self, (maxcol,maxrow)):
		"""Return pref_col from self.body if any."""
		if not hasattr(self.body, 'get_pref_col'):
			return None
		
		if self.height_type is None:
			x = self.body.get_pref_col((maxcol,))
		else:
			top, bottom = self.filler_values((maxcol,maxrow), True)
			x = self.body.get_pref_col(
				(maxcol,maxrow-top-bottom))

		return x
	
	def move_cursor_to_coords(self, (maxcol,maxrow), col, row):
		"""Pass to self.body."""
		if not hasattr(self.body, 'move_cursor_to_coords'):
			return True
		
		top, bottom = self.filler_values((maxcol,maxrow), True)
		if row < top or row >= maxcol-bottom:
			return False

		if self.height_type is None:
			return self.body.move_cursor_to_coords((maxcol,),
				col, row-top)
		return self.body.move_cursor_to_coords(
			(maxcol, maxrow-top-bottom), col, row-top)
	
	def mouse_event(self, (maxcol,maxrow), event, button, col, row, focus):
		"""Pass to self.body."""
		if not hasattr(self.body, 'mouse_event'):
			return False
		
		top, bottom = self.filler_values((maxcol,maxrow), True)
		if row < top or row >= maxcol-bottom:
			return False

		if self.height_type is None:
			return self.body.mouse_event((maxcol,),
				event, button, col, row-top, focus)
		return self.body.mouse_event( (maxcol, maxrow-top-bottom), 
			event, button,col, row-top, focus)
		
		
class OverlayError(Exception):
	pass

class Overlay(BoxWidget):
	def __init__(self, top_w, bottom_w, align, width, valign, height,
			min_width=None, min_height=None ):
		"""
		top_w -- a flow, box or fixed widget to overlay "on top"
		bottom_w -- a box widget to appear "below" previous widget
		align -- one of:
		    'left', 'center', 'right'
		    ('fixed left', columns)
		    ('fixed right', columns)
		    ('relative', percentage 0=left 100=right)
		width -- one of:
		    None if top_w is a fixed widget
		    number of columns wide
		    ('fixed right', columns)  Only if align is 'fixed left'
		    ('fixed left', columns)  Only if align is 'fixed right'
		    ('relative', percentage of total width)
		valign -- one of:
		    'top', 'middle', 'bottom'
		    ('fixed top', rows)
		    ('fixed bottom', rows)
		    ('relative', percentage 0=top 100=bottom)
		height -- one of:
		    None if top_w is a flow or fixed widget
		    number of rows high 
		    ('fixed bottom', rows)  Only if valign is 'fixed top'
		    ('fixed top', rows)  Only if valign is 'fixed bottom'
		    ('relative', percentage of total height)
		min_width -- the minimum number of columns for top_w
		    when width is not fixed
		min_height -- one of:
		    minimum number of rows for the widget when height not fixed
		
		Overlay widgets behave similarly to Padding and Filler widgets
		when determining the size and position of top_w.  bottom_w is
		always rendered the full size available "below" top_w.
		"""

		at,aa,wt,wa=decompose_align_width(align, width, OverlayError)
		vt,va,ht,ha=decompose_valign_height(valign,height,OverlayError)
		
		self.top_w = top_w
		self.bottom_w = bottom_w
		
		self.align_type, self.align_amount = at, aa
		self.width_type, self.width_amount = wt, wa
		if self.width_type and self.width_type != 'fixed':
			self.min_width = min_width
		else:
			self.min_width = None
		
		self.valign_type, self.valign_amount = vt, va
		self.height_type, self.height_amount = ht, ha
		if self.height_type not in ('fixed', None):
			self.min_height = min_height
		else:
			self.min_height = None

	def selectable(self):
		"""Return selectable from top_w."""
		return self.top_w.selectable()
	
	def keypress(self, size, key):
		"""Pass keypress to top_w."""
		return self.top_w.keypress( size, key)
	
	def get_cursor_coords(self, size):
		"""Return cursor coords from top_w, if any."""
		if not hasattr(self.body, 'get_cursor_coords'):
			return None
		left, right, top, bottom = self.calculate_padding_filler(size,
			True)
		x, y = self.top_w.get_cursor_coords(
			(maxcol-left-right, maxrow-top-bottom) )
		if y >= maxrow:  # required??
			y = maxrow-1
		return x+left, y+top
	
	def calculate_padding_filler(self, (maxcol, maxrow), focus):
		"""Return (padding left, right, filler top, bottom)."""
		height = None
		if self.width_type is None:
			# top_w is a fixed widget
			width, height = self.top_w.pack(focus=focus)
			assert height, "fixed widget must have a height"
			left, right = calculate_padding(self.align_type,
				self.align_amount, 'fixed', width, 
				None, maxcol, clip=True )
		else:
			left, right = calculate_padding(self.align_type,
				self.align_amount, self.width_type,
				self.width_amount, self.min_width, maxcol)

		if height:
			# top_w is a fixed widget
			top, bottom = calculate_filler(self.valign_type, 
				self.valign_amount, 'fixed', height,
				None, maxrow)
		elif self.height_type is None:
			# top_w is a flow widget
			height = self.body.rows((maxcol,),focus=focus)
			top, bottom =  calculate_filler( self.valign_type,
				self.valign_amount, 'fixed', height, 
				None, maxrow )
		else:	
			top, bottom = calculate_filler(self.valign_type, 
				self.valign_amount, self.height_type, 
				self.height_amount, self.min_height, maxrow)
		return left, right, top, bottom
	
	def top_w_size(self, size, left, right, top, bottom):
		"""Return the size to pass to top_w."""
		if self.width_type is None:
			# top_w is a fixed widget
			return ()
		maxcol, maxrow = size
		if self.width_type is not None and self.height_type is None:
			# top_w is a flow widget
			return (maxcol-left-right,)
		return (maxcol-left-right, maxrow-top-bottom)
			
	
	def render(self, size, focus=False):
		"""Render top_w overlayed on bottom_w."""
		left, right, top, bottom = self.calculate_padding_filler(size,
			focus)
		bottom_c = CompositeCanvas(self.bottom_w.render(size))
		top_c = self.top_w.render(
			self.top_w_size(size, left, right, top, bottom), focus)
		top_c = CompositeCanvas(top_c)
		if left<0 or right<0:
			top_c.pad_trim_left_right(min(0,left), min(0,right))
		bottom_c.overlay(top_c, max(0,left), max(0,right), top, bottom)
		return bottom_c

	def mouse_event(self, size, event, button, col, row, focus):
		"""Pass event to top_w, ignore if outside of top_w."""
		if not hasattr(self.top_w, 'mouse_event'):
			return False
		
		left, right, top, bottom = self.calculate_padding_filler(size,
			focus)
		maxcol, maxrow = size
		if ( col<left or col>=maxcol-right or
			row<top or row>=maxrow-bottom ):
			return False
			
		return self.top_w.mouse_event(
			self.top_w_size(size, left, right, top, bottom),
			event, button, col-left, row-top, focus )
	

def decompose_align_width( align, width, err ):
	try:
		if align in ('left','center','right'):
			align = (align,0)
		align_type, align_amount = align
		assert align_type in ('left','center','right','fixed left',
			'fixed right','relative')
	except:
		raise err("align value %s is not one of 'left', 'center', "
			"'right', ('fixed left', columns), ('fixed right', "
			"columns), ('relative', percentage 0=left 100=right)" 
			% `align`)

	try:
		if width is None:
			width = None, None
		elif type(width) == type(0):
			width = 'fixed', width
		width_type, width_amount = width
		assert width_type in ('fixed','fixed right','fixed left',
			'relative', None)
	except:
		raise err("width value %s is not one of ('fixed', columns "
			"width), ('fixed right', columns), ('relative', "
			"percentage of total width), None" % `width`)
		
	if width_type == 'fixed left' and align_type != 'fixed right':
		raise err("fixed left width may only be used with fixed "
			"right align")
	if width_type == 'fixed right' and align_type != 'fixed left':
		raise err("fixed right width may only be used with fixed "
			"left align")

	return align_type, align_amount, width_type, width_amount


def decompose_valign_height( valign, height, err ):
	try:
		if valign in ('top','middle','bottom'):
			valign = (valign,0)
		valign_type, valign_amount = valign
		assert valign_type in ('top','middle','bottom','fixed top','fixed bottom','relative')
	except:
		raise err, "Invalid valign: %s" % `valign`

	try:
		if height is None:
			height = None, None
		elif type(height) == type(0):
			height=('fixed',height)
		height_type, height_amount = height
		assert height_type in (None, 'fixed','fixed bottom','fixed top','relative')
	except:
		raise err, "Invalid height: %s"%`height`
		
	if height_type == 'fixed top' and valign_type != 'fixed bottom':
		raise err, "fixed top height may only be used with fixed bottom valign"
	if height_type == 'fixed bottom' and valign_type != 'fixed top':
		raise err, "fixed bottom height may only be used with fixed top valign"
		
	return valign_type, valign_amount, height_type, height_amount


def calculate_filler( valign_type, valign_amount, height_type, height_amount, 
		      min_height, maxrow ):
	if height_type == 'fixed':
		height = height_amount
	elif height_type == 'relative':
		height = int(height_amount*maxrow/100+.5)
		if min_height is not None:
			    height = max(height, min_height)
	else:
		assert height_type in ('fixed bottom','fixed top')
		height = maxrow-height_amount-valign_amount
		if min_height is not None:
			    height = max(height, min_height)
	
	if height >= maxrow:
		# use the full space (no padding)
		return 0, 0
		
	if valign_type == 'fixed top':
		top = valign_amount
		if top+height <= maxrow:
			return top, maxrow-top-height
		# need to shrink top
		return maxrow-height, 0
	elif valign_type == 'fixed bottom':
		bottom = valign_amount
		if bottom+height <= maxrow:
			return maxrow-bottom-height, bottom
		# need to shrink bottom
		return 0, maxrow-height		
	elif valign_type == 'relative':
		top = int( (maxrow-height)*valign_amount/100+.5 )
	elif valign_type == 'bottom':
		top = maxrow-height	
	elif valign_type == 'middle':
		top = int( (maxrow-height)/2 )
	else: #self.valign_type == 'top'
		top = 0
	
	if top+height > maxrow: top = maxrow-height
	if top < 0: top = 0
	
	bottom = maxrow-height-top
	return top, bottom 	


def calculate_padding( align_type, align_amount, width_type, width_amount,
		min_width, maxcol, clip=False ):
	if width_type == 'fixed':
		width = width_amount
	elif width_type == 'relative':
		width = int(width_amount*maxcol/100+.5)
		if min_width is not None:
			    width = max(width, min_width)
	else: 
		assert width_type in ('fixed right', 'fixed left')
		width = maxcol-width_amount-align_amount
		if min_width is not None:
			    width = max(width, min_width)
	
	if width == maxcol or (width > maxcol and not clip):
		# use the full space (no padding)
		return 0, 0
		
	if align_type == 'fixed left':
		left = align_amount
		if left+width <= maxcol:
			return left, maxcol-left-width
		# need to shrink left
		return maxcol-width, 0
	elif align_type == 'fixed right':
		right = align_amount
		if right+width <= maxcol:
			return maxcol-right-width, right
		# need to shrink right
		return 0, maxcol-width		
	elif align_type == 'relative':
		left = int( (maxcol-width)*align_amount/100+.5 )
	elif align_type == 'right':
		left = maxcol-width	
	elif align_type == 'center':
		left = int( (maxcol-width)/2 )
	else: 
		assert align_type == 'left'
		left = 0
	
	if width < maxcol:
		if left+width > maxcol: left = maxcol-width
		if left < 0: left = 0
	
	right = maxcol-width-left
	return left, right 	



class Frame(BoxWidget):
	def __init__(self, body, header=None, footer=None, focus_part='body'):
		"""
		body -- a box widget for the body of the frame
		header -- a flow widget for above the body (or None)
		footer -- a flow widget for below the body (or None)
		focus_part -- 'header', 'footer' or 'body'
		"""
		self.header = header
		self.body = body
		self.footer = footer
		self.focus_part = focus_part
	
	def set_focus(self, part):
		"""Set the part of the frame that is in focus.

		part -- 'header', 'footer' or 'body'
		"""
		assert part in ('header', 'footer', 'body')
		self.focus_part = part

	def frame_top_bottom(self, (maxcol,maxrow), focus):
		"""Calculate the number of rows for the header and footer.

		Returns (head rows, foot rows),(orig head, orig foot).
		orig head/foot are from rows() calls.
		"""
		frows = hrows = 0
		
		if self.header:
			hrows = self.header.rows((maxcol,),
				self.focus_part=='header' and focus)
		
		if self.footer:
			frows = self.footer.rows((maxcol,),
				self.focus_part=='footer' and focus)
		
		remaining = maxrow
		
		if self.focus_part == 'footer':
			if frows >= remaining:
				return (0, remaining),(hrows, frows)
				
			remaining -= frows
			if hrows >= remaining:
				return (remaining, frows),(hrows, frows)

		elif self.focus_part == 'header':
			if hrows >= maxrow:
				return (remaining, 0),(hrows, frows)
			
			remaining -= hrows
			if frows >= remaining:
				return (hrows, remaining),(hrows, frows)

		elif hrows + frows >= remaining:
			# self.focus_part == 'body'
			if frows >= remaining-1:
				return (0, remaining-1),(hrows, frows)
			
			remaining -= frows
			return (remaining-1,frows),(hrows, frows)
		
		return (hrows, frows),(hrows, frows)
		
	

	def render(self, (maxcol,maxrow), focus=False):
		"""Render frame and return it."""
		
		(htrim, ftrim),(hrows, frows) = self.frame_top_bottom(
			(maxcol, maxrow), focus)
		
		if not ftrim:
			foot = Canvas()
		elif ftrim < frows:
			foot = Filler(self.footer, 'bottom').render(
				(maxcol, ftrim), 
				focus and self.focus_part == 'footer')
		else:
			foot = self.footer.render((maxcol,),
				focus and self.focus_part == 'footer')
			assert foot.rows() == frows, "rows, render mismatch"
		
		if not htrim:
			head = Canvas()
		elif htrim < hrows:
			head = Filler(self.header, 'top').render(
				(maxcol, htrim), 
				focus and self.focus_part == 'header')
		else:
			head = self.header.render((maxcol,),
				focus and self.focus_part == 'header')
			assert head.rows() == hrows, "rows, render mismatch"

		if ftrim+htrim < maxrow:
			body = self.body.render((maxcol, maxrow-ftrim-htrim),
				focus and self.focus_part == 'body')
			
		return CanvasCombine( [head,body,foot] )


	def keypress(self, (maxcol,maxrow), key):
		"""Pass keypress to widget in focus."""
		
		if self.focus_part == 'header' and self.header is not None:
			if not self.header.selectable():
				return key
			return self.header.keypress((maxcol,),key) 
		if self.focus_part == 'footer' and self.footer is not None:
			if not self.footer.selectable():
				return key
			return self.footer.keypress((maxcol,),key)
		if self.focus_part != 'body':
			return key
		remaining = maxrow
		if self.header is not None:
			remaining -= self.header.rows((maxcol,))
		if self.footer is not None:
			remaining -= self.footer.rows((maxcol,))
		if remaining <= 0: return key
	
		if not self.body.selectable():
			return key
		return self.body.keypress( (maxcol, remaining), key )


	def mouse_event(self, (maxcol, maxrow), event, button, col, row, focus):
		"""
		Pass mouse event to appropriate part of frame.
		Focus may be changed on button 1 press.
		"""
		(htrim, ftrim),(hrows, frows) = self.frame_top_bottom(
			(maxcol, maxrow), focus)
		
		if row < htrim: # within header
			focus = focus and self.focus_part == 'header'
			if is_mouse_press(event) and button==1:
				if self.header.selectable():
					self.set_focus('header')
			if not hasattr(self.header, 'mouse_event'):
				return False
			return self.header.mouse_event( (maxcol,), event,
				button, col, row, focus )
		
		if row >= maxrow-ftrim: # within footer
			focus = focus and self.focus_part == 'footer'
			if is_mouse_press(event) and button==1:
				if self.footer.selectable():
					self.set_focus('footer')
			if not hasattr(self.footer, 'mouse_event'):
				return False
			return self.footer.mouse_event( (maxcol,), event,
				button, col, row-maxrow+frows, focus )
		
		# within body
		focus = focus and self.focus_part == 'body'
		if is_mouse_press(event) and button==1:
			if self.body.selectable():
				self.set_focus('body')
		
		if not hasattr(self.body, 'mouse_event'):
			return False
		return self.body.mouse_event( (maxcol, maxrow-htrim-ftrim),
			event, button, col, row-htrim, focus )

		

class AttrWrap(object):
	"""
	AttrWrap is a decorator that changes the default attribute for a 
	FlowWidget or BoxWidget
	"""
	def __init__(self, w, attr, focus_attr = None):
		"""
		w -- widget to wrap
		attr -- attribute to apply to w
		focus_attr -- attribute to apply when in focus, if None use attr
		
		This object will pass all function calls and variable references
		to the wrapped widget.
		"""
		self.w = w
		self.attr = attr
		self.focus_attr = focus_attr
	
	def render(self, size, focus = False ):
		"""Render self.w and apply attribute. Return canvas.
		
		size -- (maxcol,) if self.w contains a flow widget or
			(maxcol, maxrow) if it contains a box widget.
		"""
		attr = self.attr
		if focus and self.focus_attr is not None:
			attr = self.focus_attr
		canv = self.w.render( size, focus=focus )
		canv = CompositeCanvas(canv)
		canv.fill_attr( attr )
		cols = size[0]
		return canv

	def __getattr__(self,name):
		"""Call getattr on wrapped widget."""
		return getattr(self.w, name)

class WidgetWrap(object):
	def __init__(self, w):
		"""
		w -- widget to wrap, stored as self.w

		This object will pass the functions defined in Widget interface
		definition to self.w.
		"""
		self.w = w
	
	def __getattr__(self,name):
		"""Call self.w if name is in Widget interface definition."""
		if name in ['get_cursor_coords','get_pref_col','keypress',
			'move_cursor_to_coords','render','rows','selectable',
			'mouse_event',]:
			return getattr(self.w, name)
		raise AttributeError, name

class PileError(Exception):
	pass
		
class Pile(object): # either FlowWidget or BoxWidget
	def __init__(self, widget_list, focus_item=0):
		"""
		widget_list -- list of widgets
		focus_item -- widget or integer index

		widget_list may also contain tuples such as:
		('flow', widget) always treat widget as a flow widget
		('fixed', height, widget) give this box widget a fixed height
		('weight', weight, widget) if the pile is treated as a box
			widget then treat widget as a box widget with a
			height based on its relative weight value, otherwise
			treat widget as a flow widget
		
		widgets not in a tuple are the same as ('weight', 1, widget)

		If the pile is treated as a box widget there must be at least
		one 'weight' tuple in widget_list.
		"""
		self.widget_list = widget_list
		self.item_types = []
		for i in range(len(widget_list)):
			w = widget_list[i]
			if type(w) != type(()):
				self.item_types.append(('weight',1))
			elif w[0] == 'flow':
				f, widget = w
				self.widget_list[i] = widget
				self.item_types.append((f,None))
			elif w[0] in ('fixed', 'weight'):
				f, height, widget = w
				self.widget_list[i] = widget
				self.item_types.append((f,height))
			else:
				raise PileError, "widget list item invalid %s" % `w`
			
		self.set_focus(focus_item)
		self.pref_col = None

	def selectable(self):
		"""Return True if the focus item is selectable."""
		return self.focus_item.selectable()

	def set_focus(self, item):
		"""Set the item in focus.  
		
		item -- widget or integer index"""
		if type(item) == type(0):
			assert item>=0 and item<len(self.widget_list)
			self.focus_item = self.widget_list[item]
		else:
			assert item in self.widget_list
			self.focus_item = item

	def get_focus(self):
		"""Return the widget in focus."""
		return self.focus_item

	def get_pref_col(self, size):
		"""Return the preferred column for the cursor, or None."""
		if not self.selectable():
			return None
		self._update_pref_col_from_focus(size)
		return self.pref_col
		
	def get_item_size(self, size, i, focus, item_rows=None):
		"""
		Return a size appropriate for passing to self.widget_list[i]
		"""
		maxcol = size[0]
		f, height = self.item_types[i]
		if f=='fixed':
			return (maxcol, height)
		elif f=='weight' and len(size)==2:
			if not item_rows:
				item_rows = self.get_item_rows(size, focus)
			return (maxcol, item_rows[i])
		else:
			return (maxcol,)
					
	def get_item_rows(self, size, focus):
		"""
		Return a list of the number of rows used by each widget
		in self.item_list.
		"""
		remaining = None
		maxcol = size[0]
		if len(size)==2:
			remaining = size[1]
		
		l = []
		
		if remaining is None:
			# pile is a flow widget
			for (f, height), w in zip(
				self.item_types, self.widget_list):
				if f == 'fixed':
					l.append( height )
				else:
					l.append( w.rows( (maxcol,), focus=focus
						and self.focus_item == w ))
			return l
			
		# pile is a box widget
		# do an extra pass to calculate rows for each widget
		wtotal = 0
		for (f, height), w in zip(self.item_types, self.widget_list):
			if f == 'flow':
				rows = w.rows((maxcol,), focus=focus and
					self.focus_item == w )
				l.append(rows)
				remaining -= rows
			elif f == 'fixed':
				l.append(height)
				remaining -= height
			else:
				l.append(None)
				wtotal += height

		if wtotal == 0:
			raise PileError, "No weighted widgets found for Pile treated as a box widget"

		if remaining < 0: 
			remaining = 0

		i = 0
		for (f, height), li in zip(self.item_types, l):
			if li is None:
				rows = int(float(remaining)*height
					/wtotal+0.5)
				l[i] = rows
				remaining -= rows
				wtotal -= height
			i += 1
		return l
		
				
		
		
	
	def render(self, size, focus=False):
		"""
		Render all widgets in self.widget_list and return the results
		stacked one on top of the next.
		"""
		maxcol = size[0]
		item_rows = None
		
		l = []
		i = 0
		for (f, height), w in zip(self.item_types, self.widget_list):
			if f == 'fixed':
				l.append( w.render( (maxcol, height),
					focus=focus and self.focus_item == w ))
			elif f == 'flow' or len(size)==1:
				l.append( w.render( (maxcol,), 
					focus=focus and	self.focus_item == w ))
			else:	
				if item_rows is None:
					item_rows = self.get_item_rows(size, 
						focus)
				rows = item_rows[i]
				if rows>0:
					l.append( w.render( (maxcol, rows),
					focus=focus and	self.focus_item == w ))
			i+=1

		return CanvasCombine( l ) 
	
	def get_cursor_coords(self, size):
		"""Return the cursor coordinates of the focus widget."""
		if not self.focus_item.selectable():
			return None
		if not hasattr(self.focus_item,'get_cursor_coords'):
			return None
		
		i = self.widget_list.index(self.focus_item)
		f, height = self.item_types[i]
		item_rows = None
		maxcol = size[0]
		if f == 'fixed' or (f=='weight' and len(size)==2):
			if f == 'fixed':
				maxrow = height
			else:
				if item_rows is None:
					item_rows = self.get_item_rows(size, 
					focus=True)
				maxrow = item_rows[i]
			coords = self.focus_item.get_cursor_coords(
				(maxcol,maxrow))
		else:
			coords = self.focus_item.get_cursor_coords((maxcol,))

		if coords is None:
			return None
		x,y = coords
		if i > 0:
			if item_rows is None:
				item_rows = self.get_item_rows(size, focus=True)
			for r in item_rows[:i]:
				y += r
		return x, y
		
	
	def rows(self, (maxcol,), focus=False ):
		"""Return the number of rows required for this widget."""
		return sum( self.get_item_rows( (maxcol,), focus ) )


	def keypress(self, size, key ):
		"""Pass the keypress to the widget in focus.
		Unhandled 'up' and 'down' keys may cause a focus change."""

		maxcol = size[0]
		item_rows = None
		if len(size)==2:
			item_rows = self.get_item_rows( size, focus=True )

		i = self.widget_list.index(self.focus_item)
		f, height = self.item_types[i]
		if self.focus_item.selectable():
			tsize = self.get_item_size(size,i,True,item_rows)
			key = self.focus_item.keypress( tsize, key )
			if key not in ('up', 'down'):
				return key

		if key == 'up':
			candidates = range(i-1, -1, -1) # count backwards to 0
		else: # key == 'down'
			candidates = range(i+1, len(self.widget_list))
		
		if not item_rows:
			item_rows = self.get_item_rows( size, focus=True )
	
		for j in candidates:
			if not self.widget_list[j].selectable():
				continue
			
			self._update_pref_col_from_focus(size)
			old_focus = self.focus_item
			self.set_focus(j)
			if not hasattr(self.focus_item,'move_cursor_to_coords'):
				return

			f, height = self.item_types[j]
			rows = item_rows[j]
			if key=='up':
				rowlist = range(rows-1, -1, -1)
			else: # key == 'down'
				rowlist = range(rows)
			for row in rowlist:
				tsize=self.get_item_size(size,j,True,item_rows)
				if self.focus_item.move_cursor_to_coords(
						tsize,self.pref_col,row):
					break
			return					
				
		# nothing to select
		return key


	def _update_pref_col_from_focus(self, size ):
		"""Update self.pref_col from the focus widget."""
		
		widget = self.focus_item

		if not hasattr(widget,'get_pref_col'):
			return
		i = self.widget_list.index(widget)
		tsize = self.get_item_size(size,i,True)
		pref_col = widget.get_pref_col(tsize)
		if pref_col is not None: 
			self.pref_col = pref_col

	def move_cursor_to_coords(self, size, col, row):
		"""Capture pref col and set new focus."""
		self.pref_col = col
		
		#FIXME guessing focus==True
		focus=True
		wrow = 0 
		item_rows = self.get_item_rows(size,focus)
		for r,w in zip(item_rows, self.widget_list):
			if wrow+r > row:
				break
			wrow += r

		if not w.selectable():
			return False
		
		if hasattr(w,'move_cursor_to_coords'):
			i = self.widget_list.index(w)
			tsize = self.get_item_size(size, i, focus, item_rows)
			rval = w.move_cursor_to_coords(tsize,col,row-wrow)
			if rval is False:
				return False
			
		self.set_focus(w)
		return True
	
	def mouse_event(self, size, event, button, col, row, focus):
		"""
		Pass the event to the contained widget.
		May change focus on button 1 press.
		"""
		wrow = 0
		item_rows = self.get_item_rows(size,focus)
		for r,w in zip(item_rows, self.widget_list):
			if wrow+r > row:
				break
			wrow += r

		focus = focus and self.focus_item == w
		if is_mouse_press(event) and button==1:
			if w.selectable():
				self.set_focus(w)
		
		if not hasattr(w,'mouse_event'):
			return False

		i = self.widget_list.index(w)
		tsize = self.get_item_size(size, i, focus, item_rows)
		return w.mouse_event(tsize, event, button, col, row-wrow,
			focus)



class ColumnsError(Exception):
	pass

		
class Columns(object): # either FlowWidget or BoxWidget
	def __init__(self, widget_list, dividechars=0, focus_column=0,
		min_width=1, box_columns=None):
		"""
		widget_list -- list of flow widgets or list of box widgets
		dividechars -- blank characters between columns
		focus_column -- index into widget_list of column in focus
		min_width -- minimum width for each column before it is hidden
		box_columns -- a list of column indexes containing box widgets
			whose maxrow is set to the maximum of the rows 
			required by columns not listed in box_columns.

		widget_list may also contain tuples such as:
		('fixed', width, widget) give this column a fixed width
		('weight', weight, widget) give this column a relative weight

		widgets not in a tuple are the same as ('weight', 1, widget)	

		box_columns is ignored when this widget is being used as a
		box widget because in that case all columns are treated as box
		widgets.
		"""
		self.widget_list = widget_list
		self.column_types = []
		for i in range(len(widget_list)):
			w = widget_list[i]
			if type(w) != type(()):
				self.column_types.append(('weight',1))
			elif w[0] in ('fixed', 'weight'):
				f,width,widget = w
				self.widget_list[i] = widget
				self.column_types.append((f,width))
			else:
				raise ColumnsError, "widget list item invalid: %s" % `w`
		
		self.dividechars = dividechars
		self.focus_col = focus_column
		self.pref_col = None
		self.min_width = min_width
		self.box_columns = box_columns
	
	def set_focus_column( self, num ):
		"""Set the column in focus by its index in self.widget_list."""
		self.focus_col = num
	
	def get_focus_column( self ):
		"""Return the focus column index."""
		return self.focus_col

	def set_focus(self, item):
		"""Set the item in focus.  
		
		item -- widget or integer index"""
		if type(item) == type(0):
			assert item>=0 and item<len(self.widget_list)
			position = item
		else:
			position = self.widget_list.index(item)
		self.focus_col = position
	
	def get_focus(self):
		"""Return the widget in focus."""
		return self.widget_list[self.focus_col]

	def column_widths( self, size ):
		"""Return a list of column widths.

		size -- (maxcol,) if self.widget_list contains flow widgets or
			(maxcol, maxrow) if it contains box widgets.
		"""
		maxcol = size[0]

		col_types = self.column_types
		# hack to support old practice of editing self.widget_list
		# directly
		lwl, lct = len(self.widget_list), len(self.column_types)
		if lwl > lct:
			col_types = col_types + [('weight',1)] * (lwl-lct)
			
		widths=[]
		
		weighted = []
		shared = maxcol + self.dividechars
		growable = 0
		
		i = 0
		for t, width in col_types:
			if t == 'fixed':
				static_w = width
			else:
				static_w = self.min_width
				
			if shared < static_w + self.dividechars:
				break
		
			widths.append( static_w )	
			shared -= static_w + self.dividechars
			if t != 'fixed':
				weighted.append( (width,i) )
		
			i += 1
		
		if not shared:
			return widths
		
		# divide up the remaining space between weighted cols
		weighted.sort()
		wtotal = sum([weight for weight,i in weighted])
		grow = shared + len(weighted)*self.min_width
		for weight, i in weighted:
			width = int( float(grow) * weight / wtotal + 0.5 )
			width = max(self.min_width, width)
			widths[i] = width
			grow -= width
			wtotal -= weight
		
		
		return widths
	
	def render(self, size, focus=False):
		"""Render columns and return canvas.

		size -- (maxcol,) if self.widget_list contains flow widgets or
			(maxcol, maxrow) if it contains box widgets.
		"""
		widths = self.column_widths( size )
		
		box_maxrow = None
		if len(size)==1 and self.box_columns:
			box_maxrow = 1
			# two-pass mode to determine maxrow for box columns
			for i in range(len(widths)):
				if i in self.box_columns:
					continue
				mc = widths[i]
				w = self.widget_list[i]
				rows = w.rows( (mc,), 
					focus = focus and self.focus_col == i )
				box_maxrow = max(box_maxrow, rows)
		
		l = []
		off = 0
		for i in range(len(widths)):
			mc = widths[i]
			w = self.widget_list[i]
			if box_maxrow and i in self.box_columns:
				sub_size = (mc, box_maxrow)
			else:
				sub_size = (mc,) + size[1:]
			
			l.append(w.render(sub_size, 
				focus = focus and self.focus_col == i) )
				
			off = mc + self.dividechars
			l.append(off)
		return CanvasJoin( l[:-1] )

	def get_cursor_coords(self, size):
		"""Return the cursor coordinates from the focus widget."""
		w = self.widget_list[self.focus_col]

		if not w.selectable():
			return None
		if not hasattr(w, 'get_cursor_coords'):
			return None

		widths = self.column_widths( size )
		colw = widths[self.focus_col]

		coords = w.get_cursor_coords( (colw,)+size[1:] )
		if coords is None:
			return None
		x,y = coords
		x += self.focus_col * self.dividechars
		x += sum( widths[:self.focus_col] )
		return x, y

	def move_cursor_to_coords(self, size, col, row):
		"""Choose a selectable column to focus based on the coords."""
		widths = self.column_widths(size)
		
		best = None
		x = 0
		for i in range(len(widths)):
			w = self.widget_list[i]
			end = x + widths[i]
			if w.selectable():
				if x > col and best is None:
					# no other choice
					best = i, x, end
					break
				if x > col and col-best[2] < x-col:
					# choose one on left
					break
				best = i, x, end
				if col < end:
					# choose this one
					break
			x = end + self.dividechars
			
		if best is None:
			return False
		i, x, end = best
		w = self.widget_list[i]
		if hasattr(w,'move_cursor_to_coords'):
			if type(col)==type(0):
				move_x = min(max(0,col-x),end-x-1)
			else:
				move_x = col
			rval = w.move_cursor_to_coords((end-x,)+size[1:],
				move_x, row)
			if rval is False:
				return False
				
		self.focus_col = i
		self.pref_col = col
		return True

	def mouse_event(self, size, event, button, col, row, focus):
		"""
		Send event to appropriate column.
		May change focus on button 1 press.
		"""
		widths = self.column_widths(size)
		
		x = 0
		for i in range(len(widths)):
			if col < x:
				return False
			w = self.widget_list[i]
			end = x + widths[i]
			
			if col >= end:
				x = end + self.dividechars
				continue

			focus = focus and self.focus_col == i
			if is_mouse_press(event) and button == 1:
				if w.selectable():
					self.set_focus(w)

			if not hasattr(w,'mouse_event'):
				return False

			return w.mouse_event((end-x,)+size[1:], event, button, 
				col - x, row, focus)
		return False
		
	def get_pref_col(self, size):
		"""Return the pref col from the column in focus."""
		maxcol = size[0]
		widths = self.column_widths( (maxcol,) )
	
		w = self.widget_list[self.focus_col]
		col = None
		if hasattr(w,'get_pref_col'):
			col = w.get_pref_col((widths[self.focus_col],)+size[1:])
			if type(col)==type(0):
				col += self.focus_col * self.dividechars
				col += sum( widths[:self.focus_col] )
		if col is None:
			col = self.pref_col
		if col is None and w.selectable():
			col = widths[self.focus_col]/2
			col += self.focus_col * self.dividechars
			col += sum( widths[:self.focus_col] )
		return col

	def rows(self, (maxcol,), focus=0 ):
		"""Return the number of rows required by the columns.
		Only makes sense if self.widget_list contains flow widgets."""
		widths = self.column_widths( (maxcol,) )
	
		rows = 1
		for i in range(len(widths)):
			if self.box_columns and i in self.box_columns:
				continue
			mc = widths[i]
			w = self.widget_list[i]
			rows = max( rows, w.rows( (mc,), 
				focus = focus and self.focus_col == i ) )
		return rows
			
	def keypress(self, size, key):
		"""Pass keypress to the focus column.

		size -- (maxcol,) if self.widget_list contains flow widgets or
			(maxcol, maxrow) if it contains box widgets.
		"""
		if self.focus_col is None: return key
		
		widths = self.column_widths( size )
		if self.focus_col < 0 or self.focus_col >= len(widths):
			return key

		i = self.focus_col
		mc = widths[i]
		w = self.widget_list[i]
		if key not in ('up','down','page up','page down'):
			self.pref_col = None
		key = w.keypress( (mc,)+size[1:], key )
		
		if key not in ('left','right'):
			return key

		if key == 'left':
			candidates = range(i-1, -1, -1) # count backwards to 0
		else: # key == 'right'
			candidates = range(i+1, len(widths))

		for j in candidates:
			if not self.widget_list[j].selectable():
				continue

			self.set_focus_column( j )
			return
		return key
			

	def selectable(self):
		"""Return the selectable value of the focus column."""
		return self.widget_list[self.focus_col].selectable()




class BoxAdapter(object):
	"""
	Adapter for using a box widget where a flow widget would usually go
	"""

	def __init__(self, box_widget, height):
		"""
		Create a flow widget that contains a box widget

		box_widget -- box widget
		height -- number of rows for box widget
		"""
		
		self.height = height
		self.box_widget = box_widget

	def rows(self, (maxcol,), focus=False):
		"""
		Return self.height
		"""
		return self.height

	def selectable(self):
		"""
		Return box widget's selectable value
		"""
		return self.box_widget.selectable()

	def get_cursor_coords(self, (maxcol,)):
		if not hasattr(self.box_widget,'get_cursor_coords'):
			return None
		return self.box_widget.get_cursor_coords((maxcol, self.height))
	
	def get_pref_col(self, (maxcol,)):
		if not hasattr(self.box_widget,'get_pref_col'):
			return None
		return self.box_widget.get_pref_col((maxcol, self.height))
	
	def keypress(self, (maxcol,), key):
		return self.box_widget.keypress((maxcol, self.height), key)
	
	def move_cursor_to_coords(self, (maxcol,), col, row):
		if not hasattr(self.box_widget,'move_cursor_to_coords'):
			return True
		return self.box_widget.move_cursor_to_coords((maxcol,
			self.height), col, row )
	
	def mouse_event(self, (maxcol,), event, button, col, row, focus):
		if not hasattr(self.box_widget,'mouse_event'):
			return False
		return self.box_widget.mouse_event((maxcol, self.height),
			event, button, col, row, focus)
	
	def render(self, (maxcol,), focus=False):
		return self.box_widget.render((maxcol, self.height), focus)
	
	def __getattr__(self, name):
		"""
		Pass calls to box widget.
		"""
		return getattr(self.box_widget, name)


