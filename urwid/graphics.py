#!/usr/bin/python
#
# Urwid graphics widgets
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

from util import *
from canvas import *
from widget import *

try: True # old python?
except: False, True = 0, 1

class BarGraph(BoxWidget):
	def __init__(self, attlist, hatt=None):
		"""
		BarGraph( [bg, fg, ...], hatt )
		bg -- attribute or (attribute, character) tuple for background
		fg -- attribute or (attribute, character) tuple for bars
		... -- further attributes or tuples for multi-segment bars
		hatt -- attribute or (attribute, character) tuple for horizontal
			lines

		see set_segment_attributes for description of above parameters.
		
		character defaults to space ' ' if only attribute is given.
		"""
		self.set_segment_attributes( attlist, hatt )
		self.set_data([], 1, None)
		self.set_bar_width(None)
		
	def set_segment_attributes(self, attlist, hatt=None ):
		"""
		set_segment_attributes( [bg, fg, ...], hatt )
		bg -- attribute or (attribute, character) tuple for background
		fg -- attribute or (attribute, character) tuple for bars
		... -- further attributes or tuples for multi-segment bars
		hatt -- attribute or (attribute, character) tuple for horizontal
			lines or None

		If hatt is None it will default to (bg's attribute, "_").
		If hatt does not specidy the character it will default to "_".
		
		eg: set_segment_attributes( ['no', ('unsure',"?"), 'yes'] )
		will use the attribute 'no' for the background (the area from
		the top of the graph to the top of the bar), question marks 
		with the attribute 'unsure' will be used for the topmost 
		segment of the bar, and the attribute 'yes' will be used for
		the bottom segment of the bar.
		"""
		self.attr = []
		self.char = []
		assert len(attlist) >= 2, 'must at least specify bg and fg!'
		for a in attlist:
			if type(a)!=type(()):
				self.attr.append(a)
				self.char.append(' ')
			else:
				attr, ch = a
				self.attr.append(attr)
				self.char.append(ch)
		if hatt is None:
			self.hattr = self.attr[0], "_"
		elif type(hatt)!=type(()):
			self.hattr = hatt, "_"
		else:
			self.hattr = hatt
			
		
	
	def set_data(self, bardata, top, hlines=None):
		"""
		Store bar data, bargraph top and horizontal line positions.
		
		bardata -- a list of bar values.
		top -- maximum value for segments within bardata
		hlines -- None or a bar value marking horizontal line positions

		bar values are [ segment1, segment2, ... ] lists where top is 
		the maximal value corresponding to the top of the bar graph and
		segment1, segment2, ... are the values for the top of each 
		segment of this bar.  Simple bar graphs will only have one
		segment in each bar value.

		Eg: if top is 100 and there is a bar value of [ 80, 30 ] then
		the top of this bar will be at 80% of full height of the graph
		and it will have a second segment that starts at 30%.
		"""
		if hlines is not None:
			hlines = hlines[:] # shallow copy
			hlines.sort()
		self.data = bardata, top, hlines
	
	def get_data(self, (maxcol, maxrow)):
		"""
		Return (bardata, top, hlines)
		
		This function is called by render to retrieve the data for
		the graph. It may be overloaded to create a dynamic bar graph.
		
		This implementation will truncate the bardata list returned 
		if not all bars will fit within maxcol.
		"""
		bardata, top, hlines = self.data
		widths = self.calculate_bar_widths((maxcol,maxrow),bardata)
		
		if len(bardata) > len(widths):
			return bardata[:len(widths)], top, hlines

		return bardata, top, hlines
	
	def set_bar_width(self, width):
		"""
		Set a preferred bar width for calculate_bar_widths to use.

		width -- width of bar or None for automatic width adjustment
		"""
		assert width is None or width > 0
		self.bar_width = width
	
	def calculate_bar_widths(self, (maxcol, maxrow), bardata ):
		"""
		Return a list of bar widths, one for each bar in data.
		
		If self.bar_width is None this implementation will stretch 
		the bars across the available space specified by maxcol.
		"""
		
		if self.bar_width is not None:
			return [self.bar_width] * min(
				len(bardata), maxcol/self.bar_width )
		
		if len(bardata) >= maxcol:
			return [1] * maxcol
		
		widths = []
		grow = maxcol
		remain = len(bardata)
		for row in bardata:
			w = int(float(grow) / remain + 0.5)
			widths.append(w)
			grow -= w
			remain -= 1
		return widths
		

	def selectable(self):
		"""
		Return False.
		"""
		return False
	
	def render(self, (maxcol, maxrow), focus=False):
		"""
		Render BarGraph.
		"""
		bardata, top, hlines = self.get_data( (maxcol, maxrow) )
		widths = self.calculate_bar_widths( (maxcol, maxrow), bardata )
		disp = calculate_bargraph_display(bardata, top, widths, maxrow )
		
		shl = [ maxrow+1 ] # ie. never
		if hlines is not None:
			shl = scale_bar_values( hlines, top, maxrow )
			shl = [x-1 for x in shl if x > 0]
			shl.append( maxrow+1 )
			shl.reverse()
        	#assert 0, `shl`
		nexthl = shl.pop()
			
		r = []
		for y_count, row in disp:
			l = []
			lhl = []
			has_hl = nexthl<len(r)+y_count
			for bar_type, width in row:
				a = self.attr[bar_type]
				t = self.char[bar_type] * width
				l.append( (a, t) )
				if has_hl:
					if bar_type == 0:
						a,t = self.hattr
						t *= width
					lhl.append( (a, t) )
			c = Text(l).render( (maxcol,) )
			assert c.rows() == 1, "Invalid characters in BarGraph!"
			if not has_hl:
				r += [c] * y_count
				continue
				
			chl = Text(lhl).render( (maxcol,) )
			assert chl.rows() == 1, "Invalid characters in hline!"
			while y_count:
				if len(r)==nexthl:
					r.append(chl)
					y_count -=1
					while nexthl < len(r):
						nexthl = shl.pop()
					continue
				y_run = min( nexthl-len(r), y_count )
				y_count -= y_run
				r += [c] * y_run
			
		return CanvasCombine(r)



