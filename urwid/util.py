#!/usr/bin/python
# -*- coding: utf-8 -*-
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

import escape

import encodings
import weakref
from UserList import UserList

try:
	import str_util
except ImportError:
	import old_str_util as str_util

# bring str_util functions into our namespace
calc_text_pos = str_util.calc_text_pos
calc_width = str_util.calc_width
is_wide_char = str_util.is_wide_char
move_next_char = str_util.move_next_char
move_prev_char = str_util.move_prev_char
within_double_byte = str_util.within_double_byte


try: enumerate
except: enumerate = lambda x: zip(range(len(x)),x) # old python


# Try to determine if using a supported double-byte encoding
import locale
try:
	try:
		locale.setlocale( locale.LC_ALL, "" )
	except locale.Error:
		pass
	detected_encoding = locale.getlocale()[1]
	if not detected_encoding:
		detected_encoding = ""
except ValueError, e:
	# with invalid LANG value python will throw ValueError
	if e.args and e.args[0].startswith("unknown locale"):
		detected_encoding = ""
	else:
		raise

_target_encoding = None
_use_dec_special = True


def set_encoding( encoding ):
	"""
	Set the byte encoding to assume when processing strings and the
	encoding to use when converting unicode strings.
	"""
	encoding = encoding.lower()

	global _target_encoding, _use_dec_special

	if encoding in ( 'utf-8', 'utf8', 'utf' ):
		str_util.set_byte_encoding("utf8")
			
		_use_dec_special = False
	elif encoding in ( 'euc-jp' # JISX 0208 only
			, 'euc-kr', 'euc-cn', 'euc-tw' # CNS 11643 plain 1 only
			, 'gb2312', 'gbk', 'big5', 'cn-gb', 'uhc'
			# these shouldn't happen, should they?
			, 'eucjp', 'euckr', 'euccn', 'euctw', 'cncb' ):
		str_util.set_byte_encoding("wide")
			
		_use_dec_special = True
	else:
		str_util.set_byte_encoding("narrow")
		_use_dec_special = True

	# if encoding is valid for conversion from unicode, remember it
	_target_encoding = 'ascii'
	try:	
		if encoding:
			u"".encode(encoding)
			_target_encoding = encoding
	except LookupError: pass


def get_encoding_mode():
	"""
	Get the mode Urwid is using when processing text strings.
	Returns 'narrow' for 8-bit encodings, 'wide' for CJK encodings
	or 'utf8' for UTF-8 encodings.
	"""
	return str_util.get_byte_encoding()


def apply_target_encoding( s ):
	"""
	Return (encoded byte string, character set rle).
	"""
	if _use_dec_special and type(s) == type(u""):
		# first convert drawing characters
		try:
			s = s.translate( escape.DEC_SPECIAL_CHARMAP )
		except NotImplementedError:
			# python < 2.4 needs to do this the hard way..
			for c, alt in zip(escape.DEC_SPECIAL_CHARS, 
					escape.ALT_DEC_SPECIAL_CHARS):
				s = s.replace( c, escape.SO+alt+escape.SI )
	
	if type(s) == type(u""):
		s = s.replace( escape.SI+escape.SO, u"" ) # remove redundant shifts
		s = s.encode( _target_encoding )

	sis = s.split( escape.SO )

	sis0 = sis[0].replace( escape.SI, "" )
	sout = []
	cout = []
	if sis0:
		sout.append( sis0 )
		cout.append( (None,len(sis0)) )
	
	if len(sis)==1:
		return sis0, cout
	
	for sn in sis[1:]:
		sl = sn.split( escape.SI, 1 ) 
		if len(sl) == 1:
			sin = sl[0]
			sout.append(sin)
			rle_append_modify(cout, (escape.DEC_TAG, len(sin)))
			continue
		sin, son = sl
		son = son.replace( escape.SI, "" )
		if sin:
			sout.append(sin)
			rle_append_modify(cout, (escape.DEC_TAG, len(sin)))
		if son:
			sout.append(son)
			rle_append_modify(cout, (None, len(son)))
	
	return "".join(sout), cout
	
	
