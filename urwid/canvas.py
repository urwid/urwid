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
from escape import * 

try: True # old python?
except: False, True = 0, 1


class CanvasError(Exception):
	pass

class Canvas:
	"""
	class for storing rendered text and attributes
	"""
	def __init__(self,text = None,attr = None, cs = None, 
		cursor = None, maxcol=None, check_width=True):
		"""
		text -- list of strings, one for each line
		attr -- list of run length encoded attributes for text
		cs -- list of run length encoded character set for text
		cursor -- (x,y) of cursor or None
		maxcol -- screen columns taken by this canvas
		"""
		if text == None: 
			text = []

		if check_width:
			widths = []
			for t in text:
				if type(t) != type(""):
					raise CanvasError("Canvas text must be plain strings encoded in the screen's encoding", `text`)
				widths.append( calc_width( t, 0, len(t)) )
		else:
			assert type(maxcol) == type(0)
			widths = [maxcol] * len(text)

		if maxcol is None:
			if widths:
				# find maxcol ourselves
				maxcol = max(widths)
			else:
				maxcol = 0

		if attr == None: 
			attr = [[] for x in range(len(text))]
		if cs == None:
			cs = [[] for x in range(len(text))]
		
		# pad text and attr to maxcol
		for i in range(len(text)):
			w = widths[i]
			if w > maxcol: 
				raise CanvasError("Canvas text is wider than the maxcol specified \n%s\n%s\n%s"%(`maxcol`,`widths`,`text`))
			if w < maxcol:
				text[i] = text[i] + " "*(maxcol-w)
			a_gap = len(text[i]) - rle_len( attr[i] )
			if a_gap < 0:
				raise CanvasError("Attribute extends beyond text \n%s\n%s" % (`text[i]`,`attr[i]`) )
			if a_gap:
				rle_append_modify( attr[i], (None, a_gap))
			
			cs_gap = len(text[i]) - rle_len( cs[i] )
			if cs_gap < 0:
				raise CanvasError("Character Set extends beyond text \n%s\n%s" % (`text[i]`,`cs[i]`) )
			if cs_gap:
				rle_append_modify( cs[i], (None, cs_gap))
			
		self.attr = attr
		self.cs = cs
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
		assert top < self.rows(), "cannot trim %d lines from %d!"%(
			top, self.rows())
		
		if count is None:
			self.pad_trim(0, 0, -top, 0)
		else:
			self.pad_trim(0, 0, -top, count - self.rows())
		
		
	def trim_end(self, end):
		"""Trim lines from the bottom of the canvas.
		
		end -- number of lines to remove from the end
		"""
		assert end > 0, "invalid trim amount %d!"%end
		assert end < self.rows(), "cannot trim %d lines from %d!"%(
			end, self.rows())
		
		self.pad_trim(0, 0, 0, -end)

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
		for text, attr, cs in zip(other.text, other.attr, other.cs):
			oldt = self.text[i]
			olda = self.attr[i]
			oldc = self.cs[i]
			
			if left:
				lt, a, c= trim_text_attr_cs( 
					oldt, olda, oldc, 0, left )
				t = lt + text
				rle_join_modify(a, attr)
				rle_join_modify(c, cs)
			else:
				t, a, c = text, attr, cs

			if right:
				rt, ra, rc = trim_text_attr_cs( 
					oldt, olda, oldc,
					maxcol-right, maxcol )
				t = t + rt
				rle_join_modify(a, ra)
				rle_join_modify(c, rc)
			
			self.text[i] = t
			self.attr[i] = a
			self.cs[i] = c

			i += 1


	def pad_trim(self, left, right, top, bottom):
		"""
		Pad or trim this canvas on all sides.
		
		values > 0 indicate screen columns or rows to pad
		values < 0 indicate screen columns or rows to trim
		"""
		maxcol = self.maxcol
		assert left+right+maxcol > 0 and top+bottom+self.rows() > 0, \
			"trim out of existance? that can't be right"
		
		if top < 0:
			del self.text[:-top]
			del self.attr[:-top]
			del self.cs[:-top]
		if bottom < 0:
			del self.text[bottom:]
			del self.attr[bottom:]
			del self.cs[bottom:]

		if left or right:
			self.pad_trim_lr(left, right)
			maxcol = self.maxcol
		
		if not top and not bottom:
			return
			
		blank = " " * maxcol

		if top > 0:
			self.text = [blank] * top + self.text
			self.attr = [[(None, maxcol)] for i in range(top)] + \
				self.attr
			self.cs = [[(None, maxcol)] for i in range(top)] + \
				self.cs
		if bottom > 0:
			self.text += [blank] * bottom
			self.attr += [[(None, maxcol)] for i in range(bottom)]
			self.cs += [[(None, maxcol)] for i in range(bottom)]
			
		self.translate_coords(0, top)

			
	def pad_trim_left_right(self, left, right):
		"""
		Pad or trim this canvas on the left and right
		
		values > 0 indicate screen columns to pad
		values < 0 indicate screen columns to trim
		"""
		lpad = " " * max(0, left)
		rpad = " " * max(0, right)
		maxcol = self.maxcol

		i = 0
		for text, attr, cs in zip(self.text, self.attr, self.cs):
			if left < 0 or right < 0:
				text, attr, cs = trim_text_attr_cs(
					text, attr, cs, max(0, -left), 
					min(maxcol, maxcol+right))
			if lpad or rpad:
				text = lpad + text + rpad
			if lpad:
				a = [(None, left)]
				c = [(None, left)]
				rle_join_modify(a, attr)
				rle_join_modify(c, cs)
				attr = a
				cs = c

			if rpad:
				rle_append_modify(attr, (None, right))
				rle_append_modify(cs, (None, right))
				
			self.text[i] = text
			self.attr[i] = attr
			self.cs[i] = cs
			i += 1	

		# we now have new maxcol
		self.maxcol = maxcol + left + right
		self.translate_coords(left, 0)
		
		

