#!/usr/bin/python
#
# Urwid utility functions
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

import utable

try: True # old python?
except: False, True = 0, 1

# Try to determine if using a supported double-byte encoding
import locale
try:
	detected_encoding = locale.getdefaultlocale()[1]
	if not detected_encoding:
		detected_encoding = ""
except ValueError, e:
	# with invalid LANG value python will throw ValueError
	if e.args and e.args[0].startswith("unknown locale"):
		detected_encoding = ""
	else:
		raise

byte_encoding = None
target_encoding = None

def set_encoding( encoding ):
	"""
	Set the byte encoding to assume when processing strings and the
	encoding to use when converting unicode strings.
	"""
	encoding = encoding.lower()

	global byte_encoding, target_encoding

	if encoding in ( 'utf-8', 'utf8' ):
		byte_encoding = "utf8"
	elif encoding in ( 'euc-jp' # JISX 0208 only
			, 'euc-kr', 'euc-cn', 'euc-tw' # CNS 11643 plain 1 only
			, 'gb2312', 'gbk', 'big5', 'cn-gb', 'uhc'
			# these shouldn't happen, should they?
			, 'eucjp', 'euckr', 'euccn', 'euctw', 'cncb' ):
		byte_encoding = "wide"
	else:
		byte_encoding = "narrow"

	# if encoding is valid for conversion from unicode, remember it
	target_encoding = 'ascii'
	try:	
		if encoding:
			u"".encode(encoding)
			target_encoding = encoding
	except LookupError: pass

######################################################################
# Try to set the encoding using the one detected by the locale module
set_encoding( detected_encoding )
######################################################################


def supports_unicode():
	"""
	Return True if python is able to convert non-ascii unicode strings
	to the current encoding.
	"""
	return target_encoding and target_encoding != 'ascii'


class TextLayout:
	def supports_align_mode(self, align):
		"""Return True if align is a supported align mode."""
		return True
	def supports_wrap_mode(self, wrap):
		"""Return True if wrap is a supported wrap mode."""
		return True
	def layout(self, text, width, align, wrap ):
		"""
		Return a layout structure for text.
		
		text -- string in current encoding or unicode string
		width -- number of screen columns available
		align -- align mode for text
		wrap -- wrap mode for text

		Layout structure is a list of line layouts, one per output line.		Line layouts are lists than may contain the following tuples:
		  ( column width of text segment, start offset, end offset )
		  ( number of space characters to insert, offset or None)
		  ( column width of insert text, offset, "insert text" )

		The offset in the last two tuples is used to determine the
		attribute used for the inserted spaces or text respectively.  
		The attribute used will be the same as the attribute at that 
		text offset.  If the offset is None when inserting spaces
		then no attribute will be used.
		"""
		return [[]]

