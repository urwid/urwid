#!/usr/bin/python
#
# Urwid basic widget classes
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

import string

from util import *
from canvas import *

try: True # old python?
except: False, True = 0, 1

class FlowWidget:
	"""
	base class of widgets
	"""
	def selectable(self):
		"""Return False.  Not selectable by default."""
		return False

	def keypress(self,(maxcol,),key):
		"""Return key.  No keys are handled by default."""
		return key


class BoxWidget:
	"""
	base class of width and height constrained widgets such as
	the top level widget attached to the display object
	"""
	def keypress(self,(maxcol,maxrow),key):
		"""Return key.  No keys are handled by default."""
		return key
	


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
		self.div_char=div_char
		self.top=top
		self.bottom=bottom
		
	
	def rows(self,(maxcol,), focus=False ):
		"""Return the number of lines that will be rendered."""
		return self.top + 1 + self.bottom
	
	def render(self,(maxcol,), focus=False ):
		"""Render the divider as a canvas and return it."""
		return Canvas( [""] * self.top + 
			[ self.div_char * maxcol ] +
			[""] * self.bottom )
	
	


class Text(FlowWidget):
	"""
	a horizontally resizeable text widget
	"""
	wrap_mode = 'space'
	align_mode = 'left'
	
	def __init__(self,markup, align=None, wrap=None):
		"""
		markup -- content of text widget, one of:
			plain string -- string is displayed
			( attr, markup2 ) -- markup2 is given attribute attr
			[ markupA, markupB, ... ] -- list items joined together
		align -- align mode or None (widget will use Text.align_mode)
		wrap -- wrap mode or None (widget will use Text.wrap_mode)
		"""
		self._cache_maxcol = None
		self.set_text(markup)
		if align: self.set_align_mode(align)
		if wrap: self.set_wrap_mode(wrap)
	
	def set_text(self,markup):
		"""Set content of text widget."""
		self.text, self.attrib = decompose_tagmarkup(markup)
		self._cache_maxcol = None

	def get_text(self):
		"""get_text() -> text, attributes
		
		text -- complete string content of text widget
		attributes -- run length encoded attributes for text
		"""
		return self.text, self.attrib

	def set_align_mode(self, mode):
		"""
		Set text alignment / justification.  Valid modes include:
			'left', 'center', 'right'
		"""
		assert valid_align_mode(mode)
		if mode == self.align_mode: return
		self.align_mode = mode
		self._cache_maxcol = None

	def set_wrap_mode(self, mode):
		"""
		Set wrap mode.  Valid modes include:
			'any'	: wrap at any character
			'space'	: wrap on space character
			'clip'	: truncate lines instead of wrapping
		"""
		assert valid_wrap_mode(mode)
		if mode == self.wrap_mode: return
		self.wrap_mode = mode
		self._cache_maxcol = None

	def render(self,(maxcol,), focus=False):
		"""
		Render contents with wrapping and alignment.  Return canvas.
		"""

		if maxcol == self._cache_maxcol:
			text, attr = self.get_text()
		else:	# update self._cache_translation
			text, attr = self._update_cache_translation( maxcol )
			
		l = []
		pos = 0
		for l_pad, l_trim, r_trim, epos in self._cache_translation:
			line = text[pos:epos]
			pos = epos
			# apply trim and pad
			line = " "*l_pad + line[l_trim:len(line)-r_trim]
			l.append( line )
			
		a = split_attribute_list( attr, self._cache_translation )
		
		return Canvas(l,a)
		

	def rows(self,(maxcol,), focus=False):
		"""Return the number of rows the rendered text spans."""
		return len(self.get_line_translation(maxcol))

	def get_line_translation(self,maxcol):
		"""Return line translation for mapping self.text to a canvas.

		The line translation is a list of (l_pad, l_trim, r_trim, epos) 
		tuples. Each tuple in the line translation represents one row.
		l_pad -- number of spaces to add on the left of the line
		l_trim -- number of characters to remove from left of line
		r_trim -- number of characters to remove from right of line
		epos -- character index at the end of the line (start of next)
		"""
		# uses cached translation if available.  If set_text is not
		# used (eg. in subclass) set self._cache_maxcol to None
		# to None before calling this method.
		
		if not self._cache_maxcol or self._cache_maxcol != maxcol:
			self._update_cache_translation(maxcol)
		return self._cache_translation

	def _update_cache_translation(self,maxcol):
		text, attr = self.get_text()
		self._cache_maxcol = maxcol
		self._cache_translation = self._calc_line_translation(
			text, maxcol )
		return text, attr
	
	def _calc_line_translation(self, text, maxcol ):
		return calculate_line_translation(
			text, self._cache_maxcol, 
			self.wrap_mode, self.align_mode )