def CanvasCombine(l):
	"""Stack canvases in l vertically and return resulting canvas."""
	t = []
	a = []
	c = []
	rows = 0
	cols = 0
	cursor = None
	for r in l:
		t += r.text
		a += r.attr
		c += r.cs
		cols = max(cols, r.cols())
		if r.cursor:
			x,y = r.cursor
			cursor = x, y+rows
		rows = len( t )
	d = Canvas(t, a, c, cursor, cols )
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
	c = []
	
	rows = max([cnv.rows() for coff, cnv in l2])
	for r in range(rows):
		t.append([])
		a.append([])
		c.append([])
	
	x = 0 # current start screen col, from coff
	xw = 0 # current end screen col from x and canvas width
	cursor = None
	for coff, cnv in l2:
		x += coff
		if x < xw: 
			raise CanvasError("Join colnum < width of canvas: " +
				`x,xw`)
		if x > xw:
			pad = x-xw
			tpad = " "*pad
			for r in range(rows):
				t[r].append(tpad)
				rle_append_modify(a[r],(None,pad))
				rle_append_modify(c[r],(None,pad))
		xw = x + cnv.cols()
		i = 0
		while i < cnv.rows():
			t[i].append(cnv.text[i])
			rle_join_modify( a[i], cnv.attr[i] )
			rle_join_modify( c[i], cnv.cs[i] )
			i += 1
		if i < rows:
			pad = cnv.cols()
			tpad = " "*pad
			while i < rows:
				t[i].append(tpad)
				rle_append_modify(a[i],(None,pad))
				rle_append_modify(c[i],(None,pad))
				i += 1 
		if cnv.cursor:
			cnv.translate_coords(x, 0)
			cursor = cnv.cursor
	d = Canvas( ["".join(lt) for lt in t], a, c, cursor, xw, False )
	return d


def apply_text_layout( text, attr, ls, maxcol ):
	utext = type(text)==type(u"")
	t = []
	a = []
	c = []
	
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
		linec = []
			
		def attrrange( start_offs, end_offs, destw ):
			"""
			Add attributes based on attributes between
			start_offs and end_offs. 
			"""
			if start_offs == end_offs:
				[(at,run)] = arange(start_offs,end_offs)
				rle_append_modify( linea, ( at, destw ))
				return
			if destw == end_offs-start_offs:
				for at, run in arange(start_offs,end_offs):
					rle_append_modify( linea, ( at, run ))
				return
			# encoded version has different width
			o = start_offs
			for at, run in arange(start_offs, end_offs):
				if o+run == end_offs:
					rle_append_modify( linea, ( at, destw ))
					return
				tseg = text[o:o+run]
				tseg, cs = apply_target_encoding( tseg )
				segw = rle_len(cs)
				
				rle_append_modify( linea, ( at, segw ))
				o += run
				destw -= segw
			
			
		for seg in line_layout:
			#if seg is None: assert 0, ls
			s = LayoutSegment(seg)
			if s.end:
				tseg, cs = apply_target_encoding(
					text[s.offs:s.end])
				line.append(tseg)
				attrrange(s.offs, s.end, rle_len(cs))
				rle_join_modify( linec, cs )
			elif s.text:
				tseg, cs = apply_target_encoding( s.text )
				line.append(tseg)
				attrrange( s.offs, s.offs, len(tseg) )
				rle_join_modify( linec, cs )
			elif s.offs:
				if s.sc:
					line.append(" "*s.sc)
					attrrange( s.offs, s.offs, s.sc )
			else:
				line.append(" "*s.sc)
				linea.append((None, s.sc))
				linec.append((None, s.sc))
			
		t.append("".join(line))
		a.append(linea)
		c.append(linec)
		
	return Canvas(t,a,c, maxcol=maxcol)