######################################################################
# Try to set the encoding using the one detected by the locale module
set_encoding( detected_encoding )
######################################################################


def supports_unicode():
	"""
	Return True if python is able to convert non-ascii unicode strings
	to the current encoding.
	"""
	return _target_encoding and _target_encoding != 'ascii'


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

		Layout structure is a list of line layouts, one per output line.
		Line layouts are lists than may contain the following tuples:
		  ( column width of text segment, start offset, end offset )
		  ( number of space characters to insert, offset or None)
		  ( column width of insert text, offset, "insert text" )

		The offset in the last two tuples is used to determine the
		attribute used for the inserted spaces or text respectively.  
		The attribute used will be the same as the attribute at that 
		text offset.  If the offset is None when inserting spaces
		then no attribute will be used.
		"""
		assert 0, ("This function must be overridden by a real"
			" text layout class. (see StandardTextLayout)")
		return [[]]

class StandardTextLayout(TextLayout):
	def __init__(self):#, tab_stops=(), tab_stop_every=8):
		pass
		#"""
		#tab_stops -- list of screen column indexes for tab stops
		#tab_stop_every -- repeated interval for following tab stops
		#"""
		#assert tab_stop_every is None or type(tab_stop_every)==type(0)
		#if not tab_stops and tab_stop_every:
		#	self.tab_stops = (tab_stop_every,)
		#self.tab_stops = tab_stops
		#self.tab_stop_every = tab_stop_every
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

	def pack(self, maxcol, layout):
		"""
		Return a minimal maxcol value that would result in the same
		number of lines for layout.  layout must be a layout structure
		returned by self.layout().
		"""
		maxwidth = 0
		assert layout, "huh? empty layout?: "+`layout`
		for l in layout:
			lw = line_width(l)
			if lw >= maxcol:
				return maxcol
			maxwidth = max(maxwidth, lw)
		return maxwidth			

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
				l = [(0,n_cr)]
				if p!=n_cr:
					l = [(sc, p, n_cr)] + l
				b.append(l)
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
					l = [(0,prev)]
					if p!=prev:
						l = [(sc,p,prev)] + l
					b.append(l)
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
				if b and (len(b[-1]) == 2 or ( len(b[-1])==1 
						and len(b[-1][0])==2 )):
					# look for removed space above
					if len(b[-1]) == 1:
						[(h_sc, h_off)] = b[-1]
						p_sc = 0
						p_off = p_end = h_off
					else:
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
			spos, epos, pad_left, pad_right = calc_trim_text(
				self.text, 0, len(self.text), start, end )
			return [ (end-start, self.offs, " "*pad_left + 
				self.text[spos:epos] + " "*pad_right) ]
		elif self.end:
			# use text passed as parameter (text)
			spos, epos, pad_left, pad_right = calc_trim_text(
				text, self.offs, self.end, start, end )
			l = []
			if pad_left:
				l.append((1,spos-1))
			l.append((end-start-pad_left-pad_right, spos, epos))
			if pad_right:
				l.append((1,epos))
			return l
		else:
			# simple padding adjustment
			return [(end-start,self.offs)]


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



def calc_trim_text( text, start_offs, end_offs, start_col, end_col ):
	"""
	Calculate the result of trimming text.
	start_offs -- offset into text to treat as screen column 0
	end_offs -- offset into text to treat as the end of the line
	start_col -- screen column to trim at the left
	end_col -- screen column to trim at the right

	Returns (start, end, pad_left, pad_right), where:
	start -- resulting start offset
	end -- resulting end offset
	pad_left -- 0 for no pad or 1 for one space to be added
	pad_right -- 0 for no pad or 1 for one space to be added
	"""
	l = []
	spos = start_offs
	pad_left = pad_right = 0
	if start_col > 0:
		spos, sc = calc_text_pos( text, spos, end_offs, start_col )
		if sc < start_col:
			pad_left = 1
			spos, sc = calc_text_pos( text, start_offs, 
				end_offs, start_col+1 )
	run = end_col - start_col - pad_left
	pos, sc = calc_text_pos( text, spos, end_offs, run )
	if sc < run:
		pad_right = 1
	return ( spos, pos, pad_left, pad_right )