class Edit(Text):
	"""Text edit widget"""
	
	def valid_char(self, ch):
		"""Return true for printable characters."""
		if double_byte_encoding and len(ch)==2 and ord(ch[0])>0xA1:
			return True
		return len(ch)==1 and ord(ch) >= 32
	
	def selectable(self): return 1

	def __init__(self, caption = "", edit_text = "", multiline = False,
			align = None, wrap = None, allow_tab = False):
		"""
		caption -- markup for caption preceeding edit_text
		edit_text -- text string for editing
		multiline -- True: 'enter' inserts newline  False: return it
		align -- align mode
		wrap -- wrap mode
		allow_tab -- True: 'tab' inserts 1-8 spaces  False: return it
		"""
		
		Text.__init__(self,"", align, wrap)
		assert type(edit_text) == type("")
		self.set_caption( caption )
		self.edit_text = edit_text
		self.multiline = multiline
		self.allow_tab = allow_tab
		self.edit_pos = len(edit_text)
		self.highlight = None
		self.pref_col_maxcol = None, None
		self._shift_view_to_cursor = 0
	
	def get_text(self):
		"""get_text() -> text, attributes
		
		text -- complete text of caption and edit_text
		attributes -- run length encoded attributes for text
		"""
		return self.caption + self.edit_text, self.attrib
	
	def get_pref_col(self, (maxcol,)):
		"""Return the preferred column for the cursor, or None."""
		pref_col, then_maxcol = self.pref_col_maxcol
		if then_maxcol != maxcol:
			return None
		else:
			return pref_col
	
	def update_text(self):
		"""Deprecated.  Use set_caption and/or set_edit_text instead.
		
		Make sure any cached line translation is not reused."""
		self._cache_maxcol = None

	def set_caption(self, caption):
		"""Set the caption markup for this widget."""
		self.caption, self.attrib = decompose_tagmarkup(caption)
		self.update_text()
	
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
		self.update_text()
	
	def insert_text(self, text):
		"""Insert text at the cursor position and update cursor."""
		p = self.edit_pos
		self.edit_text = self.edit_text[:p] + text + self.edit_text[p:]
		self.update_text()
		self.set_edit_pos( self.edit_pos + len(text))
	
	def keypress(self,(maxcol,),key):
		"""Handle editing keystrokes, return others."""

		p = self.edit_pos
		if self.valid_char(key):
			self._delete_highlighted()
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
			p -= 1
			if self.within_double_byte(maxcol, p) == 2:
				p -= 1
			self.set_edit_pos(p)
		
		elif key=="right":
			if p >= len(self.edit_text): return key
			p += 1
			if self.within_double_byte(maxcol, p) == 2:
				p += 1
			self.set_edit_pos(p)
		
		elif key in ("up","down"):
			self.highlight = None
			
			x,y = self.get_cursor_coords((maxcol,))
			pref_col = self.get_pref_col((maxcol,))
			if pref_col is None: 
				pref_col = x

			if key == "up": y -= 1
			else:		y += 1

			if not self.move_cursor_to_coords((maxcol,),pref_col,y):
				return key
		
		elif key=="backspace":
			self._delete_highlighted()
			self.pref_col_maxcol = None, None
			p = self.edit_pos-1
			if p == -1:
				return key
			if self.within_double_byte(maxcol, p) == 2:
				p -= 1
			self.edit_text = ( self.edit_text[:p] + 
				self.edit_text[self.edit_pos:] )
			self.edit_pos = p
			self.update_text()

		elif key=="delete":
			self._delete_highlighted()
			self.pref_col_maxcol = None, None
			p = self.edit_pos+1
			if p > len(self.edit_text):
				return key
			if self.within_double_byte(maxcol, p) == 2:
				p += 1
			self.edit_text = ( self.edit_text[:self.edit_pos] + 
				self.edit_text[p:] )
			self.update_text()
		
		elif key in ("home", "end"):
			self.highlight = None
			self.pref_col_maxcol = None, None
			
			trans = self.get_line_translation(maxcol)
			x,y = self.get_cursor_coords((maxcol,))
			
			if key == "home":
				hpos = 0
				if y > 0:
					hpos = trans[y-1][-1]
				self.edit_pos = max(hpos - len(self.caption), 0)
			else:
				epos = trans[y][-1] -1
				if y == len(trans)-1:
					epos += 1
				epos -= len(self.caption)
				if self.within_double_byte(maxcol, epos) == 2:
					epos -= 1
				self.edit_pos = epos 
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

		pos = calculate_pos( trans, x, y )
		e_pos = pos - len(self.caption)
		if e_pos < 0: e_pos = 0
		if e_pos > len(self.edit_text): e_pos = len(self.edit_text)
		if self.within_double_byte(maxcol, e_pos) == 2:
			e_pos -= 1
		self.edit_pos = e_pos
		self.pref_col_maxcol = x, maxcol
		return True


	def _delete_highlighted(self):
		"""
		Delete all highlighted text and update cursor position, if any
		text is highlighted.
		"""
		if not self.highlight: return
		start, stop = self.highlight
		btext, etext = self.edit_text[:start], self.edit_text[stop:]
		self.edit_text = btext + etext
		self.update_text()
		self.edit_pos = start
		self.highlight = None
		
		
	def render(self,(maxcol,), focus=False):
		""" 
		Render edit widget and return canvas.  Include cursor when in
		focus.
		"""
		
		if focus and self.wrap_mode == 'clip':
			# keep the cursor visible on clipped edit fields
			self._shift_view_to_cursor = 1
			self._cache_maxcol = None
		elif self._shift_view_to_cursor:
			self._shift_view_to_cursor = 0
			self._cache_maxcol = None
		
		d = Text.render(self,(maxcol,))
		if focus:
			d.cursor = self.get_cursor_coords((maxcol,))
		# .. will need to FIXME if I want highlight to work again
		#if self.highlight:
		#	hstart, hstop = self.highlight_coords()
		#	d.coords['highlight'] = [ hstart, hstop ]
		
		return d
	
	def _calc_line_translation(self, text, maxcol ):
		trans = Text._calc_line_translation(self, text, maxcol)
		if not self._shift_view_to_cursor: 
			return trans
		
		x,y = position_to_coords( self.edit_pos + len(self.caption), trans, clamp=0 )
		if x < 0:
			return shift_translation_right( trans, -x, maxcol )
		elif x >= maxcol:
			return shift_translation_left( trans, x-maxcol+1, maxcol )
		else:
			return trans
			

	def get_cursor_coords(self,(maxcol,)):
		"""Return the (x,y) coordinates of cursor within widget."""

		if self.wrap_mode == 'clip':
			# keep the cursor visible on clipped edit fields
			self._shift_view_to_cursor = 1
			self._cache_maxcol = None

		return self.position_coords(maxcol,self.edit_pos)
	
	
	def position_coords(self,maxcol,pos):
		"""
		Return (x,y) coordinates for an offset into self.edit_text.
		"""
		
		p = pos + len(self.caption)
		trans = self.get_line_translation(maxcol)
		x,y = position_to_coords(p,trans)
		if x >= maxcol: x = maxcol-1
		return x,y


	def within_double_byte(self, maxcol, pos):
		"""
		Return whether pos is on a double-byte character.

		Return values:
		0 -- not within or double byte encoding not enabled
		1 -- on the 1st half
		2 -- on the 2nd half
		"""
		
		# try to do as little work as possible
		if not double_byte_encoding: return 0
		if pos < 0 or pos >= len(self.edit_text): return 0
		if ord(self.edit_text[pos]) < 0xA1: return 0
		
		x,y = self.position_coords(maxcol, pos)
		trans = self.get_line_translation(maxcol)

		epos = 0
		if y>0: epos = trans[y-1][3]
		
		text, attr = self.get_text()
		return within_double_byte(text, epos, pos + len(self.caption))
		




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
	                        self.edit_pos = self.edit_pos - 1
	                        self.edit_text = self.edit_text[1:]
				self.update_text()

	        unhandled = Edit.keypress(self,(maxcol,),key)

		return unhandled

	def value(self):
		"""Return the numeric value of self.edit_text."""
		if self.edit_text:
			return long(self.edit_text)
		else:
			return 0