def calculate_bargraph_display( bardata, top, bar_widths, maxrow ):
	"""
	Calculate a rendering of the bar graph described by data, bar_widths
	and height.
	
	bardata -- bar information with same structure as BarGraph.data
	top -- maximal value for bardata segments
	bar_widths -- list of integer column widths for each bar
	maxrow -- rows for display of bargraph
	
	Returns a structure as follows:
	  [ ( y_count, [ ( bar_type, width), ... ] ), ... ]

	The outer tuples represent a set of identical rows. y_count is
	the number of rows in this set, the list contains the data to be
	displayed in the row repeated through the set.

	The inner tuple describes a run of width characters of bar_type.
	bar_type is an integer starting from 0 for the background, 1 for
	the 1st segment, 2 for the 2nd segment etc..

	This function should complete in approximately O(n+m) time, where
	n is the number of bars displayed and m is the number of rows.
	"""

	assert len(bardata) == len(bar_widths)

	maxcol = sum(bar_widths)

	# build intermediate data structure
	bars = len(bardata)
	rows = [None]*maxrow
	def add_segment( seg_num, col, row, width, rows=rows ):
		if rows[row]:
			last_seg, last_col, last_end = rows[row][-1]
			if last_end > col:
				if last_col >= col:
					del rows[row][-1]
				else:
					rows[row][-1] = ( last_seg, 
						last_col, col)
			elif last_seg == seg_num and last_end == col:
				rows[row][-1] = ( last_seg, last_col, 
					last_end+width)
				return
		elif rows[row] is None:
			rows[row] = []
		rows[row].append( (seg_num, col, col+width) )
	
	col = 0
	barnum = 0
	for bar in bardata:
		width = bar_widths[barnum]
		if width < 1:
			continue
		# loop through in reverse order
		tallest = maxrow
		segments = scale_bar_values( bar, top, maxrow )
		for k in range(len(bar)-1,-1,-1): 
			s = segments[k]
			
			if s >= maxrow: 
				continue
			if s < 0:
				s = 0
			if s < tallest:
				# add only properly-overlapped bars
				tallest = s
				add_segment( k+1, col, s, width )
		col += width
		barnum += 1
	
	#print `rows`
	# build rowsets data structure
	rowsets = []
	y_count = 0
	last = [(0,maxcol)]
	
	for r in rows:
		if r is None:
			y_count = y_count + 1
			continue
		if y_count:
			rowsets.append((y_count, last))
			y_count = 0
		
		i = 0 # index into "last"
		la, ln = last[i] # last attribute, last run length
		c = 0 # current column
		o = [] # output list to be added to rowsets
		for seg_num, start, end in r:
			while start > c+ln:
				o.append( (la, ln) )
				i += 1
				c += ln
				la, ln = last[i]
				
			if la == seg_num:
				# same attribute, can combine
				o.append( (la, end-c) )
			else:
				if start-c > 0:
					o.append( (la, start-c) )
				o.append( (seg_num, end-start) )
			
			if end == maxcol:
				i = len(last)
				break
			
			# skip past old segments covered by new one
			while end >= c+ln:
				i += 1
				c += ln
				la, ln = last[i]

			if la != seg_num:
				ln = c+ln-end
				c = end
				continue
			
			# same attribute, can extend
			oa, on = o[-1]
			on += c+ln-end
			o[-1] = oa, on

			i += 1
			c += ln
			if c == maxcol:
				break
			assert i<len(last), `on, maxcol`
			la, ln = last[i]
	
		if i < len(last): 
			o += [(la,ln)]+last[i+1:]	
		last = o
		y_count += 1
	
	if y_count:
		rowsets.append((y_count, last))

	
	return rowsets
			