def trim_text_attr_cs( text, attr, cs, start_col, end_col ):
	"""
	Return ( trimmed text, trimmed attr, trimmed cs ).
	"""
	spos, epos, pad_left, pad_right = calc_trim_text( 
		text, 0, len(text), start_col, end_col )
	attrtr = rle_subseg( attr, spos, epos )
	cstr = rle_subseg( cs, spos, epos )
	if pad_left:
		al = rle_get_at( attr, spos-1 )
		rle_append_beginning_modify( attrtr, (al, 1) )
		rle_append_beginning_modify( cstr, (None, 1) )
	if pad_right:
		al = rle_get_at( attr, epos )
		rle_append_modify( attrtr, (al, 1) )
		rle_append_modify( cstr, (None, 1) )
	
	return " "*pad_left + text[spos:epos] + " "*pad_right, attrtr, cstr
	
		
def rle_get_at( rle, pos ):
	"""
	Return the attribute at offset pos.
	"""
	x = 0
	if pos < 0:
		return None
	for a, run in rle:
		if x+run > pos:
			return a
		x += run
	return None


def rle_subseg( rle, start, end ):
	"""Return a sub segment of an rle list."""
	l = []
	x = 0
	for a, run in rle:
		if start:
			if start >= run:
				start -= run
				x += run
				continue
			x += start
			run -= start
			start = 0
		if x >= end:
			break
		if x+run > end:
			run = end-x
		x += run	
		l.append( (a, run) )
	return l


def rle_len( rle ):
	"""
	Return the number of characters covered by a run length
	encoded attribute list.
	"""
	
	run = 0
	for v in rle:
		assert type(v) == type(()), `rle`
		a, r = v
		run += r
	return run

def rle_append_beginning_modify( rle, (a, r) ):
	"""
	Append (a, r) to BEGINNING of rle.
	Merge with first run when possible

	MODIFIES rle parameter contents. Returns None.
	"""
	if not rle:
		rle[:] = [(a, r)]
	else:	
		al, run = rle[0]
		if a == al:
			rle[0] = (a,run+r)
		else:
			rle[0:0] = [(al, r)]
			
			
def rle_append_modify( rle, (a, r) ):
	"""
	Append (a,r) to the rle list rle.
	Merge with last run when possible.
	
	MODIFIES rle parameter contents. Returns None.
	"""
	if not rle or rle[-1][0] != a:
		rle.append( (a,r) )
		return
	la,lr = rle[-1]
	rle[-1] = (a, lr+r)

def rle_join_modify( rle, rle2 ):
	"""
	Append attribute list rle2 to rle.
	Merge last run of rle with first run of rle2 when possible.

	MODIFIES attr parameter contents. Returns None.
	"""
	if not rle2:
		return
	rle_append_modify(rle, rle2[0])
	rle += rle2[1:]
		
def rle_product( rle1, rle2 ):
	"""
	Merge the runs of rle1 and rle2 like this:
	eg.
	rle1 = [ ("a", 10), ("b", 5) ]
	rle2 = [ ("Q", 5), ("P", 10) ]
	rle_product: [ (("a","Q"), 5), (("a","P"), 5), (("b","P"), 5) ]

	rle1 and rle2 are assumed to cover the same total run.
	"""
	i1 = i2 = 1 # rle1, rle2 indexes
	if not rle1 or not rle2: return []
	a1, r1 = rle1[0]
	a2, r2 = rle2[0]
	
	l = []
	while r1 and r2:
		r = min(r1, r2)
		rle_append_modify( l, ((a1,a2),r) )
		r1 -= r
		if r1 == 0 and i1< len(rle1):
			a1, r1 = rle1[i1]
			i1 += 1
		r2 -= r
		if r2 == 0 and i2< len(rle2):
			a2, r2 = rle2[i2]
			i2 += 1
	return l	