class Filler(BoxWidget):
	def __init__(self, body, valign="middle"):
		"""
		body -- a flow widget to be filled around
		valign -- vertical alignment: "top", "middle" or "bottom"
		"""
		self.body = body
		assert valign in ("top","middle","bottom")
		self.valign = valign
	
	def render(self, (maxcol,maxrow), focus=False):
		"""Render self.body with space around it to fill box size."""
		c = self.body.render( (maxcol,), focus )
		
		cy = None
		if c.cursor is not None:
			cx, cy = c.cursor
		
		pos = self.body_position((maxcol,maxrow), focus, c.rows(), cy )

		# need to trim top of self.body
		if pos < 0:
			c.trim( -pos, maxrow )
			return c
		top = Canvas(["" for i in range(pos)])
		
		# may need to trim bottom of self.body
		if pos + c.rows() >= maxrow:
			return CanvasCombine( [top, c] ).trim(0, maxrow)
		
		# add padding to bottom
		bottom = Canvas(["" for i in range(maxrow-c.rows()-pos)])
		return CanvasCombine( [top, c, bottom] )


	def keypress(self, (maxcol,maxrow), key):
		"""Pass keypress to self.body."""
		return self.body.keypress( (maxcol,), key )


	def body_position(self, (maxcol, maxrow), focus, rows=None, cy=None):
		"""
		Return the row offset (+ve) or reduction (-ve) of self.body.
		"""
		
		if cy is None and focus:
			if hasattr(self.body,'get_cursor_coords'):
				cx, cy = self.body.get_cursor_coords((maxcol,))

		# need to trim rows on top
		if cy is not None and cy >= maxrow:
			return maxrow-cy-1

		if self.valign == "top":
			return 0

		if rows is None:
			rows = self.body.rows((maxcol,), focus)
		if rows >= maxrow:
			return 0
		
		remaining = maxrow - rows

		if self.valign == "middle":
			return remaining / 2
		else: # valign == "bottom"
			return remaining
		
	
		
		


