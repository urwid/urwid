#!/usr/bin/python
#
# Urwid canvas class and functions
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


try: True # old python?
except: False, True = 0, 1

from util import *

class Canvas:
	"""
	class for storing rendered text and attributes
	"""
	def __init__(self, text = None, attr = None, cursor = None):
		"""
		text -- list of strings, one for each line
		attr -- list of run length encoded attributes for text
		cursor -- (x,y) of cursor or None
		"""
		if text == None: 
			text = []
		if attr == None: 
			attr = [[] for x in range(len(text))]
		self.text = text
		self.attr = attr
		self.cursor = cursor

	def rows(self):
		"""Return the number of rows in this canvas."""
		return len(self.text)

	
	def translate_coords(self,dx,dy):
		"""Shift cursor coords by (dx, dy)."""
		if self.cursor:
			x, y = self.cursor
			self.cursor = x+dx, y+dy
	
	
	def trim(self, top, count=None):
		"""Trim lines from the top and/or bottom of canvas.

		top -- number of lines to remove from top
		count -- number of lines to keep, or None for all the rest
		"""
		assert top >= 0, "invalid trim amount %d!"%top
		assert top < len(self.text), "cannot trim %d lines from %d!"%(
			top, len(self.text))
		if top:
			self.translate_coords(0,-top)
			
		if count is None:
			self.text = self.text[top:]
			self.attr = self.attr[top:]
		else:
			self.text = self.text[top:top+count]
			self.attr = self.attr[top:top+count]
		
		
	def trim_end(self, end):
		"""Trim lines from the bottom of the canvas.
		
		end -- number of lines to remove from the end
		"""
		assert end > 0, "invalid trim amount %d!"%end
		assert end < len(self.text), "cannot trim %d lines from %d!"%(
			end, len(self.text))
		self.text = self.text[:-end]
		self.attr = self.attr[:-end]

	def overlay(self, other, left, right, top, bottom, 
			maxcol ): #FIXME add width to canvas so this not needed
		"""Overlay other onto this canvas."""
		
		width = maxcol-left-right
		height = self.rows()-top-bottom
		
		assert other.rows() == height, "top canvas of overlay not the size expected!" + `other.rows(),top,bottom,height`

		if other.cursor is None:
			self.cursor = None
		else:
			cx, cy = other.cursor
			self.cursor = cx+left, cy+top

		def l_append( l, a, r ):
			if l[-1:]:
				tail_a, tail_r = l[-1]
				# combine runs of same attribute
				if tail_a == a:
					l[-1] = (a, tail_r + r)
					return
			l.append((a,r))
				

		i = top # row index
		for text, attr in zip(other.text, other.attr):
			old = self.text[i].ljust(maxcol)

			if within_double_byte(old,0,maxcol-right-1)==1:
				old = old[:maxcol-right]+" "+old[maxcol-right+1:]
			if within_double_byte(old,0,left)==2:
				old = old[:left-1]+" "+old[left:]
			
			self.text[i] = ( old[:left] + text.ljust(width) + 
					 old[left+width:] )
			
			l = [] # destination attribute row
			j = 0 # columns into destination attribute row
			k = 0 # columns into oldattr row
			oldattr = self.attr[i][:]
			while oldattr and j<left:
				a,r = oldattr.pop(0)
				k += r
				r = min( left-j, r )
				l_append( l, a, r )
				j += r
			if j < left:
				l.append( (None, left-j) )
				j = left
			for na,r in attr:
				l_append( l, na, r )
				j += r
			if j < maxcol-right:
				r = maxcol-right-j
				l_append( l, None, r )
				j+= r
			if j < k:
				r = k-j
				l_append( l, a, r )
				j += r
			while oldattr and k<maxcol-right:
				a,r = oldattr.pop(0)
				k += r
				if k > maxcol-right:
					r = k - (maxcol-right)
					l_append( l, a, r )
			for a,r in oldattr:
				l_append( l, a, r )
			# trim trailing "None"s
			if l[-1:]:
				tail_a, tail_r = l[-1]
				if tail_a is None:
					l = l[:-1]
			self.attr[i] = l
			
			#assert right, `self.text[i],l, self.attr[i+1:i+3]`

			i += 1


def CanvasCombine(l):
	"""Stack canvases in l vertically and return resulting canvas."""
	d = Canvas()
	rows = 0
	for r in l:
		d.text += r.text
		d.attr += r.attr
		if r.cursor:
			r.translate_coords(0,rows)
			d.cursor = r.cursor
		rows = len( d.text )
	return d


def CanvasJoin(l):
	"""Join canvases in l horizontally. Return result.

	l -- [canvas1, colnum2, canvas2, ... ,colnumN, canvasN]
		colnumX is the column number to start for canvasX
	"""
	
	l = [0] + l
	l2 = [( l[i], l[i+1] ) for i in range(0,len(l),2)]
	
	d = Canvas()
	hoff = 0
	for coff, r in l2:
		hoff += coff
		for i in range(len(r.text)):
			if len(d.text) == i: 
				d.text.append("")
				d.attr.append([])
			t_run = len(d.text[i])
			d.text[i] += " " * (hoff - t_run) + r.text[i]
			a_run = attr_run(d.attr[i])
			if hoff > a_run:
				d.attr[i].append( (None, hoff-a_run) )
			d.attr[i] += r.attr[i]

		if r.cursor:
			r.translate_coords(hoff,0)
			d.cursor = r.cursor
	return d


def attr_run( attr ):
	"""
	Return the number of characters covered by a run length
	encoded attribute list.
	"""
	
	run = 0
	for a, r in attr:
		run += r
	return run
