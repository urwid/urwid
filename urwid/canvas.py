#!/usr/bin/python
#
# Urwid canvas class and functions
#    Copyright (C) 2004-2006  Ian Ward
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

from __future__ import nested_scopes
from util import *

try: True # old python?
except: False, True = 0, 1


class CanvasError(Exception):
	pass

class Canvas:
	"""
	class for storing rendered text and attributes
	"""
	def __init__(self,text = None,attr = None,cursor = None,maxcol=None):
		"""
		text -- list of strings, one for each line
		attr -- list of run length encoded attributes for text
		cursor -- (x,y) of cursor or None
		maxcol -- screen columns taken by this canvas
		"""
		if text == None: 
			text = []
		widths = []
		for t in text:
			if type(t) != type(""):
				raise CanvasError("Canvas text must be plain strings encoded in the screen's encoding")
			widths.append( calc_width( t, 0, len(t)) )

		if maxcol is None:
			if widths:
				# find maxcol ourselves
				maxcol = max(widths)
			else:
				maxcol = 0

		if attr == None: 
			attr = [[] for x in range(len(text))]
		
		# pad text and attr to maxcol
		for i in range(len(text)):
			w = widths[i]
			if w > maxcol: 
				raise CanvasError("Canvas text is wider than the maxcol specified \n%s\n%s\n%s"%(`maxcol`,`widths`,`text`))
			if w < maxcol:
				text[i] = text[i] + " "*(maxcol-w)
			a_gap = len(text[i]) - attr_run( attr[i] )
			if a_gap < 0:
				raise CanvasError("Attribute extends beyond text \n%s\n%s" % (`text[i]`,`attr[i]`) )
			if a_gap:
				attr_append( attr[i], (None, a_gap))
			
		
		self.attr = attr
		self.cursor = cursor
		self.text = text
		self.maxcol = maxcol

	def rows(self):
		"""Return the number of rows in this canvas."""
		return len(self.text)

	def cols(self):
		"""Return the screen column width of this canvas."""
		return self.maxcol
	
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

	def fill_attr(self, a):
		"""
		Apply attribute a to all areas of this canvas with
		attribute currently set to None, leaving other attributes
		intact."""
		
		for l in self.attr:
			for j in range(len(l)):
				old_a, run = l[j]
				if old_a is None:
					l[j] = (a, run)
		

	def overlay(self, other, left, right, top, bottom ):
		"""Overlay other onto this canvas."""
		maxcol = self.maxcol
		
		width = maxcol-left-right
		height = self.rows()-top-bottom
		
		assert other.rows() == height, "top canvas of overlay not the size expected!" + `other.rows(),top,bottom,height`
		assert other.cols() == width, "top canvas of overlay not the size expected!" + `other.cols(),left,right,width`

		self.cursor = other.cursor
		self.translate_coords( left, top )

		i = top # row index
		for text, attr in zip(other.text, other.attr):
			oldt = self.text[i]
			olda = self.attr[i]
			
			if left:
				lt, a = trim_text_attr( oldt, olda, 0, left )
				t = lt + text
				attr_join(a, attr)
			else:
				t, a = text, attr

			if right:
				rt, ra = trim_text_attr( oldt, olda, 
					maxcol-right, maxcol )
				t = t + rt
				attr_join(a, ra)
			
			self.text[i] = t
			self.attr[i] = a

			i += 1


def CanvasCombine(l):
	"""Stack canvases in l vertically and return resulting canvas."""
	t = []
	a = []
	rows = 0
	cols = 0
	cursor = None
	for r in l:
		t += r.text
		a += r.attr
		cols = max(cols, r.cols())
		if r.cursor:
			x,y = r.cursor
			cursor = x, y+rows
		rows = len( t )
	d = Canvas(t, a, cursor, cols )
	return d