class Frame(BoxWidget):
	def __init__(self, body, header=None, footer=None):
		"""
		body -- a box widget for the body of the frame
		header -- a flow widget for above the body (or None)
		footer -- a flow widget for below the body (or None)
		"""
		self.header = header
		self.body = body
		self.footer = footer

	def render(self, (maxcol,maxrow), focus=False):
		"""Render frame and return it."""
		head = foot = Canvas()
		if self.header is not None:
			head = self.header.render((maxcol,))
		if self.footer is not None:
			foot = self.footer.render((maxcol,))
		
		remaining = maxrow - head.rows() - foot.rows()
		if remaining <= 0:
			return CanvasCombine([head,foot]).trim(0,maxrow)
		
		bod = self.body.render( (maxcol, remaining), focus=focus )
		d = CanvasCombine( [head,bod,foot] )
		return d

	def keypress(self, (maxcol,maxrow), key):
		"""Pass keypress to body widget."""
		remaining = maxrow
		if self.header is not None:
			remaining -= self.header.rows((maxcol,))
		if self.footer is not None:
			remaining -= self.footer.rows((maxcol,))
		if remaining <= 0: return key
	
		return self.body.keypress( (maxcol, remaining), key )


class AttrWrap:
	"""
	AttrWrap is a decorator that changes the default attribute for a 
	FlowWidget or BoxWidget
	"""
	def __init__(self, w, attr, focus_attr = None):
		"""
		w -- widget to wrap
		attr -- attribute to apply to w
		focus_attr -- attribute to apply when in focus, if None use attr
		
		Copy w.get_cursor_coords, w.move_cursor_to_coords, 
		w.get_pref_col functions to this widget if they exist.
		"""
		self.w = w
		self.attr = attr
		self.focus_attr = focus_attr
		if hasattr(self.w,'get_cursor_coords'):
			self.get_cursor_coords = self.w.get_cursor_coords
		if hasattr(self.w,'move_cursor_to_coords'):
			self.move_cursor_to_coords=self.w.move_cursor_to_coords
		if hasattr(self.w,'get_pref_col'):
			self.get_pref_col = self.w.get_pref_col
	
	def render(self, size, focus = False ):
		"""Render self.w and apply attribute. Return canvas.
		
		size -- (maxcol,) if self.w contains a flow widget or
			(maxcol, maxrow) if it contains a box widget.
		"""
		attr = self.attr
		if focus and self.focus_attr is not None:
			attr = self.focus_attr
		r = self.w.render( size, focus=focus )
		r.attr = fill_attribute_list( r.attr, size[0], attr )
		cols = size[0]
		r.text = [x.ljust(cols) for x in r.text]
		return r

	def selectable(self):
		"""Return the selectable value of self.w."""
		return self.w.selectable()

	def rows(self, (maxcol,), focus=False ):
		"""Return the rows needed for self.w."""
		return self.w.rows( (maxcol,), focus=focus )
	
	def keypress(self, maxvals, key):
		"""Pass keypress to self.w."""
		return self.w.keypress(maxvals, key)
	

		
class Pile(FlowWidget):
	def __init__(self, widget_list):
		"""
		widget_list -- list of flow widgets
		"""
		
		self.widget_list = widget_list
		self.maxcol = None
	
	def render(self, (maxcol,), focus=False):
		"""
		Render all widgets in self.widget_list and return the results
		stacked one on top of the next.
		"""
		return CanvasCombine(
			[ w.render((maxcol,), focus=False) 
				for w in self.widget_list ])
		
	def rows(self, (maxcol,), focus=False ):
		"""Return the number of rows required for this widget."""
		rows = 0
		for w in self.widget_list:
			rows = rows+w.rows( (maxcol,) )
		return rows

		