class StandardTextLayout(TextLayout):
	def __init__(self, tab_stops=(), tab_stop_every=8):
		"""
		tab_stops -- list of screen column indexes for tab stops
		tab_stop_every -- repeated interval for following tab stops
		"""
		assert tab_stop_every is None or type(tab_stop_every)==type(0)
		if not tab_stops and tab_stop_every:
			self.tab_stops = (tab_stop_every,)
		self.tab_stops = tab_stops
		self.tab_stop_every = tab_stop_every
	def supports_align_mode(self, align):
		"""Return True if align is 'left', 'center' or 'right'."""
		return align in ('left', 'center', 'right')
	def supports_wrap_mode(self, wrap):
		"""Return True if wrap is 'any', 'space' or 'clip'."""
		return wrap in ('any', 'space', 'clip')
	def layout(self, text, width, align, wrap ):
		"""Return a layout structure for text."""
		segs = self.calculate_text_segments( text, width, wrap )
		return self.align_layout( text, width, segs, wrap, align )

	def align_layout( self, text, width, segs, wrap, align ):
		"""Convert the layout segs to an aligned layout."""
		out = []
		for l in segs:
			sc = line_width(l)
			if sc == width or align=='left':
				out.append(l)
				continue

			if align == 'right':
				out.append([(width-sc, None)] + l)
				continue
			assert align == 'center'
			out.append([((width-sc+1)/2, None)] + l)
		return out
		

	def calculate_text_segments( self, text, width, wrap ):
		"""
		Calculate the segments of text to display given width screen 
		columns to display them.  
		
		text - text to display
		width - number of available screen columns
		wrap - wrapping mode used
		
		Returns a layout structure without aligmnent applied.
		"""
		b = []
		p = 0
		if wrap == 'clip':
			# no wrapping to calculate, so it's easy.
			while p<=len(text):
				n_cr = text.find("\n", p)
				if n_cr == -1: 
					n_cr = len(text)
				sc = calc_width(text, p, n_cr)
				b.append([(sc,p,n_cr),
					# removed character hint
					(0,n_cr)])
				p = n_cr+1
			return b

		
		while p<=len(text):
			# look for next eligible line break
			n_cr = text.find("\n", p)
			if n_cr == -1: 
				n_cr = len(text)
			sc = calc_width(text, p, n_cr)
			if sc == 0:
				# removed character hint
				b.append([(0,n_cr)])
				p = n_cr+1
				continue
			if sc <= width:
				# this segment fits
				b.append([(sc,p,n_cr),
					# removed character hint
					(0,n_cr)])
				
				p = n_cr+1
				continue
			pos, sc = calc_text_pos( text, p, n_cr, width )
			# FIXME: handle pathological width=1 double-byte case
			if wrap == 'any':
				b.append([(sc,p,pos)])
				p = pos
				continue
			assert wrap == 'space'
			if text[pos] == " ":
				# perfect space wrap
				b.append([(sc,p,pos),
					# removed character hint
					(0,pos)])
				p = pos+1
				continue
			if is_wide_char(text, pos):
				# perfect next wide
				b.append([(sc,p,pos)])
				p = pos
				continue
			prev = pos	
			while prev > p:
				prev = move_prev_char(text, p, prev)
				if text[prev] == " ":
					sc = calc_width(text,p,prev)
					b.append([(sc,p,prev),
						# removed character hint
						(0,prev)])
					p = prev+1 
					break
				if is_wide_char(text,prev):
					# wrap after wide char
					next = move_next_char(text, prev, pos)
					sc = calc_width(text,p,next)
					b.append([(sc,p,next)])
					p = next
					break
			else:
				# unwrap previous line space if possible to
				# fit more text (we're breaking a word anyway)
				if b and len(b[-1]) == 2:
					# look for removed space above
					[(p_sc, p_off, p_end),
			       		(h_sc, h_off)] = b[-1]
					if (p_sc < width and h_sc==0 and
						text[h_off] == " "):
						# combine with previous line
						del b[-1]
						p = p_off
						pos, sc = calc_text_pos( 
							text, p, n_cr, width )
						b.append([(sc,p,pos)])
						# check for trailing " " or "\n"
						p = pos
						if p < len(text) and (
							text[p] in (" ","\n")):
							# removed character hint
							b[-1].append((0,p))
							p += 1
						continue
						
						
				# force any char wrap
				b.append([(sc,p,pos)])
				p = pos
		return b