class GraphVScale(BoxWidget):
	def __init__(self, labels, top):
		"""
		GraphVScale( [(label1 position, label1 markup),...], top )
		label position -- 0 < position < top for the y position
		label markup -- text markup for this label
		top -- top y position

		This widget is a vertical scale for the BarGraph widget that
		can correspond to the BarGraph's horizontal lines
		"""
		self.set_scale( labels, top )
	
	def set_scale(self, labels, top):
		"""
		set_scale( [(label1 position, label1 markup),...], top )
		label position -- 0 < position < top for the y position
		label markup -- text markup for this label
		top -- top y position
		"""
		
		labels = labels[:] # shallow copy
		labels.sort()
		labels.reverse()
		self.pos = []
		self.txt = []
		for y, markup in labels:
			self.pos.append(y)
			self.txt.append( Text(markup) )
		self.top = top
		
	def selectable(self):
		"""
		Return False.
		"""
		return False
	
	def render(self, (maxcol, maxrow), focus=False):
		"""
		Render GraphVScale.
		"""
		pl = scale_bar_values( self.pos, self.top, maxrow )

		r = []
		rows = 0
		blank = Canvas([""])
		for p, t in zip(pl, self.txt):
			p -= 1
			if p >= maxrow: break
			if p < rows: continue
			if p > rows:
				run = p-rows
				r += [blank]*run
				rows += run
			c = t.render((maxcol,))
			rows += c.rows()
			r.append(c)
		if rows < maxrow:
			r += [blank]* (maxrow-rows)
		c = CanvasCombine(r)
		if c.rows()>maxrow:
			c.trim(0,maxrow)
		return c
			
			
	
def scale_bar_values( bar, top, maxrow ):
	"""
	Return a list of bar values aliased to integer values of maxrow.
	"""
	return [maxrow - int(float(v) * maxrow / top + 0.5) for v in bar]


class ProgressBar( FlowWidget ):
	def __init__(self, normal, complete, current=0, done=100):
		"""
		normal -- attribute for uncomplete part of progress bar
		complete -- attribute for complete part of progress bar
		current -- current progress
		done -- progress amount at 100%
		"""
		self.normal = normal
		self.complete = complete
		self.current = current
		self.done = done
	
	def set_completion(self, current ):
		"""
		current -- current progress
		"""
		self.current = current
	
	def rows(self, (maxcol,), focus=False):
		"""
		Return 1.
		"""
		return 1

	def render(self, (maxcol,), focus=False):
		"""
		Render the progress bar.
		"""
		percent = int( self.current*100/self.done )
		if percent < 0: percent = 0
		if percent > 100: percent = 100
			
		txt=Text( str(percent)+" %", 'center', 'clip' )
		c = txt.render((maxcol,))

		ccol = int( self.current*maxcol/self.done )
		if ccol <= 0:
			c.attr = [[(self.normal,maxcol)]]
		elif ccol >= maxcol:
			c.attr = [[(self.complete,maxcol)]]
		else:
			c.attr = [[(self.complete,ccol),
				(self.normal,maxcol-ccol)]]
		return c
	