class Columns: # either FlowWidget or BoxWidget
	def __init__(self, widget_list, dividechars=0):
		"""
		widget_list -- list of flow widgets or list of box widgets
		dividechars -- blank characters between columns
		"""
		self.widget_list = widget_list
		self.dividechars = dividechars
		self.focus_col = 0
	
	def set_focus_column( self, num ):
		"""Set the column in focus by its index in self.widget_list."""
		self.focus_col = num
	
	def get_focus_column( self ):
		"""Return the focus column index."""
		return self.focus_col
	
	def column_widths( self, size ):
		"""Return a list of column character widths.

		size -- (maxcol,) if self.widget_list contains flow widgets or
			(maxcol, maxrow) if it contains box widgets.
		"""
		if len(size) == 1:
			(maxcol,) = size
		else:
			(maxcol, maxrow) = size
		
		widths=[]
		
		k = len(self.widget_list)
		maxcol -= (k-1) * self.dividechars
		for w in self.widget_list:
			portion = int(maxcol/k)
			if portion <= 0: break
			k -= 1
			maxcol -= portion
			
			widths.append(portion)
		
		return widths
	
	def render(self, size, focus=False):
		"""Render columns and return canvas.

		size -- (maxcol,) if self.widget_list contains flow widgets or
			(maxcol, maxrow) if it contains box widgets.
		"""
		widths = self.column_widths( size )
		
		l = []
		off = 0
		for i in range(len(widths)):
			mc = widths[i]
			w = self.widget_list[i]
			if len(size) == 1:
				sub_size = (mc,)
			else:
				sub_size = (mc, size[1])
				
			if focus and self.focus_col == i:
				l.append(w.render(sub_size, focus=1))
			else:
				l.append(w.render(sub_size, focus=0))
				
			off = mc + self.dividechars
			l.append(off)
		return CanvasJoin( l[:-1] )
	
	def rows(self, (maxcol,), focus=0 ):
		"""Return the number of rows required by the columns.
		Only makes sense if self.widget_list contains flow widgets."""
		widths = self.column_widths( (maxcol,) )
	
		rows = 0
		for i in range(len(widths)):
			mc = widths[i]
			w = self.widget_list[i]
			if focus and self.focus_col == i:
				rows = max(rows, w.rows( (mc,), focus=1 ))
			else:
				rows = max(rows, w.rows( (mc,), focus=0 ))
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
		if len(size) == 1:
			return w.keypress( (mc,), key )
		else:
			return w.keypress( (mc, size[1]), key )

	def selectable(self):
		"""Return the selectable value of the focus column."""
		return self.widget_list[self.focus_col].selectable()






class _test:
	def __init__(self):
		from curses_display import Screen
	
		list = []
		for x in range(ord('a'),ord('z')+1):
			list.append( Edit("-- %s --\n"% chr(x),"...",1))
		list.append( Divider("~",0,1) )
		for x in range(1,10):
			list.append( Text(("%d"%x)*5*x) )
			list.append( Divider() )
		for x in range(ord('A'),ord('Z')+1):
			list.append( Edit("%s : "% chr(x)) )
		
		self.listbox = ListBox(list)
		self.header = Text("")
		self.top = Frame(self.header,self.listbox)

		self.ui = Screen()
		self.ui.register_palette([
			('command', 'light blue', 'black'),
			('key', 'light cyan', 'black'),
			])
		
		self.ui.run_wrapper(self.run)
		
	def run(self):
		self.resize()
		self.draw()

		k = 0
		while k!='q':
			k = self.ui.inchar()
			unhandled = self.listbox.keypress(k)
			if not unhandled:
				self.resize()
				self.draw()

	def resize(self):
		self.cols, self.rows = self.ui.get_cols_rows()
		l = [	Text(('command',"rows:")),
			Text(('key',`self.rows`)),
			Text(('command',"cols:")),
			Text(('key',`self.cols`)),
			Text(('command',"selected:")),
			Text(('key',`self.listbox.selected`)),
			Text(('command',"rowoffset:")),
			Text(('key',`self.listbox.rowoffset`)),
			]
		self.top.header = Columns(l)

		self.top.resize(self.cols, self.rows)
		
	def draw(self):
		self.ui.draw_screen( self.top.render() )

	

if '__main__'==__name__:
	_test()