######################################
# default layout object to use
default_layout = StandardTextLayout()
######################################

	
class LayoutSegment:
	def __init__(self, seg):
		"""Create object from line layout segment structure"""
		
		assert type(seg) == type(()), `seg`
		assert len(seg) in (2,3), `seg`
		
		self.sc, self.offs = seg[:2]
		
		assert type(self.sc) == type(0), `self.sc`
		
		if len(seg)==3:
			assert type(self.offs) == type(0), `self.offs`
			assert self.sc > 0, `seg`
			t = seg[2]
			if type(t) == type(""):
				self.text = t
				self.end = None
			else:
				assert type(t) == type(0), `t`
				self.text = None
				self.end = t
		else:
			assert len(seg) == 2, `seg`
			if self.offs is not None:
				assert self.sc >= 0, `seg`
				assert type(self.offs)==type(0)
			self.text = self.end = None
			
	def subseg(self, text, start, end):
		"""
		Return a "sub-segment" list containing segment structures 
		that make up a portion of this segment.

		A list is returned to handle cases where wide characters
		need to be replaced with a space character at either edge
		so two or three segments will be returned.
		"""
		if start < 0: start = 0
		if end > self.sc: end = self.sc
		if start >= end:
			return [] # completely gone
		if self.text:
			# use text stored in segment (self.text)
			pad_front = pad_back = 0
			spos = 0
			epos = len(self.text)
			if start>0:
				spos,sc=calc_text_pos(self.text, 0, epos, start)
				if sc < start:
					pad_front = 1
					spos,sc=calc_text_pos(self.text, 0, 
						epos, start+1)
			pos,sc=calc_text_pos(self.text, spos, epos, 
				end-start-pad_front)
			if sc < end-start-pad_front:
				pad_back = 1
			return [(sc+pad_back+pad_front, self.offs,
				" "*pad_front+self.text[spos:pos]+" "*pad_back)]
		elif self.end:
			# use text passed as parameter (text)
			l = []
			spos = self.offs
			epos = self.end
			pad_front = 0
			if start>0:
				spos,sc=calc_text_pos(text, spos, epos, start)
				if sc < start:
					pad_front=1
					l.append((1,spos))
					spos,sc=calc_text_pos(text, self.offs, 
						epos, start+1)
			pos,sc=calc_text_pos(text, spos, epos, 
				end-start-pad_front)
			if sc < end-start-pad_front:
				l.append((sc, spos, pos))
				l.append((1, pos))
				return l
			l.append((sc, spos, pos))
			return l
		else:
			# simple padding adjustment
			return [(end-start,self.offs)]


		
def move_prev_char( text, start_offs, end_offs ):
	"""
	Return the position of the character before end_offs.
	"""
	assert start_offs < end_offs
	if type(text) == type(u""):
		return end_offs-1
	assert type(text) == type("")
	if byte_encoding == "utf8":
		o = end_offs-1
		while ord(text[o])&0xc0 == 0x80:
			o -= 1
		return o
	if byte_encoding == "wide" and within_double_byte( text,
		start_offs, end_offs-1) == 2:
		return end_offs-2
	return end_offs-1

def move_next_char( text, start_offs, end_offs ):
	"""
	Return the position of the character after start_offs.
	"""
	assert start_offs < end_offs
	if type(text) == type(u""):
		return start_offs+1
	assert type(text) == type("")
	if byte_encoding == "utf8":
		o = start_offs+1
		while o<end_offs and ord(text[o])&0xc0 == 0x80:
			o += 1
		return o
	if byte_encoding == "wide" and within_double_byte(text, 
		start_offs, start_offs) == 1:
		return start_offs +2
	return start_offs+1
		
def is_wide_char( text, offs ):
	"""
	Test if the character at offs within text is wide.
	"""
	if type(text) == type(u""):
		o = ord(text[offs])
		return utable.get_width(o) == 2
	assert type(text) == type("")
	if byte_encoding == "utf8":
		o, n = utable.decode_one(text, offs)
		return utable.get_width(o) == 2
	if byte_encoding == "wide":
		return within_double_byte(text, offs, offs) == 1
	return False

def line_width( segs ):
	"""
	Return the screen column width of one line of a text layout structure.

	This function ignores any existing shift applied to the line,
	represended by an (amount, None) tuple at the start of the line.
	"""
	sc = 0
	seglist = segs
	if segs and len(segs[0])==2 and segs[0][1]==None:
		seglist = segs[1:]
	for s in seglist:
		sc += s[0]
	return sc

