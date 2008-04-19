#!/usr/bin/python
#
# Urwid widget decoration classes
#    Copyright (C) 2004-2008  Ian Ward
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


from util import *
from widget import *


class WidgetDecoration(Widget):
	def __init__(self, original_widget):
		"""
		original_widget -- the widget being decorated

		This is a base class for decoration widgets, widgets
		that contain one or more widgets and only ever have
		a single focus.  This type of widget will affect the
		display or behaviour of the original_widget but it is
		not part of determining a chain of focus.

		Don't actually do this -- use a WidgetDecoration subclass
		instead, these are not real widgets:
		>>> WidgetDecoration(Text("hi"))
		<WidgetDecoration widget <Text flow widget 'hi' align_mode='left' wrap_mode='space'>>
		"""
		self._original_widget = original_widget
	def _repr_words(self):
		return self.__super._repr_words() + [repr(self._original_widget)]
	
	def _get_original_widget(self):
		return self._original_widget
	def _set_original_widget(self, original_widget):
		self._original_widget = original_widget
		self._invalidate()
	original_widget = property(_get_original_widget, _set_original_widget)

	def get_undecorated_widget(self):
		"""
		Return the widget without decorations.  If there is only one
		Decoration then this is the same as original_widget.

		>>> t = Text('hello')
		>>> wd1 = WidgetDecoration(t)
		>>> wd2 = WidgetDecoration(wd1)
		>>> wd3 = WidgetDecoration(wd2)
		>>> wd3.original_widget is wd2
		True
		>>> wd3.get_undecorated_widget() is t
		True
		"""
		w = self
		while hasattr(w, '_original_widget'):
			w = w._original_widget
		return w

	def selectable(self):
		return self._original_widget.selectable()



class AttrWrap(WidgetDecoration):
	"""
	AttrWrap is a decoration that changes the default attribute for a 
	FlowWidget or BoxWidget
	"""
	def __init__(self, w, attr, focus_attr = None):
		"""
		w -- widget to wrap (stored as original_widget)
		attr -- attribute to apply to w
		focus_attr -- attribute to apply when in focus, if None use attr
		
		This object will pass all function calls and variable references
		to the wrapped widget.

		>>> AttrWrap(Divider("!"), 'bright')
		<AttrWrap flow widget <Divider flow widget div_char='!'> attr='bright'>
		>>> AttrWrap(Edit(), 'notfocus', 'focus')
		<AttrWrap selectable flow widget <Edit selectable flow widget '' edit_pos=0> attr='notfocus' focus_attr='focus'>
		"""
		self.__super.__init__(w)
		self._attr = attr
		self._focus_attr = focus_attr
	
	def _repr_attrs(self):
		# only include the focus_attr when it takes effect (not None)
		d = dict(self.__super._repr_attrs(), attr=self._attr)
		if self._focus_attr is not None:
			d['focus_attr'] = self._focus_attr
		return d
	
	# backwards compatibility, widget used to be stored as w
	get_w = WidgetDecoration._get_original_widget
	set_w = WidgetDecoration._set_original_widget
	w = property(get_w, set_w)
	
	def get_attr(self):
		return self._attr
	def set_attr(self, attr):
		self._attr = attr
		self._invalidate()
	attr = property(get_attr, set_attr)
	
	def get_focus_attr(self):
		return self._focus_attr
	def set_focus_attr(self, focus_attr):
		self._focus_attr = focus_attr
		self._invalidate()
	focus_attr = property(get_focus_attr, set_focus_attr)
		
	def render(self, size, focus=False):
		"""
		Render wrapped widget and apply attribute. Return canvas.
		
		>>> size = (5,)
		>>> assert False # FIXME not running due to decorator
		>>> aw = AttrWrap(Text("hi"), 'greeting', 'fgreet')
		>>> aw.render(size, focus=False).content()[0]
		[('greeting', None, 'hi   ')]
		>>> aw.render(size, focus=True).content()[0]
		[('fgreet', None, 'hi   ')]
		"""
		attr = self.attr
		if focus and self.focus_attr is not None:
			attr = self.focus_attr
		canv = self._original_widget.render(size, focus=focus)
		canv = CompositeCanvas(canv)
		canv.fill_attr(attr)
		return canv

	def sizing(self):
		return self._original_widget.sizing()

	def __getattr__(self,name):
		"""Call getattr on wrapped widget."""
		return getattr(self._original_widget, name)


class BoxAdapterError(Exception):
	pass

class BoxAdapter(WidgetDecoration):
	"""
	Adapter for using a box widget where a flow widget would usually go
	"""
	no_cache = ["rows"]
	_sizing = set(['flow']) # flow widget

	def __init__(self, box_widget, height):
		"""
		Create a flow widget that contains a box widget

		box_widget -- box widget
		height -- number of rows for box widget
		"""
		if 'box' not in box_widget.sizing():
			raise BoxAdapterError("%r is not a box widget" % 
				box_widget)
		self.__super.__init__(box_widget)
		
		self.height = height

	box_widget = property(WidgetDecoration._get_original_widget, 
		WidgetDecoration._set_original_widget)

	def rows(self, size, focus=False):
		"""
		Return self.height
		"""
		return self.height

	def get_cursor_coords(self, size):
		(maxcol,) = size
		if not hasattr(self._original_widget,'get_cursor_coords'):
			return None
		return self._original_widget.get_cursor_coords((maxcol, self.height))
	
	def get_pref_col(self, size):
		(maxcol,) = size
		if not hasattr(self._original_widget,'get_pref_col'):
			return None
		return self._original_widget.get_pref_col((maxcol, self.height))
	
	def keypress(self, size, key):
		(maxcol,) = size
		return self._original_widget.keypress((maxcol, self.height), key)
	
	def move_cursor_to_coords(self, size, col, row):
		(maxcol,) = size
		if not hasattr(self._original_widget,'move_cursor_to_coords'):
			return True
		return self._original_widget.move_cursor_to_coords((maxcol,
			self.height), col, row )
	
	def mouse_event(self, size, event, button, col, row, focus):
		(maxcol,) = size
		if not hasattr(self._original_widget,'mouse_event'):
			return False
		return self._original_widget.mouse_event((maxcol, self.height),
			event, button, col, row, focus)
	
	def render(self, size, focus=False):
		(maxcol,) = size
		canv = self._original_widget.render((maxcol, self.height), focus)
		canv = CompositeCanvas(canv)
		return canv
	
	def __getattr__(self, name):
		"""
		Pass calls to box widget.
		"""
		return getattr(self.box_widget, name)