def CanvasJoin(l):
	"""Join canvases in l horizontally. Return result.

	l -- [canvas1, colnum2, canvas2, ... ,colnumN, canvasN]
		colnumX is the screen column count between the start of
		canvas(X-1) and canvasX, colnumX >= canvas(X-1).cols()
	"""
	
	# make silly parameter slightly less silly
	l = [0] + l
	l2 = [( l[i], l[i+1] ) for i in range(0,len(l),2)]
	
	t = []
	a = []
	
	rows = max([c.rows() for coff, c in l2])
	for r in range(rows):
		t.append([])
		a.append([])
	
	x = 0 # current start screen col, from coff
	xw = 0 # current end screen col from x and canvas width
	cursor = None
	for coff, c in l2:
		x += coff
		if x < xw: 
			raise CanvasError("Join colnum < width of canvas")
		if x > xw:
			pad = x-xw
			tpad = " "*pad
			for r in range(rows):
				t[r].append(tpad)
				attr_append(a[r],(None,pad))
		xw = x + c.cols()
		i = 0
		while i < c.rows():
			t[i].append(c.text[i])
			attr_join( a[i], c.attr[i] )
			i += 1
		if i < rows:
			pad = c.cols()
			tpad = " "*pad
			while i < rows:
				t[i].append(tpad)
				attr_append(a[i],(None,pad))
				i += 1 
		if c.cursor:
			c.translate_coords(x, 0)
			cursor = c.cursor
	d = Canvas( ["".join(lt) for lt in t], a, cursor, xw )
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

def attr_append( attr, (a, r) ):
	"""
	Append (a,r) to the attribute list attr.
	Merge with last run when possible.
	
	MODIFIES attr parameter contents. Returns None.
	"""
	if not attr or attr[-1][0] != a:
		attr.append( (a,r) )
		return
	la,lr = attr[-1]
	attr[-1] = (a, lr+r)

def attr_join( attr, attr2 ):
	"""
	Append attribute list attr2 to attr.
	Merge last run of attr with first run of attr2 when possible.

	MODIFIES attr parameter contents. Returns None.
	"""
	if not attr2:
		return
	attr_append(attr, attr2[0])
	attr += attr2[1:]
		
def apply_text_layout( text, attr, ls, maxcol ):
	utext = type(text)==type(u"")
	t = []
	a = []
	
	class AttrWalk:
		pass
	aw = AttrWalk
	aw.k = 0 # counter for moving through elements of a
	aw.off = 0 # current offset into text of attr[ak]
	
	def arange( start_offs, end_offs ):
		"""Return an attribute list for the range of text specified."""
		if start_offs < aw.off:
			aw.k = 0
			aw.off = 0
		o = []
		while aw.off < end_offs:
			if len(attr)<=aw.k:
				# run out of attributes
				o.append((None,end_offs-max(start_offs,aw.off)))
				break
			at,run = attr[aw.k]
			if aw.off+run <= start_offs:
				# move forward through attr to find start_offs
				aw.k += 1
				aw.off += run
				continue
			if end_offs <= aw.off+run:
				o.append((at, end_offs-max(start_offs,aw.off)))
				break
			o.append((at, aw.off+run-max(start_offs, aw.off)))
			aw.k += 1
			aw.off += run
		return o

	
	for line_layout in ls:
		# trim the line to fit within maxcol
		line_layout = trim_line( line_layout, text, 0, maxcol )
		
		line = []
		linea = []
		def attradd( at, run ):
			assert run>0
			if not linea or linea[-1][0] != at:
				linea.append((at, run))
			else:
				linea[-1] = (at, linea[-1][1]+run)
			
		def attrrange( start_offs, end_offs, destw ):
			"""
			Add attributes based on attributes between
			start_offs and end_offs. 
			"""
			if start_offs == end_offs:
				[(at,run)] = arange(start_offs,end_offs)
				attradd( at, destw )
				return
			if destw == end_offs-start_offs:
				for at, run in arange(start_offs,end_offs):
					attradd( at, run )
				return
			# encoded version has different width
			o = start_offs
			for at, run in arange(start_offs, end_offs):
				if o+run == end_offs:
					attradd( at, destw )
					return
				tseg = text[o:o+run]
				segw = len(tseg.encode(target_encoding))
				attradd( at, segw )
				o += run
				destw -= segw
			
			
		for seg in line_layout:
			#if seg is None: assert 0, ls
			s = LayoutSegment(seg)
			if s.end:
				if utext:
					tseg = text[s.offs:s.end].encode(
						target_encoding)
					line.append(tseg)
					attrrange(s.offs, s.end, len(tseg))
				else:
					line.append(text[s.offs:s.end])
					attrrange(s.offs, s.end, s.end-s.offs )
			elif s.text:
				if type(s.text) == type(u""):
					tseg = s.text.encode( target_encoding )
				else:
					tseg = s.text
				line.append(tseg)
				attrrange( s.offs, s.offs, len(tseg) )
			elif s.offs:
				if s.sc:
					line.append(" "*s.sc)
					attrrange( s.offs, s.offs, s.sc )
			else:
				line.append(" "*s.sc)
				linea.append((None, s.sc))
			
		t.append("".join(line))
		a.append(linea)
		
	return Canvas(t,a, maxcol=maxcol)