def shift_line( segs, amount ):
	"""
	Return a shifted line from a layout structure to the left or right.
	segs -- line of a layout structure
	amount -- screen columns to shift right (+ve) or left (-ve)
	"""
	assert type(amount)==type(0), `amount`
	
	if segs and len(segs[0])==2 and segs[0][1]==None:
		# existing shift
		amount += segs[0][0]
		if amount:
			return [(amount,None)]+segs[1:]
		return segs[1:]
			
	if amount:
		return [(amount,None)]+segs
	return segs
	

def trim_line( segs, text, start, end ):
	"""
	Return a trimmed line of a text layout structure.
	text -- text to which this layout structre applies
	start -- starting screen column
	end -- ending screen column
	"""
	l = []
	x = 0
	for seg in segs:
		sc = seg[0]
		if start or sc < 0:
			if start >= sc:
				start -= sc
				x += sc
				continue
			s = LayoutSegment(seg)
			if x+sc >= end:
				# can all be done at once
				return s.subseg( text, start, end-x )
			l += s.subseg( text, start, sc )
			start = 0
			x += sc
			continue
		if x >= end:
			break
		if x+sc > end:
			s = LayoutSegment(seg)
			l += s.subseg( text, 0, end-x )
			break
		l.append( seg )
	return l


def calc_width( text, start_offs, end_offs ):
	"""
	Return the screen column width of text between start_offs and end_offs.
	"""
	assert start_offs <= end_offs, `start_offs, end_offs`
	utfs = (type(text) == type("") and byte_encoding == "utf8")
	if type(text) == type(u"") or utfs:
		i = start_offs
		sc = 0
		n = 1 # number to advance by
		while i < end_offs:
			if utfs:
				o, n = utable.decode_one(text, i)
			else:
				o = ord(text[i])
				n = i + 1
			w = utable.get_width(ord(text[i]))
			i = n
			sc += w
		return sc
	assert type(text) == type(""), `text`
	# "wide" and "narrow"
	return end_offs - start_offs
	
			
def calc_text_pos( text, start_offs, end_offs, pref_col ):
	"""
	Calculate the closest position to the screen column pref_col in text
	where start_offs is the offset into text assumed to be screen column 0
	and end_offs is the end of the range to search.
	
	Returns (position, actual_col).
	"""
	assert start_offs <= end_offs, `start_offs, end_offs`
	utfs = (type(text) == type("") and byte_encoding == "utf8")
	if type(text) == type(u"") or utfs:
		i = start_offs
		sc = 0
		n = 1 # number to advance by
		while i < end_offs:
			if sc == pref_col:
				return i, sc
			if utfs:
				o, n = utable.decode_one(text, i)
			else:
				o = ord(text[i])
				n = i + 1
			w = utable.get_width(ord(text[i]))
			if w+sc > pref_col: 
				return i, sc
			i = n
			sc += w
		return i, sc
	assert type(text) == type(""), `text`
	# "wide" and "narrow"
	i = start_offs+pref_col
	if i >= end_offs:
		return end_offs, end_offs-start_offs
	if byte_encoding == "wide":
		if within_double_byte( text, start_offs, i ) == 2:
			i -= 1
	return i, i-start_offs