class PaddingError(Exception):
	pass

class Padding(Widget):
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
		self.__super.__init__()

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
			canv = self.w.render((), focus)
		else:
			canv = self.w.render((maxcol,)+size[1:], focus)
		if canv.cols() == 0:
			canv = SolidCanvas(' ', size[0], canv.rows())
			canv = CompositeCanvas(canv)
			canv.set_depends([self.w])
			return canv
		canv = CompositeCanvas(canv)
		canv.set_depends([self.w])
		if left != 0 or right != 0:
			canv.pad_trim_left_right(left, right)

		return canv

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

	def rows(self, size, focus=False ):
		"""Return the rows needed for self.w."""
		(maxcol,) = size
		if self.width_type is None:
			ignore, height = self.w.pack(focus)
			return height
		left, right = self.padding_values(size, focus)
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
		self.__super.__init__()
		vt,va,ht,ha=decompose_valign_height(valign,height,FillerError)
		
		self._body = body
		self.valign_type, self.valign_amount = vt, va
		self.height_type, self.height_amount = ht, ha
		if self.height_type not in ('fixed', None):
			self.min_height = min_height
		else:
			self.min_height = None
	
	def get_body(self):
		return self._body
	def set_body(self, body):
		self._body = body
		self._invalidate()
	body = property(get_body, set_body)
	
	def selectable(self):
		"""Return selectable from body."""
		return self._body.selectable()
	
	def filler_values(self, size, focus):
		"""Return the number of rows to pad on the top and bottom.
		
		Override this method to define custom padding behaviour."""
		(maxcol, maxrow) = size
		
		if self.height_type is None:
			height = self.body.rows((maxcol,),focus=focus)
			return calculate_filler( self.valign_type,
				self.valign_amount, 'fixed', height, 
				None, maxrow )
			
		return calculate_filler( self.valign_type, self.valign_amount,
			self.height_type, self.height_amount,
			self.min_height, maxrow)

	
	def render(self, size, focus=False):
		"""Render self.body with space above and/or below."""
		(maxcol, maxrow) = size
		top, bottom = self.filler_values(size, focus)
		
		if self.height_type is None:
			canv = self.body.render((maxcol,), focus)
		else:
			canv = self.body.render((maxcol,maxrow-top-bottom),focus)
		canv = CompositeCanvas(canv)
		
		if maxrow and canv.rows() > maxrow and canv.cursor is not None:
			cx, cy = canv.cursor
			if cy >= maxrow:
				canv.trim(cy-maxrow+1,maxrow-top-bottom)
		if canv.rows() > maxrow:
			canv.trim(0, maxrow)
			return canv
		canv.pad_trim_top_bottom(top, bottom)
		return canv


	def keypress(self, size, key):
		"""Pass keypress to self.body."""
		(maxcol, maxrow) = size
		if self.height_type is None:
			return self.body.keypress( (maxcol,), key )

		top, bottom = self.filler_values((maxcol,maxrow), True)
		return self.body.keypress( (maxcol,maxrow-top-bottom), key )

	def get_cursor_coords(self, size):
		"""Return cursor coords from self.body if any."""
		(maxcol, maxrow) = size
		if not hasattr(self.body, 'get_cursor_coords'):
			return None
			
		top, bottom = self.filler_values(size, True)
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

	def get_pref_col(self, size):
		"""Return pref_col from self.body if any."""
		(maxcol, maxrow) = size
		if not hasattr(self.body, 'get_pref_col'):
			return None
		
		if self.height_type is None:
			x = self.body.get_pref_col((maxcol,))
		else:
			top, bottom = self.filler_values(size, True)
			x = self.body.get_pref_col(
				(maxcol,maxrow-top-bottom))

		return x
	
	def move_cursor_to_coords(self, size, col, row):
		"""Pass to self.body."""
		(maxcol, maxrow) = size
		if not hasattr(self.body, 'move_cursor_to_coords'):
			return True
		
		top, bottom = self.filler_values(size, True)
		if row < top or row >= maxcol-bottom:
			return False

		if self.height_type is None:
			return self.body.move_cursor_to_coords((maxcol,),
				col, row-top)
		return self.body.move_cursor_to_coords(
			(maxcol, maxrow-top-bottom), col, row-top)
	
	def mouse_event(self, size, event, button, col, row, focus):
		"""Pass to self.body."""
		(maxcol, maxrow) = size
		if not hasattr(self.body, 'mouse_event'):
			return False
		
		top, bottom = self.filler_values(size, True)
		if row < top or row >= maxcol-bottom:
			return False

		if self.height_type is None:
			return self.body.mouse_event((maxcol,),
				event, button, col, row-top, focus)
		return self.body.mouse_event( (maxcol, maxrow-top-bottom), 
			event, button,col, row-top, focus)

		
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


def _test():
	import doctest
	doctest.testmod()

if __name__=='__main__':
	_test()