def rle_factor( rle ):
	"""
	Inverse of rle_product.
	"""
	rle1 = []
	rle2 = []
	for (a1, a2), r in rle:
		rle_append_modify( rle1, (a1, r) )
		rle_append_modify( rle2, (a2, r) )
	return rle1, rle2


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
	
	if type(tm) == type("") or type(tm) == type( u"" ):
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


def is_mouse_event( ev ):
	return type(ev) == type(()) and len(ev)==4 and ev[0].find("mouse")>=0

def is_mouse_press( ev ):
	return ev.find("press")>=0



class MetaSuper(type):
	"""adding .__super"""
	def __init__(cls, name, bases, d):
		super(MetaSuper, cls).__init__(name, bases, d)
		if hasattr(cls, "_%s__super" % name):
			raise AttributeError, "Class has same name as one of its super classes"
		setattr(cls, "_%s__super" % name, super(cls))


class MetaSignals(type):
	"""
	register the list of signals in the class varable signals,
	including signals in superclasses.
	"""
	def __init__(cls, name, bases, d):
		signals = d.get("signals", [])
		for superclass in cls.__bases__:
			signals.extend(getattr(superclass, 'signals', []))
		signals = dict([(x,None) for x in signals]).keys()
		d["signals"] = signals
		Signals.register(cls, signals)
		super(MetaSignals, cls).__init__(name, bases, d)


class Signals(object):
	_connections = weakref.WeakKeyDictionary()
	_supported = {}

	def register(cls, sig_cls, signals):
		cls._supported[sig_cls] = signals
	register = classmethod(register)

	def connect(cls, obj, name, callback, user_arg=None):
		sig_cls = obj.__class__
		if not name in cls._supported.get(sig_cls, []):
			raise NameError, "No such signal %r for object %r" % \
				(name, obj)
		d = cls._connections.setdefault(obj, {})
		d.setdefault(name, []).append((callback, user_arg))
	connect = classmethod(connect)
		
	def disconnect(cls, obj, name, callback, user_arg=None):
		d = cls._connections.get(obj, {})
		if name not in d:
			return
		if (callback, user_arg) not in d[name]:
			return
		d[name].remove((callback, user_arg))
	disconnect = classmethod(disconnect)
 
	def emit(cls, obj, name, *args):
		result = False
		d = cls._connections.get(obj, {})
		for callback, user_arg in d.get(name, []):
			args_copy = args
			if user_arg is not None:
				args_copy = args + [user_arg]
			result |= bool(callback(*args_copy))
		return result
	emit = classmethod(emit)
	


def _call_modified(fn):
	def call_modified_wrapper(self, *args):
		rval = fn(self, *args)
		self._modified()
		return rval
	return call_modified_wrapper

class MonitoredList(UserList):
	def _modified(self):
		pass
	
	def set_modified_callback(self, callback):
		self._modified = callback

	def __repr__(self):
		return "%s.%s(%s)" % (self.__class__.__module__,
			self.__class__.__name__,
			UserList.__repr__(self))

	__add__ = _call_modified(UserList.__add__)
	__delitem__ = _call_modified(UserList.__delitem__)
	__delslice__ = _call_modified(UserList.__delslice__)
	__iadd__ = _call_modified(UserList.__iadd__)
	__imul__ = _call_modified(UserList.__imul__)
	__rmul__ = _call_modified(UserList.__rmul__)
	__setitem__ = _call_modified(UserList.__setitem__)
	__setslice__ = _call_modified(UserList.__setslice__)
	append = _call_modified(UserList.append)
	extend = _call_modified(UserList.extend)
	insert = _call_modified(UserList.insert)
	pop = _call_modified(UserList.pop)
	remove = _call_modified(UserList.remove)
	reverse = _call_modified(UserList.reverse)
	sort = _call_modified(UserList.sort)