def calc_line_pos( text, line_layout, pref_col ):
	"""
	Calculate the closest linear position to pref_col given a
	line layout structure.  Returns None if no position found.
	"""
	closest_sc = None
	closest_pos = None
	current_sc = 0

	if pref_col == 'left':
		for seg in line_layout:
			s = LayoutSegment(seg)
			if s.offs is not None:
				return s.offs
		return
	elif pref_col == 'right':
		for seg in line_layout:
			s = LayoutSegment(seg)
			if s.offs is not None:
				closest_pos = s
		s = closest_pos
		if s is None:
			return
		if s.end is None:
			return s.offs
		return calc_text_pos( text, s.offs, s.end, s.sc-1)[0]

	for seg in line_layout:
		s = LayoutSegment(seg)
		if s.offs is not None:
			if s.end is not None:
				if (current_sc <= pref_col and 
					pref_col < current_sc + s.sc):
					# exact match within this segment
					return calc_text_pos( text, 
						s.offs, s.end,
						pref_col - current_sc )[0]
				elif current_sc <= pref_col:
					closest_sc = current_sc + s.sc - 1
					closest_pos = s
					
			if closest_sc is None or ( abs(pref_col-current_sc)
					< abs(pref_col-closest_sc) ):
				# this screen column is closer
				closest_sc = current_sc
				closest_pos = s.offs
			if current_sc > closest_sc:
				# we're moving past
				break
		current_sc += s.sc
	
	if closest_pos is None or type(closest_pos) == type(0):
		return closest_pos

	# return the last positions in the segment "closest_pos"
	s = closest_pos
	return calc_text_pos( text, s.offs, s.end, s.sc-1)[0]

def calc_pos( text, layout, pref_col, row ):
	"""
	Calculate the closest linear position to pref_col and row given a
	layout structure.
	"""

	if row < 0 or row >= len(layout):
		raise Exception("calculate_pos: out of layout row range")
	
	pos = calc_line_pos( text, layout[row], pref_col )
	if pos is not None:
		return pos
	
	rows_above = range(row-1,-1,-1)
	rows_below = range(row+1,len(layout))
	while rows_above and rows_below:
		if rows_above: 
			r = rows_above.pop(0)
			pos = calc_line_pos(text, layout[r], pref_col)
			if pos is not None: return pos
		if rows_below: 
			r = rows_below.pop(0)
			pos = calc_line_pos(text, layout[r], pref_col)
			if pos is not None: return pos
	return 0


	

def within_double_byte(str, line_start, pos):
	"""Return whether pos is within a double-byte encoded character.
	
	str -- string in question
	line_start -- offset of beginning of line (< pos)
	pos -- offset in question

	Return values:
	0 -- not within dbe char, or double_byte_encoding == False
	1 -- pos is on the 1st half of a dbe char
	2 -- pos is on the 2nd half og a dbe char
	"""
	v = ord(str[pos])

	if v >= 0x40 and v < 0x7f:
		# might be second half of big5, uhc or gbk encoding
		if pos == line_start: return 0
		
		if ord(str[pos-1]) >= 0x81:
			if within_double_byte(str, line_start, pos-1) == 1:
				return 2
		return 0

	if v < 0x80: return 0

	i = pos -1
	while i >= line_start:
		if ord(str[i]) < 0x80:
			break
		i -= 1
	
	if (pos - i) & 1:
		return 1
	return 2
	

def calc_coords( text, layout, pos, clamp=1 ):
	"""
	Calculate the coordinates closest to position pos in text with layout.
	
	text -- raw string or unicode string
	layout -- layout structure applied to text
	pos -- integer position into text
	clamp -- ignored right now
	"""
	closest = None
	y = 0
	for line_layout in layout:
		x = 0
		for seg in line_layout:
			s = LayoutSegment(seg)
			if s.offs is None:
				x += s.sc
				continue
			if s.offs == pos:
				return x,y
			if s.end is not None and s.offs<=pos and s.end>pos:
				x += calc_width( text, s.offs, pos )
				return x,y
			distance = abs(s.offs - pos)
			if s.end is not None and s.end<pos:
				distance = pos - (s.end-1)
			if closest is None or distance < closest[0]:
				closest = distance, (x,y)
			x += s.sc
		y += 1
	
	if closest:
		return closest[1]
	return 0,0


def trans_line_run( trans, line_no ):
	"""Return the number of characters to the right edge of line line_no."""
	
	if line_no == 0:
		prev_epos = 0
	else:
		prev_epos = trans[line_no-1][3]
	l_pad, l_trim, r_trim, epos = trans[line_no]

	return epos - prev_epos + l_pad - l_trim - r_trim

def trans_line_skip( trans, line_no ):
	"""Return the number of characters to the left of line line_no."""
	
	return trans[line_no][0]
	


def fill_attribute_list( attr_list, width, attr ):
	"""Fill None items in attr list with an attribute."""

	o = []
	
	for line in attr_list:
		l = []
		col = 0
		for a, run in line:
			if a is None:
				a = attr
			l.append( (a, run) )
			col += run
		if col < width:
			l.append( (attr, width-col) )
		o.append( l )
	return o
	

def shift_translation_right( trans, shift, width ):
	l = []
	last = 0
	for l_pad, l_trim, r_trim, epos in trans:
		if shift <= l_trim:
			# shift satisfied by reducing l_trim
			l_trim -= shift
		else:
			l_pad = l_pad + shift - l_trim
			if l_pad > width: l_pad = width
			l_trim = 0
		
		if epos - last + l_pad - l_trim - r_trim > width:
			# shifted right side beyond width
			r_trim = epos - last + l_pad - l_trim - width

		last = epos
		l.append( (l_pad, l_trim, r_trim, epos) )
	return l
	
def shift_translation_left( trans, shift, width ):
	l = []
	last = 0
	for l_pad, l_trim, r_trim, epos in trans:
		if shift <= l_pad:
			# shift satisfied by reducing l_pad
			l_pad -= shift
		else:
			l_trim = l_trim + shift - l_pad
			if l_trim > epos - last: l_trim = epos - last
			l_pad = 0

		r_trim = 0
		if epos - last + l_pad - l_trim - r_trim > width:
			r_trim = epos - last + l_pad - l_trim - width
			
		last = epos
		l.append( (l_pad, l_trim, r_trim, epos) )
	
	# Assuming all translation shifting will occur on clipped
	# text, then every line but the last ends with a CR that
	# should be hidden.  This loop trims one character from all
	# but the last line in the translation:
	l_rm_cr = []
	last = 0
	for l_pad, l_trim, r_trim, epos in l[:-1]:
		if r_trim == 0 and l_trim < epos - last: r_trim = 1
		last = epos
		l_rm_cr.append( (l_pad, l_trim, r_trim, epos) )
	l_rm_cr.append( l[-1] )
	
	return l_rm_cr



class TagMarkupException( Exception ): pass

def decompose_tagmarkup( tm ):
	"""Return (text string, attribute list) for tagmarkup passed."""
	
	tl, al = _tagmarkup_recurse( tm, None )
	text = "".join(tl)
	
	if al and al[-1][0] is None:
		del al[-1]
		
	return text, al
	
def _tagmarkup_recurse( tm, attr ):
	"""Return (text list, attribute list) for tagmarkup passed.
	
	tm -- tagmarkup
	attr -- current attribute or None"""
	
	if type(tm) == type(""):
		# text
		return [tm], [(attr, len(tm))]
		
	if type(tm) == type([]):
		# for lists recurse to process each subelement
		rtl = [] 
		ral = []
		for element in tm:
			tl, al = _tagmarkup_recurse( element, attr )
			if ral:
				# merge attributes when possible
				last_attr, last_run = ral[-1]
				top_attr, top_run = al[0]
				if last_attr == top_attr:
					ral[-1] = (top_attr, last_run + top_run)
					del al[-1]
			rtl += tl
			ral += al
		return rtl, ral
		
	if type(tm) == type(()):
		# tuples mark a new attribute boundary
		if len(tm) != 2: 
			raise TagMarkupException, "Tuples must be in the form (attribute, tagmarkup): %s" % `tm`

		attr, element = tm
		return _tagmarkup_recurse( element, attr )
	
	raise TagMarkupException, "Invalid markup element: %s" % `tm`

